from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


@dataclass
class SplitConfig:
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    random_seed: int = 42


def validate_split_config(config: SplitConfig) -> None:
    total = config.train_fraction + config.validation_fraction + config.test_fraction
    if abs(total - 1.0) > 1e-6:
        raise ValueError("train, validation, and test fractions must add up to 1.0")
    if min(config.train_fraction, config.validation_fraction, config.test_fraction) <= 0:
        raise ValueError("all split fractions must be greater than zero")


def _looks_like_discrete_numeric(series: pd.Series) -> bool:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.empty or numeric.isna().any():
        return False
    if len(pd.unique(numeric)) < 2:
        return False
    if not np.allclose(numeric.to_numpy(), np.round(numeric.to_numpy())):
        return False
    return True


def validate_task_target(frame: pd.DataFrame, target: str, task_type: str) -> None:
    if target not in frame.columns:
        raise ValueError(f"Target column '{target}' not found in dataset")
    labels = frame[target]
    if labels.isna().all():
        raise ValueError(
            f"Target column '{target}' contains only missing target labels. Remove rows with missing target values before training."
        )

    non_missing = labels.dropna()
    if task_type == "classification":
        if pd.api.types.is_numeric_dtype(non_missing):
            numeric_labels = pd.to_numeric(non_missing, errors="coerce")
            if numeric_labels.isna().any():
                raise ValueError(
                    f"Classification target '{target}' contains non-numeric values. Choose a categorical/discrete label column or switch the task type to regression."
                )
            if not _looks_like_discrete_numeric(numeric_labels):
                raise ValueError(
                    f"Target column '{target}' is a continuous numeric field. Classification requires a discrete target with a small number of classes; choose a categorical label column or switch the task type to regression."
                )
            class_counts = pd.Series(numeric_labels).value_counts()
            if class_counts.min() < 2:
                raise ValueError(
                    f"Classification target '{target}' does not have enough class samples to create valid train/validation/test splits. Each class should contain at least 2 rows."
                )
            if class_counts.size > 20:
                raise ValueError(
                    f"Target column '{target}' has {class_counts.size} distinct labels. Classification targets should stay discrete with a small number of classes for a stable default workflow."
                )
            return

        unique_classes = pd.unique(non_missing)
        if len(unique_classes) < 2:
            raise ValueError(
                f"Target column '{target}' has fewer than 2 classes after removing missing labels. Classification requires at least 2 classes."
            )
        class_counts = non_missing.value_counts()
        if class_counts.min() < 2:
            raise ValueError(
                f"Classification target '{target}' does not have enough class samples to create valid train/validation/test splits. Each class should contain at least 2 rows."
            )
        if class_counts.size > 20:
            raise ValueError(
                f"Target column '{target}' has {class_counts.size} distinct labels. Classification targets should stay discrete with a small number of classes for a stable default workflow."
            )
        return

    if task_type == "regression":
        if not pd.api.types.is_numeric_dtype(non_missing):
            raise ValueError(
                f"Regression requires a numeric target column. Target '{target}' is categorical/discrete; choose a numeric outcome column or switch the task type to classification."
            )
        numeric_labels = pd.to_numeric(non_missing, errors="coerce")
        if numeric_labels.isna().any():
            raise ValueError(
                f"Regression target '{target}' contains non-numeric values. Remove or encode non-numeric labels before training a regression model."
            )


def split_frame(
    frame: pd.DataFrame,
    target: str,
    config: SplitConfig,
    task_type: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    validate_split_config(config)
    if target not in frame.columns:
        raise ValueError(f"Target column '{target}' not found in dataset")

    working = frame.copy()
    labels = working[target]
    missing_target_mask = labels.isna()
    if missing_target_mask.all():
        raise ValueError(
            f"Target column '{target}' contains only missing target labels. Remove rows with missing target values before training."
        )
    if missing_target_mask.any():
        working = working.loc[~missing_target_mask].copy()
        labels = working[target]

    if working.empty:
        raise ValueError(f"Dataset is empty after removing missing target labels from '{target}'.")
    if len(working) < 3:
        raise ValueError(
            f"Dataset is too small after removing missing target values from '{target}'. Need at least 3 rows to create train/validation/test splits."
        )

    task_kind = task_type or ("classification" if not pd.api.types.is_numeric_dtype(labels.dropna()) else "regression")
    validate_task_target(working, target, task_kind)

    target_values = labels.dropna()
    inferred_classification = task_kind == "classification"
    if inferred_classification:
        unique_classes = pd.unique(target_values)
        if len(unique_classes) < 2:
            raise ValueError(
                f"Target column '{target}' has fewer than 2 classes after removing missing labels. Classification requires at least 2 classes."
            )

    shuffled = working.sample(frac=1.0, random_state=config.random_seed).reset_index(drop=True)
    features = shuffled.drop(columns=[target])
    labels = shuffled[target]

    train_end = int(len(shuffled) * config.train_fraction)
    val_end = train_end + int(len(shuffled) * config.validation_fraction)
    if train_end <= 0 or len(shuffled) - val_end < 0:
        raise ValueError(
            "Dataset is too small for the requested train/validation/test split. Increase the row count or adjust the split fractions."
        )

    train_x = features.iloc[:train_end]
    val_x = features.iloc[train_end:val_end]
    test_x = features.iloc[val_end:]

    train_y = labels.iloc[:train_end]
    val_y = labels.iloc[train_end:val_end]
    test_y = labels.iloc[val_end:]
    return train_x, val_x, test_x, train_y, val_y, test_y


def _imputer_for(kind: str, strategy: str | None, constant):
    """Build a SimpleImputer honoring a user-selected strategy."""
    if strategy == "mean":
        return SimpleImputer(strategy="mean")
    if strategy == "constant":
        return SimpleImputer(strategy="constant", fill_value=constant if constant is not None else 0)
    if strategy == "most_frequent":
        return SimpleImputer(strategy="most_frequent")
    # default / "median" for numeric, most_frequent fallback for categorical
    return SimpleImputer(strategy="median" if kind == "numeric" else "most_frequent")


def build_preprocessor(X: pd.DataFrame, config: dict | None = None) -> ColumnTransformer:
    """Build the feature preprocessor.

    ``config`` (all optional, stored on the experiment for reproducibility):
      numeric_impute: "median" | "mean" | "constant"
      numeric_constant: fill value for constant imputation
      numeric_scale: "standard" | "minmax" | "none"
      categorical_impute: "most_frequent" | "constant"
      categorical_constant: fill value
      categorical_encode: "onehot" | "ordinal"
    Defaults preserve the original behavior exactly.
    """
    config = config or {}
    numeric_features = X.select_dtypes(include=["number"]).columns.tolist()
    categorical_features = [column for column in X.columns if column not in numeric_features]

    transformers: list[tuple[str, Pipeline | object, list[str]]] = []
    if numeric_features:
        steps = [
            ("imputer", _imputer_for("numeric", config.get("numeric_impute"), config.get("numeric_constant"))),
        ]
        scale = config.get("numeric_scale", "standard")
        if scale == "minmax":
            from sklearn.preprocessing import MinMaxScaler

            steps.append(("scaler", MinMaxScaler()))
        elif scale != "none":
            steps.append(("scaler", StandardScaler()))
        transformers.append(("numeric", Pipeline(steps), numeric_features))
    if categorical_features:
        if config.get("categorical_encode") == "ordinal":
            from sklearn.preprocessing import OrdinalEncoder

            transformers.append(
                (
                    "categorical",
                    Pipeline(
                        [
                            ("imputer", _imputer_for("categorical", config.get("categorical_impute"), config.get("categorical_constant"))),
                            ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
                        ]
                    ),
                    categorical_features,
                )
            )
        else:
            transformers.append(
                (
                    "categorical",
                    Pipeline(
                        [
                            ("imputer", _imputer_for("categorical", config.get("categorical_impute"), config.get("categorical_constant"))),
                            ("encoder", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    categorical_features,
                )
            )

    if not transformers:
        raise ValueError("No usable columns were found for training")

    return ColumnTransformer(transformers=transformers, remainder="drop")
