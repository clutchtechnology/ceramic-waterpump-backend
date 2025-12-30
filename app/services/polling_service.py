# ============================================================
# 文件说明: polling_service.py - 优化版数据轮询服务
# ============================================================
# 优化点:
#   1. PLC 长连接 (避免频繁连接/断开)
#   2. 批量写入 (30 次轮询缓存后批量写入)
#   3. 本地降级缓存 (InfluxDB 故障时写入 SQLite)
#   4. 自动重试机制 (缓存数据自动重试)
#   5. Mock模式支持 (use_mock_data=True时自动禁用轮询)
# ============================================================

import asyncio
import random
import struct
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from collections import deque

from config import get_settings
from app.core.influxdb import build_point, write_points_batch, check_influx_health
from app.core.local_cache import get_local_cache, CachedPoint
from app.plc.plc_manager import get_plc_manager
from app.tools.converter_elec import ElectricityConverter
from app.tools.converter_pressure import PressureConverter
from app.tools.converter_status import StatusConverter
from app.plc.parser_status import parse_status_db, is_device_comm_ok, DEVICE_STATUS_MAP
from app.plc.parser_waterpump import parse_waterpump_db
from app.core.threshold_store import check_alarm, check_pressure_alarm, get_pump_threshold, get_pressure_threshold
from app.core.alarm_store import log_alarm

settings = get_settings()

_poll_task: Optional[asyncio.Task] = None
_retry_task: Optional[asyncio.Task] = None
_is_running = False

# 转换器实例
_elec_conv = ElectricityConverter()
_pres_conv = PressureConverter()
_status_conv = StatusConverter()

# 最新状态缓存 (供 API 查询)
_latest_status: Dict[str, Any] = {}
_latest_data: Dict[str, Any] = {}

# 批量写入缓存 (30 次轮询)
_point_buffer: deque = deque(maxlen=1000)  # 最大缓存 1000 个点
_buffer_count = 0
_batch_size = 30  # 30 次轮询后批量写入

# 统计信息
_stats = {
    "total_polls": 0,
    "successful_writes": 0,
    "failed_writes": 0,
    "cached_points": 0,
    "retry_success": 0,
    "last_write_time": None,
    "last_retry_time": None
}


# ============================================================
# 模拟数据生成 (开发/测试用)
# ============================================================
def _generate_mock_db1() -> bytes:
    """生成模拟的 DB1 状态数据 (56 字节)"""
    data = bytearray(56)
    
    for device_id, offset in DEVICE_STATUS_MAP.items():
        # 95% 概率通信正常
        r = random.random()
        if r < 0.95:
            data[offset] = 0x01  # DONE=1
            data[offset+2:offset+4] = struct.pack(">H", 0)
        elif r < 0.98:
            data[offset] = 0x02  # BUSY=1
            data[offset+2:offset+4] = struct.pack(">H", 0)
        else:
            data[offset] = 0x04  # ERROR=1
            data[offset+2:offset+4] = struct.pack(">H", 0x8001)
    
    return bytes(data)


def _generate_mock_db2() -> bytes:
    """生成模拟的 DB2 数据 (338 字节)"""
    data = bytearray(338)
    
    for idx in range(6):
        offset = idx * 56
        base_voltage = 220.0 + random.uniform(-5, 5)
        base_line_voltage = 380.0 + random.uniform(-5, 5)
        base_current = 10.0 + idx * 2 + random.uniform(-2, 2)
        
        meter_values = [
            base_line_voltage + random.uniform(-2, 2),
            base_line_voltage + random.uniform(-2, 2),
            base_line_voltage + random.uniform(-2, 2),
            base_voltage + random.uniform(-2, 2),
            base_voltage + random.uniform(-2, 2),
            base_voltage + random.uniform(-2, 2),
            base_current + random.uniform(-1, 1),
            base_current + random.uniform(-1, 1),
            base_current + random.uniform(-1, 1),
            base_current * 3 * base_voltage / 1000.0,
            base_current * base_voltage / 1000.0,
            base_current * base_voltage / 1000.0,
            base_current * base_voltage / 1000.0,
            1000.0 + idx * 100 + random.uniform(0, 10),
        ]
        
        for i, val in enumerate(meter_values):
            data[offset + i*4 : offset + i*4 + 4] = struct.pack(">f", val)
    
    pressure_raw = int(1000 + random.uniform(-100, 100))
    data[336:338] = struct.pack(">H", min(65535, max(0, pressure_raw)))
    
    return bytes(data)


# ============================================================
# PLC 读取函数 (使用长连接)
# ============================================================
async def _read_plc_db(db_number: int, size: int) -> tuple[bool, bytes, str]:
    """
    读取 PLC DB 块数据（使用 PLC 管理器）
    
    Returns:
        (success, data, error_msg)
    """
    # Mock数据模式 - 直接生成模拟数据
    if settings.use_mock_data:
        await asyncio.sleep(0.01)  # 模拟读取延迟
        if db_number == 1:
            return (True, _generate_mock_db1(), "")
        elif db_number == 2:
            return (True, _generate_mock_db2(), "")
        else:
            return (False, b"", f"Unknown DB{db_number}")
    
    # 真实 PLC 模式
    plc = get_plc_manager()
    
    if not plc._initialized:
        return (False, b"", "PLC未初始化")
    
    success, data, err = plc.read_db(db_number, 0, size)
    return (success, data, err)


# ============================================================
# 报警检测函数
# ============================================================
def _check_and_log_alarms(sensor_data: Dict[str, Any]):
    """
    检测数据是否触发报警阈值，并记录报警日志
    
    Args:
        sensor_data: 从 parse_waterpump_db 解析出的数据
    """
    # 检测6个水泵电表数据
    for idx in range(6):
        meter_key = f"meter_{idx+1}"
        pump_id = idx + 1
        device_id = f"pump_{pump_id}"
        
        if meter_key not in sensor_data or "error" in sensor_data[meter_key]:
            continue
        
        meter = sensor_data[meter_key]
        
        # 检查电流 (使用Pt总功率对应的电流，或I_0)
        current = meter.get("I_0", 0)
        current_alarm = check_alarm(pump_id, "current", current)
        if current_alarm:
            threshold = get_pump_threshold(pump_id, "current")
            threshold_val = threshold["warning_max"] if current_alarm == "alarm" else threshold["normal_max"]
            log_alarm(
                device_id=device_id,
                alarm_type="current_high",
                param_name="current",
                value=current,
                threshold=threshold_val,
                level=current_alarm,
            )
        
        # 检查功率
        power = meter.get("Pt", 0)
        power_alarm = check_alarm(pump_id, "power", power)
        if power_alarm:
            threshold = get_pump_threshold(pump_id, "power")
            threshold_val = threshold["warning_max"] if power_alarm == "alarm" else threshold["normal_max"]
            log_alarm(
                device_id=device_id,
                alarm_type="power_high",
                param_name="power",
                value=power,
                threshold=threshold_val,
                level=power_alarm,
            )
    
    # 检测压力
    if "pressure" in sensor_data and "error" not in sensor_data["pressure"]:
        pressure = sensor_data["pressure"].get("pressure", 0)
        pressure_alarm = check_pressure_alarm(pressure)
        
        if pressure_alarm:
            threshold = get_pressure_threshold()
            if pressure_alarm == "alarm_high":
                log_alarm(
                    device_id="pressure",
                    alarm_type="pressure_high",
                    param_name="pressure",
                    value=pressure,
                    threshold=threshold["high_alarm"],
                    level="alarm",
                )
            elif pressure_alarm == "alarm_low":
                log_alarm(
                    device_id="pressure",
                    alarm_type="pressure_low",
                    param_name="pressure",
                    value=pressure,
                    threshold=threshold["low_alarm"],
                    level="alarm",
                )


# ============================================================
# 批量写入 & 本地缓存
# ============================================================
def _flush_buffer():
    """
    刷新缓存：批量写入 InfluxDB 或保存到本地
    """
    global _buffer_count, _stats
    
    if len(_point_buffer) == 0:
        return
    
    # 转换为 Point 列表
    points = list(_point_buffer)
    _point_buffer.clear()
    _buffer_count = 0
    
    # 检查 InfluxDB 健康状态
    healthy, msg = check_influx_health()
    
    if healthy:
        # 尝试写入 InfluxDB
        success, err = write_points_batch(points)
        
        if success:
            _stats["successful_writes"] += len(points)
            _stats["last_write_time"] = datetime.now(timezone.utc).isoformat()
            if not settings.verbose_polling_log:
                print(f"✅ 批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            print(f"❌ InfluxDB 写入失败: {err}，转存到本地缓存")
            _save_to_local_cache(points)
    else:
        # InfluxDB 不可用，保存到本地
        print(f"⚠️ InfluxDB 不可用 ({msg})，数据写入本地缓存")
        _save_to_local_cache(points)


def _save_to_local_cache(points: List):
    """保存数据点到本地 SQLite 缓存"""
    global _stats
    
    cache = get_local_cache()
    cached_points = []
    
    for point in points:
        # 提取 Point 对象的信息
        cached_point = CachedPoint(
            measurement=point._name,
            tags={k: v for k, v in point._tags.items()},
            fields={k: v for k, v in point._fields.items()},
            timestamp=point._time.isoformat() if point._time else datetime.now(timezone.utc).isoformat()
        )
        cached_points.append(cached_point)
    
    saved_count = cache.save_points(cached_points)
    _stats["cached_points"] += saved_count
    _stats["failed_writes"] += len(points)
    
    print(f"💾 已保存 {saved_count} 个数据点到本地缓存")


# ============================================================
# 缓存重试任务
# ============================================================
async def _retry_cached_data():
    """定期重试本地缓存的数据"""
    global _stats
    
    cache = get_local_cache()
    retry_interval = 60  # 每 60 秒重试一次
    
    while _is_running:
        await asyncio.sleep(retry_interval)
        
        # 检查 InfluxDB 健康状态
        healthy, _ = check_influx_health()
        if not healthy:
            continue
        
        # 获取待重试数据
        pending = cache.get_pending_points(limit=100, max_retry=5)
        
        if not pending:
            continue
        
        print(f"🔄 开始重试 {len(pending)} 条缓存数据...")
        
        # 重新构建 Point 对象
        points = []
        ids = []
        
        for point_id, cached_point in pending:
            try:
                point = build_point(
                    cached_point.measurement,
                    cached_point.tags,
                    cached_point.fields,
                    datetime.fromisoformat(cached_point.timestamp)
                )
                if point:
                    points.append(point)
                    ids.append(point_id)
            except Exception as e:
                print(f"⚠️ 重建 Point 失败: {e}")
        
        if not points:
            continue
        
        # 批量写入
        success, err = write_points_batch(points)
        
        if success:
            cache.mark_success(ids)
            _stats["retry_success"] += len(points)
            _stats["last_retry_time"] = datetime.now(timezone.utc).isoformat()
            print(f"✅ 重试成功: {len(points)} 条数据已写入 InfluxDB")
        else:
            cache.mark_retry(ids)
            print(f"❌ 重试失败: {err}")


# ============================================================
# 主轮询循环
# ============================================================
async def _poll_loop():
    """轮询主循环"""
    global _latest_status, _latest_data, _buffer_count, _stats
    
    poll_count = 0
    
    while _is_running:
        poll_count += 1
        timestamp = datetime.now(timezone.utc)
        _stats["total_polls"] += 1
        
        try:
            # ========================================
            # Step 1: 读取 DB1 状态
            # ========================================
            success_db1, db1_bytes, err_db1 = await _read_plc_db(1, 56)
            
            if not success_db1:
                print(f"❌ [poll #{poll_count}] 读取 DB1 失败: {err_db1}")
                await asyncio.sleep(settings.plc_poll_interval)
                continue
            
            status_data = parse_status_db(db1_bytes)
            _latest_status = status_data
            
            # 状态数据加入缓存
            for device_id in DEVICE_STATUS_MAP.keys():
                if device_id in status_data and device_id != "summary":
                    fields = _status_conv.convert(status_data[device_id])
                    point = build_point(
                        measurement="device_status",
                        tags={"device_id": device_id, "module_type": "CommStatus"},
                        fields=fields,
                        timestamp=timestamp
                    )
                    if point:
                        _point_buffer.append(point)
            
            # ========================================
            # Step 2: 读取 DB2 数据
            # ========================================
            success_db2, db2_bytes, err_db2 = await _read_plc_db(2, 338)
            
            if not success_db2:
                print(f"❌ [poll #{poll_count}] 读取 DB2 失败: {err_db2}")
                await asyncio.sleep(settings.plc_poll_interval)
                continue
            
            sensor_data = parse_waterpump_db(db2_bytes)
            _latest_data = sensor_data
            
            # ========================================
            # Step 3: 根据状态过滤，加入缓存
            # ========================================
            written_count = 0
            skipped_count = 0
            
            # 电表数据
            for idx in range(6):
                device_id = f"pump_meter_{idx+1}"
                meter_key = f"meter_{idx+1}"
                
                device_status = status_data.get(device_id, {})
                
                if not is_device_comm_ok(device_status):
                    skipped_count += 1
                    continue
                
                if meter_key not in sensor_data or "error" in sensor_data[meter_key]:
                    skipped_count += 1
                    continue
                
                fields = _elec_conv.convert(sensor_data[meter_key])
                point = build_point(
                    measurement="sensor_data",
                    tags={"device_id": device_id, "module_type": _elec_conv.MODULE_TYPE},
                    fields=fields,
                    timestamp=timestamp
                )
                if point:
                    _point_buffer.append(point)
                    written_count += 1
            
            # 压力表数据
            pressure_status = status_data.get("pump_pressure", {})
            
            if is_device_comm_ok(pressure_status):
                if "pressure" in sensor_data and "error" not in sensor_data["pressure"]:
                    fields = _pres_conv.convert(sensor_data["pressure"])
                    point = build_point(
                        measurement="sensor_data",
                        tags={"device_id": "pump_pressure", "module_type": _pres_conv.MODULE_TYPE},
                        fields=fields,
                        timestamp=timestamp
                    )
                    if point:
                        _point_buffer.append(point)
                        written_count += 1
            else:
                skipped_count += 1
            
            # ========================================
            # Step 3.5: 报警检测
            # ========================================
            _check_and_log_alarms(sensor_data)
            
            # ========================================
            # Step 4: 检查是否需要批量写入
            # ========================================
            _buffer_count += 1
            
            # 缓冲区满告警 (达到90%容量)
            buffer_usage = len(_point_buffer) / 1000
            if buffer_usage > 0.9:
                print(f"⚠️ 缓冲区使用率过高: {buffer_usage*100:.1f}% (可能需要降低轮询频率)")
            
            # 当轮询次数达到batch_size或缓冲区点数超过200时，触发批量写入
            if _buffer_count >= _batch_size or len(_point_buffer) >= 200:
                _flush_buffer()
            
            # ========================================
            # 日志输出
            # ========================================
            summary = status_data.get("summary", {})
            
            if settings.verbose_polling_log or _buffer_count % 10 == 0:
                cache_stats = get_local_cache().get_stats()
                print(f"📊 [poll #{poll_count}] "
                      f"状态: OK={summary.get('ok_count', 0)}/ERR={summary.get('error_count', 0)} | "
                      f"数据: 缓存={written_count}, 跳过={skipped_count} | "
                      f"缓冲区={len(_point_buffer)}/{_batch_size} | "
                      f"待写入={cache_stats['pending_count']}")
        
        except Exception as e:
            print(f"❌ [poll #{poll_count}] 轮询异常: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(settings.plc_poll_interval)


# ============================================================
# 服务控制函数
# ============================================================
async def start_polling():
    """启动轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    # Mock模式下检查是否启用Mock轮询
    if settings.use_mock_data:
        if not settings.enable_mock_polling:
            print("📝 Mock模式：跳过轮询服务启动 (enable_mock_polling=False)")
            return
        else:
            print("📝 Mock模式：启用模拟轮询 (enable_mock_polling=True)")
    
    if _is_running:
        print("⚠️ 轮询服务已在运行")
        return
    
    _is_running = True
    
    # 启动 PLC 连接
    plc = get_plc_manager()
    success, err = plc.connect()
    if success:
        print(f"✅ PLC 连接成功")
    else:
        print(f"⚠️ PLC 连接失败: {err}，将使用模拟数据")
    
    # 启动轮询任务
    _poll_task = asyncio.create_task(_poll_loop())
    _retry_task = asyncio.create_task(_retry_cached_data())
    
    print(f"✅ 轮询服务已启动 (间隔: {settings.plc_poll_interval}s, 批量: {_batch_size}次)")


async def stop_polling():
    """停止轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    _is_running = False
    
    # 刷新缓冲区
    print("⏳ 正在刷新缓冲区...")
    _flush_buffer()
    
    # 取消任务
    for task in [_poll_task, _retry_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    _poll_task = None
    _retry_task = None
    
    # 断开 PLC
    plc = get_plc_manager()
    plc.disconnect()
    
    print("⏹️ 轮询服务已停止")


# ============================================================
# 状态查询函数 (供 API 使用)
# ============================================================
def get_latest_status() -> Dict[str, Any]:
    """获取最新的设备状态"""
    return _latest_status.copy()


def get_latest_data() -> Dict[str, Any]:
    """获取最新的传感器数据"""
    return _latest_data.copy()


def is_polling_running() -> bool:
    """检查轮询服务是否在运行"""
    return _is_running


def get_polling_stats() -> Dict[str, Any]:
    """获取轮询统计信息"""
    cache_stats = get_local_cache().get_stats()
    plc_status = get_plc_manager().get_status()
    
    return {
        **_stats,
        "buffer_size": len(_point_buffer),
        "batch_size": _batch_size,
        "cache_stats": cache_stats,
        "plc_status": plc_status
    }
