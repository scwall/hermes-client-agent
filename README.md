# Hermes Client Agent

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://github.com/scwall/hermes-client-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/scwall/hermes-client-agent/actions/workflows/tests.yml)

### Remote machine control agent for the Hermes AI assistant

A lightweight agent that installs on any machine (Windows, Linux, macOS) and lets Hermes control it remotely — shell, files, mouse, keyboard, screenshot, processes — via a simple REST API.

---

## Why?

Hermes is a powerful AI assistant, but it runs on **one** machine. If you want it to interact with your other computers — trigger a build on Windows, test a UI on a laptop, check a process on a server — you have two options:

1. Install Hermes on every machine → heavy, resource-intensive
2. Deploy this lightweight agent → ~100 MB RAM, single command

The agent exposes a REST API. On the Hermes side, a native plugin adds **22 tools** (`exec`, `screenshot`, `mouse_click`, `open_app`, etc.) that call this API. Hermes keeps the intelligence, the agent does the execution.

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
                        │  windows_control     │
                        │  22 tools            │
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
| Shell | `POST /exec` | `windows_exec` |
| Files | `GET /file`, `GET /file/read`, `PUT /file`, `POST /file/delete` | `windows_file_read`, `windows_file_write`, `windows_file_delete` |
| Mouse | `POST /mouse/{move,click,doubleclick,scroll}`, `GET /mouse/position` | `windows_mouse_move`, `windows_mouse_click`, `windows_mouse_scroll` |
| Keyboard | `POST /keyboard/{type,press,hotkey}` | `windows_keyboard_type`, `windows_keyboard_press`, `windows_keyboard_hotkey` |
| Windows | `GET /window/{active,list}`, `POST /window/{focus,resize}` | `windows_window_active`, `windows_window_list`, `windows_window_focus` |
| App launch | — | `windows_open_app` (launch + focus) |
| Screenshot | `GET /screenshot` | `windows_screenshot` |
| System | `GET /system`, `GET /processes`, `POST /process/kill` | `windows_system`, `windows_processes` |
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
git clone https://github.com/scwall/hermes-client-agent.git
cd hermes-client-agent
cp .env.example .env    # edit your token
uv sync
uv run python agent.py
```

### Option B — Standalone executable (Windows)

Download `hermes-agent.exe` from the [Releases](https://github.com/scwall/hermes-client-agent/releases) page and run it. No Python required.

### Option C — Windows installer

```powershell
# Build the executable first, then:
.\scripts\installer.ps1                          # install + auto-start on login
.\scripts\installer.ps1 -InstallService          # also register as Windows service
.\scripts\installer.ps1 -Uninstall               # remove everything
```

---

## Hermes plugin

The `windows_control/` directory contains a native Hermes plugin that registers 22 tools.

```bash
cp -r windows_control/ <hermes-plugins-dir>/windows_control/
```

### Multi-agent configuration

Configure agents in Hermes' `config.yaml`:

```yaml
windows_control:
  agents:
    laptop:
      url: "http://192.168.1.4:8765"
      token: "${LAPTOP_TOKEN}"
      timeout: 30
    framework:
      url: "http://192.168.1.10:8765"
      token: "${FRAMEWORK_TOKEN}"
      timeout: 15
  default_agent: "laptop"
```

Set tokens in Hermes' `.env`:

```bash
LAPTOP_TOKEN=hermes-windows-agent-secret-change-me
FRAMEWORK_TOKEN=token-pour-framework
```

### Usage

```text
windows_exec {command: "hostname"}              → targets default_agent
windows_exec {command: "hostname", agent: "fw"} → targets framework
```

Restart Hermes after configuration. The plugin logs loaded agents on startup.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_AGENT_TOKEN` | *(required)* | Shared authentication token for API endpoints |
| `HERMES_DASHBOARD_TOKEN` | `HERMES_AGENT_TOKEN` | Optional separate token for dashboard access |
| `HERMES_AGENT_HOST` | `0.0.0.0` | Listen interface |
| `HERMES_AGENT_PORT` | `8765` | Listen port |
| `HERMES_ALLOWED_PATHS` | `~`, `/home`, `C:\Users\` | File access whitelist |

---

## Security

- Token required in `X-Agent-Token` header — invalid token → 401
- Dashboard protected remotely (localhost bypass) via `HERMES_DASHBOARD_TOKEN`
- File paths restricted to `HERMES_ALLOWED_PATHS` — path traversal → 403
- Rate limiting: 60 req/min per IP
- Audit logging: structured JSON Lines log (`logs/audit.jsonl`) with full request/response capture
- Sensitive fields (`password`, `token`, `secret`) masked in console logs
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

# Export audit logs as CSV
curl "http://agent:8765/api/logs/export?format=csv" -H "X-Agent-Token: YOUR_TOKEN" -o logs.csv
```

---

## Development

```bash
uv run pytest tests/ -v       # 135 tests
python scripts/build_exe.py   # → dist/hermes-agent.exe (23.5 MiB)
uv run ruff check .           # lint
uv run ruff format .          # format
```

Run the full endpoint test suite:

```powershell
.\tools\test_endpoints.ps1
```

---

## Roadmap

- [x] Windows agent (PowerShell, files, screenshot, mouse, keyboard)
- [x] Native Hermes plugin — `windows_control` (22 tools)
- [x] Built-in web dashboard with Jinja2 templates and audit logging
- [x] System tray icon — pystray (green/yellow/red status)
- [x] Standalone executable — PyInstaller (23.5 MiB)
- [x] Structured audit log (JSON Lines) with console output
- [x] CSV/JSON log export
- [x] PEP8 clean (ruff, line-length 360)
- [ ] Native Linux agent (systemd, X11/Wayland screenshot, xdotool)
- [ ] Native macOS agent (launchd, CoreGraphics screenshot)
- [ ] Multi-agent dashboard (unified view of all agents)
- [ ] Ed25519 key-based auth (stronger than bearer token)
- [ ] WebSocket streaming for long-running commands
- [ ] Packaging: `.deb`, `.rpm`, `.pkg`

---

## License

MIT — Pascal de Sélys ([@scwall](https://github.com/scwall))
