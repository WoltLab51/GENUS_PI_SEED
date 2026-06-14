@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy_to_pi.ps1" %*
exit /b %ERRORLEVEL%
