# Water Pump Backend API 文档

## 快速开始

```bash
# 启动服务 (Docker)
docker compose --profile default up -d --build

# 验证服务
curl http://localhost:8081/health
```

**服务地址**: `http://localhost:8081`

---

## API 端点 (共 7 个)

### 1. 健康检查
```
GET /health
GET /api/waterpump/health
```

### 2. 批量实时数据 (6泵 + 1压力表)
```
GET /api/waterpump/realtime/batch
```

**响应**:
```json
{
  "success": true,
  "timestamp": "2025-12-29T11:00:00Z",
  "source": "mock",
  "data": {
    "pumps": [
      {"id": 1, "voltage": 380.5, "current": 30.2, "power": 10.5, "status": "normal", "alarms": []},
      {"id": 2, "voltage": 379.8, "current": 29.8, "power": 10.3, "status": "normal", "alarms": []}
    ],
    "pressure": {"value": 0.55, "status": "normal"}
  }
}
```

### 3. 单个水泵实时数据
```
GET /api/waterpump/realtime/{pump_id}
```
- `pump_id`: 1-6

### 4. 压力表实时数据
```
GET /api/waterpump/realtime/pressure
```

### 5. 历史数据查询
```
GET /api/waterpump/history?pump_id=1&parameter=voltage&interval=5m
```
- `pump_id`: 1-6 (不传则查压力表)
- `parameter`: voltage / current / power / pressure
- `interval`: 1m / 5m / 1h
- `start` / `end`: ISO 8601 格式 (可选)

### 6. 统计数据
```
GET /api/waterpump/statistics?pump_id=1&parameter=voltage
```

**响应**:
```json
{
  "success": true,
  "statistics": {"max": 400.5, "min": 360.2, "avg": 380.5, "count": 120}
}
```

### 7. 系统状态
```
GET /api/waterpump/status
```

---

## 状态判断规则

| 设备 | 报警 (alarm) | 警告 (warning) |
|------|-------------|---------------|
| 水泵电压 | <360V 或 >400V | <370V 或 >390V |
| 水泵电流 | >50A | >45A |
| 水泵功率 | >30kW | - |
| 压力表 | <0.3 或 >0.8 MPa | <0.4 或 >0.7 MPa |

---

## Flutter 集成

```dart
class ApiConfig {
  static const String baseUrl = 'http://localhost:8081/api/waterpump';
}

// 获取实时数据
final response = await dio.get('${ApiConfig.baseUrl}/realtime/batch');
final pumps = response.data['data']['pumps'];
final pressure = response.data['data']['pressure'];
```

---

## Docker 环境变量

| 变量 | 说明 | Mock模式 | 生产模式 |
|------|------|---------|---------|
| USE_MOCK_DATA | 模拟数据 | true | false |
| USE_REAL_PLC | 真实PLC | false | true |
| PLC_IP | PLC地址 | - | 192.168.x.x |
| INFLUX_URL | InfluxDB | http://influxdb:8086 | 同左 |
| ENABLE_POLLING | 轮询 | true | true |
