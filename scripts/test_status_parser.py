#!/usr/bin/env python3
"""
测试 DB1 状态解析器和轮询服务
"""
import sys
import struct
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.plc.parser_status import parse_status_db, is_device_comm_ok, DEVICE_STATUS_MAP


print("=" * 60)
print("测试 DB1 状态解析器")
print("=" * 60)

# 生成测试数据 (56 字节)
test_db1 = bytearray(56)

# 设置各设备状态
test_cases = {
    "comm_module": (0, 0x01, 0),      # DONE=1, 正常
    "pump_meter_1": (4, 0x01, 0),     # DONE=1, 正常
    "pump_meter_2": (8, 0x02, 0),     # BUSY=1, 繁忙
    "pump_meter_3": (12, 0x04, 0x8001),  # ERROR=1, 错误
    "pump_meter_4": (16, 0x01, 0),    # DONE=1, 正常
    "pump_meter_5": (20, 0x01, 0),    # DONE=1, 正常
    "pump_meter_6": (24, 0x01, 0),    # DONE=1, 正常
    "pump_pressure": (52, 0x01, 0),   # DONE=1, 正常
}

for device_id, (offset, status_byte, status_word) in test_cases.items():
    test_db1[offset] = status_byte
    test_db1[offset+2:offset+4] = struct.pack(">H", status_word)

# 解析
result = parse_status_db(bytes(test_db1))

print("\n 设备状态解析结果:")
print("-" * 60)

for device_id in DEVICE_STATUS_MAP.keys():
    if device_id in result:
        status = result[device_id]
        icon = "" if status["comm_state"] == "ok" else (
            "⏳" if status["comm_state"] == "busy" else ""
        )
        print(f"  {icon} {device_id:20} | "
              f"DONE={status['done']:1} BUSY={status['busy']:1} ERROR={status['error']:1} | "
              f"STATUS=0x{status['status']:04X} | {status['comm_state']}")

print("-" * 60)
summary = result.get("summary", {})
print(f"📈 汇总: 总计={summary['total_devices']} | "
      f"正常={summary['ok_count']} | 错误={summary['error_count']} | "
      f"繁忙={summary['busy_count']}")
print(f"   全部正常: {' 是' if summary['all_ok'] else ' 否'}")

print("\n" + "=" * 60)
print("测试 is_device_comm_ok() 函数")
print("=" * 60)

for device_id in ["pump_meter_1", "pump_meter_2", "pump_meter_3"]:
    status = result[device_id]
    ok = is_device_comm_ok(status)
    print(f"  {device_id}: comm_ok = {ok}")

print("\n 测试完成!")
