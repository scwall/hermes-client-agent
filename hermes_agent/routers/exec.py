"""Shell command execution endpoint — runs cmd.exe or PowerShell, single and batch."""
import subprocess
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hermes_agent.security import verify_token

router = APIRouter(tags=["exec"], dependencies=[Depends(verify_token)])


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


def _run_command(command: str, shell: str, timeout: int) -> tuple[str, str, int]:
    """Run a command and return (stdout, stderr, exit_code)."""
    if not command:
        raise HTTPException(status_code=400, detail="Missing 'command' in request body")
    try:
        if shell.lower() in ("powershell", "ps"):
            proc = subprocess.run(
                ["powershell", "-Command", command],
                capture_output=True, timeout=timeout,
            )
        else:
            proc = subprocess.run(
                ["cmd", "/c", command],
                capture_output=True, timeout=timeout,
            )
        stdout, stderr = _decode_output(proc)
        return stdout, stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"Command timed out after {timeout} seconds", -1
    except Exception as e:
        return "", str(e), -1


@router.post("/exec", summary="Execute a shell command")
async def exec_command(body: ExecRequest):
    """Run a command via cmd.exe or PowerShell, returning stdout, stderr, and exit code.

    Supports a configurable timeout in seconds (default: 30).
    """
    stdout, stderr, exit_code = _run_command(body.command, body.shell, body.timeout)
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


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
        stdout, stderr, exit_code = _run_command(cmd.command, cmd.shell, cmd.timeout)
        duration_ms = int((time.perf_counter() - start) * 1000)
        results.append({
            "index": i,
            "command": cmd.command,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        })
        if exit_code != 0 and request.stop_on_error:
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
