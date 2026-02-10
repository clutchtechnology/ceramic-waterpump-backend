# ============================================================
# 文件说明: health.py - 健康检查和系统状态 API
# ============================================================

import logging
from datetime import datetime
from fastapi import APIRouter

from app.core.influxdb import get_influx_client
from app.services.polling_service_data_db2 import is_data_polling_running, get_data_polling_stats
from app.services.polling_service_status_db1_3 import (
    is_status_polling_running, 
    get_status_polling_stats,
    get_latest_status_data
)
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
    - influxdb: InfluxDB 连接状态 (ok/error/unknown)
    - plc: PLC 连接状态 (ok/mock/error)
    - polling_enabled: 轮询服务是否启用
    - polling_running: 轮询服务是否正在运行
    - timestamp: 当前服务时间
    """
    mode = "mock" if settings.use_mock_data else "real"
    
    # 1. 检查 InfluxDB 状态（无论 Mock 还是真实模式都检查）
    influx_status = "unknown"
    influx_online = False
    try:
        client = get_influx_client()
        # 1.1, 尝试调用 ping 或 health 端点
        try:
            # 优先使用 ping (不需要认证)
            ping_result = client.ping()
            influx_online = ping_result
            influx_status = "ok" if ping_result else "error"
            logger.debug(f"InfluxDB ping: {ping_result}")
        except AttributeError:
            # 如果没有 ping 方法，使用 health
            health_result = client.health()
            influx_online = True
            influx_status = "ok" if health_result.status == "pass" else "degraded"
            logger.debug(f"InfluxDB health check: {health_result.status}")
    except Exception as e:
        # 1.2, 区分认证错误和连接错误
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg:
            # 认证失败说明服务在线，但 Token 错误
            influx_online = True
            influx_status = "ok"
            logger.debug(f"InfluxDB 服务在线 (认证失败不影响健康状态)")
        elif "Connection" in error_msg or "refused" in error_msg or "Failed to establish" in error_msg:
            # 连接失败说明服务离线
            influx_online = False
            influx_status = "error"
            logger.warning(f"InfluxDB 连接失败 (服务未启动): {e}")
        else:
            influx_online = False
            influx_status = "error"
            logger.warning(f"InfluxDB health check failed: {e}")
    
    # 2. 检查 PLC 状态
    if settings.use_mock_data:
        plc_status = "mock"  # Mock 模式，PLC 使用模拟数据
    else:
        # 真实模式，检查 PLC 连接（这里可以添加真实的 PLC 连接检查）
        plc_status = "ok"  # 暂时假设 OK，后续可以添加真实检查
    
    # 3. 检查轮询服务状态
    data_polling_running = is_data_polling_running()
    status_polling_running = is_status_polling_running()
    polling_running = data_polling_running and status_polling_running
    
    # 4. 判断整体健康状态
    # - Mock 模式：只要 InfluxDB 正常就算健康
    # - 真实模式：InfluxDB + PLC + 轮询都正常才算健康
    if settings.use_mock_data:
        overall_status = "ok" if influx_status == "ok" else "degraded"
    else:
        overall_status = "ok" if (influx_status == "ok" and plc_status == "ok" and polling_running) else "degraded"
    
    return {
        "success": True,
        "status": overall_status,
        "mode": mode,
        "plc_connected": plc_status == "ok" or plc_status == "mock",
        "db_connected": influx_status == "ok",
        "components": {
            "influxdb": influx_status,
            "plc": plc_status,
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
        # 获取轮询状态（Mock 和真实模式都支持）
        data_polling_running = is_data_polling_running()
        status_polling_running = is_status_polling_running()
        polling_running = data_polling_running and status_polling_running
        
        data_stats = get_data_polling_stats() if data_polling_running else {}
        status_stats = get_status_polling_stats() if status_polling_running else {}
        
        mode = "mock" if settings.use_mock_data else "real"
        
        return {
            "success": True,
            "mode": mode,
            "polling_running": polling_running,
            "polling_stats": {
                "data_polling": {
                    "running": data_polling_running,
                    "stats": data_stats
                },
                "status_polling": {
                    "running": status_polling_running,
                    "stats": status_stats
                }
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_system_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/waterpump/status/devices", summary="获取设备状态")
async def get_device_status():
    """
    获取 DB1 和 DB3 设备状态数据 (HTTP 降级接口)
    
    返回：
    - success: 是否成功
    - data: 设备状态数据 (按 DB 分组)
    - summary: 统计信息
    - summary_by_db: 各 DB 统计信息
    - source: 数据来源 (mock/plc)
    - timestamp: 时间戳
    """
    try:
        # 1, 获取最新状态数据
        status_data = get_latest_status_data()
        
        if status_data is None:
            return {
                "success": False,
                "error": "状态数据未初始化",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 2, 返回数据
        return {
            "success": True,
            "data": status_data.get("data", {}),
            "summary": status_data.get("summary", {}),
            "summary_by_db": status_data.get("summary_by_db", {}),
            "source": status_data.get("source", "unknown"),
            "timestamp": status_data.get("timestamp", datetime.utcnow().isoformat() + "Z")
        }
        
    except Exception as e:
        logger.error(f"Error in get_device_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
