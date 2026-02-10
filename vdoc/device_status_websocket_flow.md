# 设备状态 WebSocket 推送流程说明

## 功能概述

实现 DB1/DB3 设备通信状态的实时推送功能，采用**按需推送**策略，只在状态变化时推送数据，避免不必要的网络开销。

## 架构设计

```
PLC/Mock → 状态轮询服务 (5s) → 内存缓存 → 状态变化检测 → WebSocket 推送 (仅变化时) → Flutter 客户端
                                    ↓
                              HTTP API (降级)
```

## 核心组件

### 1. 后端轮询服务

**文件**: `app/services/polling_service_status_db1_3.py`

**功能**:
- 每 5 秒轮询一次 DB1 和 DB3 数据块
- 解析设备通信状态（Error 位、Status 字）
- 缓存到内存 `_latest_status`
- 检测状态变化，设置 `_status_changed` 标志

**关键变量**:
```python
_latest_status: Dict[str, Any] = {}  # 最新状态缓存
_status_changed: bool = False        # 状态变化标志
```

**关键函数**:
```python
def _has_status_changed(old_status, new_status) -> bool:
    """比较状态是否变化（比较 summary 和设备列表）"""
    
def has_status_changed() -> bool:
    """检查状态是否已变化（供 WebSocket 调用）"""
    
def reset_status_changed():
    """重置状态变化标志（推送后调用）"""
```

### 2. WebSocket 推送服务

**文件**: `app/services/ws_manager.py`

**功能**:
- 每 0.1 秒检查一次状态变化标志
- 仅在 `has_status_changed() == True` 时推送数据
- 推送后调用 `reset_status_changed()` 重置标志
- 向订阅 `device_status` 频道的客户端广播消息

**推送逻辑**:
```python
async def _push_device_status(self, timestamp: str):
    # 1. 检查状态是否变化
    if not has_status_changed():
        return  # 未变化，跳过推送
    
    # 2. 获取最新状态
    latest_status = get_latest_status()
    
    # 3. 构建消息
    message = {
        "type": "device_status",
        "success": True,
        "timestamp": timestamp,
        "source": "plc" or "mock",
        "data": {"db1": [...], "db3": [...]},
        "summary": {"total": 6, "normal": 6, "error": 0},
        "summary_by_db": {...}
    }
    
    # 4. 广播消息
    await self.broadcast("device_status", message)
    
    # 5. 重置变化标志
    reset_status_changed()
```

### 3. Flutter 客户端

**文件**: `lib/services/sensor_status_service.dart`, `lib/pages/sensor_status_page.dart`

**功能**:
- 连接 WebSocket 并订阅 `device_status` 频道
- 接收服务端推送的状态数据
- 更新 UI 显示设备状态

**订阅流程**:
```dart
// 1. 启动订阅
_statusService.startPolling();

// 2. 设置回调
_statusService.onDataUpdate = (data) {
  setState(() {
    _response = data;
  });
};

// 3. WebSocket 自动订阅
_wsService.subscribeDeviceStatus();
```

## 数据流详解

### 阶段 1: 轮询与缓存 (5 秒间隔)

```
时间 0s:  轮询 DB1/DB3 → 解析状态 → 比较变化 → 更新缓存 → 设置 _status_changed = True
时间 5s:  轮询 DB1/DB3 → 解析状态 → 比较变化 → 无变化 → _status_changed = False
时间 10s: 轮询 DB1/DB3 → 解析状态 → 比较变化 → 有变化 → _status_changed = True
```

### 阶段 2: WebSocket 推送 (0.1 秒检查)

```
时间 0.0s:  检查 _status_changed → False → 跳过推送
时间 0.1s:  检查 _status_changed → False → 跳过推送
时间 0.2s:  检查 _status_changed → True  → 推送数据 → 重置标志
时间 0.3s:  检查 _status_changed → False → 跳过推送
...
时间 5.0s:  轮询更新 → _status_changed = True
时间 5.1s:  检查 _status_changed → True  → 推送数据 → 重置标志
```

### 阶段 3: 客户端更新

```
Flutter 收到 device_status 消息 → 解析 JSON → 调用回调 → setState() → UI 更新
```

## 状态变化检测逻辑

### 比较维度

1. **Summary 比较**: 比较 `summary_by_db` 中的 `total`, `normal`, `error` 数量
2. **设备列表比较**: 比较每个设备的 `error`, `status_code`, `is_normal` 字段

### 示例

**场景 1: 设备故障**
```python
# 旧状态
{"device_id": "pump_1", "error": False, "status_code": 0, "is_normal": True}

# 新状态
{"device_id": "pump_1", "error": True, "status_code": 1, "is_normal": False}

# 结果: _status_changed = True → 推送
```

**场景 2: 状态未变化**
```python
# 旧状态
{"device_id": "pump_1", "error": False, "status_code": 0, "is_normal": True}

# 新状态
{"device_id": "pump_1", "error": False, "status_code": 0, "is_normal": True}

# 结果: _status_changed = False → 不推送
```

## 消息格式

### WebSocket 推送消息

```json
{
  "type": "device_status",
  "success": true,
  "timestamp": "2026-02-08T10:30:00.000Z",
  "source": "plc",
  "data": {
    "db1": [
      {
        "device_id": "pump_1",
        "device_name": "1#水泵",
        "plc_name": "1#电表",
        "data_device_id": "pump_1",
        "offset": 0,
        "enabled": true,
        "error": false,
        "status_code": 0,
        "status_hex": "0000",
        "is_normal": true
      }
    ],
    "db3": []
  },
  "summary": {
    "total": 6,
    "normal": 6,
    "error": 0
  },
  "summary_by_db": {
    "db1": {"total": 6, "normal": 6, "error": 0},
    "db3": {"total": 0, "normal": 0, "error": 0}
  }
}
```

## 性能优化

### 1. 按需推送

- **优化前**: 每 0.1 秒推送一次，即使状态未变化（每秒 10 次 × 6 设备 = 60 次无效推送）
- **优化后**: 仅在状态变化时推送（平均每 5 秒 1 次，减少 99% 的推送量）

### 2. 内存缓存

- 状态数据缓存在内存中，避免频繁查询数据库
- WebSocket 推送直接读取缓存，响应速度快

### 3. 变化检测

- 使用字典比较，快速判断状态是否变化
- 只比较关键字段（error, status_code, is_normal），忽略时间戳等无关字段

## 测试验证

### 1. 启动后端服务

```bash
cd ceramic-waterpump-backend
python main.py
```

### 2. 观察日志

```
[DB1/DB3状态 poll #1] 状态已更新，标记为已变化
[WS] 推送 device_status (状态已变化) -> 1 个订阅者
[DB1/DB3状态 poll #2] 状态未变化
[DB1/DB3状态 poll #3] 状态未变化
[DB1/DB3状态 poll #4] 状态已更新，标记为已变化
[WS] 推送 device_status (状态已变化) -> 1 个订阅者
```

### 3. 启动 Flutter 客户端

```bash
cd ceramic-waterpump-flutter
flutter run -d windows
```

### 4. 验证功能

1. 打开"设备状态"页面
2. 观察控制台日志：`[WebSocket] 收到设备状态更新: 6 个设备`
3. 检查 UI 是否正确显示设备状态
4. 模拟设备故障（修改 Mock 数据），观察 UI 是否实时更新

## 故障排查

### 问题 1: 客户端收不到状态推送

**原因**: 未订阅 `device_status` 频道

**解决**:
```dart
// 确保调用了订阅方法
_wsService.subscribeDeviceStatus();
```

### 问题 2: 推送频率过高

**原因**: 状态变化检测逻辑有误，每次都判断为已变化

**解决**:
- 检查 `_has_status_changed()` 函数逻辑
- 确认比较的字段是否正确

### 问题 3: 状态变化但未推送

**原因**: `_status_changed` 标志未正确设置

**解决**:
- 检查轮询服务是否正常运行
- 确认 `_status_changed = True` 是否被执行

## 配置参数

### 后端配置 (.env)

```bash
# 轮询间隔（秒）
PLC_POLL_INTERVAL=5

# WebSocket 推送间隔（秒）
PUSH_INTERVAL=0.1

# 是否输出详细日志
VERBOSE_POLLING_LOG=false
```

### 前端配置

```dart
// WebSocket 心跳间隔（秒）
static const int _heartbeatInterval = 15;

// 重连间隔（秒）
static const int _initialReconnectInterval = 1;
static const int _maxReconnectInterval = 30;
```

## 总结

1. **轮询频率**: 5 秒一次（符合需求）
2. **缓存机制**: 内存缓存 `_latest_status`（已实现）
3. **变化检测**: 比较关键字段，设置 `_status_changed` 标志（新增）
4. **按需推送**: 仅在状态变化时推送（优化完成）
5. **客户端订阅**: Flutter 自动订阅 `device_status` 频道（已实现）

整个流程已经完整实现，可以直接测试使用！


