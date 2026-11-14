"""Deployment & prediction endpoints."""
import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.services import deployments as deployment_service

router = APIRouter(prefix="/projects/{project_id}", tags=["deployments"])


class DeployIn(BaseModel):
    config: dict = Field(default_factory=dict)


class PredictIn(BaseModel):
    features: dict
    request_id: str | None = Field(default=None, max_length=64)


@router.post("/models/{model_id}/versions/{version_id}/deploy", status_code=201)
def deploy(project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, body: DeployIn, user: CurrentUser, db: DbSession):
    return deployment_service.deploy_version(db, user.id, project_id, model_id, version_id, body.config)


@router.get("/deployments")
def list_deployments(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return deployment_service.list_deployments(db, user.id, project_id)


@router.get("/deployments/{deployment_id}")
def get_deployment(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return deployment_service.get_deployment(db, user.id, project_id, deployment_id)


@router.post("/deployments/{deployment_id}/stop")
def stop_deployment(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return deployment_service.stop_deployment(db, user.id, project_id, deployment_id)


@router.post("/deployments/{deployment_id}/predict")
def predict(project_id: uuid.UUID, deployment_id: uuid.UUID, body: PredictIn, user: CurrentUser, db: DbSession):
    return deployment_service.predict(db, user.id, project_id, deployment_id, body.features, body.request_id)


@router.get("/deployments/{deployment_id}/predictions")
def prediction_history(project_id: uuid.UUID, deployment_id: uuid.UUID, user: CurrentUser, db: DbSession,
                       limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return deployment_service.prediction_history(db, user.id, project_id, deployment_id, limit, offset)
