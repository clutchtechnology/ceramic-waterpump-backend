"""
阈值存储 - 简单JSON文件存储 (带缓存)
奥卡姆剃刀: 不用数据库，JSON文件足够
"""
import json
import os
import threading
from typing import Dict, Any, Optional
from datetime import datetime

# 1, 阈值配置文件路径
_THRESHOLD_FILE = "data/thresholds.json"

# 2, 内存缓存 + 文件修改时间
_cache: Optional[Dict[str, Any]] = None
_cache_mtime: float = 0.0
_cache_lock = threading.Lock()

# 3, 确保data目录存在 (模块加载时执行一次)
os.makedirs("data", exist_ok=True)

# 4, 默认阈值配置
_DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "version": 2,
    "updated_at": None,
    # 4.1, 电流阈值 (6个泵)
    "current": {
        "pump_1": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_2": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_3": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_4": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_5": {"normal_max": 50.0, "warning_max": 80.0},
        "pump_6": {"normal_max": 50.0, "warning_max": 80.0},
    },
    # 4.2, 电压阈值 (6个泵, 相电压 220V 基准)
    "voltage": {
        "pump_1": {"normal_max": 230.0, "warning_max": 242.0},
        "pump_2": {"normal_max": 230.0, "warning_max": 242.0},
        "pump_3": {"normal_max": 230.0, "warning_max": 242.0},
        "pump_4": {"normal_max": 230.0, "warning_max": 242.0},
        "pump_5": {"normal_max": 230.0, "warning_max": 242.0},
        "pump_6": {"normal_max": 230.0, "warning_max": 242.0},
    },
    # 4.3, 压力阈值
    "pressure": {
        "high_alarm": 1.0,
        "low_alarm": 0.3,
    },
    # 4.4, 振动速度阈值 (mm/s)
    "speed": {
        "pump_1": {"normal_max": 3.5, "warning_max": 4.5},
        "pump_2": {"normal_max": 3.5, "warning_max": 4.5},
        "pump_3": {"normal_max": 3.5, "warning_max": 4.5},
        "pump_4": {"normal_max": 3.5, "warning_max": 4.5},
        "pump_5": {"normal_max": 3.5, "warning_max": 4.5},
        "pump_6": {"normal_max": 3.5, "warning_max": 4.5},
    },
    # 4.5, 振动位移阈值 (um)
    "displacement": {
        "pump_1": {"normal_max": 20.0, "warning_max": 30.0},
        "pump_2": {"normal_max": 20.0, "warning_max": 30.0},
        "pump_3": {"normal_max": 20.0, "warning_max": 30.0},
        "pump_4": {"normal_max": 20.0, "warning_max": 30.0},
        "pump_5": {"normal_max": 20.0, "warning_max": 30.0},
        "pump_6": {"normal_max": 20.0, "warning_max": 30.0},
    },
    # 4.6, 振动频率阈值 (Hz)
    "frequency": {
        "pump_1": {"normal_max": 50.0, "warning_max": 52.0},
        "pump_2": {"normal_max": 50.0, "warning_max": 52.0},
        "pump_3": {"normal_max": 50.0, "warning_max": 52.0},
        "pump_4": {"normal_max": 50.0, "warning_max": 52.0},
        "pump_5": {"normal_max": 50.0, "warning_max": 52.0},
        "pump_6": {"normal_max": 50.0, "warning_max": 52.0},
    },
    # 4.7, 功率阈值 (6个泵)
    "power": {
        "pump_1": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_2": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_3": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_4": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_5": {"normal_max": 30.0, "warning_max": 50.0},
        "pump_6": {"normal_max": 30.0, "warning_max": 50.0},
    },
    # 4.8, 振动综合阈值 (6个泵, 兼容旧版)
    "vibration": {
        "pump_1": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_2": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_3": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_4": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_5": {"normal_max": 1.0, "warning_max": 1.5},
        "pump_6": {"normal_max": 1.0, "warning_max": 1.5},
    },
}


def load_thresholds() -> Dict[str, Any]:
    """
    5, 加载阈值配置 (带文件修改时间缓存)
    
    缓存策略: 仅当文件修改时间变化时才重新读取
    """
    global _cache, _cache_mtime
    
    # 5.1, 检查文件是否存在
    if not os.path.exists(_THRESHOLD_FILE):
        return _DEFAULT_THRESHOLDS.copy()
    
    # 5.2, 检查文件修改时间
    try:
        current_mtime = os.path.getmtime(_THRESHOLD_FILE)
    except OSError:
        return _DEFAULT_THRESHOLDS.copy()
    
    # 5.3, 使用缓存 (线程安全)
    with _cache_lock:
        if _cache is not None and current_mtime == _cache_mtime:
            return _cache.copy()
        
        # 5.4, 重新加载文件
        try:
            with open(_THRESHOLD_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
                _cache_mtime = current_mtime
                return _cache.copy()
        except json.JSONDecodeError as e:
            print(f"[WARN] 阈值配置文件JSON解析错误: {e}")
            return _DEFAULT_THRESHOLDS.copy()
        except IOError as e:
            print(f"[WARN] 阈值配置文件读取失败: {e}")
            return _DEFAULT_THRESHOLDS.copy()


def save_thresholds(config: Dict[str, Any]) -> bool:
    """
    6, 保存阈值配置 (更新缓存)
    """
    global _cache, _cache_mtime
    
    try:
        config["updated_at"] = datetime.now().isoformat()
        with open(_THRESHOLD_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 6.1, 更新缓存
        with _cache_lock:
            _cache = config.copy()
            _cache_mtime = os.path.getmtime(_THRESHOLD_FILE)
        
        return True
    except Exception as e:
        print(f"保存阈值配置失败: {e}")
        return False


def get_pump_threshold(pump_id: int, param_type: str) -> Optional[Dict[str, float]]:
    """
    7, 获取单个泵的阈值
    
    Args:
        pump_id: 泵编号 (1-6)
        param_type: 参数类型 (current/power/vibration)
    
    Returns:
        {"normal_max": x, "warning_max": y} 或 None
    """
    # 7.1, 参数验证
    if not (1 <= pump_id <= 6):
        return None
    if param_type not in ("current", "voltage", "power", "speed", "displacement", "frequency", "vibration"):
        return None
    
    config = load_thresholds()
    key = f"pump_{pump_id}"
    
    if param_type in config and key in config[param_type]:
        return config[param_type][key]
    return None


def get_pressure_threshold() -> Dict[str, float]:
    """8, 获取压力阈值"""
    config = load_thresholds()
    return config.get("pressure", {"high_alarm": 1.0, "low_alarm": 0.3})



