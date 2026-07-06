"""Shell command execution endpoint — runs cmd.exe or PowerShell."""

import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes_agent.security import verify_token

router = APIRouter(tags=["exec"], dependencies=[Depends(verify_token)])


class ExecRequest(BaseModel):
    """Payload for running a shell command."""

    command: str
    shell: str = "cmd"
    timeout: int = 30


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


@router.post("/exec", summary="Execute a shell command")
async def exec_command(body: ExecRequest):
    """Run a command via cmd.exe or PowerShell, returning stdout, stderr, and exit code.

    Supports a configurable timeout in seconds (default: 30).
    """
    if not body.command:
        raise HTTPException(status_code=400, detail="Missing 'command' in request body")
    try:
        if body.shell.lower() in ("powershell", "ps"):
            proc = subprocess.run(
                ["powershell", "-Command", body.command],
                capture_output=True, timeout=body.timeout,
            )
        else:
            proc = subprocess.run(
                ["cmd", "/c", body.command],
                capture_output=True, timeout=body.timeout,
            )
        stdout, stderr = _decode_output(proc)
        return {"stdout": stdout, "stderr": stderr, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {body.timeout} seconds",
            "exit_code": -1,
        }
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "exit_code": -1}
