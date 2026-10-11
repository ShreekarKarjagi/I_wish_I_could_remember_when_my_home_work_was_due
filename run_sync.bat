@echo off
REM Runs the sync and appends output to sync.log next to the script.
cd /d "%~dp0"
set PYTHONUTF8=1

REM Roll sync.log over once it passes ~1 MB so it can't grow forever.
if exist sync.log for %%F in (sync.log) do if %%~zF GTR 1048576 move /y sync.log sync.log.1 >nul

REM Pass the sync's exit code through so Task Scheduler's "Last Result" shows failures.
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 goto use_path
if exist "%USERPROFILE%\.local\bin\uv.exe" goto use_home
"%~dp0.venv\Scripts\python.exe" sync.py >> sync.log 2>&1
exit /b %ERRORLEVEL%

:use_path
uv run sync.py >> sync.log 2>&1
exit /b %ERRORLEVEL%

:use_home
"%USERPROFILE%\.local\bin\uv.exe" run sync.py >> sync.log 2>&1
exit /b %ERRORLEVEL%
