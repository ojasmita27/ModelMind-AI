"""Run Phase 1 regression tests directly without pytest."""
import sys
sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

import pandas as pd
import numpy as np
from app.ml_engine.preprocessing import SplitConfig, split_frame
from app.ml_engine.metrics import classification_metrics
from app.ml_engine.training import run_experiment

print("=" * 70)
print("PHASE 1 REGRESSION TESTS")
print("=" * 70)

# Test 1: Single-class error message
print("\n[Test 1] Single-class error message correctness")
try:
    frame = pd.DataFrame({
        "feature": [1, 2, 3, 4],
        "target": ["A", "A", "A", "A"]
    })
    split_frame(frame, "target", SplitConfig(0.7, 0.15, 0.15), "classification")
    print("✗ FAILED: Should have raised ValueError")
except ValueError as e:
    error_msg = str(e)
    if "has fewer than 2 classes" in error_msg:
        print(f"✓ PASSED: Error message correctly states 'has fewer than 2 classes'")
    else:
        print(f"✗ FAILED: Error message incorrect: {error_msg}")

# Test 2: ROC-AUC binary task parameter
print("\n[Test 2] ROC-AUC uses is_binary_task parameter")
y_true_binary = np.array([0, 1, 0, 1, 0, 1])
y_pred_binary = np.array([0, 1, 0, 1, 0, 1])
y_proba_binary = np.array([[0.9, 0.1], [0.2, 0.8], [0.8, 0.2], [0.3, 0.7], [0.9, 0.1], [0.2, 0.8]])

metrics_binary = classification_metrics(y_true_binary, y_pred_binary, y_proba_binary, is_binary_task=True)
metrics_no_binary = classification_metrics(y_true_binary, y_pred_binary, y_proba_binary, is_binary_task=False)

if "roc_auc" in metrics_binary and "roc_auc" not in metrics_no_binary:
    print(f"✓ PASSED: ROC-AUC only computed when is_binary_task=True")
else:
    print(f"✗ FAILED: ROC-AUC behavior incorrect")

# Test 3: Validation score label
print("\n[Test 3] Validation score labeled 'selection_score'")
try:
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
    cv_metrics = result["cross_validation_metrics"]
    if "selection_score" in cv_metrics and "score" not in cv_metrics:
        print(f"✓ PASSED: Uses 'selection_score' label")
    else:
        print(f"✗ FAILED: Incorrect label in cross_validation_metrics")
except Exception as e:
    print(f"✗ FAILED: {e}")

# Test 4: Binary classification ROC-AUC in all splits
print("\n[Test 4] ROC-AUC in all splits for binary classification")
try:
    np.random.seed(42)
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
    has_cv = "roc_auc" in result["cross_validation_metrics"]
    has_val = "roc_auc" in result["validation_metrics"]
    has_test = "roc_auc" in result["test_metrics"]
    if has_cv and has_val and has_test:
        print(f"✓ PASSED: ROC-AUC in all splits")
    else:
        print(f"✗ FAILED: ROC-AUC missing in some splits (cv:{has_cv}, val:{has_val}, test:{has_test})")
except Exception as e:
    print(f"✗ FAILED: {e}")

# Test 5: Multiclass no ROC-AUC
print("\n[Test 5] No ROC-AUC for multiclass classification")
try:
    np.random.seed(42)
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
    has_cv = "roc_auc" in result["cross_validation_metrics"]
    has_val = "roc_auc" in result["validation_metrics"]
    has_test = "roc_auc" in result["test_metrics"]
    if not has_cv and not has_val and not has_test:
        print(f"✓ PASSED: ROC-AUC not computed for multiclass")
    else:
        print(f"✗ FAILED: ROC-AUC incorrectly computed for multiclass")
except Exception as e:
    print(f"✗ FAILED: {e}")

# Test 6: Regression no ROC-AUC
print("\n[Test 6] No ROC-AUC for regression")
try:
    np.random.seed(42)
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
    has_cv = "roc_auc" in result["cross_validation_metrics"]
    has_val = "roc_auc" in result["validation_metrics"]
    has_test = "roc_auc" in result["test_metrics"]
    if not has_cv and not has_val and not has_test:
        print(f"✓ PASSED: ROC-AUC not computed for regression")
    else:
        print(f"✗ FAILED: ROC-AUC incorrectly computed for regression")
except Exception as e:
    print(f"✗ FAILED: {e}")

print("\n" + "=" * 70)
print("PHASE 1 TESTS COMPLETE")
print("=" * 70)
