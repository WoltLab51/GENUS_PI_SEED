@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_pi_status_key.ps1" %*
exit /b %ERRORLEVEL%
