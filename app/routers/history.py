# ============================================================
# 文件说明: history.py - 历史数据 API (统一接口)
# ============================================================
# 功能:
#   - 统一的 /api/waterpump/history 接口
#   - 参数名与 InfluxDB 字段名一致: Pt/ImpEp/I_0/I_1/I_2/Ua_0/Ua_1/Ua_2/pressure/
#                      vib_velocity_x/vib_displacement_x/vib_frequency_x 等
#   - 支持 Mock 数据和真实数据
# ============================================================

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException

from app.core.influxdb import query_data
from app.services.mock_service import MockService
from config import get_settings
from .utils import parse_interval

logger = logging.getLogger(__name__)
router = APIRouter(tags=["历史数据"])
settings = get_settings()

# 北京时区 (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


def _summarize_raw_records(raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """汇总 Influx 原始记录，便于排查字段/标签过滤问题。"""
    fields = set()
    module_types = set()
    device_ids = set()

    for record in raw_data:
        field = record.get("field")
        module_type = record.get("module_type")
        device_id = record.get("device_id")
        if field:
            fields.add(str(field))
        if module_type:
            module_types.add(str(module_type))
        if device_id:
            device_ids.add(str(device_id))

    return {
        "raw_count": len(raw_data),
        "fields": sorted(fields),
        "module_types": sorted(module_types),
        "device_ids": sorted(device_ids),
    }


def _log_empty_data_hint(
    *,
    parameter: str,
    pump_id: Optional[int],
    device_id: str,
    start_iso: str,
    stop_iso: str,
    interval: str,
    target_field: str,
    target_module: str,
    raw_summary: Dict[str, Any],
):
    """空数据时输出可执行的定位建议。"""

    # 场景 1: 字段不匹配（同标签下有数据，但目标字段不存在）
    if raw_summary["raw_count"] > 0 and target_field not in raw_summary["fields"]:
        logger.warning(
            "[HistoryQuery][Hint][FieldMismatch] parameter=%s pump_id=%s device_id=%s target_field=%s available_fields=%s suggestion=检查 PARAMETER_MAPPING 字段映射或写库字段名",
            parameter,
            pump_id,
            device_id,
            target_field,
            raw_summary["fields"],
        )
        return

    # 仅在 raw_count=0 时做额外探测，避免增加常规请求开销
    if raw_summary["raw_count"] != 0:
        return

    try:
        # 探测 A: 同 device_id + 时间窗口，去掉 module_type 标签过滤
        probe_device_all = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags=None,
        )
        probe_device_summary = _summarize_raw_records(probe_device_all)

        if probe_device_summary["raw_count"] > 0:
            logger.warning(
                "[HistoryQuery][Hint][TagMismatch] parameter=%s pump_id=%s device_id=%s target_module=%s available_modules=%s available_fields=%s suggestion=检查 module_type 标签值是否一致（如 ElectricityMeter/PressureSensor/VibrationSensor）",
                parameter,
                pump_id,
                device_id,
                target_module,
                probe_device_summary["module_types"],
                probe_device_summary["fields"],
            )
            return

        # 探测 B: 同时间窗口全量数据（不带 device/tag）
        probe_window_all = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=None,
            tags=None,
        )
        probe_window_summary = _summarize_raw_records(probe_window_all)

        if probe_window_summary["raw_count"] > 0:
            logger.warning(
                "[HistoryQuery][Hint][TagMismatch] parameter=%s pump_id=%s device_id=%s target_module=%s window_device_ids=%s suggestion=检查 device_id 命名是否一致（pump_x/vib_x/pressure）",
                parameter,
                pump_id,
                device_id,
                target_module,
                probe_window_summary["device_ids"],
            )
            return

        # 场景 3: 时间窗口无数据
        logger.warning(
            "[HistoryQuery][Hint][TimeWindowNoData] parameter=%s pump_id=%s device_id=%s start=%s end=%s interval=%s suggestion=扩大时间范围或检查轮询写库是否正常",
            parameter,
            pump_id,
            device_id,
            start_iso,
            stop_iso,
            interval,
        )

    except Exception as probe_error:
        logger.warning(
            "[HistoryQuery][Hint][ProbeFailed] parameter=%s pump_id=%s device_id=%s error=%s",
            parameter,
            pump_id,
            device_id,
            probe_error,
            exc_info=True,
        )


# ============================================================
# 参数映射表: 前端参数 -> InfluxDB field
# ============================================================
PARAMETER_MAPPING = {
    # 电表参数 (统一字段名, 与 InfluxDB 一致)
    "Pt": {"field": "Pt", "module": "ElectricityMeter", "unit": "kW"},
    "ImpEp": {"field": "ImpEp", "module": "ElectricityMeter", "unit": "kWh"},
    
    # 三相电流 (与 InfluxDB 字段名一致)
    "I_0": {"field": "I_0", "module": "ElectricityMeter", "unit": "A"},
    "I_1": {"field": "I_1", "module": "ElectricityMeter", "unit": "A"},
    "I_2": {"field": "I_2", "module": "ElectricityMeter", "unit": "A"},
    
    # 三相电压 (与 InfluxDB 字段名一致)
    "Ua_0": {"field": "Ua_0", "module": "ElectricityMeter", "unit": "V"},
    "Ua_1": {"field": "Ua_1", "module": "ElectricityMeter", "unit": "V"},
    "Ua_2": {"field": "Ua_2", "module": "ElectricityMeter", "unit": "V"},
    
    # 压力参数
    "pressure": {"field": "pressure", "module": "PressureSensor", "unit": "MPa"},
    
    # 振动参数 (速度 - 聚合，使用 vx 作为代表)
    "vibration_velocity": {"field": "vx", "module": "VibrationSensor", "unit": "mm/s"},
    
    # 三轴振动速度 (独立) - 映射到 InfluxDB 实际字段名
    "vib_velocity_x": {"field": "vx", "module": "VibrationSensor", "unit": "mm/s"},
    "vib_velocity_y": {"field": "vy", "module": "VibrationSensor", "unit": "mm/s"},
    "vib_velocity_z": {"field": "vz", "module": "VibrationSensor", "unit": "mm/s"},
    "vx": {"field": "vx", "module": "VibrationSensor", "unit": "mm/s"},
    "vy": {"field": "vy", "module": "VibrationSensor", "unit": "mm/s"},
    "vz": {"field": "vz", "module": "VibrationSensor", "unit": "mm/s"},
    
    # 振动参数 (位移 - 聚合，使用 dx 作为代表)
    "vibration_displacement": {"field": "dx", "module": "VibrationSensor", "unit": "μm"},
    
    # 三轴振动位移 (独立) - 映射到 InfluxDB 实际字段名
    "vib_displacement_x": {"field": "dx", "module": "VibrationSensor", "unit": "μm"},
    "vib_displacement_y": {"field": "dy", "module": "VibrationSensor", "unit": "μm"},
    "vib_displacement_z": {"field": "dz", "module": "VibrationSensor", "unit": "μm"},
    "dx": {"field": "dx", "module": "VibrationSensor", "unit": "μm"},
    "dy": {"field": "dy", "module": "VibrationSensor", "unit": "μm"},
    "dz": {"field": "dz", "module": "VibrationSensor", "unit": "μm"},
    
    # 振动参数 (频率 - 聚合，使用 hzx 作为代表)
    "vibration_frequency": {"field": "hzx", "module": "VibrationSensor", "unit": "Hz"},
    
    # 三轴振动频率 (独立) - 映射到 InfluxDB 实际字段名
    "vib_frequency_x": {"field": "hzx", "module": "VibrationSensor", "unit": "Hz"},
    "vib_frequency_y": {"field": "hzy", "module": "VibrationSensor", "unit": "Hz"},
    "vib_frequency_z": {"field": "hzz", "module": "VibrationSensor", "unit": "Hz"},
    "hzx": {"field": "hzx", "module": "VibrationSensor", "unit": "Hz"},
    "hzy": {"field": "hzy", "module": "VibrationSensor", "unit": "Hz"},
    "hzz": {"field": "hzz", "module": "VibrationSensor", "unit": "Hz"},
}


# ============================================================
# 工具函数
# ============================================================

def _to_utc_datetime(value: datetime) -> datetime:
    """将 datetime 统一转换为 UTC aware datetime。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_flux_rfc3339(value: datetime) -> str:
    """转换为 Flux 可直接使用的 RFC3339 UTC 时间字符串。"""
    return _to_utc_datetime(value).isoformat().replace("+00:00", "Z")


def _parse_time_range(start: Optional[str], end: Optional[str], default_hours: int = 24):
    """解析时间范围"""
    if not end:
        end_dt = datetime.now(timezone.utc)
    else:
        try:
            end_dt = _to_utc_datetime(datetime.fromisoformat(end.replace("Z", "+00:00")))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid end time format")

    if not start:
        start_dt = end_dt - timedelta(hours=default_hours)
    else:
        try:
            start_dt = _to_utc_datetime(datetime.fromisoformat(start.replace("Z", "+00:00")))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid start time format")

    return start_dt, end_dt, _to_flux_rfc3339(start_dt), _to_flux_rfc3339(end_dt)


def _mock_series(start_dt: datetime, end_dt: datetime, interval_seconds: int, base: float, jitter: float, use_beijing_time: bool = False) -> List[Dict[str, Any]]:
    """生成模拟时间序列数据"""
    data = []
    current = start_dt
    while current <= end_dt:
        value = base + random.uniform(-jitter, jitter)
        
        # 根据参数决定返回 UTC 还是北京时间
        if use_beijing_time:
            timestamp = current.astimezone(BEIJING_TZ).isoformat()
        else:
            timestamp = current.isoformat()
        
        data.append({
            "timestamp": timestamp,
            "value": round(value, 3)
        })
        current += timedelta(seconds=interval_seconds)
    return data


def _get_mock_base_value(parameter: str) -> tuple[float, float]:
    """获取模拟数据的基准值和抖动范围"""
    mock_config = {
        # 聚合参数
        "power": (35.0, 5.0),
        "energy": (100.0, 10.0),
        "current": (50.0, 8.0),
        "voltage": (380.0, 10.0),
        "pressure": (0.6, 0.1),
        "vibration_velocity": (0.8, 0.2),
        "vibration_displacement": (50.0, 10.0),
        "vibration_frequency": (35.0, 5.0),
        
        # 三相电流 (A相略高, B相中等, C相略低)
        "current_a": (52.0, 8.0),
        "current_b": (50.0, 8.0),
        "current_c": (48.0, 8.0),
        
        # 三相电压 (A相略高, B相中等, C相略低)
        "voltage_a": (385.0, 10.0),
        "voltage_b": (380.0, 10.0),
        "voltage_c": (375.0, 10.0),
        
        # 三轴振动速度 (X轴最大, Y轴中等, Z轴最小)
        "vib_velocity_x": (1.0, 0.3),
        "vib_velocity_y": (0.8, 0.2),
        "vib_velocity_z": (0.6, 0.15),
        "vx": (1.0, 0.3),
        "vy": (0.8, 0.2),
        "vz": (0.6, 0.15),
        
        # 三轴振动位移 (X轴最大, Y轴中等, Z轴最小)
        "vib_displacement_x": (60.0, 12.0),
        "vib_displacement_y": (50.0, 10.0),
        "vib_displacement_z": (40.0, 8.0),
        "dx": (60.0, 12.0),
        "dy": (50.0, 10.0),
        "dz": (40.0, 8.0),
        
        # 三轴振动频率 (X轴最高, Y轴中等, Z轴最低)
        "vib_frequency_x": (38.0, 6.0),
        "vib_frequency_y": (35.0, 5.0),
        "vib_frequency_z": (32.0, 4.0),
        "hzx": (38.0, 6.0),
        "hzy": (35.0, 5.0),
        "hzz": (32.0, 4.0),
    }
    return mock_config.get(parameter, (1.0, 0.1))


# ============================================================
# 统一历史数据接口 (适配前端8宫格布局)
# ============================================================

@router.get("/waterpump/history", summary="统一历史数据查询")
async def get_waterpump_history(
    parameter: str = Query(..., description="参数名 (支持聚合参数和三相/三轴参数)"),
    pump_id: Optional[int] = Query(None, description="水泵编号 (1-6)，压力查询时不需要"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: Optional[str] = Query(None, description="聚合间隔 (5s/1m/5m/1h/1d)，不传则自动计算")
):
    """
    统一的历史数据查询接口
    
    支持的参数类型:
    
    聚合参数:
    - power: 功率 (kW)
    - energy: 能耗 (kWh)
    - current: 电流平均值 (A)
    - voltage: 电压平均值 (V)
    - pressure: 压力 (MPa) - 不需要 pump_id
    - vibration_velocity: 振动速度 (mm/s)
    - vibration_displacement: 振动位移 (μm)
    - vibration_frequency: 振动频率 (Hz)
    
    三相电参数:
    - current_a/current_b/current_c: 三相电流 (A)
    - voltage_a/voltage_b/voltage_c: 三相电压 (V)
    
    三轴振动参数:
    - vib_velocity_x/vib_velocity_y/vib_velocity_z: 三轴振动速度 (mm/s)
    - vib_displacement_x/vib_displacement_y/vib_displacement_z: 三轴振动位移 (μm)
    - vib_frequency_x/vib_frequency_y/vib_frequency_z: 三轴振动频率 (Hz)
    
    示例:
    - GET /api/waterpump/history?parameter=power&pump_id=1&start=2024-01-01T00:00:00Z&end=2024-01-02T00:00:00Z
    - GET /api/waterpump/history?parameter=current_a&pump_id=1&start=2024-01-01T00:00:00Z&end=2024-01-02T00:00:00Z
    - GET /api/waterpump/history?parameter=vib_velocity_x&pump_id=1&start=2024-01-01T00:00:00Z&end=2024-01-02T00:00:00Z
    """
    
    # 1. 验证参数
    if parameter not in PARAMETER_MAPPING:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid parameter. Allowed: {', '.join(PARAMETER_MAPPING.keys())}"
        )
    
    param_config = PARAMETER_MAPPING[parameter]
    
    # 2. 验证 pump_id (压力查询不需要)
    if parameter == "pressure":
        device_id = "pressure"
        if pump_id is not None:
            logger.warning(f"pump_id={pump_id} ignored for pressure query")
    else:
        if pump_id is None:
            raise HTTPException(status_code=400, detail="pump_id is required for non-pressure queries")
        if pump_id < 1 or pump_id > 6:
            raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")
        # 振动参数使用 vib_X 作为 device_id, 电气参数使用 pump_X
        if param_config["module"] == "VibrationSensor":
            device_id = f"vib_{pump_id}"
        else:
            device_id = f"pump_{pump_id}"

    # 3. 解析时间范围
    start_dt, end_dt, start_iso, stop_iso = _parse_time_range(start, end, default_hours=24)
    
    # 4. 自动计算聚合间隔 (如果未指定)
    if interval is None:
        duration_seconds = (end_dt - start_dt).total_seconds()
        target_points = 50
        interval_seconds = max(5, int(duration_seconds / target_points))
        
        # 映射到标准间隔
        if interval_seconds < 60:
            interval = f"{interval_seconds}s"
        elif interval_seconds < 3600:
            interval = f"{interval_seconds // 60}m"
        elif interval_seconds < 86400:
            interval = f"{interval_seconds // 3600}h"
        else:
            interval = f"{interval_seconds // 86400}d"
        
        logger.info(f"Auto-calculated interval: {interval} (duration: {duration_seconds}s, target: {target_points} points)")
    
    logger.info(
        "[HistoryQuery] request parameter=%s pump_id=%s device_id=%s field=%s module=%s start=%s end=%s interval=%s mock=%s",
        parameter,
        pump_id,
        device_id,
        param_config["field"],
        param_config["module"],
        start_iso,
        stop_iso,
        interval,
        settings.use_mock_data,
    )

    # 5. 查询数据
    try:
        if settings.use_mock_data:
            # Mock 数据模式
            interval_seconds = parse_interval(interval)
            base, jitter = _get_mock_base_value(parameter)
            data = _mock_series(start_dt, end_dt, interval_seconds, base, jitter)
            
            logger.info(
                "[HistoryQuery][Mock] generated_points=%s parameter=%s pump_id=%s device_id=%s",
                len(data),
                parameter,
                pump_id,
                device_id,
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

        # 真实数据模式: 查询 InfluxDB (在线程中执行，避免阻塞事件循环)
        raw_data = await asyncio.to_thread(
            query_data,
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags={"module_type": param_config["module"]}
        )

        raw_summary = _summarize_raw_records(raw_data)
        logger.info(
            "[HistoryQuery][InfluxRaw] parameter=%s pump_id=%s device_id=%s raw_count=%s fields=%s module_types=%s device_ids=%s",
            parameter,
            pump_id,
            device_id,
            raw_summary["raw_count"],
            raw_summary["fields"],
            raw_summary["module_types"],
            raw_summary["device_ids"],
        )

        # 过滤指定字段的数据
        history_list = [
            {
                "timestamp": record.get("time"),
                "value": round(record.get("value", 0), 3)
            }
            for record in raw_data
            if record.get("field") == param_config["field"]
        ]
        
        logger.info(
            "[HistoryQuery][Filtered] parameter=%s pump_id=%s device_id=%s target_field=%s points=%s",
            parameter,
            pump_id,
            device_id,
            param_config["field"],
            len(history_list),
        )

        if len(history_list) == 0:
            await asyncio.to_thread(
                _log_empty_data_hint,
                parameter=parameter,
                pump_id=pump_id,
                device_id=device_id,
                start_iso=start_iso,
                stop_iso=stop_iso,
                interval=interval,
                target_field=param_config["field"],
                target_module=param_config["module"],
                raw_summary=raw_summary,
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
            "data": history_list
        }
    
    except Exception as e:
        logger.error(
            "[HistoryQuery][Error] parameter=%s pump_id=%s device_id=%s field=%s module=%s start=%s end=%s interval=%s error=%s",
            parameter,
            pump_id,
            device_id,
            param_config.get("field"),
            param_config.get("module"),
            start_iso,
            stop_iso,
            interval,
            e,
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "query": {
                "pump_id": pump_id,
                "device_id": device_id,
                "parameter": parameter,
                "start": start_iso,
                "end": stop_iso,
                "interval": interval
            },
            "data": []
        }


# ============================================================
# 兼容旧接口 (保留以防前端还在使用)
# ============================================================

@router.get("/history/press", summary="[已废弃] 压力历史数据", deprecated=True)
async def get_history_pressure(
    parameter: str = Query("pressure", description="参数名 (pressure/pressure_kpa)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    """已废弃，请使用 /api/waterpump/history?parameter=pressure"""
    return await get_waterpump_history(
        parameter="pressure",
        pump_id=None,
        start=start,
        end=end,
        interval=interval
    )


@router.get("/history/elec", summary="[已废弃] 电表历史数据", deprecated=True)
async def get_history_elec(
    pump_id: int = Query(..., description="水泵编号 (1-6)"),
    parameter: str = Query("power", description="参数名 (voltage/current/power/energy)"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    """已废弃，请使用 /api/waterpump/history?parameter=power&pump_id=1"""
    return await get_waterpump_history(
        parameter=parameter,
        pump_id=pump_id,
        start=start,
        end=end,
        interval=interval
    )


@router.get("/history/vibration", summary="[已废弃] 振动历史数据", deprecated=True)
async def get_history_vibration(
    pump_id: int = Query(..., description="水泵编号 (1-6)"),
    parameter: str = Query("VRMSX", description="参数名"),
    start: Optional[str] = Query(None, description="开始时间 (ISO 8601)"),
    end: Optional[str] = Query(None, description="结束时间 (ISO 8601)"),
    interval: str = Query("5m", description="聚合间隔 (1m/5m/1h)")
):
    """已废弃，请使用 /api/waterpump/history?parameter=vibration_velocity&pump_id=1"""
    return await get_waterpump_history(
        parameter="vibration_velocity",
        pump_id=pump_id,
        start=start,
        end=end,
        interval=interval
    )
