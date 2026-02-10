from typing import Dict, Any
from datetime import datetime

from app.plc.module_parser import ModuleParser
from app.plc.config_manager import PLCConfigManager


class WaterpumpParser:
    """水泵房 DB2 模块化解析器"""

    def __init__(self, device_config: str = "configs/config_waterpump_db2.yaml", module_config: str = "configs/plc_modules.yaml"):
        self._config_manager = PLCConfigManager(device_config)
        self._module_parser = ModuleParser(module_config)

    def parse_db(self, raw_bytes: bytes, timestamp: str | None = None) -> Dict[str, Any]:
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
                
                # 1. 安全获取 start_offset，处理 None 值
                start_offset_raw = module.get("start_offset", 0)
                if start_offset_raw is None:
                    start_offset_raw = 0
                
                try:
                    start_offset = int(start_offset_raw)
                except (TypeError, ValueError) as e:
                    device_modules[module_tag] = {
                        "module_type": module_type,
                        "module_tag": module_tag,
                        "fields": {"error": f"invalid start_offset: {start_offset_raw}"}
                    }
                    continue

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


_parser_instance: WaterpumpParser | None = None


def parse_waterpump_db(raw_bytes: bytes) -> Dict[str, Any]:
    """兼容旧调用：解析 DB2 数据并返回设备字典"""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = WaterpumpParser()
    return _parser_instance.parse_db(raw_bytes)

