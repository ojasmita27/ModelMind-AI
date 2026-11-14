"""P1-A: per-model evaluation results, new endpoints, backward compatibility."""
import time
import uuid

import numpy as np
import pandas as pd
import pytest

from app.ml_engine.training import run_experiment
from app.ml_engine.preprocessing import SplitConfig
from tests.test_experiments import upload_dataset


def _wait_terminal(client, headers, project_id, experiment_id, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(
            f"/api/v1/projects/{project_id}/experiments/{experiment_id}", headers=headers
        ).json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.1)
    raise AssertionError("experiment did not reach a terminal status")


def _make_project_with_experiment(client, headers, csv_content, payload_extra=None, name="eval"):
    project = client.post(
        "/api/v1/projects", json={"name": name, "description": "x"}, headers=headers
    ).json()
    version = upload_dataset(client, headers, project["id"], content=csv_content)
    payload = {
        "name": "Eval run",
        "dataset_id": version["dataset_id"],
        "dataset_version_id": version["id"],
        "train_fraction": 0.7,
        "validation_fraction": 0.15,
        "test_fraction": 0.15,
        **(payload_extra or {}),
    }
    exp = client.post(
        f"/api/v1/projects/{project['id']}/experiments", json=payload, headers=headers
    )
    assert exp.status_code == 201, exp.text
    return project, version, exp.json()


CLASSIFICATION_CSV = """age,gender,score,target
25,F,10.5,A
30,M,11.2,B
35,F,12.0,A
40,M,9.8,B
45,F,13.1,A
50,M,10.9,B
55,F,14.2,A
60,M,11.5,B
65,F,15.0,A
70,M,12.3,B
22,M,9.1,A
28,F,10.4,B
33,M,12.8,A
38,F,9.6,B
"""

MULTICLASS_CSV = """x1,x2,target
1,5,cat
2,4,dog
3,6,bird
4,3,cat
5,7,dog
6,2,bird
7,8,cat
8,1,dog
9,9,bird
10,5,cat
2,6,dog
4,4,bird
"""

REGRESSION_CSV = """size,rooms,age,target
1000,2,10,150000
1200,3,20,180000
800,1,5,120000
1500,3,30,220000
900,2,15,140000
2000,4,40,300000
1100,2,25,170000
1800,3,35,250000
"""


def _classif_project(client, headers):
    return _make_project_with_experiment(
        client, headers, CLASSIFICATION_CSV,
        {"task_type": "classification", "target_column": "target",
         "model_names": ["Logistic Regression", "Random Forest"]},
    )


def test_per_model_results_persisted_for_every_candidate(client, alice):
    project, version, exp = _classif_project(client, alice)
    final = _wait_terminal(client, alice, project["id"], exp["id"])
    assert final["status"] == "completed", final.get("error")

    eval_resp = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    )
    assert eval_resp.status_code == 200, eval_resp.text
    body = eval_resp.json()
    assert body["experiment_id"] == exp["id"]
    assert body["task_type"] == "classification"
    assert body["target_column"] == "target"
    assert body["best_model_name"] == final["metrics"].get("best_model_name")

    names = {m["model_name"] for m in body["models"]}
    assert names == {"Logistic Regression", "Random Forest"}
    selected = [m for m in body["models"] if m["is_selected"]]
    assert len(selected) == 1 and selected[0]["model_name"] == body["best_model_name"]


def test_classification_metrics_include_confusion_matrix_and_report(client, alice):
    project, version, exp = _classif_project(client, alice)
    _wait_terminal(client, alice, project["id"], exp["id"])
    body = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    ).json()
    for model in body["models"]:
        vm = model["validation_metrics"]
        for key in ("accuracy", "precision_macro", "recall_macro", "f1_macro"):
            assert key in vm and 0.0 <= vm[key] <= 1.0
        assert model["confusion_matrix"] is not None
        assert "labels" in model["confusion_matrix"]
        assert "matrix" in model["confusion_matrix"]
        assert model["classification_report"] is not None
        # per-class entries exist
        assert any(k not in {"accuracy", "macro avg", "weighted avg"} for k in model["classification_report"])


def test_regression_metrics_include_mse(client, alice):
    project, version, exp = _make_project_with_experiment(
        client, alice, REGRESSION_CSV,
        {"task_type": "regression", "target_column": "target",
         "model_names": ["Linear Regression", "Random Forest"]},
    )
    final = _wait_terminal(client, alice, project["id"], exp["id"])
    assert final["status"] == "completed", final.get("error")

    body = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    ).json()
    assert body["task_type"] == "regression"
    for model in body["models"]:
        vm = model["validation_metrics"]
        for key in ("mae", "mse", "rmse", "r2"):
            assert key in vm
        assert vm["mse"] >= 0
        assert model["confusion_matrix"] is None


def test_multiclass_classification_persists(client, alice):
    project, version, exp = _make_project_with_experiment(
        client, alice, MULTICLASS_CSV,
        {"task_type": "classification", "target_column": "target",
         "model_names": ["Logistic Regression", "Naive Bayes"]},
    )
    final = _wait_terminal(client, alice, project["id"], exp["id"])
    assert final["status"] == "completed", final.get("error")
    body = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    ).json()
    assert len(body["models"]) == 2
    for model in body["models"]:
        cm = model["confusion_matrix"]
        # Small splits may not contain every class; matrix must be square and
        # labels must be a subset of the known classes.
        assert cm is not None and 2 <= len(cm["labels"]) <= 3
        assert len(cm["matrix"]) == len(cm["labels"])
        assert all(len(r) == len(cm["labels"]) for r in cm["matrix"])
        assert set(cm["labels"]) <= {"bird", "dog", "cat"}
        # multiclass: no roc_auc expected in validation metrics
        assert "roc_auc" not in model["validation_metrics"]


def test_model_without_predict_proba_is_handled():
    """A candidate lacking predict_proba must still be evaluated via predict.

    SVC(probability=False) exposes fit/predict/score but no predict_proba.
    """
    from sklearn.svm import SVC

    frame = pd.DataFrame({
        "x": list(range(30)),
        "y": ["a", "b"] * 15,
        "target": ["yes", "no"] * 15,
    })
    import app.ml_engine.models as models_mod

    models_mod.MODEL_CATALOG["classification"]["No Proba SVC"] = {
        "factory": SVC(kernel="linear", probability=False),
        "description": "test",
    }
    try:
        out = run_experiment(
            frame, "target", "classification", ["No Proba SVC"],
            SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15, random_seed=7),
        )
    finally:
        models_mod.MODEL_CATALOG["classification"].pop("No Proba SVC", None)

    entry = out["model_results"][0]
    assert entry["status"] == "completed"
    assert "accuracy" in entry["validation_metrics"]


def test_selection_uses_validation_metrics_not_test(client, alice):
    """is_selected must correspond to argmax validation score across completed models."""
    project, version, exp = _classif_project(client, alice)
    final = _wait_terminal(client, alice, project["id"], exp["id"])
    assert final["status"] == "completed"
    body = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    ).json()
    completed = [m for m in body["models"] if m["status"] == "completed"]

    def val_score(m):
        vm = m["validation_metrics"]
        return vm.get("f1_macro", vm.get("accuracy", 0))

    best_score = max(val_score(m) for m in completed)
    selected = [m for m in body["models"] if m["is_selected"]]
    assert len(selected) == 1
    # Selection is argmax over validation score; exact ties are broken by
    # candidate order, so assert the SCORE, not a specific model name.
    assert val_score(selected[0]) == pytest.approx(best_score)


def test_reproducibility_endpoint(client, alice):
    project, version, exp = _classif_project(client, alice)
    _wait_terminal(client, alice, project["id"], exp["id"])
    resp = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/reproducibility", headers=alice
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["random_seed"] is not None
    assert body["train_fraction"] == pytest.approx(0.7)
    assert body["dataset_sha256"] == version["sha256_checksum"]
    assert set(body["model_configs"].keys()) == {"Logistic Regression", "Random Forest"}
    assert "preprocessing" in body and "fit_scope" in body["preprocessing"]
    # completed experiment -> manifest should be present and verified
    assert body["manifest_available"] is True
    assert body["manifest"]["experiment_id"] == exp["id"]


def test_artifact_endpoint(client, alice):
    project, version, exp = _classif_project(client, alice)
    _wait_terminal(client, alice, project["id"], exp["id"])
    resp = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/artifact", headers=alice
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["available"] is True
    assert body["artifact_uri"].startswith("local://")
    assert body["model_file_size_bytes"] > 0
    assert body["manifest_verified"] is True
    # no filesystem path leakage beyond the local:// URI scheme
    assert "\\" not in body["artifact_uri"] and "/" in body["artifact_uri"]


def test_evaluation_endpoints_reject_other_users(client, alice, bob):
    project, version, exp = _classif_project(client, alice)
    for suffix in ("evaluation", "reproducibility", "artifact"):
        resp = client.get(
            f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/{suffix}", headers=bob
        )
        assert resp.status_code == 404, f"{suffix}: {resp.status_code}"
    # also with a project bob does not own
    resp = client.get(
        f"/api/v1/projects/{uuid.uuid4()}/experiments/{exp['id']}/evaluation", headers=bob
    )
    assert resp.status_code == 404


def test_evaluation_empty_for_experiment_without_results(client, alice):
    """Backward compat: an experiment row with no persisted results returns
    an honest empty model list rather than failing."""
    project, version, exp = _classif_project(client, alice)
    # Immediately after creation the row exists but results may not be written yet.
    resp = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body["models"], list)
    _wait_terminal(client, alice, project["id"], exp["id"])  # let the job finish cleanly
