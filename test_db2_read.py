"""
测试 DB2 块读取 - 诊断工具
"""

import snap7
from snap7.util import get_real, get_int

# PLC 连接配置
PLC_IP = "192.168.50.224"
PLC_RACK = 0
PLC_SLOT = 1

def test_db2_read():
    """测试 DB2 块读取"""
    
    print(f"正在连接 PLC: {PLC_IP}...")
    client = snap7.client.Client()
    
    try:
        client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
        
        if not client.get_connected():
            print("连接失败！")
            return
        
        print("连接成功！")
        
        # 测试 1: 尝试读取 DB2 的前 4 字节
        print("\n测试 1: 读取 DB2 前 4 字节...")
        try:
            data = client.db_read(2, 0, 4)
            print(f"成功！数据: {data.hex()}")
        except Exception as e:
            print(f"失败: {e}")
            return
        
        # 测试 2: 尝试读取 DB2 的前 100 字节
        print("\n测试 2: 读取 DB2 前 100 字节...")
        try:
            data = client.db_read(2, 0, 100)
            print(f"成功！数据长度: {len(data)} 字节")
        except Exception as e:
            print(f"失败: {e}")
        
        # 测试 3: 尝试读取 DB2 的前 200 字节
        print("\n测试 3: 读取 DB2 前 200 字节...")
        try:
            data = client.db_read(2, 0, 200)
            print(f"成功！数据长度: {len(data)} 字节")
        except Exception as e:
            print(f"失败: {e}")
        
        # 测试 4: 尝试读取 DB2 的前 222 字节（S7 协议最大值）
        print("\n测试 4: 读取 DB2 前 222 字节...")
        try:
            data = client.db_read(2, 0, 222)
            print(f"成功！数据长度: {len(data)} 字节")
        except Exception as e:
            print(f"失败: {e}")
        
        # 测试 5: 尝试读取 DB2 的 1034 字节（您的配置）
        print("\n测试 5: 读取 DB2 全部 1034 字节...")
        try:
            data = client.db_read(2, 0, 1034)
            print(f"成功！数据长度: {len(data)} 字节")
        except Exception as e:
            print(f"失败: {e}")
            print("建议: 使用分块读取")
        
        # 测试 6: 尝试读取其他 DB 块（验证是否只有 DB2 有问题）
        print("\n测试 6: 读取 DB1 前 4 字节（对比测试）...")
        try:
            data = client.db_read(1, 0, 4)
            print(f"成功！数据: {data.hex()}")
        except Exception as e:
            print(f"失败: {e}")
        
    finally:
        client.disconnect()
        print("\n已断开连接")


if __name__ == "__main__":
    test_db2_read()

