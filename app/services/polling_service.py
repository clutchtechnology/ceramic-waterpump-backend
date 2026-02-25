# ============================================================
# 文件说明: polling_service.py - 统一轮询服务
# ============================================================
# 功能:
#   1. 读取 DB2 数据块 (6电表 + 1压力)
#   2. 读取 DB4 数据块 (6振动传感器)
#   3. 解析和转换传感器数据
#   4. 批量写入 InfluxDB
#   5. 本地缓存降级 (InfluxDB 故障时)
# ============================================================

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from collections import deque

from config import get_settings
from app.core.influxdb import build_point, write_points_batch, check_influx_health
from app.core.local_cache import get_local_cache, CachedPoint
from app.plc.plc_manager import get_plc_manager
from app.tools.converter_elec import ElectricityConverter
from app.tools.converter_pressure import PressureConverter
from app.tools.converter_vibration import VibrationConverter
from app.plc.parser_data_db2 import parse_data_db2
from app.plc.parser_vib_db4 import parse_vib_db4

logger = logging.getLogger(__name__)
settings = get_settings()

# Mock 数据生成器（延迟导入）
_mock_generator = None
_mock_generator_loaded = False

# 服务状态
_poll_task: Optional[asyncio.Task] = None
_retry_task: Optional[asyncio.Task] = None
_is_running = False

# 转换器实例
_elec_conv = ElectricityConverter()
_pres_conv = PressureConverter()
_vib_conv = VibrationConverter()

# 最新数据缓存 (供 API 查询)
_latest_data: Dict[str, Any] = {}

# 批量写入缓存
_point_buffer: deque = deque(maxlen=500)
_batch_size = settings.influx_batch_size

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


def _get_mock_generator():
    """获取 Mock 数据生成器单例"""
    global _mock_generator, _mock_generator_loaded
    if _mock_generator_loaded and _mock_generator is not None:
        return _mock_generator

    try:
        from tests.mock.mock_data_generator import MockDataGenerator
    except ImportError:
        from pathlib import Path
        import importlib.util
        mock_path = Path(__file__).parent.parent.parent / "tests" / "mock" / "mock_data_generator.py"
        spec = importlib.util.spec_from_file_location("mock_data_generator", mock_path)
        mock_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mock_module)
        MockDataGenerator = mock_module.MockDataGenerator

    _mock_generator = MockDataGenerator()
    _mock_generator_loaded = True
    logger.info("[轮询] Mock模式: 已加载模拟数据生成器")
    return _mock_generator


def _extract_pump_index(device_id: str) -> int | None:
    """从设备 ID 中提取泵编号"""
    try:
        parts = device_id.split("_")
        for part in reversed(parts):
            if part.isdigit():
                return int(part)
    except Exception:
        return None
    return None


def _normalize_device_id(device_id: str, module_type: str) -> str:
    """归一化设备 ID"""
    if module_type == "PressureSensor":
        return "pressure"
    if module_type in ("ElectricityMeter", "VibrationSensor"):
        idx = _extract_pump_index(device_id)
        if idx:
            return f"pump_{idx}"
    # 振动传感器: vib_1 -> vib_1
    if "vib_" in device_id:
        return device_id
    return device_id


def _build_latest_cache(parsed_db2: Dict[str, Any], parsed_db4: List[Dict[str, Any]], timestamp: datetime) -> Dict[str, Any]:
    """构建最新数据缓存
    
    Args:
        parsed_db2: DB2 解析结果 (6电表 + 1压力)
        parsed_db4: DB4 解析结果 (6振动传感器)
        timestamp: 时间戳
    
    Returns:
        缓存数据字典
    """
    cache: Dict[str, Any] = {}

    # 1. 处理 DB2 数据 (电表 + 压力)
    for device_id, device_data in parsed_db2.items():
        for module_tag, module_data in device_data.get("modules", {}).items():
            module_type = module_data.get("module_type")
            raw_fields = module_data.get("fields", {})

            if module_type == _elec_conv.MODULE_TYPE:
                fields = _elec_conv.convert(raw_fields)
                pump_id = _extract_pump_index(device_id)
                if pump_id:
                    key = f"pump_{pump_id}"
                    cache.setdefault(key, {"id": pump_id, "timestamp": timestamp.isoformat()})
                    cache[key].update({
                        "power": fields.get("Pt", 0.0),
                        "energy": fields.get("ImpEp", 0.0),
                        "electricity": fields,
                    })

            elif module_type == _pres_conv.MODULE_TYPE:
                fields = _pres_conv.convert(raw_fields)
                cache["pressure"] = {
                    "value": fields.get("pressure", 0.0),
                    "pressure_kpa": fields.get("pressure_kpa", 0.0),
                    "timestamp": timestamp.isoformat()
                }

    # 2. 处理 DB4 数据 (6个振动传感器)
    for device_data in parsed_db4:
        device_id = device_data.get("device_id")
        
        for module_tag, module_data in device_data.get("modules", {}).items():
            module_type = module_data.get("module_type")
            
            if module_type == "vibration":
                raw_fields = module_data.get("fields", {})
                fields = _vib_conv.convert(raw_fields)
                
                # 振动传感器独立存储: vib_1, vib_2, vib_3, vib_4, vib_5, vib_6
                cache[device_id] = {
                    "device_id": device_id,
                    "device_name": device_data.get("device_name"),
                    "vibration": fields,
                    "timestamp": timestamp.isoformat()
                }

    return cache


async def _read_plc_db(db_number: int, db_size: int) -> Tuple[bool, bytes, str]:
    """读取 PLC DB 数据块（支持分块读取）
    
    Args:
        db_number: DB 块编号
        db_size: DB 块大小
    
    Returns:
        (成功标志, 原始字节数据, 错误信息)
    """
    MAX_READ_SIZE = 200  # PLC 单次读取最大字节数（保守值）
    
    if settings.use_mock_data:
        generator = _get_mock_generator()
        db_data = generator.generate_all_db_data()
        db_bytes = db_data.get(db_number, bytes(db_size))
        return (True, db_bytes, "")
    
    else:
        plc = get_plc_manager()
        if not plc.is_connected():
            success, err = plc.connect()
            if not success:
                return (False, b"", f"PLC连接失败: {err}")
        
        # 分块读取
        all_data = bytearray()
        offset = 0
        
        while offset < db_size:
            chunk_size = min(MAX_READ_SIZE, db_size - offset)
            success, chunk_data, err = plc.read_db(db_number, offset, chunk_size)
            
            if not success:
                return (False, bytes(all_data), f"读取偏移 {offset} 失败: {err}")
            
            all_data.extend(chunk_data)
            offset += chunk_size
        
        return (True, bytes(all_data), "")


def _flush_buffer():
    """刷新缓存：批量写入 InfluxDB 或保存到本地"""
    global _stats
    
    if len(_point_buffer) == 0:
        return
    
    points = list(_point_buffer)
    _point_buffer.clear()
    
    healthy, msg = check_influx_health()
    
    if healthy:
        success, err = write_points_batch(points)
        
        if success:
            _stats["successful_writes"] += len(points)
            _stats["last_write_time"] = datetime.now(timezone.utc).isoformat()
            if not settings.verbose_polling_log:
                logger.info(f"[轮询] 批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            logger.error(f"[轮询] InfluxDB 写入失败: {err}，转存到本地缓存")
            _save_to_local_cache(points)
    else:
        logger.warning(f"[轮询] InfluxDB 不可用 ({msg})，数据写入本地缓存")
        _save_to_local_cache(points)


def _save_to_local_cache(points: List):
    """保存数据点到本地 SQLite 缓存"""
    global _stats
    
    cache = get_local_cache()
    cached_points = []
    
    for point in points:
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
    
    logger.info(f"[轮询] 已保存 {saved_count} 个数据点到本地缓存")


async def _retry_cached_data():
    """定期重试本地缓存的数据"""
    global _stats
    
    cache = get_local_cache()
    retry_interval = 60
    
    while _is_running:
        await asyncio.sleep(retry_interval)
        
        healthy, _ = check_influx_health()
        if not healthy:
            continue
        
        pending = cache.get_pending_points(limit=100, max_retry=5)
        
        if not pending:
            cache.cleanup_old(days=7)
            continue
        
        logger.info(f"[轮询] 开始重试 {len(pending)} 条缓存数据...")
        
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
                logger.warning(f"[轮询] 重建 Point 失败: {e}")
        
        if not points:
            continue
        
        success, err = write_points_batch(points)
        
        if success:
            cache.mark_success(ids)
            _stats["retry_success"] += len(points)
            _stats["last_retry_time"] = datetime.now(timezone.utc).isoformat()
            logger.info(f"[轮询] 重试成功: {len(points)} 条数据已写入 InfluxDB")
        else:
            cache.mark_retry(ids)
            logger.error(f"[轮询] 重试失败: {err}")


async def _poll_loop():
    """统一轮询主循环（DB2 + DB4）"""
    global _latest_data, _stats
    
    poll_count = 0
    consecutive_failures = 0
    
    while _is_running:
        poll_count += 1
        timestamp = datetime.now(timezone.utc)
        _stats["total_polls"] += 1
        
        try:
            # 1. 读取 DB2 数据 (6电表 + 1压力)
            success_db2, db2_bytes, err_db2 = await _read_plc_db(2, 338)
            
            if not success_db2:
                consecutive_failures += 1
                logger.error(f"[轮询 poll #{poll_count}] DB2 读取失败 (连续 {consecutive_failures} 次): {err_db2}")
                
                if consecutive_failures >= 3:
                    wait_time = min(30, settings.poll_interval_db2 * consecutive_failures)
                    logger.warning(f"[轮询] 连续失败 {consecutive_failures} 次，等待 {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(settings.poll_interval_db2)
                continue
            
            # 2. 读取 DB4 数据 (6振动传感器)
            success_db4, db4_bytes, err_db4 = await _read_plc_db(4, 228)
            
            if not success_db4:
                logger.error(f"[轮询 poll #{poll_count}] DB4 读取失败: {err_db4}")
                # DB4 失败不影响 DB2，继续处理
            
            # 读取成功，重置失败计数
            consecutive_failures = 0
            
            # 3. 解析数据
            parsed_db2 = parse_data_db2(db2_bytes)
            parsed_db4 = parse_vib_db4(db4_bytes) if success_db4 else []
            
            _latest_data = _build_latest_cache(parsed_db2, parsed_db4, timestamp)
            
            # 4. 转换并加入缓冲区
            written_count = 0
            
            # 4.1 处理 DB2 数据
            for device_id, device_data in parsed_db2.items():
                for module_tag, module_data in device_data.get("modules", {}).items():
                    module_type = module_data.get("module_type")
                    raw_fields = module_data.get("fields", {})

                    if module_type == _elec_conv.MODULE_TYPE:
                        fields = _elec_conv.convert(raw_fields)
                    elif module_type == _pres_conv.MODULE_TYPE:
                        fields = _pres_conv.convert(raw_fields)
                    else:
                        continue

                    normalized_id = _normalize_device_id(device_id, module_type)
                    point = build_point(
                        measurement="sensor_data",
                        tags={"device_id": normalized_id, "module_type": module_type},
                        fields=fields,
                        timestamp=timestamp
                    )
                    if point:
                        _point_buffer.append(point)
                        written_count += 1
            
            # 4.2 处理 DB4 数据 (振动传感器)
            for device_data in parsed_db4:
                device_id = device_data.get("device_id")
                
                for module_tag, module_data in device_data.get("modules", {}).items():
                    module_type = module_data.get("module_type")
                    
                    if module_type == "vibration":
                        raw_fields = module_data.get("fields", {})
                        fields = _vib_conv.convert(raw_fields)
                        
                        point = build_point(
                            measurement="sensor_data",
                            tags={"device_id": device_id, "module_type": "VibrationSensor"},
                            fields=fields,
                            timestamp=timestamp
                        )
                        if point:
                            _point_buffer.append(point)
                            written_count += 1
            
            # 5. 检查是否需要批量写入
            buffer_usage = len(_point_buffer) / 500
            if buffer_usage > 0.8:
                logger.warning(f"[轮询] 缓冲区使用率过高: {buffer_usage*100:.1f}%，强制刷新")
                _flush_buffer()
            elif len(_point_buffer) >= _batch_size:
                _flush_buffer()
            
            # 6. 日志输出
            if settings.verbose_polling_log or poll_count % 10 == 0:
                cache_stats = get_local_cache().get_stats()
                logger.debug(f"[轮询 poll #{poll_count}] "
                      f"写入={written_count} | "
                      f"缓冲区={len(_point_buffer)}/{_batch_size} | "
                      f"待写入={cache_stats['pending_count']}")
        
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"[轮询 poll #{poll_count}] 轮询异常: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(settings.poll_interval_db2)


def _task_exception_handler(task: asyncio.Task):
    """处理 Task 未捕获异常"""
    try:
        exc = task.exception()
        if exc:
            logger.critical(f"[轮询] Task {task.get_name()} 崩溃: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        pass


async def start_polling():
    """启动统一轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    if _is_running:
        logger.warning("[轮询] 轮询服务已在运行")
        return
    
    _is_running = True
    
    if settings.use_mock_data:
        logger.info("[轮询] Mock模式启动")
    else:
        plc = get_plc_manager()
        success, err = plc.connect()
        if success:
            logger.info("[轮询] PLC 连接成功")
        else:
            logger.warning(f"[轮询] PLC 连接失败: {err}，将在轮询时重试")
    
    _poll_task = asyncio.create_task(_poll_loop(), name="poll_loop")
    _poll_task.add_done_callback(_task_exception_handler)
    
    _retry_task = asyncio.create_task(_retry_cached_data(), name="retry_loop")
    _retry_task.add_done_callback(_task_exception_handler)
    
    mode_str = "Mock" if settings.use_mock_data else "PLC"
    logger.info(f"[轮询] 轮询服务已启动 ({mode_str}模式, DB2间隔: {settings.poll_interval_db2}s)")


async def stop_polling():
    """停止统一轮询服务"""
    global _poll_task, _retry_task, _is_running
    
    _is_running = False
    
    logger.info("[轮询] 正在刷新缓冲区...")
    _flush_buffer()
    
    for task in [_poll_task, _retry_task]:
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    _poll_task = None
    _retry_task = None
    
    logger.info("[轮询] 轮询服务已停止")


def get_latest_data() -> Dict[str, Any]:
    """获取最新的传感器数据"""
    return _latest_data


def is_polling_running() -> bool:
    """检查轮询服务是否在运行"""
    return _is_running


def get_polling_stats() -> Dict[str, Any]:
    """获取轮询统计信息"""
    cache_stats = get_local_cache().get_stats()
    
    return {
        **_stats,
        "buffer_size": len(_point_buffer),
        "batch_size": _batch_size,
        "cache_stats": cache_stats,
    }

