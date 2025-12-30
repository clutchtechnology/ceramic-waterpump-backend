"""
阈值存储 - 简单JSON文件存储
奥卡姆剃刀: 不用数据库，JSON文件足够
"""
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime

# 阈值配置文件路径
_THRESHOLD_FILE = "data/thresholds.json"

# 默认阈值配置
_DEFAULT_THRESHOLDS = {
    "version": 1,
    "updated_at": None,
    # 电流阈值 (6个泵)
    "current": {
        "pump_1": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_2": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_3": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_4": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_5": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_6": {"normal_max": 50.0, "warning_max": 80.0},
    },
    # 功率阈值 (6个泵)
    "power": {
        "pump_1": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_2": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_3": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_4": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_5": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_6": {"normal_max": 30.0, "warning_max": 50.0},
    },
    # 压力阈值
    "pressure": {
        "high_alarm": 1.0,
        "low_alarm": 0.3,
    },
    # 振动阈值 (6个泵)
    "vibration": {
        "pump_1": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_2": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_3": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_4": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_5": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_6": {"normal_max": 1.0, "warning_max": 1.5},
    },
}


def _ensure_data_dir():
    """确保data目录存在"""
    os.makedirs("data", exist_ok=True)


def load_thresholds() -> Dict[str, Any]:
    """加载阈值配置"""
    _ensure_data_dir()
    
    if os.path.exists(_THRESHOLD_FILE):
        try:
            with open(_THRESHOLD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    
    return _DEFAULT_THRESHOLDS.copy()


def save_thresholds(config: Dict[str, Any]) -> bool:
    """保存阈值配置"""
    _ensure_data_dir()
    
    try:
        config["updated_at"] = datetime.now().isoformat()
        with open(_THRESHOLD_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"保存阈值配置失败: {e}")
        return False


def get_pump_threshold(pump_id: int, param_type: str) -> Optional[Dict[str, float]]:
    """
    获取单个泵的阈值
    
    Args:
        pump_id: 泵编号 (1-6)
        param_type: 参数类型 (current/power/vibration)
    
    Returns:
        {"normal_max": x, "warning_max": y} 或 None
    """
    config = load_thresholds()
    key = f"pump_{pump_id}"
    
    if param_type in config and key in config[param_type]:
        return config[param_type][key]
    return None


def get_pressure_threshold() -> Dict[str, float]:
    """获取压力阈值"""
    config = load_thresholds()
    return config.get("pressure", {"high_alarm": 1.0, "low_alarm": 0.3})


def check_alarm(pump_id: int, param_type: str, value: float) -> Optional[str]:
    """
    检查是否触发报警
    
    Returns:
        None: 正常
        "warning": 警告
        "alarm": 报警
    """
    threshold = get_pump_threshold(pump_id, param_type)
    if threshold is None:
        return None
    
    if value > threshold["warning_max"]:
        return "alarm"
    elif value > threshold["normal_max"]:
        return "warning"
    return None


def check_pressure_alarm(value: float) -> Optional[str]:
    """检查压力报警"""
    threshold = get_pressure_threshold()
    
    if value > threshold["high_alarm"]:
        return "alarm_high"
    elif value < threshold["low_alarm"]:
        return "alarm_low"
    return None
