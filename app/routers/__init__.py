# ============================================================
# 文件说明: __init__.py - 路由模块入口
# ============================================================
"""
路由模块 - 按业务功能拆分

文件结构:
    ├── api.py        # 路由汇总 + api_router 导出
    ├── utils.py      # 公共工具函数
    ├── health.py     # 健康检查 API
    ├── realtime.py   # 实时数据 API
    ├── history.py    # 历史数据 API
    ├── config.py     # 配置管理 API
    ├── alarms.py     # 报警管理 API
    └── devices.py    # 设备状态 API

使用方式:
    from app.routers import api_router
    app.include_router(api_router, prefix="/api")
"""

from .api import api_router

__all__ = ["api_router"]
