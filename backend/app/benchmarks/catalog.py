"""Public benchmark dataset catalog.

Loaders resolve to real sklearn/OpenML data at import time — nothing is
fabricated. `row_count`/`column_count` are filled from the actual fetched
data, not hardcoded.
"""
from __future__ import annotations

BENCHMARK_DATASETS: list[dict] = [
    {
        "id": "breast-cancer-wisconsin",
        "name": "Breast Cancer Wisconsin",
        "description": "Classic diagnostic dataset of digitized fine-needle aspirate images of breast masses.",
        "task_type": "classification",
        "target_column": "target",
        "source": "scikit-learn (load_breast_cancer)",
        "source_url": "https://scikit-learn.org/stable/datasets/toy_dataset.html#breast-cancer-dataset",
        "license": "Public domain (UCI ML Repository)",
        "citation": "Wolberg, W. & Mangasarian, O. (1990). Cancer diagnosis via linear programming.",
        "loader": {"kind": "sklearn", "fn": "load_breast_cancer"},
    },
    {
        "id": "wine-quality-classification",
        "name": "Wine Quality (Classification)",
        "description": "Wine physicochemical properties classified into quality grades.",
        "task_type": "classification",
        "target_column": "target",
        "source": "scikit-learn (load_wine)",
        "source_url": "https://scikit-learn.org/stable/datasets/toy_dataset.html#wine-dataset",
        "license": "CC BY 4.0 (UCI ML Repository)",
        "citation": "Forina et al. (1991). PARVUS — an extendible package for data exploration.",
        "loader": {"kind": "sklearn", "fn": "load_wine"},
    },
    {
        "id": "diabetes",
        "name": "Diabetes",
        "description": "Ten baseline variables for diabetes patients; regression on disease progression.",
        "task_type": "regression",
        "target_column": "target",
        "source": "scikit-learn (load_diabetes)",
        "source_url": "https://scikit-learn.org/stable/datasets/toy_dataset.html#diabetes-dataset",
        "license": "Public domain (Efron, Hastie, Johnstone & Tibshirani, 2004)",
        "citation": "Efron et al. (2004). Least angle regression. Annals of Statistics 32(2).",
        "loader": {"kind": "sklearn", "fn": "load_diabetes"},
        "scale_target": True,
    },
    {
        "id": "california-housing",
        "name": "California Housing",
        "description": "Census-block housing attributes for median house value regression.",
        "task_type": "regression",
        "target_column": "MedHouseVal",
        "source": "scikit-learn (fetch_california_housing)",
        "source_url": "https://scikit-learn.org/stable/datasets/real_world.html#california-housing-dataset",
        "license": "Public domain (Pace & Barry, 1997)",
        "citation": "Pace, R.K. & Barry, R. (1997). Sparse spatial autoregressions. Statistics & Probability Letters 33(3).",
        "loader": {"kind": "sklearn", "fn": "fetch_california_housing"},
    },
    {
        "id": "adult-income",
        "name": "Adult Income",
        "description": "Census income survey; predict whether income exceeds $50K/yr.",
        "task_type": "classification",
        "target_column": "class",
        "source": "OpenML",
        "source_url": "https://www.openml.org/d/1590",
        "license": "Public domain (UCI ML Repository)",
        "citation": "Becker & Kohavi (1996). Adult data set. UCI ML Repository.",
        "loader": {"kind": "openml", "name": "adult", "version": 2},
    },
    {
        "id": "bank-marketing",
        "name": "Bank Marketing",
        "description": "Portuguese bank telemarketing campaign outcomes.",
        "task_type": "classification",
        "target_column": "y",
        "source": "OpenML",
        "source_url": "https://www.openml.org/d/1461",
        "license": "CC BY 4.0 (Moro, Cortez & Rita, 2014)",
        "citation": "Moro, S., Cortez, P. & Rita, P. (2014). A data-driven approach to predict the success of bank telemarketing. Decision Support Systems 62.",
        "loader": {"kind": "openml", "name": "bank-marketing", "version": 1},
    },
    {
        "id": "telco-churn",
        "name": "Telco Customer Churn",
        "description": "Telecom customer attributes and monthly churn indicator.",
        "task_type": "classification",
        "target_column": "Churn",
        "source": "OpenML",
        "source_url": "https://www.openml.org/d/42178",
        "license": "Public (IBM Sample Data)",
        "citation": "IBM (2019). Telco Customer Churn dataset, Kaggle/OpenML mirror.",
        "loader": {"kind": "openml", "name": "telco-customer-churn", "version": 1},
    },
    {
        "id": "wine-quality-regression",
        "name": "Wine Quality (Regression)",
        "description": "Wine physicochemical properties regressed onto sensory quality score.",
        "task_type": "regression",
        "target_column": "quality",
        "source": "OpenML",
        "source_url": "https://www.openml.org/d/287",
        "license": "CC BY 4.0 (UCI ML Repository)",
        "citation": "Cortez et al. (2009). Modeling wine preferences by data mining. Decision Support Systems 47(4).",
        "loader": {"kind": "openml", "name": "wine-quality-red", "version": 1},
    },
    {
        "id": "bike-sharing",
        "name": "Bike Sharing",
        "description": "Hourly bike rental counts from Capital Bikeshare.",
        "task_type": "regression",
        "target_column": "cnt",
        "source": "OpenML",
        "source_url": "https://www.openml.org/d/42712",
        "license": "Public (UCI ML Repository)",
        "citation": "Fanaee-T & Gama (2014). Event labeling combining ensemble detectors. SDM.",
        "loader": {"kind": "openml", "name": "bike-sharing-demand", "version": 1},
    },
]


def get_benchmark(benchmark_id: str) -> dict | None:
    for entry in BENCHMARK_DATASETS:
        if entry["id"] == benchmark_id:
            return entry
    return None


def public_view(entry: dict) -> dict:
    """Catalog entry for API/UI — no loader internals."""
    return {k: v for k, v in entry.items() if k != "loader"}


def load_frame(entry: dict):
    """Download/load the real dataset. Returns (frame, target_column, meta)."""
    import pandas as pd
    from sklearn import datasets

    loader = entry["loader"]
    if loader["kind"] == "sklearn":
        fn = getattr(datasets, loader["fn"])
        bunch = fn()
        frame = pd.DataFrame(bunch.data, columns=bunch.feature_names)
        target_name = entry["target_column"]
        if target_name not in frame.columns:
            frame[target_name] = bunch.target
        return frame, target_name, {"source": entry["source"], "license": entry["license"]}

    # OpenML — downloads on demand; failure surfaces to the caller.
    from sklearn.datasets import fetch_openml

    data = fetch_openml(loader["name"], version=loader.get("version", 1), as_frame=True)
    frame = data.frame.copy()
    target = entry["target_column"]
    if target not in frame.columns and data.target is not None:
        # OpenML frame includes the target as the last column typically.
        candidates = [c for c in frame.columns if str(c).lower() == target.lower()]
        if candidates:
            target = candidates[0]
        elif len(data.target_names or []) == 1:
            tname = data.target_names[0]
            if tname in frame.columns:
                target = tname
    if target not in frame.columns:
        raise ValueError(f"Target column '{entry['target_column']}' not found in downloaded data (columns: {list(frame.columns)[:20]}…)")
    return frame, target, {"source": entry["source"], "license": entry["license"], "openml_id": getattr(data, "details", {}).get("id", None) if hasattr(data, "details") else None}
