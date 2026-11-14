"""AI Research Copilot endpoints."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.services import copilot as copilot_service

router = APIRouter(prefix="/projects/{project_id}/copilot", tags=["copilot"])


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ReportIn(BaseModel):
    experiment_id: uuid.UUID | None = None


@router.post("/ask")
def ask(project_id: uuid.UUID, body: AskIn, user: CurrentUser, db: DbSession):
    return copilot_service.ask(db, user.id, project_id, body.question)


@router.post("/report")
def report(project_id: uuid.UUID, body: ReportIn, user: CurrentUser, db: DbSession):
    return copilot_service.research_report(db, user.id, project_id, body.experiment_id)


@router.get("/context")
def context(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    return copilot_service.gather_context(db, project_id)
