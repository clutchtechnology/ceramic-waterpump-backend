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
from .history import router as history_router
from .config import router as config_router
from .thresholds import router as thresholds_router
from .alarms import router as alarms_router
from .websocket import router as websocket_router


# 创建主路由
api_router = APIRouter()

# 创建 WebSocket 路由 (独立前缀 /ws)
ws_router = APIRouter()

# 注册所有子路由
api_router.include_router(health_router)
api_router.include_router(history_router)
api_router.include_router(config_router)
api_router.include_router(thresholds_router)
api_router.include_router(alarms_router)

# WebSocket 路由单独导出
ws_router.include_router(websocket_router)


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
│  【实时数据】 WebSocket (已替代 HTTP 轮询)                   │
│  └─ WS   /ws/realtime             实时数据推送 (0.1s)       │
│                                                             │
│  【历史数据】 history.py                                     │
│  ├─ GET  /api/waterpump/history   统一历史数据查询          │
│  ├─ GET  /api/history/press       [已废弃] 压力历史数据     │
│  ├─ GET  /api/history/elec        [已废弃] 电表历史数据     │
│  └─ GET  /api/history/vibration   [已废弃] 振动历史数据     │
│                                                             │
│  【配置管理】 config.py                                      │
│  └─ GET  /api/config/server       获取服务端运行配置(只读)  │
│                                                             │
│  【阈值管理】 thresholds.py                                  │
│  ├─ GET  /api/thresholds          获取所有阈值配置          │
│  ├─ POST /api/thresholds          更新阈值配置              │
│  └─ POST /api/thresholds/reset    重置为默认值              │
│                                                             │
│  【报警管理】 alarms.py                                      │
│  ├─ GET  /api/alarms/records      查询报警记录              │
│  ├─ GET  /api/alarms/count        报警数量统计              │
│  └─ GET  /api/alarms/thresholds   获取报警阈值              │
│                                                             │
└─────────────────────────────────────────────────────────────┘

文件结构:
    app/routers/
    ├── __init__.py       # 导出 api_router
    ├── api.py            # 路由汇总 (本文件)
    ├── utils.py          # 公共工具函数
    ├── health.py         # 健康检查 (2 endpoints)
    ├── history.py        # 历史数据 (1 新接口 + 3 废弃接口)
    ├── config.py         # 配置管理 (1 endpoint)
    ├── thresholds.py     # 阈值管理 (3 endpoints)
    ├── alarms.py         # 报警管理 (3 endpoints)
    └── websocket.py      # WebSocket 实时推送 (1 endpoint)

总计: 11 个 HTTP 端点 (含3个废弃) + 1 个 WebSocket 端点
"""


def print_api_summary():
    """打印 API 端点汇总"""
    summary = """
===================================================================
              水泵房监控系统 - API 端点汇总
===================================================================

  [健康检查]
    GET  /api/health                 系统健康检查
    GET  /api/status                 系统轮询状态

  [实时数据] WebSocket 推送 (已替代 HTTP 轮询)
    WS   /ws/realtime                实时数据推送 (0.1s)

  [历史数据]
    GET  /api/waterpump/history      统一历史数据查询

  [配置管理]
    GET  /api/config/server          服务端运行配置 (只读)

  [阈值管理]
    GET  /api/thresholds             获取所有阈值配置
    POST /api/thresholds             更新阈值配置
    POST /api/thresholds/reset       重置为默认值

  [报警管理]
    GET  /api/alarms/records         查询报警记录
    GET  /api/alarms/count           报警数量统计
    GET  /api/alarms/thresholds      获取报警阈值

===================================================================
  总计: 11 个 HTTP 端点 + 1 个 WebSocket 端点
===================================================================
"""
    print(summary)


if __name__ == "__main__":
    print_api_summary()
