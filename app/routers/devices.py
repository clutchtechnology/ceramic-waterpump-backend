# ============================================================
# 文件说明: devices.py - 设备状态 API
# ============================================================

import logging
from datetime import datetime
from fastapi import APIRouter

from app.plc.plc_manager import get_plc_manager
from app.plc.parser_status_waterpump import (
    parse_status_waterpump_db,
    parse_status_waterpump_master_db,
)
from app.services.polling_service import get_latest_status
from tests.mock.mock_data_generator import MockDataGenerator
from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["设备状态"])
settings = get_settings()
_mock_generator = MockDataGenerator()


@router.get("/status/devices", summary="设备通信状态")
async def get_device_status():
    """
    获取所有设备的通信状态 (DB1 + DB3)
    
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
        cached = get_latest_status()
        if cached.get("data"):
            return {
                "success": True,
                **cached
            }

        # Mock模式: 生成 DB1/DB3 并解析
        if settings.use_mock_data:
            db1_bytes = _mock_generator.generate_db1_status()
            db3_bytes = _mock_generator.generate_db3_status()
            db1_data = parse_status_waterpump_master_db(db1_bytes, only_enabled=True)
            db3_data = parse_status_waterpump_db(db3_bytes, only_enabled=True)
            return {
                "success": True,
                "data": {
                    "db1": db1_data["devices"],
                    "db3": db3_data["devices"],
                },
                "summary_by_db": {
                    "db1": db1_data["summary"],
                    "db3": db3_data["summary"],
                },
                "source": "mock",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 真实PLC模式
        plc = get_plc_manager()
        success1, db1_bytes, err1 = plc.read_db(1, 0, 80)
        success3, db3_bytes, err3 = plc.read_db(3, 0, 80)

        if not success1 and not success3:
            return {
                "success": False,
                "error": f"读取DB1失败: {err1}; 读取DB3失败: {err3}",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        data = {}
        summary_by_db = {}

        if success1:
            db1_data = parse_status_waterpump_master_db(db1_bytes, only_enabled=True)
            data["db1"] = db1_data["devices"]
            summary_by_db["db1"] = db1_data["summary"]

        if success3:
            db3_data = parse_status_waterpump_db(db3_bytes, only_enabled=True)
            data["db3"] = db3_data["devices"]
            summary_by_db["db3"] = db3_data["summary"]

        return {
            "success": True,
            "data": data,
            "summary_by_db": summary_by_db,
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
