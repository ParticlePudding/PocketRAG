@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download_models.ps1" %*
pause
