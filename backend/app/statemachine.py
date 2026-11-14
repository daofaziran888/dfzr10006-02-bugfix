"""业务状态机通用件：合法流转校验、按记录串行化与跨模块回滚。

各业务模块的动作只允许沿着固定状态序列单向推进。这里把三件容易写错的事统一收口：

1. ``ensure_transition`` —— 校验「当前状态 + 动作」是否合法，非法动作保持原记录不动；
2. ``entry_locks`` / ``locked_entry`` —— 同一记录的并发动作串行化，配合锁内二次检查，
   保证同一动作并发提交时只有一个注册版本落地；
3. ``snapshot_tables`` / ``rollback_tables`` —— 跨模块联动（注册清单 + 路由灰度）时，
   任一步失败都把已改动的表整体回退，回执与数据同时失败，不允许半截状态残留。
"""
from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator


class IllegalTransition(Exception):
    """当前状态不允许执行该动作时抛出，调用方据此返回失败回执且不改原记录。"""


def ensure_transition(
    *,
    current_status: str,
    action: str,
    action_rules: dict[str, str],
    status_order: list[str],
) -> str:
    """校验动作合法性并返回目标状态。

    ``action_rules`` 的键是动作、值是该动作要求的前置状态；目标状态取状态序列里
    前置状态的下一个状态。前置状态不匹配或已到终态时抛 :class:`IllegalTransition`，
    原记录保持不变。
    """
    if action not in action_rules:
        raise IllegalTransition(f"动作「{action}」不在允许的动作范围内")
    required_status = action_rules[action]
    if current_status != required_status:
        raise IllegalTransition(
            f"当前状态为「{current_status}」，仅「{required_status}」状态可执行{action}，已保持原记录"
        )
    try:
        index = status_order.index(required_status)
    except ValueError as exc:  # 配置错误：前置状态不在状态序列里
        raise IllegalTransition(f"状态「{required_status}」不在允许的状态序列里") from exc
    if index + 1 >= len(status_order):
        raise IllegalTransition(f"状态「{current_status}」已到终态，无可执行动作")
    return status_order[index + 1]


def entry_locks() -> dict[tuple[str, int], threading.Lock]:
    """每个模块、每条记录一把锁，惰性创建。"""
    return defaultdict(threading.Lock)


@contextmanager
def locked_entry(locks: dict[tuple[str, int], threading.Lock], module: str, entry_id: int) -> Iterator[None]:
    """串行化同一条记录上的并发动作；不同记录之间互不阻塞。"""
    lock = locks[(module, entry_id)]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def snapshot_tables(store: Any, modules: list[str]) -> dict[str, list[dict[str, Any]]]:
    """对涉及的表做深拷贝快照，供失败时整体回滚。"""
    return {module: [dict(row) for row in store.rows(module)] for module in modules}


def rollback_tables(store: Any, modules: list[str], snapshot: dict[str, list[dict[str, Any]]]) -> None:
    """把指定表恢复到快照内容（逐条复制，保留表对象本身的引用）。"""
    for module in modules:
        table = store.rows(module)
        table.clear()
        table.extend(dict(row) for row in snapshot[module])
