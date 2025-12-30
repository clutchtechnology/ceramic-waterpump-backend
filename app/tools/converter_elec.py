from typing import Dict, Any
from .converter_base import BaseConverter


class ElectricityConverter(BaseConverter):
    """
    三相电表数据转换器
    
    PLC 中所有数据都是 Real 类型（4字节浮点数），直接对应物理值
    无需缩放系数（PLC中已是实际值）
    """
    MODULE_TYPE = "ElectricityMeter"

    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        转换电表数据：保留所有关键字段
        
        输入字段：
          - Uab_0, Uab_1, Uab_2: 线电压 (V)
          - Ua_0, Ua_1, Ua_2: 相电压 (V)
          - I_0, I_1, I_2: 相电流 (A)
          - Pt: 总有功功率 (kW)
          - Pa, Pb, Pc: 各相功率 (kW)
          - ImpEp: 正向有功电能 (kWh)
        
        输出字段：
          - 关键值: Pt, ImpEp, Ua_0, I_0 (用于实时展示)
          - 详细值: 所有字段 (用于历史分析)
        """
        return {
            # 线电压（三相）
            "Uab_0": round(self.get_field_value(raw_data, "Uab_0", 0.0), 1),
            "Uab_1": round(self.get_field_value(raw_data, "Uab_1", 0.0), 1),
            "Uab_2": round(self.get_field_value(raw_data, "Uab_2", 0.0), 1),
            
            # 相电压（三相）
            "Ua_0": round(self.get_field_value(raw_data, "Ua_0", 0.0), 1),
            "Ua_1": round(self.get_field_value(raw_data, "Ua_1", 0.0), 1),
            "Ua_2": round(self.get_field_value(raw_data, "Ua_2", 0.0), 1),
            
            # 相电流（三相）
            "I_0": round(self.get_field_value(raw_data, "I_0", 0.0), 2),
            "I_1": round(self.get_field_value(raw_data, "I_1", 0.0), 2),
            "I_2": round(self.get_field_value(raw_data, "I_2", 0.0), 2),
            
            # 功率
            "Pt": round(self.get_field_value(raw_data, "Pt", 0.0), 2),  # 总有功
            "Pa": round(self.get_field_value(raw_data, "Pa", 0.0), 2),  # A相
            "Pb": round(self.get_field_value(raw_data, "Pb", 0.0), 2),  # B相
            "Pc": round(self.get_field_value(raw_data, "Pc", 0.0), 2),  # C相
            
            # 电能
            "ImpEp": round(self.get_field_value(raw_data, "ImpEp", 0.0), 2),
        }

