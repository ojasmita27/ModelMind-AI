"""CSV data profiling using pandas."""
import csv
import io
from dataclasses import dataclass
from typing import Any, BinaryIO


@dataclass
class ColumnProfile:
    """Profile for a single column."""
    name: str
    type: str  # "numeric", "categorical", "datetime", "text"
    missing_count: int
    missing_percentage: float
    unique_count: int
    sample_values: list[str]


@dataclass
class ProfileResult:
    """Result of profiling a dataset."""
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    duplicate_row_count: int
    duplicate_row_percentage: float
    constant_columns: list[str]
    warnings: list[str]


class CSVProfiler:
    """Profile CSV files using pandas."""

    @staticmethod
    def _normalize_numeric(series):
        import pandas as pd
        return pd.to_numeric(series, errors="raise")

    def __init__(self, max_rows: int = 100000, random_seed: int = 42) -> None:
        self.max_rows = max_rows
        self.random_seed = random_seed

    def profile(self, file: BinaryIO, file_path: str) -> ProfileResult:
        """Profile a CSV file.

        Args:
            file: Binary file object to read from
            file_path: Storage path for the file (for error messages)

        Returns:
            ProfileResult with statistics and warnings
        """
        import pandas as pd

        # Read CSV with pandas
        try:
            df = pd.read_csv(file, nrows=self.max_rows)
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")

        if df.empty:
            raise ValueError("Dataset is empty after reading")

        row_count = len(df)
        column_count = len(df.columns)

        # Profile each column
        columns = []
        constant_columns = []
        warnings = []

        for col in df.columns:
            col_name = str(col)
            col_data = df[col]

            # Determine type
            col_type = self._infer_type(col_data)

            # Missing values
            missing_count = col_data.isna().sum()
            missing_pct = (missing_count / row_count) * 100 if row_count > 0 else 0

            # Unique values
            unique_count = col_data.nunique()

            # Sample values (up to 5)
            sample_values = []
            non_null = col_data.dropna()
            if len(non_null) > 0:
                samples = non_null.head(5).astype(str).tolist()
                sample_values = [s[:100] for s in samples]  # Truncate long strings

            column_profile = ColumnProfile(
                name=col_name,
                type=col_type,
                missing_count=int(missing_count),
                missing_percentage=round(missing_pct, 2),
                unique_count=int(unique_count),
                sample_values=sample_values,
            )
            columns.append(column_profile)

            # Check for constant column
            if unique_count == 1 and missing_count == 0:
                constant_columns.append(col_name)

            # Warnings
            if col_type == "numeric" and unique_count == row_count:
                warnings.append(f"Column '{col_name}' has all unique values - possible identifier")

            if col_type == "categorical" and unique_count > 100:
                warnings.append(f"Column '{col_name}' has {unique_count} unique categories - high cardinality")

            if missing_pct > 50:
                warnings.append(f"Column '{col_name}' has {missing_pct:.1f}% missing values")

        # Check for duplicate rows
        duplicate_count = df.duplicated().sum()
        duplicate_pct = (duplicate_count / row_count) * 100 if row_count > 0 else 0

        if duplicate_count > 0:
            warnings.append(f"Dataset contains {duplicate_count} duplicate rows ({duplicate_pct:.1f}%)")

        # Check for class imbalance in categorical columns
        for col in columns:
            if col.type == "categorical" and col.unique_count > 1 and col.unique_count <= 50:
                col_data = df[col.name]
                value_counts = col_data.value_counts(normalize=True)
                if value_counts.max() > 0.9:
                    warnings.append(
                        f"Column '{col.name}' is imbalanced: dominant class represents {value_counts.max()*100:.1f}%"
                    )

        return ProfileResult(
            row_count=row_count,
            column_count=column_count,
            columns=columns,
            duplicate_row_count=int(duplicate_count),
            duplicate_row_percentage=round(duplicate_pct, 2),
            constant_columns=constant_columns,
            warnings=warnings,
        )

    def _infer_type(self, series) -> str:
        """Infer the type of a pandas Series."""
        import pandas as pd

        try:
            pd.to_numeric(series, errors="raise")
            return "numeric"
        except (ValueError, TypeError):
            pass

        try:
            pd.to_datetime(series, errors="raise")
            return "datetime"
        except (ValueError, TypeError):
            pass

        # Check if categorical (low cardinality relative to row count)
        unique_ratio = series.nunique() / len(series) if len(series) > 0 else 0
        if unique_ratio < 0.5 or series.nunique() <= 50:
            return "categorical"

        return "text"
