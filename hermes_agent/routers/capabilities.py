"""Public capabilities and health endpoints."""
from fastapi import APIRouter

from hermes_agent.modules import get_endpoints, get_modules

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities", summary="List available modules and endpoints")
async def capabilities():
    """Return installed optional modules and the corresponding available API endpoints."""
    return {
        "modules": get_modules(),
        "endpoints": sorted(get_endpoints()),
    }
