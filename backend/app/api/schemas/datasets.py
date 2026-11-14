"""Pydantic schemas for datasets."""
import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    """Profile for a single column."""
    name: str
    type: str
    missing_count: int
    missing_percentage: float
    unique_count: int
    sample_values: list[str]


class DatasetProfile(BaseModel):
    """Profile result for a dataset version."""
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    duplicate_row_count: int
    duplicate_row_percentage: float
    constant_columns: list[str]
    warnings: list[str]


class DatasetVersionOut(BaseModel):
    """Output schema for dataset version."""
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    sha256_checksum: str
    file_path: str
    file_size_bytes: int
    row_count: Optional[int] = None
    column_count: Optional[int] = None
    job_status: Literal["pending", "processing", "completed", "failed"]
    job_error: Optional[str] = None
    job_started_at: Optional[datetime] = None
    job_completed_at: Optional[datetime] = None
    source: str = "upload"
    derived_from_version_id: Optional[uuid.UUID] = None
    transformation_log: Optional[list[str]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CleaningOps(BaseModel):
    """Configurable cleaning operations applied in a fixed order."""
    drop_columns: list[str] = []
    rename_columns: dict[str, str] = {}
    missing: dict[str, Any] = {}
    drop_duplicates: bool = False
    outliers: dict[str, Any] = {}
    datetime_extract: list[dict[str, Any]] = []
    encode: list[dict[str, Any]] = []
    scale: dict[str, Any] = {}


class CleanPreviewOut(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    shape_before: dict[str, int]
    shape_after: dict[str, int]
    rows_removed: int = 0
    columns_removed: int = 0
    missing_before: dict[str, Any] = {}
    missing_after: dict[str, Any] = {}
    transformation_log: list[str]


class DatasetVersionCreatedOut(DatasetVersionOut):
    pass


class DatasetIntelligenceOut(BaseModel):
    """Top-level intelligence payload; column entries are dicts by design."""
    row_count: int
    column_count: int
    columns: list[dict[str, Any]]
    duplicate_row_count: int
    duplicate_row_percentage: float
    correlation: Optional[dict[str, Any]] = None
    target: Optional[dict[str, Any]] = None
    quality_score: float
    quality_criteria: dict[str, float]
    warnings: list[str]


class PaginatedPreviewOut(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    offset: int
    limit: int
    has_more: bool


class DatasetCreate(BaseModel):
    """Input schema for creating a dataset."""
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None


class DatasetOut(BaseModel):
    """Output schema for dataset."""
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetWithVersionsOut(BaseModel):
    """Output schema for dataset with its versions."""
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str]
    created_at: datetime
    versions: list[DatasetVersionOut]

    model_config = {"from_attributes": True}
