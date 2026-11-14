"""Test CSV validation with various edge cases."""
import tempfile
import pandas as pd
from pathlib import Path

# Add app to path
import sys
sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

from app.validation.csv import validate_csv_upload

print("=" * 70)
print("CSV VALIDATION AUDIT")
print("=" * 70)

test_cases = [
    ("valid_mixed", "age,income,category\n25,50000,A\n30,60000,B\n35,70000,C"),
    ("empty_file", ""),
    ("header_only", "col1,col2,col3"),
    ("duplicate_columns", "age,age,income\n25,25,50000\n30,30,60000"),
    ("missing_values", "age,income,category\n25,,A\n,60000,B\n35,70000,"),
    ("all_missing_target", "age,income,target\n25,50000,\n30,60000,\n35,70000,"),
    ("single_row", "age,income\n25,50000"),
    ("invalid_encoding", "age,income\n25,50000\n30,60000".encode('latin1')),
    ("constant_column", "age,income,value\n25,50000,X\n30,60000,X\n35,70000,X"),
]

for name, content in test_cases:
    print(f"\n--- Test: {name} ---")
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as f:
        if isinstance(content, bytes):
            f.write(content)
        else:
            f.write(content.encode('utf-8'))
        temp_path = f.name
    
    try:
        result = validate_csv_upload(temp_path, max_size_mb=10)
        print(f"✓ Valid: {result}")
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        Path(temp_path).unlink(missing_ok=True)
