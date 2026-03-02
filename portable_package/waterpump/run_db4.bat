@echo off
chcp 65001 >nul
echo ============================================================
echo DB4 振动传感器数据 (水泵项目)
echo ============================================================
"%~dp0..\python\python.exe" "%~dp0parse_db4_vibration.py"
pause
