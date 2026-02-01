# WebSocket 数据传输协议规范

> **版本**: 1.0.0  
> **适用系统**: 水泵房监控系统  
> **端点**: `ws://localhost:8081/ws/realtime`

---

## 1. 连接建立

### 1.1 WebSocket 端点

```
ws://{host}:{port}/ws/realtime
```

**示例**:
```
ws://localhost:8081/ws/realtime
```

### 1.2 连接流程

```
┌─────────────┐                    ┌─────────────┐
│   Flutter   │                    │   FastAPI   │
│   Client    │                    │   Server    │
└──────┬──────┘                    └──────┬──────┘
       │                                  │
       │  1. WebSocket Connect            │
       │ ─────────────────────────────────>
       │                                  │
       │  2. Connection Established       │
       │ <─────────────────────────────────
       │                                  │
       │  3. Subscribe (realtime)         │
       │ ─────────────────────────────────>
       │                                  │
       │  4. Subscribe (device_status)    │
       │ ─────────────────────────────────>
       │                                  │
       │  5. Realtime Data (every 5s)     │
       │ <─────────────────────────────────
       │                                  │
       │  6. Device Status (every 5s)     │
       │ <─────────────────────────────────
       │                                  │
       │  7. Heartbeat (every 15s)        │
       │ ─────────────────────────────────>
       │                                  │
       │  8. Heartbeat Response           │
       │ <─────────────────────────────────
       │                                  │
```

---

## 2. 消息格式 (JSON)

所有消息采用 JSON 格式，包含 `type` 字段标识消息类型。

### 2.1 消息类型枚举

| type            | 方向              | 说明           |
| --------------- | ----------------- | -------------- |
| `subscribe`     | Client → Server   | 订阅消息       |
| `unsubscribe`   | Client → Server   | 取消订阅       |
| `heartbeat`     | Client ↔ Server   | 心跳消息       |
| `realtime_data` | Server → Client   | 实时数据推送   |
| `device_status` | Server → Client   | 设备状态推送   |
| `error`         | Server → Client   | 错误消息       |

---

## 3. 客户端 → 服务端消息

### 3.1 订阅消息 (subscribe)

```json
{
  "type": "subscribe",
  "channel": "realtime"
}
```

**channel 可选值**:
- `realtime` - 实时数据 (水泵 + 压力表)
- `device_status` - 设备通信状态 (DB1/DB3)

### 3.2 取消订阅 (unsubscribe)

```json
{
  "type": "unsubscribe",
  "channel": "realtime"
}
```

### 3.3 心跳消息 (heartbeat)

```json
{
  "type": "heartbeat",
  "timestamp": "2026-02-01T10:30:00.000Z"
}
```

---

## 4. 服务端 → 客户端消息

### 4.1 实时数据推送 (realtime_data)

**完整消息结构**:

```json
{
  "type": "realtime_data",
  "success": true,
  "timestamp": "2026-02-01T10:30:00.000Z",
  "source": "plc",
  "data": {
    "pumps": [
      {
        "id": 1,
        "voltage": 380.5,
        "current": 12.3,
        "power": 5.6,
        "status": "normal",
        "alarms": []
      },
      {
        "id": 2,
        "voltage": 381.2,
        "current": 0.0,
        "power": 0.0,
        "status": "offline",
        "alarms": []
      },
      {
        "id": 3,
        "voltage": 379.8,
        "current": 15.1,
        "power": 7.2,
        "status": "warning",
        "alarms": ["vibration_high"]
      },
      {
        "id": 4,
        "voltage": 380.0,
        "current": 11.8,
        "power": 5.4,
        "status": "normal",
        "alarms": []
      },
      {
        "id": 5,
        "voltage": 380.3,
        "current": 12.0,
        "power": 5.5,
        "status": "normal",
        "alarms": []
      },
      {
        "id": 6,
        "voltage": 378.9,
        "current": 18.5,
        "power": 8.8,
        "status": "alarm",
        "alarms": ["overcurrent", "overheat"]
      }
    ],
    "pressure": {
      "value": 0.45,
      "status": "normal"
    }
  }
}
```

**字段说明**:

| 字段                 | 类型     | 说明                                       |
| -------------------- | -------- | ------------------------------------------ |
| `type`               | string   | 固定值 `realtime_data`                     |
| `success`            | boolean  | 数据获取是否成功                           |
| `timestamp`          | string   | ISO 8601 格式时间戳                        |
| `source`             | string   | 数据来源: `plc` / `mock`                   |
| `data.pumps`         | array    | 6 台水泵数据数组                           |
| `data.pumps[].id`    | int      | 水泵编号 (1-6)                             |
| `data.pumps[].voltage` | float  | 电压值 (V)                                 |
| `data.pumps[].current` | float  | 电流值 (A)                                 |
| `data.pumps[].power` | float    | 功率值 (kW)                                |
| `data.pumps[].status` | string  | 状态: `normal`/`warning`/`alarm`/`offline` |
| `data.pumps[].alarms` | array   | 当前报警列表                               |
| `data.pressure`      | object   | 压力表数据                                 |
| `data.pressure.value` | float   | 压力值 (MPa)                               |
| `data.pressure.status` | string | 状态: `normal`/`warning`/`alarm`/`offline` |

### 4.2 设备状态推送 (device_status)

**完整消息结构**:

```json
{
  "type": "device_status",
  "success": true,
  "timestamp": "2026-02-01T10:30:00.000Z",
  "source": "plc",
  "data": {
    "db1": [
      {
        "device_id": "pump_1",
        "device_name": "1#水泵",
        "data_device_id": "pump_1",
        "offset": 0,
        "enabled": true,
        "error": false,
        "status_code": 0,
        "status_hex": "0000",
        "is_normal": true
      },
      {
        "device_id": "pump_2",
        "device_name": "2#水泵",
        "data_device_id": "pump_2",
        "offset": 2,
        "enabled": true,
        "error": true,
        "status_code": 1,
        "status_hex": "0001",
        "is_normal": false
      }
    ],
    "db3": [
      {
        "device_id": "module_1",
        "device_name": "模块1",
        "offset": 0,
        "enabled": true,
        "error": false,
        "status_code": 0,
        "status_hex": "0000",
        "is_normal": true
      }
    ]
  },
  "summary": {
    "total": 7,
    "normal": 6,
    "error": 1
  },
  "summary_by_db": {
    "db1": {
      "total": 6,
      "normal": 5,
      "error": 1
    },
    "db3": {
      "total": 1,
      "normal": 1,
      "error": 0
    }
  }
}
```

**字段说明**:

| 字段                     | 类型    | 说明                           |
| ------------------------ | ------- | ------------------------------ |
| `type`                   | string  | 固定值 `device_status`         |
| `success`                | boolean | 数据获取是否成功               |
| `timestamp`              | string  | ISO 8601 格式时间戳            |
| `source`                 | string  | 数据来源: `plc` / `mock`       |
| `data`                   | object  | 按 DB 分组的设备状态           |
| `data.db1[]`             | array   | DB1 设备状态数组               |
| `data.db3[]`             | array   | DB3 设备状态数组               |
| `device_id`              | string  | 设备唯一标识                   |
| `device_name`            | string  | 设备显示名称                   |
| `data_device_id`         | string  | 关联的数据设备 ID (可选)       |
| `offset`                 | int     | DB 中的字节偏移量              |
| `enabled`                | boolean | 设备是否启用                   |
| `error`                  | boolean | 是否有通信错误                 |
| `status_code`            | int     | 状态码原始值                   |
| `status_hex`             | string  | 状态码十六进制显示             |
| `is_normal`              | boolean | 是否正常 (无错误)              |
| `summary`                | object  | 全局统计信息                   |
| `summary_by_db`          | object  | 按 DB 分组的统计信息           |

### 4.3 心跳响应 (heartbeat)

```json
{
  "type": "heartbeat",
  "timestamp": "2026-02-01T10:30:00.000Z"
}
```

### 4.4 错误消息 (error)

```json
{
  "type": "error",
  "code": "PLC_DISCONNECTED",
  "message": "PLC 连接已断开"
}
```

**常见错误码**:

| code               | 说明                |
| ------------------ | ------------------- |
| `PLC_DISCONNECTED` | PLC 连接断开        |
| `DB_ERROR`         | InfluxDB 连接错误   |
| `INVALID_CHANNEL`  | 无效的订阅频道      |
| `INTERNAL_ERROR`   | 服务器内部错误      |

---

## 5. 推送频率

| 数据类型       | 推送频率   | 说明                           |
| -------------- | ---------- | ------------------------------ |
| realtime_data  | 5 秒       | 实时数据推送                   |
| device_status  | 5 秒       | 设备状态推送                   |
| heartbeat      | 15 秒      | 客户端发起，服务端响应         |

---

## 6. 重连机制

### 6.1 客户端重连策略

- **指数退避**: 1s → 2s → 4s → 8s → 16s → 30s (最大)
- **重连触发**: 连接断开、心跳超时
- **重连后**: 自动重新订阅之前的频道

### 6.2 心跳超时

- **客户端心跳间隔**: 15 秒
- **服务端超时判定**: 45 秒无心跳视为客户端断开

---

## 7. FastAPI 后端实现示例

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json

app = FastAPI()

# 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[WebSocket, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = set()
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]
    
    def subscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.active_connections:
            self.active_connections[websocket].add(channel)
    
    def unsubscribe(self, websocket: WebSocket, channel: str):
        if websocket in self.active_connections:
            self.active_connections[websocket].discard(channel)
    
    async def broadcast(self, channel: str, message: dict):
        for ws, channels in self.active_connections.items():
            if channel in channels:
                try:
                    await ws.send_json(message)
                except:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/realtime")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                channel = data.get("channel")
                manager.subscribe(websocket, channel)
            
            elif msg_type == "unsubscribe":
                channel = data.get("channel")
                manager.unsubscribe(websocket, channel)
            
            elif msg_type == "heartbeat":
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# 后台任务: 推送实时数据
async def push_realtime_data():
    while True:
        data = get_realtime_data_from_plc()  # 从 PLC 获取数据
        await manager.broadcast("realtime", {
            "type": "realtime_data",
            **data
        })
        await asyncio.sleep(5)

# 后台任务: 推送设备状态
async def push_device_status():
    while True:
        data = get_device_status_from_plc()  # 从 PLC 获取状态
        await manager.broadcast("device_status", {
            "type": "device_status",
            **data
        })
        await asyncio.sleep(5)
```

---

## 8. 与 HTTP API 的对应关系

| WebSocket 消息        | 对应 HTTP 端点                      |
| --------------------- | ----------------------------------- |
| `realtime_data`       | `GET /api/waterpump/realtime/batch` |
| `device_status`       | `GET /api/waterpump/status/devices` |

**注意**: WebSocket 消息结构与 HTTP 响应结构保持一致，额外增加 `type` 字段用于消息类型识别。

---

## 9. 数据兼容性

为保持与现有 HTTP API 的兼容性:

1. **RealtimeBatchResponse**: WebSocket `realtime_data` 消息可直接使用 `RealtimeBatchResponse.fromJson()` 解析
2. **DeviceStatusResponse**: WebSocket `device_status` 消息可直接使用 `DeviceStatusResponse.fromJson()` 解析
3. **降级模式**: 当 WebSocket 连接失败时，前端可自动切换回 HTTP 轮询模式
