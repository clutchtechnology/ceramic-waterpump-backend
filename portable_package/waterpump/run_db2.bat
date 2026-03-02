@echo off
chcp 65001 >nul
echo ============================================================
echo DB2 传感器数据 (水泵项目)
echo ============================================================
"%~dp0..\python\python.exe" "%~dp0parse_db2_sensor_data.py"
pause
