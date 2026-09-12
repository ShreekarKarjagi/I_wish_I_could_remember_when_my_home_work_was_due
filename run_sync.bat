@echo off
REM Runs the sync and appends output to sync.log next to the script.
cd /d "%~dp0"
where uv >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    uv run sync.py >> sync.log 2>&1
) else if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run sync.py >> sync.log 2>&1
) else (
    "%~dp0.venv\Scripts\python.exe" sync.py >> sync.log 2>&1
)
