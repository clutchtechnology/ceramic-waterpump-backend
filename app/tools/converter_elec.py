from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """三相电表数据转换器 (水泵房)

    计算规则参考磨料车间/回转窑：
    - 电流互感器变比默认 20（可覆盖）
    - 电压: raw × 0.1 (V)
    - 电流: raw × 0.001 × ratio (A)
    - 功率: raw × 0.0001 × ratio (kW)
    - 电能: raw × ratio (kWh)
    """

    MODULE_TYPE = "ElectricityMeter"

    SCALE_VOLTAGE = 0.1
    SCALE_CURRENT = 0.001
    SCALE_POWER = 0.0001

    # 默认变比 (与料仓/风机一致，可通过 current_ratio 覆盖)
    DEFAULT_RATIO = 20

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        ratio = kwargs.get("current_ratio", self.DEFAULT_RATIO)

        return {
            # 电压（三相，仅保留A相快捷字段）
            "Uab_0": round(self.get_field_value(raw_data, "Uab_0", 0.0) * self.SCALE_VOLTAGE, 1),
            "Uab_1": round(self.get_field_value(raw_data, "Uab_1", 0.0) * self.SCALE_VOLTAGE, 1),
            "Uab_2": round(self.get_field_value(raw_data, "Uab_2", 0.0) * self.SCALE_VOLTAGE, 1),
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0) * self.SCALE_VOLTAGE, 1),
            "Ua_1": round(self.get_field_value(raw_data, "Ua_1", 0.0) * self.SCALE_VOLTAGE, 1),
            "Ua_2": round(self.get_field_value(raw_data, "Ua_2", 0.0) * self.SCALE_VOLTAGE, 1),

            # 电流 (乘变比)
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0) * self.SCALE_CURRENT * ratio, 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0) * self.SCALE_CURRENT * ratio, 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0) * self.SCALE_CURRENT * ratio, 2),

            # 功率 (乘变比)
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0) * self.SCALE_POWER * ratio, 3),
            "Pa": round(self.get_field_value(raw_data, "Pa", 0.0) * self.SCALE_POWER * ratio, 3),
            "Pb": round(self.get_field_value(raw_data, "Pb", 0.0) * self.SCALE_POWER * ratio, 3),
            "Pc": round(self.get_field_value(raw_data, "Pc", 0.0) * self.SCALE_POWER * ratio, 3),

            # 电能 (乘变比)
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0) * ratio, 3),

            # 统一字段
            "voltage": round(self.get_field_value(raw_data, "Ua_0", 0.0) * self.SCALE_VOLTAGE, 1),
            "current": round(self.get_field_value(raw_data, "I_0", 0.0) * self.SCALE_CURRENT * ratio, 2),
            "power": round(self.get_field_value(raw_data, "Pt", 0.0) * self.SCALE_POWER * ratio, 3),
        }

