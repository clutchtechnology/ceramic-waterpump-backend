#!/usr/bin/env python3
# ============================================================
# 文件说明: test_mock_generator.py - 测试模拟数据生成器
# ============================================================
# 运行: python tests/mock/test_mock_generator.py
# ============================================================

import sys
import os
import struct

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

try:
    from tests.mock.mock_data_generator import MockDataGenerator
except ImportError:
    from mock_data_generator import MockDataGenerator


def test_db1_status():
    """测试 DB1 状态数据生成"""
    print("\n" + "=" * 60)
    print("测试 DB1 状态数据生成")
    print("=" * 60)
    
    generator = MockDataGenerator()
    
    for i in range(3):
        generator.tick()
        db1 = generator.generate_db1_status()
        
        print(f"\n第 {i+1} 次生成:")
        print(f"  数据长度: {len(db1)} 字节")
        print(f"  原始数据 (前24字节): {db1[:24].hex()}")
        
        # 解析各设备状态
        device_offsets = [(0, "master_load"), (4, "meter_1"), (8, "meter_2"),
                 (12, "meter_3"), (16, "meter_4"), (20, "meter_5"), (24, "meter_6")]
        
        for offset, name in device_offsets:
            status_byte = db1[offset]
            done = bool(status_byte & 0x01)
            busy = bool(status_byte & 0x02)
            error = bool(status_byte & 0x04)
            status_word = struct.unpack(">H", db1[offset+2:offset+4])[0]
            
            state = " OK" if done and not error else (" BUSY" if busy else (" ERROR" if error else "⬜ IDLE"))
            print(f"  {name}: {state} (done={done}, busy={busy}, error={error}, status=0x{status_word:04X})")


def test_db2_sensors():
    """测试 DB2 传感器数据生成"""
    print("\n" + "=" * 60)
    print("测试 DB2 传感器数据生成")
    print("=" * 60)
    
    generator = MockDataGenerator()
    
    for i in range(3):
        generator.tick()
        db2 = generator.generate_db2_sensors()
        
        print(f"\n第 {i+1} 次生成:")
        print(f"  数据长度: {len(db2)} 字节")
        
        # 解析各电表
        for idx in range(6):
            offset = idx * 56
            uab = struct.unpack(">f", db2[offset:offset+4])[0]
            ua = struct.unpack(">f", db2[offset+12:offset+16])[0]
            ia = struct.unpack(">f", db2[offset+24:offset+28])[0]
            pt = struct.unpack(">f", db2[offset+36:offset+40])[0]
            imp_ep = struct.unpack(">f", db2[offset+52:offset+56])[0]
            
            running = generator._device_running[idx]
            status = "🟢" if running else "🔴"
            print(f"  {status} meter_{idx+1}: Uab={uab:.1f}V, Ua={ua:.1f}V, Ia={ia:.2f}A, Pt={pt:.2f}kW, E={imp_ep:.1f}kWh")
        
        # 压力传感器
        pressure_raw = struct.unpack(">H", db2[336:338])[0]
        pressure_kpa = pressure_raw * 0.01
        print(f"  🔵 pressure: {pressure_kpa:.2f} kPa (raw={pressure_raw})")

        # 振动传感器 (读取1号泵VX)
        vib_vx_raw = struct.unpack(">H", db2[338 + 12:338 + 14])[0]
        print(f"  🟣 vib_1_vx: {vib_vx_raw * 0.01:.2f} mm/s")


def test_with_parsers():
    """使用实际解析器测试"""
    print("\n" + "=" * 60)
    print("使用实际解析器测试")
    print("=" * 60)
    
    try:
        from app.plc.parser_waterpump import parse_waterpump_db
        from app.plc.parser_status_waterpump import parse_status_waterpump_master_db
        from app.tools.converter_elec import ElectricityConverter
        from app.tools.converter_pressure import PressureConverter
        
        generator = MockDataGenerator()
        elec_conv = ElectricityConverter()
        pres_conv = PressureConverter()
        
        for i in range(2):
            generator.tick()
            
            # 生成数据
            db1 = generator.generate_db1_status()
            db2 = generator.generate_db2_sensors()
            
            print(f"\n第 {i+1} 次解析:")
            
            # 解析状态
            status_result = parse_status_waterpump_master_db(db1)
            print(f"   状态汇总: {status_result.get('summary', {})}")
            
            # 解析传感器
            sensor_result = parse_waterpump_db(db2)
            
            # 转换电表数据
            for meter_id in [f"pump_meter_{j}" for j in range(1, 4)]:
                device_data = sensor_result.get(meter_id, {})
                module = device_data.get("modules", {}).get(f"elec_{meter_id.split('_')[-1]}", {})
                raw_fields = module.get("fields", {})
                if raw_fields:
                    converted = elec_conv.convert(raw_fields)
                    print(f"  ⚡ {meter_id}: Pt={converted['Pt']}kW, E={converted['ImpEp']}kWh")
            
            # 转换压力数据
            pressure_dev = sensor_result.get("pump_pressure", {})
            pressure_module = pressure_dev.get("modules", {}).get("pressure_main", {})
            pressure_raw = pressure_module.get("fields", {})
            if pressure_raw:
                pres_converted = pres_conv.convert(pressure_raw)
                print(f"  💧 pressure: {pres_converted['pressure_kpa']} kPa")
        
        print("\n 解析器测试通过!")
        
    except ImportError as e:
        print(f"\n 无法导入解析器: {e}")
        print("   请确保在项目根目录运行此脚本")


if __name__ == "__main__":
    print("=" * 60)
    print("水泵房模拟数据生成器测试")
    print("=" * 60)
    
    test_db1_status()
    test_db2_sensors()
    test_with_parsers()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
