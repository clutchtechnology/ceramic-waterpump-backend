# ============================================================
# 文件说明: alarms.py - 报警管理 API
# ============================================================

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Query

from app.core.alarm_store import query_alarms, get_alarm_count

logger = logging.getLogger(__name__)
router = APIRouter(tags=["报警管理"])


@router.get("/alarms", summary="查询报警日志")
async def get_alarms(
    start: Optional[str] = Query(None, description="开始时间 ISO格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO格式"),
    device_id: Optional[str] = Query(None, description="设备ID筛选"),
    level: Optional[str] = Query(None, description="报警级别 warning/alarm"),
    limit: int = Query(100, description="最大返回条数")
):
    """
    查询报警日志
    
    返回：报警记录列表
    """
    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
        
        alarms = query_alarms(
            start_time=start_time,
            end_time=end_time,
            device_id=device_id,
            level=level,
            limit=limit
        )
        
        return {
            "success": True,
            "data": alarms,
            "count": len(alarms),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error in get_alarms: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/alarms/count", summary="报警统计数量")
async def get_alarms_count(hours: int = Query(24, description="统计时间范围(小时)")):
    """
    获取报警统计数量
    
    返回：
    - warning: 警告数量
    - alarm: 报警数量
    - total: 总数
    """
    try:
        counts = get_alarm_count(hours=hours)
        return {
            "success": True,
            "data": counts,
            "hours": hours,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error in get_alarms_count: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "data": {"warning": 0, "alarm": 0, "total": 0},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
