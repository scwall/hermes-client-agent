"""Application configuration loaded from environment variables."""
import os
import logging
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

DEFAULT_TOKEN = "hermes-windows-agent-secret-change-me"
TOKEN = os.environ.get("HERMES_AGENT_TOKEN", DEFAULT_TOKEN)

_ALLOWED_ENV = os.environ.get("HERMES_ALLOWED_PATHS", "")
if _ALLOWED_ENV:
    ALLOWED_PATHS = _ALLOWED_ENV.split(os.pathsep)
else:
    user_home = str(Path.home())
    ALLOWED_PATHS = [os.path.join(user_home, ""), "D:\\"]

HOST = os.environ.get("HERMES_AGENT_HOST", "0.0.0.0")
PORT = int(os.environ.get("HERMES_AGENT_PORT", "8765"))
RATE_LIMIT = 60
RATE_WINDOW = 60

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("hermes-agent")
