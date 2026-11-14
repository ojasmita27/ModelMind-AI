"""Benchmark dataset catalog + import endpoints."""
import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.api.schemas.datasets import DatasetVersionOut
from app.core.logging import get_logger, log_event
from app.services import benchmarks as benchmark_service

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])
log = get_logger("benchmarks")


@router.get("")
def list_benchmarks(
    user: CurrentUser,
    task_type: str | None = Query(default=None, pattern="^(classification|regression)$"),
    search: str | None = Query(default=None, max_length=120),
):
    """List the public benchmark catalog with optional filters."""
    return benchmark_service.list_benchmarks(task_type=task_type, search=search)


@router.get("/{benchmark_id}")
def get_benchmark(benchmark_id: str, user: CurrentUser):
    """Benchmark detail (metadata only — data is fetched on import)."""
    return benchmark_service.public_view(benchmark_service.get_benchmark_or_404(benchmark_id))


@router.post("/{benchmark_id}/import", response_model=DatasetVersionOut, status_code=201)
def import_benchmark(benchmark_id: str, project_id: uuid.UUID, user: CurrentUser, db: DbSession):
    """Download the benchmark and import it into a project as a new dataset."""
    version = benchmark_service.import_benchmark(db, user.id, project_id, benchmark_id)
    log_event(log, "benchmark_imported", benchmark_id=benchmark_id, dataset_id=str(version.dataset_id), user_id=str(user.id))
    return version
