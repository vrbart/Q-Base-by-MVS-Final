@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR:~0,-1%"
set "API_HOST=127.0.0.1"
set "API_PORT=11435"
set "QB_UI_URL=http://127.0.0.1:%API_PORT%/v3/ui"
set "QB_VALIDATE_SCRIPT=%REPO_DIR%\validate_qb_multi_instance.ps1"
set "QB_LANE_MANAGER=%REPO_DIR%\scripts\codex_multi_manager.ps1"
set "CCBS_PYTHONPATH=%REPO_DIR%\src"

if defined PYTHONPATH (
  set "CCBS_PYTHONPATH=%CCBS_PYTHONPATH%;%PYTHONPATH%"
)
set "PYTHONPATH=%CCBS_PYTHONPATH%"

echo === Q-launch: QB All-in-One Startup ===
echo Repo: %REPO_DIR%\
echo.

call :ResolvePython
if errorlevel 1 (
  echo [ERROR] Python runtime not found. Expected .venv-clean\Scripts\python.exe or a valid py/python fallback.
  exit /b 1
)

echo [STEP] Optimization precheck ^(capabilities status^)...
"%PY_EXE%" %PY_ARGS% -m ccbs_app.cli capabilities status
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] Capabilities status reported issues. Continuing startup.
)

call :StartOrRestartApi
if errorlevel 1 (
  echo [ERROR] API startup failed. Check the "QB API" terminal window.
  exit /b 1
)

if /I not "%Q_LAUNCH_SKIP_VALIDATE%"=="1" (
  call :RunQbValidation
) else (
  echo [INFO] Validation skipped because Q_LAUNCH_SKIP_VALIDATE=1.
)

if /I not "%Q_LAUNCH_SKIP_LANES%"=="1" (
  call :LaunchQbLanes
) else (
  echo [INFO] Lane launch skipped because Q_LAUNCH_SKIP_LANES=1.
)

if /I not "%Q_LAUNCH_SKIP_BROWSER%"=="1" (
  start "" "%QB_UI_URL%"
  echo [OK] Opened %QB_UI_URL%
) else (
  echo [INFO] Browser launch skipped because Q_LAUNCH_SKIP_BROWSER=1.
)

echo [DONE] Q-launch completed.
exit /b 0

:StartOrRestartApi
call :GetApiPid
if defined API_PID (
  call :CheckApiHealth
  if "!API_HEALTHY!"=="1" (
    if /I "%Q_LAUNCH_FORCE_API_RESTART%"=="1" (
      echo [INFO] API already running on port %API_PORT% ^(PID !API_PID!^). Restarting because Q_LAUNCH_FORCE_API_RESTART=1...
    ) else (
      echo [INFO] API already healthy on port %API_PORT% ^(PID !API_PID!^). Reusing existing process.
      exit /b 0
    )
  ) else (
    echo [WARN] Port %API_PORT% in use ^(PID !API_PID!^) but /health failed. Restarting API process...
  )
  taskkill /PID !API_PID! /F >nul 2>&1
  timeout /t 1 >nul
)

echo [STEP] Starting QB API server...
start "QB API" cmd /k "cd /d ""%REPO_DIR%"" && set ""PYTHONPATH=%CCBS_PYTHONPATH%"" && ""%PY_EXE%"" %PY_ARGS% -m ccbs_app.cli ai api serve --host %API_HOST% --port %API_PORT%"

set "API_READY=0"
for /L %%I in (1,1,25) do (
  timeout /t 1 >nul
  call :CheckApiHealth
  if "!API_HEALTHY!"=="1" (
    set "API_READY=1"
    goto start_api_done
  )
)

:start_api_done
if "!API_READY!"=="1" (
  echo [OK] API healthy on http://%API_HOST%:%API_PORT%/health
  exit /b 0
)
echo [ERROR] API did not become healthy within timeout.
exit /b 1

:RunQbValidation
if not exist "%QB_VALIDATE_SCRIPT%" (
  echo [WARN] QB validation skipped: missing %QB_VALIDATE_SCRIPT%
  exit /b 0
)

echo [STEP] Running QB validation with secure local token store...
set "QB_VALIDATE_LOG=%TEMP%\q_launch_validate_%RANDOM%%RANDOM%.log"
powershell -NoProfile -ExecutionPolicy Bypass -File "%QB_VALIDATE_SCRIPT%" >"%QB_VALIDATE_LOG%" 2>&1
set "QB_VALIDATE_RC=%ERRORLEVEL%"
type "%QB_VALIDATE_LOG%"
if not "%QB_VALIDATE_RC%"=="0" (
  echo [ERROR] QB validation failed. Configure secure token with: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\set_qb_api_token.ps1
  del /q "%QB_VALIDATE_LOG%" >nul 2>&1
  exit /b 1
)
echo [OK] QB validation reported no endpoint failures.
del /q "%QB_VALIDATE_LOG%" >nul 2>&1
exit /b 0

:LaunchQbLanes
if not exist "%QB_LANE_MANAGER%" (
  echo [WARN] Lane launch skipped: missing %QB_LANE_MANAGER%
  exit /b 0
)
echo [STEP] Syncing and launching QB lanes...
powershell -NoProfile -ExecutionPolicy Bypass -File "%QB_LANE_MANAGER%" -Action sync-workspaces
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] sync-workspaces reported issues.
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%QB_LANE_MANAGER%" -Action launch
if not "%ERRORLEVEL%"=="0" (
  echo [WARN] launch reported issues.
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%QB_LANE_MANAGER%" -Action status
exit /b 0

:GetApiPid
set "API_PID="
for /f %%P in ('powershell -NoProfile -Command "$x=Get-NetTCPConnection -LocalPort %API_PORT% -State Listen -ErrorAction SilentlyContinue ^| Select-Object -First 1 -ExpandProperty OwningProcess; if($x){$x}"') do (
  set "API_PID=%%P"
)
exit /b 0

:CheckApiHealth
set "API_HEALTHY=0"
powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://%API_HOST%:%API_PORT%/health' -TimeoutSec 2; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if "%ERRORLEVEL%"=="0" set "API_HEALTHY=1"
exit /b 0

:ResolvePython
set "PY_EXE="
set "PY_ARGS="

set "VENV_CLEAN=%REPO_DIR%\.venv-clean\Scripts\python.exe"
if exist "%VENV_CLEAN%" (
  call :TryPython "%VENV_CLEAN%"
  if not errorlevel 1 exit /b 0
)

where py >nul 2>&1
if "%ERRORLEVEL%"=="0" (
  call :TryPython "py"
  if not errorlevel 1 exit /b 0
)

where python >nul 2>&1
if "%ERRORLEVEL%"=="0" (
  call :TryPython "python"
  if not errorlevel 1 exit /b 0
)

where python3 >nul 2>&1
if "%ERRORLEVEL%"=="0" (
  call :TryPython "python3"
  if not errorlevel 1 exit /b 0
)

exit /b 1

:TryPython
setlocal EnableDelayedExpansion
set "_EXE=%~1"
set "_FOUND="

if /i "%_EXE%"=="py" (
  for %%V in (3.12 3.11 3.10 3.9 3) do (
    for /f "delims=" %%P in ('py -%%V -c "import sys; print(sys.executable)" 2^>nul') do (
      if exist "%%P" (
        set "_FOUND=%%P"
        goto :TryPythonDone
      )
    )
  )
  goto :TryPythonDone
)

"%_EXE%" -c "import sys" >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%P in ('"%_EXE%" -c "import sys; print(sys.executable)" 2^>nul') do (
    if exist "%%P" (
      set "_FOUND=%%P"
      goto :TryPythonDone
    )
  )
)

:TryPythonDone
if not defined _FOUND (
  endlocal & exit /b 1
)
endlocal & set "PY_EXE=%_FOUND%" & set "PY_ARGS=" & exit /b 0
