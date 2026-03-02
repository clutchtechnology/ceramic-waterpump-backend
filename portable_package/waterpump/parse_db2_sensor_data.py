# -*- coding: utf-8 -*-
# ============================================================
# DB2 (Data_DB) 传感器数据解析 - 水泵项目独立诊断脚本
# ============================================================
# 配置来源:
#   configs/config_waterpump_db2.yaml  (设备映射)
#   configs/plc_modules.yaml           (模块字段定义)
# 转换来源:
#   app/tools/converter_elec.py        (电表转换)
#   app/tools/converter_pressure.py    (压力转换)
# DB大小: 338 字节 (db_mappings.yaml: total_size=338)
#   - 6个三相电表: 偏移 0-335 (每个 56 字节, 14个 Real 字段)
#   - 1个压力传感器: 偏移 336-337 (1个 Word 字段)
# 注意: 振动传感器已移至 DB4, 请运行 parse_db4_vibration.py
# ============================================================
# 电表转换公式 (converter_elec.py):
#   电压: raw x 0.1         -> V   (存储字段: Ua_0, Ua_1, Ua_2)
#   电流: raw x 0.001 x 20  -> A   (存储字段: I_0, I_1, I_2)
#   功率: raw x 2            -> kW  (存储字段: Pt)
#   电能: raw x 2            -> kWh (存储字段: ImpEp)
#   线电压/相功率: 仅读取不存储
# 压力转换公式 (converter_pressure.py):
#   压力: raw x 1.0          -> kPa (存储字段: pressure, pressure_kpa)
# ============================================================

import struct
import sys

try:
    import snap7
except ImportError:
    print("snap7 未安装, 请运行: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置
PLC_IP = "192.168.50.224"
PLC_RACK = 0
PLC_SLOT = 1

# DB2 配置 (db_mappings.yaml: total_size=338)
DB_NUMBER = 2
DB_SIZE = 338

# ============================================================
# 电表映射 (来自 config_waterpump_db2.yaml)
# 6个电表, 每个56字节, 14个Real字段(每个4字节)
# (index, device_id, device_name, start_offset)
# ============================================================
METERS = [
    (0, "pump_meter_1", "1号泵电表", 0),
    (1, "pump_meter_2", "2号泵电表", 56),
    (2, "pump_meter_3", "3号泵电表", 112),
    (3, "pump_meter_4", "4号泵电表", 168),
    (4, "pump_meter_5", "5号泵电表", 224),
    (5, "pump_meter_6", "6号泵电表", 280),
]

# ============================================================
# 电表内部字段布局 (来自 plc_modules.yaml: ElectricityMeter, 56字节)
# (field_name, offset, description)
# 全部为 Real (32-bit float, 4 bytes, Big Endian)
# ============================================================
METER_FIELDS = [
    ("Uab_0", 0,  "AB线电压"),
    ("Uab_1", 4,  "BC线电压"),
    ("Uab_2", 8,  "CA线电压"),
    ("Ua_0",  12, "A相电压"),
    ("Ua_1",  16, "B相电压"),
    ("Ua_2",  20, "C相电压"),
    ("I_0",   24, "A相电流"),
    ("I_1",   28, "B相电流"),
    ("I_2",   32, "C相电流"),
    ("Pt",    36, "总有功功率"),
    ("Pa",    40, "A相功率"),
    ("Pb",    44, "B相功率"),
    ("Pc",    48, "C相功率"),
    ("ImpEp", 52, "正向有功电能"),
]

# ============================================================
# 转换常量 (来自 converter_elec.py)
# ============================================================
SCALE_VOLTAGE = 0.1       # 电压系数
SCALE_CURRENT = 0.001     # 电流系数
CURRENT_RATIO = 20        # 电流互感器变比
SCALE_POWER = 2.0         # 功率系数
SCALE_ENERGY = 2.0        # 电能系数

# ============================================================
# 压力配置 (来自 config_waterpump_db2.yaml + converter_pressure.py)
# ============================================================
PRESSURE_OFFSET = 336     # 起始偏移
PRESSURE_SCALE = 1.0      # raw x 1.0 = kPa


def read_real(data, offset):
    """读取 Real (Big Endian float, 4字节)"""
    return struct.unpack(">f", data[offset:offset + 4])[0]


def read_word(data, offset):
    """读取 Word (Big Endian unsigned short, 2字节)"""
    return struct.unpack(">H", data[offset:offset + 2])[0]


# ============================================================
# 连接 PLC
# ============================================================
client = snap7.client.Client()
try:
    client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
except Exception as e:
    print(f"PLC 连接失败: {e}")
    sys.exit(1)

print("=" * 100)
print("DB2 (Data_DB) 传感器数据解析 - 水泵项目")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print(f"读取: DB{DB_NUMBER}, {DB_SIZE} 字节 (6个电表x56 + 1个压力x2)")
print("配置来源: configs/config_waterpump_db2.yaml + configs/plc_modules.yaml")
print("转换来源: converter_elec.py + converter_pressure.py")
print("=" * 100)

try:
    data = bytes(client.db_read(DB_NUMBER, 0, DB_SIZE))

    # ============================================================
    # 1. 电表数据解析 (6个电表, Offset 0-335)
    # ============================================================
    for idx, device_id, device_name, start_offset in METERS:

        print()
        print(f"--- [{device_name}] {device_id} (Offset {start_offset}-{start_offset + 55}, 56字节) ---")
        print()

        # 1a. 读取全部14个原始 Real 值
        raw_values = {}
        for field_name, field_offset, desc in METER_FIELDS:
            raw = read_real(data, start_offset + field_offset)
            raw_values[field_name] = raw

        # 1b. 显示原始值
        print(f"  [原始PLC值] (14个Real字段, 直接从PLC读取)")
        print(f"    Uab_0={raw_values['Uab_0']:12.4f}  Uab_1={raw_values['Uab_1']:12.4f}  Uab_2={raw_values['Uab_2']:12.4f}  (线电压)")
        print(f"    Ua_0 ={raw_values['Ua_0']:12.4f}  Ua_1 ={raw_values['Ua_1']:12.4f}  Ua_2 ={raw_values['Ua_2']:12.4f}  (相电压)")
        print(f"    I_0  ={raw_values['I_0']:12.4f}  I_1  ={raw_values['I_1']:12.4f}  I_2  ={raw_values['I_2']:12.4f}  (电流)")
        print(f"    Pt   ={raw_values['Pt']:12.4f}  Pa   ={raw_values['Pa']:12.4f}  Pb   ={raw_values['Pb']:12.4f}  Pc={raw_values['Pc']:12.4f}")
        print(f"    ImpEp={raw_values['ImpEp']:12.4f}")
        print()

        # 1c. 转换计算过程 (converter_elec.py)
        # 电压: raw x 0.1 -> V
        ua_0 = round(raw_values["Ua_0"] * SCALE_VOLTAGE, 1)
        ua_1 = round(raw_values["Ua_1"] * SCALE_VOLTAGE, 1)
        ua_2 = round(raw_values["Ua_2"] * SCALE_VOLTAGE, 1)

        # 电流: raw x 0.001 x 20 -> A
        i_0 = round(raw_values["I_0"] * SCALE_CURRENT * CURRENT_RATIO, 2)
        i_1 = round(raw_values["I_1"] * SCALE_CURRENT * CURRENT_RATIO, 2)
        i_2 = round(raw_values["I_2"] * SCALE_CURRENT * CURRENT_RATIO, 2)

        # 功率: raw x 2 -> kW
        pt = round(raw_values["Pt"] * SCALE_POWER, 3)

        # 电能: raw x 2 -> kWh
        imp_ep = round(raw_values["ImpEp"] * SCALE_ENERGY, 3)

        print(f"  [转换公式] (converter_elec.py, 变比={CURRENT_RATIO})")
        print(f"    电压: Ua_0 = {raw_values['Ua_0']:.4f} x {SCALE_VOLTAGE} = {ua_0:.1f} V")
        print(f"           Ua_1 = {raw_values['Ua_1']:.4f} x {SCALE_VOLTAGE} = {ua_1:.1f} V")
        print(f"           Ua_2 = {raw_values['Ua_2']:.4f} x {SCALE_VOLTAGE} = {ua_2:.1f} V")
        print(f"    电流: I_0  = {raw_values['I_0']:.4f} x {SCALE_CURRENT} x {CURRENT_RATIO} = {i_0:.2f} A")
        print(f"           I_1  = {raw_values['I_1']:.4f} x {SCALE_CURRENT} x {CURRENT_RATIO} = {i_1:.2f} A")
        print(f"           I_2  = {raw_values['I_2']:.4f} x {SCALE_CURRENT} x {CURRENT_RATIO} = {i_2:.2f} A")
        print(f"    功率: Pt   = {raw_values['Pt']:.4f} x {SCALE_POWER} = {pt:.3f} kW")
        print(f"    电能: ImpEp= {raw_values['ImpEp']:.4f} x {SCALE_ENERGY} = {imp_ep:.3f} kWh")
        print()

        # 1d. 最终存储值 (写入 InfluxDB 的8个字段)
        print(f"  [存储值] (写入 InfluxDB, 共8个字段)")
        print(f"    Ua_0  = {ua_0:10.1f} V")
        print(f"    Ua_1  = {ua_1:10.1f} V")
        print(f"    Ua_2  = {ua_2:10.1f} V")
        print(f"    I_0   = {i_0:10.2f} A")
        print(f"    I_1   = {i_1:10.2f} A")
        print(f"    I_2   = {i_2:10.2f} A")
        print(f"    Pt    = {pt:10.3f} kW")
        print(f"    ImpEp = {imp_ep:10.3f} kWh")

        # 1e. 未存储的参考字段
        uab_0 = round(raw_values["Uab_0"] * SCALE_VOLTAGE, 1)
        uab_1 = round(raw_values["Uab_1"] * SCALE_VOLTAGE, 1)
        uab_2 = round(raw_values["Uab_2"] * SCALE_VOLTAGE, 1)
        pa = round(raw_values["Pa"] * SCALE_POWER, 3)
        pb = round(raw_values["Pb"] * SCALE_POWER, 3)
        pc = round(raw_values["Pc"] * SCALE_POWER, 3)
        print(f"  [参考值] (仅PLC读取, 不存储)")
        print(f"    Uab_0 = {uab_0:.1f} V  Uab_1 = {uab_1:.1f} V  Uab_2 = {uab_2:.1f} V  (线电压)")
        print(f"    Pa    = {pa:.3f} kW  Pb = {pb:.3f} kW  Pc = {pc:.3f} kW  (相功率)")

    # ============================================================
    # 2. 压力传感器 (Offset 336-337)
    # ============================================================
    print()
    print("=" * 100)
    print("--- [压力传感器] pump_pressure (Offset 336-337, 2字节 Word) ---")
    print()

    pressure_raw = read_word(data, PRESSURE_OFFSET)

    print(f"  [原始PLC值]")
    print(f"    pressure_raw = {pressure_raw} (0x{pressure_raw:04X})")
    print()

    # 转换: raw x 1.0 = kPa (converter_pressure.py: DEFAULT_SCALE=1.0)
    pressure_kpa = round(pressure_raw * PRESSURE_SCALE, 1)

    print(f"  [转换公式] (converter_pressure.py, scale={PRESSURE_SCALE})")
    print(f"    pressure = {pressure_raw} x {PRESSURE_SCALE} = {pressure_kpa:.1f} kPa")
    print()

    print(f"  [存储值] (写入 InfluxDB, 共2个字段)")
    print(f"    pressure_kpa = {pressure_kpa:.1f} kPa")
    print(f"    pressure     = {pressure_kpa:.1f} kPa")

    # ============================================================
    # 3. 原始数据 Hex Dump
    # ============================================================
    print()
    print("--- 原始数据 (每行16字节, 共338字节) ---")
    for i in range(0, DB_SIZE, 16):
        chunk = data[i:min(i + 16, DB_SIZE)]
        hex_fmt = " ".join([f"{b:02X}" for b in chunk])
        print(f"  {i:3d}: {hex_fmt}")

    print()
    print("--- 振动传感器数据已移至 DB4, 请运行 parse_db4_vibration.py ---")

except Exception as e:
    print(f"读取 DB2 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")
