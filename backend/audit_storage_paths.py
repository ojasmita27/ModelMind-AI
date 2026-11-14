import sqlite3
from pathlib import Path

db_path = Path(__file__).parent.parent / "data" / "modelmind_dev.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 70)
print("STORAGE PATH INSPECTION")
print("=" * 70)

# Get file paths from database
cursor.execute('SELECT file_path FROM dataset_versions')
file_paths = cursor.fetchall()

print(f"\nFile paths in database:")
for (fp,) in file_paths:
    print(f"  {fp}")

# Check where storage should be
from app.core.config import get_settings, PROJECT_ROOT
settings = get_settings()

print(f"\nStorage base path from config:")
print(f"  PROJECT_ROOT: {PROJECT_ROOT}")
print(f"  Expected storage: {PROJECT_ROOT / 'data' / 'uploads'}")

# Check actual storage location
storage_base = Path(__file__).parent.parent / "data" / "uploads"
print(f"\nActual storage location: {storage_base}")
print(f"Exists: {storage_base.exists()}")

if storage_base.exists():
    print(f"\nContents:")
    for item in storage_base.rglob("*"):
        if item.is_file():
            print(f"  {item.relative_to(storage_base.parent.parent)}")

conn.close()
