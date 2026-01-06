# ============================================================
# 文件说明: parser_status_waterpump.py - DB3 状态数据解析器
# ============================================================
# 解析水泵房 DataState 数据块 (DB3)
# 
# 每个设备状态占 4 字节:
#   - Byte 0, Bit 0: Error (通信错误)
#   - Byte 2-3: Status (状态字, Word, Big Endian)
# ============================================================

from typing import Dict, Any, List
import struct


# 设备状态映射 (设备ID -> 偏移量)
# 根据 PLC 图片: 12个电表 + 1个压力表
DEVICE_STATUS_MAP = {
    "status_meter_1": {"offset": 0, "name": "1号泵电表", "data_id": "pump_meter_1", "enabled": True},
    "status_meter_2": {"offset": 4, "name": "2号泵电表", "data_id": "pump_meter_2", "enabled": True},
    "status_meter_3": {"offset": 8, "name": "3号泵电表", "data_id": "pump_meter_3", "enabled": True},
    "status_meter_4": {"offset": 12, "name": "4号泵电表", "data_id": "pump_meter_4", "enabled": True},
    "status_meter_5": {"offset": 16, "name": "5号泵电表", "data_id": "pump_meter_5", "enabled": True},
    "status_meter_6": {"offset": 20, "name": "6号泵电表", "data_id": "pump_meter_6", "enabled": True},
    "status_meter_7": {"offset": 24, "name": "预留电表7", "data_id": None, "enabled": False},
    "status_meter_8": {"offset": 28, "name": "预留电表8", "data_id": None, "enabled": False},
    "status_meter_9": {"offset": 32, "name": "预留电表9", "data_id": None, "enabled": False},
    "status_meter_10": {"offset": 36, "name": "预留电表10", "data_id": None, "enabled": False},
    "status_meter_11": {"offset": 40, "name": "预留电表11", "data_id": None, "enabled": False},
    "status_meter_12": {"offset": 44, "name": "预留电表12", "data_id": None, "enabled": False},
    "status_pressure": {"offset": 48, "name": "压力表", "data_id": "pump_pressure", "enabled": True},
}


def parse_device_status(raw_bytes: bytes, offset: int) -> Dict[str, Any]:
    """
    解析单个设备的通信状态
    
    Args:
        raw_bytes: DB3 原始字节数据
        offset: 设备状态的起始偏移量
    
    Returns:
        {
            "error": bool,        # 通信错误
            "status_code": int,   # 状态字 (原始值)
            "status_hex": str,    # 状态字 (十六进制)
            "is_normal": bool     # 是否正常 (无错误且状态为0)
        }
    """
    if offset + 4 > len(raw_bytes):
        return {
            "error": True,
            "status_code": 0xFFFF,
            "status_hex": "FFFF",
            "is_normal": False,
            "parse_error": "data_insufficient"
        }
    
    try:
        # 读取 Error 位 (Byte 0, Bit 0)
        error_byte = raw_bytes[offset]
        error = bool(error_byte & 0x01)
        
        # 读取状态字 (Word, Byte 2-3, Big Endian)
        status_code = struct.unpack(">H", raw_bytes[offset+2:offset+4])[0]
        status_hex = f"{status_code:04X}"
        
        # 正常 = 无错误 且 状态码为 0
        is_normal = (not error) and (status_code == 0)
        
        return {
            "error": error,
            "status_code": status_code,
            "status_hex": status_hex,
            "is_normal": is_normal
        }
    
    except Exception as e:
        return {
            "error": True,
            "status_code": 0xFFFF,
            "status_hex": "FFFF",
            "is_normal": False,
            "parse_error": str(e)
        }


def parse_status_waterpump_db(raw_bytes: bytes, only_enabled: bool = True) -> Dict[str, Any]:
    """
    解析完整的 DB3 状态数据块
    
    Args:
        raw_bytes: DB3 原始字节数据 (52 字节)
        only_enabled: 是否只返回启用的设备
    
    Returns:
        {
            "devices": [
                {
                    "device_id": str,
                    "device_name": str,
                    "data_device_id": str | None,
                    "offset": int,
                    "error": bool,
                    "status_code": int,
                    "status_hex": str,
                    "is_normal": bool
                },
                ...
            ],
            "summary": {
                "total": int,
                "normal": int,
                "error": int
            }
        }
    """
    devices: List[Dict[str, Any]] = []
    normal_count = 0
    error_count = 0
    
    for device_id, config in DEVICE_STATUS_MAP.items():
        # 跳过禁用的设备
        if only_enabled and not config["enabled"]:
            continue
        
        status = parse_device_status(raw_bytes, config["offset"])
        
        device_info = {
            "device_id": device_id,
            "device_name": config["name"],
            "data_device_id": config["data_id"],
            "offset": config["offset"],
            "enabled": config["enabled"],
            **status
        }
        devices.append(device_info)
        
        # 统计
        if status["is_normal"]:
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


def is_device_comm_ok(device_id: str, status_data: Dict[str, Any]) -> bool:
    """
    检查指定设备通信是否正常
    
    Args:
        device_id: 设备ID (如 "status_meter_1")
        status_data: parse_status_waterpump_db 的返回结果
    
    Returns:
        bool: 通信是否正常
    """
    for device in status_data.get("devices", []):
        if device["device_id"] == device_id:
            return device.get("is_normal", False)
    return False


def get_data_device_status(data_device_id: str, status_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据数据设备ID获取对应的状态
    
    Args:
        data_device_id: 数据设备ID (如 "pump_meter_1")
        status_data: parse_status_waterpump_db 的返回结果
    
    Returns:
        设备状态信息，如果未找到返回默认值
    """
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
