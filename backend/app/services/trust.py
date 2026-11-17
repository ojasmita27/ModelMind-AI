"""Trust Receipt generation, integrity verification and reproducibility assessment."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import uuid
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.db.models import (
    DatasetVersion, Experiment, ExperimentModelResult, TrustReceipt,
)
from app.services.experiments import get_owned_experiment
from app.services.projects import get_owned_project
from app.storage import LocalObjectStorage

SIGNING_KEY = os.getenv("TRUST_RECEIPT_SIGNING_KEY")  # optional HMAC key; never hardcoded

_PACKAGES = ["scikit-learn", "pandas", "numpy", "joblib", "scipy"]


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _sign(digest: str) -> dict[str, Any] | None:
    if not SIGNING_KEY:
        return None
    sig = hmac.new(SIGNING_KEY.encode(), digest.encode(), hashlib.sha256).hexdigest()
    return {"algorithm": "HMAC-SHA256", "value": sig, "key_id": "env:TRUST_RECEIPT_SIGNING_KEY"}


def _env_versions() -> dict[str, str | None]:
    out = {}
    for p in _PACKAGES:
        try:
            out[p] = pkg_version(p)
        except Exception:
            out[p] = None
    out["python"] = platform.python_version()
    return out


def _dataset_evidence(db: Session, experiment: Experiment, storage: LocalObjectStorage) -> dict[str, Any]:
    """Dataset lineage + integrity; unavailable parts marked, never invented."""
    out: dict[str, Any] = {"available": False}
    if experiment.dataset_id is None or experiment.dataset_version_id is None:
        out["note"] = "dataset reference was deleted (SET NULL) — historical linkage unavailable"
        return out
    dv = db.get(DatasetVersion, experiment.dataset_version_id)
    if dv is None:
        out["note"] = "dataset version record missing"
        return out
    out.update({
        "available": True,
        "dataset_id": str(experiment.dataset_id),
        "dataset_version_id": str(dv.id),
        "version_number": dv.version_number,
        "sha256_checksum": dv.sha256_checksum,
        "row_count": dv.row_count,
        "column_count": dv.column_count,
        "source": dv.source,
        "derived_from_version_id": str(dv.derived_from_version_id) if dv.derived_from_version_id else None,
        "transformation_log": dv.transformation_log,
    })
    # Verify the stored file still matches the recorded checksum.
    try:
        if storage.exists(dv.file_path):
            actual = storage.compute_sha256(dv.file_path)
            out["file_checksum_verified"] = actual == dv.sha256_checksum
            out["file_checksum_actual"] = actual
        else:
            out["file_checksum_verified"] = None
            out["note"] = "dataset file missing from storage"
    except Exception as exc:
        out["file_checksum_verified"] = None
        out["note"] = f"checksum verification failed: {exc}"
    return out


def _artifact_evidence(experiment: Experiment, storage: LocalObjectStorage) -> dict[str, Any]:
    out: dict[str, Any] = {"available": False}
    if not experiment.artifact_uri:
        out["note"] = "no artifact recorded"
        return out
    key = experiment.artifact_uri.removeprefix("local://")
    out.update({"artifact_uri": experiment.artifact_uri, "storage_key": key})
    try:
        if storage.exists(key):
            out["exists"] = True
            out["sha256"] = storage.compute_sha256(key)
            out["size_bytes"] = storage.get_file_size(key)
        else:
            out["exists"] = False
            out["note"] = "artifact file missing"
    except Exception as exc:
        out["exists"] = None
        out["note"] = str(exc)[:200]
    return out


def _manifest_evidence(experiment: Experiment, storage: LocalObjectStorage) -> dict[str, Any]:
    key = f"experiments/{experiment.id}/manifest.json"
    try:
        if storage.exists(key):
            with storage.open(key) as f:
                return {"available": True, "manifest": json.load(f)}
    except Exception:
        pass
    return {"available": False, "note": "manifest not found"}


def build_payload(db: Session, experiment: Experiment) -> dict[str, Any]:
    storage = LocalObjectStorage()
    results = list(db.scalars(select(ExperimentModelResult).where(ExperimentModelResult.experiment_id == experiment.id)))
    metrics = experiment.metrics or {}
    return {
        "receipt_version": 1,
        "experiment": {
            "id": str(experiment.id), "name": experiment.name, "status": experiment.status,
            "task_type": experiment.task_type, "target_column": experiment.target_column,
            "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
        },
        "dataset": _dataset_evidence(db, experiment, storage),
        "configuration": {
            "model_names": list(experiment.model_names or []),
            "random_seed": experiment.random_seed,
            "splits": {
                "train": experiment.train_fraction,
                "validation": experiment.validation_fraction,
                "test": experiment.test_fraction,
            },
            "preprocessing_config": experiment.preprocessing_config,
            "tuning_config": experiment.tuning_config,
        },
        "training": {
            "best_model_name": metrics.get("best_model_name"),
            "selection_criterion": "validation metrics only (test metrics never used for selection)",
            "training_duration_ms_total": metrics.get("training_duration_ms_total"),
        },
        "model_results": [{
            "model_name": r.model_name, "status": r.status, "is_selected": r.is_selected,
            "validation_metrics": r.validation_metrics, "test_metrics": r.test_metrics,
            "cross_validation_metrics": r.cross_validation_metrics,
            "training_duration_ms": r.training_duration_ms, "best_params": r.best_params,
            "error": r.error,
        } for r in results],
        "artifact": _artifact_evidence(experiment, storage),
        "manifest": _manifest_evidence(experiment, storage),
        "explainability": {
            "available": bool(experiment.artifact_uri and experiment.status == "completed"),
            "methods": ["shap_treeexplainer (tree models)", "permutation_importance", "leave_one_feature_out"],
            "computed_on_demand": True,
            "endpoints": [
                f"/projects/{experiment.project_id}/experiments/{experiment.id}/explain/global",
                f"/projects/{experiment.project_id}/experiments/{experiment.id}/explain/local",
                f"/projects/{experiment.project_id}/experiments/{experiment.id}/explain/dependence/{{feature}}",
            ],
            "note": "Explanations are computed on demand via /explain endpoints; SHAP values are only produced for supported tree models. "
                    "Explanations describe model behavior, not causal relationships.",
        },
        "environment": {"packages": _env_versions(), "generated_at": datetime.now(timezone.utc).isoformat()},
    }


def generate_receipt(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    if experiment.status != "completed":
        raise AppError(409, "experiment_not_completed", "Trust receipts require a completed experiment.")

    existing = db.scalar(select(TrustReceipt).where(TrustReceipt.experiment_id == experiment.id))
    if existing is not None:
        return _receipt_out(existing, already_existed=True)

    payload = build_payload(db, experiment)
    digest = _digest(payload)
    receipt = TrustReceipt(
        receipt_id=f"TR-{uuid.uuid4().hex[:16]}", project_id=project_id, experiment_id=experiment.id,
        payload=payload, digest=digest, signature=_sign(digest), verifications=[],
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return _receipt_out(receipt)


def _receipt_out(r: TrustReceipt, already_existed: bool = False) -> dict[str, Any]:
    return {
        "receipt_id": r.receipt_id, "experiment_id": r.experiment_id, "project_id": r.project_id,
        "digest": r.digest, "signature": r.signature, "payload": r.payload,
        "verifications": r.verifications, "created_at": r.created_at, "already_existed": already_existed,
    }


def _get_receipt(db: Session, project_id: uuid.UUID, receipt_id: str) -> TrustReceipt:
    r = db.scalar(select(TrustReceipt).where(TrustReceipt.receipt_id == receipt_id, TrustReceipt.project_id == project_id))
    if r is None:
        raise not_found("Trust receipt")
    return r


def get_receipt(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    get_owned_experiment(db, owner_id, project_id, experiment_id)
    r = db.scalar(select(TrustReceipt).where(TrustReceipt.experiment_id == experiment_id))
    if r is None:
        raise not_found("Trust receipt")
    return _receipt_out(r)


def list_receipts(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    rows = db.scalars(select(TrustReceipt).where(TrustReceipt.project_id == project_id)
                      .order_by(TrustReceipt.created_at.desc())).all()
    return {"receipts": [{
        "receipt_id": r.receipt_id, "experiment_id": r.experiment_id, "digest": r.digest,
        "created_at": r.created_at, "signed": r.signature is not None,
        "verification_count": len(r.verifications or []),
    } for r in rows]}


def verify_receipt(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, receipt_id: str) -> dict[str, Any]:
    """Re-verify payload integrity + live evidence checksums. Appends to verification history."""
    get_owned_project(db, owner_id, project_id)
    r = _get_receipt(db, project_id, receipt_id)
    checks: dict[str, Any] = {}

    # 1. Payload tamper check: recompute digest over stored payload.
    checks["payload_digest_match"] = _digest(r.payload) == r.digest

    # 2. Signature check (only if signed).
    if r.signature:
        expected = hmac.new(SIGNING_KEY.encode(), r.digest.encode(), hashlib.sha256).hexdigest() if SIGNING_KEY else None
        checks["signature_valid"] = expected is not None and hmac.compare_digest(expected, r.signature["value"])
        if not SIGNING_KEY:
            checks["signature_valid"] = False
            checks["signature_note"] = "signing key no longer configured — cannot verify"
    else:
        checks["signature_valid"] = None
        checks["signature_note"] = "receipt is not signed (no TRUST_RECEIPT_SIGNING_KEY at generation)"

    # 3. Live evidence checksums.
    storage = LocalObjectStorage()
    exp = db.get(Experiment, r.experiment_id)
    checks["experiment_exists"] = exp is not None
    if exp is not None:
        # Dataset file checksum vs recorded payload evidence.
        ds = r.payload.get("dataset") or {}
        if ds.get("available") and ds.get("dataset_version_id"):
            dv = db.get(DatasetVersion, uuid.UUID(ds["dataset_version_id"]))
            if dv is not None:
                try:
                    actual = storage.compute_sha256(dv.file_path) if storage.exists(dv.file_path) else None
                    checks["dataset_checksum_match"] = actual == ds.get("sha256_checksum") if actual else False
                except Exception:
                    checks["dataset_checksum_match"] = False
            else:
                checks["dataset_checksum_match"] = False
        art = r.payload.get("artifact") or {}
        if art.get("exists"):
            try:
                key = art.get("storage_key")
                checks["artifact_checksum_match"] = (
                    storage.exists(key) and storage.compute_sha256(key) == art.get("sha256")
                )
            except Exception:
                checks["artifact_checksum_match"] = False
        checks["experiment_status"] = exp.status

    ok = all(v for k, v in checks.items() if isinstance(v, bool)) if checks else False
    verification = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok and checks.get("payload_digest_match", False),
        "checks": checks,
        "note": "Integrity verification confirms stored evidence consistency — it does not certify scientific validity.",
    }
    r.verifications = list(r.verifications or []) + [verification]
    db.commit()
    return {"receipt_id": r.receipt_id, "verification": verification, "verifications": r.verifications}


def reproducibility(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, receipt_id: str) -> dict[str, Any]:
    """Assess whether the experiment can be reconstructed from stored evidence."""
    get_owned_project(db, owner_id, project_id)
    r = _get_receipt(db, project_id, receipt_id)
    payload = r.payload
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: str):
        checks.append({"check": name, "status": "pass" if ok else ("fail" if ok is False else "unknown"), "detail": detail})

    ds = payload.get("dataset") or {}
    add("dataset_version_exists", ds.get("available"), "source dataset version record present" if ds.get("available") else ds.get("note", "unavailable"))
    add("dataset_checksum_recorded", bool(ds.get("sha256_checksum")), ds.get("sha256_checksum", "not recorded")[:16] + "…" if ds.get("sha256_checksum") else "missing")
    add("dataset_file_verified", ds.get("file_checksum_verified"),
        "file checksum matches record" if ds.get("file_checksum_verified") else (ds.get("note") or "unverified"))

    cfg = payload.get("configuration") or {}
    add("training_config", bool(cfg.get("splits") and cfg.get("model_names")),
        f"seed={cfg.get('random_seed')}, splits={cfg.get('splplits') or cfg.get('splits')}")
    if cfg.get("preprocessing_config") is not None:
        add("preprocessing_config", True, "stored")
    else:
        checks.append({"check": "preprocessing_config", "status": "unknown", "detail": "not recorded — training defaults were used"})

    art = payload.get("artifact") or {}
    add("model_artifact_exists", art.get("exists"), "artifact present" if art.get("exists") else art.get("note", "missing"))
    add("model_artifact_checksum", bool(art.get("sha256")), (art.get("sha256") or "")[:16] + "…" if art.get("sha256") else "missing")

    env = (payload.get("environment") or {}).get("packages") or {}
    add("environment_recorded", any(env.values()), f"{sum(1 for v in env.values() if v)}/{len(env)} package versions recorded")

    statuses = [c["status"] for c in checks]
    if all(s == "pass" for s in statuses):
        overall = "reproducible"
    elif any(s == "fail" for s in statuses):
        overall = "not_reproducible"
    elif any(s == "unknown" for s in statuses):
        overall = "partially_reproducible"
    else:
        overall = "partially_reproducible"
    # Verification-failed override: live checksum check already failed.
    last_verify = (r.verifications or [{}])[-1]
    if last_verify.get("checks", {}).get("payload_digest_match") is False:
        overall = "verification_failed"

    return {
        "receipt_id": r.receipt_id, "experiment_id": r.experiment_id,
        "status": overall, "checks": checks,
        "note": "Reproducibility means stored evidence is complete enough to re-run training deterministically — it does not guarantee bit-identical models across environments.",
    }
