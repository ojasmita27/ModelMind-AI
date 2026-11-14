"""Benchmark import: download real data -> store as Dataset + DatasetVersion."""
from __future__ import annotations

import io
import uuid

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.benchmarks.catalog import get_benchmark, load_frame, public_view
from app.core.errors import AppError, conflict, not_found
from app.db.models import Dataset, DatasetVersion
from app.jobs import get_job_queue
from app.services.datasets import _run_profiling_job
from app.storage import LocalObjectStorage


def list_benchmarks(task_type: str | None = None, search: str | None = None) -> list[dict]:
    from app.benchmarks.catalog import BENCHMARK_DATASETS, public_view

    out = []
    for entry in BENCHMARK_DATASETS:
        if task_type and entry["task_type"] != task_type:
            continue
        if search and search.lower() not in (entry["name"] + " " + entry["description"]).lower():
            continue
        out.append(public_view(entry))
    return out


def get_benchmark_or_404(benchmark_id: str) -> dict:
    entry = get_benchmark(benchmark_id)
    if entry is None:
        raise not_found("Benchmark dataset")
    return entry


def import_benchmark(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, benchmark_id: str) -> DatasetVersion:
    """Fetch the benchmark and store it as a new dataset (duplicate-safe)."""
    from app.services.projects import get_owned_project

    get_owned_project(db, owner_id, project_id)
    entry = get_benchmark_or_404(benchmark_id)

    try:
        frame, target_column, meta = load_frame(entry)
    except Exception as exc:
        raise AppError(502, "benchmark_fetch_failed", f"Could not download benchmark dataset: {exc}") from exc

    if frame.empty:
        raise AppError(502, "benchmark_fetch_failed", "Benchmark dataset downloaded empty.")

    # Serialize to CSV bytes.
    buf = io.BytesIO()
    frame.to_csv(buf, index=False)
    buf.seek(0)

    dataset = Dataset(project_id=project_id, name=entry["name"], description=entry["description"])
    db.add(dataset)
    db.flush()

    storage = LocalObjectStorage()
    safe_name = f"benchmark_{entry['id']}.csv".replace("/", "_")
    storage_key = f"datasets/{dataset.id}/v1/{safe_name}"
    storage.put(storage_key, buf)
    sha = storage.compute_sha256(storage_key)
    size = storage.get_file_size(storage_key)

    # Duplicate protection scoped to the project (same as uploads).
    existing = db.scalar(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(DatasetVersion.sha256_checksum == sha, Dataset.project_id == project_id)
    )
    if existing is not None:
        db.rollback()
        storage.delete(storage_key)
        raise conflict("This benchmark dataset has already been imported into this project.")

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        sha256_checksum=sha,
        file_path=storage_key,
        file_size_bytes=size,
        row_count=int(len(frame)),
        column_count=int(len(frame.columns)),
        job_status="pending",
        source="benchmark",
        transformation_log=[
            f"benchmark_id={entry['id']}",
            f"target_column={target_column}",
            f"source={meta.get('source')}",
            f"license={meta.get('license')}",
            f"citation={entry.get('citation')}",
        ],
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    vid = version.id
    get_job_queue().enqueue(str(vid), lambda: _run_profiling_job(db, vid, storage_key))
    return version
