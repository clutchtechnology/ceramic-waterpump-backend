# 设备状态推送功能测试指南

## 测试目标

验证 DB1/DB3 设备状态的 WebSocket 推送功能是否正常工作。

## 测试步骤

### 1. 启动后端服务

```powershell
cd c:/Users/20216/Documents/GitHub/Clutch/ceramic-waterpump-backend
py main.py
```

**预期日志**:
```
[DB1/DB3状态] Mock模式启动
[DB1/DB3状态] 轮询服务已启动 (Mock模式, 间隔: 5s)
[WS] 推送任务已启动 (间隔: 0.1s, 心跳超时: 45s)
```

### 2. 启动 Flutter 客户端

```powershell
cd c:/Users/20216/Documents/GitHub/Clutch/ceramic-waterpump-flutter
flutter run -d windows
```

### 3. 打开设备状态页面

在 Flutter 应用中，点击"设备状态"标签页。

### 4. 观察后端日志

**首次连接时**:
```
[WS] 新连接建立 (来自 127.0.0.1)，当前连接数: 1
[WS] 客户端订阅频道: device_status, 当前该频道订阅数: 1
[DB1/DB3状态 poll #1] 状态已更新，标记为已变化
[WS] 推送 device_status (状态已变化) -> 1 个订阅者
```

**后续轮询时**:
```
[DB1/DB3状态 poll #2] 状态未变化
[DB1/DB3状态 poll #3] 状态未变化
[DB1/DB3状态 poll #4] 状态已更新，标记为已变化
[WS] 推送 device_status (状态已变化) -> 1 个订阅者
```

### 5. 观察 Flutter 日志

**连接成功**:
```
[WebSocket] 连接成功: ws://localhost:8081/ws/realtime
```

**收到状态推送**:
```
[WebSocket] 收到设备状态更新: 6 个设备
```

### 6. 验证 UI 显示

检查设备状态页面是否显示：
- DB1 区域：6 个设备（1#电表 ~ 6#电表）
- DB3 区域：0 个设备（或根据配置显示）
- 统计信息：总计 6，正常 6，异常 0
- 每个设备显示：绿色状态灯、设备名称、Error 值、Status 值

## 测试场景

### 场景 1: 正常状态推送

**操作**: 保持默认 Mock 数据

**预期**:
- 首次连接时推送一次状态
- 后续每 5 秒检查一次，如果状态未变化则不推送
- UI 显示所有设备正常（绿色状态灯）

### 场景 2: 模拟设备故障

**操作**: 修改 Mock 数据生成器，让某个设备的 Error 位为 1

**文件**: `tests/mock/mock_data_generator.py`

```python
# 找到 generate_db1_data() 方法
# 修改第一个设备的 Error 位
db1_data[0] = 1  # Error 位设置为 1
```

**预期**:
- 后端检测到状态变化
- 立即推送状态更新
- Flutter UI 显示该设备为红色状态灯
- 统计信息更新：异常 1

### 场景 3: 页面切换

**操作**: 
1. 切换到其他页面（如"实时数据"）
2. 等待 10 秒
3. 切换回"设备状态"页面

**预期**:
- 切换出去时，订阅暂停
- 切换回来时，订阅恢复
- 立即显示最新状态

### 场景 4: 网络断开重连

**操作**:
1. 停止后端服务
2. 等待 5 秒
3. 重启后端服务

**预期**:
- Flutter 自动重连（指数退避：1s, 2s, 4s, 8s...）
- 重连成功后自动重新订阅
- 恢复状态推送

## 性能验证

### 推送频率测试

**目标**: 验证状态未变化时不推送

**方法**:
1. 观察后端日志，统计 30 秒内的推送次数
2. 如果状态未变化，应该只推送 1 次（首次连接）
3. 如果状态变化，推送次数 = 变化次数

**预期**:
- Mock 模式下，状态通常不变化，30 秒内推送 1 次
- 实际 PLC 模式下，推送次数取决于设备状态变化频率

### 网络流量测试

**优化前**: 每 0.1 秒推送一次，30 秒 = 300 次推送
**优化后**: 仅在变化时推送，30 秒 = 1-6 次推送（减少 98% 流量）

## 故障排查

### 问题 1: Flutter 收不到状态推送

**检查清单**:
1. 后端服务是否正常运行？
2. WebSocket 是否连接成功？（查看 Flutter 日志）
3. 是否订阅了 `device_status` 频道？（查看后端日志）
4. 状态是否发生变化？（查看后端日志）

**解决方法**:
```dart
// 在 sensor_status_page.dart 的 initState 中添加日志
print('[设备状态页面] 开始订阅设备状态');
_statusService.startPolling();
```

### 问题 2: 推送频率过高

**检查清单**:
1. 查看后端日志，是否每次都显示"状态已更新，标记为已变化"？
2. 检查 `_has_status_changed()` 函数逻辑是否正确

**解决方法**:
```python
# 在 polling_service_status_db1_3.py 中添加调试日志
logger.debug(f"[状态比较] 旧状态: {old_status}")
logger.debug(f"[状态比较] 新状态: {new_status}")
logger.debug(f"[状态比较] 是否变化: {changed}")
```

### 问题 3: UI 不更新

**检查清单**:
1. 回调函数是否正确设置？
2. `setState()` 是否被调用？
3. `mounted` 检查是否通过？

**解决方法**:
```dart
// 在 sensor_status_page.dart 的回调中添加日志
_statusService.onDataUpdate = (data) {
  print('[设备状态页面] 收到状态更新: ${data.summary?.total ?? 0} 个设备');
  if (mounted && _isPollingActive) {
    setState(() {
      _response = data;
    });
  }
};
```

## 测试命令汇总

```powershell
# 1. 启动后端（Mock 模式）
cd c:/Users/20216/Documents/GitHub/Clutch/ceramic-waterpump-backend
py main.py

# 2. 启动 Flutter
cd c:/Users/20216/Documents/GitHub/Clutch/ceramic-waterpump-flutter
flutter run -d windows

# 3. 检查后端语法
cd c:/Users/20216/Documents/GitHub/Clutch/ceramic-waterpump-backend
py -m py_compile app/services/ws_manager.py
py -m py_compile app/services/polling_service_status_db1_3.py

# 4. 查看后端日志（筛选状态相关）
# 在后端运行时，观察控制台输出
```

## 预期结果

1. 后端每 5 秒轮询一次 DB1/DB3 状态
2. 仅在状态变化时通过 WebSocket 推送
3. Flutter 客户端实时更新设备状态显示
4. 网络流量大幅减少（相比每 0.1 秒推送）
5. 用户体验流畅，无明显延迟

## 完成标志

- [ ] 后端服务正常启动
- [ ] Flutter 客户端连接成功
- [ ] 设备状态页面显示正常
- [ ] 状态变化时实时推送
- [ ] 状态未变化时不推送
- [ ] 页面切换时订阅正常暂停/恢复
- [ ] 网络断开后自动重连

全部完成后，功能测试通过！











