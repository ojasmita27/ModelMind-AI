"""Test path traversal and filename sanitization."""
import sys
sys.path.insert(0, "d:/Projects/ModelmindAI/M1-Fullstack-Test/modelmind/backend")

from app.services.datasets import _sanitize_filename

print("=" * 70)
print("PATH TRAVERSAL AND FILENAME SANITIZATION TEST")
print("=" * 70)

test_cases = [
    ("normal.csv", "normal.csv"),
    ("../etc/passwd", "passwd"),
    ("../../windows/system32/config", "config"),
    ("/absolute/path.csv", "path.csv"),
    ("C:\\Windows\\System32\\file.csv", "file.csv"),
    ("../../../evil.sh", "evil.sh"),
    ("file with spaces.csv", "file_with_spaces.csv"),
    ("file@#$%^&*().csv", "file______.csv"),
    (".hidden", "hidden"),
    ("...hidden", "hidden"),
    ("   leading_spaces.csv", "leading_spaces.csv"),
    ("trailing_spaces.csv   ", "trailing_spaces.csv"),
    ("very_long_filename_" + "x" * 200 + ".csv", "x" * 100),  # Truncated
    ("", "upload.csv"),  # Empty fallback
    ("___", "upload.csv"),  # Only underscores fallback
]

print("\nTesting _sanitize_filename:")
all_passed = True
for input_name, expected in test_cases:
    result = _sanitize_filename(input_name)
    passed = result == expected
    all_passed = all_passed and passed
    status = "✓" if passed else "✗"
    print(f"{status} '{input_name}' -> '{result}' (expected: '{expected}')")
    if not passed:
        print(f"   MISMATCH")

print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")

# Test that sanitized names cannot escape base path
from pathlib import Path
from app.storage import LocalObjectStorage

print("\nTesting storage key construction:")
storage = LocalObjectStorage()
base_path = storage.base_path

dangerous_names = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32",
    "/absolute/path",
    "C:\\Windows\\System32",
]

for dangerous in dangerous_names:
    safe = _sanitize_filename(dangerous)
    # Simulate storage key construction
    storage_key = f"datasets/test-uuid/v1/{safe}"
    full_path = base_path / storage_key
    # Check if the resolved path stays within base_path
    try:
        resolved = full_path.resolve()
        is_safe = str(resolved).startswith(str(base_path.resolve()))
        status = "✓" if is_safe else "✗ DANGEROUS"
        print(f"{status} '{dangerous}' -> key: '{storage_key}' -> safe: {is_safe}")
    except Exception as e:
        print(f"✗ ERROR: {e}")
