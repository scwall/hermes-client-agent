#!/usr/bin/env bash
"""Build a standalone executable with PyInstaller via uv (Linux/macOS)."""
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Installing dependencies with uv..."
uv sync

rm -rf dist build *.spec

ICON=""
for candidate in icon.ico hermes_agent/icon.ico icon.png; do
    if [ -f "$candidate" ]; then
        ICON="--icon $candidate"
        break
    fi
done

TEMPLATES="$ROOT/hermes_agent/templates"

uv run pyinstaller \
    --onefile \
    --name hermes-agent \
    --clean \
    --noconfirm \
    --hidden-import pystray \
    --hidden-import PIL \
    --hidden-import PIL.Image \
    --hidden-import PIL.ImageDraw \
    --hidden-import PIL.ImageFont \
    --hidden-import jinja2 \
    --hidden-import jinja2.ext \
    --hidden-import jinja2.nodes \
    --hidden-import jinja2.utils \
    --hidden-import hermes_agent \
    --hidden-import hermes_agent.routers \
    --hidden-import hermes_agent.routers.dashboard \
    --hidden-import hermes_agent.routers.exec \
    --hidden-import hermes_agent.routers.file \
    --hidden-import hermes_agent.routers.mouse \
    --hidden-import hermes_agent.routers.keyboard_ \
    --hidden-import hermes_agent.routers.windows \
    --hidden-import hermes_agent.routers.processes \
    --hidden-import hermes_agent.routers.system \
    --hidden-import hermes_agent.routers.screenshot \
    --hidden-import hermes_agent.routers.capabilities \
    --add-data "${TEMPLATES}:hermes_agent/templates" \
    $ICON \
    agent.py

echo ""
echo "Build complete: dist/hermes-agent"
ls -lh dist/hermes-agent 2>/dev/null || echo "ERROR: binary not found"
