from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DbSession

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live():
    """Liveness: the process is up. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health")
def health(db: DbSession):
    """Readiness: includes a real database round-trip. Returns 503 if the DB is unreachable."""
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
    return {"status": "ok", "database": "up"}
