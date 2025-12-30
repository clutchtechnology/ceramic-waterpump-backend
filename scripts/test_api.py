#!/usr/bin/env python3
"""
API 接口测试脚本 - 验证 health / realtime / history 接口
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8081"

def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def test_health():
    """测试 Health 接口"""
    print_section("1. Health Check 接口")
    
    endpoints = [
        f"{BASE_URL}/health",
        f"{BASE_URL}/api/waterpump/health"
    ]
    
    for url in endpoints:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"\n✓ {url}")
                print(f"  状态: {data.get('status', 'unknown')}")
                print(f"  InfluxDB: {data.get('components', {}).get('influxdb', 'unknown')}")
                print(f"  轮询服务: {data.get('components', {}).get('polling', 'unknown')}")
                print(f"  时间: {data.get('timestamp', 'N/A')}")
            else:
                print(f"\n✗ {url} - HTTP {response.status_code}")
        except Exception as e:
            print(f"\n✗ {url} - 连接失败: {e}")

def test_realtime():
    """测试 Realtime 接口"""
    print_section("2. Realtime 接口 (实时数据)")
    
    url = f"{BASE_URL}/api/waterpump/realtime"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ {url}")
            print(f"  成功: {data.get('success', False)}")
            print(f"  时间: {data.get('timestamp', 'N/A')}")
            print(f"  设备数: {data.get('device_count', 0)}")
            
            devices = data.get('devices', {})
            if devices:
                print(f"\n  设备数据 ({len(devices)} 个):")
                for device_id, fields in devices.items():
                    print(f"\n    {device_id}:")
                    for field, value in fields.items():
                        print(f"      - {field}: {value}")
            else:
                print("  ⚠️  暂无设备数据 (确保 docker-compose up -d 已运行)")
        else:
            print(f"\n✗ HTTP {response.status_code}")
            print(f"  响应: {response.text}")
    except Exception as e:
        print(f"\n✗ 连接失败: {e}")
        print("  → 请确保后端已启动: python main.py")

def test_history():
    """测试 History 接口（不同聚合度）"""
    print_section("3. History 接口 (历史数据)")
    
    base_url = f"{BASE_URL}/api/waterpump/history"
    
    # 测试 1: 默认参数 (最近1小时, 1分钟聚合)
    print("\n  测试 3.1: 默认参数 (最近1小时, 1分钟聚合)")
    try:
        response = requests.get(base_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ 成功")
            print(f"    数据点数: {data.get('data_points', 0)}")
            if data.get('data'):
                print(f"    首条: {data['data'][0]['timestamp']}")
                print(f"    末条: {data['data'][-1]['timestamp']}")
        else:
            print(f"  ✗ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
    
    # 测试 2: 自定义聚合度 (5分钟)
    print("\n  测试 3.2: 自定义聚合度 (5分钟)")
    try:
        response = requests.get(f"{base_url}?interval=5m", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ 成功")
            print(f"    聚合间隔: {data.get('query', {}).get('interval', 'N/A')}")
            print(f"    数据点数: {data.get('data_points', 0)}")
        else:
            print(f"  ✗ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")
    
    # 测试 3: 自定义时间范围 + 聚合度
    print("\n  测试 3.3: 自定义时间范围 + 聚合度 (1小时聚合)")
    try:
        end = datetime.utcnow()
        start = end - timedelta(hours=6)
        
        params = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "interval": "1h"
        }
        response = requests.get(base_url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ 成功")
            print(f"    开始: {data.get('query', {}).get('start', 'N/A')}")
            print(f"    结束: {data.get('query', {}).get('end', 'N/A')}")
            print(f"    聚合: {data.get('query', {}).get('interval', 'N/A')}")
            print(f"    数据点数: {data.get('data_points', 0)}")
        else:
            print(f"  ✗ HTTP {response.status_code}")
    except Exception as e:
        print(f"  ✗ 失败: {e}")

def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                     水泵房后端 API 接口测试                                  ║
║                  (Waterpump Backend API Test Suite)                        ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    print(f"目标地址: {BASE_URL}")
    print("\n前置条件:")
    print("  1. InfluxDB 已启动: docker-compose up -d")
    print("  2. 后端已启动: python main.py (或 uvicorn main:app)")
    
    test_health()
    test_realtime()
    test_history()
    
    print_section("测试完成")
    print("""
推荐在 Flutter 中调用的接口：

  1️⃣  Health Check
      GET http://192.168.x.x:8081/health
      或 GET http://192.168.x.x:8081/api/waterpump/health

  2️⃣  实时数据 (更新频率: 每5秒)
      GET http://192.168.x.x:8081/api/waterpump/realtime

  3️⃣  历史数据 (查询示例)
      GET http://192.168.x.x:8081/api/waterpump/history
      GET http://192.168.x.x:8081/api/waterpump/history?interval=5m
      GET http://192.168.x.x:8081/api/waterpump/history?start=2025-12-24T00:00:00&end=2025-12-24T12:00:00&interval=1h

更多细节: http://192.168.x.x:8081/docs (Swagger 文档)
    """)

if __name__ == "__main__":
    main()
