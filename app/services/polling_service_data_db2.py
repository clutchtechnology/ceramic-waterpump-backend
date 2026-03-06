# ============================================================
# 文件说明: polling_service_data_db2.py - DB2+DB4 数据轮询服务
# ============================================================
# 功能:
#   1. 读取 DB2 数据块 (6电表 + 1压力)
#   2. 读取 DB4 数据块 (6振动传感器)
#   3. 解析和转换传感器数据
#   4. 批量写入 InfluxDB (失败时丢弃数据)
# ============================================================

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from collections import deque

from config import get_settings
from app.core.influxdb import build_point, write_points_batch, check_influx_health
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
_data_poll_task: Optional[asyncio.Task] = None
_is_data_running = False

# 转换器实例
_elec_conv = ElectricityConverter()
_pres_conv = PressureConverter()
_vib_conv = VibrationConverter()

# 最新数据缓存 (供 API 查询)
_latest_data: Dict[str, Any] = {}

# 批量写入缓存（优化：减小缓冲区大小，避免内存占用过高）
_point_buffer: deque = deque(maxlen=500)
_batch_size = settings.influx_batch_size

# 统计信息
_data_stats = {
    "total_polls": 0,
    "successful_writes": 0,
    "failed_writes": 0,
    "discarded_points": 0,
    "last_write_time": None
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
    logger.info("[DB2数据] Mock模式: 已加载模拟数据生成器")
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
    return device_id


def _build_latest_cache(parsed_db2: Dict[str, Any], parsed_db4: list, timestamp: datetime) -> Dict[str, Any]:
    """构建最新数据缓存
    
    Args:
        parsed_db2: DB2 解析结果 (6电表 + 1压力)
        parsed_db4: DB4 解析结果 (6振动传感器)
        timestamp: 时间戳
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
                cache[device_id] = {
                    "device_id": device_id,
                    "device_name": device_data.get("device_name"),
                    "vibration": fields,
                    "timestamp": timestamp.isoformat()
                }

    return cache


def _sync_read_plc_db2() -> Tuple[bool, bytes, str]:
    """[sync] 同步读取 PLC DB2 数据块 - 在线程中执行"""
    DB_NUMBER = 2
    DB_SIZE = 338
    MAX_READ_SIZE = 200

    plc = get_plc_manager()
    if not plc.is_connected():
        success, err = plc.connect()
        if not success:
            return (False, b"", f"PLC连接失败: {err}")

    all_data = bytearray()
    offset = 0

    while offset < DB_SIZE:
        chunk_size = min(MAX_READ_SIZE, DB_SIZE - offset)
        success, chunk_data, err = plc.read_db(DB_NUMBER, offset, chunk_size)
        if not success:
            return (False, bytes(all_data), f"读取偏移 {offset} 失败: {err}")
        all_data.extend(chunk_data)
        offset += chunk_size

    return (True, bytes(all_data), "")


async def _read_plc_db2() -> Tuple[bool, bytes, str]:
    """读取 PLC DB2 数据块 (6电表 + 1压力, 共338字节)
    
    注意: 振动传感器在 DB4 中, 不在 DB2
    
    Returns:
        (成功标志, 原始字节数据, 错误信息)
    """
    DB_SIZE = 338
    
    if settings.use_mock_data:
        generator = _get_mock_generator()
        db_data = generator.generate_all_db_data()
        db2_bytes = db_data.get(2, bytes(DB_SIZE))
        return (True, db2_bytes, "")
    
    else:
        return await asyncio.to_thread(_sync_read_plc_db2)


def _sync_read_plc_db4() -> Tuple[bool, bytes, str]:
    """[sync] 同步读取 PLC DB4 数据块 - 在线程中执行"""
    DB_NUMBER = 4
    DB_SIZE = 228
    MAX_READ_SIZE = 200

    plc = get_plc_manager()
    if not plc.is_connected():
        success, err = plc.connect()
        if not success:
            return (False, b"", f"PLC连接失败: {err}")

    all_data = bytearray()
    offset = 0

    while offset < DB_SIZE:
        chunk_size = min(MAX_READ_SIZE, DB_SIZE - offset)
        success, chunk_data, err = plc.read_db(DB_NUMBER, offset, chunk_size)
        if not success:
            return (False, bytes(all_data), f"DB4读取偏移 {offset} 失败: {err}")
        all_data.extend(chunk_data)
        offset += chunk_size

    return (True, bytes(all_data), "")


async def _read_plc_db4() -> Tuple[bool, bytes, str]:
    """读取 PLC DB4 数据块 (6个振动传感器, 228字节)
    
    Returns:
        (成功标志, 原始字节数据, 错误信息)
    """
    DB_SIZE = 228

    if settings.use_mock_data:
        generator = _get_mock_generator()
        db_data = generator.generate_all_db_data()
        db4_bytes = db_data.get(4, bytes(DB_SIZE))
        return (True, db4_bytes, "")

    else:
        return await asyncio.to_thread(_sync_read_plc_db4)


def _flush_buffer():
    """刷新缓存：批量写入 InfluxDB，失败时丢弃数据"""
    global _data_stats
    
    if len(_point_buffer) == 0:
        return
    
    points = list(_point_buffer)
    _point_buffer.clear()
    
    healthy, msg = check_influx_health()
    
    if healthy:
        success, err = write_points_batch(points)
        
        if success:
            _data_stats["successful_writes"] += len(points)
            _data_stats["last_write_time"] = datetime.now(timezone.utc).isoformat()
            if not settings.verbose_polling_log:
                logger.info(f"[DB2数据] 批量写入 {len(points)} 个数据点到 InfluxDB")
        else:
            _data_stats["failed_writes"] += len(points)
            _data_stats["discarded_points"] += len(points)
            logger.error(f"[DB2数据] InfluxDB 写入失败: {err}，丢弃 {len(points)} 个数据点")
    else:
        _data_stats["failed_writes"] += len(points)
        _data_stats["discarded_points"] += len(points)
        logger.warning(f"[DB2数据] InfluxDB 不可用 ({msg})，丢弃 {len(points)} 个数据点")


async def _data_poll_loop():
    """DB2+DB4 数据轮询主循环"""
    global _latest_data, _data_stats
    
    poll_count = 0
    consecutive_failures = 0  # 连续失败次数
    
    while _is_data_running:
        poll_count += 1
        timestamp = datetime.now(timezone.utc)
        _data_stats["total_polls"] += 1
        
        try:
            # 1. 读取 DB2 数据 (6电表 + 1压力)
            success_db2, db2_bytes, err_db2 = await _read_plc_db2()
            
            if not success_db2:
                consecutive_failures += 1
                logger.error(f"[DB2数据 poll #{poll_count}] DB2 读取失败 (连续 {consecutive_failures} 次): {err_db2}")
                
                # 连续失败超过 3 次，增加等待时间，避免频繁重连
                if consecutive_failures >= 3:
                    wait_time = min(30, settings.poll_interval_db2 * consecutive_failures)
                    logger.warning(f"[DB2数据] 连续失败 {consecutive_failures} 次，等待 {wait_time}s 后重试")
                    await asyncio.sleep(wait_time)
                else:
                    await asyncio.sleep(settings.poll_interval_db2)
                continue
            
            # 2. 读取 DB4 数据 (6振动传感器)
            success_db4, db4_bytes, err_db4 = await _read_plc_db4()
            if not success_db4:
                logger.error(f"[DB2数据 poll #{poll_count}] DB4 读取失败: {err_db4}")
                # DB4 失败不影响 DB2，继续处理
            
            # 读取成功，重置失败计数
            consecutive_failures = 0
            
            # 3. 解析数据
            parsed_db2 = parse_data_db2(db2_bytes)
            parsed_db4 = parse_vib_db4(db4_bytes) if success_db4 else []
            
            _latest_data = _build_latest_cache(parsed_db2, parsed_db4, timestamp)

            # 3.5 报警检测 (在线程中执行，避免阻塞事件循环)
            try:
                from app.services.alarm_checker import check_all_alarms
                await asyncio.to_thread(check_all_alarms, _latest_data, timestamp)
            except Exception as e:
                logger.error("[DB2数据] 报警检测异常: %s", e, exc_info=True)
            
            # 4. 转换并加入缓冲区
            written_count = 0
            
            # 4.1 处理 DB2 数据 (电表 + 压力)
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
            
            # 4. 检查是否需要批量写入（基于缓存数组长度）
            buffer_usage = len(_point_buffer) / 500
            if buffer_usage > 0.8:
                logger.warning(f"[DB2数据] 缓冲区使用率过高: {buffer_usage*100:.1f}%，强制刷新")
                await asyncio.to_thread(_flush_buffer)
            elif len(_point_buffer) >= _batch_size:
                await asyncio.to_thread(_flush_buffer)
            
            # 5. 日志输出
            if settings.verbose_polling_log or poll_count % 10 == 0:
                logger.debug(f"[DB2数据 poll #{poll_count}] "
                      f"写入={written_count} | "
                      f"缓冲区={len(_point_buffer)}/{_batch_size}")
        
        except Exception as e:
            consecutive_failures += 1
            logger.error(f"[DB2数据 poll #{poll_count}] 轮询异常: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(settings.poll_interval_db2)


def _task_exception_handler(task: asyncio.Task):
    """处理 Task 未捕获异常"""
    try:
        exc = task.exception()
        if exc:
            logger.critical(f"[DB2数据] Task {task.get_name()} 崩溃: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        pass


async def start_data_polling():
    """启动 DB2 数据轮询服务"""
    global _data_poll_task, _is_data_running
    
    if _is_data_running:
        logger.warning("[DB2数据] 轮询服务已在运行")
        return
    
    _is_data_running = True
    
    if settings.use_mock_data:
        logger.info("[DB2数据] Mock模式启动")
    else:
        plc = get_plc_manager()
        success, err = await asyncio.to_thread(plc.connect)
        if success:
            logger.info("[DB2数据] PLC 连接成功")
        else:
            logger.warning(f"[DB2数据] PLC 连接失败: {err}，将在轮询时重试")
    
    _data_poll_task = asyncio.create_task(_data_poll_loop(), name="data_poll_loop")
    _data_poll_task.add_done_callback(_task_exception_handler)
    
    mode_str = "Mock" if settings.use_mock_data else "PLC"
    logger.info(f"[DB2数据] 轮询服务已启动 ({mode_str}模式, 间隔: {settings.poll_interval_db2}s)")


async def stop_data_polling():
    """停止 DB2 数据轮询服务"""
    global _data_poll_task, _is_data_running
    
    _is_data_running = False
    
    logger.info("[DB2数据] 正在刷新缓冲区...")
    await asyncio.to_thread(_flush_buffer)
    
    if _data_poll_task:
        _data_poll_task.cancel()
        try:
            await _data_poll_task
        except asyncio.CancelledError:
            pass
    
    _data_poll_task = None
    
    logger.info("[DB2数据] 轮询服务已停止")


def get_latest_data() -> Dict[str, Any]:
    """获取最新的传感器数据（优化：直接返回引用，避免频繁拷贝）"""
    return _latest_data


def is_data_polling_running() -> bool:
    """检查数据轮询服务是否在运行"""
    return _is_data_running


def get_data_polling_stats() -> Dict[str, Any]:
    """获取数据轮询统计信息"""
    return {
        **_data_stats,
        "buffer_size": len(_point_buffer),
        "batch_size": _batch_size,
    }

