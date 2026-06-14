@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish_pi_status.ps1" %*
exit /b %ERRORLEVEL%
