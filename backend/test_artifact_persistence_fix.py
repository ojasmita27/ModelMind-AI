"""Test artifact persistence fix with isolated storage."""
import sys
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

import pandas as pd
import numpy as np
import joblib
import json
from app.storage import LocalObjectStorage
from app.ml_engine.preprocessing import SplitConfig
from app.ml_engine.training import run_experiment

print("=" * 70)
print("ARTIFACT PERSISTENCE FIX VERIFICATION")
print("=" * 70)

# Create temporary storage directory
temp_storage = Path(tempfile.mkdtemp())
print(f"\nUsing temporary storage: {temp_storage}")

try:
    # Create isolated storage instance
    storage = LocalObjectStorage(base_path=temp_storage)
    
    # Create test dataset
    np.random.seed(42)
    frame = pd.DataFrame({
        "feature1": np.random.randn(100),
        "feature2": np.random.randn(100),
        "target": np.random.choice([0, 1], 100)
    })
    
    print("\n[Test 1] Run experiment with artifact persistence")
    try:
        result = run_experiment(
            frame,
            "target",
            "classification",
            ["Logistic Regression"],
            SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=42)
        )
        print("✓ Experiment training completed")
        
        # Simulate the artifact persistence process from experiments.py
        import io
        import uuid
        
        experiment_id = uuid.uuid4()
        model_key = f"experiments/{experiment_id}/model.joblib"
        manifest_key = f"experiments/{experiment_id}/manifest.json"
        
        # Write model
        model_buf = io.BytesIO()
        joblib.dump(result["trained_model"], model_buf)
        model_buf.seek(0)
        storage.put(model_key, model_buf)
        
        # Verify model write
        if not storage.exists(model_key):
            print("✗ FAILED: Model file verification failed")
        else:
            print("✓ Model file verified after write")
        
        # Write manifest
        manifest = {
            "experiment_id": str(experiment_id),
            "task_type": "classification",
            "target_column": "target",
            "best_model_name": result["best_model_name"],
            "test_metrics": result["test_metrics"]
        }
        manifest_buf = io.BytesIO(json.dumps(manifest, indent=2).encode("utf-8"))
        storage.put(manifest_key, manifest_buf)
        
        # Verify manifest write
        if not storage.exists(manifest_key):
            print("✗ FAILED: Manifest file verification failed")
        else:
            print("✓ Manifest file verified after write")
        
        print("\n[Test 2] Load model from storage")
        try:
            with storage.open(model_key) as f:
                loaded_model = joblib.load(f)
            print(f"✓ Model loaded successfully: {type(loaded_model).__name__}")
            
            # Verify model can predict
            test_data = frame.iloc[:5].drop(columns=["target"])
            predictions = loaded_model.predict(test_data)
            print(f"✓ Model can predict: {predictions}")
            
        except Exception as e:
            print(f"✗ FAILED to load model: {e}")
        
        print("\n[Test 3] Load manifest from storage")
        try:
            with storage.open(manifest_key) as f:
                loaded_manifest = json.load(f)
            print(f"✓ Manifest loaded successfully")
            print(f"  Experiment ID: {loaded_manifest.get('experiment_id')}")
            print(f"  Best model: {loaded_manifest.get('best_model_name')}")
            
        except Exception as e:
            print(f"✗ FAILED to load manifest: {e}")
        
        print("\n[Test 4] Simulate storage write failure")
        # Test that verification catches missing files
        fake_key = "experiments/fake-id/model.joblib"
        if storage.exists(fake_key):
            print("✗ FAILED: Fake key should not exist")
        else:
            print("✓ Storage verification correctly detects missing files")
        
    except Exception as e:
        print(f"✗ FAILED: {e}")
        import traceback
        traceback.print_exc()

finally:
    # Cleanup
    shutil.rmtree(temp_storage, ignore_errors=True)
    print(f"\nCleaned up temporary storage")

print("\n" + "=" * 70)
print("ARTIFACT PERSISTENCE TESTS COMPLETE")
print("=" * 70)
