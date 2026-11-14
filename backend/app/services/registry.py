"""服务注册发现业务规则：状态流转、字段校验、并发控制与路由联动。

状态只能按 草稿 → 已注册 → 已下线 → 已注销 单向推进：
- 上线服务：仅草稿可执行，落地一个新的注册版本，路由灰度入口同步纳入；
- 下线服务：仅已注册可执行，路由灰度入口摘除该实例；
- 注销服务：仅已下线可执行，路由规则整体降级，旧分流目标不再可用。

非法动作保持原记录并回失败回执；同一动作并发提交经记录级锁串行化，
只有一个注册版本落地；联动路由失败时注册清单与路由回执同时回退。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.router import RouterService
from app.statemachine import (
    IllegalTransition,
    ensure_transition,
    entry_locks,
    locked_entry,
    rollback_tables,
    snapshot_tables,
)
from app.store import store

MODULE = "registry"
LOG_MODULE = "registry_action_log"
REQUIRED_FIELDS = ["实例编号", "服务名称", "服务地址"]
STATUS_ORDER = ["草稿", "已注册", "已下线", "已注销"]
# 动作 -> 执行该动作所要求的前置状态；目标状态由状态序列推导，杜绝回退/跳级。
ACTION_RULES = {"上线服务": "草稿", "下线服务": "已注册", "注销服务": "已下线"}
# 各注册状态对应的实例健康状态口径
HEALTH_BY_STATUS = {
    "草稿": "待上线",
    "已注册": "健康",
    "已下线": "已隔离",
    "已注销": "已摘除",
}


class RegistryService:
    def __init__(self, router_service: RouterService | None = None) -> None:
        self._locks = entry_locks()
        self._router = router_service or RouterService()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("实例编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def list_action_logs(self, entry_id: int | None = None) -> list[dict[str, Any]]:
        """实例动作记录：按时间倒序返回，可按实例过滤。"""
        rows = store.rows(LOG_MODULE)
        if entry_id is not None:
            rows = [row for row in rows if int(row.get("entry_id", 0)) == entry_id]
        return sorted(rows, key=lambda row: int(row["id"]), reverse=True)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["注册版本"] = 0  # 草稿尚未注册，没有落地的注册版本
        entry["健康状态"] = HEALTH_BY_STATUS[STATUS_ORDER[0]]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"服务实例 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于服务注册发现可执行范围"

        # 同一实例的动作串行化：并发的同一动作只有第一个能通过锁内状态检查。
        with locked_entry(self._locks, MODULE, entry_id):
            current_status = str(entry["status"])
            version_before = int(entry.get("注册版本", 0))
            try:
                target_status = ensure_transition(
                    current_status=current_status,
                    action=action,
                    action_rules=ACTION_RULES,
                    status_order=STATUS_ORDER,
                )
            except IllegalTransition as exc:
                # 非法动作：原记录保持不变，仅落一条失败回执，避免前端重复显示成成功。
                self._append_log(entry, action, current_status, current_status, False, str(exc), version_before)
                return None, str(exc)

            # 跨模块联动先做快照：注册清单与路由灰度任一步失败都整体回退。
            snapshot = snapshot_tables(store, [MODULE, self._router.module])
            try:
                self._apply_registry_change(entry, action, target_status)
                self._sync_router(entry, action)
            except Exception as exc:  # noqa: BLE001 - 联动失败必须回滚并回执失败
                rollback_tables(store, [MODULE, self._router.module], snapshot)
                message = f"{action}联动路由失败，注册清单与路由已同时回退：{exc}"
                self._append_log(entry, action, current_status, current_status, False, message, version_before)
                return None, message

            message = f"服务实例已{action}"
            self._append_log(entry, action, current_status, target_status, True, message)
            return entry, message

    def _apply_registry_change(self, entry: dict[str, Any], action: str, target_status: str) -> None:
        if action == "上线服务":
            # 只有成功上线才会产生新的注册版本；并发的第二次动作在状态检查处即被拦下。
            entry["注册版本"] = int(entry.get("注册版本", 0)) + 1
        entry["status"] = target_status
        entry["健康状态"] = HEALTH_BY_STATUS[target_status]
        entry["pending"] = target_status != STATUS_ORDER[-1]
        entry["abnormal"] = target_status == "已下线"

    def _sync_router(self, entry: dict[str, Any], action: str) -> None:
        """注册状态变更同步到路由灰度入口，保证旧路由目标不残留。"""
        instance_no = str(entry["实例编号"])
        if action == "上线服务":
            self._router.attach_canary_target(instance_no)
        elif action == "下线服务":
            self._router.detach_canary_target(instance_no)
        elif action == "注销服务":
            self._router.degrade_rules_targeting(
                instance_no, service_name=str(entry["服务名称"])
            )

    def _append_log(
        self,
        entry: dict[str, Any],
        action: str,
        from_status: str,
        to_status: str,
        ok: bool,
        message: str,
        version: int | None = None,
    ) -> None:
        rows = store.rows(LOG_MODULE)
        log = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "entry_id": entry["id"],
            "实例编号": entry["实例编号"],
            "服务名称": entry["服务名称"],
            "动作": action,
            "from_status": from_status,
            "to_status": to_status,
            "注册版本": int(entry.get("注册版本", 0)) if version is None else version,
            "ok": ok,
            "回执": message,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(log)
