#!/bin/bash
set -e
echo "Installing dependencies with uv..."
uv sync
echo "Starting Hermes Agent on port 8765..."
uv run python agent.py
