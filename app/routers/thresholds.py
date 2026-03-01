"""
阈值管理 API 路由
提供阈值配置的增删改查接口
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

from app.services.threshold_service import get_threshold_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/thresholds", tags=["阈值管理"])


class ThresholdUpdateRequest(BaseModel):
    """阈值更新请求模型"""
    current: Optional[Dict[str, Dict[str, float]]] = None
    voltage: Optional[Dict[str, Dict[str, float]]] = None
    pressure: Optional[Dict[str, float]] = None
    speed: Optional[Dict[str, Dict[str, float]]] = None
    displacement: Optional[Dict[str, Dict[str, float]]] = None
    frequency: Optional[Dict[str, Dict[str, float]]] = None


@router.get("")
async def get_thresholds():
    """
    获取所有阈值配置
    
    Returns:
        {
            "success": true,
            "data": {
                "current": {...},
                "voltage": {...},
                "pressure": {...},
                "speed": {...},
                "displacement": {...},
                "frequency": {...}
            }
        }
    """
    try:
        threshold_service = get_threshold_service()
        thresholds = threshold_service.get_all_thresholds()
        
        return {
            "success": True,
            "data": thresholds
        }
    except Exception as e:
        logger.error(f"获取阈值配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{param_type}")
async def get_threshold_by_type(param_type: str, pump_id: Optional[int] = None):
    """
    获取指定类型的阈值配置
    
    Args:
        param_type: 参数类型 (current, voltage, pressure, speed, displacement, frequency)
        pump_id: 水泵编号 (1-6)，压力阈值不需要此参数
    
    Returns:
        {
            "success": true,
            "data": {
                "normal_max": 50.0,
                "warning_max": 80.0
            }
        }
    """
    try:
        threshold_service = get_threshold_service()
        threshold = threshold_service.get_threshold(param_type, pump_id)
        
        if threshold is None:
            raise HTTPException(status_code=404, detail="阈值配置不存在")
        
        return {
            "success": True,
            "data": threshold
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取阈值配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def update_thresholds(request: ThresholdUpdateRequest):
    """
    更新阈值配置
    
    Request Body:
        {
            "current": {
                "pump_1": {"normal_max": 50.0, "warning_max": 80.0},
                ...
            },
            "voltage": {...},
            "pressure": {"high_alarm": 1.0, "low_alarm": 0.3},
            "speed": {...},
            "displacement": {...},
            "frequency": {...}
        }
    
    Returns:
        {
            "success": true,
            "message": "阈值配置已更新"
        }
    """
    try:
        threshold_service = get_threshold_service()
        
        # 转换为字典
        new_thresholds = request.dict(exclude_none=True)
        
        # 更新配置
        success = threshold_service.update_thresholds(new_thresholds)
        
        if not success:
            raise HTTPException(status_code=400, detail="阈值配置更新失败")
        
        return {
            "success": True,
            "message": "阈值配置已更新"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新阈值配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_thresholds():
    """
    重置为默认阈值配置
    
    Returns:
        {
            "success": true,
            "message": "阈值配置已重置为默认值"
        }
    """
    try:
        threshold_service = get_threshold_service()
        success = threshold_service.reset_to_default()
        
        if not success:
            raise HTTPException(status_code=500, detail="重置阈值配置失败")
        
        return {
            "success": True,
            "message": "阈值配置已重置为默认值"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置阈值配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))



