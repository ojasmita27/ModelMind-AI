from pathlib import Path

# Read the actual file that exists
file_path = Path(__file__).parent.parent / "data" / "uploads" / "datasets" / "1d19fad5-4284-40cd-b2f9-9a104c9f5525" / "v1" / "modelmind_customer_churn_sample.csv"

print("=" * 70)
print("READING ACTUAL DATASET FILE")
print("=" * 70)
print(f"File: {file_path}")
print(f"Exists: {file_path.exists()}")

if file_path.exists():
    import pandas as pd
    df = pd.read_csv(file_path)
    print(f"\nShape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst 5 rows:")
    print(df.head())
    print(f"\nData types:")
    print(df.dtypes)
    print(f"\nMissing values:")
    print(df.isnull().sum())
    print(f"\nUnique values per column:")
    for col in df.columns:
        print(f"  {col}: {df[col].nunique()}")
