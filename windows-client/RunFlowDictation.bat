@echo off
title Flow Dictation Background Service
:loop
echo [Flow Dictation] Starting service...
cd /d "%~dp0"
call venv\Scripts\activate
python src\main.py > startup_out.log 2> startup_err.log
echo [Flow Dictation] Service stopped or crashed. Restarting in 2 seconds...
timeout /t 2 /nobreak >nul
goto loop
