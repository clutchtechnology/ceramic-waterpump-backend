# -*- coding: utf-8 -*-
# ============================================================
# DB3 (DataState) 从站通信状态解析 - 水泵项目独立诊断脚本
# ============================================================
# 配置来源:
#   configs/status_waterpump_db3.yaml  (设备映射)
# DB大小: 76 字节 (db_mappings.yaml: total_size=76)
#   - 12个电表状态: 偏移 0-47  (每个 4 字节)
#   - 1个压力状态:  偏移 48-51
#   - 6个振动状态:  偏移 52-75
#   合计: 19个设备 x 4字节 = 76字节
# ============================================================
# 每个设备 4 字节结构:
#   Byte0 Bit0 = Error (Bool, true=通信错误)
#   Byte2-3    = Status (Word, 0x0000=正常)
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

# DB3 配置 (db_mappings.yaml: total_size=76)
DB_NUMBER = 3
DB_SIZE = 76

# ============================================================
# 设备映射 (来自 status_waterpump_db3.yaml, 共19个设备)
# (offset, device_id, device_name, plc_name, category)
# ============================================================
DEVICES = [
    # 电表 (12个, Offset 0-44)
    (0,  "status_meter_0",  "电表1状态",     "ElectricityMeter_0",  "meter"),
    (4,  "status_meter_1",  "电表2状态",     "ElectricityMeter_1",  "meter"),
    (8,  "status_meter_2",  "电表3状态",     "ElectricityMeter_2",  "meter"),
    (12, "status_meter_3",  "电表4状态",     "ElectricityMeter_3",  "meter"),
    (16, "status_meter_4",  "电表5状态",     "ElectricityMeter_4",  "meter"),
    (20, "status_meter_5",  "电表6状态",     "ElectricityMeter_5",  "meter"),
    (24, "status_meter_6",  "电表7状态",     "ElectricityMeter_6",  "meter"),
    (28, "status_meter_7",  "电表8状态",     "ElectricityMeter_7",  "meter"),
    (32, "status_meter_8",  "电表9状态",     "ElectricityMeter_8",  "meter"),
    (36, "status_meter_9",  "电表10状态",    "ElectricityMeter_9",  "meter"),
    (40, "status_meter_10", "电表11状态",    "ElectricityMeter_10", "meter"),
    (44, "status_meter_11", "电表12状态",    "ElectricityMeter_11", "meter"),
    # 压力传感器 (1个, Offset 48)
    (48, "status_press",    "总管压力状态",  "PRESS",               "press"),
    # 振动传感器 (6个, Offset 52-72)
    (52, "status_vib_1",    "1号泵震动状态", "VIB_1",               "vib"),
    (56, "status_vib_2",    "2号泵震动状态", "VIB_2",               "vib"),
    (60, "status_vib_3",    "3号泵震动状态", "VIB_3",               "vib"),
    (64, "status_vib_4",    "4号泵震动状态", "VIB_4",               "vib"),
    (68, "status_vib_5",    "5号泵震动状态", "VIB_5",               "vib"),
    (72, "status_vib_6",    "6号泵震动状态", "VIB_6",               "vib"),
]


def parse_status(data, offset):
    """解析单个设备状态 (4字节: Error Bool + Status Word)"""
    byte0 = data[offset]
    error = bool(byte0 & 0x01)
    status_word = struct.unpack(">H", data[offset + 2:offset + 4])[0]
    return error, status_word, byte0


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
print("DB3 (DataState) 从站通信状态解析 - 水泵项目")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print(f"读取: DB{DB_NUMBER}, {DB_SIZE} 字节 (19个设备 x 4字节)")
print("配置来源: configs/status_waterpump_db3.yaml")
print("=" * 100)

try:
    data = bytes(client.db_read(DB_NUMBER, 0, DB_SIZE))

    # ============================================================
    # [1/4] 电表从站状态 (12个, Offset 0-47)
    # ============================================================
    print()
    print("--- [1/4] 电表从站状态 (12个, Offset 0-47) ---")
    print(f"  {'Offset':>6s}  {'设备名':12s}  {'PLC名':24s}  {'Error':>5s}  {'Status':>8s}  {'Byte0':>8s}  {'结果':4s}")
    print(f"  {'-'*6}  {'-'*12}  {'-'*24}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*4}")

    meter_errors = 0
    for offset, dev_id, name, plc_name, cat in DEVICES:
        if cat != "meter":
            continue
        error, status_word, byte0 = parse_status(data, offset)
        result = "OK" if not error and status_word == 0 else "ERR"
        if error:
            meter_errors += 1
        print(f"  {offset:6d}  {name:12s}  {plc_name:24s}  {str(error):>5s}  0x{status_word:04X}    {byte0:08b}b  {result}")

    # ============================================================
    # [2/4] 压力从站状态 (1个, Offset 48)
    # ============================================================
    print()
    print("--- [2/4] 压力从站状态 (1个, Offset 48) ---")
    print(f"  {'Offset':>6s}  {'设备名':12s}  {'PLC名':24s}  {'Error':>5s}  {'Status':>8s}  {'Byte0':>8s}  {'结果':4s}")
    print(f"  {'-'*6}  {'-'*12}  {'-'*24}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*4}")

    press_errors = 0
    for offset, dev_id, name, plc_name, cat in DEVICES:
        if cat != "press":
            continue
        error, status_word, byte0 = parse_status(data, offset)
        result = "OK" if not error and status_word == 0 else "ERR"
        if error:
            press_errors += 1
        print(f"  {offset:6d}  {name:12s}  {plc_name:24s}  {str(error):>5s}  0x{status_word:04X}    {byte0:08b}b  {result}")

    # ============================================================
    # [3/4] 振动从站状态 (6个, Offset 52-72)
    # ============================================================
    print()
    print("--- [3/4] 振动从站状态 (6个, Offset 52-72) ---")
    print(f"  {'Offset':>6s}  {'设备名':12s}  {'PLC名':24s}  {'Error':>5s}  {'Status':>8s}  {'Byte0':>8s}  {'结果':4s}")
    print(f"  {'-'*6}  {'-'*12}  {'-'*24}  {'-'*5}  {'-'*8}  {'-'*8}  {'-'*4}")

    vib_errors = 0
    for offset, dev_id, name, plc_name, cat in DEVICES:
        if cat != "vib":
            continue
        error, status_word, byte0 = parse_status(data, offset)
        result = "OK" if not error and status_word == 0 else "ERR"
        if error:
            vib_errors += 1
        print(f"  {offset:6d}  {name:12s}  {plc_name:24s}  {str(error):>5s}  0x{status_word:04X}    {byte0:08b}b  {result}")

    # ============================================================
    # 统计汇总
    # ============================================================
    total = len(DEVICES)
    total_errors = meter_errors + press_errors + vib_errors
    total_ok = total - total_errors

    print()
    print(f"--- 统计汇总 ---")
    print(f"  总设备: {total}  正常: {total_ok}  异常: {total_errors}")
    print(f"  电表:   12 (异常: {meter_errors})")
    print(f"  压力:    1 (异常: {press_errors})")
    print(f"  振动:    6 (异常: {vib_errors})")

    # ============================================================
    # [4/4] 原始数据 Hex Dump
    # ============================================================
    print()
    print("--- [4/4] 原始数据 (每行16字节, 共76字节) ---")
    for i in range(0, DB_SIZE, 16):
        chunk = data[i:min(i + 16, DB_SIZE)]
        hex_fmt = " ".join([f"{b:02X}" for b in chunk])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB3 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")
