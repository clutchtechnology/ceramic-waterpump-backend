# ============================================================
# 文件说明: polling_service_status_db1_3.py - DB1/DB3 状态轮询服务
# ============================================================
# 功能:
#   1. 读取 DB1 主站状态块
#   2. 读取 DB3 从站状态块
#   3. 解析通信状态
#   4. 缓存到内存 (不写入 InfluxDB)
#   5. 供 WebSocket 推送使用
# ============================================================

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from config import get_settings
from app.plc.plc_manager import get_plc_manager
from app.plc.parser_status_db1 import parse_status_db1
from app.plc.parser_status_db3 import parse_status_db3

logger = logging.getLogger(__name__)
settings = get_settings()

# Mock 数据生成器（延迟导入）
_mock_generator = None
_mock_generator_loaded = False

# 服务状态
_status_poll_task: Optional[asyncio.Task] = None
_is_status_running = False

# 最新状态缓存 (供 API 查询和 WebSocket 推送)
_latest_status: Dict[str, Any] = {}

# 状态变化标志 (用于通知 WebSocket 推送)
_status_changed = False

# 统计信息
_status_stats = {
    "total_polls": 0,
    "last_poll_time": None,
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
    logger.info("[DB1/DB3状态] Mock模式: 已加载模拟数据生成器")
    return _mock_generator


async def _read_plc_db1() -> Tuple[bool, bytes, str]:
    """读取 PLC DB1 主站状态块
    
    Returns:
        (成功标志, 原始字节数据, 错误信息)
    """
    DB_NUMBER = 1
    DB_SIZE = 80

    if settings.use_mock_data:
        generator = _get_mock_generator()
        db_data = generator.generate_all_db_data()
        db1_bytes = db_data.get(1, bytes(DB_SIZE))
        return (True, db1_bytes, "")

    plc = get_plc_manager()
    if not plc.is_connected():
        success, err = plc.connect()
        if not success:
            return (False, b"", f"PLC连接失败: {err}")

    success, data, err = plc.read_db(DB_NUMBER, 0, DB_SIZE)
    return (success, data, err)


async def _read_plc_db3() -> Tuple[bool, bytes, str]:
    """读取 PLC DB3 从站状态块
    
    Returns:
        (成功标志, 原始字节数据, 错误信息)
    """
    DB_NUMBER = 3
    DB_SIZE = 80

    if settings.use_mock_data:
        generator = _get_mock_generator()
        db_data = generator.generate_all_db_data()
        db3_bytes = db_data.get(3, bytes(DB_SIZE))
        return (True, db3_bytes, "")

    plc = get_plc_manager()
    if not plc.is_connected():
        success, err = plc.connect()
        if not success:
            return (False, b"", f"PLC连接失败: {err}")

    success, data, err = plc.read_db(DB_NUMBER, 0, DB_SIZE)
    return (success, data, err)


def _has_status_changed(old_status: Dict[str, Any], new_status: Dict[str, Any]) -> bool:
    """检查状态是否发生变化
    
    Args:
        old_status: 旧状态数据
        new_status: 新状态数据
    
    Returns:
        True 表示状态已变化，False 表示未变化
    """
    if not old_status:
        return True
    
    # 比较 summary_by_db
    old_summary = old_status.get("summary_by_db", {})
    new_summary = new_status.get("summary_by_db", {})
    
    if old_summary != new_summary:
        return True
    
    # 比较设备状态列表
    old_data = old_status.get("data", {})
    new_data = new_status.get("data", {})
    
    for db_key in ["db1", "db3"]:
        old_devices = old_data.get(db_key, [])
        new_devices = new_data.get(db_key, [])
        
        if len(old_devices) != len(new_devices):
            return True
        
        # 比较每个设备的关键字段
        for old_dev, new_dev in zip(old_devices, new_devices):
            if (old_dev.get("error") != new_dev.get("error") or
                old_dev.get("status_code") != new_dev.get("status_code") or
                old_dev.get("is_normal") != new_dev.get("is_normal")):
                return True
    
    return False


def _build_status_cache(
    db1_bytes: Optional[bytes],
    db3_bytes: Optional[bytes],
    source: str,
    timestamp: datetime,
) -> Dict[str, Any]:
    """构建状态缓存
    
    Args:
        db1_bytes: DB1 原始字节数据
        db3_bytes: DB3 原始字节数据
        source: 数据来源 (mock/plc)
        timestamp: 时间戳
    
    Returns:
        状态缓存字典
    """
    data: Dict[str, Any] = {}
    summary_by_db: Dict[str, Any] = {}

    if db1_bytes:
        parsed_db1 = parse_status_db1(db1_bytes, only_enabled=True)
        data["db1"] = parsed_db1.get("devices", [])
        summary_by_db["db1"] = parsed_db1.get("summary", {})

    if db3_bytes:
        parsed_db3 = parse_status_db3(db3_bytes, only_enabled=True)
        data["db3"] = parsed_db3.get("devices", [])
        summary_by_db["db3"] = parsed_db3.get("summary", {})

    return {
        "data": data,
        "summary_by_db": summary_by_db,
        "source": source,
        "timestamp": timestamp.isoformat() + "Z",
    }


async def _status_poll_loop():
    """DB1/DB3 状态轮询主循环"""
    global _latest_status, _status_stats, _status_changed
    
    poll_count = 0
    
    while _is_status_running:
        poll_count += 1
        timestamp = datetime.now(timezone.utc)
        _status_stats["total_polls"] += 1
        _status_stats["last_poll_time"] = timestamp.isoformat()
        
        try:
            # 1. 读取 DB1 和 DB3
            if settings.use_mock_data:
                generator = _get_mock_generator()
                db_data = generator.generate_all_db_data()
                db1_bytes = db_data.get(1)
                db3_bytes = db_data.get(3)
                success_db1, success_db3 = True, True
                err_db1 = err_db3 = ""
            else:
                success_db1, db1_bytes, err_db1 = await _read_plc_db1()
                success_db3, db3_bytes, err_db3 = await _read_plc_db3()

            if not success_db1:
                logger.warning(f"[DB1/DB3状态 poll #{poll_count}] 读取 DB1 失败: {err_db1}")
                db1_bytes = None

            if not success_db3:
                logger.warning(f"[DB1/DB3状态 poll #{poll_count}] 读取 DB3 失败: {err_db3}")
                db3_bytes = None

            # 2. 解析并缓存状态
            if db1_bytes or db3_bytes:
                source = "mock" if settings.use_mock_data else "plc"
                new_status = _build_status_cache(db1_bytes, db3_bytes, source, timestamp)
                
                # 检查状态是否变化
                if _has_status_changed(_latest_status, new_status):
                    _latest_status.update(new_status)
                    _status_changed = True
                    logger.info(f"[DB1/DB3状态 poll #{poll_count}] 状态已更新，标记为已变化")
                else:
                    _latest_status.update(new_status)
            
            # 3. 日志输出
            if settings.verbose_polling_log or poll_count % 10 == 0:
                summary = _latest_status.get("summary_by_db", {})
                db1_summary = summary.get("db1", {})
                db3_summary = summary.get("db3", {})
                logger.debug(f"[DB1/DB3状态 poll #{poll_count}] "
                      f"DB1: {db1_summary.get('normal', 0)}/{db1_summary.get('total', 0)} 正常 | "
                      f"DB3: {db3_summary.get('normal', 0)}/{db3_summary.get('total', 0)} 正常")
        
        except Exception as e:
            logger.error(f"[DB1/DB3状态 poll #{poll_count}] 轮询异常: {e}")
            traceback.print_exc()
        
        await asyncio.sleep(settings.poll_interval_db1_3)


def _task_exception_handler(task: asyncio.Task):
    """处理 Task 未捕获异常"""
    try:
        exc = task.exception()
        if exc:
            logger.critical(f"[DB1/DB3状态] Task {task.get_name()} 崩溃: {exc}", exc_info=exc)
    except asyncio.CancelledError:
        pass


async def start_status_polling():
    """启动 DB1/DB3 状态轮询服务"""
    global _status_poll_task, _is_status_running
    
    if _is_status_running:
        logger.warning("[DB1/DB3状态] 轮询服务已在运行")
        return
    
    _is_status_running = True
    
    if settings.use_mock_data:
        logger.info("[DB1/DB3状态] Mock模式启动")
    else:
        plc = get_plc_manager()
        success, err = plc.connect()
        if success:
            logger.info("[DB1/DB3状态] PLC 连接成功")
        else:
            logger.warning(f"[DB1/DB3状态] PLC 连接失败: {err}，将在轮询时重试")
    
    _status_poll_task = asyncio.create_task(_status_poll_loop(), name="status_poll_loop")
    _status_poll_task.add_done_callback(_task_exception_handler)
    
    mode_str = "Mock" if settings.use_mock_data else "PLC"
    logger.info(f"[DB1/DB3状态] 轮询服务已启动 ({mode_str}模式, 间隔: {settings.poll_interval_db1_3}s)")


async def stop_status_polling():
    """停止 DB1/DB3 状态轮询服务"""
    global _status_poll_task, _is_status_running
    
    _is_status_running = False
    
    if _status_poll_task:
        _status_poll_task.cancel()
        try:
            await _status_poll_task
        except asyncio.CancelledError:
            pass
    
    _status_poll_task = None
    
    logger.info("[DB1/DB3状态] 轮询服务已停止")


def get_latest_status() -> Dict[str, Any]:
    """获取最新的通信状态（优化：直接返回引用，避免频繁拷贝）"""
    return _latest_status


def is_status_polling_running() -> bool:
    """检查状态轮询服务是否在运行"""
    return _is_status_running


def has_status_changed() -> bool:
    """检查状态是否已变化（用于 WebSocket 推送判断）"""
    global _status_changed
    return _status_changed


def reset_status_changed():
    """重置状态变化标志（推送后调用）"""
    global _status_changed
    _status_changed = False


def get_status_polling_stats() -> Dict[str, Any]:
    """获取状态轮询统计信息"""
    return _status_stats.copy()


def get_latest_status_data() -> Optional[Dict[str, Any]]:
    """获取最新状态数据（用于 HTTP API）"""
    if not _latest_status:
        return None
    return _latest_status.copy()
