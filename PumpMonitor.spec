# -*- mode: python ; coding: utf-8 -*-

import os, sys, glob

# snap7.dll: 自动定位，找不到时不中断打包
_snap7_dll_candidates = glob.glob(
    os.path.join(sys.prefix, 'Lib', 'site-packages', 'snap7', 'lib', 'snap7.dll')
) + glob.glob(
    os.path.join(sys.prefix, 'Lib', 'site-packages', 'snap7', '**', 'snap7.dll'),
)
_snap7_binaries = [(_snap7_dll_candidates[0], 'snap7/lib')] if _snap7_dll_candidates else []

# 仅当 .env 存在时才打进内置资源 (部署时根目录 .env 优先)
_env_datas = [('.env', '.')] if os.path.exists('.env') else []

# 1. 分析阶段
a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_snap7_binaries,
    datas=[
        ('configs', 'configs'),
        ('data', 'data'),
        ('asserts', 'asserts'),
        ('tests/mock/mock_data_generator.py', 'tests/mock'),
    ] + _env_datas,
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn', 'fastapi',
        'uvicorn.logging',
        'uvicorn.loops', 'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan', 'uvicorn.lifespan.on',
        'starlette', 'pydantic',
        'websockets', 'websockets.legacy', 'websockets.legacy.server',
        # PyQt5 (系统托盘)
        'PyQt5', 'PyQt5.sip',
        # Snap7 (PLC通信)
        'snap7',
        'snap7.client', 'snap7.common', 'snap7.util', 'snap7.error',
        'snap7.type',      # snap7 2.x
        'snap7.types',     # snap7 1.x
        # InfluxDB
        'influxdb_client', 'influxdb_client.client', 'influxdb_client.client.write_api',
        # 报警模块
        'app.core.alarm_store',
        'app.services.alarm_checker',
        'app.services.threshold_service',
        # 其他
        'psutil', 'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks/pyi_rth_snap7.py'],
    excludes=['sqlalchemy', 'tests'],
    noarchive=False,
    optimize=0,
)

# 2. 打包阶段
pyz = PYZ(a.pure)

# 3. onedir 模式: exclude_binaries=True, 由 COLLECT 收集
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PumpMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 4. 收集所有文件到 dist/PumpMonitor/ 目录
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PumpMonitor',
)

# 5. 打包后处理: 复制用户可编辑文件到根目录
import shutil
from pathlib import Path

dist_dir = Path('dist/PumpMonitor')

# 复制 .env 到根目录 (用户可修改, 优先于 _internal/.env)
if Path('.env').exists():
    shutil.copy('.env', dist_dir / '.env')
    print("[打包] 已复制 .env 到根目录")

# 复制 configs/ 到根目录 (用户可修改)
if Path('configs').exists():
    if (dist_dir / 'configs').exists():
        shutil.rmtree(dist_dir / 'configs')
    shutil.copytree('configs', dist_dir / 'configs')
    print("[打包] 已复制 configs/ 到根目录")

# 复制 asserts/ 到根目录 (托盘图标)
if Path('asserts').exists():
    if (dist_dir / 'asserts').exists():
        shutil.rmtree(dist_dir / 'asserts')
    shutil.copytree('asserts', dist_dir / 'asserts')
    print("[打包] 已复制 asserts/ 到根目录")

# 创建 data/ 目录 (存放 cache.db / thresholds.json)
data_dir = dist_dir / 'data'
data_dir.mkdir(exist_ok=True)
# 复制 thresholds.json 默认配置
if Path('data/thresholds.json').exists():
    shutil.copy('data/thresholds.json', data_dir / 'thresholds.json')
print("[打包] 已创建 data/ 目录")

# 创建 logs/ 目录
(dist_dir / 'logs').mkdir(exist_ok=True)
print("[打包] 已创建 logs/ 目录")

print("\n[打包完成] 目录结构:")
print("  dist/PumpMonitor/")
print("  |- PumpMonitor.exe       # 主程序")
print("  |- .env                  # 配置文件 (用户可修改)")
print("  |- configs/              # 设备配置 (用户可修改)")
print("  |- asserts/              # 图标资源")
print("  |- data/                 # 数据目录")
print("  |- logs/                 # 日志目录")
print("  |- _internal/            # PyInstaller 内部文件 (不要修改)")
