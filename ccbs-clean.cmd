@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "VENV_CLI=%ROOT%.venv-clean\Scripts\ccbs-clean.exe"
set "VENV_PY=%ROOT%.venv-clean\Scripts\python.exe"

pushd "%ROOT%" >nul 2>&1

if exist "%VENV_CLI%" (
  "%VENV_CLI%" %*
  set "RC=%ERRORLEVEL%"
  popd >nul 2>&1
  exit /b %RC%
)

if exist "%VENV_PY%" (
  set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
  "%VENV_PY%" -m ccbs_app.cli %*
  set "RC=%ERRORLEVEL%"
  popd >nul 2>&1
  exit /b %RC%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  set "PYTHONPATH=%ROOT%src;%PYTHONPATH%"
  python -m ccbs_app.cli %*
  set "RC=%ERRORLEVEL%"
  popd >nul 2>&1
  exit /b %RC%
)

echo [ERROR] No usable Python launcher found. Expected .venv-clean\Scripts\ccbs-clean.exe or python on PATH.
popd >nul 2>&1
exit /b 1