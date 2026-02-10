from typing import Dict, Any
from .converter_base import BaseConverter


class PressureConverter(BaseConverter):
    """
    压力传感器数据转换器
    
    计算公式: 压力 = 原始值 × 1.0 (直接使用原始值)
    单位: kPa
    
    PLC 中压力值为 Word (0-65535)，原始值就是 kPa
    """
    MODULE_TYPE = "PressureSensor"

    # 压力转换系数: 直接使用原始值
    DEFAULT_SCALE = 1.0

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换压力数据

        输入: pressure_raw (Word, 范围 0-65535)
        输出:
            - pressure_kpa (单位 kPa)
            - pressure (单位 kPa，与 pressure_kpa 相同)

        示例: raw=505 → pressure_kpa=505.0 kPa → pressure=505.0 kPa
        """
        scale = kwargs.get("scale", self.DEFAULT_SCALE)
        raw_value = self.get_field_value(raw_data, "pressure_raw", 0.0)

        pressure_kpa = raw_value * scale

        return {
            "pressure_kpa": round(pressure_kpa, 1),
            "pressure": round(pressure_kpa, 1),
        }

