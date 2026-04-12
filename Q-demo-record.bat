@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "RUNNER=%ROOT%scripts\automate_demo.ps1"

if not exist "%RUNNER%" (
  echo [ERROR] Missing automation runner: %RUNNER%
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%" %*
exit /b %ERRORLEVEL%
