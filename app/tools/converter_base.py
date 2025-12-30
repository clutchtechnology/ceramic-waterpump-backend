from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseConverter(ABC):
    MODULE_TYPE: str = ""
    OUTPUT_FIELDS: Dict[str, Dict[str, str]] = {}

    @abstractmethod
    def convert(self, raw_data: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        pass

    def get_field_value(self, raw_data: Dict[str, Any], field_name: str, default: Any = 0.0):
        if field_name in raw_data:
            info = raw_data[field_name]
            if isinstance(info, dict):
                return info.get("value", default)
            return info
        return default
