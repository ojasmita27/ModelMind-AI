from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def classification_metrics(y_true: Any, y_pred: Any, y_proba: Any | None = None, is_binary_task: bool = False) -> dict[str, float]:
    metrics: dict[str, float] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision_macro": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }
    # ROC-AUC is only valid for binary classification tasks and only when both
    # classes are actually present in the split being scored.
    if y_proba is not None and is_binary_task:
        unique_classes = np.unique(np.asarray(y_true))
        if len(unique_classes) == 2:
            try:
                metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba[:, 1] if y_proba.ndim > 1 else y_proba))
            except ValueError:
                pass
    return metrics


def confusion_matrix_payload(y_true: Any, y_pred: Any) -> dict[str, Any]:
    """Confusion matrix as JSON-safe data: labels + matrix rows."""
    labels = sorted(set(np.asarray(y_true).tolist()) | set(np.asarray(y_pred).tolist()))
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    return {"labels": [str(x) for x in labels], "matrix": matrix.tolist()}


def classification_report_payload(y_true: Any, y_pred: Any) -> dict[str, Any]:
    """Per-class precision/recall/F1/support as JSON-safe data."""
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
    return {k: v for k, v in report.items() if k != "accuracy" or True}


def regression_metrics(y_true: Any, y_pred: Any) -> dict[str, float]:
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "mse": mse,
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_true, y_pred)),
    }
