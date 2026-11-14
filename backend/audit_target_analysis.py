import pandas as pd
from pathlib import Path

file_path = Path(__file__).parent.parent / "data" / "uploads" / "datasets" / "1d19fad5-4284-40cd-b2f9-9a104c9f5525" / "v1" / "modelmind_customer_churn_sample.csv"
df = pd.read_csv(file_path)

print("=" * 70)
print("TARGET COLUMN ANALYSIS")
print("=" * 70)

# Analyze each column used as a target in experiments
targets_used = ["age", "tenure_months", "annual_income", "churn"]

for target in targets_used:
    print(f"\n--- Target: {target} ---")
    print(f"Data type: {df[target].dtype}")
    print(f"Unique values: {df[target].nunique()}")
    print(f"Missing values: {df[target].isnull().sum()}")
    print(f"Sample values: {df[target].head(10).tolist()}")
    
    if df[target].dtype in ['int64', 'float64']:
        print(f"Min: {df[target].min()}, Max: {df[target].max()}")
        print(f"Mean: {df[target].mean():.2f}, Std: {df[target].std():.2f}")
        
        # Check if it's actually discrete (could be classification)
        if df[target].nunique() < 20:
            print(f"Value counts:")
            print(df[target].value_counts().head(10))
    else:
        print(f"Value counts:")
        print(df[target].value_counts())

print(f"\n--- RECOMMENDATION ---")
print("Classification should use categorical targets like 'churn' (Yes/No)")
print("Regression should use continuous targets like 'age', 'tenure_months', 'annual_income'")
print("Using continuous numeric columns as classification targets is scientifically incorrect")
