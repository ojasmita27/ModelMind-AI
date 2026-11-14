"""Regression tests for Phase 1 correctness bug fixes."""
import pytest
import pandas as pd
import numpy as np
from sklearn.metrics import roc_auc_score

from app.ml_engine.preprocessing import SplitConfig, split_frame
from app.ml_engine.metrics import classification_metrics
from app.ml_engine.training import run_experiment


def test_single_class_error_message_correct():
    """Test that single-class target error message is correctly worded."""
    frame = pd.DataFrame({
        "feature": [1, 2, 3, 4],
        "target": ["A", "A", "A", "A"]  # Single class
    })
    
    with pytest.raises(ValueError) as exc_info:
        split_frame(frame, "target", SplitConfig(0.7, 0.15, 0.15), "classification")
    
    error_msg = str(exc_info.value)
    # Should correctly state the problem: "has fewer than 2 classes"
    assert "has fewer than 2 classes" in error_msg, f"Error message should say 'has fewer than 2 classes', got: {error_msg}"


def test_roc_auc_binary_task_parameter():
    """Test that ROC-AUC uses is_binary_task parameter, not split-specific class count."""
    # Binary classification task
    y_true_binary = np.array([0, 1, 0, 1, 0, 1])
    y_pred_binary = np.array([0, 1, 0, 1, 0, 1])
    y_proba_binary = np.array([[0.9, 0.1], [0.2, 0.8], [0.8, 0.2], [0.3, 0.7], [0.9, 0.1], [0.2, 0.8]])
    
    # With is_binary_task=True, should include ROC-AUC
    metrics_binary = classification_metrics(y_true_binary, y_pred_binary, y_proba_binary, is_binary_task=True)
    assert "roc_auc" in metrics_binary
    assert metrics_binary["roc_auc"] == pytest.approx(1.0, abs=0.01)
    
    # With is_binary_task=False, should NOT include ROC-AUC even if split has 2 classes
    metrics_no_binary = classification_metrics(y_true_binary, y_pred_binary, y_proba_binary, is_binary_task=False)
    assert "roc_auc" not in metrics_no_binary


def test_roc_auc_multiclass_not_computed():
    """Test that ROC-AUC is not computed for multiclass tasks even with is_binary_task=False."""
    # Multiclass data (3 classes)
    y_true_multi = np.array([0, 1, 2, 0, 1, 2])
    y_pred_multi = np.array([0, 1, 2, 0, 1, 2])
    # Fake probabilities for 3 classes
    y_proba_multi = np.array([
        [0.9, 0.05, 0.05],
        [0.1, 0.8, 0.1],
        [0.05, 0.1, 0.85],
        [0.85, 0.1, 0.05],
        [0.1, 0.85, 0.05],
        [0.05, 0.1, 0.85]
    ])
    
    # With is_binary_task=False, should not include ROC-AUC
    metrics = classification_metrics(y_true_multi, y_pred_multi, y_proba_multi, is_binary_task=False)
    assert "roc_auc" not in metrics


def test_validation_score_label_not_misleading():
    """Test that model selection score is labeled 'selection_score', not 'score'."""
    frame = pd.DataFrame({
        "feature1": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "feature2": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "target": [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    })
    
    result = run_experiment(
        frame,
        "target",
        "classification",
        ["Logistic Regression"],
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    )
    
    # cross_validation_metrics should have 'selection_score', not 'score'
    cv_metrics = result["cross_validation_metrics"]
    assert "selection_score" in cv_metrics, "cross_validation_metrics should contain 'selection_score'"
    assert "score" not in cv_metrics, "cross_validation_metrics should not contain misleading 'score' key"


def test_binary_classification_roc_auc_in_all_splits():
    """Test that ROC-AUC is computed for all splits in binary classification."""
    frame = pd.DataFrame({
        "feature1": np.random.randn(100),
        "feature2": np.random.randn(100),
        "target": np.random.choice([0, 1], 100)
    })
    
    result = run_experiment(
        frame,
        "target",
        "classification",
        ["Logistic Regression"],
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    )
    
    # ROC-AUC should be in all metric dictionaries for binary classification
    assert "roc_auc" in result["cross_validation_metrics"], "ROC-AUC should be in cross_validation_metrics"
    assert "roc_auc" in result["validation_metrics"], "ROC-AUC should be in validation_metrics"
    assert "roc_auc" in result["test_metrics"], "ROC-AUC should be in test_metrics"


def test_multiclass_classification_no_roc_auc():
    """Test that ROC-AUC is not computed for multiclass classification."""
    frame = pd.DataFrame({
        "feature1": np.random.randn(100),
        "feature2": np.random.randn(100),
        "target": np.random.choice([0, 1, 2], 100)
    })
    
    result = run_experiment(
        frame,
        "target",
        "classification",
        ["Logistic Regression"],
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    )
    
    # ROC-AUC should NOT be in any metric dictionaries for multiclass
    assert "roc_auc" not in result["cross_validation_metrics"], "ROC-AUC should not be in cross_validation_metrics for multiclass"
    assert "roc_auc" not in result["validation_metrics"], "ROC-AUC should not be in validation_metrics for multiclass"
    assert "roc_auc" not in result["test_metrics"], "ROC-AUC should not be in test_metrics for multiclass"


def test_regression_no_roc_auc():
    """Test that ROC-AUC is never computed for regression."""
    frame = pd.DataFrame({
        "feature1": np.random.randn(100),
        "feature2": np.random.randn(100),
        "target": np.random.randn(100)
    })
    
    result = run_experiment(
        frame,
        "target",
        "regression",
        ["Linear Regression"],
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    )
    
    # Regression metrics should not include ROC-AUC
    assert "roc_auc" not in result["cross_validation_metrics"]
    assert "roc_auc" not in result["validation_metrics"]
    assert "roc_auc" not in result["test_metrics"]
