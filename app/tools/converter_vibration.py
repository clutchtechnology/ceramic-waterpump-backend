from typing import Dict, Any
from .converter_base import BaseConverter


class VibrationConverter(BaseConverter):
    """振动传感器数据转换器 - 水泵专用版
    
    只输出水泵振动监测的9个核心字段:
    - 速度幅值 (VX/VY/VZ): 振动强度（最重要）
    - 位移幅值 (DX/DY/DZ): 检测松动和不对中
    - 振动频率 (HZX/HZY/HZZ): 故障定位
    
    数据已在解析阶段按 scale 缩放，这里只做字段归一与取整。
    """

    MODULE_TYPE = "VibrationSensor"

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {
            # 1. 速度幅值 (mm/s) - 振动强度（最重要）
            "vx": round(self.get_field_value(raw_data, "VX", 0.0), 2),
            "vy": round(self.get_field_value(raw_data, "VY", 0.0), 2),
            "vz": round(self.get_field_value(raw_data, "VZ", 0.0), 2),
            
            # 2. 位移幅值 (um) - 检测松动/不对中
            "dx": round(self.get_field_value(raw_data, "DX", 0.0), 1),
            "dy": round(self.get_field_value(raw_data, "DY", 0.0), 1),
            "dz": round(self.get_field_value(raw_data, "DZ", 0.0), 1),
            
            # 3. 振动频率 (Hz) - 故障定位
            "hzx": round(self.get_field_value(raw_data, "HZX", 0.0), 1),
            "hzy": round(self.get_field_value(raw_data, "HZY", 0.0), 1),
            "hzz": round(self.get_field_value(raw_data, "HZZ", 0.0), 1),
        }
