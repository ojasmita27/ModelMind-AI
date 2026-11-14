import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("DETAILED EXPERIMENT INSPECTION")
print("=" * 70)

cursor.execute('''
    SELECT id, name, status, task_type, target_column, 
           train_fraction, validation_fraction, test_fraction, 
           random_seed, model_names, metrics, error, 
           dataset_id, dataset_version_id
    FROM experiments
    ORDER BY created_at DESC
''')

experiments = cursor.fetchall()

print(f"\nTotal experiments: {len(experiments)}\n")

for i, exp in enumerate(experiments, 1):
    (exp_id, name, status, task_type, target, 
     train_frac, val_frac, test_frac, seed, 
     models_json, metrics_json, error, 
     dataset_id, version_id) = exp
    
    print(f"--- Experiment {i}: {name} ---")
    print(f"ID: {exp_id}")
    print(f"Status: {status}")
    print(f"Task: {task_type}")
    print(f"Target: {target}")
    print(f"Splits: train={train_frac}, val={val_frac}, test={test_frac}")
    print(f"Seed: {seed}")
    print(f"Models: {models_json}")
    print(f"Dataset ID: {dataset_id}")
    print(f"Version ID: {version_id}")
    
    if metrics_json:
        try:
            metrics = json.loads(metrics_json)
            print(f"Metrics: {json.dumps(metrics, indent=2)}")
        except:
            print(f"Metrics (raw): {metrics_json}")
    else:
        print("Metrics: None")
    
    if error:
        print(f"Error: {error}")
    
    print()

conn.close()
