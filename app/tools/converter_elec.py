from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """三相电表数据转换器 (水泵房)

    计算规则:
    - 电流互感器变比默认 20
    - 电压: raw x 0.1 (V)
    - 电流: raw x 0.001 x 20 (A)
    - 功率: raw x 2 (kW)
    - 能耗: raw x 2 (kWh)
    
    输出字段 (8个):
    - Ua_0, Ua_1, Ua_2: A/B/C 相电压 (V)
    - I_0, I_1, I_2: A/B/C 相电流 (A)
    - Pt: 总有功功率 (kW)
    - ImpEp: 正向有功电能 (kWh)
    """

    MODULE_TYPE = "ElectricityMeter"

    SCALE_VOLTAGE = 0.1
    SCALE_CURRENT = 0.001
    SCALE_POWER = 2.0
    SCALE_ENERGY = 2.0

    # 默认变比 (用于电流计算)
    DEFAULT_RATIO = 20

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        ratio = kwargs.get("current_ratio", self.DEFAULT_RATIO)

        return {
            # 三相电压 (V)
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * self.SCALE_VOLTAGE, 1),
            "Ua_1": round(self.get_field_value(raw_data, "Ua_1", 0.0) * self.SCALE_VOLTAGE, 1),
            "Ua_2": round(self.get_field_value(raw_data, "Ua_2", 0.0) * self.SCALE_VOLTAGE, 1),
            # 三相电流 (A)
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * self.SCALE_CURRENT * ratio, 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0) * self.SCALE_CURRENT * ratio, 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0) * self.SCALE_CURRENT * ratio, 2),
            # 总有功功率 (kW)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * self.SCALE_POWER, 3),
            # 正向有功电能 (kWh)
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * self.SCALE_ENERGY, 3),
        }

