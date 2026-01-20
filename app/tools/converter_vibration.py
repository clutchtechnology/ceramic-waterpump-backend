from typing import Dict, Any
from .converter_base import BaseConverter


class VibrationConverter(BaseConverter):
    """振动传感器数据转换器

    对齐料仓 VibrationSelected 核心指标输出。
    数据已在解析阶段按 scale 缩放，这里只做字段归一与取整。
    """

    MODULE_TYPE = "VibrationSensor"

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return {
            "dx": round(self.get_field_value(raw_data, "DX", 0.0), 2),
            "dy": round(self.get_field_value(raw_data, "DY", 0.0), 2),
            "dz": round(self.get_field_value(raw_data, "DZ", 0.0), 2),
            "freq_x": round(self.get_field_value(raw_data, "HZX", 0.0), 1),
            "freq_y": round(self.get_field_value(raw_data, "HZY", 0.0), 1),
            "freq_z": round(self.get_field_value(raw_data, "HZZ", 0.0), 1),
            "acc_peak_x": round(self.get_field_value(raw_data, "KX", 0.0), 2),
            "acc_peak_y": round(self.get_field_value(raw_data, "KY", self.get_field_value(raw_data, "AAVGY", 0.0)), 2),
            "acc_peak_z": round(self.get_field_value(raw_data, "KZ", self.get_field_value(raw_data, "AAVGZ", 0.0)), 2),
            "vrms_x": round(self.get_field_value(raw_data, "VRMSX", 0.0), 2),
            "vrms_y": round(self.get_field_value(raw_data, "VRMSY", 0.0), 2),
            "vrms_z": round(self.get_field_value(raw_data, "VRMSZ", 0.0), 2),
        }
