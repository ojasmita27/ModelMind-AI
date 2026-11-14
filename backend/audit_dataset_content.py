import sqlite3
import json
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("DATASET CONTENT INSPECTION")
print("=" * 70)

# Get dataset versions with file paths
cursor.execute('''
    SELECT d.id, d.name, dv.id, dv.version_number, dv.file_path, 
           dv.row_count, dv.column_count, dv.job_status
    FROM datasets d
    JOIN dataset_versions dv ON d.id = dv.dataset_id
    ORDER BY d.name, dv.version_number
''')

datasets = cursor.fetchall()

for ds in datasets:
    (ds_id, ds_name, v_id, v_num, file_path, row_count, col_count, job_status) = ds
    print(f"\n--- Dataset: {ds_name}, Version {v_num} ---")
    print(f"ID: {ds_id}")
    print(f"Version ID: {v_id}")
    print(f"File: {file_path}")
    print(f"Rows: {row_count}, Columns: {col_count}")
    print(f"Job Status: {job_status}")
    
    # Try to read the file
    try:
        import pandas as pd
        df = pd.read_csv(file_path)
        print(f"\nActual shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print(f"\nFirst 3 rows:")
        print(df.head(3))
        print(f"\nData types:")
        print(df.dtypes)
        print(f"\nMissing values:")
        print(df.isnull().sum())
    except Exception as e:
        print(f"Error reading file: {e}")

conn.close()
