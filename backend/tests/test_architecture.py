"""Enforces the layering rule: ML code and interface definitions stay framework-free."""
import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = {"fastapi", "starlette", "sqlalchemy", "mlflow", "alembic"}


def imported_roots(path: Path) -> set[str]:
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_ml_engine_and_interfaces_do_not_import_web_or_db_frameworks():
    files = list((APP / "ml_engine").rglob("*.py")) + list((APP / "extensions").rglob("*.py")) + [APP / "interfaces.py"]
    assert files
    for f in files:
        assert not (imported_roots(f) & FORBIDDEN), f"{f.relative_to(APP)} imports a forbidden framework"


def test_interfaces_module_defines_expected_seams():
    from app import interfaces

    for name in ("ObjectStorage", "DatasetProfiler", "ExperimentRunner", "ArtifactStore", "ExperimentTracker", "ExperimentSnapshot"):
        assert hasattr(interfaces, name)
    snap = interfaces.ExperimentSnapshot("e1", "dv1", "sha", "classification", "y", ("a", "b"))
    assert snap.random_seed == 42  # reproducibility: a seed is always part of the snapshot
