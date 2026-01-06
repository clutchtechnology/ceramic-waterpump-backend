# ============================================================
# 文件说明: realtime.py - 实时数据查询 API
# ============================================================

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException

from app.core.influxdb import query_data
from app.services.polling_service import get_latest_data
from app.services.mock_service import MockService
from config import get_settings
from .utils import check_mock_alarms

logger = logging.getLogger(__name__)
router = APIRouter(tags=["实时数据"])
settings = get_settings()


@router.get("/realtime/batch", summary="批量实时数据")
async def get_realtime_batch():
    """
    获取所有设备实时数据 (6个水泵 + 1个压力表)
    
    返回格式：
    {
        "success": true,
        "timestamp": "2025-12-24T10:00:00Z",
        "source": "mock" | "cache" | "influxdb",
        "data": {
            "pumps": [...],
            "pressure": {...}
        }
    }
    """
    try:
        # Mock模式：使用模拟数据
        if settings.use_mock_data:
            data = MockService.generate_realtime_batch()
            check_mock_alarms(data)
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        # 真实模式：优先使用内存缓存
        cached_data = get_latest_data()
        if cached_data:
            pumps = []
            pressure = None
            
            for device_id, device_data in cached_data.items():
                if device_id.startswith("pump_"):
                    pumps.append({
                        "pump_id": device_id,
                        **device_data
                    })
                elif device_id == "pressure":
                    pressure = device_data
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": {
                    "pumps": pumps,
                    "pressure": pressure
                }
            }
        
        # 缓存为空，查询InfluxDB
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start.isoformat() + "Z",
            stop_iso=end.isoformat() + "Z",
            interval="10s"
        )
        
        # 解析为设备分组
        devices_dict = {}
        for record in raw_data:
            device_id = record.get("device_id", "unknown")
            field = record.get("field", "")
            value = record.get("value", 0)
            
            if device_id not in devices_dict:
                devices_dict[device_id] = {}
            devices_dict[device_id][field] = value
        
        # 转换为前端格式
        pumps = []
        pressure = None
        for device_id, device_data in devices_dict.items():
            if device_id.startswith("pump_"):
                pumps.append({"pump_id": device_id, **device_data})
            elif device_id == "pressure":
                pressure = device_data
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": {"pumps": pumps, "pressure": pressure}
        }
        
    except Exception as e:
        logger.error(f"Error in get_realtime_batch: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/realtime/pressure", summary="压力表实时数据")
async def get_realtime_pressure():
    """
    获取压力表实时数据
    """
    try:
        if settings.use_mock_data:
            data = MockService.generate_pressure_data()
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        cached_data = get_latest_data()
        if cached_data and "pressure" in cached_data:
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": cached_data["pressure"]
            }
        
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start.isoformat() + "Z",
            stop_iso=end.isoformat() + "Z",
            interval="10s",
            device_id="pressure"
        )
        
        pressure_data = {}
        for record in raw_data:
            field = record.get("field", "")
            value = record.get("value", 0)
            pressure_data[field] = value
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": pressure_data
        }
        
    except Exception as e:
        logger.error(f"Error in get_realtime_pressure: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/realtime/{pump_id}", summary="单个水泵实时数据")
async def get_realtime_pump(pump_id: int):
    """
    获取单个水泵实时数据
    
    参数：
    - pump_id: 水泵编号 (1-6)
    """
    if pump_id < 1 or pump_id > 6:
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")
    
    device_id = f"pump_{pump_id}"
    
    try:
        if settings.use_mock_data:
            data = MockService.generate_pump_data(pump_id)
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        cached_data = get_latest_data()
        if cached_data and device_id in cached_data:
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": {"pump_id": device_id, **cached_data[device_id]}
            }
        
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start.isoformat() + "Z",
            stop_iso=end.isoformat() + "Z",
            interval="10s",
            device_id=device_id
        )
        
        device_data = {}
        for record in raw_data:
            field = record.get("field", "")
            value = record.get("value", 0)
            device_data[field] = value
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": {"pump_id": device_id, **device_data}
        }
        
    except Exception as e:
        logger.error(f"Error in get_realtime_pump: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
