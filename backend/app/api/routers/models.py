"""Model registry endpoints (project-scoped for ownership)."""
import uuid
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger, log_event
from app.services import registry as registry_service

router = APIRouter(prefix="/projects/{project_id}/models", tags=["models"])
log = get_logger("models")


class RegisterIn(BaseModel):
    experiment_id: uuid.UUID
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None


class TransitionIn(BaseModel):
    to_status: str
    note: str | None = Field(default=None, max_length=500)


class RollbackIn(BaseModel):
    target_version_id: uuid.UUID | None = None


@router.get("")
def list_models(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    return registry_service.list_models(db, project_id)


@router.post("/register", status_code=201)
def register_model(project_id: uuid.UUID, body: RegisterIn, user: CurrentUser, db: DbSession):
    v = registry_service.register_model(db, user.id, project_id, body.experiment_id, body.name, body.description)
    log_event(log, "model_registered", model_id=str(v.model_id), version_id=str(v.id), user_id=str(user.id))
    return registry_service._version_out(v) | {"model_id": v.model_id}


@router.get("/compare")
def compare_models(project_id: uuid.UUID, user: CurrentUser, db: DbSession, version_ids: str = Query(...)):
    ids = [uuid.UUID(x) for x in version_ids.split(",") if x.strip()]
    return registry_service.compare_versions(db, user.id, project_id, ids)


@router.get("/{model_id}")
def get_model(project_id: uuid.UUID, model_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return registry_service.get_model_detail(db, user.id, project_id, model_id)


@router.post("/{model_id}/versions/{version_id}/validate")
def validate_version(project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return registry_service.validate_version(db, user.id, project_id, model_id, version_id)


@router.post("/{model_id}/versions/{version_id}/transition")
def transition_version(project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, body: TransitionIn, user: CurrentUser, db: DbSession):
    return registry_service.transition_version(db, user.id, project_id, model_id, version_id, body.to_status, body.note)


@router.post("/{model_id}/versions/{version_id}/rollback")
def rollback_version(project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, body: RollbackIn, user: CurrentUser, db: DbSession):
    return registry_service.rollback_version(db, user.id, project_id, model_id, body.target_version_id or version_id)


@router.get("/{model_id}/versions/{version_id}/history")
def version_history(project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return registry_service.version_history(db, user.id, project_id, model_id, version_id)
