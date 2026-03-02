@echo off
chcp 65001 >nul
echo ============================================================
echo DB1 主站通信状态 (水泵项目)
echo ============================================================
"%~dp0..\python\python.exe" "%~dp0parse_db1_master_status.py"
pause
