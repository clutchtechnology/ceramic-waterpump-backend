# ============================================================
# 文件说明: history.py - 历史数据和统计 API
# ============================================================

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

from app.core.influxdb import query_data
from app.services.mock_service import MockService
from config import get_settings
from .utils import parse_interval

logger = logging.getLogger(__name__)
router = APIRouter(tags=["历史数据"])
settings = get_settings()


@router.get("/history", summary="历史数据查询")
async def get_history_data(
    pump_id: Optional[int] = Query(None, description="水泵编号 (1-6)，None表示查询压力表"),
    parameter: str = Query(..., description="参数名 (voltage/current/power/pressure)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    """
    查询历史数据（支持聚合）
    
    参数：
    - pump_id: 水泵编号 (1-6)，不传则查询压力表
    - parameter: 参数名 (voltage, current, power, pressure)
    - start: 开始时间 (ISO 8601格式)
    - end: 结束时间 (ISO 8601格式)
    - interval: 聚合间隔 (1m, 5m, 1h 等)
    """
    # 验证参数
    if pump_id is not None and (pump_id < 1 or pump_id > 6):
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")
    
    if parameter not in ["voltage", "current", "power", "pressure"]:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    
    # 处理时间范围
    if not end:
        end_dt = datetime.utcnow()
    else:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end time format")
    
    if not start:
        start_dt = end_dt - timedelta(hours=1)
    else:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start time format")
    
    start_iso = start_dt.isoformat() + "Z"
    stop_iso = end_dt.isoformat() + "Z"
    device_id = f"pump_{pump_id}" if pump_id is not None else "pressure"
    
    try:
        # Mock模式
        if settings.use_mock_data:
            interval_seconds = parse_interval(interval)
            data = MockService.generate_history_data(
                pump_id=pump_id,
                parameter=parameter,
                start_time=start_dt,
                end_time=end_dt,
                interval_seconds=interval_seconds
            )
            return {
                "success": True,
                "query": {
                    "pump_id": pump_id,
                    "device_id": device_id,
                    "parameter": parameter,
                    "start": start_iso,
                    "end": stop_iso,
                    "interval": interval
                },
                "data": data
            }
        
        # 真实模式：查询InfluxDB
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id
        )
        
        # 提取指定参数
        history_list = []
        for record in raw_data:
            if record.get("field") == parameter:
                value = record.get("value", 0)
                history_list.append({
                    "timestamp": record.get("time"),
                    "value": round(value, 1) if isinstance(value, (int, float)) else value
                })
        
        return {
            "success": True,
            "query": {
                "pump_id": pump_id,
                "device_id": device_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso,
                "interval": interval
            },
            "data": history_list
        }
        
    except Exception as e:
        logger.error(f"Error in get_history_data: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "query": {
                "pump_id": pump_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso,
                "interval": interval
            }
        }


@router.get("/statistics", summary="统计数据查询")
async def get_statistics(
    pump_id: Optional[int] = Query(None, description="水泵编号 (1-6)"),
    parameter: str = Query(..., description="参数名 (voltage/current/power/pressure)"),
    start: Optional[str] = Query(None, description="开始时间"),
    end: Optional[str] = Query(None, description="结束时间")
):
    """
    查询统计数据 (最大/最小/平均)
    """
    # 验证参数
    if pump_id is not None and (pump_id < 1 or pump_id > 6):
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")
    
    if parameter not in ["voltage", "current", "power", "pressure"]:
        raise HTTPException(status_code=400, detail="Invalid parameter")
    
    # 处理时间范围
    if not end:
        end_dt = datetime.utcnow()
    else:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end time format")
    
    if not start:
        start_dt = end_dt - timedelta(hours=1)
    else:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start time format")
    
    start_iso = start_dt.isoformat() + "Z"
    stop_iso = end_dt.isoformat() + "Z"
    device_id = f"pump_{pump_id}" if pump_id is not None else "pressure"
    
    try:
        # Mock模式
        if settings.use_mock_data:
            history = MockService.generate_history_data(
                pump_id=pump_id,
                parameter=parameter,
                start_time=start_dt,
                end_time=end_dt,
                interval_seconds=60
            )
            
            if not history:
                return {"success": False, "error": "No data available"}
            
            values = [item["value"] for item in history]
            return {
                "success": True,
                "query": {
                    "pump_id": pump_id,
                    "device_id": device_id,
                    "parameter": parameter,
                    "start": start_iso,
                    "end": stop_iso
                },
                "statistics": {
                    "max": max(values),
                    "min": min(values),
                    "avg": sum(values) / len(values),
                    "count": len(values)
                }
            }
        
        # 真实模式
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval="1m",
            device_id=device_id
        )
        
        values = [
            record.get("value", 0)
            for record in raw_data
            if record.get("field") == parameter
        ]
        
        if not values:
            return {
                "success": False,
                "error": "No data found",
                "query": {
                    "pump_id": pump_id,
                    "parameter": parameter,
                    "start": start_iso,
                    "end": stop_iso
                }
            }
        
        return {
            "success": True,
            "query": {
                "pump_id": pump_id,
                "device_id": device_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso
            },
            "statistics": {
                "max": max(values),
                "min": min(values),
                "avg": sum(values) / len(values),
                "count": len(values)
            }
        }
        
    except Exception as e:
        logger.error(f"Error in get_statistics: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "query": {
                "pump_id": pump_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso
            }
        }
