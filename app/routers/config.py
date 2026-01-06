# ============================================================
# 文件说明: config.py - 配置管理 API
# ============================================================

import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter

from app.core.threshold_store import load_thresholds, save_thresholds

logger = logging.getLogger(__name__)
router = APIRouter(tags=["配置管理"])


@router.get("/config/thresholds", summary="获取阈值配置")
async def get_thresholds():
    """
    获取当前阈值配置
    
    返回：
    - current: 电流阈值 (6泵)
    - power: 功率阈值 (6泵)
    - pressure: 压力阈值 (高低)
    - vibration: 振动阈值 (6泵)
    """
    try:
        config = load_thresholds()
        return {
            "success": True,
            "data": config,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error in get_thresholds: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/config/thresholds", summary="更新阈值配置")
async def set_thresholds(config: Dict[str, Any]):
    """
    更新阈值配置 (从Flutter同步)
    
    Body参数：
    - current: 电流阈值
    - power: 功率阈值
    - pressure: 压力阈值
    - vibration: 振动阈值
    """
    try:
        existing = load_thresholds()
        
        for key in ["current", "power", "pressure", "vibration"]:
            if key in config:
                existing[key] = config[key]
        
        success = save_thresholds(existing)
        
        if success:
            return {
                "success": True,
                "message": "阈值配置已更新",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        else:
            return {
                "success": False,
                "error": "保存配置失败",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
    except Exception as e:
        logger.error(f"Error in set_thresholds: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
