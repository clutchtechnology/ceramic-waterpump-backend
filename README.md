# 水泵房监控系统 - 后端服务

FastAPI + InfluxDB + WebSocket 实时数据推送

## 项目架构

```
本地部署架构 (无 Docker)
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  Flutter 前端 (.exe)  ←─ WebSocket (0.1s) ─→  后端 (.exe)  │
│                                                             │
│                                                  ↓          │
│                                          InfluxDB (本地)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 快速启动

### 1. 安装 InfluxDB (本地)

**Windows**:
```powershell
# 下载 InfluxDB 2.x
# https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.10-windows.zip

# 解压后启动
.\influxd.exe

# 浏览器访问 http://localhost:8086 完成初始化
# 创建 Organization: ceramic-workshop
# 创建 Bucket: waterpump
# 保存 Token
```

### 2. 配置后端

```bash
# 复制配置文件
cp .env.example .env

# 编辑 .env，填入 InfluxDB Token
INFLUX_TOKEN=your-token-here
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动后端

```bash
# 开发模式 (带系统托盘)
python main.py

# 或使用 Mock 数据测试
# 在 .env 中设置: USE_MOCK_DATA=true
python main.py
```

### 5. 访问服务

- **API 文档**: http://localhost:8081/docs
- **健康检查**: http://localhost:8081/health
- **WebSocket**: ws://localhost:8081/ws/realtime
- **InfluxDB UI**: http://localhost:8086

## 项目结构

```
ceramic-waterpump-backend/
├── main.py                         # 入口 + 系统托盘
├── config.py                       # 配置管理
├── requirements.txt                # Python 依赖
├── .env                            # 环境变量配置
│
├── configs/                        # YAML 配置文件
│   ├── config_waterpump.yaml      # 设备数据点映射
│   ├── db_mappings.yaml           # DB 块映射
│   └── plc_modules.yaml           # 模块定义
│
├── app/
│   ├── core/
│   │   ├── influxdb.py            # InfluxDB 操作
│   │   ├── local_cache.py         # SQLite 降级缓存
│   │   └── alarm_store.py         # 报警日志
│   │
│   ├── services/
│   │   ├── ws_manager.py          # WebSocket 连接管理
│   │   ├── polling_service.py     # PLC 数据轮询
│   │   └── mock_service.py        # Mock 数据生成
│   │
│   ├── routers/
│   │   ├── websocket.py           # WebSocket 路由
│   │   ├── realtime.py            # 实时数据 API
│   │   ├── history.py             # 历史数据 API
│   │   └── health.py              # 健康检查 API
│   │
│   └── plc/
│       ├── plc_manager.py         # PLC 连接管理
│       └── parser_waterpump.py    # 数据解析器
│
├── scripts/
│   └── tray_app.py                # 系统托盘应用
│
└── logs/                           # 日志文件
```

## 核心功能

### 1. WebSocket 实时推送

- **推送间隔**: 0.1 秒 (每秒 10 次)
- **推送内容**: 6 台水泵 + 1 个压力表
- **自动重连**: 指数退避策略
- **心跳保活**: 客户端 15 秒，服务端 45 秒超时

### 2. 数据轮询 (Mock 模式)

- **轮询间隔**: 5 秒
- **数据生成**: MockService 随机生成
- **批量写入**: 每 10 次轮询批量写入 InfluxDB
- **本地缓存**: InfluxDB 故障时自动降级到 SQLite

### 3. 健康检查

- **InfluxDB 状态**: 实时检测连接状态
- **PLC 状态**: Mock 模式 / 真实连接
- **轮询服务**: 运行状态监控

## API 接口

### 健康检查

```bash
GET /health
```

返回示例:
```json
{
  "success": true,
  "status": "ok",
  "mode": "mock",
  "components": {
    "influxdb": "ok",
    "plc": "mock",
    "polling_enabled": true,
    "polling_running": true
  }
}
```

### 实时数据 (HTTP)

```bash
GET /api/realtime/batch
```

### 历史数据

```bash
GET /api/history/elec?pump_id=1&parameter=power&start=2026-01-01T00:00:00Z&end=2026-01-01T01:00:00Z&interval=5m
GET /api/history/press?parameter=pressure&start=2026-01-01T00:00:00Z&end=2026-01-01T01:00:00Z&interval=5m
```

### WebSocket 实时推送

```javascript
// 连接
const ws = new WebSocket('ws://localhost:8081/ws/realtime');

// 订阅实时数据
ws.send(JSON.stringify({
  type: 'subscribe',
  channel: 'realtime'
}));

// 接收数据
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.data.pumps); // 6 台水泵数据
  console.log(data.data.pressure); // 压力表数据
};

// 心跳
setInterval(() => {
  ws.send(JSON.stringify({
    type: 'heartbeat',
    timestamp: new Date().toISOString()
  }));
}, 15000);
```

## 打包为 .exe

### 使用 PyInstaller

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包 (已配置 PumpMonitor.spec)
pyinstaller PumpMonitor.spec

# 输出目录
dist/PumpMonitor/PumpMonitor.exe
```

### 打包后的目录结构

```
dist/PumpMonitor/
├── PumpMonitor.exe              # 主程序
├── configs/                     # 配置文件
├── data/                        # 数据目录 (SQLite 缓存)
├── logs/                        # 日志目录
└── _internal/                   # 依赖库
```

## 配置说明

### .env 配置

```bash
# InfluxDB 配置
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=your-token-here
INFLUX_ORG=ceramic-workshop
INFLUX_BUCKET=waterpump

# 服务配置
HOST=0.0.0.0
PORT=8081

# Mock 模式 (开发测试)
USE_MOCK_DATA=true

# 轮询配置
ENABLE_POLLING=true
PLC_POLL_INTERVAL=5
BATCH_SIZE=10

# 日志配置
LOG_LEVEL=INFO
VERBOSE_POLLING_LOG=false
```

### PLC 真实模式

```bash
# 修改 .env
USE_MOCK_DATA=false
USE_REAL_PLC=true
PLC_IP=192.168.50.224
PLC_RACK=0
PLC_SLOT=1
```

## 开发指南

### 添加新的 API 端点

1. 在 `app/routers/` 创建新的路由文件
2. 在 `app/routers/api.py` 中注册路由
3. 重启服务

### 修改 WebSocket 推送逻辑

编辑 `app/services/ws_manager.py` 的 `_push_realtime_data` 方法

### 修改数据解析

编辑 `app/plc/parser_waterpump.py` 或 `configs/config_waterpump.yaml`

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| InfluxDB 连接失败 | 检查 InfluxDB 是否运行，Token 是否正确 |
| WebSocket 连接失败 | 检查防火墙，确保 8081 端口开放 |
| 数据不更新 | 检查轮询服务是否运行，查看日志 |
| 内存占用高 | 降低推送频率或批量写入大小 |

## 系统要求

- **操作系统**: Windows 10/11, Linux
- **Python**: 3.8+
- **内存**: 最低 2GB，推荐 4GB
- **磁盘**: 最低 10GB (用于 InfluxDB 数据存储)
- **网络**: 如果连接真实 PLC，需要工业以太网

## License

MIT
