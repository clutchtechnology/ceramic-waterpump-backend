"""
Mock数据服务 - 生成模拟水泵和压力传感器数据
"""
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


class MockService:
    """Mock数据生成器"""
    
    @staticmethod
    def generate_pump_data(pump_id: int) -> Dict[str, Any]:
        """生成单个水泵的模拟数据"""
        # 基础值随机浮动
        voltage_base = 380.0 + random.uniform(-10, 10)
        current_base = 30.0 + random.uniform(-5, 5)
        power_base = voltage_base * current_base / 1000 * 0.9  # 功率 = V * A * 功率因数
        
        # 模拟异常情况（10%概率）
        if random.random() < 0.1:
            # 电压异常
            if random.random() < 0.5:
                voltage_base = random.choice([350.0, 410.0])  # 电压过低或过高
            else:
                current_base = 55.0  # 电流过高
        
        vibration = {
            "VX": round(random.uniform(0.3, 1.2), 2),
            "VY": round(random.uniform(0.3, 1.2), 2),
            "VZ": round(random.uniform(0.3, 1.2), 2),
            "TEMP": round(random.uniform(30.0, 45.0), 1),
        }

        return {
            'id': pump_id,
            'Ua_0': round(voltage_base, 1),
            'I_0': round(current_base, 1),
            'Pt': round(power_base, 1),
            'ImpEp': round(random.uniform(1000, 5000), 1),
            'status': MockService._calculate_status(voltage_base, current_base, power_base),
            'alarms': MockService._generate_alarms(voltage_base, current_base, power_base),
            'vibration': vibration,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def generate_pressure_data() -> Dict[str, Any]:
        """生成压力传感器模拟数据"""
        pressure_base = 0.5 + random.uniform(-0.1, 0.1)
        
        # 模拟异常情况（5%概率）
        if random.random() < 0.05:
            pressure_base = random.choice([0.15, 0.95])  # 压力过低或过高
        
        return {
            'value': round(pressure_base, 1),  # 保留1位小数
            'status': MockService._calculate_pressure_status(pressure_base),
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def generate_realtime_batch() -> Dict[str, Any]:
        """生成批量实时数据（6个水泵 + 1个压力传感器）"""
        pumps = [MockService.generate_pump_data(i) for i in range(1, 7)]
        pressure = MockService.generate_pressure_data()
        
        return {
            'pumps': pumps,
            'pressure': pressure,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def generate_history_data(
        pump_id: int,
        parameter: str,
        start_time: datetime,
        end_time: datetime,
        interval_seconds: int = 5
    ) -> List[Dict[str, Any]]:
        """
        生成历史数据
        
        参数：
        - pump_id: 水泵编号（压力表时为 None）
        - parameter: 参数名 (Ua_0/I_0/Pt/pressure)
        - start_time: 开始时间
        - end_time: 结束时间
        - interval_seconds: 数据点间隔（秒），默认5秒
        """
        data_points = []
        current_time = start_time
        
        # 确保间隔至少为1秒
        if interval_seconds < 1:
            interval_seconds = 1
        
        # 基础值 (字段名与 InfluxDB 一致)
        base_values = {
            'Ua_0': 380.0,
            'I_0': 30.0,
            'Pt': 10.5,
            'pressure': 0.5
        }
        
        base_value = base_values.get(parameter, 0)
        
        while current_time <= end_time:
            # 添加随机波动
            value = base_value + random.uniform(-base_value * 0.1, base_value * 0.1)
            
            data_points.append({
                'timestamp': current_time.isoformat(),
                'value': round(value, 1)  # 保留1位小数
            })
            
            current_time += timedelta(seconds=interval_seconds)
        
        return data_points
    
    @staticmethod
    def _calculate_status(voltage: float, current: float, power: float) -> str:
        """计算状态"""
        if voltage < 360 or voltage > 400 or current > 50 or power > 30:
            return 'alarm'
        elif voltage < 370 or voltage > 390 or current > 45:
            return 'warning'
        return 'normal'
    
    @staticmethod
    def _calculate_pressure_status(pressure: float) -> str:
        """计算压力状态"""
        if pressure < 0.2 or pressure > 1.0:
            return 'alarm'
        elif pressure < 0.3 or pressure > 0.8:
            return 'warning'
        return 'normal'
    
    @staticmethod
    def _generate_alarms(voltage: float, current: float, power: float) -> List[str]:
        """生成报警信息"""
        alarms = []
        
        if voltage < 360:
            alarms.append('电压过低')
        elif voltage > 400:
            alarms.append('电压过高')
        
        if current > 50:
            alarms.append('电流过载')
        
        if power > 30:
            alarms.append('功率超限')
        
        return alarms
