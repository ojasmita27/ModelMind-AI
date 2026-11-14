from __future__ import annotations

from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

# Optional dependency: included only when installed.
try:
    from xgboost import XGBClassifier, XGBRegressor

    _XGBOOST_AVAILABLE = True
except Exception:  # pragma: no cover - depends on environment
    _XGBOOST_AVAILABLE = False

MODEL_CATALOG: dict[str, dict[str, object]] = {
    "classification": {
        "Logistic Regression": {"factory": LogisticRegression(max_iter=500, multi_class="auto", n_jobs=None)},
        "Decision Tree": {"factory": DecisionTreeClassifier(random_state=42)},
        "Random Forest": {"factory": RandomForestClassifier(n_estimators=200, random_state=42)},
        "Gradient Boosting": {"factory": GradientBoostingClassifier(random_state=42)},
        "SVM": {"factory": SVC(probability=True, random_state=42)},
        "KNN": {"factory": KNeighborsClassifier()},
        "Naive Bayes": {"factory": GaussianNB()},
    },
    "regression": {
        "Linear Regression": {"factory": LinearRegression()},
        "Decision Tree": {"factory": DecisionTreeRegressor(random_state=42)},
        "Random Forest": {"factory": RandomForestRegressor(n_estimators=300, random_state=42)},
        "Gradient Boosting": {"factory": GradientBoostingRegressor(random_state=42)},
        "SVR": {"factory": SVR()},
        "KNN": {"factory": KNeighborsRegressor()},
    },
}

if _XGBOOST_AVAILABLE:
    MODEL_CATALOG["classification"]["XGBoost"] = {"factory": XGBClassifier(random_state=42, eval_metric="logloss")}
    MODEL_CATALOG["regression"]["XGBoost"] = {"factory": XGBRegressor(random_state=42)}

# Small randomized-search grids per model name. Only models listed here are
# tunable; others train with default hyperparameters.
PARAM_GRIDS: dict[str, dict[str, list]] = {
    "Logistic Regression": {"C": [0.01, 0.1, 1.0, 10.0], "penalty": ["l2"]},
    "Decision Tree": {"max_depth": [3, 5, 8, None], "min_samples_split": [2, 5, 10]},
    "Random Forest": {"n_estimators": [50, 100, 200], "max_depth": [3, 8, None], "min_samples_split": [2, 5]},
    "Gradient Boosting": {"n_estimators": [50, 100, 200], "learning_rate": [0.03, 0.1, 0.3], "max_depth": [3, 5]},
    "SVM": {"C": [0.1, 1.0, 10.0], "kernel": ["rbf", "linear"]},
    "KNN": {"n_neighbors": [3, 5, 11], "weights": ["uniform", "distance"]},
    "SVR": {"C": [0.1, 1.0, 10.0], "kernel": ["rbf", "linear"], "epsilon": [0.01, 0.1, 0.5]},
}


def get_param_grid(task_type: str, model_name: str) -> dict[str, list] | None:
    """Return the search grid for a model, or None when not tunable."""
    return PARAM_GRIDS.get(model_name)


def get_model_candidates(task_type: str, names: list[str]) -> list[tuple[str, object]]:
    """Resolve model names to (name, estimator) pairs, preserving request order.

    Raises ValueError if the task type is unknown or ANY requested name is not
    in the catalog — unknown names must never be silently dropped, because a
    positional zip against a filtered list would misattribute results.
    """
    if task_type not in MODEL_CATALOG:
        raise ValueError(f"Unknown task type '{task_type}'. Expected one of: {', '.join(MODEL_CATALOG)}")
    choices = MODEL_CATALOG[task_type]
    unknown = [name for name in names if name not in choices]
    if unknown:
        raise ValueError(
            f"Unknown model(s) for task '{task_type}': {', '.join(unknown)}. "
            f"Valid options: {', '.join(choices)}"
        )
    return [(name, choices[name]["factory"]) for name in names]
