"""Data cleaning workbench: configurable, previewable transformations."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import DatasetVersion
from app.intelligence.profile import _infer_type
from app.services.datasets import _sanitize_filename
from app.storage import LocalObjectStorage


def _col_type(series: pd.Series) -> str:
    return _infer_type(series)


def apply_cleaning_ops(frame: pd.DataFrame, ops: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    """Apply cleaning operations in a fixed, documented order.

    Returns (cleaned_frame, human-readable transformation log).
    """
    df = frame.copy()
    log: list[str] = []

    drop_cols = [c for c in ops.get("drop_columns") or [] if c in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
        log.append(f"Dropped columns: {', '.join(drop_cols)}")

    renames = ops.get("rename_columns") or {}
    applied = {old: new for old, new in renames.items() if old in df.columns and new}
    if applied:
        df = df.rename(columns=applied)
        log.append("Renamed columns: " + ", ".join(f"{o} -> {n}" for o, n in applied.items()))

    missing = ops.get("missing") or {}
    strategy = missing.get("strategy", "none")
    if strategy != "none":
        df, mlog = _handle_missing(df, strategy, missing.get("constant_value"))
        log.extend(mlog)

    if ops.get("drop_duplicates"):
        before = len(df)
        df = df.drop_duplicates()
        removed = before - len(df)
        if removed:
            log.append(f"Removed {removed} duplicate rows")

    outlier_cfg = ops.get("outliers") or {}
    if outlier_cfg.get("enabled"):
        df, olog = _handle_outliers(df, outlier_cfg)
        log.extend(olog)

    for spec in ops.get("datetime_extract") or []:
        df, dlog = _datetime_extract(df, spec)
        log.extend(dlog)

    for spec in ops.get("encode") or []:
        df, elog = _encode(df, spec)
        log.extend(elog)

    scale_cfg = ops.get("scale") or {}
    if scale_cfg.get("method") and scale_cfg["method"] != "none":
        df, slog = _scale(df, scale_cfg)
        log.extend(slog)

    return df, log


def _handle_missing(df: pd.DataFrame, strategy: str, constant: Any) -> tuple[pd.DataFrame, list[str]]:
    log: list[str] = []
    if strategy == "drop_rows":
        before = len(df)
        df = df.dropna()
        log.append(f"Dropped {before - len(df)} rows with missing values")
        return df, log

    for col in df.columns:
        series = df[col]
        if series.isna().sum() == 0:
            continue
        if _col_type(series) == "numeric":
            if strategy == "numeric_mean":
                fill = pd.to_numeric(series, errors="coerce").mean()
            elif strategy == "numeric_median":
                fill = pd.to_numeric(series, errors="coerce").median()
            elif strategy == "numeric_constant":
                fill = float(constant) if constant not in (None, "") else 0.0
            else:
                continue
            df[col] = pd.to_numeric(series, errors="coerce").fillna(fill)
            log.append(f"Imputed '{col}' (numeric, {strategy})")
        else:
            if strategy in ("categorical_mode", "categorical_constant"):
                fill = series.mode().iloc[0] if strategy == "categorical_mode" and not series.mode().empty else (constant if constant not in (None, "") else "missing")
                df[col] = series.fillna(fill)
                log.append(f"Imputed '{col}' (categorical, {strategy})")
    return df, log


def _iqr_bounds(series: pd.Series, k: float) -> tuple[float, float] | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    iqr = q3 - q1
    return float(q1 - k * iqr), float(q3 + k * iqr)


def _handle_outliers(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    cols = [c for c in (cfg.get("columns") or []) if c in df.columns]
    if not cols:
        cols = [c for c in df.columns if _col_type(df[c]) == "numeric"]
    k = float(cfg.get("k", 1.5))
    strategy = cfg.get("strategy", "drop_rows")
    log: list[str] = []
    for col in cols:
        bounds = _iqr_bounds(df[col], k)
        if bounds is None:
            continue
        lo, hi = bounds
        numeric = pd.to_numeric(df[col], errors="coerce")
        mask = (numeric < lo) | (numeric > hi)
        count = int(mask.sum())
        if count == 0:
            continue
        if strategy == "clip":
            df[col] = numeric.clip(lo, hi)
            log.append(f"Clipped {count} outliers in '{col}' to IQR bounds [{lo:.4g}, {hi:.4g}]")
        else:
            df = df.loc[~mask]
            log.append(f"Dropped {count} outlier rows from '{col}' (IQR k={k})")
    return df, log


def _datetime_extract(df: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    col = spec.get("column")
    parts = spec.get("parts") or ["year", "month", "day"]
    if not col or col not in df.columns:
        return df, []
    parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
    added: list[str] = []
    for part in parts:
        new_col = f"{col}_{part}"
        if part == "year":
            df[new_col] = parsed.dt.year
        elif part == "month":
            df[new_col] = parsed.dt.month
        elif part == "day":
            df[new_col] = parsed.dt.day
        elif part == "dayofweek":
            df[new_col] = parsed.dt.dayofweek
        elif part == "hour":
            df[new_col] = parsed.dt.hour
        else:
            continue
        added.append(new_col)
    return df, [f"Extracted {', '.join(added)} from '{col}'"] if added else []


def _encode(df: pd.DataFrame, spec: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    col = spec.get("column")
    method = spec.get("method", "one_hot")
    if not col or col not in df.columns:
        return df, []
    if method == "ordinal":
        df[col] = df[col].astype("category").cat.codes
        return df, [f"Ordinal-encoded '{col}'"]
    dummies = pd.get_dummies(df[col].astype("category"), prefix=col, dummy_na=False)
    df = pd.concat([df.drop(columns=[col]), dummies], axis=1)
    return df, [f"One-hot encoded '{col}' into {dummies.shape[1]} columns"]


def _scale(df: pd.DataFrame, cfg: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    method = cfg.get("method")
    cols = cfg.get("columns")
    numeric_cols = [c for c in df.columns if _col_type(df[c]) == "numeric"]
    if cols:
        numeric_cols = [c for c in cols if c in numeric_cols]
    if not numeric_cols:
        return df, []
    for col in numeric_cols:
        values = pd.to_numeric(df[col], errors="coerce")
        if method == "minmax":
            lo, hi = values.min(), values.max()
            df[col] = (values - lo) / (hi - lo) if hi != lo else 0.0
        else:  # standard
            mean, std = values.mean(), values.std(ddof=0)
            df[col] = (values - mean) / std if std else 0.0
    return df, [f"Applied {method} scaling to {len(numeric_cols)} numeric columns"]


def _missing_summary(frame: pd.DataFrame) -> dict[str, Any]:
    total_cells = int(frame.size) if len(frame.columns) else 0
    missing = int(frame.isna().sum().sum())
    return {
        "missing_cells": missing,
        "missing_pct": round(missing / total_cells * 100, 2) if total_cells else 0.0,
        "columns_with_missing": int((frame.isna().sum() > 0).sum()),
    }


def preview_cleaning(frame: pd.DataFrame, ops: dict[str, Any], sample_rows: int = 10) -> dict[str, Any]:
    cleaned, log = apply_cleaning_ops(frame, ops)
    sample = cleaned.head(sample_rows).astype(object)
    sample = sample.where(sample.notna(), None)
    return {
        "columns": [str(c) for c in cleaned.columns],
        "rows": sample.to_dict("records"),
        "shape_before": {"rows": int(len(frame)), "columns": int(len(frame.columns))},
        "shape_after": {"rows": int(len(cleaned)), "columns": int(len(cleaned.columns))},
        "rows_removed": int(len(frame) - len(cleaned)),
        "columns_removed": int(len(frame.columns) - len(cleaned.columns)),
        "missing_before": _missing_summary(frame),
        "missing_after": _missing_summary(cleaned),
        "transformation_log": log,
    }


def create_cleaned_version(
    db: Session,
    version: DatasetVersion,
    ops: dict[str, Any],
    transformation_log: list[str],
    storage: LocalObjectStorage | None = None,
) -> DatasetVersion:
    """Persist cleaning output as a NEW dataset version (source never overwritten)."""
    storage = storage or LocalObjectStorage()
    with storage.open(version.file_path) as raw:
        import io as _io

        frame = pd.read_csv(_io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))

    cleaned, applied_log = apply_cleaning_ops(frame, ops)
    if cleaned.empty:
        raise AppError(422, "validation_error", "Cleaning operations produced an empty dataset.")

    buf = io.BytesIO()
    cleaned.to_csv(buf, index=False)
    buf.seek(0)

    from sqlalchemy import func, select

    max_v = db.scalar(select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == version.dataset_id)) or 0
    next_version = int(max_v) + 1

    safe_name = _sanitize_filename(f"cleaned_v{next_version}.csv")
    storage_key = f"datasets/{version.dataset_id}/v{next_version}/{safe_name}"
    storage.put(storage_key, buf)
    sha = storage.compute_sha256(storage_key)
    size = storage.get_file_size(storage_key)

    new_version = DatasetVersion(
        dataset_id=version.dataset_id,
        version_number=next_version,
        sha256_checksum=sha,
        file_path=storage_key,
        file_size_bytes=size,
        row_count=int(len(cleaned)),
        column_count=int(len(cleaned.columns)),
        job_status="pending",
        source="cleaned",
        derived_from_version_id=version.id,
        transformation_log=[*transformation_log, *applied_log],
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)

    from app.jobs import get_job_queue
    from app.services.datasets import _run_profiling_job

    vid = new_version.id
    get_job_queue().enqueue(str(vid), lambda: _run_profiling_job(db, vid, storage_key))
    return new_version
