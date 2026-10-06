@echo off
setlocal DisableDelayedExpansion
if not defined PLUGIN_ROOT (
  echo Patpat hook error: PLUGIN_ROOT is missing. 1>&2
  exit /b 2
)
if not defined PLUGIN_DATA (
  echo Patpat hook error: PLUGIN_DATA is missing. 1>&2
  exit /b 2
)
set "_PATPAT_SCRIPT=%PLUGIN_ROOT%\hooks\scripts\patpat_loop_state.py"
if not exist "%_PATPAT_SCRIPT%" (
  echo Patpat hook error: hook script is missing under PLUGIN_ROOT. 1>&2
  exit /b 3
)
if not defined SystemRoot (
  echo Patpat hook error: SystemRoot is missing. 1>&2
  exit /b 3
)
set "_PATPAT_SYSTEM32=%SystemRoot%\System32"
if not exist "%_PATPAT_SYSTEM32%\where.exe" (
  echo Patpat hook error: Windows where.exe is missing from System32. 1>&2
  exit /b 3
)
cd /d "%_PATPAT_SYSTEM32%" || exit /b 3
set "_PATPAT_PY="
for /f "delims=" %%P in ('"%_PATPAT_SYSTEM32%\where.exe" py.exe 2^>nul') do if not defined _PATPAT_PY set "_PATPAT_PY=%%~fP"
if defined _PATPAT_PY (
  "%_PATPAT_PY%" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
  if not errorlevel 1 goto run_py
)
:check_python
set "_PATPAT_PY="
for /f "delims=" %%P in ('"%_PATPAT_SYSTEM32%\where.exe" python.exe 2^>nul') do if not defined _PATPAT_PY set "_PATPAT_PY=%%~fP"
if not defined _PATPAT_PY goto no_runtime
"%_PATPAT_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
if not errorlevel 1 goto run_python
echo Patpat hook error: Python 3.11 or newer is required. 1>&2
exit /b 3
:run_py
"%_PATPAT_PY%" -3 "%_PATPAT_SCRIPT%"
exit /b %ERRORLEVEL%
:run_python
"%_PATPAT_PY%" "%_PATPAT_SCRIPT%"
exit /b %ERRORLEVEL%
:no_runtime
echo Patpat hook error: no supported Python 3.11+ runtime found; install Python and ensure py.exe or python.exe is on PATH. 1>&2
exit /b 127
