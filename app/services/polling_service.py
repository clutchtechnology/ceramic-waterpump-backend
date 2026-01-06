# ============================================================
# 文件说明: polling_service.py - 优化版数据轮询服务
# ============================================================
# 优化点:
#   1. PLC 长连接 (避免频繁连接/断开)
#   2. 批量写入 (30 次轮询缓存后批量写入)
#   3. 本地降级缓存 (InfluxDB 故障时写入 SQLite)
#   4. 自动重试机制 (缓存数据自动重试)
#   5. Mock模式支持 (使用MockDataGenerator生成模拟数据)
# ============================================================

import asyncio
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from collections import deque

from config import get_settings
from app.core.influxdb import build_point, write_points_batch, check_influx_health
from app.core.local_cache import get_local_cache, CachedPoint
from app.plc.plc_manager import get_plc_manager
from app.tools.converter_elec import ElectricityConverter
from app.tools.converter_pressure import PressureConverter
from app.plc.parser_waterpump import parse_waterpump_db
from app.core.threshold_store import check_alarm, check_pressure_alarm, get_pump_threshold, get_pressure_threshold
from app.core.alarm_store import log_alarm

logger = logging.getLogger(__name__)
settings = get_settings()

# Mock数据生成器（延迟导入，仅在mock模式下使用）
_mock_generator = None

_poll_task: Optional[asyncio.Task] = None
_retry_task: Optional[asyncio.Task] = None
_is_running = False

# 转换器实例
_elec_conv = ElectricityConverter()
_pres_conv = PressureConverter()

# 最新数据缓存 (供 API 查询)
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
# PLC 数据读取函数 (支持 Mock 模式)
# ============================================================
async def _read_plc_db2() -> Tuple[bool, bytes, str]:
    """读取 PLC DB2 数据块
    
    支持两种模式:
    1. Mock模式 (use_mock_data=True): 使用 MockDataGenerator 生成模拟数据
    2. 真实PLC模式: 通过 snap7 从真实 PLC 读取数据
    
    Returns:
        Tuple[bool, bytes, str]: (成功标志, 原始字节数据, 错误信息)
    """
    global _mock_generator
    
    # DB2 配置: 338 字节 (6个电表×56 + 压力表2)
    DB_NUMBER = 2
    DB_SIZE = 338
    
    if settings.use_mock_data:
        # Mock模式: 使用模拟数据生成器
        if _mock_generator is None:
            # 动态导入 MockDataGenerator (避免硬依赖)
            try:
                from tests.mock.mock_data_generator import MockDataGenerator
            except ImportError:
                # 兼容旧路径
                from pathlib import Path
                import importlib.util
                mock_path = Path(__file__).parent.parent.parent / "tests" / "mock" / "mock_data_generator.py"
                spec = importlib.util.spec_from_file_location("mock_data_generator", mock_path)
                mock_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mock_module)
                MockDataGenerator = mock_module.MockDataGenerator
            
            _mock_generator = MockDataGenerator()
            logger.info("Mock模式: 已加载模拟数据生成器")
        
        # 生成模拟数据
        db_data = _mock_generator.generate_all_db_data()
        db2_bytes = db_data.get(2, bytes(DB_SIZE))
        
        return (True, db2_bytes, "")
    
    else:
        # 真实PLC模式: 通过 snap7 读取
        plc = get_plc_manager()
        
        # 确保连接
        if not plc.is_connected():
            success, err = plc.connect()
            if not success:
                return (False, b"", f"PLC连接失败: {err}")
        
        # 读取 DB2
        success, data, err = plc.read_db(DB_NUMBER, 0, DB_SIZE)
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
                logger.info(f"批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            logger.error(f"InfluxDB 写入失败: {err}，转存到本地缓存")
            _save_to_local_cache(points)
    else:
        # InfluxDB 不可用，保存到本地
        logger.warning(f"InfluxDB 不可用 ({msg})，数据写入本地缓存")
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
    
    logger.info(f"已保存 {saved_count} 个数据点到本地缓存")


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
        
        logger.info(f"开始重试 {len(pending)} 条缓存数据...")
        
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
                logger.warning(f"重建 Point 失败: {e}")
        
        if not points:
            continue
        
        # 批量写入
        success, err = write_points_batch(points)
        
        if success:
            cache.mark_success(ids)
            _stats["retry_success"] += len(points)
            _stats["last_retry_time"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"重试成功: {len(points)} 条数据已写入 InfluxDB")
        else:
            cache.mark_retry(ids)
            logger.error(f"重试失败: {err}")


# ============================================================
# 主轮询循环
# ============================================================
async def _poll_loop():
    """轮询主循环"""
    global _latest_data, _buffer_count, _stats
    
    poll_count = 0
    
    while _is_running:
        poll_count += 1
        timestamp = datetime.now(timezone.utc)
        _stats["total_polls"] += 1
        
        try:
            # ========================================
            # Step 1: 读取 DB2 数据
            # ========================================
            success_db2, db2_bytes, err_db2 = await _read_plc_db2()
            
            if not success_db2:
                logger.error(f"[poll #{poll_count}] 读取 DB2 失败: {err_db2}")
                await asyncio.sleep(settings.plc_poll_interval)
                continue
            
            sensor_data = parse_waterpump_db(db2_bytes)
            _latest_data = sensor_data
            
            # ========================================
            # Step 2: 数据加入缓存
            # ========================================
            written_count = 0
            
            # 电表数据
            for idx in range(6):
                device_id = f"pump_meter_{idx+1}"
                meter_key = f"meter_{idx+1}"
                
                if meter_key not in sensor_data or "error" in sensor_data[meter_key]:
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
            
            # ========================================
            # Step 3: 报警检测
            # ========================================
            _check_and_log_alarms(sensor_data)
            
            # ========================================
            # Step 4: 检查是否需要批量写入
            # ========================================
            _buffer_count += 1
            
            # 缓冲区满告警 (达到90%容量)
            buffer_usage = len(_point_buffer) / 1000
            if buffer_usage > 0.9:
                logger.warning(f"缓冲区使用率过高: {buffer_usage*100:.1f}% (可能需要降低轮询频率)")
            
            # 当轮询次数达到batch_size或缓冲区点数超过200时，触发批量写入
            if _buffer_count >= _batch_size or len(_point_buffer) >= 200:
                _flush_buffer()
            
            # ========================================
            # 日志输出
            # ========================================
            if settings.verbose_polling_log or _buffer_count % 10 == 0:
                cache_stats = get_local_cache().get_stats()
                logger.debug(f"[poll #{poll_count}] "
                      f"数据: 写入={written_count} | "
                      f"缓冲区={len(_point_buffer)}/{_batch_size} | "
                      f"待写入={cache_stats['pending_count']}")
        
        except Exception as e:
            logger.error(f"[poll #{poll_count}] 轮询异常: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(settings.plc_poll_interval)


# ============================================================
# 服务控制函数
# ============================================================
def _task_exception_handler(task: asyncio.Task):
    """处理 Task 未捕获异常"""
    try:
        exc = task.exception()
        if exc:
            logger.critical(f"Task {task.get_name()} 崩溃: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        pass  # 正常取消


async def start_polling():
    """启动轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    if _is_running:
        logger.warning("轮询服务已在运行")
        return
    
    _is_running = True
    
    # 打印启动模式
    if settings.use_mock_data:
        logger.info("Mock模式：数据流 MockGenerator → 解析 → 转换 → InfluxDB")
    else:
        # 真实PLC模式：连接PLC
        plc = get_plc_manager()
        success, err = plc.connect()
        if success:
            logger.info("PLC 连接成功")
        else:
            logger.warning(f"PLC 连接失败: {err}，将在轮询时重试")
    
    # 启动轮询任务 (添加异常处理)
    _poll_task = asyncio.create_task(_poll_loop(), name="poll_loop")
    _poll_task.add_done_callback(_task_exception_handler)
    
    _retry_task = asyncio.create_task(_retry_cached_data(), name="retry_cached")
    _retry_task.add_done_callback(_task_exception_handler)
    
    mode_str = "Mock" if settings.use_mock_data else "PLC"
    logger.info(f"轮询服务已启动 ({mode_str}模式, 间隔: {settings.plc_poll_interval}s)")


async def stop_polling():
    """停止轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    _is_running = False
    
    # 刷新缓冲区
    logger.info("正在刷新缓冲区...")
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
    
    logger.info("轮询服务已停止")


# ============================================================
# 状态查询函数 (供 API 使用)
# ============================================================
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
