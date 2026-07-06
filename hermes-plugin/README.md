# Hermes Windows Control Plugin

Gives **Hermes Agent** full control over a remote Windows or Linux machine running the **Hermes Client Agent** (FastAPI HTTP server).

## Features

- **21 tools** in the  toolset
- **Multi-agent** — control several machines from one Hermes instance
- **Auto health-check** on session start ( hook)

### Tools

| Category   | Tools |
|------------|-------|
| Shell      |  — PowerShell or CMD with timeout |
| Files      | , ,  |
| Mouse      | , , , ,  |
| Keyboard   | , ,  |
| Windows    | , ,  |
| Screen     |  — full screen or region |
| System     | , ,  |
| Meta       | ,  |

## Installation

### 1. Deploy the Client Agent

On the remote machine (Windows or Linux):



### 2. Install the Plugin

Copy  into your Hermes plugins directory:



### 3. Configure

Edit  with your agent's IP and token:



### 4. Restart Hermes



## Usage

All tools accept an optional  parameter to target a specific machine:



## Security

- Token-based auth via  header
- File access restricted to allowed paths ( in )
- Rate limiting built into the client agent (60 req/min)
- No port exposed to Internet — LAN only

## Requirements

- Hermes Agent (plugin system)
- Python 3.10+ on the remote machine
- Optional: ,  for mouse/keyboard/window control
