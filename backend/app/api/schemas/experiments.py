import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    task_type: Literal["classification", "regression"]
    target_column: str = Field(min_length=1, max_length=120)
    train_fraction: float = Field(default=0.7, gt=0, lt=1)
    validation_fraction: float = Field(default=0.15, gt=0, lt=1)
    test_fraction: float = Field(default=0.15, gt=0, lt=1)
    random_seed: int = Field(default=42, ge=0, le=999999)
    model_names: list[str] = Field(default_factory=lambda: ["Logistic Regression", "Random Forest"])
    preprocessing: Optional[dict[str, Any]] = None
    tuning: Optional[dict[str, Any]] = None

    model_config = {"str_strip_whitespace": True}


class ExperimentOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    # NULL after the referenced dataset/version was deleted; history is preserved.
    dataset_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    name: str
    task_type: Literal["classification", "regression"]
    target_column: str
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    random_seed: int
    model_names: list[str]
    preprocessing_config: Optional[dict[str, Any]] = None
    tuning_config: Optional[dict[str, Any]] = None
    status: Literal["queued", "running", "completed", "failed"]
    error: Optional[str] = None
    metrics: dict[str, Any] = {}
    artifact_uri: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ExperimentSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    name: str
    task_type: Literal["classification", "regression"]
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    metrics: dict[str, Any] = {}


class ModelResultOut(BaseModel):
    model_name: str
    task_type: str
    is_selected: bool
    status: Literal["completed", "failed"]
    error: Optional[str] = None
    cross_validation_metrics: dict[str, Any] = {}
    validation_metrics: dict[str, Any] = {}
    test_metrics: dict[str, Any] = {}
    confusion_matrix: Optional[dict[str, Any]] = None
    classification_report: Optional[dict[str, Any]] = None
    best_params: Optional[dict[str, Any]] = None
    training_duration_ms: Optional[float] = None

    model_config = {"from_attributes": True}


class ExperimentEvaluationOut(BaseModel):
    experiment_id: uuid.UUID
    status: str
    task_type: str
    target_column: str
    best_model_name: Optional[str] = None
    models: list[ModelResultOut] = []


class ReproducibilityOut(BaseModel):
    experiment_id: uuid.UUID
    name: str
    task_type: str
    target_column: str
    random_seed: int
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    dataset_id: Optional[uuid.UUID] = None
    dataset_version_id: Optional[uuid.UUID] = None
    dataset_sha256: Optional[str] = None
    model_names: list[str] = []
    model_configs: dict[str, Any] = {}
    preprocessing: dict[str, Any] = {}
    manifest: Optional[dict[str, Any]] = None
    manifest_available: bool = False


class ArtifactOut(BaseModel):
    experiment_id: uuid.UUID
    available: bool
    artifact_uri: Optional[str] = None
    model_file_size_bytes: Optional[int] = None
    manifest_verified: bool = False
    manifest_error: Optional[str] = None
