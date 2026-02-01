"""打包脚本 - 将托盘应用打包为 Windows 可执行文件。

使用方法:
    1. 安装 PyInstaller: pip install pyinstaller
    2. 运行此脚本: python scripts/build_exe.py
    
或者直接运行 PyInstaller 命令:
    pyinstaller --name="水泵房监测系统" --windowed --onefile --icon=scripts/app.ico main.py
"""
import subprocess
import sys
from pathlib import Path

WORKDIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = WORKDIR / "scripts"
DIST_DIR = WORKDIR / "dist"

# PyInstaller 配置
APP_NAME = "PumpMonitor"
MAIN_SCRIPT = WORKDIR / "main.py"
ICON_FILE = SCRIPTS_DIR / "app.ico"  # 可选：自定义图标


def check_pyinstaller() -> bool:
    """检查 PyInstaller 是否已安装。"""
    try:
        import PyInstaller
        return True
    except ImportError:
        return False


def install_pyinstaller() -> None:
    """安装 PyInstaller。"""
    print("正在安装 PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_exe() -> None:
    """执行打包。"""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name", APP_NAME,
        "--windowed",           # 不显示控制台窗口
        "--onefile",            # 打包成单个 exe 文件
        "--noconfirm",          # 覆盖已有输出
        "--clean",              # 清理临时文件
        # 添加隐式导入（PyQt5 相关）
        "--hidden-import", "PyQt5.sip",
        "--hidden-import", "psutil",
        # uvicorn 和 fastapi 相关
        "--hidden-import", "uvicorn",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "fastapi",
        "--hidden-import", "pydantic",
        "--hidden-import", "starlette",
        "--hidden-import", "yaml",
        "--hidden-import", "influxdb_client",
        # websockets 支持
        "--hidden-import", "websockets",
        "--hidden-import", "websockets.legacy",
        "--hidden-import", "websockets.legacy.server",
        # 添加数据文件
        "--add-data", f"{WORKDIR / 'configs'};configs",
        "--add-data", f"{WORKDIR / 'data'};data",
    ]
    
    # 如果有自定义图标，添加图标参数
    if ICON_FILE.exists():
        cmd.extend(["--icon", str(ICON_FILE)])
    
    cmd.append(str(MAIN_SCRIPT))
    
    print("=" * 50)
    print("开始打包...")
    print(f"命令: {' '.join(cmd)}")
    print("=" * 50)
    
    subprocess.check_call(cmd, cwd=str(WORKDIR))
    
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if exe_path.exists():
        print("=" * 50)
        print(f"✅ 打包成功！")
        print(f"📁 输出文件: {exe_path}")
        print(f"📏 文件大小: {exe_path.stat().st_size / 1024 / 1024:.2f} MB")
        print("=" * 50)
    else:
        print("❌ 打包失败，请检查错误信息")


def main() -> None:
    if not check_pyinstaller():
        install_pyinstaller()
    
    build_exe()


if __name__ == "__main__":
    main()
