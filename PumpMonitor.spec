# -*- mode: python ; coding: utf-8 -*-


import os, sys
_snap7_dll = os.path.join(sys.prefix, 'Lib', 'site-packages', 'snap7', 'lib', 'snap7.dll')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[(_snap7_dll, 'snap7/lib')],
    datas=[('configs', 'configs'), ('data', 'data'), ('.env', '.')],
    hiddenimports=[
        # FastAPI / Uvicorn
        'uvicorn', 'fastapi',
        # PyQt5 (系统托盘)
        'PyQt5',
        # Snap7 (PLC通信) - 同时包含 1.x 和 2.x 的模块
        'snap7', 
        'snap7.client', 
        'snap7.common', 
        'snap7.util', 
        'snap7.error',
        'snap7.type',      # snap7 2.x
        'snap7.types',     # snap7 1.x
        # InfluxDB
        'influxdb_client', 'influxdb_client.client', 'influxdb_client.client.write_api',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks/pyi_rth_snap7.py'],
    excludes=['sqlalchemy'],
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
