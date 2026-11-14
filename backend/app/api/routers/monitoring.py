"""Model monitoring endpoints."""
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.services import monitoring as monitoring_service

router = APIRouter(prefix="/projects/{project_id}/deployments/{deployment_id}/monitoring", tags=["monitoring"])


class ConfigIn(BaseModel):
    thresholds: dict[str, float] = Field(default_factory=dict)


class RunIn(BaseModel):
    since_run_id: uuid.UUID | None = None


class LabelsIn(BaseModel):
    labels: list[dict] = Field(min_length=1, max_length=1000)


@router.get("/config")
def get_config(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return monitoring_service.get_config(db, user.id, project_id, deployment_id)


@router.put("/config")
def set_config(project_id: uuid.UUID, deployment_id: uuid.UUID, body: ConfigIn, user: CurrentUser, db: DbSession):
    return monitoring_service.set_config(db, user.id, project_id, deployment_id, body.thresholds)


@router.post("/run", status_code=201)
def run_monitoring(project_id: uuid.UUID, deployment_id: uuid.UUID, body: RunIn, user: CurrentUser, db: DbSession):
    return monitoring_service.run_monitoring(db, user.id, project_id, deployment_id, body.since_run_id)


@router.get("/runs")
def list_runs(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession,
              limit: int = Query(20, ge=1, le=100)):
    return monitoring_service.list_runs(db, user.id, project_id, deployment_id, limit)


@router.get("/performance")
def performance(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return monitoring_service.performance_history(db, user.id, project_id, deployment_id)


@router.post("/labels")
def ingest_labels(project_id: uuid.UUID, deployment_id: uuid.UUID, body: LabelsIn, user: CurrentUser, db: DbSession):
    return monitoring_service.ingest_labels(db, user.id, project_id, deployment_id, body.labels)
