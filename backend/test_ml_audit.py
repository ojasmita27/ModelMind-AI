"""Standalone ML performance audit script - tests ML pipeline without FastAPI dependencies."""
import sys
import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, mean_absolute_error, mean_squared_error, r2_score

# Add app to path
sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

from app.ml_engine.preprocessing import SplitConfig, split_frame
from app.ml_engine.training import run_experiment
from app.ml_engine.metrics import classification_metrics, regression_metrics


def test_synthetic_classification():
    """Test classification pipeline on synthetic data."""
    print("=" * 70)
    print("TEST 1: Synthetic Classification Dataset")
    print("=" * 70)
    
    # Create synthetic classification data
    np.random.seed(42)
    n_samples = 300
    X = pd.DataFrame({
        "feature1": np.random.randn(n_samples),
        "feature2": np.random.randn(n_samples),
        "feature3": np.random.choice(["A", "B", "C"], n_samples),
    })
    # Create a target with some signal
    y = ((X["feature1"] + X["feature2"] > 0) & (X["feature3"] == "A")).astype(int)
    frame = X.copy()
    frame["target"] = y
    
    print(f"Dataset shape: {frame.shape}")
    print(f"Target distribution: {frame['target'].value_counts().to_dict()}")
    print(f"Target classes: {sorted(frame['target'].unique())}")
    
    config = SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    
    try:
        result = run_experiment(
            frame,
            "target",
            "classification",
            ["Logistic Regression"],
            config,
        )
        
        print("\n--- RESULTS ---")
        print(f"Best model: {result['best_model_name']}")
        print(f"\nValidation metrics: {result['validation_metrics']}")
        print(f"Test metrics: {result['test_metrics']}")
        
        # Independent verification of test metrics
        train_x, val_x, test_x, train_y, val_y, test_y = split_frame(frame, "target", config, "classification")
        
        # Get predictions from trained model
        pipeline = result["trained_model"]
        test_pred = pipeline.predict(test_x)
        test_proba = pipeline.predict_proba(test_x) if hasattr(pipeline, "predict_proba") else None
        
        # Calculate metrics independently
        independent_metrics = {
            "accuracy": accuracy_score(test_y, test_pred),
            "precision_macro": precision_score(test_y, test_pred, average="macro", zero_division=0),
            "recall_macro": recall_score(test_y, test_pred, average="macro", zero_division=0),
            "f1_macro": f1_score(test_y, test_pred, average="macro", zero_division=0),
        }
        
        print("\n--- INDEPENDENT VERIFICATION ---")
        print(f"Independent test metrics: {independent_metrics}")
        print(f"Pipeline test metrics: {result['test_metrics']}")
        
        # Compare
        for key in independent_metrics:
            diff = abs(independent_metrics[key] - result['test_metrics'].get(key, 0))
            if diff < 0.001:
                print(f"✓ {key}: MATCH (diff={diff:.6f})")
            else:
                print(f"✗ {key}: MISMATCH (diff={diff:.6f})")
        
        return True, result['test_metrics']
        
    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, {}


def test_synthetic_regression():
    """Test regression pipeline on synthetic data."""
    print("\n" + "=" * 70)
    print("TEST 2: Synthetic Regression Dataset")
    print("=" * 70)
    
    # Create synthetic regression data
    np.random.seed(42)
    n_samples = 300
    X = pd.DataFrame({
        "feature1": np.random.randn(n_samples),
        "feature2": np.random.randn(n_samples),
        "feature3": np.random.choice(["A", "B", "C"], n_samples),
    })
    # Create a target with linear relationship + noise
    y = 2 * X["feature1"] + 3 * X["feature2"] + np.random.randn(n_samples) * 0.5
    frame = X.copy()
    frame["target"] = y
    
    print(f"Dataset shape: {frame.shape}")
    print(f"Target range: [{y.min():.2f}, {y.max():.2f}]")
    print(f"Target mean: {y.mean():.2f}, std: {y.std():.2f}")
    
    config = SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    
    try:
        result = run_experiment(
            frame,
            "target",
            "regression",
            ["Linear Regression"],
            config,
        )
        
        print("\n--- RESULTS ---")
        print(f"Best model: {result['best_model_name']}")
        print(f"\nValidation metrics: {result['validation_metrics']}")
        print(f"Test metrics: {result['test_metrics']}")
        
        # Independent verification of test metrics
        train_x, val_x, test_x, train_y, val_y, test_y = split_frame(frame, "target", config, "regression")
        
        # Get predictions from trained model
        pipeline = result["trained_model"]
        test_pred = pipeline.predict(test_x)
        
        # Calculate metrics independently
        independent_metrics = {
            "mae": mean_absolute_error(test_y, test_pred),
            "rmse": np.sqrt(mean_squared_error(test_y, test_pred)),
            "r2": r2_score(test_y, test_pred),
        }
        
        print("\n--- INDEPENDENT VERIFICATION ---")
        print(f"Independent test metrics: {independent_metrics}")
        print(f"Pipeline test metrics: {result['test_metrics']}")
        
        # Compare
        for key in independent_metrics:
            diff = abs(independent_metrics[key] - result['test_metrics'].get(key, 0))
            if diff < 0.001:
                print(f"✓ {key}: MATCH (diff={diff:.6f})")
            else:
                print(f"✗ {key}: MISMATCH (diff={diff:.6f})")
        
        return True, result['test_metrics']
        
    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, {}


def test_leakage_detection():
    """Test that pipeline detects potential target leakage."""
    print("\n" + "=" * 70)
    print("TEST 3: Target Leakage Detection")
    print("=" * 70)
    
    # Create data with perfect correlation (leakage)
    np.random.seed(42)
    n_samples = 100
    frame = pd.DataFrame({
        "feature1": np.random.randn(n_samples),
        "perfect_predictor": np.random.randint(0, 2, n_samples),  # This is the target!
        "target": np.random.randint(0, 2, n_samples),
    })
    frame["perfect_predictor"] = frame["target"]  # Perfect leakage
    
    print(f"Dataset with perfect correlation feature")
    print(f"Correlation with target: {frame['perfect_predictor'].corr(frame['target'])}")
    
    config = SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    
    try:
        result = run_experiment(
            frame,
            "target",
            "classification",
            ["Logistic Regression"],
            config,
        )
        
        print(f"\n--- RESULTS ---")
        print(f"Test accuracy: {result['test_metrics'].get('accuracy', 0):.4f}")
        
        if result['test_metrics'].get('accuracy', 0) > 0.95:
            print("⚠ WARNING: Very high accuracy may indicate target leakage")
        
        return True, result['test_metrics']
        
    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        return False, {}


def test_train_test_overlap():
    """Test that train and test sets are properly separated."""
    print("\n" + "=" * 70)
    print("TEST 4: Train/Test Separation")
    print("=" * 70)
    
    np.random.seed(42)
    frame = pd.DataFrame({
        "id": range(100),
        "feature": np.random.randn(100),
        "target": np.random.randint(0, 2, 100),
    })
    
    config = SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
    
    train_x, val_x, test_x, train_y, val_y, test_y = split_frame(frame, "target", config, "classification")
    
    print(f"Train size: {len(train_x)}")
    print(f"Validation size: {len(val_x)}")
    print(f"Test size: {len(test_x)}")
    
    # Check for overlap using the id column
    train_ids = set(train_x["id"])
    val_ids = set(val_x["id"])
    test_ids = set(test_x["id"])
    
    train_val_overlap = train_ids & val_ids
    train_test_overlap = train_ids & test_ids
    val_test_overlap = val_ids & test_ids
    
    print(f"\nTrain-Validation overlap: {len(train_val_overlap)}")
    print(f"Train-Test overlap: {len(train_test_overlap)}")
    print(f"Validation-Test overlap: {len(val_test_overlap)}")
    
    if len(train_test_overlap) == 0 and len(train_val_overlap) == 0 and len(val_test_overlap) == 0:
        print("✓ No overlap detected between splits")
        return True, {}
    else:
        print("✗ OVERLAP DETECTED - data leakage between splits")
        return False, {}


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("ML PERFORMANCE AUDIT - ModelMind AI")
    print("=" * 70)
    
    results = {}
    
    # Test 1: Classification
    success, metrics = test_synthetic_classification()
    results["classification"] = {"success": success, "metrics": metrics}
    
    # Test 2: Regression
    success, metrics = test_synthetic_regression()
    results["regression"] = {"success": success, "metrics": metrics}
    
    # Test 3: Leakage detection
    success, metrics = test_leakage_detection()
    results["leakage_test"] = {"success": success, "metrics": metrics}
    
    # Test 4: Train/test separation
    success, metrics = test_train_test_overlap()
    results["separation_test"] = {"success": success, "metrics": metrics}
    
    # Summary
    print("\n" + "=" * 70)
    print("AUDIT SUMMARY")
    print("=" * 70)
    for test_name, result in results.items():
        status = "✓ PASS" if result["success"] else "✗ FAIL"
        print(f"{test_name}: {status}")
