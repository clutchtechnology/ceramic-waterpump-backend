from typing import Dict, Any
from .converter_base import BaseConverter


class PressureConverter(BaseConverter):
    """
    压力传感器数据转换器
    
    PLC 中压力值为 Word (0-65535)，实际值 = raw * 0.01 (kPa)
    """
    MODULE_TYPE = "PressureSensor"

    # 压力转换系数: PLC 中以 0.01kPa 为单位，1 = 0.01kPa
    DEFAULT_SCALE = 0.01

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换压力数据
        
        输入: pressure_raw (Word, 范围 0-65535)
        输出: pressure_kpa (单位 kPa，精度 0.001)
        
        示例: raw=10132 → pressure_kpa=101.32 kPa
        """
        scale = kwargs.get("scale", self.DEFAULT_SCALE)
        raw_value = self.get_field_value(raw_data, "pressure_raw", 0.0)
        
        return {
            "pressure_kpa": round(raw_value * scale, 2)
        }

