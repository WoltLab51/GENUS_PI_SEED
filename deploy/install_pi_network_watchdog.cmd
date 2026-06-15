@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_pi_network_watchdog.ps1" %*
exit /b %ERRORLEVEL%
