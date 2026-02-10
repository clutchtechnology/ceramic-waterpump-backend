# ============================================================
# 文件说明: config_manager.py - 水泵房配置管理器
# ============================================================

import yaml
from pathlib import Path
from typing import Dict, Any, List

from config import get_resource_path


class PLCConfigManager:
    """读取设备配置文件并提供设备配置"""

    def __init__(self, config_path: str = "configs/config_waterpump_db2.yaml"):
        self.config_path = get_resource_path(config_path)
        self._devices: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            raise FileNotFoundError(f"设备配置不存在: {self.config_path}")
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self._devices = raw.get("devices", []) if isinstance(raw, dict) else []

    def get_devices(self) -> List[Dict[str, Any]]:
        return self._devices
