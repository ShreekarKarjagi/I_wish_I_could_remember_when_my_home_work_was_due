@echo off
REM Runs the sync and appends output to sync.log next to the script.
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" sync.py >> sync.log 2>&1
