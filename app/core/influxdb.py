"""
InfluxDB 核心模块 - 数据写入与查询
奥卡姆剃刀: 单例 Client + 复用 WriteAPI
"""
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import threading
import atexit

from config import get_settings

settings = get_settings()

# 1, 模块级单例: Client + WriteAPI + 写入锁
_client: Optional[InfluxDBClient] = None
_write_api = None
_write_lock = threading.Lock()
_client_lock = threading.Lock()


def _get_or_create_client() -> Tuple[InfluxDBClient, Any]:
    """
    1, 获取或创建 InfluxDB Client 和 WriteAPI (线程安全单例)
    """
    global _client, _write_api
    
    if _client is not None and _write_api is not None:
        return _client, _write_api
    
    with _client_lock:
        if _client is None:
            _client = InfluxDBClient(
                url=settings.influx_url,
                token=settings.influx_token,
                org=settings.influx_org
            )
            _write_api = _client.write_api(write_options=SYNCHRONOUS)
            print(f"[OK] InfluxDB Client 已创建: {settings.influx_url}")
    
    return _client, _write_api


def get_influx_client() -> InfluxDBClient:
    """获取 InfluxDB Client (兼容旧接口)"""
    client, _ = _get_or_create_client()
    return client


def close_influx_client() -> None:
    """
    关闭 InfluxDB Client (应用退出时调用)
    """
    global _client, _write_api
    
    with _client_lock:
        if _write_api is not None:
            try:
                _write_api.close()
            except Exception:
                pass
            _write_api = None
        
        if _client is not None:
            try:
                _client.close()
                print("[OK] InfluxDB Client 已关闭")
            except Exception:
                pass
            _client = None


# 2, 应用退出时自动关闭连接
atexit.register(close_influx_client)


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


def write_point(
    measurement: str,
    tags: Dict[str, str],
    fields: Dict[str, Any],
    timestamp: Optional[datetime] = None
) -> bool:
    """
    3, 写入单个数据点到 InfluxDB (复用 WriteAPI)
    
    Args:
        measurement: 测量名称 (sensor_data / device_status / alarm_logs)
        tags: 标签字典 (device_id, module_type 等)
        fields: 字段字典 (数值数据)
        timestamp: 时间戳 (可选，默认当前时间)
    
    Returns:
        写入是否成功
    """
    point = build_point(measurement, tags, fields, timestamp)
    if point is None:
        return False
    
    try:
        _, write_api = _get_or_create_client()
        with _write_lock:
            write_api.write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                record=point
            )
        return True
    except Exception as e:
        print(f"[ERROR] InfluxDB 写入失败: {e}")
        return False


def write_points_batch(points: List[Point]) -> Tuple[bool, str]:
    """
    3, 批量写入数据点到 InfluxDB (复用 WriteAPI)
    
    Args:
        points: Point 对象列表
    
    Returns:
        (success, error_message)
    """
    if not points:
        return (True, "")
    
    try:
        _, write_api = _get_or_create_client()
        with _write_lock:
            write_api.write(
                bucket=settings.influx_bucket,
                org=settings.influx_org,
                record=points
            )
        return (True, "")
    except Exception as e:
        return (False, str(e))


def build_point(
    measurement: str,
    tags: Dict[str, str],
    fields: Dict[str, Any],
    timestamp: Optional[datetime] = None
) -> Optional[Point]:
    """
    4, 构建 InfluxDB Point 对象
    
    Args:
        measurement: 测量名称
        tags: 标签字典
        fields: 字段字典
        timestamp: 时间戳 (可选)
    
    Returns:
        Point 对象或 None (如果无有效字段)
    """
    point = Point(measurement)
    
    # 4.1, 添加标签
    for k, v in tags.items():
        point = point.tag(k, v)
    
    # 4.2, 添加字段 (alarm_logs 允许字符串字段)
    allow_string = measurement == "alarm_logs"
    valid_fields = 0
    
    for k, v in fields.items():
        if v is None:
            continue
        # 4.3, 字符串字段仅限 alarm_logs 或 comm_state
        if isinstance(v, str) and not (allow_string or k == "comm_state"):
            continue
        point = point.field(k, v)
        valid_fields += 1
    
    if valid_fields == 0:
        return None
    
    # 4.4, 设置时间戳
    if timestamp:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
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
    5, 查询 InfluxDB 历史数据
    
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
    
    # 5.1, 构建过滤条件 (防注入: 仅允许字母数字下划线)
    filters = []
    
    if device_id and device_id.replace("_", "").isalnum():
        filters.append(f'r["device_id"] == "{device_id}"')
    
    if tags:
        for k, v in tags.items():
            if k.isalnum() and str(v).replace("_", "").isalnum():
                filters.append(f'r["{k}"] == "{v}"')
    
    tag_filter = ""
    if filters:
        tag_filter = " |> filter(fn: (r) => " + " and ".join(filters) + ")"

    # 5.2, 构建 Flux 查询
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
        print(f"[ERROR] InfluxDB 查询失败: {e}")
        return []

