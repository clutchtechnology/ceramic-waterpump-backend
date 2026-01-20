# ============================================================
# 文件说明: history.py - 历史数据 API (按设备类型拆分)
# ============================================================

import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException

from app.core.influxdb import query_data
from app.core.alarm_store import query_alarms
from app.services.mock_service import MockService
from config import get_settings
from .utils import parse_interval

logger = logging.getLogger(__name__)
router = APIRouter(tags=["历史数据"])
settings = get_settings()


def _parse_time_range(start: Optional[str], end: Optional[str], default_hours: int = 1):
    if not end:
        end_dt = datetime.utcnow()
    else:
        try:
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end time format")

    if not start:
        start_dt = end_dt - timedelta(hours=default_hours)
    else:
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start time format")

    return start_dt, end_dt, start_dt.isoformat() + "Z", end_dt.isoformat() + "Z"


def _mock_series(start_dt: datetime, end_dt: datetime, interval_seconds: int, base: float, jitter: float) -> List[Dict[str, Any]]:
    data = []
    current = start_dt
    while current <= end_dt:
        value = base + random.uniform(-jitter, jitter)
        data.append({
            "timestamp": current.isoformat(),
            "value": round(value, 3)
        })
        current += timedelta(seconds=interval_seconds)
    return data


@router.get("/history/press", summary="压力历史数据")
async def get_history_pressure(
    parameter: str = Query("pressure", description="参数名 (pressure/pressure_kpa)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    if parameter not in ["pressure", "pressure_kpa"]:
        raise HTTPException(status_code=400, detail="Invalid parameter")

    start_dt, end_dt, start_iso, stop_iso = _parse_time_range(start, end)
    device_id = "pressure"

    try:
        if settings.use_mock_data:
            interval_seconds = parse_interval(interval)
            base = 0.6 if parameter == "pressure" else 600.0
            jitter = 0.1 if parameter == "pressure" else 80.0
            data = _mock_series(start_dt, end_dt, interval_seconds, base, jitter)
            return {
                "success": True,
                "query": {
                    "device_id": device_id,
                    "parameter": parameter,
                    "start": start_iso,
                    "end": stop_iso,
                    "interval": interval
                },
                "data": data
            }

        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags={"module_type": "PressureSensor"}
        )

        history_list = [
            {
                "timestamp": record.get("time"),
                "value": round(record.get("value", 0), 3)
            }
            for record in raw_data
            if record.get("field") == parameter
        ]

        return {
            "success": True,
            "query": {
                "device_id": device_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso,
                "interval": interval
            },
            "data": history_list
        }
    except Exception as e:
        logger.error(f"Error in get_history_pressure: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "query": {
                "device_id": device_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso,
                "interval": interval
            }
        }


@router.get("/history/elec", summary="电表历史数据")
async def get_history_elec(
    pump_id: int = Query(..., description="水泵编号 (1-6)"),
    parameter: str = Query("power", description="参数名 (voltage/current/power/energy/ImpEp/Pt/Ua_0/I_0/Pa/Pb/Pc)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    if pump_id < 1 or pump_id > 6:
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")

    allowed = {"voltage", "current", "power", "energy", "ImpEp", "Pt", "Ua_0", "I_0", "Pa", "Pb", "Pc"}
    if parameter not in allowed:
        raise HTTPException(status_code=400, detail="Invalid parameter")

    start_dt, end_dt, start_iso, stop_iso = _parse_time_range(start, end)
    device_id = f"pump_{pump_id}"

    try:
        if settings.use_mock_data:
            interval_seconds = parse_interval(interval)
            data = MockService.generate_history_data(
                pump_id=pump_id,
                parameter="power" if parameter in {"power", "Pt"} else "voltage",
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

        field = "ImpEp" if parameter == "energy" else parameter
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags={"module_type": "ElectricityMeter"}
        )

        history_list = [
            {
                "timestamp": record.get("time"),
                "value": round(record.get("value", 0), 3)
            }
            for record in raw_data
            if record.get("field") == field
        ]

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
        logger.error(f"Error in get_history_elec: {e}", exc_info=True)
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


@router.get("/history/vibration", summary="振动历史数据")
async def get_history_vibration(
    pump_id: int = Query(..., description="水泵编号 (1-6)"),
    parameter: str = Query("VX", description="参数名 (VX/VY/VZ/TEMP/HZX/HZY/HZZ/CFX/KX/VRMSX/CFY/KY/VRMSY/CFZ/KZ/VRMSZ/ERRX/ERRY/ERRZ)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    if pump_id < 1 or pump_id > 6:
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")

    allowed = {"VX", "VY", "VZ", "TEMP", "HZX", "HZY", "HZZ", "CFX", "KX", "VRMSX", "CFY", "KY", "VRMSY", "CFZ", "KZ", "VRMSZ", "ERRX", "ERRY", "ERRZ"}
    if parameter not in allowed:
        raise HTTPException(status_code=400, detail="Invalid parameter")

    start_dt, end_dt, start_iso, stop_iso = _parse_time_range(start, end)
    device_id = f"pump_{pump_id}"

    try:
        if settings.use_mock_data:
            interval_seconds = parse_interval(interval)
            base = 0.6 if parameter in {"VX", "VY", "VZ"} else 35.0
            jitter = 0.2 if parameter in {"VX", "VY", "VZ"} else 2.0
            data = _mock_series(start_dt, end_dt, interval_seconds, base, jitter)
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

        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags={"module_type": "VibrationSensor"}
        )

        history_list = [
            {
                "timestamp": record.get("time"),
                "value": round(record.get("value", 0), 3)
            }
            for record in raw_data
            if record.get("field") == parameter
        ]

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
        logger.error(f"Error in get_history_vibration: {e}", exc_info=True)
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


@router.get("/history/alarm", summary="报警历史数据")
async def get_history_alarm(
    start: Optional[str] = Query(None, description="开始时间 ISO格式"),
    end: Optional[str] = Query(None, description="结束时间 ISO格式"),
    device_id: Optional[str] = Query(None, description="设备ID筛选"),
    level: Optional[str] = Query(None, description="报警级别 warning/alarm"),
    limit: int = Query(100, description="最大返回条数")
):
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
        logger.error(f"Error in get_history_alarm: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
