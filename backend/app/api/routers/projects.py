import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.api.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate
from app.core.logging import get_logger, log_event
from app.services import projects as project_service

router = APIRouter(prefix="/projects", tags=["projects"])
log = get_logger("projects")


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, user: CurrentUser, db: DbSession):
    project = project_service.create_project(db, user.id, body.name, body.description)
    log_event(log, "project_created", project_id=str(project.id), user_id=str(user.id))
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return project_service.list_projects(db, user.id, limit, offset)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    return project_service.get_owned_project(db, user.id, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, user: CurrentUser, db: DbSession):
    project = project_service.update_project(db, user.id, project_id, body.model_dump(exclude_unset=True))
    log_event(log, "project_updated", project_id=str(project.id), user_id=str(user.id))
    return project


@router.delete("/{project_id}")
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    report = project_service.delete_project(db, user.id, project_id)
    log_event(log, "project_deleted", project_id=str(project_id), user_id=str(user.id))
    return {"deleted": True, "cleanup": report}
