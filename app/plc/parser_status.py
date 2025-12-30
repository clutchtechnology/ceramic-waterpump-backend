# ============================================================
# 文件说明: parser_status.py - DB1 状态数据解析器
# ============================================================
# 解析 Modbus 通信状态块 (MBValueTemp)
# 
# 每个设备状态占 4 字节:
#   - Byte 0, Bit 0: DONE (通信完成)
#   - Byte 0, Bit 1: BUSY (正在通信)
#   - Byte 0, Bit 2: ERROR (通信错误)
#   - Byte 2-3: STATUS (状态字, Word)
# ============================================================

from typing import Dict, Any, List
import struct


# 设备状态映射 (设备ID -> 偏移量)
DEVICE_STATUS_MAP = {
    "comm_module": 0,      # MB_COMM_LOAD
    "pump_meter_1": 4,     # DB_MASTER_ELEC_0
    "pump_meter_2": 8,     # DB_MASTER_ELEC_1
    "pump_meter_3": 12,    # DB_MASTER_ELEC_2
    "pump_meter_4": 16,    # DB_MASTER_ELEC_3
    "pump_meter_5": 20,    # DB_MASTER_ELEC_4
    "pump_meter_6": 24,    # DB_MASTER_ELEC_5
    "pump_pressure": 52,   # DB_MASTER_PRESS
}


def parse_device_status(raw_bytes: bytes, offset: int) -> Dict[str, Any]:
    """
    解析单个设备的通信状态
    
    Args:
        raw_bytes: DB1 原始字节数据
        offset: 设备状态的起始偏移量
    
    Returns:
        {
            "done": bool,      # 通信完成
            "busy": bool,      # 正在通信
            "error": bool,     # 通信错误
            "status": int,     # 状态字
            "comm_state": str  # 综合状态描述
        }
    """
    if offset + 4 > len(raw_bytes):
        return {
            "done": False,
            "busy": False,
            "error": True,
            "status": 0xFFFF,
            "comm_state": "data_insufficient"
        }
    
    try:
        # 读取状态字节
        status_byte = raw_bytes[offset]
        
        # 解析位字段
        done = bool(status_byte & 0x01)       # Bit 0
        busy = bool(status_byte & 0x02)       # Bit 1
        error = bool(status_byte & 0x04)      # Bit 2
        
        # 读取状态字 (Word, Big Endian)
        status_word = struct.unpack(">H", raw_bytes[offset+2:offset+4])[0]
        
        # 判断综合状态
        if error:
            comm_state = "error"
        elif busy:
            comm_state = "busy"
        elif done:
            comm_state = "ok"
        else:
            comm_state = "idle"
        
        return {
            "done": done,
            "busy": busy,
            "error": error,
            "status": status_word,
            "comm_state": comm_state
        }
    
    except Exception as e:
        return {
            "done": False,
            "busy": False,
            "error": True,
            "status": 0xFFFF,
            "comm_state": f"parse_error: {e}"
        }


def parse_status_db(raw_bytes: bytes) -> Dict[str, Dict[str, Any]]:
    """
    解析完整的 DB1 状态数据块
    
    Args:
        raw_bytes: DB1 原始字节数据 (56 字节)
    
    Returns:
        {
            "comm_module": { ... },
            "pump_meter_1": { ... },
            ...
            "pump_pressure": { ... },
            "summary": {
                "total_devices": int,
                "ok_count": int,
                "error_count": int,
                "busy_count": int
            }
        }
    """
    result: Dict[str, Dict[str, Any]] = {}
    
    ok_count = 0
    error_count = 0
    busy_count = 0
    
    for device_id, offset in DEVICE_STATUS_MAP.items():
        status = parse_device_status(raw_bytes, offset)
        result[device_id] = status
        
        # 统计
        if status["comm_state"] == "ok":
            ok_count += 1
        elif status["comm_state"] == "error":
            error_count += 1
        elif status["comm_state"] == "busy":
            busy_count += 1
    
    # 添加汇总信息
    result["summary"] = {
        "total_devices": len(DEVICE_STATUS_MAP),
        "ok_count": ok_count,
        "error_count": error_count,
        "busy_count": busy_count,
        "all_ok": error_count == 0
    }
    
    return result


def is_device_comm_ok(status_data: Dict[str, Any]) -> bool:
    """
    检查设备通信是否正常
    
    Args:
        status_data: parse_device_status 返回的状态数据
    
    Returns:
        True = 通信正常可读取数据
    """
    return status_data.get("done", False) and not status_data.get("error", True)
