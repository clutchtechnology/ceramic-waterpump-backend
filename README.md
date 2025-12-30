# Waterpump Backend

水泵房数字监控后端 - FastAPI + InfluxDB

## 快速启动

### 方案 A: Docker 部署 (Windows/Linux 推荐)

```bash
# 1. 启动 InfluxDB (Docker)
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动后端
python main.py
```

### 方案 B: 本地安装 (Android 工控机/无 Docker 环境)

**详细安装指南**: [INFLUXDB_INSTALL.md](INFLUXDB_INSTALL.md)

```bash
# 1. 下载并安装 InfluxDB (根据平台选择)
# Windows: 见 INFLUXDB_INSTALL.md
# Linux/Android: 见 INFLUXDB_INSTALL.md 或 DEPLOY_ANDROID.md

# 2. 启动 InfluxDB
./influxd --bolt-path=./data/influxd.bolt --engine-path=./data/engine

# 3. 初始化 InfluxDB (浏览器访问 http://localhost:8086 或使用 CLI)
./influx setup --username admin --password adminpass --org ceramic-workshop --bucket waterpump

# 4. 安装 Python 依赖
pip install -r requirements.txt

# 5. 配置 .env (填写 InfluxDB Token)
cp .env.example .env
# 编辑 INFLUX_TOKEN=<your-token>

# 6. 启动后端
python main.py
```

**访问地址**:
- API 文档: http://localhost:8081/docs
- 实时数据: http://localhost:8081/api/waterpump/realtime
- 历史数据: http://localhost:8081/api/waterpump/history
- InfluxDB UI: http://localhost:8086

**📱 Android 工控机部署**: 查看 [DEPLOY_ANDROID.md](DEPLOY_ANDROID.md) 完整指南  
**💾 InfluxDB 本地安装**: 查看 [INFLUXDB_INSTALL.md](INFLUXDB_INSTALL.md) 详细步骤

### 🧪 Mock 模式 (无 PLC 环境测试)

```bash
# 方法1: 使用独立的 Mock 轮询服务 (推荐)
python tests/mock/mock_polling_service.py

# 方法2: 测试 Mock 数据生成器
python tests/mock/test_mock_generator.py

# 方法3: 配置 .env 使用内置模拟模式
# USE_REAL_PLC=false
python main.py
```

## 项目结构

```
ceramic-waterpump-backend/
├── main.py                         # 入口 + 生命周期管理
├── config.py                       # 配置 (InfluxDB/PLC地址)
├── docker-compose.yml              # InfluxDB 容器
├── requirements.txt                # Python 依赖
│
├── configs/                        # YAML 配置文件 (动态配置)
│   ├── db_mappings.yaml           # DB块映射配置 (DB1状态 + DB2数据)
│   ├── plc_modules.yaml           # 基础模块定义 (电表56B + 压力2B)
│   ├── config_waterpump.yaml      # DB2 设备配置 (6电表+1压力)
│   └── config_status.yaml         # DB1 状态配置 (通信状态)
│
└── app/
    ├── core/influxdb.py           # InfluxDB 读写
    ├── plc/
    │   ├── parser_waterpump.py    # DB2 数据解析器
    │   └── parser_status.py       # DB1 状态解析器
    ├── services/
    │   └── polling_service.py     # 5s轮询 (带状态检查)
    ├── tools/
    │   ├── converter_base.py      # 转换器基类
    │   ├── converter_elec.py      # 电表转换器
    │   ├── converter_pressure.py  # 压力表转换器
    │   └── converter_status.py    # 状态转换器
    └── routers/
        └── waterpump.py           # 水泵API路由
```

## PLC 数据结构

### DB1 - 状态块 (MBValueTemp, 56字节)

| 偏移量 | 名称 | 类型 | 说明 |
|--------|------|------|------|
| 0 | MB_COMM_LOAD | Struct(4B) | 通信模块初始化状态 |
| 4 | DB_MASTER_ELEC_0 | Struct(4B) | 电表1通信状态 |
| 8 | DB_MASTER_ELEC_1 | Struct(4B) | 电表2通信状态 |
| ... | ... | ... | ... |
| 52 | DB_MASTER_PRESS | Struct(4B) | 压力表通信状态 |

每个状态块结构：
- Bit 0: DONE (通信完成)
- Bit 1: BUSY (正在通信)
- Bit 2: ERROR (通信错误)
- Byte 2-3: STATUS (状态字 Word)

### DB2 - 数据块 (Data_DB, 338字节)

| 偏移量 | 名称 | 大小 | 说明 |
|--------|------|------|------|
| 0 | ElectricityMeter_0 | 56B | 1号泵电表 |
| 56 | ElectricityMeter_1 | 56B | 2号泵电表 |
| 112 | ElectricityMeter_2 | 56B | 3号泵电表 |
| 168 | ElectricityMeter_3 | 56B | 4号泵电表 |
| 224 | ElectricityMeter_4 | 56B | 5号泵电表 |
| 280 | ElectricityMeter_5 | 56B | 6号泵电表 |
| 336 | Press_Data | 2B | 压力表 (Word) |

## 数据流

```
PLC轮询 (5秒)
   ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. 读取 DB1 状态块 + DB2 数据块 (PLC Manager 长连接)             │
│    - PLC Manager 维持持久连接，避免频繁重连                      │
│    - 自动重连机制 (最多3次)                                     │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 解析 + 转换 (Parser + Converter)                             │
│    - 状态检查: 只处理 DONE=1 && ERROR=0 的设备                  │
│    - 数据转换: 原始字段 → 存储字段                               │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. 批量缓冲 (Point Buffer, deque 最大1000点)                    │
│    - 每次轮询产生的数据点进入缓冲区                              │
│    - 轮询计数达到 BATCH_SIZE (默认30) 触发批量写入               │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. 写入 InfluxDB (批量写入)                                      │
│    ✅ 成功 → 清空缓冲区，influx_write_count++                    │
│    ❌ 失败 → 触发本地缓存机制                                    │
└─────────────────────────────────────────────────────────────────┘
                    ↓ (失败时)
┌─────────────────────────────────────────────────────────────────┐
│ 5. 本地 SQLite 缓存 (降级存储)                                   │
│    - 保存失败的数据点到 data/cache.db                           │
│    - 记录重试次数、时间戳                                        │
│    - cache_save_count++                                         │
└─────────────────────────────────────────────────────────────────┘
   ↓ (后台任务 60秒)
┌─────────────────────────────────────────────────────────────────┐
│ 6. 缓存重试机制 (Retry Worker)                                  │
│    - 每60秒检查 InfluxDB 健康状态                                │
│    - 健康时批量读取 pending_points (最多100点)                   │
│    - 重试写入成功 → 标记删除                                     │
│    - 重试失败 → retry_count++ (最多5次后放弃)                    │
└─────────────────────────────────────────────────────────────────┘
   ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. REST API 提供数据查询                                         │
│    - /api/waterpump/realtime  (实时数据)                        │
│    - /api/waterpump/history   (历史数据)                        │
│    - /api/waterpump/stats     (轮询统计)                        │
└─────────────────────────────────────────────────────────────────┘
```

## 核心优化

### 1. 批量写入 (Batch Write)

**问题**: 每次轮询(5秒)产生7个数据点，频繁写入InfluxDB消耗资源

**解决**:
- 使用 `deque(maxlen=1000)` 作为缓冲区
- 每30次轮询 (150秒) 触发一次批量写入
- 单次写入 210 个点 (30次×7点)
- 写入频率从 12次/分 降低到 0.4次/分 (减少30倍)

**配置**:
```python
# config.py
batch_size: int = 30  # 调整批量大小
```

### 2. 本地缓存 (Local Cache)

**问题**: InfluxDB 故障时数据丢失

**解决**:
- SQLite 作为本地降级存储 (`data/cache.db`)
- 写入失败时自动保存到缓存表 `pending_points`
- 后台任务每60秒重试 (最多5次)
- 数据结构: measurement, tags (JSON), fields (JSON), timestamp, retry_count

**配置**:
```python
# config.py
local_cache_path: str = "data/cache.db"  # SQLite 路径
cache_retry_interval: int = 60           # 重试间隔(秒)
cache_max_retry: int = 5                 # 最大重试次数
```

### 3. PLC 长连接 (Persistent Connection)

**问题**: 每次轮询 connect() → read() → disconnect() 消耗大量时间

**解决**:
- `PLCManager` 单例维持持久连接
- 自动重连机制 (连接失败最多重试3次)
- 线程安全 (使用 `threading.Lock()`)
- 统计信息: 读取次数、错误次数、平均耗时

**统计数据**:
```json
{
  "plc_stats": {
    "connected": true,
    "read_count": 150,
    "error_count": 2,
    "reconnect_count": 1,
    "avg_read_time": 45.3
  }
}
```


## InfluxDB 存储字段

**Measurement**: `sensor_data`

### Tags (索引)

| Tag          | 说明         |
|--------------|--------------|
| device_id    | 设备ID (meter_1 ~ meter_6, pressure_1) |
| module_type  | 模块类型 (ElectricityMeter, PressureSensor) |

### Fields (按模块类型)

| 模块类型 | 存储字段 | 说明 |
|----------|----------|------|
| **ElectricityMeter** | `Pt`, `ImpEp`, `Ua_0`, `I_0` | 功率(kW), 电能(kWh), 电压(V), 电流(A) |
| **PressureSensor** | `pressure_kpa` | 压力(kPa) |
| **CommStatus** | `comm_done`, `comm_error`, `comm_status` | 通信完成, 通信错误, 状态码 |

## API 端点

### 1️⃣ 健康检查

```bash
GET /health
```

### 2️⃣ 设备实时状态

```bash
GET /api/waterpump/device_status
```

返回所有设备的最新数据 + 通信状态

### 3️⃣ 实时数据 (兼容旧版)

```bash
GET /api/waterpump/realtime
```

### 4️⃣ 历史数据

```bash
GET /api/waterpump/history?device_id=meter_1&start=2024-01-01T00:00:00Z&end=2024-01-02T00:00:00Z&interval=5m
```

### 5️⃣ 轮询统计 (新增)

```bash
GET /api/waterpump/stats
```

返回:
- `polling_count`: 累计轮询次数
- `buffer_size`: 当前缓冲区点数
- `influx_write_count`: InfluxDB 写入次数
- `cache_save_count`: 本地缓存保存次数
- `cache_pending`: 待重试缓存点数
- `plc_stats`: PLC 连接统计
  - `connected`: 当前连接状态
  - `read_count`: 累计读取次数
  - `error_count`: 累计错误次数
  - `reconnect_count`: 累计重连次数
  - `avg_read_time`: 平均读取时间(ms)

## 测试

### 快速测试

```bash
# 测试统计端点 + 设备状态
python scripts/test_integration.py
```

### 完整测试 (可选)

```bash
# 测试批量缓冲 (需等待150秒)
python scripts/test_integration.py
# 输入: y

# 测试本地缓存 (需手动停止InfluxDB)
# 1. docker stop ceramic-influxdb
# 2. 等待系统保存到缓存
# 3. docker start ceramic-influxdb
# 4. 观察自动重试
```

## 部署

### 选项 1: Docker 部署 (Windows/Linux)

```bash
# 开发环境
docker-compose up -d

# 生产环境
docker-compose -f deploy/docker-compose.prod.yml up -d
```

### 选项 2: 本地安装 (无 Docker 环境)

#### Windows 本地安装

```powershell
# 1. 下载 InfluxDB Windows 版本
# https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.10-windows.zip

# 2. 解压到 C:\influxdb

# 3. 启动 InfluxDB
cd C:\influxdb
.\influxd.exe

# 4. 浏览器访问 http://localhost:8086 完成初始化

# 5. 配置后端 .env
cp .env.example .env
# 编辑 INFLUX_TOKEN

# 6. 启动后端
python main.py

# 7. 安装为 Windows 服务 (可选)
.\install_as_service.ps1
```

#### Linux/Android 本地安装

```bash
# 1. 下载 InfluxDB (根据架构选择)
# AMD64: https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.10_linux_amd64.tar.gz
# ARM64: https://dl.influxdata.com/influxdb/releases/influxdb2-2.7.10_linux_arm64.tar.gz

# 2. 解压
tar xzf influxdb2-2.7.10_linux_*.tar.gz

# 3. 启动 InfluxDB
./influxd --bolt-path=./data/influxd.bolt --engine-path=./data/engine &

# 4. 初始化
./influx setup \
  --username admin \
  --password adminpass123 \
  --org ceramic-workshop \
  --bucket waterpump \
  --force

# 5. 配置后端
cp .env.example .env
# 编辑 INFLUX_TOKEN (从 ./influx auth list 获取)

# 6. 启动后端
python main.py
```

#### 📱 Android 工控机部署 (Termux)

**完整部署指南**: [DEPLOY_ANDROID.md](DEPLOY_ANDROID.md)

**一键部署**:
```bash
# 在 Termux 中执行
bash scripts/android_deploy.sh
```

**特点**:
- ✅ 无需 Docker
- ✅ 原生 ARM64 InfluxDB
- ✅ 轻量级 (~600MB 内存)
- ✅ 开机自启 (Termux:Boot)

### 本地开发 (Docker)

```bash
# 1. 复制配置
cp .env.example .env

# 2. 修改 .env
# USE_REAL_PLC=false  (开发时使用模拟数据)
# BATCH_SIZE=30
# LOCAL_CACHE_PATH=data/cache.db

# 3. 启动 InfluxDB
docker-compose up -d

# 4. 启动后端
python main.py
```

## 文件说明

| 文件 | 说明 |
|------|------|
| **app/core/local_cache.py** | SQLite 缓存管理器 (降级存储) |
| **app/plc/plc_manager.py** | PLC 长连接管理器 (单例) |
| **app/services/polling_service.py** | 轮询服务 (批量缓冲 + 缓存重试) |
| **app/core/influxdb.py** | InfluxDB 操作 (批量写入) |
| **scripts/test_integration.py** | 完整集成测试脚本 |
GET /api/waterpump/health
```

**返回示例**:
```json
{
  "success": true,
  "status": "ok",
  "components": {
    "influxdb": "ok",
    "polling_enabled": true,
    "polling_running": true
  },
  "timestamp": "2025-12-24T10:00:00Z"
}
```

### 2️⃣ Device Status (设备通信状态 - 来自 DB1)

```bash
GET /api/waterpump/status
```

**说明**:
- 返回所有设备的 Modbus 通信状态
- 用于判断设备数据是否可信

**返回示例**:
```json
{
  "success": true,
  "timestamp": "2025-12-24T10:00:00Z",
  "summary": {
    "total_devices": 8,
    "ok_count": 7,
    "error_count": 1,
    "all_ok": false
  },
  "devices": {
    "pump_meter_1": {
      "done": true,
      "busy": false,
      "error": false,
      "status": 0,
      "comm_state": "ok"
    },
    "pump_meter_2": {
      "done": false,
      "busy": false,
      "error": true,
      "status": 32769,
      "comm_state": "error"
    }
  }
}
```


### 3️⃣ Realtime 接口 (实时数据)

```bash
GET /api/waterpump/realtime
```

**说明**:
- 优先返回内存缓存（最近一次轮询结果）
- 缓存为空时查询 InfluxDB 最近 1 分钟数据
- 自动按设备分组
- **只返回通信状态正常的设备数据**


**返回示例**:
```json
{
  "success": true,
  "timestamp": "2025-12-24T10:00:00Z",
  "device_count": 7,
  "devices": {
    "meter_1": {
      "Pt": 45.67,
      "ImpEp": 1234.56,
      "Ua_0": 220.5,
      "I_0": 12.34
    },
    "meter_2": {
      "Pt": 52.18,
      "ImpEp": 1245.78,
      "Ua_0": 219.8,
      "I_0": 13.02
    },
    "meter_3": {...},
    "meter_4": {...},
    "meter_5": {...},
    "meter_6": {...},
    "pressure_1": {
      "pressure_kpa": 101.325
    }
  }
}
```

### 3️⃣ History 接口 (历史数据 - 支持聚合)

```bash
GET /api/waterpump/history
```

**参数**:

| 参数 | 说明 | 示例 | 默认值 |
|------|------|------|--------|
| `start` | 开始时间 (ISO 8601) | `2025-12-24T00:00:00` | 当前时间前 1 小时 |
| `end` | 结束时间 (ISO 8601) | `2025-12-24T12:00:00` | 当前时间 |
| `interval` | 聚合间隔 | `1m`, `5m`, `10m`, `30m`, `1h`, `1d` | `1m` (1分钟) |

**使用示例**:

```bash
# 1. 最近1小时，1分钟聚合（默认）
GET /api/waterpump/history

# 2. 最近1小时，5分钟聚合
GET /api/waterpump/history?interval=5m

# 3. 自定义时间范围，1小时聚合
GET /api/waterpump/history?start=2025-12-24T00:00:00&end=2025-12-24T12:00:00&interval=1h

# 4. 最近24小时，1小时聚合
GET /api/waterpump/history?interval=1h
```

**返回示例**:
```json
{
  "success": true,
  "query": {
    "start": "2025-12-24T09:00:00Z",
    "end": "2025-12-24T10:00:00Z",
    "interval": "5m"
  },
  "data_points": 12,
  "data": [
    {
      "timestamp": "2025-12-24T09:00:00Z",
      "devices": {
        "meter_1": {
          "Pt": 45.67,
          "ImpEp": 1234.56,
          "Ua_0": 220.5,
          "I_0": 12.34
        },
        "pressure_1": {
          "pressure_kpa": 101.325
        }
      }
    },
    {
      "timestamp": "2025-12-24T09:05:00Z",
      "devices": {...}
    },
    ...
  ]
}
```

## 设备清单

| 设备ID | 名称 | 类型 | 模块 |
|--------|------|------|------|
| meter_1 ~ meter_6 | 电表 1-6 | waterpump | ElectricityMeter |
| pressure_1 | 压力表 | waterpump | PressureSensor |

## 配置文件说明

### db_mappings.yaml

定义 PLC DB 块到 Parser 类的映射（动态配置核心）

```yaml
db_mappings:
  - db_number: 11              # PLC DB块号
    db_name: "DB11_Waterpump"
    total_size: 128            # DB块总字节数
    config_file: "configs/config_waterpump.yaml"
    parser_class: "WaterpumpParser"
    enabled: true
```

### plc_modules.yaml

定义模块类型与字段结构（可复用于多个DB块）

```yaml
plc_modules:
  - module_type: "ElectricityMeter"
    size: 40
    fields:
      - name: "Pt"
        display_name: "总有功功率"
        unit: "kW"
        data_type: "Real"
        offset: 0
```

### config_waterpump.yaml

定义具体设备与模块配置（设备级配置）

```yaml
devices:
  - device_id: "meter_1"
    device_name: "泵房电表-1"
    db_number: 11
    modules:
      - module_type: "ElectricityMeter"
        start_offset: 0
```

## 环境变量 (.env)

```bash
# InfluxDB
INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=waterpump-token
INFLUX_ORG=waterpump
INFLUX_BUCKET=sensor_data

# PLC (可选)
PLC_IP=192.168.0.100
PLC_RACK=0
PLC_SLOT=1
PLC_POLL_INTERVAL=5
ENABLE_POLLING=true
```

## 开发指南

### 添加新的模块类型

1. 在 `configs/plc_modules.yaml` 定义模块结构
2. 在 `app/tools/` 创建转换器 (继承 BaseConverter)
3. 在 `app/routers/waterpump.py` 的查询中引用新字段

### 修改设备配置

只需编辑 `configs/config_waterpump.yaml`，重启后端即可生效。无需修改代码。

### 接入真实 PLC

修改 `app/services/polling_service.py`，替换模拟数据逻辑为实际的 PLC 读取：

```python
# 当前（模拟数据）
raw = {"Pt": random.randint(0, 5000), ...}

# 改为（真实PLC）
from snap7.client import Client
plc = Client()
plc.connect(settings.plc_ip, settings.plc_rack, settings.plc_slot)
db_bytes = plc.db_read(11, 0, 128)
raw = parse_waterpump_db(db_bytes)
```

## 测试

```bash
# 确保 docker 中 influxdb 运行
docker-compose up -d

# 启动后端
python3 main.py

# 验证实时数据
curl http://localhost:8081/api/waterpump/realtime | python -m json.tool

# 查询历史数据
curl "http://localhost:8081/api/waterpump/history?start=2025-12-24T00:00:00&end=2025-12-24T12:00:00" | python -m json.tool
```

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| InfluxDB 连接失败 | 确保 `docker-compose up -d` 运行，检查 `localhost:8086` |
| 无数据写入 | 检查 `ENABLE_POLLING=true` 和轮询服务日志 |
| PLC 连接失败 | 检查 `PLC_IP`，确认网络连通 |
| CPU/内存占用高 | 访问 `/api/waterpump/resources` 查看资源监控，降低轮询频率 |
| 缓冲区满告警 | 检查 InfluxDB 写入性能，增大 `batch_size` 或降低轮询频率 |

## 🏭 工控机部署指南

### 部署前检查

```powershell
# 1. 运行部署检查脚本
python scripts/check_deployment.py

# 检查项包括:
# - Python 版本 (≥3.8)
# - 依赖库完整性
# - InfluxDB 运行状态
# - 磁盘空间 (建议 >10GB)
# - 防火墙端口 (8081, 8086, 102)
# - 配置文件 (.env)
```

### 安装为 Windows 服务 (推荐)

```powershell
# 以管理员身份运行 PowerShell
.\install_as_service.ps1

# 服务管理命令
nssm status CeramicWaterpumpBackend   # 查看状态
nssm stop CeramicWaterpumpBackend     # 停止服务
nssm start CeramicWaterpumpBackend    # 启动服务
nssm restart CeramicWaterpumpBackend  # 重启服务

# 查看日志
Get-Content logs\service_stdout.log -Tail 50 -Wait
```

**服务特性**:
- ✅ 开机自启动
- ✅ 崩溃自动重启 (5秒后)
- ✅ 日志自动轮转 (10MB)
- ✅ 无需登录即可运行

### 关键配置项 (.env)

```bash
# PLC 配置
USE_REAL_PLC=true           # 生产环境设为 true
PLC_IP=192.168.1.10
PLC_RACK=0
PLC_SLOT=1

# 批量写入优化
BATCH_SIZE=30               # 轮询30次后批量写入
POLLING_INTERVAL=5          # 轮询间隔(秒)

# 本地缓存 (InfluxDB故障时)
LOCAL_CACHE_PATH=data/cache.db
CACHE_RETRY_INTERVAL=60     # 重试间隔(秒)
CACHE_MAX_RETRY=5           # 最大重试次数
```

### 监控端点

```bash
# 轮询统计
curl http://localhost:8081/api/waterpump/stats

# 系统资源
curl http://localhost:8081/api/waterpump/resources
```

**资源监控告警阈值**:
- CPU > 90%: 建议降低轮询频率
- 内存 > 90%: 检查是否有内存泄漏
- 磁盘 > 90%: 清理日志或扩容

### 注意事项

| 风险点 | 建议 |
|--------|------|
| **Windows 自动更新** | 在工控机上禁用自动重启，改为通知模式 |
| **散热问题** | 定期清理风扇灰尘，确保通风良好 |
| **端口冲突** | 确保 8081(后端)、8086(InfluxDB) 未被占用 |
| **PLC 网络** | 使用独立工业以太网，避免与办公网混用 |
| **备份策略** | 定期备份 InfluxDB 数据和 `data/cache.db` |

### AI 识别集成注意

如果集成煤矸石识别等 AI 模块：

1. **资源隔离**: AI 推理尽量使用独立进程，避免阻塞 PLC 采集线程
2. **GPU 管理**: 监控 GPU 温度，避免降频影响性能
3. **内存控制**: 限制 AI 模型加载数量，避免内存溢出
4. **优先级**: PLC 采集优先级 > AI 推理 > 界面渲染

## License

MIT
