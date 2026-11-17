"""Explainability endpoints."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbSession
from app.services import explain as explain_service

router = APIRouter(prefix="/projects/{project_id}/experiments/{experiment_id}/explain", tags=["explain"])


class LocalIn(BaseModel):
    features: dict


@router.get("/global")
def global_explain(project_id: uuid.UUID, experiment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return explain_service.explain_global(db, user.id, project_id, experiment_id)


@router.post("/local")
def local_explain(project_id: uuid.UUID, experiment_id: uuid.UUID, body: LocalIn, user: CurrentUser, db: DbSession):
    return explain_service.explain_local(db, user.id, project_id, experiment_id, body.features)


@router.get("/dependence/{feature}")
def dependence_explain(project_id: uuid.UUID, experiment_id: uuid.UUID, feature: str, user: CurrentUser, db: DbSession):
    return explain_service.explain_dependence(db, user.id, project_id, experiment_id, feature)
