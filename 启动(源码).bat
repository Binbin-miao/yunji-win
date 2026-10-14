@echo off
rem 云姬设置 (Windows) 源码启动脚本
cd /d "%~dp0"
python app\main.py
if errorlevel 1 pause
