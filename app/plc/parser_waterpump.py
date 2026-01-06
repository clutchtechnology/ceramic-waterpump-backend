from typing import Dict, Any
import struct

# 电表字段定义 (字段名, 偏移量)
_METER_FIELDS = (
    ("Uab_0", 0), ("Uab_1", 4), ("Uab_2", 8),
    ("Ua_0", 12), ("Ua_1", 16), ("Ua_2", 20),
    ("I_0", 24), ("I_1", 28), ("I_2", 32),
    ("Pt", 36), ("Pa", 40), ("Pb", 44), ("Pc", 48),
    ("ImpEp", 52),
)


def parse_waterpump_db(raw_bytes: bytes) -> Dict[str, Dict[str, Any]]:
    """
    解析水泵房 DB2 块数据
    
    结构：
    - 6 个电表 (ElectricityMeter_0 ~ ElectricityMeter_5)，每个 56 字节
    - 1 个压力表 (Press_Data)，2 字节 (Word)
    
    大小端: Big Endian (S7-1200 标准)
    """
    
    result: Dict[str, Dict[str, Any]] = {}
    
    # ============================================================
    # 解析 6 个电表 (offset 0-336)
    # ============================================================
    for idx in range(6):
        meter_offset = idx * 56
        meter_id = f"meter_{idx+1}"
        
        # 确保有足够的字节
        if meter_offset + 56 > len(raw_bytes):
            result[meter_id] = {"error": "data insufficient"}
            continue
        
        try:
            # 提取电表数据段
            meter_data = raw_bytes[meter_offset : meter_offset + 56]
            
            # 批量解析 14 个 float 字段
            parsed = {
                name: struct.unpack_from(">f", meter_data, offset)[0]
                for name, offset in _METER_FIELDS
            }
            result[meter_id] = parsed
        
        except Exception as e:
            result[meter_id] = {"error": str(e)}
    
    # ============================================================
    # 解析压力表 (offset 336-338)
    # ============================================================
    pressure_offset = 336
    if pressure_offset + 2 <= len(raw_bytes):
        try:
            pressure_raw = struct.unpack(">H", raw_bytes[pressure_offset:pressure_offset+2])[0]
            result["pressure"] = {
                "pressure_raw": pressure_raw
            }
        except Exception as e:
            result["pressure"] = {"error": str(e)}
    else:
        result["pressure"] = {"error": "data insufficient"}
    
    return result

