from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from app.core.influxdb import query_data, get_influx_client
from app.services.polling_service import (
    get_latest_status, 
    get_latest_data, 
    is_polling_running,
    get_polling_stats
)
from app.services.resource_monitor import get_monitor_stats
from app.services.mock_service import MockService
from app.plc.plc_manager import get_plc_manager
from app.core.threshold_store import load_thresholds, save_thresholds, check_alarm, check_pressure_alarm, get_pump_threshold, get_pressure_threshold
from app.core.alarm_store import query_alarms, get_alarm_count, log_alarm
from config import get_settings

router = APIRouter()
settings = get_settings()


# ============================================================
# 辅助函数
# ============================================================
def _parse_interval(interval: str) -> int:
    """
    解析间隔字符串为秒数
    
    支持格式: 5s, 1m, 5m, 1h, 1d 等
    
    返回: 秒数
    """
    interval = interval.lower().strip()
    
    if interval.endswith('s'):
        return int(interval[:-1])
    elif interval.endswith('m'):
        return int(interval[:-1]) * 60
    elif interval.endswith('h'):
        return int(interval[:-1]) * 3600
    elif interval.endswith('d'):
        return int(interval[:-1]) * 86400
    else:
        # 默认按秒处理
        try:
            return int(interval)
        except:
            return 60


def _check_mock_alarms(data: Dict[str, Any]):
    """
    Mock模式下检测报警并记录
    在每次返回实时数据时调用
    """
    # 检测6个水泵
    pumps = data.get('pumps', [])
    for pump in pumps:
        pump_id = pump.get('id', 0)
        device_id = f"pump_{pump_id}"
        
        # 检查电流
        current = pump.get('current', 0)
        current_alarm = check_alarm(pump_id, 'current', current)
        if current_alarm:
            threshold = get_pump_threshold(pump_id, 'current')
            threshold_val = threshold['warning_max'] if current_alarm == 'alarm' else threshold['normal_max']
            log_alarm(
                device_id=device_id,
                alarm_type='current_high',
                param_name='current',
                value=current,
                threshold=threshold_val,
                level=current_alarm,
            )
        
        # 检查功率
        power = pump.get('power', 0)
        power_alarm = check_alarm(pump_id, 'power', power)
        if power_alarm:
            threshold = get_pump_threshold(pump_id, 'power')
            threshold_val = threshold['warning_max'] if power_alarm == 'alarm' else threshold['normal_max']
            log_alarm(
                device_id=device_id,
                alarm_type='power_high',
                param_name='power',
                value=power,
                threshold=threshold_val,
                level=power_alarm,
            )
    
    # 检测压力
    pressure_data = data.get('pressure', {})
    pressure = pressure_data.get('value', 0)
    pressure_alarm = check_pressure_alarm(pressure)
    
    if pressure_alarm:
        threshold = get_pressure_threshold()
        if pressure_alarm == 'alarm_high':
            log_alarm(
                device_id='pressure',
                alarm_type='pressure_high',
                param_name='pressure',
                value=pressure,
                threshold=threshold['high_alarm'],
                level='alarm',
            )
        elif pressure_alarm == 'alarm_low':
            log_alarm(
                device_id='pressure',
                alarm_type='pressure_low',
                param_name='pressure',
                value=pressure,
                threshold=threshold['low_alarm'],
                level='alarm',
            )


# ============================================================
# 1. Health Check (健康检查)
# ============================================================
@router.get("/health")
async def health():
    """
    系统健康状态检查
    
    返回：
    - mode: mock | real (运行模式)
    - influx_ok: InfluxDB 连接状态
    - polling_enabled: 轮询服务是否启用
    - polling_running: 轮询服务是否正在运行
    - timestamp: 当前服务时间
    """
    mode = "mock" if settings.use_mock_data else "real"
    
    # Mock模式下，跳过真实组件检查
    if settings.use_mock_data:
        return {
            "success": True,
            "status": "ok",
            "mode": mode,
            "components": {
                "influxdb": "skipped (mock mode)",
                "plc": "skipped (mock mode)",
                "polling_enabled": False,
                "polling_running": False
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    # 真实模式检查
    influx_status = "unknown"
    try:
        client = get_influx_client()
        health_result = client.health()
        influx_status = "ok" if health_result.status == "pass" else "error"
    except Exception as e:
        influx_status = "error"
        print(f"InfluxDB health check failed: {e}")

    polling_running = is_polling_running()
    
    return {
        "success": True,
        "status": "ok" if influx_status == "ok" and polling_running else "degraded",
        "mode": mode,
        "components": {
            "influxdb": influx_status,
            "polling_enabled": settings.enable_polling,
            "polling_running": polling_running
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ============================================================
# 2. Realtime Batch (实时批量数据 - 所有6个水泵+压力表)
# ============================================================
@router.get("/realtime/batch")
async def get_realtime_batch():
    """
    获取所有设备实时数据 (6个水泵 + 1个压力表)
    
    返回格式：
    {
        "success": true,
        "timestamp": "2025-12-24T10:00:00Z",
        "source": "mock" | "cache" | "influxdb",
        "data": {
            "pumps": [
                {
                    "pump_id": "pump_1",
                    "voltage": 380.5,
                    "current": 32.1,
                    "power": 11234.5,
                    "status": "normal" | "warning" | "alarm",
                    "alarms": ["超压告警", ...]
                },
                ...
            ],
            "pressure": {
                "value": 0.65,
                "status": "normal" | "warning" | "alarm"
            }
        }
    }
    """
    try:
        # Mock模式：使用模拟数据
        if settings.use_mock_data:
            data = MockService.generate_realtime_batch()
            
            # Mock模式下也检测报警 (记录到InfluxDB)
            _check_mock_alarms(data)
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        # 真实模式：优先使用内存缓存
        cached_data = get_latest_data()
        if cached_data:
            # 转换为前端期望格式
            pumps = []
            pressure = None
            
            for device_id, device_data in cached_data.items():
                if device_id.startswith("pump_"):
                    pumps.append({
                        "pump_id": device_id,
                        **device_data
                    })
                elif device_id == "pressure":
                    pressure = device_data
            
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": {
                    "pumps": pumps,
                    "pressure": pressure
                }
            }
        
        # 缓存为空，查询InfluxDB
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        start_iso = start.isoformat() + "Z"
        stop_iso = end.isoformat() + "Z"
        
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start_iso,
            stop_iso=stop_iso,
            interval="10s"
        )
        
        # 解析为设备分组
        devices_dict = {}
        for record in raw_data:
            device_id = record.get("device_id", "unknown")
            field = record.get("field", "")
            value = record.get("value", 0)
            
            if device_id not in devices_dict:
                devices_dict[device_id] = {}
            
            devices_dict[device_id][field] = value
        
        # 转换为前端格式
        pumps = []
        pressure = None
        for device_id, device_data in devices_dict.items():
            if device_id.startswith("pump_"):
                pumps.append({
                    "pump_id": device_id,
                    **device_data
                })
            elif device_id == "pressure":
                pressure = device_data
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": {
                "pumps": pumps,
                "pressure": pressure
            }
        }
        
    except Exception as e:
        print(f"Error in get_realtime_batch: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ============================================================
# 3. Realtime Pressure (压力表实时数据)
# ============================================================
@router.get("/realtime/pressure")
async def get_realtime_pressure():
    """
    获取压力表实时数据
    
    返回格式：
    {
        "success": true,
        "timestamp": "...",
        "source": "mock" | "cache" | "influxdb",
        "data": {
            "value": 0.65,
            "status": "normal" | "warning" | "alarm"
        }
    }
    """
    try:
        # Mock模式
        if settings.use_mock_data:
            data = MockService.generate_pressure_data()
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        # 真实模式：优先缓存
        cached_data = get_latest_data()
        if cached_data and "pressure" in cached_data:
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": cached_data["pressure"]
            }
        
        # 查询InfluxDB
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start.isoformat() + "Z",
            stop_iso=end.isoformat() + "Z",
            interval="10s",
            device_id="pressure"
        )
        
        pressure_data = {}
        for record in raw_data:
            field = record.get("field", "")
            value = record.get("value", 0)
            pressure_data[field] = value
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": pressure_data
        }
        
    except Exception as e:
        print(f"Error in get_realtime_pressure: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ============================================================
# 4. Realtime Single Pump (单个水泵实时数据)
# ============================================================
@router.get("/realtime/{pump_id}")
async def get_realtime_pump(pump_id: int):
    """
    获取单个水泵实时数据
    
    参数：
    - pump_id: 水泵编号 (1-6)
    
    返回格式：
    {
        "success": true,
        "timestamp": "...",
        "source": "mock" | "cache" | "influxdb",
        "data": {
            "pump_id": "pump_1",
            "voltage": 380.5,
            "current": 32.1,
            "power": 11234.5,
            "status": "normal",
            "alarms": []
        }
    }
    """
    if pump_id < 1 or pump_id > 6:
        raise HTTPException(status_code=400, detail="pump_id must be between 1 and 6")
    
    device_id = f"pump_{pump_id}"
    
    try:
        # Mock模式
        if settings.use_mock_data:
            data = MockService.generate_pump_data(pump_id)
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "mock",
                "data": data
            }
        
        # 真实模式：优先缓存
        cached_data = get_latest_data()
        if cached_data and device_id in cached_data:
            return {
                "success": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "source": "cache",
                "data": {
                    "pump_id": device_id,
                    **cached_data[device_id]
                }
            }
        
        # 查询InfluxDB
        end = datetime.utcnow()
        start = end - timedelta(minutes=1)
        raw_data = query_data(
            measurement="sensor_data",
            start_iso=start.isoformat() + "Z",
            stop_iso=end.isoformat() + "Z",
            interval="10s",
            device_id=device_id
        )
        
        device_data = {}
        for record in raw_data:
            field = record.get("field", "")
            value = record.get("value", 0)
            device_data[field] = value
        
        return {
            "success": True,
            "timestamp": end.isoformat() + "Z",
            "source": "influxdb",
            "data": {
                "pump_id": device_id,
                **device_data
            }
        }
        
    except Exception as e:
        print(f"Error in get_realtime_pump: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ============================================================
# 5. History Data (历史数据查询)
# ============================================================
@router.get("/history")
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
    
    返回格式：
    {
        "success": true,
        "query": {
            "pump_id": 1,
            "parameter": "voltage",
            "start": "...",
            "end": "...",
            "interval": "5m"
        },
        "data": [
            {"timestamp": "2025-12-24T10:00:00Z", "value": 380.5},
            ...
        ]
    }
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
    
    # 确定设备ID
    device_id = f"pump_{pump_id}" if pump_id is not None else "pressure"
    
    try:
        # Mock模式
        if settings.use_mock_data:
            interval_seconds = _parse_interval(interval)
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
        
        # 提取指定参数 (保留1位小数)
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
        print(f"Error in get_history_data: {e}")
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


# ============================================================
# 6. Statistics (统计数据：最大/最小/平均)
# ============================================================
@router.get("/statistics")
async def get_statistics(
    pump_id: Optional[int] = Query(None, description="水泵编号 (1-6)"),
    parameter: str = Query(..., description="参数名 (voltage/current/power/pressure)"),
    start: Optional[str] = Query(None, description="开始时间"),
    end: Optional[str] = Query(None, description="结束时间")
):
    """
    查询统计数据 (最大/最小/平均)
    
    返回格式：
    {
        "success": true,
        "query": {...},
        "statistics": {
            "max": 400.5,
            "min": 360.2,
            "avg": 380.5,
            "count": 120
        }
    }
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
        # Mock模式：基于历史数据计算
        if settings.use_mock_data:
            history = MockService.generate_history_data(
                pump_id=pump_id,
                parameter=parameter,
                start_time=start_dt,
                end_time=end_dt,
                interval_minutes=1
            )
            
            if not history:
                return {
                    "success": False,
                    "error": "No data available"
                }
            
            values = [item["value"] for item in history]
            stats = {
                "max": max(values),
                "min": min(values),
                "avg": sum(values) / len(values),
                "count": len(values)
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
                "statistics": stats
            }
        
        # 真实模式：查询InfluxDB并计算
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
                "error": "No data found for the specified query",
                "query": {
                    "pump_id": pump_id,
                    "parameter": parameter,
                    "start": start_iso,
                    "end": stop_iso
                }
            }
        
        stats = {
            "max": max(values),
            "min": min(values),
            "avg": sum(values) / len(values),
            "count": len(values)
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
            "statistics": stats
        }
        
    except Exception as e:
        print(f"Error in get_statistics: {e}")
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


# ============================================================
@router.get("/status")
async def get_system_status():
    """
    获取系统轮询状态
    
    返回：
    - polling_running: 轮询服务是否运行
    - polling_stats: 轮询统计信息
    - resource_stats: 系统资源统计
    """
    try:
        # Mock模式下，跳过轮询统计
        if settings.use_mock_data:
            return {
                "success": True,
                "mode": "mock",
                "polling_running": False,
                "polling_stats": {
                    "message": "Polling disabled in mock mode"
                },
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
        
        # 真实模式
        polling_running = is_polling_running()
        stats = get_polling_stats() if polling_running else {}
        
        return {
            "success": True,
            "mode": "real",
            "polling_running": polling_running,
            "polling_stats": stats,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
    except Exception as e:
        print(f"Error in get_system_status: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ============================================================
# 阈值配置 API
# ============================================================
@router.get("/config/thresholds")
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
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.post("/config/thresholds")
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
        # 合并现有配置
        existing = load_thresholds()
        
        # 更新各类阈值
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
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


# ============================================================
# 报警日志 API
# ============================================================
@router.get("/alarms")
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
        return {
            "success": False,
            "error": str(e),
            "data": [],
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }


@router.get("/alarms/count")
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
        return {
            "success": False,
            "error": str(e),
            "data": {"warning": 0, "alarm": 0, "total": 0},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
