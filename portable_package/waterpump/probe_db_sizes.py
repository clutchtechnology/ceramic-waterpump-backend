# -*- coding: utf-8 -*-
"""探测 PLC 各 DB 块的实际大小 (独立脚本, 无外部依赖)

用途: 当出现 'Address out of range' 错误时，用此脚本确认 PLC 中
      DB1/DB2/DB3/DB4 的实际可读长度，帮助定位配置问题。

方法: 二分法逐步探测每个 DB 块的最大可读字节数
"""

import sys
import time

try:
    import snap7
except ImportError:
    print("snap7 not installed, run: pip install python-snap7")
    sys.exit(1)

# PLC 连接配置 (根据实际情况修改)
PLC_IP = "192.168.50.224"
PLC_RACK = 0
PLC_SLOT = 1

# 需要探测的 DB 块
# (DB号, 名称, 后端代码中配置的大小)
DB_LIST = [
    (1, "MBValueTemp (主站状态)", 80),
    (2, "Data_DB (传感器数据)", 338),
    (3, "DataState (从站状态)", 76),
    (4, "Vibration_DB (振动传感器)", 228),
]


def probe_db_size(client, db_number: int, max_guess: int) -> int:
    """用二分法探测 DB 块的实际可读大小

    Args:
        client: snap7 客户端
        db_number: DB 块号
        max_guess: 猜测的最大值上限

    Returns:
        实际可读的最大字节数 (0 表示完全不可读)
    """
    # 1. 先测试 1 字节是否可读
    try:
        client.db_read(db_number, 0, 1)
    except Exception:
        return 0

    # 2. 先测试 max_guess 是否能完整读取
    try:
        client.db_read(db_number, 0, max_guess)
        return max_guess  # 完整读取成功
    except Exception:
        pass

    # 3. 二分法探测
    low = 1
    high = max_guess
    result = 1

    while low <= high:
        mid = (low + high) // 2
        try:
            client.db_read(db_number, 0, mid)
            result = mid
            low = mid + 1
        except Exception:
            high = mid - 1

    return result


def probe_db_readable_by_chunk(client, db_number: int, max_size: int, chunk: int = 200) -> int:
    """按分块读取方式探测实际可读长度 (模拟后端代码的分块读取逻辑)

    Args:
        client: snap7 客户端
        db_number: DB 块号
        max_size: 最大读取长度
        chunk: 每次读取的块大小

    Returns:
        成功读取到的最大偏移量
    """
    offset = 0
    while offset < max_size:
        read_size = min(chunk, max_size - offset)
        try:
            client.db_read(db_number, offset, read_size)
            offset += read_size
        except Exception:
            # 在此 offset 处失败，再精确探测
            fine_low = offset
            fine_high = offset + read_size
            fine_result = offset
            while fine_low <= fine_high:
                mid = (fine_low + fine_high) // 2
                try:
                    client.db_read(db_number, offset, mid - offset)
                    fine_result = mid
                    fine_low = mid + 1
                except Exception:
                    fine_high = mid - 1
            return fine_result
    return offset


def main():
    client = snap7.client.Client()

    try:
        client.connect(PLC_IP, PLC_RACK, PLC_SLOT)
    except Exception as e:
        print(f"PLC 连接失败: {e}")
        sys.exit(1)

    print("=" * 80)
    print("PLC DB 块大小探测工具")
    print(f"PLC: {PLC_IP}  Rack: {PLC_RACK}  Slot: {PLC_SLOT}")
    print("=" * 80)
    print()

    for db_number, db_name, expected_size in DB_LIST:
        print(f"--- DB{db_number}: {db_name} ---")
        print(f"  后端代码配置大小: {expected_size} 字节")

        # 方法1: 二分法探测
        actual_size = probe_db_size(client, db_number, expected_size + 100)
        print(f"  二分法探测结果:   {actual_size} 字节")

        # 方法2: 分块读取探测 (模拟后端逻辑)
        chunk_size = probe_db_readable_by_chunk(client, db_number, expected_size, chunk=200)
        print(f"  分块读取探测结果: {chunk_size} 字节 (chunk=200)")

        # 判断
        if actual_size >= expected_size:
            print(f"  [OK] DB{db_number} 大小充足 (实际 >= 配置)")
        else:
            print(f"  [ERROR] DB{db_number} 实际大小不足! 配置需要 {expected_size}, 实际只有 {actual_size}")
            print(f"          需要在 PLC 中扩大 DB{db_number} 或修改后端配置")

        # 尝试读取开头数据显示
        try:
            preview_size = min(actual_size, 64)
            if preview_size > 0:
                data = bytes(client.db_read(db_number, 0, preview_size))
                print(f"  前 {preview_size} 字节:")
                for i in range(0, preview_size, 16):
                    hex_str = data[i:min(i + 16, preview_size)].hex().upper()
                    hex_fmt = " ".join([hex_str[j:j + 2] for j in range(0, len(hex_str), 2)])
                    print(f"    {i:3d}: {hex_fmt}")
        except Exception as e:
            print(f"  预览数据读取失败: {e}")

        print()

    # 额外探测: 更大范围 (看 DB2 到底能读多大)
    print("=" * 80)
    print("DB2 扩展探测 (探测到 500 字节)")
    print("=" * 80)
    extended_size = probe_db_size(client, 2, 500)
    print(f"  DB2 最大可读: {extended_size} 字节")

    # 按 100 字节步进测试 DB2
    print()
    print("  DB2 分段可读性测试:")
    for test_offset in range(0, 500, 100):
        test_size = 100
        try:
            client.db_read(2, test_offset, min(test_size, max(0, extended_size - test_offset)))
            print(f"    偏移 {test_offset:4d} - {test_offset + test_size:4d}: OK")
        except Exception:
            print(f"    偏移 {test_offset:4d} - {test_offset + test_size:4d}: FAIL")

    client.disconnect()
    print()
    print("=" * 80)
    print("探测完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
    input("按回车键退出...")
