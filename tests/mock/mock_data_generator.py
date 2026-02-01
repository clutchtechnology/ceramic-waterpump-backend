# ============================================================
# 文件说明: mock_data_generator.py - 水泵房模拟数据生成器
# ============================================================
# 功能:
# 1. 生成符合PLC DB块结构的原始数据
# 2. 模拟水泵房电表、压力传感器、设备状态
# 3. 支持 DB1/DB3(设备状态) 和 DB2(传感器数据)
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
            'pressure': 0.45,  # MPa (出水压力，典型值 0.3-0.6 MPa)
            # 振动传感器基础值 (mm/s)
            'vibration': [0.6, 0.7, 0.5, 0.8, 0.65, 0.55],
        }
        
        # 时间累计值 (用于生成连续变化的数据)
        self._tick = 0
        
        # 能耗累计值
        self._energy_accumulator = [0.0] * 6
        
        # 设备运行状态 (模拟开关) - 默认前4台运行
        self._device_running = [True, True, True, True, False, False]
        
        # 动态基础值偏移 (模拟负载变化)
        self._load_factor = [1.0] * 6
    
    def tick(self):
        """时间前进一步 (每次轮询调用)"""
        self._tick += 1
        
        # 每20次轮询，随机调整负载因子 (模拟负载波动)
        if self._tick % 20 == 0:
            for i in range(6):
                if self._device_running[i]:
                    # 负载在 0.7 ~ 1.3 之间波动
                    self._load_factor[i] = random.uniform(0.7, 1.3)
        
        # 每200次轮询，随机切换一个设备状态 (约16分钟)
        if self._tick % 200 == 0:
            idx = random.randint(0, 5)
            self._device_running[idx] = not self._device_running[idx]
            if self._device_running[idx]:
                self._load_factor[idx] = random.uniform(0.8, 1.2)
    
    def _add_noise(self, base: float, noise_range: float = 0.05) -> float:
        """添加随机波动"""
        noise = random.uniform(-noise_range, noise_range)
        return base * (1 + noise)
    
    def _add_sine_wave(self, base: float, amplitude: float = 0.1, period: int = 60) -> float:
        """添加正弦波动 (模拟周期性变化)
        
        Args:
            base: 基础值
            amplitude: 振幅比例 (0.1 = ±10%)
            period: 周期 (tick数，5秒/tick 则 period=12 约为1分钟)
        """
        wave = math.sin(2 * math.pi * self._tick / period) * amplitude
        # 叠加一个更快的小波动，让数据看起来更自然
        fast_wave = math.sin(2 * math.pi * self._tick / (period / 3)) * (amplitude * 0.3)
        return base * (1 + wave + fast_wave)
    
    # ============================================================
    # DB1: 设备状态数据 (80 字节)
    # ============================================================
    def generate_db1_status(self) -> bytes:
        """生成 DB1 设备状态数据 (80 字节)
        
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
        data = bytearray(80)

        # 20 个状态块 (0-76, 步长4)
        device_offsets = list(range(0, 80, 4))
        
        for idx, offset in enumerate(device_offsets):
            running = self._device_running[idx % len(self._device_running)]
            if running:
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
    # DB3: 从站状态数据 (80 字节)
    # ============================================================
    def generate_db3_status(self) -> bytes:
        """生成 DB3 从站状态数据 (80 字节)

        结构:
        - Byte 0, Bit 0: Error
        - Byte 2-3: Status (Word)
        """
        data = bytearray(80)
        device_offsets = list(range(0, 80, 4))

        for idx, offset in enumerate(device_offsets):
            running = self._device_running[idx % len(self._device_running)]

            if running:
                # 95% 正常, 5% 错误
                error = random.random() >= 0.95
                data[offset] = 0x01 if error else 0x00
                status_code = 0x8001 if error else 0x0000
                data[offset + 2:offset + 4] = struct.pack(">H", status_code)
            else:
                data[offset] = 0x00
                data[offset + 2:offset + 4] = struct.pack(">H", 0x0000)

        return bytes(data)
    
    # ============================================================
    # DB2: 传感器数据 (1034 字节)
    # ============================================================
    def generate_db2_sensors(self) -> bytes:
        """生成 DB2 传感器数据 (1034 字节)
        
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
        data = bytearray(1034)
        
        for idx in range(6):
            offset = idx * 56
            
            if self._device_running[idx]:
                # 设备运行中，生成真实数据
                base_v = self._base_values['pump_voltage'][idx]
                base_i = self._base_values['pump_current'][idx] * self._load_factor[idx]
                base_p = self._base_values['pump_power'][idx] * self._load_factor[idx]
                base_e = self._base_values['pump_energy'][idx]
                
                # 添加波动 (增大幅度使变化更明显)
                # 电压波动 ±3% (周期约40秒)
                line_voltage = self._add_sine_wave(base_v, amplitude=0.03, period=8)
                phase_voltage = line_voltage / 1.732
                
                # 电流波动 ±20% (周期约25秒)
                current = self._add_sine_wave(base_i, amplitude=0.20, period=5)
                
                # 功率波动 ±15% (周期约30秒)
                power = self._add_sine_wave(base_p, amplitude=0.15, period=6)
                
                # 累计能耗 (每5秒增加)
                self._energy_accumulator[idx] += abs(power) * (5 / 3600)
                energy = base_e + self._energy_accumulator[idx]
                
                # 打包电表数据 (14 个 REAL, 大端)
                values = [
                    line_voltage + random.uniform(-3, 3),      # Uab
                    line_voltage + random.uniform(-3, 3),      # Ubc
                    line_voltage + random.uniform(-3, 3),      # Uca
                    phase_voltage + random.uniform(-2, 2),     # Ua
                    phase_voltage + random.uniform(-2, 2),     # Ub
                    phase_voltage + random.uniform(-2, 2),     # Uc
                    current + random.uniform(-1, 1),           # Ia
                    current + random.uniform(-1, 1),           # Ib
                    current + random.uniform(-1, 1),           # Ic
                    power,                                      # Pt
                    power / 3 + random.uniform(-0.2, 0.2),     # Pa
                    power / 3 + random.uniform(-0.2, 0.2),     # Pb
                    power / 3 + random.uniform(-0.2, 0.2),     # Pc
                    energy,                                     # ImpEp
                ]
            else:
                # 设备停止，数据为0
                values = [0.0] * 14
            
            for i, val in enumerate(values):
                data[offset + i*4 : offset + i*4 + 4] = struct.pack(">f", val)
        
        # 压力传感器 (偏移 336, 2字节)
        # 压力波动 ±15% (周期约50秒)，模拟用水量变化
        pressure = self._add_sine_wave(
            self._base_values['pressure'],
            amplitude=0.15,
            period=10
        )
        # 添加随机扰动
        pressure += random.uniform(-0.02, 0.02)
        # 压力传感器原始值范围 0-10000 对应 0-10 MPa (即 0.001 MPa/单位)
        pressure_raw = int(pressure * 1000)
        data[336:338] = struct.pack(">H", min(65535, max(0, pressure_raw)))

        # 振动传感器 (6个, 起始偏移 338, 模块大小 84字节)
        vib_base_offsets = [338, 422, 506, 590, 674, 758]
        for idx, base in enumerate(vib_base_offsets):
            if not self._device_running[idx]:
                # 设备未运行，振动为0
                continue
                
            base_v = self._base_values['vibration'][idx] * self._load_factor[idx]
            # 振动波动 ±25% (周期约15-20秒)
            vib_vx = self._add_sine_wave(base_v, amplitude=0.25, period=3 + idx)
            vib_vy = self._add_sine_wave(base_v * 0.9, amplitude=0.25, period=4 + idx)
            vib_vz = self._add_sine_wave(base_v * 1.1, amplitude=0.25, period=5 + idx)
            freq = 50.0 + random.uniform(-5, 5)

            def _write_word(offset: int, value: float, scale: float):
                raw = int(max(0, min(65535, value / scale)))
                data[base + offset: base + offset + 2] = struct.pack(">H", raw)

            # 位移幅值 (μm) DX/DY/DZ
            _write_word(0, vib_vx * 1000, 1.0)
            _write_word(2, vib_vy * 1000, 1.0)
            _write_word(4, vib_vz * 1000, 1.0)

            # 频率 (Hz) HZX/HZY/HZZ, scale=0.1
            _write_word(6, freq, 0.1)
            _write_word(8, freq, 0.1)
            _write_word(10, freq, 0.1)

            # X轴数据块
            _write_word(12, 2.0, 1.0)  # CFX
            _write_word(14, 2.5 + random.uniform(-0.3, 0.3), 0.01)  # KX
            _write_word(16, 2.6 + random.uniform(-0.3, 0.3), 0.01)  # AAVGX
            _write_word(18, vib_vx * 1.2, 0.1)  # VARX
            _write_word(20, vib_vx * 800, 1.0)  # RRAX 位移峰值
            _write_word(22, 1.5, 0.01)  # WX 包络加速度
            _write_word(24, 10, 1.0)  # PIX
            _write_word(26, 12, 1.0)  # PCX
            _write_word(28, 14, 1.0)  # SKX
            _write_word(30, vib_vx, 0.1)  # VRMSX
            _write_word(32, vib_vx * 1.1, 0.1)  # VKX
            _write_word(34, vib_vx * 900, 1.0)  # DRMSX 位移RMS

            # Y轴数据块
            _write_word(36, 2.1, 1.0)  # CFY
            _write_word(38, 2.6 + random.uniform(-0.3, 0.3), 0.01)  # KY
            _write_word(40, 2.7 + random.uniform(-0.3, 0.3), 0.01)  # AAVGY
            _write_word(42, vib_vy * 1.2, 0.1)  # VARY
            _write_word(44, vib_vy * 800, 1.0)  # RRAY
            _write_word(46, 1.6, 0.01)  # WY
            _write_word(48, 10, 1.0)  # PIY
            _write_word(50, 12, 1.0)  # PCY
            _write_word(52, 14, 1.0)  # SKY
            _write_word(54, vib_vy, 0.1)  # VRMSY
            _write_word(56, vib_vy * 1.1, 0.1)  # VKY
            _write_word(58, vib_vy * 900, 1.0)  # DRMSY

            # Z轴数据块
            _write_word(60, 2.2, 1.0)  # CFZ
            _write_word(62, 2.7 + random.uniform(-0.3, 0.3), 0.01)  # KZ
            _write_word(64, 2.8 + random.uniform(-0.3, 0.3), 0.01)  # AAVGZ
            _write_word(66, vib_vz * 1.2, 0.1)  # VARZ
            _write_word(68, vib_vz * 800, 1.0)  # RRAZ
            _write_word(70, 1.7, 0.01)  # WZ
            _write_word(72, 10, 1.0)  # PIZ
            _write_word(74, 12, 1.0)  # PCZ
            _write_word(76, 14, 1.0)  # SKZ
            _write_word(78, vib_vz, 0.1)  # VRMSZ
            _write_word(80, vib_vz * 1.1, 0.1)  # VKZ
            _write_word(82, vib_vz * 900, 1.0)  # DRMSZ
        
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
            3: self.generate_db3_status(),
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
