"""
报警日志存储 - InfluxDB measurement: alarm_logs
奥卡姆剃刀: 复用已有的InfluxDB
"""
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from app.core.influxdb import write_point, get_influx_client
from config import get_settings

settings = get_settings()

# 1, 报警去重: 同一设备同一类型报警，5分钟内不重复记录
_last_alarms: Dict[str, datetime] = {}
_alarms_lock = threading.Lock()  # 1, 线程安全锁
_ALARM_DEDUP_SECONDS = 300  # 5分钟

# 2, 设备ID验证正则 (仅允许字母数字下划线)
_DEVICE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')


def log_alarm(
    device_id: str,
    alarm_type: str,
    param_name: str,
    value: float,
    threshold: float,
    level: str,  # warning / alarm
    message: str = ""
) -> bool:
    """
    3, 记录报警日志到InfluxDB (线程安全 + 去重)
    
    Args:
        device_id: 设备ID (pump_1, pump_2, ..., pressure)
        alarm_type: 报警类型 (current_high, power_high, pressure_high, pressure_low, vibration_high)
        param_name: 参数名 (current, power, pressure, vibration)
        value: 当前值
        threshold: 触发阈值
        level: 报警级别 (warning / alarm)
        message: 报警消息
    
    Returns:
        是否成功记录 (去重后可能返回False)
    """
    # 3.1, 去重检查 (线程安全)
    dedup_key = f"{device_id}_{alarm_type}_{level}"
    now = datetime.now(timezone.utc)
    
    with _alarms_lock:
        if dedup_key in _last_alarms:
            elapsed = (now - _last_alarms[dedup_key]).total_seconds()
            if elapsed < _ALARM_DEDUP_SECONDS:
                return False  # 跳过重复报警
    
    # 3.2, 构建报警记录
    tags = {
        "device_id": device_id,
        "alarm_type": alarm_type,
        "level": level,
    }
    
    # 3.3, 确保数值字段始终为float类型，避免InfluxDB类型冲突
    fields = {
        "param_name": param_name,
        "value": float(value),
        "threshold": float(threshold),
        "message": message or f"{device_id} {param_name}={value:.2f} 超过阈值 {threshold:.2f}",
        "acknowledged": False,
    }
    
    success = write_point("alarm_logs", tags, fields, now)
    
    # 3.4, 更新去重记录 (线程安全)
    if success:
        with _alarms_lock:
            _last_alarms[dedup_key] = now
        print(f"🚨 报警记录: {device_id} {alarm_type} {level} - {param_name}={value:.2f}")
    
    return success


def _validate_id(value: Optional[str]) -> Optional[str]:
    """2, 验证ID参数 (防注入)"""
    if value is None:
        return None
    if _DEVICE_ID_PATTERN.match(value):
        return value
    return None


def query_alarms(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    device_id: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    4, 查询报警日志 (带输入验证)
    
    Args:
        start_time: 开始时间 (默认24小时前)
        end_time: 结束时间 (默认现在)
        device_id: 设备ID筛选
        level: 报警级别筛选
        limit: 最大返回条数
    
    Returns:
        报警记录列表
    """
    if start_time is None:
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
    if end_time is None:
        end_time = datetime.now(timezone.utc)
    
    # 4.1, 输入验证 (防注入)
    safe_device_id = _validate_id(device_id)
    safe_level = _validate_id(level)
    safe_limit = min(max(1, limit), 1000)  # 限制在 1-1000
    
    # 4.2, 构建Flux查询过滤条件
    filters = []
    if safe_device_id:
        filters.append(f'r["device_id"] == "{safe_device_id}"')
    if safe_level:
        filters.append(f'r["level"] == "{safe_level}"')
    
    filter_clause = " and ".join(filters) if filters else "true"
    
    query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: {start_time.isoformat()}, stop: {end_time.isoformat()})
        |> filter(fn: (r) => r["_measurement"] == "alarm_logs")
        |> filter(fn: (r) => {filter_clause})
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: {safe_limit})
    '''
    
    try:
        client = get_influx_client()
        query_api = client.query_api()
        tables = query_api.query(query, org=settings.influx_org)
        
        results = []
        for table in tables:
            for record in table.records:
                results.append({
                    "timestamp": record.get_time().isoformat(),
                    "device_id": record.values.get("device_id", ""),
                    "alarm_type": record.values.get("alarm_type", ""),
                    "level": record.values.get("level", ""),
                    "param_name": record.values.get("param_name", ""),
                    "value": record.values.get("value", 0),
                    "threshold": record.values.get("threshold", 0),
                    "message": record.values.get("message", ""),
                    "acknowledged": record.values.get("acknowledged", False),
                })
        
        return results
    except Exception as e:
        print(f"查询报警日志失败: {e}")
        return []


def get_alarm_count(hours: int = 24) -> Dict[str, int]:
    """
    5, 获取报警统计
    
    Args:
        hours: 统计时间范围 (小时)
    
    Returns:
        {"warning": n, "alarm": m, "total": n+m}
    """
    # 5.1, 参数验证
    safe_hours = min(max(1, hours), 168)  # 限制在 1-168 小时 (7天)
    start_time = datetime.now(timezone.utc) - timedelta(hours=safe_hours)
    
    query = f'''
    from(bucket: "{settings.influx_bucket}")
        |> range(start: {start_time.isoformat()})
        |> filter(fn: (r) => r["_measurement"] == "alarm_logs")
        |> filter(fn: (r) => r["_field"] == "value")
        |> group(columns: ["level"])
        |> count()
    '''
    
    try:
        client = get_influx_client()
        query_api = client.query_api()
        tables = query_api.query(query, org=settings.influx_org)
        
        counts = {"warning": 0, "alarm": 0}
        for table in tables:
            for record in table.records:
                level = record.values.get("level", "")
                if level in counts:
                    counts[level] = record.get_value()
        
        counts["total"] = counts["warning"] + counts["alarm"]
        return counts
    except Exception as e:
        print(f"查询报警统计失败: {e}")
        return {"warning": 0, "alarm": 0, "total": 0}
