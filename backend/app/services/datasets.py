"""Dataset operations with ownership isolation through projects."""
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, conflict, not_found
from app.db.models import Dataset, DatasetVersion
from app.jobs import get_job_queue
from app.profiling import CSVProfiler, ProfileResult
from app.storage import LocalObjectStorage
from app.validation import CSVValidationError, validate_csv_upload

# Characters that are safe in a cross-platform filename component.
# Everything outside [A-Za-z0-9._-] is replaced with an underscore.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^\w.\-]")
_MAX_FILENAME_LEN = 100  # conservative limit to keep storage keys short


def _sanitize_filename(raw: str) -> str:
    """Return a filesystem-safe filename derived from *raw*.

    Rules applied in order:
    1. Strip directory components — only the final name component is kept.
    2. Strip leading dots/spaces to prevent hidden-file tricks.
    3. Replace every character outside [A-Za-z0-9._-] with ``_``.
    4. Collapse consecutive underscores to one.
    5. Truncate to ``_MAX_FILENAME_LEN`` characters.
    6. Fall back to ``upload.csv`` if the result is empty.
    """
    # 1. Strip any directory part (handles ../evil, /etc/passwd, C:\windows\...).
    name = Path(raw).name
    # 2. Strip leading dots and whitespace.
    name = name.lstrip(". ")
    # 3. Replace unsafe characters.
    name = _UNSAFE_FILENAME_CHARS.sub("_", name)
    # 4. Collapse runs of underscores.
    name = re.sub(r"_+", "_", name)
    # 5. Truncate.
    name = name[:_MAX_FILENAME_LEN]
    # 6. Fallback.
    return name if name else "upload.csv"


def create_dataset(
    db: Session,
    project_id: uuid.UUID,
    name: str,
    description: Optional[str],
    file,
    filename: str,
) -> DatasetVersion:
    """Create a new dataset with its first version.

    This validates the CSV, stores it, computes checksum, and queues profiling job.
    """
    settings = get_settings()

    # Validate CSV
    try:
        row_count, columns = validate_csv_upload(
            file,
            filename,
            settings.max_dataset_size_mb,
            settings.allowed_dataset_extensions,
        )
    except CSVValidationError as e:
        raise AppError(422, "validation_error", e.message) from e

    # Reset file pointer for storage
    file.seek(0)

    # Create dataset
    dataset = Dataset(project_id=project_id, name=name, description=description)
    db.add(dataset)
    db.flush()  # Get dataset.id without committing

    # Determine version number (first version = 1)
    version_number = 1

    # Sanitize the caller-supplied filename before embedding it in a storage key.
    # UploadFile.filename is user-controlled and must never be used as a raw path
    # component — it may contain "../", absolute paths, or shell-special characters.
    safe_filename = _sanitize_filename(filename)

    # Generate storage key
    storage_key = f"datasets/{dataset.id}/v{version_number}/{safe_filename}"

    # Store file
    storage = LocalObjectStorage()
    storage.put(storage_key, file)

    # Compute SHA-256
    sha256 = storage.compute_sha256(storage_key)
    file_size = storage.get_file_size(storage_key)

    # A duplicate checksum in the same project is treated as a duplicate upload.
    # We keep the duplicate check scoped to the project to avoid exposing another
    # user's dataset metadata through the API contract.
    existing_version = db.scalar(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(DatasetVersion.sha256_checksum == sha256, Dataset.project_id == project_id)
    )
    if existing_version is not None:
        db.rollback()
        if storage.exists(storage_key):
            storage.delete(storage_key)
        raise conflict("A dataset with the same content already exists in this project.")

    # Create dataset version
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=version_number,
        sha256_checksum=sha256,
        file_path=storage_key,
        file_size_bytes=file_size,
        row_count=row_count,
        column_count=len(columns),
        job_status="pending",
    )
    db.add(version)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if storage.exists(storage_key):
            storage.delete(storage_key)
        raise conflict("A dataset with the same content already exists.") from exc
    db.refresh(version)

    # Queue profiling job
    job_queue = get_job_queue()
    job_id = str(version.id)

    def profile_job():
        _run_profiling_job(db, version.id, storage_key)

    job_queue.enqueue(job_id, profile_job)

    return version


def list_datasets(db: Session, project_id: uuid.UUID) -> list[Dataset]:
    """List all datasets for a project."""
    stmt = select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
    return list(db.scalars(stmt))


def get_owned_dataset(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> Dataset:
    """Get a dataset if it belongs to the project."""
    dataset = db.scalar(
        select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id)
    )
    if dataset is None:
        raise not_found("Dataset")
    return dataset


def delete_dataset(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> None:
    """Delete a dataset and all its versions."""
    dataset = get_owned_dataset(db, project_id, dataset_id)

    # Delete files from storage
    storage = LocalObjectStorage()
    for version in dataset.versions:
        if storage.exists(version.file_path):
            storage.delete(version.file_path)

    # Delete version rows explicitly: the collection is loaded (we just
    # iterated it), so the ORM would otherwise try to NULL their dataset_id
    # (NOT NULL) instead of letting the FK cascade / SET NULL handle refs.
    # Experiments referencing these versions get dataset_version_id=NULL.
    for version in dataset.versions:
        db.delete(version)
    db.delete(dataset)
    db.commit()


def get_dataset_versions(db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID) -> list[DatasetVersion]:
    """Get all versions of a dataset."""
    dataset = get_owned_dataset(db, project_id, dataset_id)
    stmt = (
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset.id)
        .order_by(DatasetVersion.version_number.desc())
    )
    return list(db.scalars(stmt))


def get_dataset_version(
    db: Session, project_id: uuid.UUID, dataset_id: uuid.UUID, version_id: uuid.UUID
) -> DatasetVersion:
    """Get a specific version of a dataset."""
    dataset = get_owned_dataset(db, project_id, dataset_id)
    version = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset.id
        )
    )
    if version is None:
        raise not_found("Dataset version")
    return version


def _run_profiling_job(db: Session, version_id: uuid.UUID, storage_key: str) -> None:
    """Run the profiling job for a dataset version."""
    from datetime import datetime, timezone

    from app.db.session import get_sessionmaker

    storage = LocalObjectStorage()
    session_factory = get_sessionmaker()
    job_session = session_factory()
    try:
        version = job_session.get(DatasetVersion, version_id)
        if version is None:
            return

        version.job_status = "processing"
        version.job_started_at = datetime.now(timezone.utc)
        job_session.commit()

        try:
            with storage.open(storage_key) as f:
                profiler = CSVProfiler()
                profile = profiler.profile(f, storage_key)

            version.row_count = profile.row_count
            version.column_count = profile.column_count
            version.job_status = "completed"
            version.job_completed_at = datetime.now(timezone.utc)
            version.job_error = "\n".join(profile.warnings) if profile.warnings else None
            job_session.commit()
        except Exception as e:
            version.job_status = "failed"
            version.job_completed_at = datetime.now(timezone.utc)
            version.job_error = str(e)
            job_session.commit()
            raise
    finally:
        job_session.close()
