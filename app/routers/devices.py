# ============================================================
# 文件说明: devices.py - 设备状态 API
# ============================================================

import logging
from datetime import datetime
from fastapi import APIRouter

from app.plc.plc_manager import get_plc_manager
from app.plc.parser_status_waterpump import parse_status_waterpump_db
from config import get_settings
from .utils import generate_mock_status

logger = logging.getLogger(__name__)
router = APIRouter(tags=["设备状态"])
settings = get_settings()


@router.get("/status/devices", summary="设备通信状态")
async def get_device_status():
    """
    获取所有设备的通信状态 (DB3 DataState)
    
    返回格式：
    {
        "success": true,
        "data": {
            "db3": [
                {
                    "device_id": "status_meter_1",
                    "device_name": "1号泵电表",
                    "error": false,
                    "status_code": 0,
                    "status_hex": "0000",
                    "is_normal": true
                },
                ...
            ]
        },
        "summary": {
            "total": 7,
            "normal": 7,
            "error": 0
        }
    }
    """
    try:
        # Mock模式
        if settings.use_mock_data:
            mock_data = generate_mock_status()
            return {
                "success": True,
                "data": {"db3": mock_data["devices"]},
                "summary": mock_data["summary"],
                "source": "mock",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 真实PLC模式
        plc = get_plc_manager()
        success, db3_bytes, err = plc.read_db(3, 0, 52)
        
        if not success:
            return {
                "success": False,
                "error": f"读取DB3失败: {err}",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        status_data = parse_status_waterpump_db(db3_bytes, only_enabled=True)
        
        return {
            "success": True,
            "data": {"db3": status_data["devices"]},
            "summary": status_data["summary"],
            "source": "plc",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        logger.error(f"Error in get_device_status: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
