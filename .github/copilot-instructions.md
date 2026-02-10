# Ceramic Waterpump Backend - AI Coding Guidelines

> **Project Identity**: `ceramic-waterpump-backend` (FastAPI + WebSocket + InfluxDB + Polling)
> **Role**: AI Assistant for Industrial IoT Backend Development
> **Core Philosophy**: **Occam's Razor** - Do not multiply entities without necessity. Keep logic simple, stateless where possible, and robust.

## 1. 核心架构原则 (Core Principles)

1.  **WebSocket 优先 (WebSocket First)**:
    - **实时推送**: 使用 WebSocket (`ws://host:port/ws/realtime`) 作为主要数据传输方式，提供更快的响应速度。
    - **HTTP 兼容**: 保留 HTTP API 端点作为降级方案和历史数据查询接口。
    - **连接管理**: 使用 `ws_manager.py` 统一管理所有 WebSocket 连接、订阅和推送任务。

2.  **本地部署优先 (Local Deployment First)**:
    - **InfluxDB 本地化**: 不使用 Docker 部署 InfluxDB，改用本地安装的 InfluxDB 实例，减少网络延迟。
    - **直连优势**: 本地部署提供更快的数据写入和查询响应。
    - **配置灵活**: 通过环境变量 `INFLUX_URL` 配置本地或远程 InfluxDB 地址。

3.  **稳定性优先 (Stability First)**:
    - **Lifespan Management**: 使用 `main.py` 中的 `lifespan` 上下文管理器严格管理 `start_polling`/`stop_polling`、WebSocket 推送任务和数据库连接。
    - **Resource Cleanup**: 确保所有后台任务 (WebSocket 推送、轮询服务、资源监控) 在关闭时优雅退出。

4.  **配置驱动 (Configuration Driven)**:
    - **config_waterpump.yaml**: 定义水泵和传感器的数据点映射。
    - **原则**: 新增设备或调整参数时，优先修改 YAML 配置，避免硬编码。

5.  **高可靠性轮询 (High Reliability Polling)**:
    - **批量写入**: 采集数据缓存后批量写入 InfluxDB，减少 I/O 压力。
    - **Mock 模式**: 当 `USE_MOCK_DATA=true` 时，无缝切换到 `mock_service.py` 生成数据，保障前端开发不依赖硬件。
    - **异常处理**: 轮询循环必须包含宽泛的 `try-except`，捕获所有已知/未知异常并记录日志，**绝不允许服务崩溃退出**。

## 2. 数据流架构 (Data Flow Architecture)

```mermaid
graph TD
    Source[Data Source (Mock / PLC / Sensor)] -->|Polling 5s| PollingService

    subgraph PollingService
        direction TB
        Logic[Business Logic]
        Buffer[Memory Cache]
        LocalCache[SQLite Cache (Fallback)]
    end

    Source --> Logic
    Logic --> Buffer

    Buffer -->|Batch Write| InfluxDB[(Local InfluxDB)]
    Buffer -.->|Fail| LocalCache
    LocalCache -.->|Retry| InfluxDB

    Buffer -->|Real-time| WSManager[WebSocket Manager]
    WSManager -->|Push 0.1s| Clients[WebSocket Clients]

    InfluxDB -->|Query| HTTPEndpoints[HTTP API Endpoints]
    Buffer -->|Query| HTTPEndpoints
```

## 3. 关键文件结构 (Project Structure)

```text
ceramic-waterpump-backend/
├── main.py                           # FastAPI 入口 (Lifespan, WebSocket + HTTP)
├── config.py                         # 全局配置 (Env)
├── configs/                          # [配置层]
│   ├── config_waterpump.yaml         # 设备配置 (DB2 数据点)
│   ├── config_waterpump_db2.yaml     # DB2 数据点映射
│   ├── db_mappings.yaml              # ★ DB块映射总表 (Poll Config)
│   ├── plc_modules.yaml              # ★ 基础模块定义 (Modules)
│   ├── status_waterpump_db1.yaml     # DB1 设备状态映射
│   └── status_waterpump_db3.yaml     # DB3 设备状态映射
├── app/
│   ├── core/                         # [核心层]
│   │   ├── influxdb.py               # InfluxDB 读写封装
│   │   ├── local_cache.py            # SQLite 本地降级缓存
│   │   ├── threshold_store.py        # 阈值存储管理
│   │   └── alarm_store.py            # 报警记录存储
│   ├── models/                       # [数据模型]
│   │   └── ws_messages.py            # ★ WebSocket 消息 Pydantic 模型
│   ├── plc/                          # [PLC 层]
│   │   ├── plc_manager.py            # 连接管理器 (Reconnect)
│   │   ├── s7_client.py              # Snap7 客户端封装
│   │   ├── parser_waterpump.py       # 水泵数据解析器 (DB2)
│   │   ├── parser_status_waterpump.py # 设备状态解析器 (DB1/DB3)
│   │   ├── module_parser.py          # 通用模块解析器
│   │   └── config_manager.py         # 配置文件管理器
│   ├── tools/                        # [转换层]
│   │   ├── converter_base.py         # 转换器基类
│   │   ├── converter_elec.py         # 电气数据转换 (电压/电流/功率)
│   │   ├── converter_pressure.py     # 压力数据转换
│   │   └── converter_vibration.py    # 振动数据转换
│   ├── services/                     # [服务层]
│   │   ├── polling_service.py        # ★ 核心轮询逻辑 (Data Collection)
│   │   ├── mock_service.py           # 模拟数据生成
│   │   ├── ws_manager.py             # ★ WebSocket 连接管理器
│   │   └── resource_monitor.py       # 系统资源监控
│   └── routers/                      # [API 路由]
│       ├── __init__.py               # 路由汇总 (api_router, ws_router)
│       ├── websocket.py              # ★ WebSocket 端点 (/ws/realtime)
│       ├── realtime.py               # 实时数据 HTTP 接口 (降级)
│       ├── history.py                # 历史数据查询接口
│       ├── devices.py                # 设备状态接口
│       ├── alarms.py                 # 报警管理接口
│       ├── config.py                 # 阈值配置接口
│       ├── health.py                 # 健康检查接口
│       └── utils.py                  # 路由工具函数
├── data/
│   ├── thresholds.json               # 阈值持久化存储
│   └── cache.db                      # SQLite 本地缓存
├── docs/
│   └── WEBSOCKET_PROTOCOL.md         # ★ WebSocket 协议规范文档
├── scripts/                          # [工具脚本]
│   ├── tray_app.py                   # 系统托盘应用
│   ├── log_viewer.py                 # 日志查看器
│   └── test_*.py                     # 各种测试脚本
└── docker-compose.yml                # 容器编排 (仅 InfluxDB，可选)
```

## 4. 核心实现规范 (Implementation Specs)

### 4.1 WebSocket 通信架构

#### 4.1.1 连接管理 (`ws_manager.py`)

- **单例模式**: 使用 `get_ws_manager()` 获取全局唯一的 `ConnectionManager` 实例。
- **连接生命周期**:
  - `connect()`: 接受新连接，初始化订阅集合和心跳时间。
  - `disconnect()`: 清理连接资源，移除订阅记录。
  - `update_heartbeat()`: 更新客户端心跳时间戳。
- **订阅管理**:
  - 支持频道: `realtime` (实时数据), `device_status` (设备状态)。
  - 客户端可订阅多个频道，服务端按频道广播消息。

#### 4.1.2 推送任务

- **推送间隔**:
  - 实时数据推送: `0.1s` (100ms，极快响应)
  - 设备状态推送: `0.1s` (100ms)
  - 心跳超时检测: `15s` 检查一次，超时阈值 `45s`
- **数据来源优先级**:
  1. `polling_service` 内存缓存 (最快)
  2. Mock 数据生成 (开发模式)
  3. InfluxDB 查询 (降级方案)
- **推送逻辑**:
  - 仅向订阅了对应频道的客户端推送数据。
  - 推送失败自动清理断开的连接。

#### 4.1.3 消息格式

- **所有消息必须包含 `type` 字段**，用于标识消息类型。
- **使用 Pydantic 模型** (`app/models/ws_messages.py`) 进行消息验证和序列化。
- **消息类型**:
  - 客户端 → 服务端: `subscribe`, `unsubscribe`, `heartbeat`
  - 服务端 → 客户端: `realtime_data`, `device_status`, `heartbeat`, `error`

### 4.2 轮询服务设计 (`polling_service.py`)

- **死循环防护**: 轮询必须在 `while check_running():` 循环中运行，并包含 `await asyncio.sleep()` 防止 CPU 100%。
- **错误隔离**: 单个设备的采集失败不应中断整个轮询线程。
- **内存缓存**: 使用全局变量缓存最新数据和设备状态，供 WebSocket 推送和 HTTP 接口快速访问。
- **双重写入**:
  1. 更新内存缓存 (实时推送用)
  2. 批量写入 InfluxDB (历史查询用)

### 4.3 数据解析与转换流程

1.  **Parse (解析)**: `Parser` 类读取 `config_*.yaml` 中的偏移量，将 PLC `bytes` 解析为 Python 字典 (Raw Values)。
    - _Tip_: Parser 不进行单位转换，只按 Byte/Word/Real 读取数值。
2.  **Convert (转换)**: `Converter` 类将 Raw Values 转换为物理量 (Physical Values)。
    - 例: 将原始电压值转换为实际电压 V。
    - 例: 计算功率因数、累计能耗等。

### 4.4 InfluxDB 设计

- **部署方式**:
  - **推荐**: 本地安装 InfluxDB (Windows/Linux)，配置 `INFLUX_URL=http://localhost:8086`
  - **可选**: Docker 部署 (仅用于开发测试)
- **Measurement**: `sensor_data` (单表存储)。
- **Tags**: `device_id`, `device_type`, `module_type`。
- **Fields**: `voltage`, `current`, `power`, `vibration`, `pressure`... (动态字段)。
- **性能优化**: 批量写入，减少网络往返次数。

## 5. API 接口规范 (API Specifications)

### 5.1 WebSocket 接口 (主要通信方式)

#### 5.1.1 连接端点

```
ws://localhost:8081/ws/realtime
```

#### 5.1.2 客户端消息

**订阅实时数据**:

```json
{ "type": "subscribe", "channel": "realtime" }
```

**订阅设备状态**:

```json
{ "type": "subscribe", "channel": "device_status" }
```

**心跳保活**:

```json
{ "type": "heartbeat", "timestamp": "2026-02-07T10:30:00Z" }
```

**取消订阅**:

```json
{ "type": "unsubscribe", "channel": "realtime" }
```

#### 5.1.3 服务端推送

**实时数据推送** (0.1s 间隔):

```json
{
	"type": "realtime_data",
	"success": true,
	"timestamp": "2026-02-07T10:30:00.000Z",
	"source": "plc",
	"data": {
		"pumps": [
			{
				"id": 1,
				"voltage": 380.5,
				"current": 12.3,
				"power": 5.6,
				"energy": 1234.5,
				"status": "normal",
				"alarms": []
			},
			{
				"id": 2,
				"voltage": 381.2,
				"current": 0.0,
				"power": 0.0,
				"energy": 0.0,
				"status": "offline",
				"alarms": []
			}
		],
		"pressure": { "value": 0.45, "status": "normal" }
	}
}
```

**设备状态推送** (0.1s 间隔):

```json
{
	"type": "device_status",
	"success": true,
	"timestamp": "2026-02-07T10:30:00.000Z",
	"source": "plc",
	"data": {
		"db1": [
			{
				"device_id": "pump_1",
				"device_name": "1#水泵",
				"enabled": true,
				"error": false,
				"is_normal": true
			}
		],
		"db3": []
	},
	"summary": { "total": 6, "normal": 6, "error": 0 }
}
```

**错误消息**:

```json
{
	"type": "error",
	"code": "INVALID_CHANNEL",
	"message": "无效的频道: unknown_channel"
}
```

#### 5.1.4 连接管理

- **心跳机制**: 客户端每 15 秒发送一次心跳，服务端 45 秒无心跳则断开连接。
- **重连策略**: 客户端应实现指数退避重连 (1s → 2s → 4s → 8s → 16s → 30s)。
- **订阅恢复**: 重连后需重新发送订阅消息。

### 5.2 HTTP 接口 (降级方案)

**注意**: HTTP 接口仅作为 WebSocket 的降级方案，用于历史数据查询和配置管理。实时数据推送应优先使用 WebSocket。

#### 5.2.1 实时数据接口

- **Base URL**: `http://localhost:8081/api`
- **Endpoints**:
  - `GET /realtime/batch`: 获取所有设备最新数据 (6泵 + 1压力表)
  - `GET /realtime/{pump_id}`: 获取单个水泵实时数据 (pump_id: 1-6)
  - `GET /realtime/pressure`: 获取压力表实时数据

#### 5.2.2 历史数据接口

- `GET /history`: 历史数据查询
  - 参数: `pump_id`, `parameter`, `interval`, `start`, `end`
  - 注意 InfluxDB 查询性能优化

#### 5.2.3 设备状态接口

- `GET /status/devices`: 获取所有设备通信状态 (DB1/DB3)

#### 5.2.4 配置管理接口

- `GET /config/thresholds`: 获取阈值配置
- `POST /config/thresholds`: 更新阈值配置

#### 5.2.5 健康检查接口

- `GET /health`: 系统健康检查
- `GET /ws/status`: WebSocket 连接状态统计

### 5.3 响应格式

**成功响应**:

```json
{
  "success": true,
  "data": { ... },
  "timestamp": "2026-02-07T10:30:00Z",
  "source": "plc"
}
```

**错误响应**:

```json
{
	"success": false,
	"error": "错误描述",
	"timestamp": "2026-02-07T10:30:00Z"
}
```

### 5.4 错误处理

- **4xx**: 客户端错误（参数校验失败）
- **5xx**: 服务端错误（数据库连接失败、PLC 通信异常）
- 所有错误必须返回结构化的 JSON 响应，包含错误码和描述

## 6. 日志规范 (Logging Standards)

- **格式**: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- **级别**: 生产环境 INFO，调试环境 DEBUG。
- **内容**: 关键操作（启动、停止、配置变更、严重错误）必须记录。
- **Traceback**: 报错时产生的日志必须包含 traceback 和上下文信息。
- **WebSocket 日志**:
  - 连接建立/断开: INFO 级别
  - 订阅/取消订阅: INFO 级别
  - 心跳消息: DEBUG 级别
  - 推送消息: DEBUG 级别

## 7. 开发命令 (Development)

```powershell
# 本地运行 (推荐)
uvicorn main:create_app --factory --host 0.0.0.0 --port 8081 --reload

# 启动 Mock 模式 (Docker)
docker compose --profile mock up -d

# 启动生产模式 (Docker)
docker compose --profile production up -d

# 仅启动 InfluxDB (本地开发推荐)
docker compose up influxdb -d

# 运行测试
pytest tests/ -v

# 代码检查
ruff check .
```

## 8. 部署方式 (Deployment)

### 8.1 本地部署 (推荐)

**InfluxDB 本地安装**:

1. 下载 InfluxDB 2.x: https://www.influxdata.com/downloads/
2. 安装并启动服务
3. 配置环境变量:
   ```bash
   INFLUX_URL=http://localhost:8086
   INFLUX_TOKEN=your-token
   INFLUX_ORG=waterpump
   INFLUX_BUCKET=sensor_data
   ```

**Python 后端**:

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
# 或
uvicorn main:create_app --factory --host 0.0.0.0 --port 8081
```

### 8.2 Docker 部署 (可选)

**仅用于开发测试**，生产环境推荐本地部署以获得更快的响应速度。

```bash
# Mock 模式
docker compose --profile mock up -d

# 生产模式
docker compose --profile production up -d
```

### 8.3 环境变量配置

| 变量           | 说明     | Mock模式              | 生产模式              |
| -------------- | -------- | --------------------- | --------------------- |
| USE_MOCK_DATA  | 模拟数据 | true                  | false                 |
| USE_REAL_PLC   | 真实PLC  | false                 | true                  |
| PLC_IP         | PLC地址  | -                     | 192.168.x.x           |
| INFLUX_URL     | InfluxDB | http://localhost:8086 | http://localhost:8086 |
| ENABLE_POLLING | 轮询     | true                  | true                  |
| SERVER_PORT    | 服务端口 | 8081                  | 8081                  |

## 9. 复用指南 (Replication Guide)

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
5.  **WebSocket 消息**: 若需要新的消息类型，在 `app/models/ws_messages.py` 定义 Pydantic 模型。
6.  **端口配置**: 修改 `docker-compose.yml` 和 `main.py` 中的端口，避免冲突。

## 10. 编码规范 (Coding Standards)

### 10.1 命名规范

#### 10.1.1 基础命名规则

- **文件名**: 小写下划线 `snake_case.py`
- **类名**: 大驼峰 `PascalCase`
- **函数/变量**: 小写下划线 `snake_case`
- **常量**: 大写下划线 `UPPER_SNAKE_CASE`
- **Pydantic 模型字段**: 小写下划线 `snake_case`

#### 10.1.2 模块命名规范

**模块文件名和类名必须遵循"模块类型\_功能描述"格式**：

正确命名：

```python
# 文件名: converter_elec.py
class ConverterElec(ConverterBase):
    """电气数据转换器"""
    pass

# 文件名: parser_waterpump.py
class ParserWaterpump:
    """水泵数据解析器"""
    pass

# 文件名: router_history.py / history.py
# Router 在 routers/ 目录下可省略前缀
```

错误命名：

```python
# 文件名: elec_converter.py (错误: 功能在前)
class ElecConverter:
    pass
```

**常见模块类型前缀**：

| 模块类型     | 说明       | 示例                                                |
| ------------ | ---------- | --------------------------------------------------- |
| `converter_` | 数据转换器 | `converter_elec.py`, `converter_pressure.py`        |
| `parser_`    | 数据解析器 | `parser_waterpump.py`, `parser_status_waterpump.py` |
| `router_`    | API 路由   | 在 `routers/` 目录下可省略前缀                      |
| `service_`   | 业务服务   | `polling_service.py`, `mock_service.py`             |
| `model_`     | 数据模型   | `ws_messages.py` (在 `models/` 目录下可省略前缀)    |

### 10.2 注释规范

**使用序号+注释风格，不使用冗长的文档字符串**：

```python
# 1. 初始化轮询服务
async def start_polling():
    global _polling_task
    _polling_task = asyncio.create_task(_poll_loop())

# 2. 轮询主循环
async def _poll_loop():
    while check_running():
        try:
            await _collect_data()
        except Exception as e:
            logger.error(f"轮询异常: {e}", exc_info=True)
        await asyncio.sleep(settings.plc_poll_interval)
```

**文件头部注释**：

```python
"""
文件功能简短描述（一行即可）
"""
```

不要使用：

```python
def start_polling():
    """启动轮询服务

    该函数初始化轮询任务，创建异步循环...

    Args:
        无参数
    Returns:
        无返回值
    Raises:
        RuntimeError: 如果轮询已启动
    """
    pass
```

#### 10.2.1 禁止使用 Emoji 表情符号

**原则**: 注释和日志中不使用任何 emoji 图标或表情符号。

正确的注释：

```python
# 1. 初始化 WebSocket 管理器
# 注意: 这里需要设置心跳超时
# 警告: 不要在同步上下文中调用
logger.info("服务启动完成")
logger.error("连接失败: %s", err)
```

错误的注释（禁止使用）：

```python
# 🚀 初始化 WebSocket 管理器
# ⚠️ 注意: 这里需要设置心跳超时
logger.info("✅ 服务启动完成")
logger.error("❌ 连接失败: %s", err)
```

**原因**：

1. **编码兼容性**: Emoji 在某些终端和日志系统中显示为乱码
2. **日志检索**: 纯文本日志更易于 grep 和搜索
3. **专业性**: 工业控制系统代码应保持严谨风格
4. **跨平台**: 不同系统对 Emoji 支持程度不同

### 10.3 代码设计原则

**避免过度抽象**：

- **不要提前抽象**: 需要用的时候再抽象，不要预创建大量工具方法
- **避免冗余方法**: 一个文件不要抽象出太多方法，保持简洁
- **实用主义**: 能直接写就直接写，不要为了"优雅"而过度封装

好的做法：

```python
# 1. 构建实时数据响应
def build_realtime_response(data: dict) -> dict:
    return {
        "type": "realtime_data",
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "data": data,
    }
```

过度抽象：

```python
def _build_base_response(type_name: str) -> dict:
    return {"type": type_name, "timestamp": datetime.now().isoformat()}

def _add_success_flag(resp: dict, success: bool) -> dict:
    resp["success"] = success
    return resp

def _add_data_payload(resp: dict, data: dict) -> dict:
    resp["data"] = data
    return resp

def build_realtime_response(data: dict) -> dict:
    resp = _build_base_response("realtime_data")
    resp = _add_success_flag(resp, True)
    resp = _add_data_payload(resp, data)
    return resp
```

## 11. 技术约定 (Technical Conventions)

### 11.1 依赖管理

```yaml
framework: FastAPI 0.109.0
websocket: Starlette WebSocket + websockets 15.0.1
database: InfluxDB 2.7 (本地部署)
cache: SQLite (local fallback)
async: asyncio + uvicorn
validation: Pydantic v2
plc: python-snap7 1.3
```

### 11.2 代码风格

- 使用 `ruff` 进行代码格式化和检查
- 类型注解 (Type Hints) 必须完整
- WebSocket 相关代码必须处理连接断开异常

### 11.3 性能优化

- **WebSocket 推送**: 使用 `asyncio.create_task()` 异步推送，避免阻塞
- **批量写入**: InfluxDB 写入使用批量模式，减少网络开销
- **内存缓存**: 轮询服务维护内存缓存，WebSocket 推送直接读取缓存
- **连接池**: InfluxDB 客户端使用连接池，复用连接

## 12. Troubleshooting

| Issue              | Solution                                  |
| ------------------ | ----------------------------------------- |
| InfluxDB 连接失败  | 检查本地 InfluxDB 服务状态，确认端口 8086 |
| WebSocket 连接断开 | 检查心跳机制，查看客户端重连逻辑          |
| 轮询服务无数据     | 检查 Mock 模式是否启用，查看日志          |
| 推送延迟高         | 检查 PUSH_INTERVAL 配置，优化内存缓存     |
| 内存持续增长       | 检查 WebSocket 连接清理，查看缓存大小     |
| 服务启动后立即退出 | 检查 lifespan 管理器，查看启动日志        |
| WebSocket 推送失败 | 检查客户端连接状态，查看错误日志          |

---

**AI 指令**:

1. **WebSocket 优先**: 实时数据推送必须使用 WebSocket，HTTP 接口仅作为降级方案。
2. **简单至上**: 能用简单逻辑实现的，不要引入复杂的类层次结构。
3. **防崩溃**: 任何涉及 I/O (网络, 数据库, WebSocket) 的操作必须有超时和重试机制。
4. **清晰日志**: 报错时产生的日志必须包含 traceback 和上下文信息。
5. **配置优先**: 在修改代码时，优先检查 `configs/` 目录，通过配置驱动逻辑。
6. **分层架构**: 保持 "Router-Service-Core" 的分层结构，职责清晰。
7. **连接管理**: WebSocket 连接必须正确处理断开、超时和重连场景。
8. **性能优化**: 使用内存缓存减少数据库查询，批量写入减少网络开销。
9. **本地优先**: 推荐使用本地 InfluxDB 部署，避免 Docker 网络延迟。
10. **协议规范**: 严格遵循 `docs/WEBSOCKET_PROTOCOL.md` 中定义的消息格式和通信流程。

## 其他规范

- **PowerShell 命令**：不支持 `&&`，使用分号 `;` 分隔命令
- **称呼**：每次回答必须称呼我为"大王"
- **测试文件**：不要创建多余的 md/py/test 文件，测试完毕后一定要删除,并且我的任何测试代码不要使用 emoji.
- **文档管理**：md 文件需要放到 `vdoc/` 目录里面
- **代码整洁**：目录务必整洁，修改代码时删除旧代码，不要冗余
- **回答执行规范**：你是一个很严格的python pyqt6写上位机的高手,你很严谨认真,且对代码很严苛,不会写无用冗余代码,并且很多问题,对于我希望实现的效果和架构你会认真思考,如果我的提议不好或者你有更好的方案,你会规劝我.
- **反驳我的回答** 对于我说的需求等的话,肯定会有一些东西说的不专业,如果你理解了的话,就回答我,"大王,小的罪该万死,但是这个XXXX"这样回答.
- **编码问题** 我的代码文件肯定会就是有中文和python代码,以及可能会有图标,所以的话,生成的代码需要规避编码问题错误.
- **log以及代码文件** 我的代码文件以及log的输出的话,等一切不要使用图标等标注. .这样的.
- **不要虚构** 回答我以及生成的md文件之中一定要和我的实际的代码文件相关,而不是虚构的.
- **不使用虚拟环境启动python**
- **必须真实有效的回答我,不能虚构**不要虚构任何我项目没有的文件,回答也必须严谨有效,而不是虚构.
