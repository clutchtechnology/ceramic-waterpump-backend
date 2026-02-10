# ============================================================
# 文件说明: parser_status_db1.py - DB1 主站状态数据解析器
# ============================================================
# 功能: 解析 DB1 (MBValueTemp) 主站指令块状态
# 包含: Done, Busy, Error, Status 字段
# ============================================================

from typing import Dict, Any, List
import struct
import yaml
from pathlib import Path

from config import get_resource_path


def _read_status_field(data: bytes, field: Dict[str, Any], base_offset: int) -> Any:
    """读取状态字段值
    
    Args:
        data: 原始字节数据
        field: 字段配置
        base_offset: 基础偏移量
    
    Returns:
        字段值
    """
    data_type = field.get("data_type", "Word")
    byte_offset = int(field.get("byte_offset", 0))
    bit_offset = field.get("bit_offset")
    offset = base_offset + byte_offset

    if data_type == "Bool":
        if offset >= len(data):
            return False
        bit_offset = 0 if bit_offset is None else int(bit_offset)
        return bool(data[offset] & (1 << bit_offset))
    
    if data_type == "Word":
        if offset + 2 > len(data):
            return 0
        return struct.unpack(">H", data[offset:offset + 2])[0]

    return 0


def parse_status_db1(raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
    """解析 DB1 (MBValueTemp) 主站状态
    
    Args:
        raw_bytes: DB1 原始字节数据 (80 字节)
        only_enabled: 是否只解析启用的设备
    
    Returns:
        解析结果字典，包含 devices 和 summary
    """
    cfg = yaml.safe_load(get_resource_path("configs/status_waterpump_db1.yaml").read_text(encoding="utf-8"))
    status_fields = cfg.get("status_module", {}).get("fields", [])
    devices_cfg = cfg.get("devices", [])

    devices: List[Dict[str, Any]] = []
    normal_count = 0
    error_count = 0

    for device in devices_cfg:
        enabled = device.get("enabled", True)
        if only_enabled and not enabled:
            continue

        offset = int(device.get("start_offset", 0))
        parsed_fields = {}
        
        # 解析所有字段
        for field in status_fields:
            parsed_fields[field["name"]] = _read_status_field(raw_bytes, field, offset)

        # 判断通信状态
        done = bool(parsed_fields.get("done", False))
        error = bool(parsed_fields.get("error", False))
        status_code = int(parsed_fields.get("status", 0))
        status_hex = f"{status_code:04X}"
        
        # 主站状态正常: done=True && error=False
        is_normal = done and (not error)

        device_info = {
            "device_id": device.get("device_id", ""),
            "device_name": device.get("device_name", ""),
            "plc_name": device.get("plc_name", ""),
            "offset": offset,
            "enabled": enabled,
            "done": done,
            "busy": bool(parsed_fields.get("busy", False)),
            "error": error,
            "status_code": status_code,
            "status_hex": status_hex,
            "is_normal": is_normal,
        }
        devices.append(device_info)

        if is_normal:
            normal_count += 1
        else:
            error_count += 1

    return {
        "devices": devices,
        "summary": {
            "total": len(devices),
            "normal": normal_count,
            "error": error_count
        }
    }


class StatusDB1Parser:
    """DB1 主站状态解析器包装类"""

    def parse_db(self, raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
        """解析 DB1 数据块
        
        Args:
            raw_bytes: DB1 原始字节数据
            only_enabled: 是否只解析启用的设备
        
        Returns:
            解析结果
        """
        return parse_status_db1(raw_bytes, only_enabled)

