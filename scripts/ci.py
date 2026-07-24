#!/usr/bin/env python3
"""Local CI runner — mirrors .github/workflows/tests.yml without pushing to GitHub."""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_FILES = [
    "tests/test_linux_compat.py",
    "tests/test_tray.py",
]
EXCLUDE_TESTS = [
    "test_opencode_installed",
    "test_valid_config_parsed",
    "test_invalid_config_returns_error",
    "test_openapi_json",
    "test_log_dashboard_accessible",
    "test_api_logs_returns_list",
]


def run(cmd: list[str], timeout: int = 120) -> tuple[int, float]:
    print(f"\n{'=' * 60}")
    print(f"  {' '.join(cmd[:4])}{'...' if len(cmd) > 4 else ''}")
    print(f"{'=' * 60}\n")
    start = time.time()
    result = subprocess.run(cmd, cwd=ROOT, timeout=timeout)
    elapsed = time.time() - start
    return result.returncode, elapsed


def main() -> int:
    print(f"CI Runner — {ROOT.name}")
    print(f"Platform: {sys.platform}  Python: {sys.version.split()[0]}")

    failures = 0

    rc, elapsed = run(
        ["uv", "sync", "--group", "dev"],
        timeout=120,
    )
    if rc != 0:
        print("✗ Install failed")
        return 1

    ignore_args = []
    for f in EXCLUDE_FILES:
        ignore_args.extend(["--ignore", f])
    k_expr = " and ".join(f"not {t}" for t in EXCLUDE_TESTS)

    rc, elapsed = run(
        ["uv", "run", "pytest", "tests/", "-v", "--tb=short", *ignore_args, "-k", k_expr],
        timeout=180,
    )
    if rc == 0:
        print(f"\n✓ Tests passed ({elapsed:.0f}s)")
    else:
        failures += 1

    rc, elapsed = run(
        ["uv", "run", "ruff", "check", "hermes_agent/", "windows_control/"],
        timeout=60,
    )
    if rc == 0:
        print(f"\n✓ Lint passed ({elapsed:.0f}s)")
    else:
        failures += 1

    print(f"\n{'=' * 60}")
    if failures == 0:
        print("  ✓ ALL CHECKS PASSED — ready to push")
    else:
        print(f"  ✗ {failures} step(s) FAILED")
    print(f"{'=' * 60}\n")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
