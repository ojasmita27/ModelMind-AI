import threading
import time
import uuid

import pandas as pd
import pytest

from app.ml_engine.preprocessing import SplitConfig, split_frame
from app.ml_engine.training import run_experiment


def upload_dataset(client, headers, project_id, name="demo", content=None):
    csv_content = content or """age,gender,target\n25,F,1\n30,M,0\n35,F,1\n40,M,0\n45,F,1\n50,M,0\n55,F,1\n60,M,0\n65,F,1\n70,M,0\n"""
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        data={"name": name, "description": "Demo dataset"},
        files={"file": ("demo.csv", csv_content, "text/csv")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_list_experiment(client, alice):
    project = client.post(
        "/api/v1/projects",
        json={"name": "Experiment project", "description": "For ML runs"},
        headers=alice,
    ).json()

    version = upload_dataset(client, alice, project["id"])
    dataset_id = version["dataset_id"]

    response = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Baseline classifier",
            "dataset_id": dataset_id,
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "target",
            "train_fraction": 0.7,
            "validation_fraction": 0.15,
            "test_fraction": 0.15,
            "model_names": ["Logistic Regression", "Random Forest"],
        },
        headers=alice,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Baseline classifier"
    assert body["project_id"] == project["id"]
    assert body["status"] in {"queued", "running", "completed", "failed"}

    listed = client.get(f"/api/v1/projects/{project['id']}/experiments", headers=alice)
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == body["id"]


def test_experiment_requires_dataset_ownership(client, alice, bob):
    project_a = client.post(
        "/api/v1/projects",
        json={"name": "A", "description": "A"},
        headers=alice,
    ).json()
    project_b = client.post(
        "/api/v1/projects",
        json={"name": "B", "description": "B"},
        headers=bob,
    ).json()

    dataset = upload_dataset(client, alice, project_a["id"], name="shared")
    response = client.post(
        f"/api/v1/projects/{project_b['id']}/experiments",
        json={
            "name": "Bad run",
            "dataset_id": dataset["dataset_id"],
            "dataset_version_id": dataset["id"],
            "task_type": "classification",
            "target_column": "target",
            "model_names": ["Logistic Regression"],
        },
        headers=bob,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_experiment_detail_requires_project_ownership(client, alice, bob):
    """User B must not read User A's experiment even with both UUIDs (IDOR regression)."""
    project_a = client.post(
        "/api/v1/projects",
        json={"name": "A", "description": "A"},
        headers=alice,
    ).json()
    version = upload_dataset(client, alice, project_a["id"], name="shared")
    created = client.post(
        f"/api/v1/projects/{project_a['id']}/experiments",
        json={
            "name": "Private run",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "target",
            "model_names": ["Logistic Regression"],
        },
        headers=alice,
    )
    assert created.status_code == 201, created.text
    experiment_id = created.json()["id"]

    detail = client.get(
        f"/api/v1/projects/{project_a['id']}/experiments/{experiment_id}",
        headers=bob,
    )
    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "not_found"

    # The owner still sees their own experiment.
    own = client.get(
        f"/api/v1/projects/{project_a['id']}/experiments/{experiment_id}",
        headers=alice,
    )
    assert own.status_code == 200
    assert own.json()["id"] == experiment_id


def test_experiment_rejects_unknown_model_names(client, alice):
    project = client.post(
        "/api/v1/projects",
        json={"name": "Model validation", "description": "x"},
        headers=alice,
    ).json()
    version = upload_dataset(client, alice, project["id"], content="a,b\n1,2\n3,4\n")

    response = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Bad models",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "a",
            "model_names": ["Logistic Regression", "Not A Model"],
        },
        headers=alice,
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "Not A Model" in body["error"]["message"]

    # No experiment row may be created for a rejected request.
    listed = client.get(f"/api/v1/projects/{project['id']}/experiments", headers=alice)
    assert listed.status_code == 200
    assert listed.json() == []


def test_model_candidates_are_strict_and_name_aligned():
    from app.ml_engine.models import get_model_candidates

    pairs = get_model_candidates("classification", ["Random Forest", "Logistic Regression"])
    assert [name for name, _ in pairs] == ["Random Forest", "Logistic Regression"]

    with pytest.raises(ValueError, match="Unknown model"):
        get_model_candidates("classification", ["Logistic Regression", "Bogus"])
    with pytest.raises(ValueError, match="Unknown task type"):
        get_model_candidates("clustering", ["Logistic Regression"])


def test_run_experiment_rejects_model_name_mismatch():
    frame = pd.DataFrame(
        {
            "feature": [1, 2, 3, 4, 5, 6, 7, 8],
            "label": ["a", "b", "a", "b", "a", "b", "a", "b"],
        }
    )
    with pytest.raises(ValueError, match="Unknown model"):
        run_experiment(frame, "label", "classification", ["Linear Regression"], SplitConfig(0.7, 0.15, 0.15))


def test_experiment_target_must_exist_in_dataset(client, alice):
    project = client.post(
        "/api/v1/projects",
        json={"name": "Target test", "description": "x"},
        headers=alice,
    ).json()
    version = upload_dataset(client, alice, project["id"], content="a,b\n1,2\n3,4\n")
    response = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Missing target",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "missing",
            "model_names": ["Logistic Regression"],
        },
        headers=alice,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_split_frame_removes_missing_targets_before_training():
    frame = pd.DataFrame(
        {
            "age": [25, 32, 44, 51, 60],
            "segment": ["A", "B", "A", "B", "A"],
            "churn": ["yes", None, "no", "yes", "no"],
        }
    )

    train_x, val_x, test_x, train_y, val_y, test_y = split_frame(
        frame,
        "churn",
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15),
    )

    assert len(train_x) + len(val_x) + len(test_x) == 4
    assert not train_y.isna().any()
    assert not val_y.isna().any()
    assert not test_y.isna().any()
    assert set(train_y.unique()) <= {"yes", "no"}


def test_run_experiment_handles_missing_features_and_categorical_columns():
    frame = pd.DataFrame(
        {
            "age": [25, 30, None, 45, 60, 75, 80, 55],
            "plan": ["basic", "pro", None, "basic", "pro", "pro", "basic", "pro"],
            "region": ["us", "eu", "us", "eu", "us", "eu", "us", "eu"],
            "churn": ["yes", "no", "yes", "no", "yes", "no", "yes", "no"],
        }
    )

    result = run_experiment(
        frame,
        "churn",
        "classification",
        ["Logistic Regression"],
        SplitConfig(train_fraction=0.7, validation_fraction=0.15, test_fraction=0.15),
    )

    assert result["best_model_name"] == "Logistic Regression"
    assert "accuracy" in result["validation_metrics"]
    assert "f1_macro" in result["validation_metrics"]


def test_experiment_create_returns_queued_before_training_finishes(client, alice, monkeypatch):
    project = client.post(
        "/api/v1/projects",
        json={"name": "Async project", "description": "x"},
        headers=alice,
    ).json()
    version = upload_dataset(client, alice, project["id"])

    original = __import__("app.services.experiments", fromlist=["run_experiment"]).run_experiment

    def slow_run(*args, **kwargs):
        time.sleep(1.5)
        return original(*args, **kwargs)

    monkeypatch.setattr("app.services.experiments.run_experiment", slow_run)

    started = time.perf_counter()
    response = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Async run",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "target",
            "train_fraction": 0.7,
            "validation_fraction": 0.15,
            "test_fraction": 0.15,
            "model_names": ["Logistic Regression"],
        },
        headers=alice,
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 201, response.text
    assert response.json()["status"] == "queued"
    assert elapsed < 0.75, f"response took too long: {elapsed:.2f}s"


def test_experiment_status_transitions_and_failure_is_persisted(client, alice, monkeypatch):
    project = client.post(
        "/api/v1/projects",
        json={"name": "Failure project", "description": "x"},
        headers=alice,
    ).json()
    version = upload_dataset(client, alice, project["id"])

    def fail_run(*args, **kwargs):
        raise RuntimeError("training exploded")

    monkeypatch.setattr("app.services.experiments.run_experiment", fail_run)

    response = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Broken run",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "target",
            "train_fraction": 0.7,
            "validation_fraction": 0.15,
            "test_fraction": 0.15,
            "model_names": ["Logistic Regression"],
        },
        headers=alice,
    )
    assert response.status_code == 201, response.text
    experiment_id = response.json()["id"]

    deadline = time.time() + 5
    while time.time() < deadline:
        poll = client.get(f"/api/v1/projects/{project['id']}/experiments/{experiment_id}", headers=alice)
        body = poll.json()
        if body["status"] == "failed":
            assert "training exploded" in body["error"]
            break
        time.sleep(0.1)
    else:
        pytest.fail("Experiment never reached failed status")


def test_duplicate_experiment_job_enqueue_is_ignored(client, alice):
    from app.jobs import get_job_queue

    job_queue = get_job_queue()
    queue_before = len(job_queue._queue)
    job_queue.enqueue("duplicate-job", lambda: None)
    job_queue.enqueue("duplicate-job", lambda: None)
    assert len(job_queue._queue) == queue_before + 1


def test_split_frame_rejects_single_class_targets_and_invalid_splits():
    frame = pd.DataFrame({"value": [1, 2, 3, 4], "target": ["yes", "yes", "yes", "yes"]})
    with pytest.raises(ValueError, match="at least 2 classes"):
        split_frame(frame, "target", SplitConfig(0.7, 0.15, 0.15))

    with pytest.raises(ValueError, match="must add up to 1.0"):
        split_frame(frame, "target", SplitConfig(0.5, 0.2, 0.2))


def test_split_frame_rejects_all_missing_targets():
    frame = pd.DataFrame({"value": [1, 2, 3, 4], "target": [None, None, None, None]})
    with pytest.raises(ValueError, match="missing target labels"):
        split_frame(frame, "target", SplitConfig(0.7, 0.15, 0.15))


def test_run_experiment_rejects_continuous_numeric_target_for_classification():
    frame = pd.DataFrame(
        {
            "age": [21, 24, 26, 29, 31, 33, 35, 38],
            "score": [0.1, 0.4, 0.7, 1.2, 1.4, 1.8, 2.3, 2.9],
            "segment": ["A", "B", "A", "B", "A", "B", "A", "B"],
        }
    )

    with pytest.raises(ValueError, match="continuous.*classification|discrete.*classification|categorical"):
        run_experiment(frame, "score", "classification", ["Logistic Regression"], SplitConfig(0.7, 0.15, 0.15))


def test_run_experiment_rejects_categorical_target_for_regression():
    frame = pd.DataFrame(
        {
            "age": [21, 24, 26, 29, 31, 33, 35, 38],
            "segment": ["A", "B", "A", "B", "A", "B", "A", "B"],
            "amount": [10, 12, 11, 18, 16, 17, 19, 20],
        }
    )

    with pytest.raises(ValueError, match="numeric.*regression|categorical.*regression|Regression requires"):
        run_experiment(frame, "segment", "regression", ["Linear Regression"], SplitConfig(0.7, 0.15, 0.15))


def test_run_experiment_rejects_insufficient_class_samples_for_classification():
    frame = pd.DataFrame(
        {
            "feature": [1, 2, 3, 4, 5],
            "label": ["yes", "yes", "yes", "yes", "no"],
        }
    )

    with pytest.raises(ValueError, match="at least 2 samples|class samples|sufficient"):
        run_experiment(frame, "label", "classification", ["Logistic Regression"], SplitConfig(0.7, 0.15, 0.15))
