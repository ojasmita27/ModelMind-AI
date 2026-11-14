import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", passive_deletes=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="projects")
    datasets: Mapped[list["Dataset"]] = relationship(back_populates="project", passive_deletes=True)
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="project", passive_deletes=True)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="datasets")
    versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="dataset", passive_deletes=True)
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="dataset", passive_deletes=True)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(nullable=True)
    column_count: Mapped[Optional[int]] = mapped_column(nullable=True)

    # Job tracking for async validation/profiling
    job_status: Mapped[Literal["pending", "processing", "completed", "failed"]] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    job_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    job_completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    # Versioning lineage: "upload" for originals, "cleaned" for derived versions.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload", server_default="upload")
    derived_from_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    transformation_log: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="dataset_version", passive_deletes=True)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable + SET NULL: deleting a dataset must NOT destroy experiment
    # history. Experiments keep metrics/config; dataset refs become NULL and
    # the API reports them honestly as deleted.
    dataset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[Literal["classification", "regression"]] = mapped_column(String(20), nullable=False)
    target_column: Mapped[str] = mapped_column(String(120), nullable=False)
    train_fraction: Mapped[float] = mapped_column(nullable=False)
    validation_fraction: Mapped[float] = mapped_column(nullable=False)
    test_fraction: Mapped[float] = mapped_column(nullable=False)
    random_seed: Mapped[int] = mapped_column(nullable=False, default=42)
    model_names: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # User-configurable preprocessing choices; fitted on train split only.
    preprocessing_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tuning_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[Literal["queued", "running", "completed", "failed"]] = mapped_column(
        String(20), nullable=False, default="queued"
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    artifact_uri: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    project: Mapped[Project] = relationship(back_populates="experiments")
    dataset: Mapped[Dataset] = relationship(back_populates="experiments")
    dataset_version: Mapped[DatasetVersion] = relationship(back_populates="experiments")
    model_results: Mapped[list["ExperimentModelResult"]] = relationship(
        back_populates="experiment", passive_deletes=True
    )


class ExperimentModelResult(Base):
    """Per-candidate-model evaluation results for one experiment.

    One row per (experiment, model). Stores real metrics computed during the
    run for each evaluation split, plus diagnostic artifacts (confusion
    matrix / classification report) on the validation split. Rows with
    status='failed' carry the per-model error instead of metrics.
    """

    __tablename__ = "experiment_model_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_selected: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[Literal["completed", "failed"]] = mapped_column(String(20), nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cross_validation_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    validation_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    test_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confusion_matrix: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    classification_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    best_params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    training_duration_ms: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    experiment: Mapped[Experiment] = relationship(back_populates="model_results")


class WhatIfRun(Base):
    """Persisted What-If / counterfactual analysis record."""

    __tablename__ = "whatif_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "predict" | "counterfactual"
    input_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    experiment: Mapped[Experiment] = relationship()


class RegisteredModel(Base):
    """A named model family in the registry (groups immutable versions)."""

    __tablename__ = "registered_models"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan")


class ModelVersion(Base):
    """Immutable registered snapshot of a trained experiment artifact."""

    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True
    )
    artifact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(nullable=False)
    algorithm: Mapped[str] = mapped_column(String(120), nullable=False)
    framework: Mapped[str] = mapped_column(String(60), nullable=False, default="scikit-learn")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")
    validation: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    model: Mapped[RegisteredModel] = relationship(back_populates="versions")
    transitions: Mapped[list["ModelTransition"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="ModelTransition.created_at"
    )


class ModelTransition(Base):
    """Lifecycle transition audit record."""

    __tablename__ = "model_transitions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )

    version: Mapped[ModelVersion] = relationship(back_populates="transitions")


class Deployment(Base):
    """A deployed registered model version (logical serving record)."""

    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )

    predictions: Mapped[list["PredictionRecord"]] = relationship(back_populates="deployment", cascade="all, delete-orphan")


class PredictionRecord(Base):
    """Persisted prediction request metadata + result."""

    __tablename__ = "prediction_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False, index=True
    )

    deployment: Mapped[Deployment] = relationship(back_populates="predictions")


class MonitoringRun(Base):
    """A monitoring execution over a deployment's prediction window."""

    __tablename__ = "monitoring_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    window_start: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    reference_sample_count: Mapped[int] = mapped_column(nullable=False, default=0)
    health_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False, index=True
    )


class LabelRecord(Base):
    """Ground-truth label matched to a prediction request."""

    __tablename__ = "label_records"
    __table_args__ = (UniqueConstraint("deployment_id", "request_id", name="uq_label_request"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )


class TrustReceipt(Base):
    """Immutable trust receipt snapshot for a completed experiment."""

    __tablename__ = "trust_receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    verifications: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, server_default=func.now(), nullable=False
    )
