# Hermes Client Agent

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-72%20passed-brightgreen)](tests/)

### Remote machine control agent for the Hermes AI assistant

A lightweight agent that installs on any machine (Windows, Linux, macOS) and lets Hermes control it remotely — shell, files, mouse, keyboard, screenshot, processes — via a simple REST API.

---

## Why?

Hermes is a powerful AI assistant, but it runs on **one** machine. If you want it to interact with your other computers — trigger a build on Windows, test a UI on a laptop, check a process on a server — you have two options:

1. Install Hermes on every machine → heavy, resource-intensive
2. Deploy this lightweight agent → ~100 MB RAM, single command

The agent exposes a REST API. On the Hermes side, a native plugin adds 21 tools (`exec`, `screenshot`, `mouse_click`, etc.) that call this API. Hermes keeps the intelligence, the agent does the execution.

---

## Architecture

```
                        ┌─────────────────────┐
                        │      HERMES          │
                        │  (anywhere: VPS,     │
                        │   LAN, RPi, laptop,  │
                        │   home server...)    │
                        │                      │
                        │  Native plugin       │
                        │  21 tools            │
                        └──────┬──────────────┘
                               │
                    HTTP REST (LAN or VPN)
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  Agent       │   │  Agent       │   │  Agent       │
   │  Windows     │   │  Linux       │   │  macOS       │
   │              │   │              │   │              │
   │  PowerShell  │   │  bash/sh     │   │  zsh/bash    │
   │  Files       │   │  Files       │   │  Files       │
   │  Mouse       │   │  Mouse       │   │  Mouse       │
   │  Keyboard    │   │  Keyboard    │   │  Keyboard    │
   │  Screenshot  │   │  Screenshot  │   │  Screenshot  │
   └──────────────┘   └──────────────┘   └──────────────┘
```

Hermes runs wherever you want. Agents live on target machines. Communication goes over the local network or a VPN (Tailscale, WireGuard). Each agent is independent.

---

## Where to run

| Scenario | Hermes | Agents | Network |
|----------|--------|--------|---------|
| **Home / lab** | NAS, RPi, or old PC | Windows PC, Linux laptop, Mac | LAN (192.168.x.x) |
| **VPS + machines** | VPS (Hetzner, DO...) | Home PCs, servers | VPN (Tailscale/WireGuard) |
| **All-in-one** | Same machine as agents | localhost | 127.0.0.1 |

---

## Features

| Category | Endpoints | Hermes tool |
|----------|-----------|-------------|
| Shell | `POST /exec` | `exec` |
| Files | `GET /file`, `PUT /file`, `POST /file/delete` | `file_read`, `file_write`, `file_delete` |
| Mouse | `POST /mouse/{move,click,doubleclick,scroll}`, `GET /mouse/position` | `mouse_move`, `mouse_click`, `mouse_scroll` |
| Keyboard | `POST /keyboard/{type,press,hotkey}` | `keyboard_type`, `keyboard_press`, `keyboard_hotkey` |
| Windows | `GET /window/{active,list}`, `POST /window/{focus,resize}` | `window_active`, `window_list`, `window_focus` |
| Screenshot | `GET /screenshot` | `screenshot` |
| System | `GET /system`, `GET /processes`, `POST /process/kill` | `system`, `processes` |
| Dashboard | `GET /dashboard`, `GET /dashboard/{logs,errors,exec}` | — |
| API logs | `GET /api/logs`, `GET /api/stats`, `GET /api/logs/export` | — |

Mouse, keyboard, and window endpoints are optional — they depend on `pyautogui` and `pygetwindow`. The agent works without them.

---

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — `pip install uv`

## Installation

### Option A — From source (all OS)

```bash
git clone https://github.com/pascdesel/hermes-client-agent.git
cd hermes-client-agent
cp .env.example .env    # edit your token
uv sync
uv run python agent.py
```

### Option B — Standalone executable (Windows)

Download `hermes-agent.exe` from the [Releases](https://github.com/pascdesel/hermes-client-agent/releases) page and run it. No Python required.

### Option C — Windows installer

```powershell
# Build the executable first, then:
.\scripts\installer.ps1                          # install + auto-start on login
.\scripts\installer.ps1 -InstallService          # also register as Windows service
.\scripts\installer.ps1 -Uninstall               # remove everything
```

---

## Hermes plugin

```bash
cp -r hermes-plugin/ ~/.hermes/plugins/windows-control/
# Edit state.json with each agent's IP and token
# Restart Hermes
```

The plugin auto-discovers agents listed in its configuration and exposes their endpoints as native Hermes tools.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_AGENT_TOKEN` | *(required)* | Shared authentication token |
| `HERMES_AGENT_HOST` | `0.0.0.0` | Listen interface |
| `HERMES_AGENT_PORT` | `8765` | Listen port |
| `HERMES_ALLOWED_PATHS` | `~`, `/home`, `C:\Users\` | File access whitelist |

---

## Security

- Token required in `X-Agent-Token` header — invalid token → 401
- File paths restricted to `HERMES_ALLOWED_PATHS` — path traversal → 403
- Rate limiting: 60 req/min per IP
- **Recommended**: LAN or VPN only (Tailscale is free)
- No built-in HTTPS → use a reverse proxy (nginx, Caddy) if exposing externally

---

## Examples

```bash
# Health check
curl http://localhost:8765/health -H "X-Agent-Token: YOUR_TOKEN"

# Run a command (Windows)
curl -X POST http://agent:8765/exec \
  -H "X-Agent-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":"dir C:\\Users","shell":"cmd"}'

# Run a command (Linux)
curl -X POST http://agent:8765/exec \
  -H "X-Agent-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"command":"ps aux | head -20","shell":"bash"}'

# Take a screenshot
curl http://agent:8765/screenshot \
  -H "X-Agent-Token: YOUR_TOKEN" \
  -o screen.png

# Read dashboard stats
curl http://agent:8765/api/stats -H "X-Agent-Token: YOUR_TOKEN"
```

---

## Development

```bash
uv run pytest tests/ -v       # 72 tests
python scripts/build_exe.py   # → dist/hermes-agent.exe
uv run ruff check .           # lint
uv run ruff format .          # format
```

---

## Roadmap

- [x] Windows agent (PowerShell, files, screenshot, mouse, keyboard)
- [x] Built-in web dashboard with audit logging
- [x] System tray icon (Windows)
- [x] Standalone executable (PyInstaller)
- [ ] Native Linux agent (systemd, X11/Wayland screenshot, xdotool)
- [ ] Native macOS agent (launchd, CoreGraphics screenshot)
- [ ] Multi-agent dashboard (unified view of all agents)
- [ ] Ed25519 key-based auth (stronger than bearer token)
- [ ] WebSocket streaming for long-running commands
- [ ] Packaging: `.deb`, `.rpm`, `.pkg`

---

## License

MIT — Pascal de Sélys ([@pascdesel](https://github.com/pascdesel))
