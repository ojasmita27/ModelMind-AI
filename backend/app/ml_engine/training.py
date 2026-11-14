from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.model_selection import cross_val_predict

from app.ml_engine.metrics import (
    classification_metrics,
    classification_report_payload,
    confusion_matrix_payload,
    regression_metrics,
)
import time

from app.ml_engine.models import get_model_candidates, get_param_grid
from app.ml_engine.preprocessing import SplitConfig, build_preprocessor, split_frame, validate_task_target


@dataclass
class ExperimentArtifacts:
    best_model_name: str
    best_metrics: dict[str, float]
    cross_validation_metrics: dict[str, float]
    validation_metrics: dict[str, float]
    test_metrics: dict[str, float]
    trained_model: Any


def _proba_predictions(estimator_has_proba: bool, proba: np.ndarray, classes: np.ndarray) -> np.ndarray:
    """Derive class predictions from predict_proba output without a second CV pass."""
    return classes[np.argmax(proba, axis=1)]


def run_experiment(frame: pd.DataFrame, target: str, task_type: str, model_names: list[str], split: SplitConfig, preprocessing_config: dict[str, Any] | None = None, tuning_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Dataset is empty. Upload a non-empty CSV before training.")
    if target not in frame.columns:
        raise ValueError(f"Target column '{target}' not found in dataset.")
    if frame[target].isna().all():
        raise ValueError(
            f"Target column '{target}' contains only missing target labels. Remove rows with missing target values before training."
        )
    validate_task_target(frame, target, task_type)

    train_x, val_x, test_x, train_y, val_y, test_y = split_frame(frame, target, split, task_type)
    if task_type == "classification":
        classes = sorted(pd.unique(train_y.dropna()))
        if len(classes) < 2:
            raise ValueError(
                f"Target column '{target}' has fewer than 2 classes after removing missing labels. Classification requires at least 2 classes."
            )
        is_binary_task = len(classes) == 2
    else:
        is_binary_task = False
    # The preprocessor is fitted inside each Pipeline on the TRAIN split only;
    # validation/test never influence imputation, encoding or scaling.
    preprocessor = build_preprocessor(train_x, preprocessing_config)

    tuning = tuning_config or {}
    tuning_enabled = bool(tuning.get("enabled"))
    n_iter = int(tuning.get("n_iter", 5))
    search_cv = int(tuning.get("cv", 3))

    candidates = get_model_candidates(task_type, model_names)

    best_name = model_names[0]
    best_scores: dict[str, float] | None = None
    best_validation: dict[str, float] | None = None
    best_model = None
    best_test = None
    model_results: list[dict[str, Any]] = []

    for model_name, estimator in candidates:
        result_entry: dict[str, Any] = {
            "model_name": model_name,
            "is_selected": False,
            "status": "failed",
            "error": None,
            "cross_validation_metrics": {},
            "validation_metrics": {},
            "test_metrics": {},
            "confusion_matrix": None,
            "classification_report": None,
            "best_params": None,
            "training_duration_ms": None,
        }
        started = time.perf_counter()
        try:
            pipeline = __build_pipeline(preprocessor, estimator)
            grid = get_param_grid(task_type, model_name)
            if tuning_enabled and grid:
                from sklearn.model_selection import RandomizedSearchCV

                scoring = "f1_macro" if task_type == "classification" else "neg_root_mean_squared_error"
                search = RandomizedSearchCV(
                    pipeline,
                    param_distributions={f"model__{k}": v for k, v in grid.items()},
                    n_iter=n_iter,
                    cv=search_cv,
                    scoring=scoring,
                    random_state=split.random_seed,
                    error_score="raise",
                )
                search.fit(train_x, train_y)
                pipeline = search.best_estimator_
                result_entry["best_params"] = {
                    k.removeprefix("model__"): _json_safe(v) for k, v in search.best_params_.items()
                }
            has_proba = hasattr(pipeline, "predict_proba")

            if task_type == "classification":
                if has_proba:
                    # One CV pass: probabilities -> derive labels via argmax.
                    cv_proba = cross_val_predict(pipeline, train_x, train_y, cv=3, method="predict_proba")
                    cv_classes = getattr(pipeline, "classes_", np.array(sorted(pd.unique(train_y.dropna()))))
                    cv_pred = _proba_predictions(True, cv_proba, cv_classes)
                else:
                    cv_pred = cross_val_predict(pipeline, train_x, train_y, cv=3, method="predict")
                    cv_proba = None
                cv_metrics = classification_metrics(train_y, cv_pred, cv_proba, is_binary_task)

                pipeline.fit(train_x, train_y)
                val_pred = pipeline.predict(val_x)
                val_proba = pipeline.predict_proba(val_x) if has_proba else None
                validation_metrics = classification_metrics(val_y, val_pred, val_proba, is_binary_task)
                test_pred = pipeline.predict(test_x)
                test_proba = pipeline.predict_proba(test_x) if has_proba else None
                test_metrics = classification_metrics(test_y, test_pred, test_proba, is_binary_task)

                if is_binary_task and val_proba is not None:
                    try:
                        from sklearn.metrics import brier_score_loss

                        classes = list(getattr(pipeline, "classes_", []))
                        if 1 in classes or True in classes:
                            pos_idx = classes.index(1) if 1 in classes else classes.index(True)
                            validation_metrics["brier_score"] = round(float(brier_score_loss(val_y, val_proba[:, pos_idx])), 6)
                    except Exception:
                        pass

                # Evaluation artifacts are computed on the VALIDATION split
                # (the selection split); test metrics never influence selection.
                try:
                    result_entry["confusion_matrix"] = confusion_matrix_payload(val_y, val_pred)
                    result_entry["classification_report"] = classification_report_payload(val_y, val_pred)
                except Exception:
                    pass  # diagnostics are best-effort; metrics remain authoritative

                score = float(validation_metrics.get("f1_macro", validation_metrics.get("accuracy", 0.0)))
            else:
                cv_pred = cross_val_predict(pipeline, train_x, train_y, cv=3, method="predict")
                cv_metrics = regression_metrics(train_y, cv_pred)
                pipeline.fit(train_x, train_y)
                val_pred = pipeline.predict(val_x)
                validation_metrics = regression_metrics(val_y, val_pred)
                test_pred = pipeline.predict(test_x)
                test_metrics = regression_metrics(test_y, test_pred)
                score = float(-(validation_metrics.get("rmse", 0.0)))

                residuals = pd.to_numeric(val_y, errors="coerce") - pd.to_numeric(val_pred, errors="coerce")
                residuals = residuals.dropna()
                if not residuals.empty:
                    validation_metrics["residual_mean"] = round(float(residuals.mean()), 6)
                    validation_metrics["residual_std"] = round(float(residuals.std(ddof=0)), 6)
                    validation_metrics["residual_min"] = round(float(residuals.min()), 6)
                    validation_metrics["residual_max"] = round(float(residuals.max()), 6)

            result_entry["training_duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            result_entry.update(
                status="completed",
                cross_validation_metrics=cv_metrics,
                validation_metrics=validation_metrics,
                test_metrics=test_metrics,
            )

            if best_scores is None or score > float(best_scores.get("selection_score", float("-inf"))):
                best_name = model_name
                best_scores = {"selection_score": score, **cv_metrics}
                best_validation = validation_metrics
                best_model = pipeline
                best_test = test_metrics
        except Exception as exc:
            # A single candidate failing must not sink the whole experiment;
            # the failure is persisted as a meaningful per-model error.
            result_entry["error"] = str(exc)
            result_entry["status"] = "failed"

        model_results.append(result_entry)

    if best_model is None or best_validation is None:
        raise ValueError("No candidate models could be trained from the configuration")

    for entry in model_results:
        if entry["model_name"] == best_name and entry["status"] == "completed":
            entry["is_selected"] = True
            break

    return {
        "best_model_name": best_name,
        "best_metrics": best_validation,
        "cross_validation_metrics": best_scores,
        "validation_metrics": best_validation,
        "test_metrics": best_test,
        "trained_model": best_model,
        "model_results": model_results,
    }


def _json_safe(value):
    import numpy as np

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def __build_pipeline(preprocessor, estimator):
    from sklearn.pipeline import Pipeline

    model = clone(estimator)
    return Pipeline([("preprocessor", preprocessor), ("model", model)])
