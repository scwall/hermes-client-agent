# Hermes Windows Control Plugin

Native Hermes plugin for remote PC control via HTTP REST API.

22 tools: shell, files, mouse, keyboard, windows, screenshot, open_app, processes, system.

## Changelog

### v1.1.0
- Default timeout reduced from 30s to 15s
- Screenshot requests use 10s timeout
- UTF-8 encoding forced via `chcp 65001` on every exec
- Error responses now include the response body (up to 500 chars)
- New tool: `windows_open_app` — launches an app then brings its window to front

### v1.0.0
- Initial release with 21 tools

See README in main repo for full docs.
