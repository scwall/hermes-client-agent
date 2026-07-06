"""File read, write, and delete endpoints — path-restricted."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from hermes_agent.security import verify_token, check_path_allowed

router = APIRouter(tags=["file"], dependencies=[Depends(verify_token)])


class FileWriteRequest(BaseModel):
    """Payload to write content to a file, creating parent directories."""

    path: str
    content: str


class FileDeleteRequest(BaseModel):
    """Payload to delete a file by path."""

    path: str


@router.get("/file", summary="Read a file from disk")
async def file_read(request: Request, path: str = Query(..., description="Absolute path to read")):
    """Return the full text content of the file at the given path.

    The path must be within the allowed directories defined by HERMES_ALLOWED_PATHS.
    """
    check_path_allowed(path, request)
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        return {"path": path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/file", summary="Write content to a file")
async def file_write(request: Request, body: FileWriteRequest):
    """Create or overwrite a file with the given content.

    The path must be within the allowed directories. Parent directories are created automatically.
    """
    if not body.path:
        raise HTTPException(status_code=400, detail="Missing 'path' in request body")
    check_path_allowed(body.path, request)
    try:
        Path(body.path).parent.mkdir(parents=True, exist_ok=True)
        Path(body.path).write_text(body.content, encoding="utf-8")
        return {"path": body.path, "written": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/file/delete", summary="Delete a file")
async def file_delete(request: Request, body: FileDeleteRequest):
    """Delete the file at the given path.

    The path must be within the allowed directories.
    """
    if not body.path:
        raise HTTPException(status_code=400, detail="Missing 'path' in request body")
    check_path_allowed(body.path, request)
    try:
        Path(body.path).unlink()
        return {"path": body.path, "deleted": True}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {body.path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
