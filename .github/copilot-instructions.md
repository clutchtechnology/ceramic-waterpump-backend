# Ceramic Waterpump Backend - AI Coding Guidelines

> **Project Identity**: `ceramic-waterpump-backend` (FastAPI + InfluxDB + Polling)
> **Role**: AI Assistant for Industrial IoT Backend Development
> **Core Philosophy**: **Occam's Razor** - Do not multiply entities without necessity. Keep logic simple, stateless where possible, and robust.

## 1. 核心架构原则 (Core Principles)

1.  **稳定性优先 (Stability First)**:
    - **Lifespan Management**: 使用 `main.py` 中的 `lifespan` 上下文管理器严格管理 `start_polling`/`stop_polling` 和数据库连接。
    - **Resource Cleanup**: 确保所有后台任务 (BackgroundTasks)、线程池在关闭时优雅退出。

2.  **配置驱动 (Configuration Driven)**:
    - **config_waterpump.yaml**: 定义水泵和传感器的数据点映射。
    - **原则**: 新增设备或调整参数时，优先修改 YAML 配置，避免硬编码。

3.  **高可靠性轮询 (High Reliability Polling)**:
    - **批量写入**: 采集数据缓存后批量写入 InfluxDB，减少 I/O 压力。
    - **Mock 模式**: 当 `MOCK_MODE=true` 时，无缝切换到 `mock_service.py` 生成数据，保障前端开发不依赖硬件。
    - **异常处理**: 轮询循环必须包含宽泛的 `try-except`，捕获所有已知/未知异常并记录日志，**绝不允许服务崩溃退出**。

## 2. 数据流架构 (Data Flow Architecture)

```mermaid
graph TD
    Source[Data Source (Mock / PLC / Sensor)] -->|Polling| PollingService

    subgraph PollingService
        direction TB
        Logic[Business Logic]
        Buffer[Batch Buffer]
        LocalCache[SQLite Cache (Fallback)]
    end

    Source --> Logic
    Logic --> Buffer

    Buffer -->|Batch Write| InfluxDB[(InfluxDB)]
    Buffer -.->|Fail| LocalCache
    LocalCache -.->|Retry| InfluxDB

    InfluxDB -->|Query| API[FastAPI Endpoints]
```

## 3. 关键文件结构 (Project Structure)

```text
ceramic-waterpump-backend/
├── main.py                           # FastAPI 入口 (Lifespan, Logging Config)
├── config.py                         # 全局配置 (Env)
├── configs/                          # [配置层]
│   ├── config_waterpump.yaml         # 设备配置
│   ├── db_mappings.yaml              # ★ DB块映射总表 (Poll Config)
│   ├── plc_modules.yaml              # ★ 基础模块定义 (Modules)
│   └── status_waterpump.yaml         # 状态映射
├── app/
│   ├── core/
│   │   ├── influxdb.py               # InfluxDB 读写封装
│   │   ├── local_cache.py            # SQLite 本地降级缓存
│   │   └── influx_migration.py       # 自动Schema迁移
│   ├── plc/                          # [PLC 层]
│   │   ├── plc_manager.py            # 连接管理器 (Reconnect)
│   │   └── parser_waterpump.py       # 水泵数据解析器
│   ├── tools/                        # [转换层]
│   │   └── converter_waterpump.py    # 水泵数据转换
│   ├── services/                     # [服务层]
│   │   ├── polling_service.py        # 核心轮询逻辑 (Data Collection)
│   │   ├── mock_service.py           # 模拟数据生成
│   │   └── resource_monitor.py       # 系统资源监控
│   └── routers/                      # [API 路由]
│       ├── api_router.py             # 路由汇总
│       ├── realtime.py               # 实时数据接口
│       ├── history.py                # 历史数据接口
│       └── settings.py               # 阈值配置接口
├── data/
│   └── thresholds.json               # 阈值持久化存储
└── docker-compose.yml                # 容器编排
```

## 4. 核心实现规范 (Implementation Specs)

### 4.1 轮询服务设计 (`polling_service.py`)

- **死循环防护**: 轮询必须在 `while check_running():` 循环中运行，并包含 `await asyncio.sleep()` 防止 CPU 100%。
- **错误隔离**: 单个设备的采集失败不应中断整个轮询线程。

### 4.2 数据解析与转换流程

1.  **Parse (解析)**: `Parser` 类读取 `config_*.yaml` 中的偏移量，将 PLC `bytes` 解析为 Python 字典 (Raw Values)。
    - _Tip_: Parser 不进行单位转换，只按 Byte/Word/Real 读取数值。
2.  **Convert (转换)**: `Converter` 类将 Raw Values 转换为物理量 (Physical Values)。
    - 例: 将原始电压值转换为实际电压 V。
    - 例: 计算功率因数、累计能耗等。

### 4.3 InfluxDB 设计

- **Measurement**: `sensor_data` (单表存储)。
- **Tags**: `device_id`, `device_type`, `module_type`。
- **Fields**: `voltage`, `current`, `power`, `vibration`, `pressure`... (动态字段)。

## 5. API 接口规范 (API Specifications)

### 5.1 接口设计

- **Base URL**: `http://localhost:8081` (注意与 Workshop App 区分端口)
- **Endpoints**:
  - `GET /api/realtime/batch`: 获取所有设备最新数据。
  - `GET /api/history`: 历史数据查询 (注意 InfluxDB 查询性能优化)。
  - `POST /api/settings`: 阈值配置更新。
  - `GET /api/health`: 系统健康检查 (InfluxDB连接状态, 队列长度)。

### 5.2 响应格式

```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2025-01-20T10:30:00Z",
  "error": null
}
```

### 5.3 错误处理

- **4xx**: 客户端错误（参数校验失败）
- **5xx**: 服务端错误（数据库连接失败、PLC 通信异常）
- 所有错误必须返回结构化的 JSON 响应，包含错误码和描述

## 6. 日志规范 (Logging Standards)

- **格式**: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- **级别**: 生产环境 INFO，调试环境 DEBUG。
- **内容**: 关键操作（启动、停止、配置变更、严重错误）必须记录。
- **Traceback**: 报错时产生的日志必须包含 traceback 和上下文信息。

## 7. 开发命令 (Development)

```powershell
# 启动 Mock 模式
docker compose --profile mock up -d

# 本地运行
uvicorn main:create_app --factory --host 0.0.0.0 --port 8081 --reload

# 运行测试
pytest tests/ -v

# 代码检查
ruff check .
```

## 8. 复用指南 (Replication Guide)

如果需要基于此架构创建新项目（如：`ceramic-new-factory-backend`）：

1.  **结构复制**: 完整复制 `app/` 和 `configs/` 目录。
2.  **配置适配**:
    - 修改 `configs/db_mappings.yaml` 中的 DB 块号和大小。
    - 根据新 PLC 的变量表，更新 `configs/config_*.yaml`。
    - 若有新设备类型，在 `configs/plc_modules.yaml` 定义新模块结构。
3.  **解析器调整**:
    - 若设备结构变化，在 `app/plc/` 下新增或修改 `Parser` 类。
    - 确保 `polling_service.py` 中注册了新的 `Parser`。
4.  **转换逻辑**: 若有特殊计算（如流量累积、速度计算），在 `app/tools/` 新增 Converter。
5.  **端口配置**: 修改 `docker-compose.yml` 和 `main.py` 中的端口，避免冲突。

## 9. 技术约定 (Technical Conventions)

### 9.1 依赖管理

```yaml
framework: FastAPI
database: InfluxDB 2.7
cache: SQLite (local fallback)
async: asyncio + uvicorn
validation: Pydantic v2
```

### 9.2 代码风格

- 使用 `ruff` 进行代码格式化和检查
- 类型注解 (Type Hints) 必须完整
- 函数/方法必须有 docstring

## 10. Troubleshooting

| Issue              | Solution                           |
| ------------------ | ---------------------------------- |
| InfluxDB 连接失败  | 检查 Docker 容器状态，确认端口映射 |
| 轮询服务无数据     | 检查 Mock 模式是否启用，查看日志   |
| API 响应超时       | 检查 InfluxDB 查询性能，添加索引   |
| 内存持续增长       | 检查批量缓冲区是否正确刷新         |
| 服务启动后立即退出 | 检查 lifespan 管理器，查看启动日志 |

---

**AI 指令**:

1. **简单至上**: 能用简单逻辑实现的，不要引入复杂的类层次结构。
2. **防崩溃**: 任何涉及 I/O (网络, 数据库) 的操作必须有超时和重试机制。
3. **清晰日志**: 报错时产生的日志必须包含 traceback 和上下文信息。
4. **配置优先**: 在修改代码时，优先检查 `configs/` 目录，通过配置驱动逻辑。
5. **分层架构**: 保持 "Router-Service-Core" 的分层结构，职责清晰。
