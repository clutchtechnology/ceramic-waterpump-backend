#!/usr/bin/env python3
# ============================================================
# 文件说明: mock_polling_service.py - 水泵房模拟轮询服务
# ============================================================
# 功能:
# 1. 模拟PLC轮询，生成符合DB块结构的原始数据
# 2. 使用与正式代码相同的解析器和转换器
# 3. 将数据写入InfluxDB
# 4. 每5秒轮询一次
#
# 使用方法:
#   python tests/mock/mock_polling_service.py
#
# 停止方法:
#   Ctrl+C
# ============================================================

import sys
import os
import asyncio
import signal
from datetime import datetime, timezone
from typing import Dict, Any

# 添加项目根目录到路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from mock_data_generator import MockDataGenerator
from config import get_settings
from app.core.influxdb import write_point, check_influx_health
from app.plc.parser_status import parse_status_db, parse_device_status, DEVICE_STATUS_MAP
from app.plc.parser_waterpump import parse_waterpump_db
from app.tools.converter_elec import ElectricityConverter
from app.tools.converter_pressure import PressureConverter
from app.tools.converter_status import StatusConverter

settings = get_settings()

# ============================================================
# 配置
# ============================================================
POLL_INTERVAL = 5  # 轮询间隔 (秒)

# 转换器实例
_elec_conv = ElectricityConverter()
_pres_conv = PressureConverter()
_status_conv = StatusConverter()

# 运行状态
_is_running = True


def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    global _is_running
    print("\n⏹️  收到停止信号，正在退出...")
    _is_running = False


def write_sensor_data(device_id: str, module_type: str, fields: Dict[str, Any], timestamp: datetime):
    """写入传感器数据到 InfluxDB"""
    write_point(
        measurement="sensor_data",
        tags={
            "device_id": device_id,
            "module_type": module_type,
        },
        fields=fields,
        timestamp=timestamp
    )


def write_status_data(device_id: str, status_fields: Dict[str, Any], timestamp: datetime):
    """写入设备状态到 InfluxDB"""
    write_point(
        measurement="device_status",
        tags={
            "device_id": device_id,
        },
        fields=status_fields,
        timestamp=timestamp
    )


def process_db1_status(raw_data: bytes, timestamp: datetime) -> int:
    """处理 DB1 状态数据"""
    count = 0
    
    for device_id, offset in DEVICE_STATUS_MAP.items():
        # 使用 parse_device_status 解析单个设备状态
        status_raw = parse_device_status(raw_data, offset)
        
        # 直接使用 status_raw (已经包含正确的字段)
        status_fields = _status_conv.convert(status_raw)
        
        write_status_data(device_id, status_fields, timestamp)
        count += 1
    
    return count


def process_db2_sensors(raw_data: bytes, timestamp: datetime) -> int:
    """处理 DB2 传感器数据"""
    count = 0
    
    # 解析水泵电表数据
    parsed = parse_waterpump_db(raw_data)
    
    # 遍历电表数据 (meter_1 ~ meter_6)
    for meter_id in [f"meter_{i}" for i in range(1, 7)]:
        if meter_id in parsed and "error" not in parsed[meter_id]:
            elec_fields = _elec_conv.convert(parsed[meter_id])
            if elec_fields:
                write_sensor_data(meter_id, "ElectricityMeter", elec_fields, timestamp)
                count += 1
    
    # 解析压力传感器
    if "pressure" in parsed and "error" not in parsed["pressure"]:
        pressure_fields = _pres_conv.convert(parsed["pressure"])
        if pressure_fields:
            write_sensor_data("pressure_sensor", "PressureSensor", pressure_fields, timestamp)
            count += 1
    
    return count


async def poll_mock_data():
    """模拟轮询主循环"""
    global _is_running
    
    print("=" * 60)
    print(" 水泵房模拟轮询服务启动")
    print("=" * 60)
    print(f" 轮询间隔: {POLL_INTERVAL}秒")
    print(f"📦 DB块: DB1(设备状态), DB2(传感器数据)")
    print(f"🔗 InfluxDB: {settings.influx_url}")
    print(f" Bucket: {settings.influx_bucket}")
    print("=" * 60)
    
    # 检查 InfluxDB 连接
    healthy, msg = check_influx_health()
    if healthy:
        print(f" InfluxDB 连接正常")
    else:
        print(f" InfluxDB 连接异常: {msg}")
        print("   将继续运行，数据可能无法写入")
    
    print("=" * 60)
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    # 初始化数据生成器
    generator = MockDataGenerator()
    
    poll_count = 0
    
    while _is_running:
        try:
            poll_count += 1
            timestamp = datetime.now(timezone.utc)
            
            print(f"\n[{timestamp.strftime('%H:%M:%S')}] 第 {poll_count} 次轮询...")
            
            # 生成所有DB块的模拟数据
            all_db_data = generator.generate_all_db_data()
            
            total_points = 0
            
            # 处理 DB1 状态数据
            db1_data = all_db_data.get(1)
            if db1_data:
                status_count = process_db1_status(db1_data, timestamp)
                total_points += status_count
                print(f"   DB1 (状态): {status_count} 个设备")
            
            # 处理 DB2 传感器数据
            db2_data = all_db_data.get(2)
            if db2_data:
                sensor_count = process_db2_sensors(db2_data, timestamp)
                total_points += sensor_count
                print(f"   DB2 (传感器): {sensor_count} 个数据点")
            
            print(f"   共写入 {total_points} 个数据点")
            
            # 显示设备状态
            device_status = generator.get_device_status()
            running = [k for k, v in device_status.items() if v]
            stopped = [k for k, v in device_status.items() if not v]
            print(f"  🟢 运行中: {', '.join(running) if running else '无'}")
            print(f"  🔴 已停止: {', '.join(stopped) if stopped else '无'}")
            
        except Exception as e:
            print(f"   轮询错误: {e}")
            import traceback
            traceback.print_exc()
        
        # 等待下次轮询
        await asyncio.sleep(POLL_INTERVAL)
    
    print("\n 模拟轮询服务已停止")


def main():
    """主入口"""
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 运行异步轮询
    try:
        asyncio.run(poll_mock_data())
    except KeyboardInterrupt:
        print("\n⏹️  服务已停止")


if __name__ == "__main__":
    main()
