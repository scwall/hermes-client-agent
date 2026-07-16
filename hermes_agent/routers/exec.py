"""Shell command execution endpoint — runs cmd.exe or PowerShell, single and batch."""
import logging
import os
import subprocess
import sys
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hermes_agent.security import verify_token

router = APIRouter(tags=["exec"], dependencies=[Depends(verify_token)])
_log = logging.getLogger("hermes-agent")


class ExecRequest(BaseModel):
    """Payload for running a shell command."""

    command: str
    shell: str = "cmd"
    timeout: int = 30


class BatchCommand(BaseModel):
    """A single command within a batch execution request."""

    command: str
    shell: Literal["cmd", "powershell"] = "cmd"
    timeout: int = Field(default=30, ge=1, le=300)


class BatchExecRequest(BaseModel):
    """Payload for running multiple commands sequentially."""

    commands: list[BatchCommand] = Field(..., min_length=1, max_length=20)
    stop_on_error: bool = False


def _decode_output(result: subprocess.CompletedProcess) -> tuple[str, str]:
    """Decode stdout and stderr from a CompletedProcess."""
    try:
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
    except Exception:
        stdout = ""
    try:
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    except Exception:
        stderr = ""
    return stdout, stderr


def _build_shell_args(shell: str, command: str) -> tuple[list[str], str]:
    """Build the platform-appropriate shell invocation.

    On Windows:  'cmd' → cmd.exe /c, 'powershell'/'ps' → powershell -Command
    On Linux:    'cmd'/'powershell'/'ps' → /bin/bash -c,
                 'powershell'/'ps' → pwsh -Command if available, else bash.

    Returns (argv_list, actual_shell_name).
    """
    shell_lower = shell.lower()

    if sys.platform == "win32":
        if shell_lower in ("powershell", "ps"):
            return (["powershell", "-Command", command], "powershell")
        return (["cmd", "/c", command], "cmd")

    if shell_lower in ("powershell", "ps"):
        if os.path.exists("/usr/bin/pwsh"):
            return (["pwsh", "-Command", command], "pwsh")
        if os.path.exists("/snap/bin/pwsh"):
            return (["/snap/bin/pwsh", "-Command", command], "pwsh")
        _log.info("Exec: powershell requested but pwsh not found, falling back to bash")
        return (["bash", "-c", command], "bash (powershell→bash)")

    return (["bash", "-c", command], "bash (cmd→bash)")


def _run_command(command: str, shell: str, timeout: int) -> dict:
    """Run a command and return (stdout, stderr, exit_code, shell).

    On Linux, cmd/powershell shells are automatically mapped to bash.
    """
    _log.debug("exec command=%r shell=%s timeout=%s", command, shell, timeout)
    if not command:
        raise HTTPException(status_code=400, detail="Missing 'command' in request body")
    try:
        cmd_argv, actual_shell = _build_shell_args(shell, command)
        proc = subprocess.run(
            cmd_argv,
            capture_output=True, timeout=timeout,
        )
        stdout, stderr = _decode_output(proc)
        return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode, "shell": actual_shell}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Command timed out after {timeout} seconds", "exit_code": -1, "shell": shell}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1, "shell": shell}


@router.post("/exec", summary="Execute a shell command")
async def exec_command(body: ExecRequest):
    """Run a command via cmd.exe or PowerShell on Windows, bash on Linux.

    On Linux, 'cmd' and 'powershell' shells are automatically mapped to bash.
    The response includes the actual shell used in the 'shell' field.
    Supports a configurable timeout in seconds (default: 30).
    """
    return _run_command(body.command, body.shell, body.timeout)


@router.post("/exec/batch", summary="Execute multiple commands sequentially")
async def exec_batch(request: BatchExecRequest):
    """Execute multiple commands sequentially on the remote machine.

    Returns all results with per-command timing. If stop_on_error is true,
    stops at the first error and skips remaining commands.
    """
    results: list[dict] = []
    total_start = time.perf_counter()

    for i, cmd in enumerate(request.commands):
        start = time.perf_counter()
        result = _run_command(cmd.command, cmd.shell, cmd.timeout)
        duration_ms = int((time.perf_counter() - start) * 1000)
        results.append({
            "index": i,
            "command": cmd.command,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "exit_code": result["exit_code"],
            "shell": result.get("shell", cmd.shell),
            "duration_ms": duration_ms,
        })
        if result["exit_code"] != 0 and request.stop_on_error:
            break

    total_duration_ms = int((time.perf_counter() - total_start) * 1000)
    success_count = sum(1 for r in results if r["exit_code"] == 0)
    error_count = len(results) - success_count

    return {
        "results": results,
        "total_duration_ms": total_duration_ms,
        "success_count": success_count,
        "error_count": error_count,
    }
