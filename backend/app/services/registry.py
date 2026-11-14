"""Model registry: registration, versioning, lifecycle, validation, comparison."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, conflict, not_found
from app.db.models import Experiment, ModelTransition, ModelVersion, RegisteredModel
from app.services.experiments import get_owned_experiment
from app.services.projects import get_owned_project
from app.storage import LocalObjectStorage

_STATES = {"registered", "validated", "staging", "production", "archived", "failed"}
# validated/staging/production require prior validation; production requires validated.
_ALLOWED = {
    "registered": {"validated", "staging", "archived", "failed"},
    "validated": {"staging", "production", "archived", "failed"},
    "staging": {"production", "archived", "failed"},
    "production": {"archived", "failed", "staging"},
    "archived": {"registered", "failed"},
    "failed": {"registered"},
}
_METRIC_KEYS = {
    "classification": ["accuracy", "f1_macro", "precision_macro", "recall_macro", "roc_auc"],
    "regression": ["mae", "mse", "rmse", "r2"],
}


def _get_model(db: Session, project_id: uuid.UUID, model_id: uuid.UUID) -> RegisteredModel:
    model = db.scalar(select(RegisteredModel).where(RegisteredModel.id == model_id, RegisteredModel.project_id == project_id))
    if model is None:
        raise not_found("Model")
    return model


def _get_version(db: Session, model: RegisteredModel, version_id: uuid.UUID) -> ModelVersion:
    v = db.scalar(select(ModelVersion).where(ModelVersion.id == version_id, ModelVersion.model_id == model.id))
    if v is None:
        raise not_found("Model version")
    return v


def register_model(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID, name: str | None, description: str | None) -> ModelVersion:
    get_owned_project(db, owner_id, project_id)
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    if experiment.status != "completed" or not experiment.artifact_uri:
        raise AppError(409, "experiment_not_ready", "Only completed experiments with artifacts can be registered.")

    key = experiment.artifact_uri.removeprefix("local://")
    storage = LocalObjectStorage()
    if not storage.exists(key):
        raise AppError(409, "artifact_missing", "Experiment artifact is missing from storage.")
    checksum = storage.compute_sha256(key)
    size = storage.get_file_size(key)

    metrics = experiment.metrics or {}
    best_name = metrics.get("best_model_name") or (experiment.model_names[0] if experiment.model_names else "model")
    model_name = (name or best_name).strip()[:120] or best_name

    model = db.scalar(select(RegisteredModel).where(RegisteredModel.project_id == project_id, RegisteredModel.name == model_name))
    if model is None:
        model = RegisteredModel(project_id=project_id, name=model_name, description=description, task_type=experiment.task_type, created_by=owner_id)
        db.add(model)
        db.flush()

    # Duplicate registration of the same experiment is rejected.
    existing = db.scalar(select(ModelVersion).where(ModelVersion.experiment_id == experiment.id, ModelVersion.model_id == model.id))
    if existing is not None:
        raise conflict("This experiment is already registered as a version of this model.")

    next_v = (db.scalar(select(func.max(ModelVersion.version_number)).where(ModelVersion.model_id == model.id)) or 0) + 1
    version = ModelVersion(
        model_id=model.id, version_number=next_v, experiment_id=experiment.id,
        dataset_version_id=experiment.dataset_version_id, artifact_key=key,
        checksum_sha256=checksum, file_size_bytes=size or 0,
        algorithm=best_name, framework="scikit-learn",
        metrics=metrics, config={
            "task_type": experiment.task_type, "target_column": experiment.target_column,
            "random_seed": experiment.random_seed, "model_names": list(experiment.model_names or []),
            "preprocessing_config": experiment.preprocessing_config or {},
            "tuning_config": experiment.tuning_config or {},
            "splits": {"train": experiment.train_fraction, "validation": experiment.validation_fraction, "test": experiment.test_fraction},
        },
        lifecycle_status="registered", created_by=owner_id,
    )
    db.add(version)
    db.flush()
    _transition(db, version, None, "registered", owner_id, "Registered from experiment")
    db.commit()
    db.refresh(version)
    return version


def list_models(db: Session, project_id: uuid.UUID) -> list[dict[str, Any]]:
    models = list(db.scalars(select(RegisteredModel).where(RegisteredModel.project_id == project_id).order_by(RegisteredModel.created_at.desc())))
    out = []
    for m in models:
        latest = db.scalar(select(ModelVersion).where(ModelVersion.model_id == m.id).order_by(ModelVersion.version_number.desc()))
        out.append({
            "id": m.id, "name": m.name, "description": m.description, "task_type": m.task_type,
            "created_at": m.created_at, "version_count": len(m.versions),
            "latest_version": _version_out(latest) if latest else None,
        })
    return out


def _version_out(v: ModelVersion) -> dict[str, Any]:
    return {
        "id": v.id, "version_number": v.version_number, "experiment_id": v.experiment_id,
        "dataset_version_id": v.dataset_version_id, "algorithm": v.algorithm, "framework": v.framework,
        "checksum_sha256": v.checksum_sha256, "file_size_bytes": v.file_size_bytes,
        "metrics": v.metrics, "config": v.config, "lifecycle_status": v.lifecycle_status,
        "validation": v.validation, "created_at": v.created_at,
    }


def get_model_detail(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    model = _get_model(db, project_id, model_id)
    versions = list(db.scalars(select(ModelVersion).where(ModelVersion.model_id == model.id).order_by(ModelVersion.version_number.desc())))
    return {
        "id": model.id, "name": model.name, "description": model.description, "task_type": model.task_type,
        "created_at": model.created_at,
        "versions": [_version_out(v) for v in versions],
        "production_version_id": next((v.id for v in versions if v.lifecycle_status == "production"), None),
    }


def compare_versions(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, version_ids: list[uuid.UUID]) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    if len(version_ids) < 2 or len(version_ids) > 6:
        raise AppError(422, "validation_error", "Provide 2-6 version IDs to compare.")
    rows = []
    for vid in version_ids:
        v = db.scalar(select(ModelVersion).where(ModelVersion.id == vid))
        if v is None:
            raise not_found("Model version")
        m = _get_model(db, project_id, v.model_id)  # enforces project ownership
        metrics = (v.metrics or {}).get("validation_metrics") or {}
        rows.append({
            "version_id": v.id, "model_name": m.name, "version_number": v.version_number,
            "algorithm": v.algorithm, "task_type": m.task_type, "lifecycle_status": v.lifecycle_status,
            "metrics": {k: metrics.get(k) for k in _METRIC_KEYS.get(m.task_type, [])},
            "training_duration_ms": None,
        })
    task_types = {r["task_type"] for r in rows}
    if len(task_types) > 1:
        raise AppError(422, "validation_error", "Cannot compare models with different task types.")
    return {"task_type": rows[0]["task_type"], "versions": rows}


def _transition(db: Session, version: ModelVersion, from_status: str | None, to_status: str, actor_id: uuid.UUID | None, note: str | None = None) -> None:
    db.add(ModelTransition(version_id=version.id, from_status=from_status or version.lifecycle_status, to_status=to_status, actor_id=actor_id, note=note))
    version.lifecycle_status = to_status


def validate_version(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    model = _get_model(db, project_id, model_id)
    v = _get_version(db, model, version_id)
    storage = LocalObjectStorage()
    result = _validate_version_inner(db, v, storage)
    v.validation = result
    if result["ok"] and v.lifecycle_status in ("registered", "failed"):
        _transition(db, v, v.lifecycle_status, "validated", owner_id, "Validation passed")
    elif not result["ok"] and v.lifecycle_status == "registered":
        pass  # stays registered; failure is recorded in validation report
    db.commit()
    return {"version_id": v.id, "validation": result, "lifecycle_status": v.lifecycle_status}


def _validate_version_inner(db: Session, version: ModelVersion, storage: LocalObjectStorage) -> dict[str, Any]:
    checks: dict[str, Any] = {"ok": True, "checks": {}, "reasons": []}
    c = checks["checks"]
    c["artifact_exists"] = storage.exists(version.artifact_key)
    if not c["artifact_exists"]:
        checks["reasons"].append("artifact file missing")
    else:
        c["checksum_match"] = storage.compute_sha256(version.artifact_key) == version.checksum_sha256
        if not c["checksum_match"]:
            checks["reasons"].append("artifact checksum mismatch")
        c["file_size_match"] = (storage.get_file_size(version.artifact_key) or -1) == version.file_size_bytes
        if not c["file_size_match"]:
            checks["reasons"].append("artifact size mismatch")
    exp = db.get(Experiment, version.experiment_id)
    c["experiment_completed"] = exp is not None and exp.status == "completed"
    if not c["experiment_completed"]:
        checks["reasons"].append("source experiment not completed")
    vm = (version.metrics or {}).get("validation_metrics") or {}
    c["metrics_present"] = bool(vm)
    if not c["metrics_present"]:
        checks["reasons"].append("no validation metrics recorded")
    checks["ok"] = all(val for key, val in c.items())
    checks["validated_at"] = datetime.now(timezone.utc).isoformat()
    return checks


def transition_version(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, to_status: str, note: str | None) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    model = _get_model(db, project_id, model_id)
    v = _get_version(db, model, version_id)
    to_status = to_status.lower()
    if to_status not in _STATES:
        raise AppError(422, "validation_error", f"Unknown lifecycle state '{to_status}'.")
    current = v.lifecycle_status
    if to_status == "validated":
        # Validation must go through the validate endpoint.
        raise AppError(422, "validation_error", "Use the validate endpoint to mark a version validated.")
    if to_status == "production":
        val = v.validation or {}
        if not val.get("ok"):
            raise AppError(409, "validation_required", "Version must pass validation before production promotion.")
    allowed = _ALLOWED.get(current, set())
    if to_status not in allowed:
        raise AppError(409, "invalid_transition", f"Cannot transition {current} -> {to_status}.")
    if to_status == "production":
        # Only one production version per model.
        others = db.scalars(select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.id != v.id, ModelVersion.lifecycle_status == "production"))
        for o in others:
            _transition(db, o, "production", "staging", owner_id, f"Superseded by v{o.version_number} -> v{v.version_number}")
    _transition(db, v, current, to_status, owner_id, note)
    db.commit()
    return {"version_id": v.id, "from": current, "to": to_status, "lifecycle_status": v.lifecycle_status}


def rollback_version(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID, target_version_id: uuid.UUID | None) -> dict[str, Any]:
    """Roll back: demote current production, promote a previous validated/staging version."""
    get_owned_project(db, owner_id, project_id)
    model = _get_model(db, project_id, model_id)
    current_prod = db.scalar(select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.lifecycle_status == "production"))
    if current_prod is None:
        raise AppError(409, "no_production", "No production version to roll back.")
    if target_version_id is None:
        candidates = db.scalars(
            select(ModelVersion).where(
                ModelVersion.model_id == model.id,
                ModelVersion.id != current_prod.id,
                ModelVersion.lifecycle_status.in_(["validated", "staging", "archived"]),
            ).order_by(ModelVersion.version_number.desc())
        )
        target = next(iter(candidates), None)
    else:
        target = _get_version(db, model, target_version_id)
        if target.lifecycle_status not in ("validated", "staging", "archived") and not (target.validation or {}).get("ok"):
            raise AppError(409, "not_eligible", "Rollback target must be validated or better.")
    if target is None:
        raise AppError(409, "no_eligible_version", "No eligible previous version found for rollback.")
    _transition(db, current_prod, "production", "staging", owner_id, f"Rolled back to v{target.version_number}")
    if target.lifecycle_status != "production":
        _transition(db, target, target.lifecycle_status, "production", owner_id, f"Rollback target (was production v{current_prod.version_number})")
    db.commit()
    return {"rolled_back_from": current_prod.id, "production_version_id": target.id}


def version_history(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, model_id: uuid.UUID, version_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    model = _get_model(db, project_id, model_id)
    v = _get_version(db, model, version_id)
    transitions = [
        {"from": t.from_status, "to": t.to_status, "actor_id": t.actor_id, "note": t.note, "created_at": t.created_at}
        for t in sorted(v.transitions, key=lambda t: t.created_at)
    ]
    return {"version_id": v.id, "lifecycle_status": v.lifecycle_status, "validation": v.validation, "transitions": transitions}
