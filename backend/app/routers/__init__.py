"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import registry as router_registry
from app.routers import router as router_router
from app.routers import cache as router_cache
from app.routers import limiter as router_limiter
from app.routers import orchestra as router_orchestra
from app.routers import trace as router_trace
from app.routers import diagnose as router_diagnose
from app.routers import schema as router_schema
from app.routers import subscribe as router_subscribe
from app.routers import transform as router_transform
from app.routers import mock as router_mock
from app.routers import gateway as router_gateway
from app.routers import metric as router_metric
from app.routers import whitelist as router_whitelist
from app.routers import balance as router_balance
from app.routers import rollback as router_rollback

ROUTERS = [router_registry, router_router, router_cache, router_limiter, router_orchestra, router_trace, router_diagnose, router_schema, router_subscribe, router_transform, router_mock, router_gateway, router_metric, router_whitelist, router_balance, router_rollback]
