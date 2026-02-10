# PyInstaller runtime hook for snap7
# 在应用启动前设置 snap7 DLL 搜索路径和模块导入

import os
import sys

if getattr(sys, 'frozen', False):
    # 打包模式: 将 snap7/lib 目录加入 DLL 搜索路径
    _meipass = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    snap7_lib_dir = os.path.join(_meipass, 'snap7', 'lib')

    if os.path.isdir(snap7_lib_dir):
        # 1. 加入 PATH 环境变量
        os.environ['PATH'] = snap7_lib_dir + os.pathsep + os.environ.get('PATH', '')
        # 2. 使用 os.add_dll_directory (Python 3.8+)
        try:
            os.add_dll_directory(snap7_lib_dir)
        except (OSError, AttributeError):
            pass
    
    # 3. 预导入 snap7 子模块，避免运行时找不到
    try:
        import snap7
        import snap7.client
        import snap7.common
        import snap7.util
        import snap7.error
        # 尝试导入 snap7.types (1.x) 或 snap7.type (2.x)
        try:
            import snap7.types
        except (ImportError, AttributeError):
            pass
        try:
            import snap7.type
        except (ImportError, AttributeError):
            pass
    except ImportError:
        pass
