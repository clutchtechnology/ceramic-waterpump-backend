# ============================================================
# 文件说明: plc_manager.py - PLC 长连接管理器
# ============================================================
# 功能:
#   1. 维护 PLC 长连接
#   2. 自动重连机制
#   3. 连接健康检查
#   4. 线程安全读写
# ============================================================

import atexit
import logging
import threading
import time
from typing import Optional, Tuple
from datetime import datetime, timezone

from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 尝试导入 snap7 (兼容 1.x 和 2.x)
try:
    import snap7
    from snap7.util import get_real, get_int
    
    # 尝试获取 PingTimeout 参数值
    _PingTimeout = 3  # 默认值
    
    try:
        # snap7 2.x: snap7.type.Parameter.PingTimeout
        if hasattr(snap7, 'type'):
            import snap7.type
            if hasattr(snap7.type, 'Parameter'):
                _PingTimeout = snap7.type.Parameter.PingTimeout
    except (ImportError, AttributeError):
        pass
    
    try:
        # snap7 1.x: snap7.types.PingTimeout
        if hasattr(snap7, 'types'):
            import snap7.types
            if hasattr(snap7.types, 'PingTimeout'):
                _PingTimeout = snap7.types.PingTimeout
    except (ImportError, AttributeError):
        pass
    
    SNAP7_AVAILABLE = True
    logger.info(f"snap7 已加载，PingTimeout 参数值: {_PingTimeout}")
    
except ImportError as e:
    SNAP7_AVAILABLE = False
    _PingTimeout = 3
    logger.warning(f"snap7 未安装，使用模拟模式: {e}")


class PLCManager:
    """PLC 长连接管理器
    
    注意: 请使用 get_plc_manager() 获取单例，不要直接实例化
    """
    
    def __init__(self):
        
        # 连接配置
        self._ip: str = settings.plc_ip
        self._rack: int = settings.plc_rack
        self._slot: int = settings.plc_slot
        self._timeout_ms: int = settings.plc_timeout
        
        # 连接状态
        self._client: Optional['snap7.client.Client'] = None
        self._connected: bool = False
        self._last_connect_time: Optional[datetime] = None
        self._last_read_time: Optional[datetime] = None
        self._connect_count: int = 0
        self._error_count: int = 0
        self._last_error: str = ""
        
        # 线程锁
        self._rw_lock = threading.Lock()
        
        # 重连配置
        self._reconnect_interval: float = 5.0  # 重连间隔（秒）
        self._max_reconnect_attempts: int = 3  # 最大重连次数
        self._health_check_interval: float = 30.0  # 健康检查间隔
        
        logger.info(f"PLC Manager 初始化: {self._ip}:{self._rack}/{self._slot}")
    
    def update_config(self, ip: str = None, rack: int = None, slot: int = None, timeout_ms: int = None):
        """更新 PLC 连接配置（需要重连生效）"""
        with self._rw_lock:
            if ip:
                self._ip = ip
            if rack is not None:
                self._rack = rack
            if slot is not None:
                self._slot = slot
            if timeout_ms is not None:
                self._timeout_ms = timeout_ms
            
            # 断开旧连接
            self._disconnect_internal()
            logger.info(f"PLC 配置已更新: {self._ip}:{self._rack}/{self._slot}")
    
    def connect(self) -> Tuple[bool, str]:
        """
        连接到 PLC（如果已连接则跳过）
        
        Returns:
            (success, error_message)
        """
        with self._rw_lock:
            return self._connect_internal()
    
    def _connect_internal(self) -> Tuple[bool, str]:
        """内部连接方法（不加锁）"""
        if self._connected and self._client:
            # 检查连接是否仍然有效
            try:
                if SNAP7_AVAILABLE and self._client.get_connected():
                    return (True, "")
            except Exception:
                pass
            self._connected = False
        
        if not SNAP7_AVAILABLE:
            # 模拟模式
            self._connected = True
            self._last_connect_time = datetime.now(timezone.utc)
            self._connect_count += 1
            return (True, "模拟模式")
        
        try:
            if self._client is None:
                self._client = snap7.client.Client()
            
            # 设置超时
            self._client.set_param(_PingTimeout, self._timeout_ms)
            
            # 连接
            self._client.connect(self._ip, self._rack, self._slot)
            
            if not self._client.get_connected():
                self._error_count += 1
                self._last_error = "连接后状态检查失败"
                return (False, self._last_error)
            
            self._connected = True
            self._last_connect_time = datetime.now(timezone.utc)
            self._connect_count += 1
            self._error_count = 0
            logger.info(f"PLC 已连接 ({self._ip}) [第 {self._connect_count} 次]")
            return (True, "")
        
        except Exception as e:
            self._connected = False
            self._error_count += 1
            self._last_error = str(e)
            logger.error(f"PLC 连接失败: {e}")
            return (False, self._last_error)
    
    def disconnect(self):
        """断开 PLC 连接"""
        with self._rw_lock:
            self._disconnect_internal()
    
    def _disconnect_internal(self):
        """内部断开方法（不加锁）"""
        if self._client:
            try:
                if SNAP7_AVAILABLE and self._client.get_connected():
                    self._client.disconnect()
                    # 等待 TCP 连接完全关闭
                    time.sleep(0.5)
            except Exception as e:
                logger.warning(f"断开连接时出错: {e}")
        self._connected = False
        logger.info("PLC 已断开")
    
    def read_db(self, db_number: int, start: int, size: int) -> Tuple[bool, bytes, str]:
        """
        读取 DB 块数据（长连接模式，不轻易断开）
        
        Args:
            db_number: DB 块号
            start: 起始偏移
            size: 读取字节数
        
        Returns:
            (success, data, error_message)
        """
        with self._rw_lock:
            # 确保连接
            if not self._connected:
                success, err = self._connect_internal()
                if not success:
                    return (False, b"", f"连接失败: {err}")
            
            # 模拟模式
            if not SNAP7_AVAILABLE:
                self._last_read_time = datetime.now(timezone.utc)
                return (True, bytes(size), "模拟数据")
            
            # 尝试读取数据（保持长连接，不断开）
            try:
                data = self._client.db_read(db_number, start, size)
                self._last_read_time = datetime.now(timezone.utc)
                self._error_count = 0
                return (True, bytes(data), "")
            
            except Exception as e:
                self._error_count += 1
                self._last_error = str(e)
                logger.warning(f"DB{db_number} 读取失败: {e}")
                
                # 只有在连续失败多次后才考虑重连
                if self._error_count >= 5:
                    logger.error(f"DB{db_number} 连续失败 {self._error_count} 次，尝试重连")
                    self._disconnect_internal()
                    time.sleep(2.0)  # 等待 PLC 释放连接
                    success, _ = self._connect_internal()
                    if not success:
                        logger.error(f"DB{db_number} 重连失败")
                        return (False, b"", self._last_error)
                    
                    # 重连后再试一次
                    try:
                        data = self._client.db_read(db_number, start, size)
                        self._last_read_time = datetime.now(timezone.utc)
                        self._error_count = 0
                        return (True, bytes(data), "")
                    except Exception as e2:
                        logger.error(f"DB{db_number} 重连后仍然失败: {e2}")
                        return (False, b"", str(e2))
                
                # 失败次数不多，直接返回错误，不断开连接
                return (False, b"", self._last_error)
    
    def is_connected(self) -> bool:
        """检查连接状态"""
        with self._rw_lock:
            if not self._connected:
                return False
            if not SNAP7_AVAILABLE:
                return True
            try:
                return self._client and self._client.get_connected()
            except Exception:
                return False
    
    def get_status(self) -> dict:
        """获取连接状态信息"""
        with self._rw_lock:
            return {
                "connected": self._connected,
                "ip": self._ip,
                "rack": self._rack,
                "slot": self._slot,
                "connect_count": self._connect_count,
                "error_count": self._error_count,
                "last_error": self._last_error,
                "last_connect_time": self._last_connect_time.isoformat() if self._last_connect_time else None,
                "last_read_time": self._last_read_time.isoformat() if self._last_read_time else None,
                "snap7_available": SNAP7_AVAILABLE
            }
    
    def health_check(self) -> Tuple[bool, str]:
        """
        健康检查（尝试读取少量数据）
        
        Returns:
            (healthy, message)
        """
        # 尝试读取 DB1 的前 4 字节
        success, _, err = self.read_db(1, 0, 4)
        if success:
            return (True, "PLC 响应正常")
        return (False, err)


# ============================================================
# 模块级单例 (线程安全)
# ============================================================
_plc_manager: Optional[PLCManager] = None
_plc_manager_lock = threading.Lock()


def get_plc_manager() -> PLCManager:
    """获取 PLC 管理器单例 (线程安全)"""
    global _plc_manager
    if _plc_manager is None:
        with _plc_manager_lock:
            if _plc_manager is None:
                _plc_manager = PLCManager()
    return _plc_manager


def close_plc_manager() -> None:
    """关闭 PLC 连接 (进程退出时调用)"""
    global _plc_manager
    if _plc_manager is not None:
        _plc_manager.disconnect()
        _plc_manager = None
        logger.info("PLC Manager 已清理")


# 注册退出清理
atexit.register(close_plc_manager)
