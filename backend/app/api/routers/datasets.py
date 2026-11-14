"""Dataset API endpoints."""
import csv
import io
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.api.schemas.datasets import (
    CleaningOps,
    CleanPreviewOut,
    DatasetCreate,
    DatasetIntelligenceOut,
    DatasetOut,
    DatasetProfile,
    DatasetVersionOut,
    DatasetWithVersionsOut,
    PaginatedPreviewOut,
)
from app.core.errors import AppError
from app.core.logging import get_logger, log_event
from app.profiling import CSVProfiler
from app.services import datasets as dataset_service
from app.storage import LocalObjectStorage

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])
log = get_logger("datasets")


@router.post("", response_model=DatasetVersionOut, status_code=status.HTTP_201_CREATED)
async def create_dataset(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    name: Annotated[str, Form()],
    description: Annotated[str | None, Form()] = None,
    file: UploadFile = File(...),
):
    """Upload a CSV file and create a new dataset with its first version."""
    # Verify project ownership (will raise 404 if not owned)
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)

    version = dataset_service.create_dataset(
        db,
        project_id,
        name,
        description,
        file.file,
        file.filename or "upload.csv",
    )
    log_event(log, "dataset_created", dataset_id=str(version.dataset_id), user_id=str(user.id))
    return version


@router.get("", response_model=list[DatasetOut])
def list_datasets(project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """List all datasets for a project."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    return dataset_service.list_datasets(db, project_id)


@router.get("/{dataset_id}", response_model=DatasetWithVersionsOut)
def get_dataset(project_id: uuid.UUID, dataset_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """Get a dataset with its versions."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    dataset = dataset_service.get_owned_dataset(db, project_id, dataset_id)
    versions = dataset_service.get_dataset_versions(db, project_id, dataset_id)
    return DatasetWithVersionsOut(
        id=str(dataset.id),
        project_id=str(dataset.project_id),
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        versions=versions,
    )


@router.get("/{dataset_id}/preview")
def preview_dataset(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=25)] = 1,
):
    """Return a safe preview sample of the latest dataset version, capped by a strict row limit."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    version = dataset_service.get_dataset_versions(db, project_id, dataset_id)
    if not version:
        raise HTTPException(status_code=404, detail="Dataset has no versions.")
    latest = version[0]
    if latest.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset preview is not ready yet.")

    storage = LocalObjectStorage()
    with storage.open(latest.file_path) as csv_file:
        rows = list(csv.reader(io.TextIOWrapper(csv_file, encoding="utf-8-sig")))
    if not rows:
        return {"columns": [], "rows": []}
    header = rows[0]
    data_rows = rows[1:limit + 1]
    return {
        "columns": header,
        "rows": [dict(zip(header, row, strict=False)) for row in data_rows],
    }


@router.get("/{dataset_id}/profile", response_model=DatasetProfile)
def get_dataset_profile(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    """Return the computed profile for the latest completed dataset version."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    versions = dataset_service.get_dataset_versions(db, project_id, dataset_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Dataset has no versions.")
    latest = versions[0]
    if latest.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset profile is not ready yet.")

    storage = LocalObjectStorage()
    with storage.open(latest.file_path) as csv_file:
        profile = CSVProfiler().profile(csv_file, latest.file_path)
    return DatasetProfile(
        row_count=profile.row_count,
        column_count=profile.column_count,
        columns=[
            {
                "name": c.name,
                "type": c.type,
                "missing_count": c.missing_count,
                "missing_percentage": c.missing_percentage,
                "unique_count": c.unique_count,
                "sample_values": c.sample_values,
            }
            for c in profile.columns
        ],
        duplicate_row_count=profile.duplicate_row_count,
        duplicate_row_percentage=profile.duplicate_row_percentage,
        constant_columns=profile.constant_columns,
        warnings=profile.warnings,
    )


def _owned_version(project_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID, user, db):
    """Ownership-checked dataset version lookup (404 for non-owners)."""
    from app.services.projects import get_owned_project

    get_owned_project(db, user.id, project_id)
    return dataset_service.get_dataset_version(db, project_id, dataset_id, version_id)


def _load_version_frame(version) -> "object":
    import pandas as pd

    storage = LocalObjectStorage()
    with storage.open(version.file_path) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


@router.get("/{dataset_id}/versions/{version_id}/intelligence", response_model=DatasetIntelligenceOut)
def get_version_intelligence(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    target_column: str | None = None,
):
    """Deep dataset intelligence computed live from the stored CSV.

    Computed on demand, so calling it again IS the refresh — no stale cache.
    """
    from app.intelligence.profile import compute_intelligence

    version = _owned_version(project_id, dataset_id, version_id, user, db)
    if version.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset version is not ready yet.")
    frame = _load_version_frame(version)
    if target_column and target_column not in frame.columns:
        raise HTTPException(status_code=422, detail=f"Target column '{target_column}' not found in dataset.")
    return compute_intelligence(frame, target_column)


@router.get("/{dataset_id}/versions/{version_id}/preview", response_model=PaginatedPreviewOut)
def preview_version_paginated(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
):
    """Paginated preview of a specific dataset version (streaming, no full load)."""
    version = _owned_version(project_id, dataset_id, version_id, user, db)
    if version.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset version is not ready yet.")

    storage = LocalObjectStorage()
    columns: list[str] = []
    rows: list[dict] = []
    total = 0
    with storage.open(version.file_path) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = next(reader, None)
        if not header:
            return PaginatedPreviewOut(columns=[], rows=[], total_rows=0, offset=offset, limit=limit, has_more=False)
        columns = header
        for i, row in enumerate(reader):
            total += 1
            if offset <= i < offset + limit:
                rows.append(dict(zip(header, row, strict=False)))
    return PaginatedPreviewOut(
        columns=columns, rows=rows, total_rows=total, offset=offset, limit=limit, has_more=offset + limit < total
    )


@router.post("/{dataset_id}/versions/{version_id}/clean-preview", response_model=CleanPreviewOut)
def clean_preview(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    ops: CleaningOps,
    user: CurrentUser,
    db: DbSession,
):
    """Apply cleaning ops and return a preview WITHOUT persisting anything."""
    from app.services.cleaning import preview_cleaning

    version = _owned_version(project_id, dataset_id, version_id, user, db)
    if version.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset version is not ready yet.")
    frame = _load_version_frame(version)
    try:
        return preview_cleaning(frame, ops.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cleaning failed: {exc}") from exc


@router.post("/{dataset_id}/versions/{version_id}/clean", response_model=DatasetVersionOut, status_code=status.HTTP_201_CREATED)
def clean_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    ops: CleaningOps,
    user: CurrentUser,
    db: DbSession,
):
    """Apply cleaning ops and persist the result as a NEW dataset version.

    The source version is never modified or overwritten.
    """
    from app.services.cleaning import create_cleaned_version

    version = _owned_version(project_id, dataset_id, version_id, user, db)
    if version.job_status != "completed":
        raise HTTPException(status_code=409, detail="Dataset version is not ready yet.")
    try:
        new_version = create_cleaned_version(db, version, ops.model_dump(), [f"cleaning_ops: {ops.model_dump_json()}"])
    except AppError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cleaning failed: {exc}") from exc
    log_event(log, "dataset_version_cleaned", dataset_id=str(dataset_id), source_version=str(version_id), new_version=str(new_version.id))
    return new_version


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(project_id: uuid.UUID, dataset_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """Delete a dataset and all its versions."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    dataset_service.delete_dataset(db, project_id, dataset_id)
    log_event(log, "dataset_deleted", dataset_id=str(dataset_id), user_id=str(user.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{dataset_id}/versions", response_model=list[DatasetVersionOut])
def list_dataset_versions(
    project_id: uuid.UUID, dataset_id: uuid.UUID, user: CurrentUser, db: DbSession
):
    """List all versions of a dataset."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    return dataset_service.get_dataset_versions(db, project_id, dataset_id)


@router.get("/{dataset_id}/versions/{version_id}", response_model=DatasetVersionOut)
def get_dataset_version(
    project_id: uuid.UUID,
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
):
    """Get a specific version of a dataset."""
    from app.services.projects import get_owned_project
    get_owned_project(db, user.id, project_id)
    return dataset_service.get_dataset_version(db, project_id, dataset_id, version_id)
