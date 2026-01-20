# ============================================================
# 文件说明: parser_status_waterpump.py - DB1/DB3 状态数据解析器
# ============================================================

from typing import Dict, Any, List
import struct
import yaml
from pathlib import Path


def _read_status_field(data: bytes, field: Dict[str, Any], base_offset: int) -> Any:
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


def _parse_status_from_config(raw_bytes: bytes, config_path: str, only_enabled: bool = True) -> Dict[str, Any]:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
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
        for field in status_fields:
            parsed_fields[field["name"]] = _read_status_field(raw_bytes, field, offset)

        error = bool(parsed_fields.get("error", False))
        status_code = int(parsed_fields.get("status", 0))
        status_hex = f"{status_code:04X}"
        is_normal = (not error) and status_code == 0

        device_info = {
            "device_id": device.get("device_id", ""),
            "device_name": device.get("device_name", ""),
            "data_device_id": device.get("data_device_id"),
            "offset": offset,
            "enabled": enabled,
            "error": error,
            "status_code": status_code,
            "status_hex": status_hex,
            "is_normal": is_normal,
            **parsed_fields
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


def parse_status_waterpump_db(raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
    """解析 DB3 (DataState) 从站状态"""
    return _parse_status_from_config(raw_bytes, "configs/status_waterpump_db3.yaml", only_enabled)


def parse_status_waterpump_master_db(raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
    """解析 DB1 (MBValueTemp) 主站状态"""
    return _parse_status_from_config(raw_bytes, "configs/status_waterpump_db1.yaml", only_enabled)


def is_device_comm_ok(device_id: str, status_data: Dict[str, Any]) -> bool:
    for device in status_data.get("devices", []):
        if device["device_id"] == device_id:
            return device.get("is_normal", False)
    return False


def get_data_device_status(data_device_id: str, status_data: Dict[str, Any]) -> Dict[str, Any]:
    for device in status_data.get("devices", []):
        if device.get("data_device_id") == data_device_id:
            return device

    return {
        "error": True,
        "status_code": 0xFFFF,
        "status_hex": "FFFF",
        "is_normal": False,
        "not_found": True
    }


class StatusWaterpumpParser:
    """DB3 状态解析器包装类"""

    def parse_db(self, raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
        return parse_status_waterpump_db(raw_bytes, only_enabled)


class StatusWaterpumpMasterParser:
    """DB1 主站状态解析器包装类"""

    def parse_db(self, raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
        return parse_status_waterpump_master_db(raw_bytes, only_enabled)
