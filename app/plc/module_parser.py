# ============================================================
# 文件说明: module_parser.py - 模块化数据解析器
# ============================================================

import struct
import yaml
from typing import Dict, Any
from pathlib import Path


class ModuleParser:
    """模块化数据解析器 (基于 configs/plc_modules.yaml)"""

    def __init__(self, config_path: str = "configs/plc_modules.yaml"):
        self.config_path = Path(config_path)
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.load_module_configs()

    def load_module_configs(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"模块配置文件不存在: {self.config_path}")

        config = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        for module in config.get("plc_modules", []):
            self.modules[module["module_type"]] = module

    def _read_value(self, data: bytes, data_type: str, offset: int, bit_offset: int | None = None):
        if data_type == "Word":
            return struct.unpack(">H", data[offset:offset + 2])[0] if offset + 2 <= len(data) else 0
        if data_type == "DWord":
            return struct.unpack(">I", data[offset:offset + 4])[0] if offset + 4 <= len(data) else 0
        if data_type == "Int":
            return struct.unpack(">h", data[offset:offset + 2])[0] if offset + 2 <= len(data) else 0
        if data_type == "DInt":
            return struct.unpack(">i", data[offset:offset + 4])[0] if offset + 4 <= len(data) else 0
        if data_type == "Real":
            return struct.unpack(">f", data[offset:offset + 4])[0] if offset + 4 <= len(data) else 0
        if data_type == "Bool":
            if bit_offset is None:
                bit_offset = 0
            if offset >= len(data):
                return False
            return bool(data[offset] & (1 << bit_offset))
        return 0.0

    def parse_module(self, module_type: str, data: bytes) -> Dict[str, Any]:
        if module_type not in self.modules:
            raise ValueError(f"未找到模块配置: {module_type}")

        module_config = self.modules[module_type]
        result: Dict[str, Any] = {}

        for field in module_config.get("fields", []):
            offset = field.get("offset", field.get("byte_offset", 0))
            data_type = field.get("data_type", "Word")
            bit_offset = field.get("bit_offset")
            scale = field.get("scale", 1.0)

            raw_value = self._read_value(data, data_type, offset, bit_offset)
            value = raw_value * scale if isinstance(raw_value, (int, float)) else raw_value
            result[field["name"]] = value

        return result

    def get_module_size(self, module_type: str) -> int:
        if module_type not in self.modules:
            return 0
        return int(self.modules[module_type].get("size", 0))
