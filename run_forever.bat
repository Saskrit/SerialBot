@echo off
title Serial Bot
cd /d "%~dp0"

:loop
echo [%date% %time%] Starting bot...
python bot.py
echo [%date% %time%] Bot exited. Restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop
