"""
Windows 工控机部署检查清单
用于验证所有关键点都已配置正确
"""
import sys
import subprocess
import psutil
import os
from pathlib import Path


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major == 3 and version.minor >= 8:
        print(f"✅ Python 版本: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python 版本过低: {version.major}.{version.minor}.{version.micro} (需要 ≥ 3.8)")
        return False


def check_dependencies():
    """检查依赖库"""
    required = ['fastapi', 'uvicorn', 'influxdb-client', 'snap7', 'psutil']
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
            print(f"✅ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"❌ {pkg} 未安装")
    
    if missing:
        print(f"\n运行: pip install {' '.join(missing)}")
        return False
    
    return True


def check_influxdb():
    """检查 InfluxDB 是否运行"""
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=ceramic-influxdb', '--format', '{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if 'Up' in result.stdout:
            print("✅ InfluxDB 正在运行")
            return True
        else:
            print("❌ InfluxDB 未运行 (请执行 docker-compose up -d)")
            return False
    except Exception as e:
        print(f"⚠️ 无法检查 InfluxDB 状态: {e}")
        return False


def check_disk_space():
    """检查磁盘空间"""
    disk = psutil.disk_usage('/')
    free_gb = disk.free / (1024**3)
    
    if free_gb > 10:
        print(f"✅ 磁盘空间充足: {free_gb:.1f} GB 可用")
        return True
    else:
        print(f"⚠️ 磁盘空间不足: 仅剩 {free_gb:.1f} GB (建议 > 10 GB)")
        return False


def check_firewall():
    """检查 Windows 防火墙（仅提示）"""
    print("⚠️ 手动检查: Windows 防火墙需要放行以下端口:")
    print("   - 8081 (FastAPI)")
    print("   - 8086 (InfluxDB)")
    print("   - 102 (PLC S7 通信)")
    return True


def check_directories():
    """检查必要目录"""
    dirs = ['logs', 'data']
    
    for d in dirs:
        if not os.path.exists(d):
            os.makedirs(d)
            print(f"✅ 创建目录: {d}/")
        else:
            print(f"✅ 目录存在: {d}/")
    
    return True


def check_config():
    """检查配置文件"""
    if not os.path.exists('.env'):
        print("⚠️ 缺少 .env 配置文件")
        print("   请执行: cp .env.example .env")
        print("   然后编辑 .env 修改以下参数:")
        print("   - PLC_IP (PLC IP 地址)")
        print("   - INFLUX_TOKEN (InfluxDB Token)")
        return False
    else:
        print("✅ .env 配置文件存在")
        return True


def check_service_installed():
    """检查是否已安装为 Windows 服务"""
    try:
        result = subprocess.run(
            ['sc', 'query', 'CeramicWaterpumpBackend'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if 'RUNNING' in result.stdout:
            print("✅ Windows 服务已安装并运行")
            return True
        elif 'STOPPED' in result.stdout:
            print("⚠️ Windows 服务已安装但未运行")
            print("   执行: nssm start CeramicWaterpumpBackend")
            return True
        else:
            print("⚠️ 未安装为 Windows 服务")
            print("   建议执行: .\\install_as_service.ps1 (需管理员权限)")
            return False
    except Exception as e:
        print(f"⚠️ 无法检查服务状态: {e}")
        return False


def main():
    """运行所有检查"""
    print("=" * 60)
    print("🔍 Windows 工控机部署检查")
    print("=" * 60)
    print()
    
    checks = [
        ("Python 版本", check_python_version),
        ("依赖库", check_dependencies),
        ("InfluxDB", check_influxdb),
        ("磁盘空间", check_disk_space),
        ("防火墙", check_firewall),
        ("目录结构", check_directories),
        ("配置文件", check_config),
        ("Windows 服务", check_service_installed),
    ]
    
    results = []
    
    for name, check_func in checks:
        print(f"\n【{name}】")
        try:
            passed = check_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ 检查失败: {e}")
            results.append((name, False))
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 检查结果总结")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✅" if passed else "❌"
        print(f"{status} {name}")
    
    print()
    print(f"通过: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n🎉 所有检查通过！系统已就绪。")
    else:
        print("\n⚠️ 部分检查未通过，请根据提示修复后重新检查。")


if __name__ == "__main__":
    main()
