"""Interfaces for FUTURE milestones. Nothing here is implemented in this package.

These Protocols fix the seams between the web layer, services and the ML engine so that
later milestones add implementations without reshaping the foundation:

    M2  ObjectStorage        local disk now, Amazon S3 later (same interface)
    M3  DatasetProfiler      pure pandas profiling
    M5-6  ExperimentRunner   train/evaluate with leakage-safe splits
    M6  ArtifactStore        fitted-pipeline binaries + manifest
    M7  ExperimentTracker    MLflow adapter (PostgreSQL/SQLite stays the source of truth)

Rules: this module and ``app.ml_engine`` must NOT import FastAPI, SQLAlchemy or MLflow
(enforced by tests/test_architecture.py).
"""
from dataclasses import dataclass, field
from typing import Any, BinaryIO, Optional, Protocol


class ObjectStorage(Protocol):
    """Opaque key -> bytes storage. Keys are relative, e.g. 'datasets/{project}/{dataset}/v1/original.csv'."""

    def put(self, key: str, data: BinaryIO) -> str:
        """Store data and return a storage URI (local://... or s3://...)."""

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...


class DatasetProfiler(Protocol):
    """Pure computation: a table in, a JSON-serialisable profile and warnings out."""

    def profile(self, frame: Any, *, max_rows: int, random_seed: int) -> dict[str, Any]:
        """`frame` is a pandas DataFrame. Warnings are candidates for investigation, never proof."""


@dataclass(frozen=True)
class ExperimentSnapshot:
    """Everything needed to reproduce an experiment. Frozen before training starts."""

    experiment_id: str
    dataset_version_id: str
    dataset_sha256: str
    task_type: str  # "classification" | "regression"
    target_column: str
    feature_columns: tuple[str, ...]
    preprocessing: dict[str, Any] = field(default_factory=dict)
    split: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    random_seed: int = 42


class ExperimentRunner(Protocol):
    def run(self, snapshot: ExperimentSnapshot, algorithms: list[str]) -> list[dict[str, Any]]:
        """Return one result per algorithm; a failure is reported, never hidden."""


class ArtifactStore(Protocol):
    def save_model(self, experiment_id: str, run_id: str, pipeline: Any, manifest: dict[str, Any]) -> str:
        """Persist a fitted pipeline plus its manifest; return the artifact URI."""

    def load_model(self, uri: str) -> Any:
        """Load ONLY artifacts this system wrote itself (joblib/pickle is unsafe for untrusted files)."""


class ExperimentTracker(Protocol):
    """One-way sink for experiment metadata. The application database stays canonical."""

    def log_run(self, snapshot: ExperimentSnapshot, algorithm: str, params: dict[str, Any],
                metrics: dict[str, float], tags: dict[str, str]) -> Optional[str]:
        """Return the tracker's run id, or None if tracking is unavailable."""
