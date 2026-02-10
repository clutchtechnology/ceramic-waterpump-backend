"""
阈值管理服务
功能：
1. 加载和保存阈值配置（thresholds.json）
2. 提供阈值查询接口
3. 验证阈值配置的合法性
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ThresholdService:
    """阈值管理服务"""
    
    # 阈值配置文件路径
    THRESHOLD_FILE = Path(__file__).parent.parent.parent / "data" / "thresholds.json"
    
    # 默认阈值配置
    DEFAULT_THRESHOLDS = {
        "version": 2,
        "updated_at": datetime.now().isoformat(),
        "current": {
            f"pump_{i}": {"normal_max": 50.0, "warning_max": 80.0}
            for i in range(1, 7)
        },
        "voltage": {
            f"pump_{i}": {"normal_max": 400.0, "warning_max": 420.0}
            for i in range(1, 7)
        },
        "pressure": {
            "high_alarm": 1.0,
            "low_alarm": 0.3
        },
        "speed": {
            f"pump_{i}": {"normal_max": 1450.0, "warning_max": 1500.0}
            for i in range(1, 7)
        },
        "displacement": {
            f"pump_{i}": {"normal_max": 0.5, "warning_max": 1.0}
            for i in range(1, 7)
        },
        "frequency": {
            f"pump_{i}": {"normal_max": 50.0, "warning_max": 52.0}
            for i in range(1, 7)
        }
    }
    
    def __init__(self):
        """初始化阈值服务"""
        self._thresholds: Dict[str, Any] = {}
        self._load_thresholds()
    
    def _load_thresholds(self) -> None:
        """从文件加载阈值配置"""
        try:
            if self.THRESHOLD_FILE.exists():
                with open(self.THRESHOLD_FILE, 'r', encoding='utf-8') as f:
                    self._thresholds = json.load(f)
                logger.info(f"阈值配置已加载，版本: {self._thresholds.get('version', 1)}")
            else:
                logger.warning("阈值配置文件不存在，使用默认配置")
                self._thresholds = self.DEFAULT_THRESHOLDS.copy()
                self._save_thresholds()
        except Exception as e:
            logger.error(f"加载阈值配置失败: {e}，使用默认配置")
            self._thresholds = self.DEFAULT_THRESHOLDS.copy()
    
    def _save_thresholds(self) -> bool:
        """保存阈值配置到文件"""
        try:
            # 确保目录存在
            self.THRESHOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # 更新时间戳
            self._thresholds["updated_at"] = datetime.now().isoformat()
            
            # 保存到文件
            with open(self.THRESHOLD_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._thresholds, f, indent=2, ensure_ascii=False)
            
            logger.info("阈值配置已保存")
            return True
        except Exception as e:
            logger.error(f"保存阈值配置失败: {e}")
            return False
    
    def get_all_thresholds(self) -> Dict[str, Any]:
        """获取所有阈值配置"""
        return self._thresholds.copy()
    
    def get_threshold(self, param_type: str, pump_id: Optional[int] = None) -> Optional[Dict[str, float]]:
        """
        获取指定参数的阈值
        
        Args:
            param_type: 参数类型 (current, voltage, pressure, speed, displacement, frequency)
            pump_id: 水泵编号 (1-6)，压力阈值不需要此参数
        
        Returns:
            阈值配置字典，如 {"normal_max": 50.0, "warning_max": 80.0}
        """
        if param_type not in self._thresholds:
            return None
        
        if param_type == "pressure":
            return self._thresholds["pressure"]
        
        if pump_id is None or pump_id < 1 or pump_id > 6:
            return None
        
        pump_key = f"pump_{pump_id}"
        return self._thresholds[param_type].get(pump_key)
    
    def update_thresholds(self, new_thresholds: Dict[str, Any]) -> bool:
        """
        更新阈值配置
        
        Args:
            new_thresholds: 新的阈值配置（前端传来的格式）
        
        Returns:
            是否更新成功
        """
        try:
            # 验证配置格式
            if not self._validate_thresholds(new_thresholds):
                logger.error("阈值配置格式验证失败")
                return False
            
            # 更新配置
            for param_type in ["current", "voltage", "speed", "displacement", "frequency"]:
                if param_type in new_thresholds:
                    self._thresholds[param_type] = new_thresholds[param_type]
            
            # 更新压力配置
            if "pressure" in new_thresholds:
                self._thresholds["pressure"] = new_thresholds["pressure"]
            
            # 保存到文件
            return self._save_thresholds()
        except Exception as e:
            logger.error(f"更新阈值配置失败: {e}")
            return False
    
    def _validate_thresholds(self, thresholds: Dict[str, Any]) -> bool:
        """
        验证阈值配置的合法性
        
        Args:
            thresholds: 待验证的阈值配置
        
        Returns:
            是否合法
        """
        try:
            # 验证水泵参数阈值
            for param_type in ["current", "voltage", "speed", "displacement", "frequency"]:
                if param_type in thresholds:
                    param_config = thresholds[param_type]
                    if not isinstance(param_config, dict):
                        return False
                    
                    # 验证每个水泵的配置
                    for pump_id in range(1, 7):
                        pump_key = f"pump_{pump_id}"
                        if pump_key in param_config:
                            pump_threshold = param_config[pump_key]
                            if not isinstance(pump_threshold, dict):
                                return False
                            
                            # 验证必需字段
                            if "normal_max" not in pump_threshold or "warning_max" not in pump_threshold:
                                return False
                            
                            # 验证数值类型
                            normal_max = pump_threshold["normal_max"]
                            warning_max = pump_threshold["warning_max"]
                            if not isinstance(normal_max, (int, float)) or not isinstance(warning_max, (int, float)):
                                return False
                            
                            # 验证逻辑关系：warning_max 应该 >= normal_max
                            if warning_max < normal_max:
                                logger.warning(f"{param_type} {pump_key}: warning_max < normal_max")
                                return False
            
            # 验证压力阈值
            if "pressure" in thresholds:
                pressure_config = thresholds["pressure"]
                if not isinstance(pressure_config, dict):
                    return False
                
                if "high_alarm" not in pressure_config or "low_alarm" not in pressure_config:
                    return False
                
                high_alarm = pressure_config["high_alarm"]
                low_alarm = pressure_config["low_alarm"]
                if not isinstance(high_alarm, (int, float)) or not isinstance(low_alarm, (int, float)):
                    return False
                
                # 验证逻辑关系：high_alarm 应该 > low_alarm
                if high_alarm <= low_alarm:
                    logger.warning("pressure: high_alarm <= low_alarm")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"验证阈值配置时出错: {e}")
            return False
    
    def reset_to_default(self) -> bool:
        """重置为默认阈值配置"""
        try:
            self._thresholds = self.DEFAULT_THRESHOLDS.copy()
            return self._save_thresholds()
        except Exception as e:
            logger.error(f"重置阈值配置失败: {e}")
            return False


# 全局单例
_threshold_service: Optional[ThresholdService] = None

def get_threshold_service() -> ThresholdService:
    """获取阈值服务单例"""
    global _threshold_service
    if _threshold_service is None:
        _threshold_service = ThresholdService()
    return _threshold_service

