#!/bin/bash
# Run locally — mirrors .github/workflows/tests.yml
set -e
echo "=== Install ===" && uv sync --group dev
echo "=== Tests ===" && uv run pytest tests/ -v --tb=short \
  --ignore=tests/test_linux_compat.py \
  --ignore=tests/test_tray.py \
  -k "not (test_opencode_installed or test_valid_config_parsed or test_invalid_config_returns_error or test_openapi_json or test_log_dashboard_accessible or test_api_logs_returns_list)"
echo "=== Lint ===" && uv run ruff check hermes_agent/ windows_control/
echo "=== DONE ==="
