import csv
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import joblib
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.core.logging import get_logger, log_event
from app.db.models import Dataset, DatasetVersion, Experiment, ExperimentModelResult, Project
from app.ml_engine.models import MODEL_CATALOG
from app.ml_engine.preprocessing import SplitConfig, validate_split_config, validate_task_target
from app.ml_engine.training import run_experiment
from app.services.projects import get_owned_project
from app.storage import LocalObjectStorage

log = get_logger("experiments")


def _verify_persisted_artifacts(storage: LocalObjectStorage, experiment_id: uuid.UUID, model_key: str, manifest_key: str) -> None:
    if not storage.exists(model_key):
        raise RuntimeError(f"Model file write failed: {model_key} not found after storage.put()")
    try:
        with storage.open(model_key) as model_file:
            loaded_model = joblib.load(model_file)
    except Exception as exc:  # pragma: no cover - defensive check for corrupted artifacts
        raise RuntimeError(f"Model file failed to load from storage for experiment {experiment_id}: {exc}") from exc
    if not hasattr(loaded_model, "predict"):
        raise RuntimeError(f"Saved model for experiment {experiment_id} does not expose a usable predict() method.")

    if not storage.exists(manifest_key):
        raise RuntimeError(f"Manifest file write failed: {manifest_key} not found after storage.put()")
    try:
        with storage.open(manifest_key) as manifest_file:
            manifest = json.load(manifest_file)
    except Exception as exc:  # pragma: no cover - defensive check for corrupted manifest
        raise RuntimeError(f"Manifest file failed to load for experiment {experiment_id}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Manifest file for experiment {experiment_id} is not a JSON object.")
    if manifest.get("experiment_id") != str(experiment_id):
        raise RuntimeError(f"Manifest experiment_id mismatch for experiment {experiment_id}: {manifest.get('experiment_id')!r}")


def list_experiments(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[Experiment]:
    get_owned_project(db, owner_id, project_id)
    stmt = (
        select(Experiment)
        .where(Experiment.project_id == project_id)
        .order_by(Experiment.created_at.desc(), Experiment.id)
    )
    return list(db.scalars(stmt))


def get_owned_experiment(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> Experiment:
    get_owned_project(db, owner_id, project_id)
    experiment = db.scalar(
        select(Experiment).where(Experiment.id == experiment_id, Experiment.project_id == project_id)
    )
    if experiment is None:
        raise not_found("Experiment")
    return experiment


def _run_training_job(experiment_id: uuid.UUID) -> None:
    """Background worker for experiment training and artifact persistence."""
    from app.db.session import get_sessionmaker

    session_factory = get_sessionmaker()
    with session_factory() as db:
        experiment = db.get(Experiment, experiment_id)
        if experiment is None:
            return

        experiment.status = "running"
        experiment.started_at = datetime.now(timezone.utc)
        experiment.completed_at = None
        experiment.error = None
        db.commit()

        try:
            dataset = db.get(Dataset, experiment.dataset_id)
            if dataset is None:
                raise RuntimeError(f"Dataset {experiment.dataset_id} no longer exists.")

            version = db.get(DatasetVersion, experiment.dataset_version_id)
            if version is None:
                raise RuntimeError(f"Dataset version {experiment.dataset_version_id} no longer exists.")

            storage = LocalObjectStorage()
            with storage.open(version.file_path) as raw_file:
                import pandas as pd

                with io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="") as text_file:
                    frame = pd.read_csv(text_file)

            config = SplitConfig(
                train_fraction=experiment.train_fraction,
                validation_fraction=experiment.validation_fraction,
                test_fraction=experiment.test_fraction,
                random_seed=experiment.random_seed,
            )
            result = run_experiment(
                frame,
                experiment.target_column,
                experiment.task_type,
                list(experiment.model_names),
                config,
                preprocessing_config=experiment.preprocessing_config,
                tuning_config=experiment.tuning_config,
            )

            model_buf = io.BytesIO()
            joblib.dump(result["trained_model"], model_buf)
            model_buf.seek(0)
            model_key = f"experiments/{experiment.id}/model.joblib"
            storage.put(model_key, model_buf)

            manifest: dict[str, Any] = {
                "experiment_id": str(experiment.id),
                "dataset_version_id": str(experiment.dataset_version_id),
                "dataset_sha256": version.sha256_checksum,
                "task_type": experiment.task_type,
                "target_column": experiment.target_column,
                "random_seed": config.random_seed,
                "train_fraction": config.train_fraction,
                "validation_fraction": config.validation_fraction,
                "test_fraction": config.test_fraction,
                "best_model_name": result["best_model_name"],
                "model_names_evaluated": list(experiment.model_names),
                "preprocessing_config": experiment.preprocessing_config or {},
                "tuning_config": experiment.tuning_config or {},
                "validation_metrics": result["validation_metrics"],
                "test_metrics": result["test_metrics"],
            }
            manifest_key = f"experiments/{experiment.id}/manifest.json"
            manifest_buf = io.BytesIO(json.dumps(manifest, indent=2).encode("utf-8"))
            storage.put(manifest_key, manifest_buf)
            _verify_persisted_artifacts(storage, experiment.id, model_key, manifest_key)

            experiment.status = "completed"
            experiment.completed_at = datetime.now(timezone.utc)
            experiment.metrics = {
                "best_model_name": result["best_model_name"],
                "best_metrics": result["best_metrics"],
                "cross_validation_metrics": result["cross_validation_metrics"],
                "validation_metrics": result["validation_metrics"],
                "test_metrics": result["test_metrics"],
            }
            experiment.artifact_uri = f"local://{model_key}"
            experiment.error = None

            # Persist every candidate's evaluation results (winners and
            # failures alike) so the experiment detail is fully auditable.
            for entry in result.get("model_results", []):
                db.add(
                    ExperimentModelResult(
                        experiment_id=experiment.id,
                        model_name=entry["model_name"],
                        task_type=experiment.task_type,
                        is_selected=bool(entry.get("is_selected")),
                        status=entry.get("status", "failed"),
                        error=entry.get("error"),
                        cross_validation_metrics=entry.get("cross_validation_metrics") or {},
                        validation_metrics=entry.get("validation_metrics") or {},
                        test_metrics=entry.get("test_metrics") or {},
                        confusion_matrix=entry.get("confusion_matrix"),
                        classification_report=entry.get("classification_report"),
                        best_params=entry.get("best_params"),
                        training_duration_ms=entry.get("training_duration_ms"),
                    )
                )
            db.commit()
        except Exception as exc:
            experiment.status = "failed"
            experiment.artifact_uri = None
            experiment.error = str(exc)
            experiment.completed_at = datetime.now(timezone.utc)
            db.commit()
            # Remove any partial artifacts (model/manifest written before the
            # failure). Best-effort: failures are logged, never hidden.
            cleanup_experiment_artifacts(storage, experiment.id)


def cleanup_experiment_artifacts(storage: LocalObjectStorage, experiment_id: uuid.UUID) -> dict[str, Any]:
    """Delete everything under ``experiments/{id}/``. Returns a cleanup report.

    Only ever touches the given experiment's own prefix — the storage layer's
    containment guard plus the server-generated key make cross-experiment or
    path-traversal deletion impossible. Missing files are ignored; failures
    are counted and logged, not swallowed.
    """
    prefix = f"experiments/{experiment_id}/"
    try:
        report = storage.delete_prefix(prefix)
    except Exception as exc:
        log_event(log, "artifact_cleanup_failed", level=40, experiment_id=str(experiment_id), error=str(exc))
        return {"prefix": prefix, "deleted": 0, "failed": -1, "error": str(exc)}
    if report["failed"]:
        log_event(
            log, "artifact_cleanup_partial", level=30,
            experiment_id=str(experiment_id), deleted=report["deleted"], failed=report["failed"],
        )
    else:
        log_event(log, "artifact_cleanup_completed", experiment_id=str(experiment_id), deleted=report["deleted"])
    return {"prefix": prefix, **report}


def delete_experiment(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    """Delete an experiment row and its stored artifacts.

    Model-result rows cascade with the experiment. Artifact files are removed
    best-effort; the report tells the caller honestly what could not be
    deleted rather than claiming a clean sweep.
    """
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    storage = LocalObjectStorage()
    cleanup = cleanup_experiment_artifacts(storage, experiment.id)
    db.delete(experiment)
    db.commit()
    log_event(log, "experiment_deleted", experiment_id=str(experiment_id), user_id=str(owner_id), cleanup=cleanup)
    return cleanup


def create_experiment(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, payload: dict[str, Any]) -> Experiment:
    get_owned_project(db, owner_id, project_id)

    dataset_id = payload["dataset_id"]
    version_id = payload["dataset_version_id"]
    target_column = payload["target_column"]
    task_type = payload["task_type"]
    model_names = payload.get("model_names") or ["Logistic Regression"]
    if not model_names:
        raise AppError(422, "validation_error", "At least one model must be selected.")

    valid_models = MODEL_CATALOG.get(task_type, {})
    invalid_models = [name for name in model_names if name not in valid_models]
    if invalid_models:
        raise AppError(
            422,
            "validation_error",
            f"Unknown model(s) for task '{task_type}': {', '.join(invalid_models)}. "
            f"Valid options: {', '.join(valid_models)}.",
        )

    dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id, Dataset.project_id == project_id))
    if dataset is None:
        raise not_found("Dataset")

    version = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.id == version_id,
            DatasetVersion.dataset_id == dataset.id,
        )
    )
    if version is None:
        raise not_found("Dataset version")

    storage = LocalObjectStorage()
    with storage.open(version.file_path) as raw_file:
        with io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="") as text_file:
            rows = list(csv.DictReader(text_file))
    fieldnames = list(rows[0].keys()) if rows else []
    if not fieldnames and version.row_count is not None and version.row_count > 0:
        raise AppError(422, "validation_error", "Dataset file does not include a header row.")
    if target_column not in fieldnames:
        raise AppError(422, "validation_error", f"Target column '{target_column}' not found in dataset.")

    try:
        with storage.open(version.file_path) as raw_file:
            import pandas as pd

            with io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="") as text_file:
                frame = pd.read_csv(text_file)
        validate_task_target(frame, target_column, task_type)
    except ValueError as exc:
        raise AppError(422, "validation_error", str(exc)) from exc

    config = SplitConfig(
        train_fraction=float(payload.get("train_fraction", 0.7)),
        validation_fraction=float(payload.get("validation_fraction", 0.15)),
        test_fraction=float(payload.get("test_fraction", 0.15)),
        random_seed=int(payload.get("random_seed", 42)),
    )
    try:
        validate_split_config(config)
    except ValueError as exc:
        raise AppError(422, "validation_error", str(exc)) from exc

    experiment = Experiment(
        project_id=project_id,
        dataset_id=dataset_id,
        dataset_version_id=version_id,
        name=str(payload["name"]),
        task_type=task_type,
        target_column=target_column,
        train_fraction=config.train_fraction,
        validation_fraction=config.validation_fraction,
        test_fraction=config.test_fraction,
        random_seed=config.random_seed,
        model_names=list(model_names),
        preprocessing_config=payload.get("preprocessing") if isinstance(payload.get("preprocessing"), dict) else None,
        tuning_config=payload.get("tuning") if isinstance(payload.get("tuning"), dict) else None,
        status="queued",
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)

    from app.jobs import get_job_queue

    job_queue = get_job_queue()
    job_queue.enqueue(str(experiment.id), lambda: _run_training_job(experiment.id))
    return experiment


def get_model_results(db: Session, experiment_id: uuid.UUID) -> list[ExperimentModelResult]:
    """All persisted per-model evaluation rows for an experiment, oldest first."""
    stmt = (
        select(ExperimentModelResult)
        .where(ExperimentModelResult.experiment_id == experiment_id)
        .order_by(ExperimentModelResult.created_at, ExperimentModelResult.id)
    )
    return list(db.scalars(stmt))


def get_experiment_evaluation(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID):
    """Owner-checked experiment + its persisted per-model results."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    return experiment, get_model_results(db, experiment.id)


def _model_config_descriptors(task_type: str, names: list[str]) -> dict[str, Any]:
    """JSON-safe description of each requested model's estimator + params."""
    out: dict[str, Any] = {}
    choices = MODEL_CATALOG.get(task_type, {})
    for name in names:
        entry = choices.get(name)
        if entry is None:
            continue
        estimator = entry["factory"]
        try:
            params = estimator.get_params()
        except Exception:
            params = {}
        out[name] = {
            "estimator": type(estimator).__name__,
            "params": {k: v for k, v in params.items() if isinstance(v, (str, int, float, bool, type(None)))},
        }
    return out


_PREPROCESSING_DESCRIPTION = {
    "numeric": {"imputer": "median", "scaler": "standard"},
    "categorical": {"imputer": "most_frequent", "encoder": "one_hot", "handle_unknown": "ignore"},
    "remainder": "drop",
    "fit_scope": "training_split_only",
}


def _read_manifest(storage: LocalObjectStorage, experiment_id: uuid.UUID):
    """Return (manifest_dict_or_None, error_or_None) for the stored manifest."""
    manifest_key = f"experiments/{experiment_id}/manifest.json"
    if not storage.exists(manifest_key):
        return None, "manifest.json not found in storage"
    try:
        with storage.open(manifest_key) as f:
            manifest = json.load(f)
        if not isinstance(manifest, dict):
            return None, "manifest is not a JSON object"
        if manifest.get("experiment_id") != str(experiment_id):
            return None, "manifest experiment_id mismatch"
        return manifest, None
    except Exception as exc:
        return None, f"manifest unreadable: {exc}"


def get_experiment_reproducibility(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    """Everything needed to reproduce a run: seed, splits, data identity,
    model + preprocessing configuration, and the stored manifest."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    version = (
        db.get(DatasetVersion, experiment.dataset_version_id)
        if experiment.dataset_version_id is not None
        else None
    )

    storage = LocalObjectStorage()
    manifest, _manifest_err = _read_manifest(storage, experiment.id)

    return {
        "experiment_id": experiment.id,
        "name": experiment.name,
        "task_type": experiment.task_type,
        "target_column": experiment.target_column,
        "random_seed": experiment.random_seed,
        "train_fraction": experiment.train_fraction,
        "validation_fraction": experiment.validation_fraction,
        "test_fraction": experiment.test_fraction,
        "dataset_id": experiment.dataset_id,
        "dataset_version_id": experiment.dataset_version_id,
        "dataset_sha256": version.sha256_checksum if version else None,
        "model_names": list(experiment.model_names or []),
        "model_configs": _model_config_descriptors(experiment.task_type, list(experiment.model_names or [])),
        "preprocessing": {
            **_PREPROCESSING_DESCRIPTION,
            "configured": experiment.preprocessing_config or {},
        },
        "manifest": manifest,
        "manifest_available": manifest is not None,
    }


def get_experiment_artifact(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    """Artifact availability + manifest verification status (no file download)."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    storage = LocalObjectStorage()

    artifact_uri = experiment.artifact_uri
    model_key = artifact_uri.removeprefix("local://") if artifact_uri else None
    model_available = bool(model_key) and storage.exists(model_key)
    model_size = storage.get_file_size(model_key) if model_available else None

    manifest, manifest_err = _read_manifest(storage, experiment.id)

    return {
        "experiment_id": experiment.id,
        "available": model_available,
        "artifact_uri": artifact_uri if model_available else None,
        "model_file_size_bytes": model_size,
        "manifest_verified": manifest is not None,
        "manifest_error": manifest_err,
    }
