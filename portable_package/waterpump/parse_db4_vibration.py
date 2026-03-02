# -*- coding: utf-8 -*-
# ============================================================
# DB4 (Vibration_DB) 振动传感器数据解析 - 水泵项目独立诊断脚本
# ============================================================
# 配置来源:
#   configs/config_vib_4_db4.yaml     (设备映射+字段定义)
# 转换来源:
#   app/plc/parser_vib_db4.py         (YAML scale 预缩放)
#   app/tools/converter_vibration.py   (最终转换)
# DB大小: 228 字节 (db_mappings.yaml: total_size=228)
#   - 6个振动传感器, 每个 38 字节
# ============================================================
# 每个传感器 38 字节布局 (全部为 Int, signed 16-bit, Big Endian):
#   +0  accel      (6B): accel_x/y/z      加速度幅值   (scale=1)
#   +6  accel_f    (6B): accel_f_x/y/z    加速度频率   (scale=1, Hz)
#   +12 vel        (6B): vel_x/y/z        速度幅值     (scale=0.01)
#   +18 reserved   (8B): reserved_x/y/z + temp  预留+温度 (scale=1)
#   +26 dis_f      (6B): dis_f_x/y/z      位移幅值     (scale=1, um)
#   +32 freq       (6B): freq_x/y/z       频率         (scale=1, Hz)
# ============================================================
# 转换公式 (两步):
#   步骤1 - parser_vib_db4.py 应用 YAML scale:
#     vel:   raw_int x 0.01
#     dis_f: raw_int x 1
#     freq:  raw_int x 1
#   步骤2 - converter_vibration.py 最终转换:
#     VX/VY/VZ   = 步骤1结果 / 100  -> mm/s  (总计: raw / 10000)
#     DX/DY/DZ   = 步骤1结果 / 10   -> um    (总计: raw / 10)
#     HZX/HZY/HZZ = 步骤1结果 / 10  -> Hz    (总计: raw / 10)
# 存储字段: vx, vy, vz, dx, dy, dz, hzx, hzy, hzz (共9个)
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

# DB4 配置 (db_mappings.yaml: total_size=228)
DB_NUMBER = 4
DB_SIZE = 228
SENSOR_SIZE = 38
SENSOR_COUNT = 6

# ============================================================
# 传感器映射 (来自 config_vib_4_db4.yaml)
# (index, device_id, device_name, base_offset)
# ============================================================
SENSORS = [
    (0, "vib_1", "1号振动传感器", 0),
    (1, "vib_2", "2号振动传感器", 38),
    (2, "vib_3", "3号振动传感器", 76),
    (3, "vib_4", "4号振动传感器", 114),
    (4, "vib_5", "5号振动传感器", 152),
    (5, "vib_6", "6号振动传感器", 190),
]

# ============================================================
# 模块内字段布局 (来自 config_vib_4_db4.yaml, 相对于传感器起始偏移)
# (module_name, rel_offset, fields_list)
# 每个字段: (name, rel_offset_in_sensor, display_name)
# 全部为 Int (signed 16-bit, 2 bytes)
# ============================================================
MODULES = [
    ("accel", 0, "加速度幅值 (scale=1)", [
        ("accel_x", 0,  "X轴加速度"),
        ("accel_y", 2,  "Y轴加速度"),
        ("accel_z", 4,  "Z轴加速度"),
    ]),
    ("accel_f", 6, "加速度频率 (scale=1, Hz)", [
        ("accel_f_x", 6,  "X轴加速度频率"),
        ("accel_f_y", 8,  "Y轴加速度频率"),
        ("accel_f_z", 10, "Z轴加速度频率"),
    ]),
    ("vel", 12, "速度幅值 (scale=0.01, mm/s) [核心]", [
        ("vel_x", 12, "X轴速度"),
        ("vel_y", 14, "Y轴速度"),
        ("vel_z", 16, "Z轴速度"),
    ]),
    ("reserved", 18, "预留+温度 (scale=1)", [
        ("reserved_x", 18, "预留X"),
        ("reserved_y", 20, "预留Y"),
        ("reserved_z", 22, "预留Z"),
        ("temp",       24, "温度"),
    ]),
    ("dis_f", 26, "位移幅值 (scale=1, um) [核心]", [
        ("dis_f_x", 26, "X轴位移"),
        ("dis_f_y", 28, "Y轴位移"),
        ("dis_f_z", 30, "Z轴位移"),
    ]),
    ("freq", 32, "频率 (scale=1, Hz) [核心]", [
        ("freq_x", 32, "X轴频率"),
        ("freq_y", 34, "Y轴频率"),
        ("freq_z", 36, "Z轴频率"),
    ]),
]


def read_int(data, offset):
    """读取 Int (signed 16-bit, Big Endian, 2字节)"""
    return struct.unpack(">h", data[offset:offset + 2])[0]


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
print("DB4 (Vibration_DB) 振动传感器数据解析 - 水泵项目")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print(f"读取: DB{DB_NUMBER}, {DB_SIZE} 字节 ({SENSOR_COUNT}个传感器 x {SENSOR_SIZE}字节)")
print("配置来源: configs/config_vib_4_db4.yaml")
print("转换来源: parser_vib_db4.py (YAML scale) + converter_vibration.py (最终转换)")
print("=" * 100)

try:
    data = bytes(client.db_read(DB_NUMBER, 0, DB_SIZE))

    for idx, device_id, device_name, base_offset in SENSORS:
        print()
        print(f"=== [{device_name}] {device_id} (Offset {base_offset}-{base_offset + SENSOR_SIZE - 1}, {SENSOR_SIZE}字节) ===")

        # --------------------------------------------------------
        # 1. 读取全部模块原始 Int 值
        # --------------------------------------------------------
        print()
        print(f"  [原始PLC值] (全部 Int, signed 16-bit)")

        raw_values = {}
        for mod_name, mod_offset, mod_desc, fields in MODULES:
            vals = []
            for fname, foffset, fdesc in fields:
                raw = read_int(data, base_offset + foffset)
                raw_values[fname] = raw
                vals.append(f"{fname}={raw:6d}")
            print(f"    {mod_name:10s} (+{mod_offset:2d}): {', '.join(vals)}  | {mod_desc}")

        # --------------------------------------------------------
        # 2. 转换公式过程 (仅核心9个存储字段)
        # --------------------------------------------------------
        print()
        print(f"  [转换公式] (parser YAML scale -> converter 最终转换)")

        # vel: raw x 0.01 (YAML scale) -> / 100 (converter) -> mm/s
        # 总计: raw / 10000
        vel_x_scaled = raw_values["vel_x"] * 0.01
        vel_y_scaled = raw_values["vel_y"] * 0.01
        vel_z_scaled = raw_values["vel_z"] * 0.01
        vx = round(vel_x_scaled / 100.0, 2)
        vy = round(vel_y_scaled / 100.0, 2)
        vz = round(vel_z_scaled / 100.0, 2)

        print(f"    vel_x: {raw_values['vel_x']:6d} x 0.01 = {vel_x_scaled:8.2f} -> / 100 = {vx:8.4f} mm/s")
        print(f"    vel_y: {raw_values['vel_y']:6d} x 0.01 = {vel_y_scaled:8.2f} -> / 100 = {vy:8.4f} mm/s")
        print(f"    vel_z: {raw_values['vel_z']:6d} x 0.01 = {vel_z_scaled:8.2f} -> / 100 = {vz:8.4f} mm/s")

        # dis_f: raw x 1 (YAML scale) -> / 10 (converter) -> um
        # 总计: raw / 10
        dis_x_scaled = raw_values["dis_f_x"] * 1.0
        dis_y_scaled = raw_values["dis_f_y"] * 1.0
        dis_z_scaled = raw_values["dis_f_z"] * 1.0
        dx = round(dis_x_scaled / 10.0, 1)
        dy = round(dis_y_scaled / 10.0, 1)
        dz = round(dis_z_scaled / 10.0, 1)

        print(f"    dis_f_x: {raw_values['dis_f_x']:6d} x 1 = {dis_x_scaled:8.1f} -> / 10 = {dx:8.1f} um")
        print(f"    dis_f_y: {raw_values['dis_f_y']:6d} x 1 = {dis_y_scaled:8.1f} -> / 10 = {dy:8.1f} um")
        print(f"    dis_f_z: {raw_values['dis_f_z']:6d} x 1 = {dis_z_scaled:8.1f} -> / 10 = {dz:8.1f} um")

        # freq: raw x 1 (YAML scale) -> / 10 (converter) -> Hz
        # 总计: raw / 10
        freq_x_scaled = raw_values["freq_x"] * 1.0
        freq_y_scaled = raw_values["freq_y"] * 1.0
        freq_z_scaled = raw_values["freq_z"] * 1.0
        hzx = round(freq_x_scaled / 10.0, 1)
        hzy = round(freq_y_scaled / 10.0, 1)
        hzz = round(freq_z_scaled / 10.0, 1)

        print(f"    freq_x: {raw_values['freq_x']:6d} x 1 = {freq_x_scaled:8.1f} -> / 10 = {hzx:8.1f} Hz")
        print(f"    freq_y: {raw_values['freq_y']:6d} x 1 = {freq_y_scaled:8.1f} -> / 10 = {hzy:8.1f} Hz")
        print(f"    freq_z: {raw_values['freq_z']:6d} x 1 = {freq_z_scaled:8.1f} -> / 10 = {hzz:8.1f} Hz")

        # --------------------------------------------------------
        # 3. 最终存储值 (写入 InfluxDB 的 9 个字段)
        # --------------------------------------------------------
        print()
        print(f"  [存储值] (写入 InfluxDB, 共9个字段)")
        print(f"    vx  = {vx:10.4f} mm/s    vy  = {vy:10.4f} mm/s    vz  = {vz:10.4f} mm/s")
        print(f"    dx  = {dx:10.1f} um      dy  = {dy:10.1f} um      dz  = {dz:10.1f} um")
        print(f"    hzx = {hzx:10.1f} Hz      hzy = {hzy:10.1f} Hz      hzz = {hzz:10.1f} Hz")

    # ============================================================
    # 原始数据 Hex Dump
    # ============================================================
    print()
    print("--- 原始数据 (每行16字节, 共228字节) ---")
    for i in range(0, DB_SIZE, 16):
        chunk = data[i:min(i + 16, DB_SIZE)]
        hex_fmt = " ".join([f"{b:02X}" for b in chunk])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB4 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")
