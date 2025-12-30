from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS, WriteOptions
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from functools import lru_cache
import threading

from config import get_settings

settings = get_settings()

# 写入锁
_write_lock = threading.Lock()


@lru_cache()
def get_influx_client() -> InfluxDBClient:
    return InfluxDBClient(url=settings.influx_url, token=settings.influx_token, org=settings.influx_org)


def check_influx_health() -> Tuple[bool, str]:
    """
    检查 InfluxDB 连接健康状态
    
    Returns:
        (healthy, message)
    """
    try:
        client = get_influx_client()
        health = client.health()
        if health.status == "pass":
            return (True, "InfluxDB 正常")
        return (False, f"InfluxDB 状态: {health.status}")
    except Exception as e:
        return (False, str(e))


def write_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> bool:
    """
    写入单个数据点到 InfluxDB
    
    Args:
        measurement: 测量名称 (sensor_data / device_status)
        tags: 标签字典 (device_id, module_type 等)
        fields: 字段字典 (数值数据)
        timestamp: 时间戳 (可选，默认当前时间)
    
    Returns:
        写入是否成功
    """
    try:
        client = get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        point = _build_point(measurement, tags, fields, timestamp)
        if point is None:
            return False
        
        with _write_lock:
            write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=point)
        return True
    except Exception as e:
        print(f"❌ InfluxDB 写入失败: {e}")
        return False


def write_points_batch(points: List[Point]) -> Tuple[bool, str]:
    """
    批量写入数据点到 InfluxDB
    
    Args:
        points: Point 对象列表
    
    Returns:
        (success, error_message)
    """
    if not points:
        return (True, "")
    
    try:
        client = get_influx_client()
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        with _write_lock:
            write_api.write(bucket=settings.influx_bucket, org=settings.influx_org, record=points)
        
        return (True, "")
    except Exception as e:
        return (False, str(e))


def build_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> Optional[Point]:
    """
    构建 InfluxDB Point 对象（供外部批量使用）
    
    Returns:
        Point 对象或 None (如果字段为空)
    """
    return _build_point(measurement, tags, fields, timestamp)


def _build_point(measurement: str, tags: Dict[str, str], fields: Dict[str, Any], timestamp: Optional[datetime] = None) -> Optional[Point]:
    """
    内部方法：构建 Point 对象
    """
    point = Point(measurement)
    
    for k, v in tags.items():
        point = point.tag(k, v)
    
    # alarm_logs 允许字符串字段
    allow_string = measurement == "alarm_logs"
    
    valid_fields = 0
    for k, v in fields.items():
        # 跳过 None 值
        if v is None:
            continue
        # InfluxDB 字符串字段处理
        if isinstance(v, str):
            # alarm_logs 和特定字段允许字符串
            if not (allow_string or k == "comm_state"):
                continue
        point = point.field(k, v)
        valid_fields += 1
    
    if valid_fields == 0:
        return None
    
    if timestamp:
        if timestamp.tzinfo is None:
            timestamp = timestamp.astimezone(timezone.utc)
        point = point.time(timestamp)
    
    return point



def query_data(
    measurement: str, 
    start_iso: str, 
    stop_iso: str, 
    tags: Optional[Dict[str, str]] = None, 
    interval: str = "1m",
    device_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    查询 InfluxDB 历史数据
    
    Args:
        measurement: 测量名称
        start_iso: 开始时间 (ISO 格式)
        stop_iso: 结束时间 (ISO 格式)
        tags: 标签过滤条件
        interval: 聚合间隔 (1m/5m/1h/1d 等)
        device_id: 设备 ID 过滤 (可选)
    
    Returns:
        数据点列表
    """
    client = get_influx_client()
    query_api = client.query_api()
    
    # 构建过滤条件
    filters = []
    
    if device_id:
        filters.append(f'r["device_id"] == "{device_id}"')
    
    if tags:
        for k, v in tags.items():
            filters.append(f'r["{k}"] == "{v}"')
    
    tag_filter = ""
    if filters:
        tag_filter = " |> filter(fn: (r) => " + " and ".join(filters) + ")"

    query = f'''
    from(bucket: "{settings.influx_bucket}")
      |> range(start: {start_iso}, stop: {stop_iso})
      |> filter(fn: (r) => r["_measurement"] == "{measurement}")
      {tag_filter}
      |> aggregateWindow(every: {interval}, fn: mean, createEmpty: false)
      |> yield(name: "mean")
    '''

    try:
        result = query_api.query(query)
        data = []
        for table in result:
            for record in table.records:
                data.append({
                    "time": record.get_time().isoformat(),
                    "field": record.get_field(),
                    "value": record.get_value(),
                    **{k: v for k, v in record.values.items() if not k.startswith("_")}
                })
        return data
    except Exception as e:
        print(f"❌ InfluxDB 查询失败: {e}")
        return []

