"""Deployment management + CPU inference on registered model versions."""
from __future__ import annotations

import os
import time
import uuid
from collections import OrderedDict
from typing import Any

import joblib
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.db.models import Deployment, Experiment, ModelVersion, PredictionRecord, RegisteredModel
from app.services.projects import get_owned_project
from app.services import whatif as whatif_service
from app.storage import LocalObjectStorage

MAX_CACHE = int(os.getenv("MODEL_CACHE_SIZE", "8"))
LOG_INPUTS = os.getenv("PREDICTION_LOG_INPUTS", "true").lower() != "false"
MAX_FEATURES_BYTES = 64 * 1024

# Bounded LRU cache: version_id -> loaded pipeline
_CACHE: OrderedDict[uuid.UUID, Any] = OrderedDict()


def _cache_get(vid: uuid.UUID):
    if vid in _CACHE:
        _CACHE.move_to_end(vid)
        return _CACHE[vid]
    return None


def _cache_put(vid: uuid.UUID, model) -> None:
    _CACHE[vid] = model
    _CACHE.move_to_end(vid)
    while len(_CACHE) > MAX_CACHE:
        _CACHE.popitem(last=False)


def _get_deployment(db: Session, project_id: uuid.UUID, deployment_id: uuid.UUID) -> Deployment:
    d = db.scalar(select(Deployment).where(Deployment.id == deployment_id, Deployment.project_id == project_id))
    if d is None:
        raise not_found("Deployment")
    return d


def _get_version(db: Session, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID) -> tuple[RegisteredModel, ModelVersion]:
    model = db.scalar(select(RegisteredModel).where(RegisteredModel.id == model_id, RegisteredModel.project_id == project_id))
    if model is None:
        raise not_found("Model")
    v = db.scalar(select(ModelVersion).where(ModelVersion.id == version_id, ModelVersion.model_id == model.id))
    if v is None:
        raise not_found("Model version")
    return model, v


def deploy_version(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, config: dict[str, Any] | None) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    model, v = _get_version(db, project_id, model_id, version_id)

    if v.lifecycle_status != "production":
        raise AppError(409, "not_production", "Only versions in 'production' lifecycle state can be deployed.")
    val = v.validation or {}
    if not val.get("ok"):
        raise AppError(409, "validation_required", "Version must pass validation before deployment.")

    storage = LocalObjectStorage()
    if not storage.exists(v.artifact_key):
        raise AppError(409, "artifact_missing", "Model artifact is missing from storage.")
    if storage.compute_sha256(v.artifact_key) != v.checksum_sha256:
        raise AppError(409, "checksum_mismatch", "Artifact checksum does not match the registered version.")

    # Ensure artifact actually loads before marking active.
    try:
        with storage.open(v.artifact_key) as f:
            loaded = joblib.load(f)
        if not hasattr(loaded, "predict"):
            raise ValueError("no predict")
    except Exception as exc:
        raise AppError(500, "artifact_invalid", f"Artifact failed to load: {exc}") from exc

    existing = db.scalar(select(Deployment).where(Deployment.version_id == v.id, Deployment.status.in_(["pending", "deploying", "active"])))
    if existing is not None:
        raise AppError(409, "already_deployed", "This version already has an active or pending deployment.")

    d = Deployment(
        project_id=project_id, model_id=model.id, version_id=v.id,
        artifact_key=v.artifact_key, checksum_sha256=v.checksum_sha256,
        status="active", config=config or {}, created_by=owner_id,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return _deployment_out(d, model.name, v.version_number, v.algorithm, v.experiment_id)


def _deployment_out(d: Deployment, model_name: str | None = None, version_number: int | None = None,
                    algorithm: str | None = None, experiment_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "id": d.id, "project_id": d.project_id, "model_id": d.model_id, "version_id": d.version_id,
        "experiment_id": experiment_id,
        "model_name": model_name, "version_number": version_number, "algorithm": algorithm,
        "status": d.status, "config": d.config, "last_error": d.last_error,
        "created_at": d.created_at, "updated_at": d.updated_at,
    }


def list_deployments(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[dict[str, Any]]:
    get_owned_project(db, owner_id, project_id)
    rows = db.execute(
        select(Deployment, RegisteredModel.name, ModelVersion.version_number, ModelVersion.algorithm, ModelVersion.experiment_id)
        .join(RegisteredModel, Deployment.model_id == RegisteredModel.id)
        .join(ModelVersion, Deployment.version_id == ModelVersion.id)
        .where(Deployment.project_id == project_id)
        .order_by(Deployment.created_at.desc())
    ).all()
    return [_deployment_out(d, name, vn, alg, eid) for d, name, vn, alg, eid in rows]


def get_deployment(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    model = db.get(RegisteredModel, d.model_id)
    v = db.get(ModelVersion, d.version_id)
    out = _deployment_out(d, model.name if model else None, v.version_number if v else None, v.algorithm if v else None, v.experiment_id if v else None)
    out["checksum_sha256"] = d.checksum_sha256
    out["prediction_count"] = db.scalar(select(func.count(PredictionRecord.id)).where(PredictionRecord.deployment_id == d.id)) or 0
    return out


def stop_deployment(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    if d.status == "stopped":
        return _deployment_out(d)
    if d.status not in ("active", "pending", "deploying"):
        raise AppError(409, "invalid_state", f"Cannot stop a deployment in state '{d.status}'.")
    d.status = "stopped"
    _CACHE.pop(d.version_id, None)
    db.commit()
    return _deployment_out(d)


def _load_model_for_version(db: Session, version_id: uuid.UUID):
    cached = _cache_get(version_id)
    if cached is not None:
        return cached
    v = db.get(ModelVersion, version_id)
    if v is None:
        raise not_found("Model version")
    storage = LocalObjectStorage()
    if not storage.exists(v.artifact_key):
        raise AppError(404, "artifact_missing", "Model artifact is missing.")
    if storage.compute_sha256(v.artifact_key) != v.checksum_sha256:
        raise AppError(409, "checksum_mismatch", "Artifact checksum mismatch — refusing to load.")
    try:
        with storage.open(v.artifact_key) as f:
            model = joblib.load(f)
    except Exception as exc:
        raise AppError(500, "artifact_invalid", f"Artifact failed to load: {exc}") from exc
    if not hasattr(model, "predict"):
        raise AppError(500, "artifact_invalid", "Artifact does not expose predict().")
    _cache_put(version_id, model)
    return model


def predict(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID, features: dict[str, Any], request_id: str | None) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    if d.status != "active":
        raise AppError(409, "deployment_inactive", f"Deployment is '{d.status}', not active.")
    if not isinstance(features, dict) or not features:
        raise AppError(422, "validation_error", "features must be a non-empty object.")
    import json as _json
    if len(_json.dumps(features, default=str)) > MAX_FEATURES_BYTES:
        raise AppError(422, "validation_error", "Feature payload too large.")

    v = db.get(ModelVersion, d.version_id)
    exp = db.get(Experiment, v.experiment_id) if v else None
    if exp is None:
        raise AppError(409, "experiment_missing", "Source experiment unavailable.")

    rid = request_id or uuid.uuid4().hex[:16]
    started = time.perf_counter()
    record = PredictionRecord(
        deployment_id=d.id, request_id=rid, model_version_id=d.version_id,
        input_data=features if LOG_INPUTS else None, status="completed",
    )
    try:
        storage = LocalObjectStorage()
        model = _load_model_for_version(db, d.version_id)
        frame = whatif_service._coerce_features(exp, storage, features)
        payload = whatif_service._predict_payload(model, frame, exp.task_type)
        duration = int((time.perf_counter() - started) * 1000)
        record.duration_ms = duration
        record.output_data = payload
        db.add(record)
        db.commit()
        return {
            "request_id": rid, "deployment_id": d.id, "model_id": d.model_id,
            "model_version_id": d.version_id, "prediction": payload.get("prediction"),
            "probabilities": payload.get("probabilities"), "duration_ms": duration,
            "timestamp": record.created_at.isoformat() if record.created_at else None,
        }
    except AppError:
        raise
    except Exception as exc:
        duration = int((time.perf_counter() - started) * 1000)
        record.status = "failed"
        record.error = str(exc)[:500]
        record.duration_ms = duration
        db.add(record)
        db.commit()
        raise AppError(500, "inference_failed", f"Prediction failed: {exc}") from exc


def prediction_history(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    total = db.scalar(select(func.count(PredictionRecord.id)).where(PredictionRecord.deployment_id == d.id)) or 0
    rows = db.scalars(
        select(PredictionRecord).where(PredictionRecord.deployment_id == d.id)
        .order_by(PredictionRecord.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "deployment_id": d.id, "total": total, "limit": limit, "offset": offset,
        "records": [{
            "id": r.id, "request_id": r.request_id, "status": r.status,
            "input": r.input_data, "output": r.output_data, "duration_ms": r.duration_ms,
            "error": r.error, "created_at": r.created_at,
        } for r in rows],
    }
