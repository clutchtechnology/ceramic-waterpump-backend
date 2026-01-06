# ============================================================
# 文件说明: api.py - API 路由汇总展示
# ============================================================
"""
水泵房监控系统 - API 端点汇总

运行本文件可查看所有 API 端点:
    python -m app.routers.api
"""

from fastapi import APIRouter

# 导入所有子路由
from .health import router as health_router
from .realtime import router as realtime_router
from .history import router as history_router
from .config import router as config_router
from .alarms import router as alarms_router
from .devices import router as devices_router


# 创建主路由
api_router = APIRouter()

# 注册所有子路由
api_router.include_router(health_router)
api_router.include_router(realtime_router)
api_router.include_router(history_router)
api_router.include_router(config_router)
api_router.include_router(alarms_router)
api_router.include_router(devices_router)


# ============================================================
# API 端点汇总 (按业务分类)
# ============================================================
"""
┌─────────────────────────────────────────────────────────────┐
│                   水泵房监控系统 API                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【健康检查】 health.py                                      │
│  ├─ GET  /api/health              系统健康检查              │
│  └─ GET  /api/status              系统轮询状态              │
│                                                             │
│  【实时数据】 realtime.py                                    │
│  ├─ GET  /api/realtime/batch      批量实时数据 (6泵+压力)   │
│  ├─ GET  /api/realtime/pressure   压力表实时数据            │
│  └─ GET  /api/realtime/{pump_id}  单个水泵实时数据          │
│                                                             │
│  【历史数据】 history.py                                     │
│  ├─ GET  /api/history             历史数据查询              │
│  └─ GET  /api/statistics          统计数据 (max/min/avg)    │
│                                                             │
│  【配置管理】 config.py                                      │
│  ├─ GET  /api/config/thresholds   获取阈值配置              │
│  └─ POST /api/config/thresholds   更新阈值配置              │
│                                                             │
│  【报警管理】 alarms.py                                      │
│  ├─ GET  /api/alarms              查询报警日志              │
│  └─ GET  /api/alarms/count        报警统计数量              │
│                                                             │
│  【设备状态】 devices.py                                     │
│  └─ GET  /api/status/devices      设备通信状态 (DB3)        │
│                                                             │
└─────────────────────────────────────────────────────────────┘

文件结构:
    app/routers/
    ├── __init__.py       # 导出 api_router
    ├── api.py            # 路由汇总 (本文件)
    ├── utils.py          # 公共工具函数
    ├── health.py         # 健康检查 (2 endpoints)
    ├── realtime.py       # 实时数据 (3 endpoints)
    ├── history.py        # 历史数据 (2 endpoints)
    ├── config.py         # 配置管理 (2 endpoints)
    ├── alarms.py         # 报警管理 (2 endpoints)
    └── devices.py        # 设备状态 (1 endpoint)

总计: 12 个 API 端点
"""


def print_api_summary():
    """打印 API 端点汇总"""
    summary = """
╔═══════════════════════════════════════════════════════════════╗
║               水泵房监控系统 - API 端点汇总                     ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  【健康检查】                                                  ║
║    GET  /api/health                 系统健康检查              ║
║    GET  /api/status                 系统轮询状态              ║
║                                                               ║
║  【实时数据】                                                  ║
║    GET  /api/realtime/batch         批量实时数据              ║
║    GET  /api/realtime/pressure      压力表实时数据            ║
║    GET  /api/realtime/{pump_id}     单个水泵实时数据          ║
║                                                               ║
║  【历史数据】                                                  ║
║    GET  /api/history                历史数据查询              ║
║    GET  /api/statistics             统计数据查询              ║
║                                                               ║
║  【配置管理】                                                  ║
║    GET  /api/config/thresholds      获取阈值配置              ║
║    POST /api/config/thresholds      更新阈值配置              ║
║                                                               ║
║  【报警管理】                                                  ║
║    GET  /api/alarms                 查询报警日志              ║
║    GET  /api/alarms/count           报警统计数量              ║
║                                                               ║
║  【设备状态】                                                  ║
║    GET  /api/status/devices         设备通信状态              ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  总计: 12 个端点  |  前缀: /api                                ║
╚═══════════════════════════════════════════════════════════════╝
"""
    print(summary)


if __name__ == "__main__":
    print_api_summary()
