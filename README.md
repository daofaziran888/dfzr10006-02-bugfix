# 实时数据服务总线平台

面向业务系统的一站式实时数据服务总线平台。覆盖数据服务注册与发现、查询路由分发、结果缓存加速、调用限流降级、服务编排组合、调用链追踪与服务健康诊断的完整数据服务链路。

这是一个前后端分离的管理平台：前端 React + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 React + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 服务注册发现 | `registry` | 服务实例 | 实例编号、服务名称、服务地址 |
| 查询路由分发 | `router` | 路由规则 | 规则编号、匹配条件、目标服务 |
| 结果缓存加速 | `cache` | 缓存配置 | 配置编号、缓存键名、过期秒数 |
| 调用限流降级 | `limiter` | 限流规则 | 规则编号、限流对象、限流算法 |
| 服务编排组合 | `orchestra` | 编排流程 | 流程编号、流程名称、编排步骤 |
| 调用链追踪 | `trace` | 追踪记录 | 记录编号、调用链ID、服务名称 |
| 服务健康诊断 | `diagnose` | 诊断报告 | 报告编号、诊断对象、健康分值 |
| 数据接口契约 | `schema` | 接口定义 | 接口编号、接口名称、请求方法 |
| 数据订阅推送 | `subscribe` | 订阅任务 | 任务编号、数据源名称、推送目标 |
| 数据加工转换 | `transform` | 加工规则 | 规则编号、输入格式、输出格式 |
| 数据模拟服务 | `mock` | 模拟配置 | 配置编号、模拟对象、数据模板 |
| 接入网关管理 | `gateway` | 网关配置 | 配置编号、网关名称、监听端口 |
| 服务指标采集 | `metric` | 指标采集器 | 采集器编号、监控对象、指标名称 |
| 调用来源管理 | `whitelist` | 来源登记 | 登记编号、应用名称、调用标识 |
| 负载均衡策略 | `balance` | 均衡策略 | 策略编号、策略名称、均衡算法 |
| 服务版本回退 | `rollback` | 版本快照 | 快照编号、服务名称、版本号 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数据分析与数据应用
