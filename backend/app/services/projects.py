"""Project operations. EVERY query filters by owner_id.

A project that exists but belongs to another user is indistinguishable from one that
does not exist: both raise not_found (404), so resource existence is never leaked.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.core.logging import get_logger, log_event
from app.db.models import DatasetVersion, Experiment, Project
from app.storage import LocalObjectStorage

log = get_logger("projects")


def create_project(db: Session, owner_id: uuid.UUID, name: str, description: Optional[str]) -> Project:
    project = Project(owner_id=owner_id, name=name, description=description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, owner_id: uuid.UUID, limit: int, offset: int) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.owner_id == owner_id)
        .order_by(Project.created_at.desc(), Project.id)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def get_owned_project(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    )
    if project is None:
        raise not_found("Project")
    return project


def update_project(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, changes: dict) -> Project:
    project = get_owned_project(db, owner_id, project_id)
    for field, value in changes.items():
        setattr(project, field, value)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


def _project_storage_keys(db: Session, project_id: uuid.UUID) -> tuple[list[str], list[str]]:
    """All storage keys owned by a project: dataset files + experiment artifact dirs."""
    from app.db.models import Dataset
    version_rows = db.scalars(
        select(DatasetVersion.file_path)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(Dataset.project_id == project_id)
    )
    file_keys = [fp for fp in version_rows if fp]

    experiment_ids = db.scalars(select(Experiment.id).where(Experiment.project_id == project_id))
    artifact_prefixes = [f"experiments/{eid}/" for eid in experiment_ids]
    return file_keys, artifact_prefixes


def delete_project(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict:
    """Delete a project, its datasets/experiments (DB cascade) AND its files.

    File cleanup is best-effort and reported honestly: missing files are
    ignored, failures are counted in the returned report and logged — the
    response never claims a clean sweep that did not happen.
    """
    project = get_owned_project(db, owner_id, project_id)
    file_keys, artifact_prefixes = _project_storage_keys(db, project_id)

    storage = LocalObjectStorage()
    files_deleted = files_failed = 0
    for key in file_keys:
        try:
            if storage.exists(key):
                storage.delete(key)
            files_deleted += 1
        except Exception as exc:
            files_failed += 1
            log_event(log, "project_file_cleanup_failed", level=30, project_id=str(project_id), key=key, error=str(exc))

    artifacts_deleted = artifacts_failed = 0
    for prefix in artifact_prefixes:
        try:
            report = storage.delete_prefix(prefix)
            artifacts_deleted += report["deleted"]
            artifacts_failed += report["failed"]
        except Exception as exc:
            artifacts_failed += 1
            log_event(log, "project_artifact_cleanup_failed", level=30, project_id=str(project_id), prefix=prefix, error=str(exc))

    db.delete(project)
    db.commit()

    report = {
        "project_id": str(project_id),
        "dataset_files_deleted": files_deleted,
        "dataset_files_failed": files_failed,
        "artifact_files_deleted": artifacts_deleted,
        "artifact_files_failed": artifacts_failed,
    }
    if files_failed or artifacts_failed:
        log_event(log, "project_delete_cleanup_partial", level=30, **report)
    else:
        log_event(log, "project_deleted", **report)
    log_event(log, "project_deleted", project_id=str(project_id), user_id=str(owner_id))
    return report
