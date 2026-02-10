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
            # 6个水泵电表基础值（原始 PLC 值，需要经过转换器缩放）
            'pump_voltage': [380.0, 380.0, 380.0, 380.0, 380.0, 380.0],  # 原始值，转换器会 × 0.1
            'pump_current': [15.0, 18.0, 12.0, 20.0, 16.0, 14.0],  # 原始值，转换器会 × 0.001 × 20
            'pump_power': [4250.0, 5100.0, 3400.0, 6000.0, 4750.0, 4000.0],  # 原始值，转换器会 × 0.0001 × 20 = 8.5-12.0 kW
            'pump_energy': [1250.0, 1580.0, 980.0, 2100.0, 1420.0, 1180.0],  # 原始值，转换器会 × 20
            
            # 压力传感器基础值
            'pressure': 0.45,  # MPa (出水压力，典型值 0.3-0.6 MPa)
            # 振动传感器基础值 (mm/s)
            'vibration': [0.6, 0.7, 0.5, 0.8, 0.65, 0.55],
        }
        
        # 时间累计值 (用于生成连续变化的数据)
        self._tick = 0
        
        # 能耗累计值
        self._energy_accumulator = [0.0] * 6
        
        # 设备运行状态 (模拟开关) - 默认全部运行
        self._device_running = [True, True, True, True, True, True]
        
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
        
        # 禁用自动切换设备状态，避免数据突然变为 0
        # 每200次轮询，随机切换一个设备状态 (约16分钟)
        # if self._tick % 200 == 0:
        #     idx = random.randint(0, 5)
        #     self._device_running[idx] = not self._device_running[idx]
        #     if self._device_running[idx]:
        #         self._load_factor[idx] = random.uniform(0.8, 1.2)
    
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
                # 电压波动 ±5% (周期约10秒，更快更明显)
                line_voltage = self._add_sine_wave(base_v, amplitude=0.05, period=2)
                phase_voltage = line_voltage / 1.732
                
                # 电流波动 ±30% (周期约10秒，更快更明显)
                current = self._add_sine_wave(base_i, amplitude=0.30, period=2)
                
                # 功率波动 ±25% (周期约10秒，更快更明显)
                power = self._add_sine_wave(base_p, amplitude=0.25, period=2)
                
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
        # 压力波动 ±25% (周期约10秒)，模拟用水量变化，更快更明显
        pressure = self._add_sine_wave(
            self._base_values['pressure'],
            amplitude=0.25,
            period=2
        )
        # 添加随机扰动
        pressure += random.uniform(-0.03, 0.03)
        # 压力传感器原始值：转换器使用 raw * 0.01 kPa，所以 raw = pressure_mpa * 1000 / 0.01 = pressure_mpa * 100000
        # 例如：0.45 MPa = 450 kPa，raw = 450 / 0.01 = 45000
        pressure_kpa = pressure * 1000  # MPa 转 kPa
        pressure_raw = int(pressure_kpa / 0.01)  # kPa 转原始值
        data[336:338] = struct.pack(">H", min(65535, max(0, pressure_raw)))

        # 振动传感器 (6个, 起始偏移 338, 模块大小 116字节)
        # 只生成核心的 V/D/HZ 三组数据（9个字段）
        vib_base_offsets = [338, 454, 570, 686, 802, 918]
        for idx, base in enumerate(vib_base_offsets):
            if not self._device_running[idx]:
                # 设备未运行，振动为0
                continue
                
            base_v = self._base_values['vibration'][idx] * self._load_factor[idx]
            # 振动波动 ±35% (周期约10秒，更快更明显)
            vib_vx = self._add_sine_wave(base_v, amplitude=0.35, period=2)
            vib_vy = self._add_sine_wave(base_v * 0.9, amplitude=0.35, period=2)
            vib_vz = self._add_sine_wave(base_v * 1.1, amplitude=0.35, period=2)
            freq = 50.0 + random.uniform(-5, 5)

            def _write_word(offset: int, value: float, scale: float):
                raw = int(max(0, min(65535, value / scale)))
                data[base + offset: base + offset + 2] = struct.pack(">H", raw)

            # 速度幅值 (mm/s) VX/VY/VZ - offset 12, 14, 16
            _write_word(12, vib_vx, 1.0)
            _write_word(14, vib_vy, 1.0)
            _write_word(16, vib_vz, 1.0)

            # 位移幅值 (μm) DX/DY/DZ - offset 26, 28, 30
            _write_word(26, vib_vx * 1000, 1.0)
            _write_word(28, vib_vy * 1000, 1.0)
            _write_word(30, vib_vz * 1000, 1.0)

            # 频率 (Hz) HZX/HZY/HZZ - offset 32, 34, 36
            _write_word(32, freq, 1.0)
            _write_word(34, freq, 1.0)
            _write_word(36, freq, 1.0)
        
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
