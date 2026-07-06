"""Process listing and management — uses psutil with stdlib fallback."""
import subprocess

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hermes_agent.security import verify_token

try:
    import psutil
except Exception:
    psutil = None

router = APIRouter(tags=["processes"], dependencies=[Depends(verify_token)])


class KillRequest(BaseModel):
    """Payload containing the PID of the process to terminate."""

    pid: int


def _get_process_list() -> list[dict]:
    """Return a list of running processes.

    Uses psutil if available, otherwise falls back to wmic/tasklist on Windows
    or basic subprocess-based enumeration.
    """
    if psutil is not None:
        return _psutil_process_list()
    return _basic_process_list()


def _psutil_process_list() -> list[dict]:
    """Enumerate processes using psutil with pid, name, cpu, and memory info."""
    procs = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = proc.info
            mem = info.get("memory_info")
            mem_bytes = mem.rss if mem else 0
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "memory_bytes": mem_bytes,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return procs


def _basic_process_list() -> list[dict]:
    """Fallback process enumeration using wmic (Windows) or ps-like commands."""
    procs = []
    try:
        output = subprocess.check_output(
            ["wmic", "process", "get", "ProcessId,Name,WorkingSetSize", "/format:csv"],
            timeout=10,
        ).decode("utf-8", errors="replace")
        for line in output.strip().split("\n")[2:]:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                try:
                    pid = int(parts[2])
                    name = parts[3]
                    mem_str = parts[1]
                    mem = int(mem_str) if mem_str.isdigit() else 0
                    procs.append({"pid": pid, "name": name, "memory_bytes": mem})
                except (ValueError, IndexError):
                    continue
    except Exception:
        try:
            output = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"], timeout=10,
            ).decode("utf-8", errors="replace")
            for line in output.strip().split("\n"):
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                        name = parts[0]
                        procs.append({"pid": pid, "name": name, "memory_bytes": 0})
                    except ValueError:
                        continue
        except Exception:
            pass
    return procs


@router.get("/processes", summary="List all running processes")
async def processes_list():
    """Return a JSON array of running processes with pid, name, memory, and CPU."""
    return {"processes": _get_process_list()}


@router.post("/process/kill", summary="Kill a process by PID")
async def process_kill(body: KillRequest):
    """Terminate the process identified by the given PID."""
    pid = body.pid
    if psutil is not None:
        return _kill_with_psutil(pid)
    return _kill_with_taskkill(pid)


def _kill_with_psutil(pid: int) -> dict:
    """Kill a process using psutil (preferred method)."""
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except psutil.TimeoutExpired:
            proc.kill()
        return {"pid": pid, "killed": True, "message": f"Process {pid} terminated"}
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail=f"No process with PID {pid}")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail=f"Access denied: cannot kill PID {pid}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _kill_with_taskkill(pid: int) -> dict:
    """Kill a process using the Windows taskkill command."""
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, timeout=10,
        )
        return {"pid": pid, "killed": True, "message": f"Process {pid} terminated"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
