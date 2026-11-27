@echo off
cd /d "%~dp0"
set "PY=C:\Users\z1900\AppData\Local\Doubao\User Data\sandbox_runtime\bases\772984f6fd3a8ae0ae7d2422cd7c2bfa\python\python.exe"
if not exist "%PY%" set "PY=python"
start "" /min cmd /c "timeout /t 3 /nobreak >nul && start http://127.0.0.1:17860"
"%PY%" server.py
pause