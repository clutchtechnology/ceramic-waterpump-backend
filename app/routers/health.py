# ============================================================
# 文件说明: health.py - 健康检查和系统状态 API
# ============================================================

import logging
from datetime import datetime
from fastapi import APIRouter

from app.core.influxdb import get_influx_client
from app.services.polling_service import is_polling_running, get_polling_stats
from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["健康检查"])
settings = get_settings()


@router.get("/health", summary="系统健康检查")
async def health():
    """
    系统健康状态检查
    
    返回：
    - mode: mock | real (运行模式)
    - influx_ok: InfluxDB 连接状态
    - polling_enabled: 轮询服务是否启用
    - polling_running: 轮询服务是否正在运行
    - timestamp: 当前服务时间
    """
    mode = "mock" if settings.use_mock_data else "real"
    
    # Mock模式下，跳过真实组件检查
    if settings.use_mock_data:
        return {
            "success": True,
            "status": "ok",
            "mode": mode,
            "components": {
                "influxdb": "skipped (mock mode)",
                "plc": "skipped (mock mode)",
                "polling_enabled": False,
                "polling_running": False
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    # 真实模式检查
    influx_status = "unknown"
    try:
        client = get_influx_client()
        health_result = client.health()
        influx_status = "ok" if health_result.status == "pass" else "error"
    except Exception as e:
        influx_status = "error"
        logger.warning(f"InfluxDB health check failed: {e}")

    polling_running = is_polling_running()
    
    return {
        "success": True,
        "status": "ok" if influx_status == "ok" and polling_running else "degraded",
        "mode": mode,
        "components": {
            "influxdb": influx_status,
            "polling_enabled": settings.enable_polling,
            "polling_running": polling_running
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/status", summary="系统轮询状态")
async def get_system_status():
    """
    获取系统轮询状态
    
    返回：
    - polling_running: 轮询服务是否运行
    - polling_stats: 轮询统计信息
    - resource_stats: 系统资源统计
    """
    try:
        # Mock模式下，跳过轮询统计
        if settings.use_mock_data:
            return {
                "success": True,
                "mode": "mock",
                "polling_running": False,
                "polling_stats": {
                    "message": "Polling disabled in mock mode"
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 真实模式
        polling_running = is_polling_running()
        stats = get_polling_stats() if polling_running else {}
        
        return {
            "success": True,
            "mode": "real",
            "polling_running": polling_running,
            "polling_stats": stats,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_system_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
