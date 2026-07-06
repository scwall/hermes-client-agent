"""System information endpoint — OS, CPU, memory, disks, network."""
import os
import sys
import socket
import platform
from typing import Any

from fastapi import APIRouter, Depends

from hermes_agent.security import verify_token

try:
    import psutil
except Exception:
    psutil = None

router = APIRouter(tags=["system"], dependencies=[Depends(verify_token)])


def _get_local_ip() -> str:
    """Determine the primary local IP by connecting to an external address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _get_network_interfaces() -> dict[str, list[str]]:
    """Return a mapping of interface name to list of IPv4 addresses.

    Uses psutil when available; falls back to Linux ioctl otherwise.
    """
    if psutil is not None:
        result = {}
        for name, addrs in psutil.net_if_addrs().items():
            v4 = [addr.address for addr in addrs if addr.family == socket.AF_INET]
            if v4:
                result[name] = v4
        return result

    result = {}
    try:
        import struct
        import fcntl
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _index, name in socket.if_nameindex():
            try:
                packed = struct.pack("256s", name[:15].encode())
                ifreq = fcntl.ioctl(sock.fileno(), 0x8915, packed)
                ip = socket.inet_ntoa(ifreq[20:24])
                result[name] = [ip]
            except Exception:
                pass
        sock.close()
    except Exception:
        pass
    return result


def _get_system_info() -> dict[str, Any]:
    """Collect hostname, OS, CPU count/usage, memory, disks, local IP, and network interfaces.

    Uses psutil for detailed stats when available; falls back to stdlib for
    basic information.
    """
    info: dict[str, Any] = {
        "hostname": platform.node(),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version,
    }
    if psutil is not None:
        info["cpu_count"] = psutil.cpu_count()
        info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        info["memory_total"] = mem.total
        info["memory_available"] = mem.available
        info["memory_percent"] = mem.percent
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                })
            except Exception:
                continue
        info["disks"] = disks
    else:
        info["cpu_count"] = os.cpu_count() or 0
        info["cpu_percent"] = 0.0
        info["memory_total"] = 0
        info["memory_available"] = 0
        info["memory_percent"] = 0.0
        info["disks"] = []
    info["local_ip"] = _get_local_ip()
    info["network_interfaces"] = _get_network_interfaces()
    return info


@router.get("/system", summary="Get full system information")
async def system_info():
    """Return hostname, OS details, CPU, memory, disk partitions, and local IP."""
    return _get_system_info()
