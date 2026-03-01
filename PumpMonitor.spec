# -*- mode: python ; coding: utf-8 -*-


import os, sys, glob

# snap7.dll: 自动定位，找不到时不中断打包（如无 PLC 场景）
_snap7_dll_candidates = glob.glob(
    os.path.join(sys.prefix, 'Lib', 'site-packages', 'snap7', 'lib', 'snap7.dll')
) + glob.glob(
    os.path.join(sys.prefix, 'Lib', 'site-packages', 'snap7', '**', 'snap7.dll'),
)
_snap7_binaries = [(_snap7_dll_candidates[0], 'snap7/lib')] if _snap7_dll_candidates else []

# 仅当 .env 存在时才把它打进包（部署时放在 exe 同级目录，不依赖内置版本）
_env_datas = [('.env', '.')] if os.path.exists('.env') else []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_snap7_binaries,
    datas=[
        ('configs', 'configs'),
        ('data', 'data'),
        ('tests/mock/mock_data_generator.py', 'tests/mock'),  # Mock 模式支持
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
        # Snap7 (PLC通信) - 同时包含 1.x 和 2.x 的模块
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
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
