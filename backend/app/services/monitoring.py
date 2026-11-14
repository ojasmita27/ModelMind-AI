"""Model monitoring: drift detection, health assessment, ground-truth performance."""
from __future__ import annotations

import io
import math
import os
import uuid
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, not_found
from app.db.models import Deployment, Experiment, LabelRecord, ModelVersion, MonitoringRun, PredictionRecord
from app.services.projects import get_owned_project
from app.storage import LocalObjectStorage

MIN_SAMPLES = int(os.getenv("MONITOR_MIN_SAMPLES", "30"))
DEFAULT_THRESHOLDS = {
    "psi_warning": 0.1, "psi_critical": 0.25,
    "ks_p_warning": 0.05, "chi2_p_warning": 0.05,
    "missing_rate_delta_warning": 0.1,
}


def _get_deployment(db: Session, project_id: uuid.UUID, deployment_id: uuid.UUID) -> Deployment:
    d = db.scalar(select(Deployment).where(Deployment.id == deployment_id, Deployment.project_id == project_id))
    if d is None:
        raise not_found("Deployment")
    return d


def _thresholds(d: Deployment) -> dict[str, float]:
    cfg = (d.config or {}).get("monitoring") or {}
    t = dict(DEFAULT_THRESHOLDS)
    t.update({k: float(v) for k, v in cfg.items() if k in t and isinstance(v, (int, float))})
    return t


def get_config(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    return {"deployment_id": d.id, "thresholds": _thresholds(d), "min_samples": MIN_SAMPLES,
            "input_logging": os.getenv("PREDICTION_LOG_INPUTS", "true").lower() != "false"}


def set_config(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID, thresholds: dict[str, Any]) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    cfg = dict(d.config or {})
    mon = dict(cfg.get("monitoring") or {})
    for k, v in thresholds.items():
        if k in DEFAULT_THRESHOLDS:
            if not isinstance(v, (int, float)) or not (0 <= float(v) <= 10):
                raise AppError(422, "validation_error", f"threshold '{k}' must be a number in [0,10]")
            mon[k] = float(v)
    cfg["monitoring"] = mon
    d.config = cfg
    db.commit()
    return get_config(db, owner_id, project_id, deployment_id)


def _reference_frame(db: Session, d: Deployment) -> tuple[pd.DataFrame, list[str]]:
    """Load the exact source dataset version used by the registered model version."""
    v = db.get(ModelVersion, d.version_id)
    if v is None or v.dataset_version_id is None:
        raise AppError(409, "no_reference", "Registered version has no source dataset version — cannot compute drift.")
    from app.db.models import DatasetVersion
    dv = db.get(DatasetVersion, v.dataset_version_id)
    if dv is None:
        raise AppError(409, "no_reference", "Source dataset version was deleted — drift reference unavailable.")
    exp = db.get(Experiment, v.experiment_id)
    target = exp.target_column if exp else None
    with LocalObjectStorage().open(dv.file_path) as raw:
        df = pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
    features = [c for c in df.columns if c != target]
    return df[features], features


def _window_records(db: Session, d: Deployment, since_id: uuid.UUID | None) -> list[PredictionRecord]:
    q = select(PredictionRecord).where(
        PredictionRecord.deployment_id == d.id,
        PredictionRecord.status == "completed",
        PredictionRecord.input_data.isnot(None),
    ).order_by(PredictionRecord.created_at)
    if since_id is not None:
        prev = db.get(MonitoringRun, since_id)
        if prev and prev.window_end:
            q = q.where(PredictionRecord.created_at > prev.window_end)
    return list(db.scalars(q))


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index. Returns 0 when distributions identical."""
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < 2 or len(actual) < 2:
        return float("nan")
    breaks = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    if len(breaks) < 2:
        return 0.0
    exp_counts = np.histogram(expected, bins=breaks)[0] / len(expected)
    act_counts = np.histogram(actual, bins=breaks)[0] / len(actual)
    eps = 1e-4
    exp_counts = np.clip(exp_counts, eps, 1)
    act_counts = np.clip(act_counts, eps, 1)
    return float(np.sum((act_counts - exp_counts) * np.log(act_counts / exp_counts)))


def _feature_drift(ref: pd.Series, cur: pd.Series, name: str) -> dict[str, Any]:
    ref_num = pd.to_numeric(ref, errors="coerce")
    cur_num = pd.to_numeric(cur, errors="coerce")
    ref_numeric = ref_num.notna().mean() > 0.9 and len(ref_num.dropna()) > 1
    out: dict[str, Any] = {"feature": name, "type": "numeric" if ref_numeric else "categorical"}
    out["missing_rate_ref"] = round(float(ref.isna().mean()), 4)
    out["missing_rate_current"] = round(float(cur.isna().mean()), 4) if len(cur) else None
    out["missing_rate_delta"] = round(abs(out["missing_rate_current"] - out["missing_rate_ref"]), 4) if len(cur) else None
    if ref_numeric and len(cur_num.dropna()) >= 2:
        out["psi"] = round(psi(ref_num.dropna().to_numpy(), cur_num.dropna().to_numpy()), 4)
        try:
            out["ks_statistic"] = round(float(stats.ks_2samp(ref_num.dropna(), cur_num.dropna()).statistic), 4)
            out["ks_pvalue"] = float(stats.ks_2samp(ref_num.dropna(), cur_num.dropna()).pvalue)
        except Exception:
            out["ks_statistic"] = out["ks_pvalue"] = None
    else:
        cats = sorted(set(ref.dropna().astype(str)) | set(cur.dropna().astype(str)))[:50]
        if cats:
            ref_counts = ref.astype(str).value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy()
            cur_counts = cur.astype(str).value_counts(normalize=True).reindex(cats, fill_value=0).to_numpy() if len(cur) else np.zeros(len(cats))
            try:
                chi2, p, _, _ = stats.chi2_contingency(
                    np.array([ref_counts * max(len(ref), 1), cur_counts * max(len(cur), 1)]))
                out["chi2_pvalue"] = float(p)
            except Exception:
                out["chi2_pvalue"] = None
            out["psi"] = round(psi(ref_counts, cur_counts), 4) if len(cur) else None
            out["top_categories"] = cats[:10]
    return out


def _prediction_drift(records: list[PredictionRecord], task_type: str) -> dict[str, Any]:
    preds = []
    for r in records:
        p = (r.output_data or {}).get("prediction")
        if p is not None:
            preds.append(p)
    if not preds:
        return {"available": False, "reason": "no predictions in window"}
    vc = pd.Series(preds).astype(str).value_counts(normalize=True)
    return {"available": True, "distribution": {k: round(float(v), 4) for k, v in vc.items()}, "n": len(preds)}


def _health(summary: dict[str, Any], thresholds: dict[str, float], sample_count: int, ref_count: int) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if sample_count < MIN_SAMPLES:
        return "insufficient_data", [f"only {sample_count} samples (min {MIN_SAMPLES})"]
    if ref_count < MIN_SAMPLES:
        reasons.append(f"reference has {ref_count} rows (min {MIN_SAMPLES}); statistics may be unstable")
    worst = "healthy"
    for f in summary.get("features", []):
        psi_v = f.get("psi")
        if psi_v is not None and not (isinstance(psi_v, float) and math.isnan(psi_v)):
            if psi_v >= thresholds["psi_critical"]:
                worst = "critical"; reasons.append(f"{f['feature']}: PSI {psi_v} >= {thresholds['psi_critical']}")
            elif psi_v >= thresholds["psi_warning"] and worst == "healthy":
                worst = "warning"; reasons.append(f"{f['feature']}: PSI {psi_v} >= {thresholds['psi_warning']}")
        p = f.get("ks_pvalue") or f.get("chi2_pvalue")
        warn_p = thresholds["ks_p_warning"]
        if p is not None and p < warn_p and worst == "healthy":
            worst = "warning"; reasons.append(f"{f['feature']}: distribution test p={p:.4f} < {warn_p}")
        if f.get("missing_rate_delta") is not None and f["missing_rate_delta"] >= thresholds["missing_rate_delta_warning"]:
            if worst == "healthy": worst = "warning"
            reasons.append(f"{f['feature']}: missing-rate delta {f['missing_rate_delta']}")
    perf = summary.get("performance") or {}
    if perf.get("status") == "degraded":
        worst = "critical"; reasons.append("ground-truth performance degraded vs baseline")
    elif perf.get("status") == "warning":
        if worst == "healthy": worst = "warning"
        reasons.append("ground-truth performance below baseline")
    if not reasons:
        reasons.append("no drift or degradation signals exceeded thresholds")
    return worst, reasons


def run_monitoring(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID,
                   since_run_id: uuid.UUID | None = None) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    if d.status != "active":
        raise AppError(409, "deployment_inactive", f"Deployment is '{d.status}'.")
    thresholds = _thresholds(d)
    run = MonitoringRun(deployment_id=d.id, thresholds=thresholds, status="completed")
    try:
        ref_df, features = _reference_frame(db, d)
        records = _window_records(db, d, since_run_id)
        run.reference_sample_count = min(len(ref_df), 50000)
        if len(records) < MIN_SAMPLES:
            run.status = "insufficient_data"
            run.sample_count = len(records)
            run.health_status = "insufficient_data"
            run.summary = {"reason": f"{len(records)} prediction samples < minimum {MIN_SAMPLES}",
                           "note": "Prediction inputs may be disabled (PREDICTION_LOG_INPUTS) or volume is low."}
            db.add(run); db.commit(); db.refresh(run)
            return _run_out(run)

        current = pd.DataFrame([r.input_data for r in records])
        feature_results = []
        for fname in features:
            if fname in current.columns:
                feature_results.append(_feature_drift(ref_df[fname], current[fname], fname))
            else:
                feature_results.append({"feature": fname, "type": "missing_in_window", "psi": None})
        exp = db.get(Experiment, db.get(ModelVersion, d.version_id).experiment_id)
        task_type = exp.task_type if exp else "classification"
        pred_drift = _prediction_drift(records, task_type)
        perf = _performance_for_window(db, d, records)
        summary = {
            "features": feature_results,
            "prediction_distribution": pred_drift,
            "performance": perf,
            "window": {"n_predictions": len(records)},
            "methodology": "PSI (decile bins), KS test (numeric), chi-square (categorical), missing-rate delta. Drift indicates distribution shift, not confirmed model failure.",
        }
        health, reasons = _health(summary, thresholds, len(records), len(ref_df))
        run.sample_count = len(records)
        run.health_status = health
        run.summary = {**summary, "health_reasons": reasons}
        run.window_start = records[0].created_at if records else None
        run.window_end = records[-1].created_at if records else None
        db.add(run); db.commit(); db.refresh(run)
        return _run_out(run)
    except AppError:
        run.status = "failed"; run.error = "reference unavailable"; db.add(run); db.commit(); db.refresh(run)
        raise
    except Exception as exc:
        run.status = "failed"; run.error = str(exc)[:500]; db.add(run); db.commit(); db.refresh(run)
        raise AppError(500, "monitoring_failed", str(exc)) from exc


def _run_out(run: MonitoringRun) -> dict[str, Any]:
    return {
        "id": run.id, "deployment_id": run.deployment_id, "status": run.status,
        "health_status": run.health_status, "sample_count": run.sample_count,
        "reference_sample_count": run.reference_sample_count, "thresholds": run.thresholds,
        "summary": run.summary, "error": run.error,
        "window_start": run.window_start, "window_end": run.window_end, "created_at": run.created_at,
    }


def list_runs(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID, limit: int = 20) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    _get_deployment(db, project_id, deployment_id)
    rows = db.scalars(select(MonitoringRun).where(MonitoringRun.deployment_id == deployment_id)
                      .order_by(MonitoringRun.created_at.desc()).limit(min(limit, 100))).all()
    return {"deployment_id": deployment_id, "runs": [_run_out(r) for r in rows]}


def ingest_labels(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID,
                  labels: list[dict[str, Any]]) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    d = _get_deployment(db, project_id, deployment_id)
    if not labels or len(labels) > 1000:
        raise AppError(422, "validation_error", "Provide 1-1000 label records.")
    # Validate request_ids exist as completed predictions.
    rids = [str(l.get("request_id", "")) for l in labels]
    if any(not r for r in rids):
        raise AppError(422, "validation_error", "Each label needs request_id.")
    preds = {r.request_id: r for r in db.scalars(select(PredictionRecord).where(
        PredictionRecord.deployment_id == d.id, PredictionRecord.request_id.in_(rids),
        PredictionRecord.status == "completed")).all()}
    missing = [r for r in rids if r not in preds]
    if missing:
        raise AppError(422, "validation_error", f"Unknown request_id(s): {', '.join(missing[:5])}")
    added, skipped = 0, 0
    for l in labels:
        rid = str(l["request_id"])
        exists = db.scalar(select(LabelRecord.id).where(LabelRecord.deployment_id == d.id, LabelRecord.request_id == rid))
        if exists:
            skipped += 1
            continue
        db.add(LabelRecord(deployment_id=d.id, request_id=rid, label=l.get("label")))
        added += 1
    db.commit()
    return {"added": added, "skipped_duplicates": skipped}


def _performance_for_window(db: Session, d: Deployment, records: list[PredictionRecord]) -> dict[str, Any]:
    """Match labels to this window's predictions; compute real metrics."""
    rids = [r.request_id for r in records]
    if not rids:
        return {"status": "no_labels", "reason": "no labeled predictions"}
    labels = {l.request_id: l.label for l in db.scalars(select(LabelRecord).where(
        LabelRecord.deployment_id == d.id, LabelRecord.request_id.in_(rids))).all()}
    if not labels:
        return {"status": "no_labels", "matched": 0}
    pairs = [(records_map[rid].output_data.get("prediction"), labels[rid]) for rid in rids
             if rid in labels and rid in (records_map := {r.request_id: r for r in records})]
    if len(pairs) < 5:
        return {"status": "insufficient_labels", "matched": len(pairs)}
    y_pred = [p[0] for p in pairs]; y_true = [p[1] for p in pairs]
    v = db.get(ModelVersion, d.version_id)
    exp = db.get(Experiment, v.experiment_id) if v else None
    task = exp.task_type if exp else "classification"
    try:
        if task == "classification":
            from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder(); yt = le.fit_transform([str(y) for y in y_true]); yp = le.transform([str(y) for y in y_pred])
            out = {"status": "measured", "matched": len(pairs), "task_type": task,
                   "accuracy": round(float(accuracy_score(yt, yp)), 4),
                   "precision": round(float(precision_score(yt, yp, average="macro", zero_division=0)), 4),
                   "recall": round(float(recall_score(yt, yp, average="macro", zero_division=0)), 4),
                   "f1": round(float(f1_score(yt, yp, average="macro", zero_division=0)), 4)}
            if len(set(yt)) == 2:
                try:
                    proba_pairs = [(records_map[rid].output_data.get("probabilities") or {}) for rid in rids if rid in labels]
                    # AUC needs scores for positive class; use stored probabilities if present.
                    scores = []
                    ok = True
                    for rid in [r for r in rids if r in labels]:
                        probs = records_map[rid].output_data.get("probabilities") or {}
                        pos = [c for c in probs if str(c) == str(le.classes_[1])]
                        if not pos: ok = False; break
                        scores.append(probs[pos[0]])
                    if ok and len(scores) == len(pairs):
                        out["roc_auc"] = round(float(roc_auc_score(yt, scores)), 4)
                except Exception:
                    pass
            return out
        else:
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            yt = np.array([float(y) for y in y_true]); yp = np.array([float(p) for p in y_pred])
            return {"status": "measured", "matched": len(pairs), "task_type": task,
                    "mae": round(float(mean_absolute_error(yt, yp)), 4),
                    "rmse": round(float(math.sqrt(mean_squared_error(yt, yp))), 4),
                    "r2": round(float(r2_score(yt, yp)), 4)}
    except Exception as exc:
        return {"status": "error", "reason": str(exc)[:200], "matched": len(pairs)}


def performance_history(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, deployment_id: uuid.UUID) -> dict[str, Any]:
    get_owned_project(db, owner_id, project_id)
    _get_deployment(db, project_id, deployment_id)
    runs = db.scalars(select(MonitoringRun).where(MonitoringRun.deployment_id == deployment_id)
                      .order_by(MonitoringRun.created_at)).all()
    series = []
    for r in runs:
        perf = (r.summary or {}).get("performance") or {}
        if perf.get("status") == "measured":
            series.append({"run_id": r.id, "created_at": r.created_at, "matched": perf.get("matched"),
                           "metrics": {k: v for k, v in perf.items() if k not in ("status", "matched", "task_type")}})
    return {"deployment_id": deployment_id, "series": series}
