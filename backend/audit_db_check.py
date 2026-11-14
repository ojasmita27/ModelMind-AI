import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("DATABASE INSPECTION")
print("=" * 70)

# Tables
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = [row[0] for row in cursor.fetchall()]
print(f"\nTables: {tables}")

# Row counts
for table in tables:
    cursor.execute(f'SELECT COUNT(*) FROM {table}')
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

# Check for experiments
cursor.execute('SELECT id, name, status, task_type, target_column FROM experiments LIMIT 5')
experiments = cursor.fetchall()
print(f"\nRecent experiments:")
for exp in experiments:
    print(f"  {exp}")

# Check for datasets
cursor.execute('SELECT id, name FROM datasets LIMIT 5')
datasets = cursor.fetchall()
print(f"\nDatasets:")
for ds in datasets:
    print(f"  {ds}")

# Check for dataset versions
cursor.execute('SELECT id, dataset_id, version_number, job_status FROM dataset_versions LIMIT 5')
versions = cursor.fetchall()
print(f"\nDataset versions:")
for v in versions:
    print(f"  {v}")

conn.close()
