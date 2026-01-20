# ============================================================
# 文件说明: s7_client.py - Siemens S7-1200 PLC 通信客户端
# ============================================================

import threading
from typing import Optional
import snap7
from config import get_settings


class S7Client:
    """Siemens S7-1200 PLC 客户端"""

    def __init__(self, ip: str, rack: int = 0, slot: int = 1, timeout_ms: int = 5000):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.timeout_ms = timeout_ms
        self.client: Optional[snap7.client.Client] = None

    def connect(self) -> bool:
        try:
            if self.client is None:
                self.client = snap7.client.Client()
            self.client.connect(self.ip, self.rack, self.slot)
            if not self.client.get_connected():
                raise ConnectionError(f"无法连接到PLC {self.ip}")
            return True
        except Exception as e:
            raise ConnectionError(f"PLC连接失败: {e}")

    def disconnect(self) -> None:
        if self.client and self.client.get_connected():
            self.client.disconnect()

    def read_db_block(self, db_number: int, start: int, size: int) -> bytes:
        if not self.client or not self.client.get_connected():
            raise ConnectionError("PLC未连接")
        try:
            return self.client.db_read(db_number, start, size)
        except Exception as e:
            raise Exception(f"读取DB{db_number}失败: {e}")

    def is_connected(self) -> bool:
        return self.client is not None and self.client.get_connected()


_s7_client: Optional[S7Client] = None
_s7_client_lock = threading.Lock()


def get_s7_client() -> S7Client:
    global _s7_client
    if _s7_client is None:
        with _s7_client_lock:
            if _s7_client is None:
                settings = get_settings()
                _s7_client = S7Client(
                    ip=settings.plc_ip,
                    rack=settings.plc_rack,
                    slot=settings.plc_slot,
                    timeout_ms=settings.plc_timeout,
                )
    return _s7_client


def reset_s7_client() -> None:
    global _s7_client
    if _s7_client is not None:
        try:
            _s7_client.disconnect()
        except Exception:
            pass
        _s7_client = None
