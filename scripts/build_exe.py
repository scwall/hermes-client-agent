"""Build a standalone Windows executable with PyInstaller via uv."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"> {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(cwd))


def main() -> None:
    """Ensure uv + dependencies, then build the standalone .exe."""
    try:
        subprocess.run(["uv", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("uv not found. Install it: pip install uv")
        sys.exit(1)

    project_root = Path(__file__).resolve().parent.parent

    print("Installing dependencies...")
    _run(["uv", "sync"], project_root)

    templates_src = project_root / "hermes_agent" / "templates"
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    for d in (dist_dir, build_dir):
        if d.exists():
            shutil.rmtree(d)
    for spec in project_root.glob("*.spec"):
        spec.unlink()

    icon_arg = []
    for p in [project_root / "icon.ico", project_root / "hermes_agent" / "icon.ico"]:
        if p.exists():
            icon_arg = ["--icon", str(p)]
            break

    sep = ";" if sys.platform == "win32" else ":"
    templates_dst = "hermes_agent/templates"
    entry = str(project_root / "agent.py")

    cmd = [
        "uv", "run", "pyinstaller",
        "--onefile",
        "--console",
        "--name", "hermes-agent",
        "--clean",
        "--noconfirm",
        "--hidden-import", "pystray",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageDraw",
        "--hidden-import", "PIL.ImageFont",
        "--hidden-import", "jinja2",
        "--hidden-import", "jinja2.ext",
        "--hidden-import", "jinja2.nodes",
        "--hidden-import", "jinja2.utils",
        "--hidden-import", "hermes_agent",
        "--hidden-import", "hermes_agent.routers",
        "--hidden-import", "hermes_agent.routers.dashboard",
        "--hidden-import", "hermes_agent.routers.exec",
        "--hidden-import", "hermes_agent.routers.file",
        "--hidden-import", "hermes_agent.routers.mouse",
        "--hidden-import", "hermes_agent.routers.keyboard_",
        "--hidden-import", "hermes_agent.routers.windows",
        "--hidden-import", "hermes_agent.routers.processes",
        "--hidden-import", "hermes_agent.routers.system",
        "--hidden-import", "hermes_agent.routers.screenshot",
        "--hidden-import", "hermes_agent.routers.capabilities",
        "--add-data", f"{templates_src}{sep}{templates_dst}",
    ]
    cmd.extend(icon_arg)
    cmd.append(entry)

    _run(cmd, project_root)

    exe = dist_dir / "hermes-agent.exe"
    if exe.exists():
        print(f"\nBuild successful: {exe}")
        print(f"Size: {exe.stat().st_size / 1024 / 1024:.1f} MiB")
    else:
        print("\nBuild failed: .exe not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
