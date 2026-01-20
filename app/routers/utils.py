# ============================================================
# 文件说明: utils.py - 路由公共工具函数
# ============================================================

import logging
import random
from datetime import datetime
from typing import Dict, Any

from app.core.threshold_store import check_alarm, check_pressure_alarm, get_pump_threshold, get_pressure_threshold
from app.core.alarm_store import log_alarm

logger = logging.getLogger(__name__)


def parse_interval(interval: str) -> int:
    """
    解析间隔字符串为秒数
    
    支持格式: 5s, 1m, 5m, 1h, 1d 等
    
    返回: 秒数
    """
    interval = interval.lower().strip()
    
    if interval.endswith('s'):
        return int(interval[:-1])
    elif interval.endswith('m'):
        return int(interval[:-1]) * 60
    elif interval.endswith('h'):
        return int(interval[:-1]) * 3600
    elif interval.endswith('d'):
        return int(interval[:-1]) * 86400
    else:
        try:
            return int(interval)
        except ValueError:
            return 60


def check_mock_alarms(data: Dict[str, Any]):
    """
    Mock模式下检测报警并记录
    在每次返回实时数据时调用
    """
    # 检测6个水泵
    pumps = data.get('pumps', [])
    for pump in pumps:
        pump_id = pump.get('id', 0)
        device_id = f"pump_{pump_id}"
        
        # 检查电流
        current = pump.get('current', 0)
        current_alarm = check_alarm(pump_id, 'current', current)
        if current_alarm:
            threshold = get_pump_threshold(pump_id, 'current')
            threshold_val = threshold['warning_max'] if current_alarm == 'alarm' else threshold['normal_max']
            log_alarm(
                device_id=device_id,
                alarm_type='current_high',
                param_name='current',
                value=current,
                threshold=threshold_val,
                level=current_alarm,
            )
        
        # 检查功率
        power = pump.get('power', 0)
        power_alarm = check_alarm(pump_id, 'power', power)
        if power_alarm:
            threshold = get_pump_threshold(pump_id, 'power')
            threshold_val = threshold['warning_max'] if power_alarm == 'alarm' else threshold['normal_max']
            log_alarm(
                device_id=device_id,
                alarm_type='power_high',
                param_name='power',
                value=power,
                threshold=threshold_val,
                level=power_alarm,
            )

        # 检查振动
        vibration = pump.get('vibration', {})
        if isinstance(vibration, dict):
            vib_value = max(
                vibration.get('VX', 0.0),
                vibration.get('VY', 0.0),
                vibration.get('VZ', 0.0)
            )
            vib_alarm = check_alarm(pump_id, 'vibration', vib_value)
            if vib_alarm:
                threshold = get_pump_threshold(pump_id, 'vibration')
                threshold_val = threshold['warning_max'] if vib_alarm == 'alarm' else threshold['normal_max']
                log_alarm(
                    device_id=device_id,
                    alarm_type='vibration_high',
                    param_name='vibration',
                    value=vib_value,
                    threshold=threshold_val,
                    level=vib_alarm,
                )
    
    # 检测压力
    pressure_data = data.get('pressure', {})
    pressure = pressure_data.get('value', 0)
    pressure_alarm = check_pressure_alarm(pressure)
    
    if pressure_alarm:
        threshold = get_pressure_threshold()
        if pressure_alarm == 'alarm_high':
            log_alarm(
                device_id='pressure',
                alarm_type='pressure_high',
                param_name='pressure',
                value=pressure,
                threshold=threshold['high_alarm'],
                level='alarm',
            )
        elif pressure_alarm == 'alarm_low':
            log_alarm(
                device_id='pressure',
                alarm_type='pressure_low',
                param_name='pressure',
                value=pressure,
                threshold=threshold['low_alarm'],
                level='alarm',
            )


def generate_mock_status() -> Dict[str, Any]:
    """生成模拟的设备状态数据"""
    devices = []
    normal_count = 0
    error_count = 0
    
    # 6个水泵电表 + 1个压力表
    device_configs = [
        ("status_meter_1", "1号泵电表", "pump_meter_1", 0),
        ("status_meter_2", "2号泵电表", "pump_meter_2", 4),
        ("status_meter_3", "3号泵电表", "pump_meter_3", 8),
        ("status_meter_4", "4号泵电表", "pump_meter_4", 12),
        ("status_meter_5", "5号泵电表", "pump_meter_5", 16),
        ("status_meter_6", "6号泵电表", "pump_meter_6", 20),
        ("status_pressure", "压力表", "pump_pressure", 48),
    ]
    
    for device_id, name, data_id, offset in device_configs:
        # 95% 概率正常
        is_normal = random.random() < 0.95
        
        if is_normal:
            error = False
            status_code = 0
            normal_count += 1
        else:
            error = random.random() < 0.5
            status_code = random.choice([0x8001, 0x8002, 0x8003]) if error else 0
            error_count += 1
        
        devices.append({
            "device_id": device_id,
            "device_name": name,
            "data_device_id": data_id,
            "offset": offset,
            "enabled": True,
            "error": error,
            "status_code": status_code,
            "status_hex": f"{status_code:04X}",
            "is_normal": is_normal
        })
    
    return {
        "devices": devices,
        "summary": {
            "total": len(devices),
            "normal": normal_count,
            "error": error_count
        }
    }
