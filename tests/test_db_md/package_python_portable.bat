@echo off
chcp 65001 >nul
echo ========================================
echo 打包 Python 可移植环境
echo ========================================
echo.

set OUTPUT_DIR=python_portable_waterpump
set PYTHON_VERSION=3.12

echo [1/5] 检查 Python 版本...
python --version
if errorlevel 1 (
    echo 错误: 未找到 Python
    pause
    exit /b 1
)

echo.
echo [2/5] 创建输出目录...
if exist %OUTPUT_DIR% rmdir /s /q %OUTPUT_DIR%
mkdir %OUTPUT_DIR%

echo.
echo [3/5] 复制 Python 运行时...
where python >python_path.txt
set /p PYTHON_PATH=<python_path.txt
del python_path.txt

for %%i in ("%PYTHON_PATH%") do set PYTHON_DIR=%%~dpi
echo Python 目录: %PYTHON_DIR%

xcopy /E /I /Y "%PYTHON_DIR%*" "%OUTPUT_DIR%\python\"

echo.
echo [4/5] 安装依赖到可移植环境...
%OUTPUT_DIR%\python\python.exe -m pip install --upgrade pip
%OUTPUT_DIR%\python\python.exe -m pip install python-snap7

echo.
echo [5/5] 创建启动脚本...

REM 创建 DB1 启动脚本
echo @echo off > %OUTPUT_DIR%\run_parse_db1.bat
echo chcp 65001 ^>nul >> %OUTPUT_DIR%\run_parse_db1.bat
echo set SCRIPT_DIR=%%~dp0 >> %OUTPUT_DIR%\run_parse_db1.bat
echo %%SCRIPT_DIR%%python\python.exe %%SCRIPT_DIR%%parse_db1_master_status.py >> %OUTPUT_DIR%\run_parse_db1.bat
echo pause >> %OUTPUT_DIR%\run_parse_db1.bat

REM 创建 DB2 启动脚本
echo @echo off > %OUTPUT_DIR%\run_parse_db2.bat
echo chcp 65001 ^>nul >> %OUTPUT_DIR%\run_parse_db2.bat
echo set SCRIPT_DIR=%%~dp0 >> %OUTPUT_DIR%\run_parse_db2.bat
echo %%SCRIPT_DIR%%python\python.exe %%SCRIPT_DIR%%parse_db2_sensor_data.py >> %OUTPUT_DIR%\run_parse_db2.bat
echo pause >> %OUTPUT_DIR%\run_parse_db2.bat

REM 创建 DB3 启动脚本
echo @echo off > %OUTPUT_DIR%\run_parse_db3.bat
echo chcp 65001 ^>nul >> %OUTPUT_DIR%\run_parse_db3.bat
echo set SCRIPT_DIR=%%~dp0 >> %OUTPUT_DIR%\run_parse_db3.bat
echo %%SCRIPT_DIR%%python\python.exe %%SCRIPT_DIR%%parse_db3_slave_status.py >> %OUTPUT_DIR%\run_parse_db3.bat
echo pause >> %OUTPUT_DIR%\run_parse_db3.bat

echo.
echo [完成] 打包完成！
echo.
echo 输出目录: %OUTPUT_DIR%
echo.
echo 请将整个 %OUTPUT_DIR% 文件夹复制到工控机
echo 然后双击 run_parse_db1.bat / run_parse_db2.bat / run_parse_db3.bat 运行
echo.
pause







