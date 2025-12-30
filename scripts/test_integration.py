"""
完整测试脚本 - 验证批量写入、本地缓存、PLC长连接
"""
import asyncio
import time
from datetime import datetime

# 测试配置
TEST_BACKEND_URL = "http://localhost:8081"


async def test_stats_endpoint():
    """测试统计端点"""
    import aiohttp
    
    print("\n=== 测试统计端点 ===")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{TEST_BACKEND_URL}/api/waterpump/stats") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        stats = data.get("data", {})
                        print("✅ 统计端点正常")
                        print(f"  - 轮询次数: {stats.get('polling_count', 0)}")
                        print(f"  - 缓冲区大小: {stats.get('buffer_size', 0)}")
                        print(f"  - InfluxDB写入: {stats.get('influx_write_count', 0)}次")
                        print(f"  - 本地缓存: {stats.get('cache_save_count', 0)}次")
                        print(f"  - 待重试: {stats.get('cache_pending', 0)}点")
                        
                        plc_stats = stats.get('plc_stats', {})
                        print(f"  - PLC连接: {'✅ 已连接' if plc_stats.get('connected') else '❌ 未连接'}")
                        print(f"  - PLC读取: {plc_stats.get('read_count', 0)}次")
                        print(f"  - PLC错误: {plc_stats.get('error_count', 0)}次")
                        print(f"  - PLC重连: {plc_stats.get('reconnect_count', 0)}次")
                        print(f"  - 平均耗时: {plc_stats.get('avg_read_time', 0):.2f}ms")
                        return True
                    else:
                        print(f"❌ API返回失败: {data.get('error')}")
                else:
                    print(f"❌ HTTP状态码: {resp.status}")
        except Exception as e:
            print(f"❌ 请求失败: {e}")
    
    return False


async def test_device_status():
    """测试设备状态端点"""
    import aiohttp
    
    print("\n=== 测试设备状态端点 ===")
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{TEST_BACKEND_URL}/api/waterpump/device_status") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        devices = data.get("data", {}).get("devices", [])
                        print(f"✅ 设备状态正常 (共{len(devices)}个设备)")
                        
                        for dev in devices[:3]:  # 只显示前3个
                            print(f"  - {dev.get('device_id')}: "
                                  f"温度={dev.get('temperature', 0):.1f}°C, "
                                  f"压力={dev.get('pressure', 0):.2f}MPa, "
                                  f"流量={dev.get('flow_rate', 0):.2f}m³/h")
                        
                        if len(devices) > 3:
                            print(f"  ... 等 {len(devices)-3} 个设备")
                        return True
                    else:
                        print(f"❌ API返回失败: {data.get('error')}")
                else:
                    print(f"❌ HTTP状态码: {resp.status}")
        except Exception as e:
            print(f"❌ 请求失败: {e}")
    
    return False


async def test_batch_buffering():
    """测试批量缓冲机制"""
    print("\n=== 测试批量缓冲 (需等待150秒) ===")
    print("说明: 轮询间隔5秒, BATCH_SIZE=30, 预计150秒后第一次批量写入")
    
    import aiohttp
    
    start_time = time.time()
    last_influx_count = 0
    
    async with aiohttp.ClientSession() as session:
        for i in range(35):  # 监控35次 (175秒)
            try:
                async with session.get(f"{TEST_BACKEND_URL}/api/waterpump/stats") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            stats = data.get("data", {})
                            buffer_size = stats.get('buffer_size', 0)
                            influx_count = stats.get('influx_write_count', 0)
                            polling_count = stats.get('polling_count', 0)
                            
                            elapsed = int(time.time() - start_time)
                            print(f"[{elapsed:3d}s] 轮询{polling_count}次, 缓冲{buffer_size}点, "
                                  f"写入{influx_count}次", end="")
                            
                            # 检测到批量写入
                            if influx_count > last_influx_count:
                                print(" ✅ 批量写入触发!")
                                last_influx_count = influx_count
                                if i >= 29:  # 第30次轮询应该触发
                                    return True
                            else:
                                print()
            
            except Exception as e:
                print(f"❌ 监控失败: {e}")
            
            await asyncio.sleep(5)
    
    return False


async def test_local_cache():
    """测试本地缓存 (需要手动停止InfluxDB验证)"""
    print("\n=== 测试本地缓存 ===")
    print("说明: 需要手动 docker stop ceramic-influxdb 来模拟故障")
    print("按回车继续...")
    input()
    
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        # 先获取当前缓存数
        try:
            async with session.get(f"{TEST_BACKEND_URL}/api/waterpump/stats") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success"):
                        stats = data.get("data", {})
                        initial_cache = stats.get('cache_save_count', 0)
                        print(f"当前本地缓存次数: {initial_cache}")
        except:
            pass
        
        print("\n请执行: docker stop ceramic-influxdb")
        print("然后等待30秒观察缓存增长...")
        input("停止InfluxDB后按回车继续监控...")
        
        # 监控缓存增长
        for i in range(10):
            try:
                async with session.get(f"{TEST_BACKEND_URL}/api/waterpump/stats") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success"):
                            stats = data.get("data", {})
                            cache_count = stats.get('cache_save_count', 0)
                            pending = stats.get('cache_pending', 0)
                            
                            print(f"[{i*5}s] 本地缓存: {cache_count}次 (待重试{pending}点)")
                            
                            if cache_count > initial_cache:
                                print("✅ 本地缓存机制正常工作!")
                                print("\n请执行: docker start ceramic-influxdb")
                                print("等待系统自动重试缓存数据...")
                                return True
            except:
                pass
            
            await asyncio.sleep(5)
    
    return False


async def main():
    """主测试流程"""
    print("=" * 60)
    print("陶瓷车间水泵房后端 - 完整测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 测试1: 统计端点
    stats_ok = await test_stats_endpoint()
    
    # 测试2: 设备状态
    status_ok = await test_device_status()
    
    # 测试3: 批量缓冲
    print("\n是否测试批量缓冲? (需等待150秒) [y/N]: ", end="")
    if input().lower() == 'y':
        batch_ok = await test_batch_buffering()
    else:
        print("跳过批量缓冲测试")
        batch_ok = None
    
    # 测试4: 本地缓存
    print("\n是否测试本地缓存? (需手动停止InfluxDB) [y/N]: ", end="")
    if input().lower() == 'y':
        cache_ok = await test_local_cache()
    else:
        print("跳过本地缓存测试")
        cache_ok = None
    
    # 总结
    print("\n" + "=" * 60)
    print("测试结果总结:")
    print(f"  ✅ 统计端点: {'通过' if stats_ok else '失败'}")
    print(f"  ✅ 设备状态: {'通过' if status_ok else '失败'}")
    print(f"  {'✅' if batch_ok else '⏭️ '} 批量缓冲: {'通过' if batch_ok else '跳过' if batch_ok is None else '失败'}")
    print(f"  {'✅' if cache_ok else '⏭️ '} 本地缓存: {'通过' if cache_ok else '跳过' if cache_ok is None else '失败'}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
