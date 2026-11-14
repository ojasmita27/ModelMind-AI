"""What-If analysis & counterfactual generation on persisted experiment models."""
from __future__ import annotations

import io
import json
import uuid
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.db.models import DatasetVersion, Experiment
from app.services.experiments import get_owned_experiment
from app.storage import LocalObjectStorage

_MAX_CANDIDATES = 300
_MAX_RETURN = 3
_MAX_CATEGORICAL_DOMAIN = 200
_SAMPLE_ROWS_FOR_SCHEMA = 5000


def _load_experiment_model(experiment: Experiment):
    """Load the persisted pipeline for a completed experiment."""
    if experiment.status != "completed" or not experiment.artifact_uri:
        raise AppError(409, "experiment_not_ready", "Experiment has no trained model artifact yet.")
    key = experiment.artifact_uri.removeprefix("local://")
    storage = LocalObjectStorage()
    if not storage.exists(key):
        raise AppError(404, "artifact_missing", "Model artifact is missing from storage.")
    try:
        with storage.open(key) as f:
            model = joblib.load(f)
    except Exception as exc:
        raise AppError(500, "artifact_corrupt", f"Model artifact could not be loaded: {exc}") from exc
    if not hasattr(model, "predict"):
        raise AppError(500, "artifact_invalid", "Loaded artifact does not expose predict().")
    return model, storage


def _load_version_frame(experiment: Experiment, storage: LocalObjectStorage) -> pd.DataFrame:
    version = experiment.dataset_version
    if version is None or experiment.dataset_version_id is None:
        raise AppError(409, "dataset_unavailable", "The dataset version for this experiment is no longer available.")
    with storage.open(version.file_path) as raw:
        return pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""), nrows=_SAMPLE_ROWS_FOR_SCHEMA)


def _feature_schema(experiment: Experiment, storage: LocalObjectStorage) -> list[dict[str, Any]]:
    frame = _load_version_frame(experiment, storage)
    target = experiment.target_column
    features = [c for c in frame.columns if c != target]
    schema: list[dict[str, Any]] = []
    for col in features:
        series = frame[col]
        numeric = pd.to_numeric(series, errors="coerce")
        is_numeric = series.notna().any() and numeric.notna().mean() > 0.9
        entry: dict[str, Any] = {
            "name": col,
            "type": "numeric" if is_numeric else "categorical",
            "missing_count": int(series.isna().sum()),
        }
        if is_numeric:
            vals = numeric.dropna()
            entry["min"] = float(vals.min()) if not vals.empty else None
            entry["max"] = float(vals.max()) if not vals.empty else None
            entry["median"] = float(vals.median()) if not vals.empty else None
        else:
            uniques = [str(v) for v in series.dropna().unique()]
            entry["categories"] = uniques[:_MAX_CATEGORICAL_DOMAIN]
            entry["categories_truncated"] = len(uniques) > _MAX_CATEGORICAL_DOMAIN
        schema.append(entry)
    return schema


def _coerce_features(experiment: Experiment, storage: LocalObjectStorage, raw: dict[str, Any]) -> pd.DataFrame:
    """Validate + coerce user input into a one-row feature frame."""
    if not isinstance(raw, dict) or not raw:
        raise AppError(422, "validation_error", "features must be a non-empty object.")
    if len(raw) > 500:
        raise AppError(422, "validation_error", "Too many feature values supplied.")

    schema = _feature_schema(experiment, storage)
    known = {f["name"]: f for f in schema}
    unknown = [k for k in raw if k not in known]
    if unknown:
        raise AppError(422, "validation_error", f"Unknown feature(s): {', '.join(unknown)}")
    missing = [name for name in known if name not in raw]
    if missing:
        raise AppError(422, "validation_error", f"Missing required feature(s): {', '.join(missing)}")

    row: dict[str, Any] = {}
    for name, spec in known.items():
        value = raw[name]
        if spec["type"] == "numeric":
            try:
                num = float(value)
            except (TypeError, ValueError):
                raise AppError(422, "validation_error", f"Feature '{name}' must be numeric, got {value!r}") from None
            if not np.isfinite(num):
                raise AppError(422, "validation_error", f"Feature '{name}' must be a finite number.")
            row[name] = num
        else:
            if value is None or (isinstance(value, float) and np.isnan(value)):
                raise AppError(422, "validation_error", f"Feature '{name}' is required (categorical).")
            sval = str(value)
            cats = spec.get("categories") or []
            if cats and sval not in cats:
                raise AppError(422, "validation_error", f"Feature '{name}' must be one of the observed categories.")
            row[name] = sval
    return pd.DataFrame([row])


def _predict_payload(model, frame: pd.DataFrame, task_type: str) -> dict[str, Any]:
    pred = model.predict(frame)
    out: dict[str, Any] = {"prediction": pred[0].item() if hasattr(pred[0], "item") else pred[0]}
    if task_type == "classification" and hasattr(model, "predict_proba"):
        try:
            proba = model.predict_proba(frame)[0]
            classes = getattr(model, "classes_", None)
            if classes is None:
                # Pipeline: classes live on the final estimator.
                final = model.steps[-1][1] if hasattr(model, "steps") else model
                classes = getattr(final, "classes_", None)
            if classes is not None:
                out["probabilities"] = {str(c): round(float(p), 6) for c, p in zip(classes, proba)}
        except Exception:
            pass  # probability output is best-effort; prediction stands alone
    return out


def _normalize(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Min-max normalize a numeric series to [0,1] using observed bounds."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.0, index=series.index), pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo), (hi - lo)


def _distance(row_a: pd.Series, row_b: pd.Series, schema: list[dict[str, Any]]) -> float:
    """Normalized L1 distance over mutable features (0 = identical)."""
    total = 0.0
    count = 0
    for spec in schema:
        name = spec["name"]
        if spec["type"] == "numeric":
            span = (spec.get("max") or 0) - (spec.get("min") or 0)
            if span and span > 0:
                total += abs(float(row_a[name]) - float(row_b[name])) / span
                count += 1
        else:
            total += 0.0 if str(row_a[name]) == str(row_b[name]) else 1.0
            count += 1
    return round(total / max(count, 1), 6)


def get_whatif_schema(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_experiment_model(experiment)
    schema = _feature_schema(experiment, storage)
    final = model.steps[-1][1] if hasattr(model, "steps") else model
    classes = getattr(final, "classes_", None)
    return {
        "experiment_id": experiment.id,
        "task_type": experiment.task_type,
        "target_column": experiment.target_column,
        "features": schema,
        "classes": [str(c) for c in classes] if classes is not None else None,
        "supports_probabilities": task_type_supports_proba(model, experiment.task_type),
    }


def task_type_supports_proba(model, task_type: str) -> bool:
    return task_type == "classification" and hasattr(model, "predict_proba")


def _record_run(db: Session, experiment_id: uuid.UUID, kind: str, input_data: dict, output_data: dict) -> None:
    try:
        from app.db.models import WhatIfRun

        db.add(WhatIfRun(experiment_id=experiment_id, kind=kind, input_data=input_data, output_data=output_data))
        db.commit()
    except Exception:
        db.rollback()  # persistence is best-effort; never fail the analysis


def predict_whatif(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID, features: dict[str, Any]) -> dict[str, Any]:
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_experiment_model(experiment)
    frame = _coerce_features(experiment, storage, features)
    result = _predict_payload(model, frame, experiment.task_type)
    _record_run(db, experiment.id, "predict", {"features": features}, result)
    return {"experiment_id": experiment.id, "input": features, "output": result}


def _perturb(rng: np.random.Generator, base: dict[str, Any], schema: list[dict[str, Any]], immutable: set[str], k: int) -> dict[str, Any]:
    row = dict(base)
    mutable = [f for f in schema if f["name"] not in immutable]
    if not mutable:
        return row
    for spec in rng.choice(mutable, size=min(k, len(mutable)), replace=False):
        name = spec["name"]
        if spec["type"] == "numeric":
            lo, hi = spec.get("min"), spec.get("max")
            if lo is None or hi is None or hi <= lo:
                continue
            # Gaussian perturbation around current value, clipped to observed range.
            span = hi - lo
            new_val = float(row[name]) + rng.normal(0, span / 6)
            row[name] = round(float(np.clip(new_val, lo, hi)), 6)
        else:
            cats = spec.get("categories") or []
            if len(cats) > 1:
                row[name] = str(rng.choice(cats))
    return row


def _goal_met(pred_payload: dict[str, Any], goal: dict[str, Any], task_type: str) -> bool:
    pred = pred_payload["prediction"]
    if task_type == "classification":
        target = goal.get("class")
        return target is not None and str(pred) == str(target)
    if "min" in goal or "max" in goal:
        try:
            v = float(pred)
        except (TypeError, ValueError):
            return False
        if "min" in goal and v < float(goal["min"]):
            return False
        if "max" in goal and v > float(goal["max"]):
            return False
        return True
    if "value" in goal:
        try:
            return abs(float(pred) - float(goal["value"])) <= max(1e-6, abs(float(goal["value"])) * 0.001)
        except (TypeError, ValueError):
            return False
    return False


def generate_counterfactuals(
    db: Session,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
    experiment_id: uuid.UUID,
    features: dict[str, Any],
    goal: dict[str, Any],
    n_candidates: int = _MAX_RETURN,
    seed: int = 42,
    immutable: list[str] | None = None,
) -> dict[str, Any]:
    """Randomized search for minimal-change inputs reaching the goal prediction.

    This finds MODEL counterfactuals — feature combinations the persisted
    model would score differently. It is not a causal or real-world claim.
    """
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_experiment_model(experiment)
    schema = _feature_schema(experiment, storage)
    known = {f["name"] for f in schema}
    immutable_set = set(immutable or []) & known
    if immutable_set - known:
        raise AppError(422, "validation_error", "Immutable features must be valid feature names.")

    if experiment.task_type == "classification":
        final = model.steps[-1][1] if hasattr(model, "steps") else model
        raw_classes = getattr(final, "classes_", None)
        classes = [str(c) for c in raw_classes] if raw_classes is not None else []
        target_class = goal.get("class")
        if target_class is None or str(target_class) not in classes:
            raise AppError(422, "validation_error", f"goal.class must be one of: {', '.join(classes)}")
    else:
        if not any(k in goal for k in ("value", "min", "max")):
            raise AppError(422, "validation_error", "Regression counterfactuals need goal.value or goal.min/goal.max.")

    n_candidates = max(1, min(int(n_candidates), _MAX_CANDIDATES))
    frame = _coerce_features(experiment, storage, features)
    base_row = {c: frame.iloc[0][c] for c in frame.columns}
    original = _predict_payload(model, frame, experiment.task_type)

    rng = np.random.default_rng(seed)
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    mutable_count = len([f for f in schema if f["name"] not in immutable_set])

    for i in range(n_candidates * 4):  # bounded search; early exit when enough found
        k = int(rng.integers(1, max(2, min(mutable_count, 4))))
        candidate = _perturb(rng, base_row, schema, immutable_set, k)
        key = json.dumps(candidate, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        try:
            cframe = pd.DataFrame([candidate])
            payload = _predict_payload(model, cframe, experiment.task_type)
        except Exception:
            continue
        if not _goal_met(payload, goal, experiment.task_type):
            continue
        changed = {name: {"from": base_row[name], "to": candidate[name]} for name in candidate if str(candidate[name]) != str(base_row[name])}
        dist = _distance(pd.Series(base_row), pd.Series(candidate), [f for f in schema if f["name"] not in immutable_set])
        accepted.append({
            "features": candidate,
            "changed_features": changed,
            "prediction": payload,
            "distance": dist,
            "feasibility": round(max(0.0, 1.0 - dist), 4),
        })
        if len(accepted) >= _MAX_RETURN:
            break

    accepted.sort(key=lambda c: (c["distance"], -c["feasibility"]))
    response = {
        "experiment_id": experiment.id,
        "task_type": experiment.task_type,
        "goal": goal,
        "immutable_features": sorted(immutable_set),
        "original": {"input": features, "output": original},
        "counterfactuals": accepted[:_MAX_RETURN],
        "candidates_evaluated": len(seen),
        "note": "Counterfactuals are model-space explanations, not guaranteed real-world outcomes.",
    }
    _record_run(db, experiment.id, "counterfactual", {"features": features, "goal": goal, "seed": seed}, response)
    return response
