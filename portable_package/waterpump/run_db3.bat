@echo off
chcp 65001 >nul
echo ============================================================
echo DB3 从站通信状态 (水泵项目)
echo ============================================================
"%~dp0..\python\python.exe" "%~dp0parse_db3_slave_status.py"
pause
