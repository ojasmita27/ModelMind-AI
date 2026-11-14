"""Detailed investigation of artifact persistence issue."""
import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("ARTIFACT PERSISTENCE INVESTIGATION")
print("=" * 70)

# Get all experiments with their artifact_uri
cursor.execute('''
    SELECT id, name, status, artifact_uri, created_at, completed_at
    FROM experiments
    ORDER BY created_at DESC
''')

experiments = cursor.fetchall()
print(f"\nTotal experiments: {len(experiments)}\n")

# Check storage structure
from app.storage import LocalObjectStorage
storage = LocalObjectStorage()
experiments_dir = storage.base_path / "experiments"

print(f"Storage base path: {storage.base_path}")
print(f"Experiments directory exists: {experiments_dir.exists()}")

if experiments_dir.exists():
    exp_folders = list(experiments_dir.iterdir())
    print(f"Experiment folders in storage: {len(exp_folders)}")
    for folder in exp_folders:
        print(f"  {folder.name}")

print("\n" + "=" * 70)
print("EXPERIMENT-BY-EXPERIMENT ANALYSIS")
print("=" * 70)

for exp_id, name, status, artifact_uri, created_at, completed_at in experiments:
    print(f"\n--- Experiment: {name} ---")
    print(f"ID: {exp_id}")
    print(f"Status: {status}")
    print(f"Created: {created_at}")
    print(f"Completed: {completed_at}")
    print(f"Artifact URI: {artifact_uri}")
    
    if artifact_uri:
        if artifact_uri.startswith("local://"):
            storage_key = artifact_uri.replace("local://", "")
            print(f"Storage key: {storage_key}")
            
            # Check if file exists
            exists = storage.exists(storage_key)
            print(f"Model file exists: {exists}")
            
            # Check manifest
            manifest_key = storage_key.replace("model.joblib", "manifest.json")
            manifest_exists = storage.exists(manifest_key)
            print(f"Manifest file exists: {manifest_exists}")
            
            # Check if experiment folder exists
            exp_folder = storage.base_path / storage_key
            if exp_folder.parent.exists():
                print(f"Experiment folder exists: {exp_folder.parent.exists()}")
                print(f"Folder contents: {list(exp_folder.parent.iterdir())}")
            
            if not exists:
                print("⚠ MISSING ARTIFACT - This experiment cannot be reproduced")
        else:
            print(f"⚠ Invalid artifact_uri format: {artifact_uri}")
    else:
        if status == "completed":
            print("⚠ COMPLETED BUT NO ARTIFACT_URI - This is a data integrity issue")
        else:
            print("No artifact (expected for non-completed experiments)")

conn.close()

# Check if there's a UUID mismatch issue
print("\n" + "=" * 70)
print("UUID MISMATCH ANALYSIS")
print("=" * 70)

# Extract UUIDs from database artifact_uris
cursor.execute('SELECT id, artifact_uri FROM experiments WHERE artifact_uri IS NOT NULL')
db_uris = cursor.fetchall()

print("\nDatabase artifact URIs:")
for exp_id, uri in db_uris:
    if uri and uri.startswith("local://"):
        key = uri.replace("local://", "")
        exp_uuid = key.split("/")[1]
        print(f"  Experiment ID: {exp_id}")
        print(f"    Storage UUID: {exp_uuid}")
        print(f"    Match: {str(exp_id).replace('-', '') == exp_uuid.replace('-', '')}")

conn.close()
