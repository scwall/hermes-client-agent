#!/usr/bin/env python3
"""
Local CI/CD runner — executes tests in Docker containers like GitHub Actions.

Equivalent to: act -j test --container-architecture linux/amd64
Without Docker: falls back to local execution.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_FILES = ["tests/test_linux_compat.py", "tests/test_tray.py"]
EXCLUDE_TESTS = [
    "test_opencode_installed",
    "test_valid_config_parsed",
    "test_invalid_config_returns_error",
    "test_openapi_json",
    "test_log_dashboard_accessible",
    "test_api_logs_returns_list",
]

LINUX_IMAGE = "python:3.13-slim"
WINDOWS_IMAGE = "python:3.13-windowsservercore"  # only works on Windows hosts


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _pull_image(image: str) -> bool:
    print(f"  Pulling {image}...")
    r = subprocess.run(["docker", "pull", image], cwd=ROOT, capture_output=True)
    return r.returncode == 0


def _run_in_docker(image: str, commands: list[str], timeout: int = 300) -> tuple[int, str, float]:
    """Run commands inside a Docker container, return (exit_code, output, elapsed_seconds)."""
    script = "set -e\n" + "\n".join(commands)
    script_path = ROOT / ".ci_script.sh"
    script_path.write_text(script)

    container_name = f"hermes-ci-{os.getpid()}"
    start = time.time()

    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "-v", f"{ROOT}:/workspace",
        "-w", "/workspace",
        image,
        "bash", "/workspace/.ci_script.sh",
    ]

    try:
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + "\n" + result.stderr
        return result.returncode, output, time.time() - start
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        return 1, "TIMEOUT", time.time() - start
    finally:
        script_path.unlink(missing_ok=True)


def run_local() -> dict:
    """Run tests locally (no containers)."""
    print("\n=== MODE: Local (pas de Docker) ===\n")
    results = {}

    start = time.time()
    r = subprocess.run(["uv", "sync", "--group", "dev"], cwd=ROOT, capture_output=True, timeout=120)
    results["install"] = {"rc": r.returncode, "elapsed": time.time() - start}
    if r.returncode != 0:
        results["install"]["error"] = r.stderr[:500]
        return results

    ignore_args = []
    for f in EXCLUDE_FILES:
        ignore_args.extend(["--ignore", f])
    k_expr = " and ".join(f"not {t}" for t in EXCLUDE_TESTS)

    start = time.time()
    r = subprocess.run(
        ["uv", "run", "pytest", "tests/", "-v", "--tb=short", *ignore_args, "-k", k_expr],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    results["tests"] = {"rc": r.returncode, "elapsed": time.time() - start, "output": r.stdout[-2000:]}
    if r.returncode != 0:
        results["tests"]["error"] = r.stderr[-1000:] if r.stderr else ""

    start = time.time()
    r = subprocess.run(
        ["uv", "run", "ruff", "check", "hermes_agent/", "windows_control/"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    results["lint"] = {"rc": r.returncode, "elapsed": time.time() - start}
    if r.returncode != 0:
        results["lint"]["output"] = r.stdout[-1000:]

    return results


def run_linux_docker() -> dict:
    """Run tests inside a Linux Docker container."""
    print(f"\n=== MODE: Docker Linux ({LINUX_IMAGE}) ===\n")

    if not _docker_available():
        print("  Docker not available — falling back to local")
        return run_local()

    print("  Installing uv and dependencies, then running tests + lint inside container...\n")
    commands = [
        "pip install uv -q",
        "uv sync --group dev",
        "uv run pytest tests/ -v --tb=short "
        + " ".join(f"--ignore={f}" for f in EXCLUDE_FILES)
        + ' -k "'
        + " and ".join(f"not {t}" for t in EXCLUDE_TESTS)
        + '"',
        "uv run ruff check hermes_agent/ windows_control/",
    ]

    rc, output, elapsed = _run_in_docker(LINUX_IMAGE, commands)
    return {"docker_linux": {"rc": rc, "elapsed": elapsed, "output": output[-3000:]}}


def run_windows_docker() -> dict:
    """Run tests inside a Windows Docker container (only works on Windows hosts)."""
    if sys.platform != "win32":
        return {"docker_windows": {"rc": 0, "note": "skipped (Windows containers require Windows host)"}}

    print(f"\n=== MODE: Docker Windows ({WINDOWS_IMAGE}) ===\n")

    if not _docker_available():
        return {"docker_windows": {"rc": 1, "error": "Docker not available"}}

    commands = [
        "pip install uv -q",
        "uv sync --group dev",
        f"uv run pytest tests/ -v --tb=short --ignore={EXCLUDE_FILES[0]} --ignore={EXCLUDE_FILES[1]} -k \"{' and '.join(f'not {t}' for t in EXCLUDE_TESTS)}\"",
        "uv run ruff check hermes_agent/ windows_control/",
    ]

    rc, output, elapsed = _run_in_docker(WINDOWS_IMAGE, commands, timeout=600)
    return {"docker_windows": {"rc": rc, "elapsed": elapsed, "output": output[-3000:]}}


def print_results(results: dict):
    all_pass = True
    print(f"\n{'=' * 60}")
    print("  CI RESULTS")
    print(f"{'=' * 60}")
    for step, info in results.items():
        rc = info.get("rc", -1)
        elapsed = info.get("elapsed", 0)
        status = "✓" if rc == 0 else "✗"
        note = info.get("note", "")
        if note:
            print(f"  {status} {step}: {note}")
        elif rc == 0:
            print(f"  {status} {step}: passed ({elapsed:.0f}s)")
        else:
            print(f"  {status} {step}: FAILED (rc={rc}, {elapsed:.0f}s)")
            all_pass = False
            err = info.get("error", "") or info.get("output", "")
            if err:
                print(f"    {err[:500]}")
    print(f"{'=' * 60}")
    if all_pass:
        print("  ✓ ALL CHECKS PASSED — ready to push")
    else:
        print("  ✗ SOME CHECKS FAILED")
    print(f"{'=' * 60}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Local CI/CD runner")
    parser.add_argument("--docker", action="store_true", help="Run in Docker containers")
    parser.add_argument("--linux", action="store_true", help="Run Linux Docker only")
    parser.add_argument("--windows", action="store_true", help="Run Windows Docker only")
    parser.add_argument("--all", action="store_true", help="Run all platforms (local + docker)")
    args = parser.parse_args()

    results = {}

    if args.all or (not args.docker and not args.linux and not args.windows):
        results.update(run_local())

    if args.all or args.docker or args.linux:
        results.update(run_linux_docker())

    if args.all or args.docker or args.windows:
        results.update(run_windows_docker())

    print_results(results)

    all_ok = all(info.get("rc", -1) == 0 for info in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
