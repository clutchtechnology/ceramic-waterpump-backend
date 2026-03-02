# -*- coding: utf-8 -*-
# ============================================================
# DB1 (MBValueTemp) 主站通信状态解析 - 水泵项目独立诊断脚本
# ============================================================
# 配置来源: configs/status_waterpump_db1.yaml
# DB大小: 80 字节 (20个设备 x 4字节)
# 结构: 每个设备 4 字节
#   Byte 0: 位域 - Bit0=Done, Bit1=Busy, Bit2=Error
#   Byte 1: 保留
#   Byte 2-3: Status (Word, 大端序)
# 判定: Error=false -> 正常, Error=true -> 故障
# 存储: 不写入 InfluxDB, 仅用于通信状态监控
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

# DB1 总大小 (db_mappings.yaml: total_size=80)
DB_NUMBER = 1
DB_SIZE = 80

# ============================================================
# 设备映射 (来自 status_waterpump_db1.yaml, 20个设备)
# (offset, device_name, plc_name, category)
# ============================================================
DEVICES = [
    (0,  "主站通信负载",      "MB_COMM_LOAD",       "system"),
    (4,  "电表1主站状态",     "DB_MASTER_ELEC_0",   "meter"),
    (8,  "电表2主站状态",     "DB_MASTER_ELEC_1",   "meter"),
    (12, "电表3主站状态",     "DB_MASTER_ELEC_2",   "meter"),
    (16, "电表4主站状态",     "DB_MASTER_ELEC_3",   "meter"),
    (20, "电表5主站状态",     "DB_MASTER_ELEC_4",   "meter"),
    (24, "电表6主站状态",     "DB_MASTER_ELEC_5",   "meter"),
    (28, "电表7主站状态",     "DB_MASTER_ELEC_6",   "meter"),
    (32, "电表8主站状态",     "DB_MASTER_ELEC_7",   "meter"),
    (36, "电表9主站状态",     "DB_MASTER_ELEC_8",   "meter"),
    (40, "电表10主站状态",    "DB_MASTER_ELEC_9",   "meter"),
    (44, "电表11主站状态",    "DB_MASTER_ELEC_10",  "meter"),
    (48, "电表12主站状态",    "DB_MASTER_ELEC_11",  "meter"),
    (52, "总管压力主站状态",  "DB_MASTER_PRESS",    "press"),
    (56, "1号泵震动主站状态", "DB_MASTER_VIB_1",    "vib"),
    (60, "2号泵震动主站状态", "DB_MASTER_VIB_2",    "vib"),
    (64, "3号泵震动主站状态", "DB_MASTER_VIB_3",    "vib"),
    (68, "4号泵震动主站状态", "DB_MASTER_VIB_4",    "vib"),
    (72, "5号泵震动主站状态", "DB_MASTER_VIB_5",    "vib"),
    (76, "6号泵震动主站状态", "DB_MASTER_VIB_6",    "vib"),
]


def parse_status(data, offset):
    """解析单个设备的4字节状态"""
    byte0 = data[offset]
    status_word = struct.unpack(">H", data[offset + 2:offset + 4])[0]
    done = bool(byte0 & 0x01)
    busy = bool(byte0 & 0x02)
    error = bool(byte0 & 0x04)
    return byte0, done, busy, error, status_word


def print_table_header():
    print(f"  {'Offset':>6s}  {'设备名称':20s} {'PLC名称':26s} {'Byte0':>6s} {'Done':>5s} {'Busy':>5s} {'Error':>6s} {'Status':>8s}  {'判定':>6s}")
    print(f"  {'-'*6}  {'-'*20} {'-'*26} {'-'*6} {'-'*5} {'-'*5} {'-'*6} {'-'*8}  {'-'*6}")


def print_table_row(offset, name, plc_name, byte0, done, busy, error, status_word):
    result = "ERROR" if error else ("BUSY" if busy else "OK")
    print(f"  {offset:6d}  {name:20s} {plc_name:26s} 0x{byte0:02X}  {done!s:>5s} {busy!s:>5s} {error!s:>6s} 0x{status_word:04X}    {result:>6s}")


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
print("DB1 (MBValueTemp) 主站通信状态解析 - 水泵项目")
print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
print(f"读取: DB{DB_NUMBER}, {DB_SIZE} 字节 (20个设备 x 4字节)")
print("配置来源: configs/status_waterpump_db1.yaml")
print("=" * 100)

try:
    data = bytes(client.db_read(DB_NUMBER, 0, DB_SIZE))

    # ============================================================
    # 1. 系统通信负载 (Offset 0)
    # ============================================================
    print()
    print("--- [1/4] 系统通信负载 (Offset 0) ---")
    print()
    byte0, done, busy, error, status_word = parse_status(data, 0)
    result = "ERROR" if error else ("BUSY" if busy else "OK")
    print(f"  原始: Byte0 = 0x{byte0:02X} ({byte0:08b}b)  StatusWord = 0x{status_word:04X} ({status_word})")
    print(f"  解析: Done={done}  Busy={busy}  Error={error}")
    print(f"  判定: {result}")

    # ============================================================
    # 2. 电表主站状态 (12个, Offset 4-48)
    # ============================================================
    print()
    print("--- [2/4] 电表主站状态 (12个, Offset 4-48, 步进4字节) ---")
    print()
    print_table_header()
    for offset, name, plc_name, category in DEVICES:
        if category != "meter":
            continue
        byte0, done, busy, error, status_word = parse_status(data, offset)
        print_table_row(offset, name, plc_name, byte0, done, busy, error, status_word)

    # ============================================================
    # 3. 压力主站状态 (1个, Offset 52)
    # ============================================================
    print()
    print("--- [3/4] 压力主站状态 (1个, Offset 52) ---")
    print()
    for offset, name, plc_name, category in DEVICES:
        if category != "press":
            continue
        byte0, done, busy, error, status_word = parse_status(data, offset)
        result = "ERROR" if error else ("BUSY" if busy else "OK")
        print(f"  原始: Byte0 = 0x{byte0:02X} ({byte0:08b}b)  StatusWord = 0x{status_word:04X} ({status_word})")
        print(f"  解析: Done={done}  Busy={busy}  Error={error}")
        print(f"  判定: {result}")

    # ============================================================
    # 4. 震动主站状态 (6个, Offset 56-76)
    # ============================================================
    print()
    print("--- [4/4] 震动主站状态 (6个, Offset 56-76, 步进4字节) ---")
    print()
    print_table_header()
    for offset, name, plc_name, category in DEVICES:
        if category != "vib":
            continue
        byte0, done, busy, error, status_word = parse_status(data, offset)
        print_table_row(offset, name, plc_name, byte0, done, busy, error, status_word)

    # ============================================================
    # 汇总
    # ============================================================
    print()
    print("--- 汇总 ---")
    ok_count = 0
    err_count = 0
    for offset, name, plc_name, category in DEVICES:
        byte0, done, busy, error, status_word = parse_status(data, offset)
        if error:
            err_count += 1
        else:
            ok_count += 1
    print(f"  总计: {len(DEVICES)}  正常: {ok_count}  故障: {err_count}")

    # ============================================================
    # 原始数据 Hex Dump
    # ============================================================
    print()
    print("--- 原始数据 (每行16字节) ---")
    for i in range(0, DB_SIZE, 16):
        chunk = data[i:min(i + 16, DB_SIZE)]
        hex_fmt = " ".join([f"{b:02X}" for b in chunk])
        print(f"  {i:3d}: {hex_fmt}")

except Exception as e:
    print(f"读取 DB1 失败: {e}")
    import traceback
    traceback.print_exc()

client.disconnect()
print()
print("=" * 100)
print("读取完成")
print("=" * 100)
input("按回车键退出...")
