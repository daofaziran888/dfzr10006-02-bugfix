"""查询路由分发业务规则：状态流转、灰度入口维护与注册联动。

路由规则状态只能按 草稿 → 生效中 → 已降级 → 已关闭 单向推进：
- 启用规则：仅草稿可执行；
- 降级路由：仅生效中可执行；
- 关闭规则：仅已降级可执行。

同时承接服务注册发现的联动：实例上线纳入灰度标记、下线摘除灰度目标、
注销则把仍指向该实例的规则整体降级，杜绝旧分流目标残留。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.statemachine import (
    IllegalTransition,
    ensure_transition,
    entry_locks,
    locked_entry,
)
from app.store import store

MODULE = "router"
LOG_MODULE = "router_action_log"
REQUIRED_FIELDS = ["规则编号", "匹配条件", "目标服务"]
STATUS_ORDER = ["草稿", "生效中", "已降级", "已关闭"]
ACTION_RULES = {"启用规则": "草稿", "降级路由": "生效中", "关闭规则": "已降级"}
CANARY_SEP = "|"


class RouterService:
    def __init__(self) -> None:
        self._locks = entry_locks()

    @property
    def module(self) -> str:
        return MODULE

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
            rows = [row for row in rows if keyword in str(row.get("规则编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def list_action_logs(self, entry_id: int | None = None) -> list[dict[str, Any]]:
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
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"路由规则 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于查询路由分发可执行范围"

        with locked_entry(self._locks, MODULE, entry_id):
            current_status = str(entry["status"])
            try:
                target_status = ensure_transition(
                    current_status=current_status,
                    action=action,
                    action_rules=ACTION_RULES,
                    status_order=STATUS_ORDER,
                )
            except IllegalTransition as exc:
                self._append_log(entry, action, current_status, current_status, False, str(exc))
                return None, str(exc)

            entry["status"] = target_status
            entry["pending"] = target_status != STATUS_ORDER[-1]
            entry["abnormal"] = target_status == "已降级"
            message = f"路由规则已{action}"
            self._append_log(entry, action, current_status, target_status, True, message)
            return entry, message

    # ---- 服务注册发现联动：路由灰度入口维护 ----

    def attach_canary_target(self, instance_no: str) -> None:
        """实例上线：把实例编号纳入生效规则的灰度标记，作为可分流目标。"""
        for rule in store.rows(MODULE):
            if rule.get("status") != "生效中":
                continue
            targets = self._canary_targets(rule)
            if instance_no not in targets:
                targets.append(instance_no)
                rule["灰度标记"] = CANARY_SEP.join(targets)

    def detach_canary_target(self, instance_no: str) -> None:
        """实例下线：从所有规则的灰度标记中摘除该实例，下线实例不再参与分流。"""
        for rule in store.rows(MODULE):
            targets = self._canary_targets(rule)
            if instance_no in targets:
                targets.remove(instance_no)
                rule["灰度标记"] = CANARY_SEP.join(targets) if targets else "无灰度目标"

    def degrade_rules_targeting(self, instance_no: str, service_name: str) -> None:
        """实例注销：仍指向该实例（灰度标记或目标服务命中）的生效规则强制降级。"""
        for rule in store.rows(MODULE):
            if rule.get("status") != "生效中":
                continue
            targets = self._canary_targets(rule)
            hit_canary = instance_no in targets
            hit_service = service_name and str(rule.get("目标服务", "")) == service_name
            if not hit_canary and not hit_service:
                continue
            if hit_canary:
                targets.remove(instance_no)
                rule["灰度标记"] = CANARY_SEP.join(targets) if targets else "无灰度目标"
            rule["status"] = "已降级"
            rule["pending"] = True
            rule["abnormal"] = True
            self._append_log(
                rule,
                "降级路由",
                "生效中",
                "已降级",
                True,
                f"服务实例 {instance_no} 已注销，路由规则联动降级",
            )

    def _canary_targets(self, rule: dict[str, Any]) -> list[str]:
        raw = str(rule.get("灰度标记") or "")
        if not raw or raw == "无灰度目标":
            return []
        return [item.strip() for item in raw.split(CANARY_SEP) if item.strip()]

    def _append_log(
        self,
        entry: dict[str, Any],
        action: str,
        from_status: str,
        to_status: str,
        ok: bool,
        message: str,
    ) -> None:
        rows = store.rows(LOG_MODULE)
        log = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "entry_id": entry["id"],
            "规则编号": entry["规则编号"],
            "目标服务": entry.get("目标服务"),
            "动作": action,
            "from_status": from_status,
            "to_status": to_status,
            "ok": ok,
            "回执": message,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        rows.append(log)
