@echo off
call "%~dp0setup.bat"
echo Starting Hermes Agent on port 8765...
uv run python agent.py
pause
