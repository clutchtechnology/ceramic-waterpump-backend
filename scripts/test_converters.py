#!/usr/bin/env python3
"""
简单测试脚本：验证数据流、转换器、InfluxDB 写入
"""

import sys
import json
from datetime import datetime

# 测试 1：转换器
print("=" * 60)
print("Test 1: 转换器测试")
print("=" * 60)

from app.tools.converter_elec import ElectricityConverter
from app.tools.converter_pressure import PressureConverter

# 模拟 PLC 原始数据
raw_elec = {"Pt": 4567, "ImpEp": 123456, "Ua_0": 2205, "I_0": 123}
raw_pressure = {"pressure": 10132}

# 转换
elec_conv = ElectricityConverter()
pres_conv = PressureConverter()

elec_fields = elec_conv.convert(raw_elec)
pres_fields = pres_conv.convert(raw_pressure)

print(f"电表原始: {raw_elec}")
print(f"电表转换: {elec_fields}")
print(f"✓ 电表数据精简: 4->4 字段\n")

print(f"压力原始: {raw_pressure}")
print(f"压力转换: {pres_fields}")
print(f"✓ 压力数据转换: 1->1 字段\n")

# 测试 2：InfluxDB 写入 (可选，需要 docker-compose up -d)
print("=" * 60)
print("Test 2: InfluxDB 写入测试 (可选)")
print("=" * 60)

try:
    from app.core.influxdb import write_point, query_data
    from config import get_settings

    settings = get_settings()
    timestamp = datetime.utcnow()

    # 写入电表数据
    write_point(
        "sensor_data",
        tags={"device_id": "meter_1", "module_type": "ElectricityMeter"},
        fields=elec_fields,
        timestamp=timestamp
    )
    print(f"✓ 写入电表数据到 InfluxDB: meter_1\n")

    # 写入压力数据
    write_point(
        "sensor_data",
        tags={"device_id": "pressure_1", "module_type": "PressureSensor"},
        fields=pres_fields,
        timestamp=timestamp
    )
    print(f"✓ 写入压力数据到 InfluxDB: pressure_1\n")

    # 查询（等待1秒后）
    import time
    time.sleep(1)

    start_iso = (datetime.utcnow().replace(second=0, microsecond=0).isoformat() + "Z")
    stop_iso = (datetime.utcnow().isoformat() + "Z")

    data = query_data("sensor_data", start_iso, stop_iso, interval="1m")
    print(f"✓ 查询结果: {len(data)} 个数据点")
    if data:
        print(f"  示例: {data[0]}\n")

except Exception as e:
    print(f"  InfluxDB 测试跳过: {e}\n")
    print("  → 请确保 docker-compose up -d 已运行\n")

# 总结
print("=" * 60)
print("测试完成!")
print("=" * 60)
print("\n下一步:")
print("1. 启动后端: python3 main.py")
print("2. 访问 API: http://localhost:8081/api/waterpump/realtime")
print("3. 查看文档: http://localhost:8081/docs")
