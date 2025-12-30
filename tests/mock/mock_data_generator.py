# ============================================================
# 文件说明: mock_data_generator.py - 水泵房模拟数据生成器
# ============================================================
# 功能:
# 1. 生成符合PLC DB块结构的原始数据
# 2. 模拟水泵房电表、压力传感器、设备状态
# 3. 支持 DB1(设备状态) 和 DB2(传感器数据)
# ============================================================

import struct
import random
import math
from datetime import datetime
from typing import Dict, Tuple


class MockDataGenerator:
    """水泵房模拟数据生成器
    
    生成符合PLC DB块结构的原始字节数据
    """
    
    def __init__(self):
        # 基础值 (用于模拟真实波动)
        self._base_values = {
            # 6个水泵电表基础值
            'pump_voltage': [380.0, 380.0, 380.0, 380.0, 380.0, 380.0],
            'pump_current': [15.0, 18.0, 12.0, 20.0, 16.0, 14.0],
            'pump_power': [8.5, 10.2, 6.8, 12.0, 9.5, 8.0],
            'pump_energy': [1250.0, 1580.0, 980.0, 2100.0, 1420.0, 1180.0],
            
            # 压力传感器基础值
            'pressure': 2.5,  # MPa
        }
        
        # 时间累计值 (用于生成连续变化的数据)
        self._tick = 0
        
        # 能耗累计值
        self._energy_accumulator = [0.0] * 6
        
        # 设备运行状态 (模拟开关)
        self._device_running = [True, True, True, True, False, False]
    
    def tick(self):
        """时间前进一步 (每次轮询调用)"""
        self._tick += 1
        
        # 每100次轮询，随机切换一个设备状态
        if self._tick % 100 == 0:
            idx = random.randint(0, 5)
            self._device_running[idx] = not self._device_running[idx]
    
    def _add_noise(self, base: float, noise_range: float = 0.05) -> float:
        """添加随机波动"""
        noise = random.uniform(-noise_range, noise_range)
        return base * (1 + noise)
    
    def _add_sine_wave(self, base: float, amplitude: float = 0.1, period: int = 60) -> float:
        """添加正弦波动 (模拟周期性变化)"""
        wave = math.sin(2 * math.pi * self._tick / period) * amplitude
        return base * (1 + wave)
    
    # ============================================================
    # DB1: 设备状态数据 (56 字节)
    # ============================================================
    def generate_db1_status(self) -> bytes:
        """生成 DB1 设备状态数据 (56 字节)
        
        每个设备状态块: 4 字节
        - Byte 0: 状态位 (DONE=0x01, BUSY=0x02, ERROR=0x04)
        - Byte 1: 保留
        - Byte 2-3: 错误码 (Word)
        
        设备映射 (参考 parser_status.py):
        - waterpump_1: 偏移 0
        - waterpump_2: 偏移 4
        - waterpump_3: 偏移 8
        - waterpump_4: 偏移 12
        - waterpump_5: 偏移 16
        - waterpump_6: 偏移 20
        """
        data = bytearray(56)
        
        device_offsets = [0, 4, 8, 12, 16, 20]
        
        for idx, offset in enumerate(device_offsets):
            if self._device_running[idx]:
                # 95% 正常运行, 3% 忙碌, 2% 错误
                r = random.random()
                if r < 0.95:
                    data[offset] = 0x01  # DONE
                    data[offset+2:offset+4] = struct.pack(">H", 0)
                elif r < 0.98:
                    data[offset] = 0x02  # BUSY
                    data[offset+2:offset+4] = struct.pack(">H", 0)
                else:
                    data[offset] = 0x04  # ERROR
                    data[offset+2:offset+4] = struct.pack(">H", 0x8001)
            else:
                # 设备停止
                data[offset] = 0x00
                data[offset+2:offset+4] = struct.pack(">H", 0)
        
        return bytes(data)
    
    # ============================================================
    # DB2: 传感器数据 (338 字节)
    # ============================================================
    def generate_db2_sensors(self) -> bytes:
        """生成 DB2 传感器数据 (338 字节)
        
        结构:
        - 6 个水泵电表: 每个 56 字节 (14 个 REAL 值)
        - 压力传感器: 2 字节 (Word)
        
        电表字段 (每个 56 字节):
        - Uab, Ubc, Uca (线电压, 3x4=12B)
        - Ua, Ub, Uc (相电压, 3x4=12B)
        - Ia, Ib, Ic (电流, 3x4=12B)
        - Pt (总功率, 4B)
        - Pa, Pb, Pc (分相功率, 3x4=12B)
        - ImpEp (累计电量, 4B)
        """
        data = bytearray(338)
        
        for idx in range(6):
            offset = idx * 56
            
            if self._device_running[idx]:
                # 设备运行中，生成真实数据
                base_v = self._base_values['pump_voltage'][idx]
                base_i = self._base_values['pump_current'][idx]
                base_p = self._base_values['pump_power'][idx]
                base_e = self._base_values['pump_energy'][idx]
                
                # 添加波动
                line_voltage = self._add_sine_wave(base_v, amplitude=0.02, period=120)
                phase_voltage = line_voltage / 1.732
                current = self._add_sine_wave(base_i, amplitude=0.15, period=30)
                power = self._add_sine_wave(base_p, amplitude=0.1, period=45)
                
                # 累计能耗
                self._energy_accumulator[idx] += power * (5 / 3600)  # 5秒轮询
                energy = base_e + self._energy_accumulator[idx]
                
                # 打包电表数据 (14 个 REAL, 大端)
                values = [
                    line_voltage + random.uniform(-2, 2),      # Uab
                    line_voltage + random.uniform(-2, 2),      # Ubc
                    line_voltage + random.uniform(-2, 2),      # Uca
                    phase_voltage + random.uniform(-1, 1),     # Ua
                    phase_voltage + random.uniform(-1, 1),     # Ub
                    phase_voltage + random.uniform(-1, 1),     # Uc
                    current + random.uniform(-0.5, 0.5),       # Ia
                    current + random.uniform(-0.5, 0.5),       # Ib
                    current + random.uniform(-0.5, 0.5),       # Ic
                    power,                                      # Pt
                    power / 3 + random.uniform(-0.1, 0.1),     # Pa
                    power / 3 + random.uniform(-0.1, 0.1),     # Pb
                    power / 3 + random.uniform(-0.1, 0.1),     # Pc
                    energy,                                     # ImpEp
                ]
            else:
                # 设备停止，数据为0
                values = [0.0] * 14
            
            for i, val in enumerate(values):
                data[offset + i*4 : offset + i*4 + 4] = struct.pack(">f", val)
        
        # 压力传感器 (偏移 336, 2字节)
        pressure = self._add_sine_wave(
            self._base_values['pressure'],
            amplitude=0.08,
            period=60
        )
        # 假设压力传感器原始值范围 0-10000 对应 0-10 MPa
        pressure_raw = int(pressure * 1000)
        data[336:338] = struct.pack(">H", min(65535, max(0, pressure_raw)))
        
        return bytes(data)
    
    # ============================================================
    # 生成所有 DB 数据
    # ============================================================
    def generate_all_db_data(self) -> Dict[int, bytes]:
        """生成所有 DB 块的模拟数据
        
        Returns:
            {db_number: raw_bytes}
        """
        self.tick()
        
        return {
            1: self.generate_db1_status(),
            2: self.generate_db2_sensors(),
        }
    
    def get_device_status(self) -> Dict[str, bool]:
        """获取设备运行状态"""
        return {
            f"waterpump_{i+1}": self._device_running[i]
            for i in range(6)
        }


# ============================================================
# 测试入口
# ============================================================
if __name__ == "__main__":
    generator = MockDataGenerator()
    
    print("=" * 60)
    print("水泵房模拟数据生成器测试")
    print("=" * 60)
    
    for i in range(3):
        generator.tick()
        
        print(f"\n--- 第 {i+1} 次生成 ---")
        
        # 生成 DB1
        db1 = generator.generate_db1_status()
        print(f"DB1 (状态): {len(db1)} 字节")
        print(f"  前16字节: {db1[:16].hex()}")
        
        # 生成 DB2
        db2 = generator.generate_db2_sensors()
        print(f"DB2 (传感器): {len(db2)} 字节")
        
        # 解析第一个电表
        uab = struct.unpack(">f", db2[0:4])[0]
        ia = struct.unpack(">f", db2[24:28])[0]
        pt = struct.unpack(">f", db2[36:40])[0]
        print(f"  水泵1: Uab={uab:.1f}V, Ia={ia:.2f}A, Pt={pt:.2f}kW")
        
        # 压力
        pressure_raw = struct.unpack(">H", db2[336:338])[0]
        print(f"  压力: {pressure_raw/1000:.3f} MPa")
    
    print("\n" + "=" * 60)
    print("设备状态:", generator.get_device_status())
