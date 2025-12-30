from typing import Dict, Any
import struct


def parse_waterpump_db(raw_bytes: bytes) -> Dict[str, Dict[str, Any]]:
    """
    解析水泵房 DB2 块数据
    
    结构：
    - 6 个电表 (ElectricityMeter_0 ~ ElectricityMeter_5)，每个 56 字节
      - Uab_0, Uab_1, Uab_2: 线电压 (Real)
      - Ua_0, Ua_1, Ua_2: 相电压 (Real)
      - I_0, I_1, I_2: 相电流 (Real)
      - Pt, Pa, Pb, Pc: 功率 (Real)
      - ImpEp: 电能 (Real)
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
            
            # 解析各字段 (big endian, 4字节 Real)
            parsed = {
                "Uab_0": struct.unpack(">f", meter_data[0:4])[0],
                "Uab_1": struct.unpack(">f", meter_data[4:8])[0],
                "Uab_2": struct.unpack(">f", meter_data[8:12])[0],
                
                "Ua_0": struct.unpack(">f", meter_data[12:16])[0],
                "Ua_1": struct.unpack(">f", meter_data[16:20])[0],
                "Ua_2": struct.unpack(">f", meter_data[20:24])[0],
                
                "I_0": struct.unpack(">f", meter_data[24:28])[0],
                "I_1": struct.unpack(">f", meter_data[28:32])[0],
                "I_2": struct.unpack(">f", meter_data[32:36])[0],
                
                "Pt": struct.unpack(">f", meter_data[36:40])[0],
                "Pa": struct.unpack(">f", meter_data[40:44])[0],
                "Pb": struct.unpack(">f", meter_data[44:48])[0],
                "Pc": struct.unpack(">f", meter_data[48:52])[0],
                
                "ImpEp": struct.unpack(">f", meter_data[52:56])[0],
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

