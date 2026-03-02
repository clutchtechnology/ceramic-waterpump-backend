# ============================================================
# 文件说明: parser_data_db2.py - DB2 数据块解析器
# ============================================================
# 功能: 解析 DB2 (Data_DB) 传感器实际数据
# 包含: 6个电表 + 1个压力表 (338字节, 振动在DB4)
# ============================================================

from typing import Dict, Any
from datetime import datetime

from app.plc.module_parser import ModuleParser
from app.plc.config_manager import PLCConfigManager


class DataDB2Parser:
    """DB2 数据块模块化解析器
    
    解析 DB2 (Data_DB) 中的传感器数据 (338字节):
    - 6 个电表 (ElectricityMeter, 6x56=336字节)
    - 1 个压力表 (PressureSensor, 2字节)
    
    振动传感器在 DB4 (228字节), 由 VibDB4Parser 解析
    """

    def __init__(self, device_config: str = "configs/config_waterpump_db2.yaml", module_config: str = "configs/plc_modules.yaml"):
        """初始化解析器
        
        Args:
            device_config: 设备配置文件路径
            module_config: 模块配置文件路径
        """
        self._config_manager = PLCConfigManager(device_config)
        self._module_parser = ModuleParser(module_config)

    def parse_db(self, raw_bytes: bytes, timestamp: str | None = None) -> Dict[str, Any]:
        """解析 DB2 数据块
        
        Args:
            raw_bytes: DB2 原始字节数据 (338 字节: 6电表 + 1压力)
            timestamp: 时间戳 (可选)
        
        Returns:
            解析结果字典，按设备 ID 组织
        """
        if timestamp is None:
            timestamp = datetime.utcnow().isoformat() + "Z"

        result: Dict[str, Any] = {}

        for device in self._config_manager.get_devices():
            device_id = device.get("device_id")
            modules = device.get("modules", [])
            if not device_id or not modules:
                continue

            device_modules: Dict[str, Any] = {}
            for module in modules:
                module_type = module.get("module_type")
                module_tag = module.get("module_tag") or module_type
                start_offset = int(module.get("start_offset", 0))

                if not module_type:
                    continue

                size = self._module_parser.get_module_size(module_type)
                if start_offset + size > len(raw_bytes):
                    device_modules[module_tag] = {
                        "module_type": module_type,
                        "module_tag": module_tag,
                        "fields": {"error": "data insufficient"}
                    }
                    continue

                module_data = raw_bytes[start_offset:start_offset + size]
                fields = self._module_parser.parse_module(module_type, module_data)

                device_modules[module_tag] = {
                    "module_type": module_type,
                    "module_tag": module_tag,
                    "description": module.get("description", ""),
                    "fields": fields
                }

            result[device_id] = {
                "device_id": device_id,
                "device_name": device.get("device_name", ""),
                "device_type": device.get("device_type", ""),
                "timestamp": timestamp,
                "modules": device_modules
            }

        return result


# 全局单例实例
_parser_instance: DataDB2Parser | None = None


def parse_data_db2(raw_bytes: bytes) -> Dict[str, Any]:
    """解析 DB2 数据块 (便捷函数)
    
    Args:
        raw_bytes: DB2 原始字节数据
    
    Returns:
        解析结果字典
    """
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DataDB2Parser()
    return _parser_instance.parse_db(raw_bytes)

