# ============================================================
# 文件说明: alarms.py - 报警管理路由
# ============================================================
# 接口列表:
# 1. GET  /api/alarms/records     - 查询历史报警记录
# 2. GET  /api/alarms/count       - 统计报警数量
# 3. GET  /api/alarms/thresholds  - 获取报警阈值配置
# ============================================================
from fastapi import APIRouter, Query
from datetime import datetime
from typing import Optional
import logging

from app.core.alarm_store import query_alarms, get_alarm_count
from app.services.threshold_service import get_threshold_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alarms", tags=["报警"])


# ------------------------------------------------------------
# 1. GET /api/alarms/records - 查询历史报警记录
# ------------------------------------------------------------
@router.get("/records")
async def get_alarm_records(
    start: Optional[str] = Query(None, description="开始时间 ISO8601"),
    end: Optional[str] = Query(None, description="结束时间 ISO8601"),
    level: Optional[str] = Query(None, description="报警级别: warning | alarm"),
    param_prefix: Optional[str] = Query(None, description="参数名前缀, 如 pump_current, vib_speed"),
    limit: int = Query(200, ge=1, le=1000, description="返回条数上限"),
):
    """查询历史报警记录, 默认返回最近24小时"""
    try:
        if level and level not in {"warning", "alarm"}:
            return {"success": False, "error": "level 参数仅支持 warning 或 alarm"}

        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if start:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if end:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

        if start_dt and end_dt and start_dt > end_dt:
            return {"success": False, "error": "start 不能晚于 end"}

        records = query_alarms(
            start_time=start_dt,
            end_time=end_dt,
            level=level,
            param_prefix=param_prefix,
            limit=limit,
        )
        return {"success": True, "data": {"records": records, "count": len(records)}}
    except Exception as e:
        logger.error("[Alarm] 查询报警记录失败: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------
# 2. GET /api/alarms/count - 统计报警数量
# ------------------------------------------------------------
@router.get("/count")
async def get_count(
    hours: int = Query(24, ge=1, le=168, description="统计时长(小时), 最长7天"),
):
    """统计指定时长内的各级别报警数量"""
    try:
        counts = get_alarm_count(hours=hours)
        return {"success": True, "data": counts}
    except Exception as e:
        logger.error("[Alarm] 统计报警数量失败: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------
# 3. GET /api/alarms/thresholds - 获取报警阈值配置
# ------------------------------------------------------------
@router.get("/thresholds")
async def get_thresholds():
    """获取全量阈值配置"""
    try:
        svc = get_threshold_service()
        data = svc.get_all_thresholds()
        return {"success": True, "data": data}
    except Exception as e:
        logger.error("[Alarm] 获取阈值配置失败: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}
