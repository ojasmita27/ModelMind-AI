"""Structured dataset intelligence findings from computed profile data."""
from __future__ import annotations

from typing import Any


def _finding(fid: str, category: str, method: str, columns: list[str], rows: int | None,
             pct: float | None, severity: str, evidence: str, explanation: str,
             recommendation: str, confidence: str = "heuristic") -> dict[str, Any]:
    return {
        "id": fid, "category": category, "method": method, "columns": columns,
        "affected_rows": rows, "affected_pct": pct, "severity": severity,
        "evidence": evidence, "confidence": confidence, "explanation": explanation,
        "recommendation": recommendation,
    }


def build_findings(profile: dict[str, Any], frame_rows: int) -> list[dict[str, Any]]:
    """Convert a compute_intelligence() profile into structured findings."""
    findings: list[dict[str, Any]] = []
    cols = profile.get("columns") or []

    for c in cols:
        name = c.get("name", "?")
        mp = c.get("missing_percentage") or 0
        if mp > 0:
            sev = "critical" if mp >= 50 else "warning" if mp >= 10 else "info"
            findings.append(_finding(
                f"missing_{name}", "missing_values", "null-rate per column", [name],
                c.get("missing_count"), mp, sev,
                f"{mp}% of rows are null",
                "Missing values can bias statistics and break some models.",
                "Investigate why values are absent; consider imputation or row filtering in the cleaning workbench.",
            ))
        stats = c.get("stats") or {}
        op = stats.get("outlier_pct")
        if op and op > 0:
            findings.append(_finding(
                f"outlier_{name}", "outliers", "IQR fences (1.5×IQR)", [name],
                int(round(op / 100 * frame_rows)), op, "warning" if op < 10 else "critical",
                f"{op}% of values fall outside IQR fences",
                "Extreme values may dominate distance-based models and inflate variance.",
                "Inspect whether outliers are genuine or errors; use IQR capping or row removal if appropriate.",
            ))
        if c.get("is_high_cardinality"):
            findings.append(_finding(
                f"cardinality_{name}", "high_cardinality", "unique-value count", [name], None, None,
                "warning", f"{c.get('unique_count')} unique values",
                "High-cardinality categoricals can cause overfitting and sparse one-hot encoding.",
                "Consider grouping rare categories or target encoding.",
            ))
        if c.get("is_constant"):
            findings.append(_finding(
                f"constant_{name}", "constant_feature", "unique-value count == 1", [name], frame_rows, 100.0,
                "info", "Column has a single distinct value",
                "Constant columns carry no information for the model.",
                "Drop the column in the cleaning workbench.",
            ))
        elif c.get("is_near_constant"):
            findings.append(_finding(
                f"nearconst_{name}", "near_constant", "dominant-value share > 98%", [name], None, None,
                "info", f"Top value share {c.get('top_values') and 'dominant' or 'high'}",
                "Near-constant columns add little information.",
                "Review whether the column is meaningful before dropping.",
            ))
        if c.get("is_identifier"):
            findings.append(_finding(
                f"leakage_{name}", "leakage_indicator", "all-unique numeric heuristic", [name], None, None,
                "warning", f"'{name}' has all-unique numeric values",
                "Identifier-like columns may leak the target or inflate metrics; heuristic only — verify manually.",
                "Confirm the column is not derived from the target; exclude it if it is.",
                "heuristic"))

    dup_count = profile.get("duplicate_row_count") or 0
    dup_pct = profile.get("duplicate_row_percentage") or 0.0
    if dup_count:
        findings.append(_finding(
            "duplicates", "duplicates", "exact-row hashing", [], dup_count, dup_pct,
            "warning" if dup_pct > 5 else "info", f"{dup_count} duplicate rows ({dup_pct}%)",
            "Duplicate rows can overweight repeated records.",
            "Review duplicates; remove exact duplicates if they are not meaningful repeats.",
        ))

    target = profile.get("target") or {}
    if target.get("dominant_class_pct") and target["dominant_class_pct"] > 90:
        findings.append(_finding(
            "imbalance", "class_imbalance", "target distribution share", [target.get("column", "?")], None,
            target["dominant_class_pct"], "warning",
            f"Dominant class is {target['dominant_class_pct']}% of rows",
            "Imbalanced classes can bias models toward the majority class.",
            "Consider class weighting, resampling, or threshold tuning; verify with stratified splits.",
            "statistical"))

    # Correlation / multicollinearity from the correlation matrix.
    corr = profile.get("correlation") or {}
    cols = corr.get("columns") or []
    matrix = corr.get("matrix") or []
    pairs = []
    for i in range(len(matrix)):
        for j in range(i + 1, len(matrix[i])):
            v = matrix[i][j]
            if isinstance(v, (int, float)) and abs(v) >= 0.95:
                pairs.append((cols[i], cols[j], round(v, 3)))
    if pairs:
        findings.append(_finding(
            "multicollinearity", "correlation", "Pearson correlation ≥ 0.95", sorted({p for pair in pairs for p in pair[:2]}),
            None, None, "info",
            "; ".join(f"{a}↔{b} r={r}" for a, b, r in pairs[:5]),
            "Highly correlated features can destabilize some models.",
            "Review correlated pairs; consider dropping or combining redundant features.",
            "statistical"))

    return findings


def severity_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    out = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "info")
        out[sev] = out.get(sev, 0) + 1
    return out
