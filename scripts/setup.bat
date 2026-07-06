@echo off
echo Installing dependencies with uv...
uv sync
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: uv sync failed. Is uv installed? Run: pip install uv
    pause
    exit /b 1
)
echo Dependencies installed successfully.
echo Run: uv run python agent.py
