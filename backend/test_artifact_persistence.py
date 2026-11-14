"""Test model artifact persistence and loading."""
import sys
import sqlite3
import json
from pathlib import Path

sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

from app.storage import LocalObjectStorage

print("=" * 70)
print("ARTIFACT PERSISTENCE AND LOADING TEST")
print("=" * 70)

# Check database for experiments with artifacts
db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('''
    SELECT id, name, status, artifact_uri, metrics
    FROM experiments
    WHERE status = 'completed'
    LIMIT 5
''')

experiments = cursor.fetchall()
print(f"\nFound {len(experiments)} completed experiments")

storage = LocalObjectStorage()

for exp_id, name, status, artifact_uri, metrics_json in experiments:
    print(f"\n--- Experiment: {name} ---")
    print(f"ID: {exp_id}")
    print(f"Status: {status}")
    print(f"Artifact URI: {artifact_uri}")
    
    if artifact_uri:
        # Extract key from URI
        if artifact_uri.startswith("local://"):
            storage_key = artifact_uri.replace("local://", "")
            print(f"Storage key: {storage_key}")
            
            # Check if file exists
            exists = storage.exists(storage_key)
            print(f"Model file exists: {exists}")
            
            if exists:
                try:
                    # Try to load the model
                    import joblib
                    with storage.open(storage_key) as f:
                        model = joblib.load(f)
                    print(f"✓ Model loaded successfully")
                    print(f"  Model type: {type(model).__name__}")
                    
                    # Check for manifest
                    manifest_key = storage_key.replace("model.joblib", "manifest.json")
                    manifest_exists = storage.exists(manifest_key)
                    print(f"Manifest exists: {manifest_exists}")
                    
                    if manifest_exists:
                        with storage.open(manifest_key) as f:
                            manifest = json.load(f)
                        print(f"✓ Manifest loaded")
                        print(f"  Experiment ID in manifest: {manifest.get('experiment_id')}")
                        print(f"  Dataset SHA256: {manifest.get('dataset_sha256')[:16]}...")
                    
                except Exception as e:
                    print(f"✗ Failed to load model: {e}")
            else:
                print(f"✗ Model file missing from storage")
    else:
        print(f"✗ No artifact_uri (model not persisted)")
    
    # Check metrics
    if metrics_json:
        try:
            metrics = json.loads(metrics_json)
            print(f"Metrics keys: {list(metrics.keys())}")
        except:
            print(f"✗ Failed to parse metrics JSON")

conn.close()

# Check storage directory structure
print(f"\n--- Storage Directory Structure ---")
experiments_dir = storage.base_path / "experiments"
if experiments_dir.exists():
    print(f"Experiments directory exists: {experiments_dir}")
    for item in experiments_dir.iterdir():
        if item.is_dir():
            print(f"  Experiment folder: {item.name}")
            model_file = item / "model.joblib"
            manifest_file = item / "manifest.json"
            print(f"    model.joblib: {'✓' if model_file.exists() else '✗'}")
            print(f"    manifest.json: {'✓' if manifest_file.exists() else '✗'}")
else:
    print(f"✗ Experiments directory does not exist")
