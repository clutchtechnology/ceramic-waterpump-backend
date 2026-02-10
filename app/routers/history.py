# ============================================================
# 文件说明: history.py - 历史数据 API (统一接口)
# ============================================================
# 功能:
#   - 统一的 /api/waterpump/history 接口
#   - 参数名与 InfluxDB 字段名一致: Pt/ImpEp/I_0/I_1/I_2/Ua_0/Ua_1/Ua_2/pressure/
#                      vib_velocity_x/vib_displacement_x/vib_frequency_x 等
#   - 支持 Mock 数据和真实数据
# ============================================================

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
    
    # 振动参数 (位移 - 聚合，使用 dx 作为代表)
    "vibration_displacement": {"field": "dx", "module": "VibrationSensor", "unit": "μm"},
    
    # 三轴振动位移 (独立) - 映射到 InfluxDB 实际字段名
    "vib_displacement_x": {"field": "dx", "module": "VibrationSensor", "unit": "μm"},
    "vib_displacement_y": {"field": "dy", "module": "VibrationSensor", "unit": "μm"},
    "vib_displacement_z": {"field": "dz", "module": "VibrationSensor", "unit": "μm"},
    
    # 振动参数 (频率 - 聚合，使用 hzx 作为代表)
    "vibration_frequency": {"field": "hzx", "module": "VibrationSensor", "unit": "Hz"},
    
    # 三轴振动频率 (独立) - 映射到 InfluxDB 实际字段名
    "vib_frequency_x": {"field": "hzx", "module": "VibrationSensor", "unit": "Hz"},
    "vib_frequency_y": {"field": "hzy", "module": "VibrationSensor", "unit": "Hz"},
    "vib_frequency_z": {"field": "hzz", "module": "VibrationSensor", "unit": "Hz"},
}


# ============================================================
# 工具函数
# ============================================================

def _parse_time_range(start: Optional[str], end: Optional[str], default_hours: int = 24):
    """解析时间范围"""
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
        
        # 三轴振动位移 (X轴最大, Y轴中等, Z轴最小)
        "vib_displacement_x": (60.0, 12.0),
        "vib_displacement_y": (50.0, 10.0),
        "vib_displacement_z": (40.0, 8.0),
        
        # 三轴振动频率 (X轴最高, Y轴中等, Z轴最低)
        "vib_frequency_x": (38.0, 6.0),
        "vib_frequency_y": (35.0, 5.0),
        "vib_frequency_z": (32.0, 4.0),
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
    
    # 5. 查询数据
    try:
        if settings.use_mock_data:
            # Mock 数据模式
            interval_seconds = parse_interval(interval)
            base, jitter = _get_mock_base_value(parameter)
            data = _mock_series(start_dt, end_dt, interval_seconds, base, jitter)
            
            logger.info(f"[Mock] Generated {len(data)} points for {parameter} (pump_id={pump_id})")
            
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

        # 真实数据模式: 查询 InfluxDB
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval=interval,
            device_id=device_id,
            tags={"module_type": param_config["module"]}
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
        
        logger.info(f"[InfluxDB] Queried {len(history_list)} points for {parameter} (pump_id={pump_id})")

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
        logger.error(f"Error in get_waterpump_history: {e}", exc_info=True)
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
