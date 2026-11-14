"""Dataset intelligence profiling — all values computed from actual data."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

_IQR_K = 1.5


def _infer_type(series: pd.Series) -> str:
    if pd.api.types.is_numeric_dtype(series) or _is_numeric_strings(series):
        return "numeric"
    if _is_datetime(series):
        return "datetime"
    unique_ratio = series.nunique() / max(len(series), 1)
    if unique_ratio < 0.5 or series.nunique() <= 50:
        return "categorical"
    return "text"


def _is_numeric_strings(series: pd.Series) -> bool:
    non_null = series.dropna()
    if non_null.empty:
        return False
    return pd.to_numeric(non_null, errors="coerce").notna().all()


def _is_datetime(series: pd.Series) -> bool:
    non_null = series.dropna().astype(str)
    if non_null.empty or len(non_null) > 5000:
        non_null = non_null.head(5000)
    try:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    except Exception:
        return False
    return bool(parsed.notna().mean() > 0.8)


def _numeric_stats(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {}
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    iqr = float(q3 - q1)
    lo, hi = q1 - _IQR_K * iqr, q3 + _IQR_K * iqr
    outliers = int(((numeric < lo) | (numeric > hi)).sum())
    return {
        "mean": round(float(numeric.mean()), 6),
        "median": round(float(numeric.median()), 6),
        "std": round(float(numeric.std(ddof=0)), 6),
        "min": round(float(numeric.min()), 6),
        "max": round(float(numeric.max()), 6),
        "q1": round(float(q1), 6),
        "q3": round(float(q3), 6),
        "iqr": round(iqr, 6),
        "outlier_count": outliers,
        "outlier_pct": round(outliers / len(numeric) * 100, 2),
    }


def _column_profile(name: str, series: pd.Series, row_count: int) -> dict[str, Any]:
    col_type = _infer_type(series)
    missing = int(series.isna().sum())
    unique = int(series.nunique(dropna=True))
    non_null = series.dropna()

    profile: dict[str, Any] = {
        "name": name,
        "type": col_type,
        "missing_count": missing,
        "missing_percentage": round(missing / row_count * 100, 2) if row_count else 0.0,
        "unique_count": unique,
        "unique_percentage": round(unique / max(len(non_null), 1) * 100, 2),
        "is_constant": unique <= 1,
        "is_near_constant": unique > 1 and (unique / max(len(non_null), 1) < 0.01 or _top_share(non_null) > 0.98),
        "is_high_cardinality": col_type in ("categorical", "text") and unique > 100,
        "is_identifier": col_type == "numeric" and unique == len(non_null) and len(non_null) > 10,
        "sample_values": [str(v)[:100] for v in non_null.head(5)],
    }
    if col_type == "numeric":
        profile["stats"] = _numeric_stats(series)
    elif col_type == "datetime":
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        profile["stats"] = {
            "min": str(parsed.min()) if parsed.notna().any() else None,
            "max": str(parsed.max()) if parsed.notna().any() else None,
        }
    else:
        vc = non_null.value_counts().head(5)
        profile["top_values"] = {str(k)[:80]: int(v) for k, v in vc.items()}
    return profile


def _top_share(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(series.value_counts(normalize=True).iloc[0])


def compute_intelligence(frame: pd.DataFrame, target_column: str | None = None) -> dict[str, Any]:
    """Compute the full intelligence payload for a dataset frame."""
    row_count = len(frame)
    warnings: list[str] = []
    columns = [_column_profile(str(c), frame[c], row_count) for c in frame.columns]

    dup_count = int(frame.duplicated().sum())
    dup_pct = round(dup_count / row_count * 100, 2) if row_count else 0.0

    numeric_cols = [c["name"] for c in columns if c["type"] == "numeric"]
    correlation: dict[str, Any] | None = None
    if len(numeric_cols) >= 2:
        corr = frame[numeric_cols].apply(pd.to_numeric, errors="coerce").corr()
        corr = corr.fillna(0.0)
        correlation = {
            "columns": numeric_cols,
            "matrix": [[round(float(corr.iloc[i, j]), 4) for j in range(len(numeric_cols))] for i in range(len(numeric_cols))],
        }

    target_info: dict[str, Any] | None = None
    if target_column and target_column in frame.columns:
        t = frame[target_column]
        vc = t.value_counts(dropna=False)
        non_null = t.dropna()
        target_info = {
            "column": target_column,
            "type": _infer_type(t),
            "missing_count": int(t.isna().sum()),
            "class_count": int(non_null.nunique()),
            "distribution": {str(k)[:80]: int(v) for k, v in vc.head(20).items()},
        }
        if target_info["class_count"] > 1:
            shares = non_null.value_counts(normalize=True)
            target_info["imbalance_ratio"] = round(float(shares.max() / shares.min()), 2)
            target_info["dominant_class_pct"] = round(float(shares.max() * 100), 2)
            if shares.max() > 0.9:
                warnings.append(f"Target '{target_column}' is highly imbalanced: dominant class is {shares.max()*100:.1f}% of rows.")

    for c in columns:
        if c["is_identifier"]:
            warnings.append(f"Column '{c['name']}' looks like an identifier (all unique values) — leakage risk.")
        if c["is_high_cardinality"]:
            warnings.append(f"Column '{c['name']}' has high cardinality ({c['unique_count']} unique values).")
        if c["is_constant"]:
            warnings.append(f"Column '{c['name']}' is constant and carries no information.")
        elif c["is_near_constant"]:
            warnings.append(f"Column '{c['name']}' is near-constant.")
        if c["missing_percentage"] > 50:
            warnings.append(f"Column '{c['name']}' is {c['missing_percentage']}% missing.")
        if c["type"] == "numeric" and c.get("stats", {}).get("outlier_pct", 0) > 5:
            warnings.append(f"Column '{c['name']}' has {c['stats']['outlier_pct']}% IQR outliers.")
    if dup_count:
        warnings.append(f"{dup_count} duplicate rows ({dup_pct}%).")

    # Transparent quality score: start at 100, subtract per-criterion penalties.
    criteria = {
        "missing_values": round(min(sum(c["missing_percentage"] for c in columns) / len(columns), 100) * 0.4, 2),
        "duplicate_rows": round(min(dup_pct * 2, 40), 2),
        "constant_columns": round(len([c for c in columns if c["is_constant"]]) * 5, 2),
        "high_missing_columns": round(len([c for c in columns if c["missing_percentage"] > 50]) * 10, 2),
        "identifier_columns": round(len([c for c in columns if c["is_identifier"]]) * 10, 2),
        "outliers": round(min(sum(c.get("stats", {}).get("outlier_pct", 0) for c in columns if c["type"] == "numeric") / max(len(numeric_cols), 1), 100) * 0.2, 2),
    }
    total_penalty = round(sum(criteria.values()), 2)
    quality_score = max(0, round(100 - total_penalty, 1))

    return {
        "row_count": row_count,
        "column_count": len(frame.columns),
        "columns": columns,
        "duplicate_row_count": dup_count,
        "duplicate_row_percentage": dup_pct,
        "correlation": correlation,
        "target": target_info,
        "quality_score": quality_score,
        "quality_criteria": criteria,
        "warnings": warnings,
    }
