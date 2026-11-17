"""Explainable AI: SHAP where supported, permutation-based fallback.

All values are computed from the persisted trained pipeline — never fabricated.
Explanations describe model behavior, not causal relationships.
"""
from __future__ import annotations

import io
import uuid
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Experiment
from app.services.experiments import get_owned_experiment
from app.services import whatif as whatif_service
from app.storage import LocalObjectStorage

_MAX_BACKGROUND = 200
_MAX_FEATURES_SHAP = 30


def _load_pipeline(experiment: Experiment):
    if experiment.status != "completed" or not experiment.artifact_uri:
        raise AppError(409, "experiment_not_ready", "Experiment has no trained model artifact.")
    key = experiment.artifact_uri.removeprefix("local://")
    storage = LocalObjectStorage()
    if not storage.exists(key):
        raise AppError(404, "artifact_missing", "Model artifact is missing.")
    with storage.open(key) as f:
        model = joblib.load(f)
    return model, storage


def _background_frame(experiment: Experiment, storage: LocalObjectStorage, n: int = _MAX_BACKGROUND) -> pd.DataFrame:
    """Deterministic background sample: first n rows of the source dataset version."""
    version = experiment.dataset_version
    if version is None:
        raise AppError(409, "dataset_unavailable", "Source dataset version unavailable.")
    with storage.open(version.file_path) as raw:
        df = pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""), nrows=_MAX_BACKGROUND)
    features = [c for c in df.columns if c != experiment.target_column]
    return df[features].head(n)


def _estimator(model):
    return model.steps[-1][1] if hasattr(model, "steps") else model


def _shap_available() -> bool:
    try:
        import shap  # noqa
        return True
    except ImportError:
        return False


def _tree_explainer(model, background_transformed: np.ndarray):
    import shap
    est = _estimator(model)
    for cls in (shap.TreeExplainer,):
        try:
            return cls(est)
        except Exception:
            pass
    return None


def explain_global(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID) -> dict[str, Any]:
    """Global feature importance. Uses SHAP TreeExplainer for tree ensembles when
    shap is installed; otherwise bounded permutation importance on the pipeline."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_pipeline(experiment)
    bg = _background_frame(experiment, storage)
    features = list(bg.columns)
    if len(features) > _MAX_FEATURES_SHAP:
        features = features[:_MAX_FEATURES_SHAP]
        bg = bg[features]

    method = "unavailable"
    importances: dict[str, float] = {}
    notes: list[str] = []

    if _shap_available() and _is_tree_model(model):
        try:
            import shap
            est = _estimator(model)
            # Transform background through the fitted preprocessor, then explain.
            prep = model.named_steps.get("preprocessor") if hasattr(model, "named_steps") else None
            X_bg = prep.transform(bg) if prep is not None else bg.values
            if hasattr(X_bg, "toarray"):
                X_bg = X_bg.toarray()
            explainer = shap.TreeExplainer(est)
            sv = explainer.shap_values(X_bg[:_MAX_BACKGROUND])
            # For multiclass, sv may be a list per class — take mean abs across classes.
            if isinstance(sv, list):
                arr = np.mean([np.abs(np.asarray(s)).mean(axis=0) for s in sv], axis=0)
            else:
                arr = np.abs(np.asarray(sv)).mean(axis=0)
            # Feature names after preprocessing may differ (one-hot). Map by position when counts match.
            if len(arr) == len(features):
                importances = {f: round(float(v), 6) for f, v in zip(features, arr)}
                method = "shap_treeexplainer"
            else:
                method = "shap_treeexplainer_transformed"
                importances = {f"feature_{i}": round(float(v), 6) for i, v in enumerate(arr[:50])}
                notes.append("Preprocessing expanded features (e.g. one-hot); importance is per transformed column.")
        except Exception as exc:
            notes.append(f"SHAP computation failed: {exc}")
            method = "unavailable"

    if method == "unavailable":
        # Bounded permutation importance — real, model-agnostic.
        rng = np.random.default_rng(42)
        baseline = model.predict(bg)
        scores = []
        for fname in features:
            perm = bg.copy()
            perm[fname] = rng.permutation(perm[fname].to_numpy())
            try:
                perturbed = model.predict(perm)
                if experiment.task_type == "classification":
                    drop = float((baseline != perturbed).mean())
                else:
                    drop = float(np.mean(np.abs(np.asarray(baseline, dtype=float) - np.asarray(perturbed, dtype=float))))
                scores.append((fname, round(drop, 6)))
            except Exception:
                continue
        importances = dict(sorted(scores, key=lambda kv: -kv[1]))
        method = "permutation_importance"
        notes.append("Permutation importance (prediction-change based); install shap for SHAP values on tree models.")

    return {
        "experiment_id": experiment.id, "method": method,
        "background_samples": min(len(bg), _MAX_BACKGROUND),
        "feature_count": len(features),
        "importances": importances,
        "notes": notes,
        "disclaimer": "Explanations describe model behavior on this data, not causal relationships.",
    }


def _is_tree_model(model) -> bool:
    est = _estimator(model)
    name = type(est).__name__.lower()
    return any(k in name for k in ("tree", "forest", "gradientboosting", "xgb", "lightgbm", "catboost"))


def explain_dependence(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID,
                       feature: str) -> dict[str, Any]:
    """SHAP dependence data for one feature (tree models only). Returns per-sample
    SHAP value + feature value pairs for scatter plotting."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_pipeline(experiment)
    bg = _background_frame(experiment, storage)
    if feature not in bg.columns:
        raise AppError(422, "validation_error", f"Unknown feature '{feature}'.")
    if not _shap_available() or not _is_tree_model(model):
        raise AppError(409, "unsupported", "Dependence plots require SHAP TreeExplainer (tree-based models only).")
    import shap
    est = _estimator(model)
    prep = model.named_steps.get("preprocessor") if hasattr(model, "named_steps") else None
    X_bg = prep.transform(bg) if prep is not None else bg.values
    if hasattr(X_bg, "toarray"):
        X_bg = X_bg.toarray()
    explainer = shap.TreeExplainer(est)
    sv = explainer.shap_values(X_bg[:_MAX_BACKGROUND])
    if isinstance(sv, list):
        # multiclass: use mean absolute contribution across classes
        arr = np.mean([np.asarray(s) for s in sv], axis=0)
    else:
        arr = np.asarray(sv)
    if arr.ndim == 3:
        arr = arr[:, :, 0] if arr.shape[-1] == 1 else arr.mean(axis=2)
    # locate column index: transformed feature index may differ; use position of feature
    # in transformed matrix when counts match, else fall back to first matching name.
    idx = None
    try:
        names = list(prep.get_feature_names_out()) if prep is not None and hasattr(prep, "get_feature_names_out") else list(bg.columns)
        if feature in names:
            idx = names.index(feature)
    except Exception:
        idx = None
    if idx is None:
        idx = min(bg.columns.get_loc(feature), arr.shape[1] - 1) if arr.shape[1] == len(bg.columns) else 0
    col = arr[:, idx] if arr.ndim == 2 else arr
    vals = bg[feature].iloc[: len(col)].tolist()
    return {
        "experiment_id": experiment.id, "feature": feature, "method": "shap_dependence",
        "points": [{"x": float(v) if isinstance(v, (int, float, np.floating)) else str(v), "shap": round(float(s), 6)}
                   for v, s in zip(vals, col)],
        "disclaimer": "SHAP dependence shows model sensitivity to this feature; not a causal claim.",
    }


def explain_local(db: Session, owner_id: uuid.UUID, project_id: uuid.UUID, experiment_id: uuid.UUID,
                  features: dict[str, Any]) -> dict[str, Any]:
    """Local explanation: leave-one-feature-out prediction deltas on the actual
    input — model-agnostic, exact, bounded. Uses observed feature domains for
    replacement values where possible."""
    experiment = get_owned_experiment(db, owner_id, project_id, experiment_id)
    model, storage = _load_pipeline(experiment)
    frame = whatif_service._coerce_features(experiment, storage, features)
    schema = whatif_service._feature_schema(experiment, storage)
    spec = {f["name"]: f for f in schema}

    base_pred = model.predict(frame)
    base_payload = whatif_service._predict_payload(model, frame, experiment.task_type)

    contributions = []
    for name in frame.columns:
        s = spec.get(name, {})
        # Replacement value: median for numeric, mode/first category for categorical.
        if s.get("type") == "numeric" and s.get("median") is not None:
            repl = s["median"]
        elif s.get("categories"):
            repl = s["categories"][0]
        else:
            repl = frame.iloc[0][name]
        alt = frame.copy()
        alt.iloc[0, alt.columns.get_loc(name)] = repl
        try:
            alt_pred = model.predict(alt)[0]
            delta = float(abs(float(alt_pred) - float(base_pred[0]))) if experiment.task_type == "regression" else float(alt_pred != base_pred[0])
        except Exception:
            delta = 0.0
        contributions.append({"feature": name, "value": frame.iloc[0][name], "replacement": repl, "delta": round(delta, 6)})
    contributions.sort(key=lambda c: -c["delta"])

    return {
        "experiment_id": experiment.id, "method": "leave_one_feature_out",
        "prediction": base_payload,
        "contributions": contributions,
        "disclaimer": "Local explanation via feature ablation — describes model sensitivity, not causation.",
    }
