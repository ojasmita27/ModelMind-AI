"""P1-B/C/D: artifact lifecycle, project file cleanup, dataset-delete safety."""
import time
import uuid

import pytest

from app.db.session import get_sessionmaker
from app.db.models import Experiment, ExperimentModelResult
from app.storage.local import LocalObjectStorage
from app.services.experiments import cleanup_experiment_artifacts
from sqlalchemy import select
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


def _project_with_completed_experiment(client, headers):
    project = client.post(
        "/api/v1/projects", json={"name": "Lifecycle", "description": "x"}, headers=headers
    ).json()
    version = upload_dataset(client, headers, project["id"])
    exp = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Lifecycle run",
            "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"],
            "task_type": "classification",
            "target_column": "target",
            "train_fraction": 0.7,
            "validation_fraction": 0.15,
            "test_fraction": 0.15,
            "model_names": ["Logistic Regression"],
        },
        headers=headers,
    )
    assert exp.status_code == 201, exp.text
    final = _wait_terminal(client, headers, project["id"], exp.json()["id"])
    assert final["status"] == "completed", final.get("error")
    return project, version, exp.json()


# ---------------------------------------------------------------- P1-B

def test_experiment_delete_removes_artifacts(client, alice):
    project, version, exp = _project_with_completed_experiment(client, alice)
    storage = LocalObjectStorage()
    prefix = f"experiments/{exp['id']}/"
    assert storage.list_keys(prefix), "expected model.joblib + manifest.json on disk"

    resp = client.delete(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}", headers=alice
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    assert storage.list_keys(prefix) == [], "artifact files must be gone"

    # row + model results gone
    db = get_sessionmaker()()
    assert db.get(Experiment, uuid.UUID(exp["id"])) is None
    assert list(db.scalars(select(ExperimentModelResult).where(ExperimentModelResult.experiment_id == uuid.UUID(exp["id"])))) == []


def test_experiment_delete_is_owner_scoped(client, alice, bob):
    project, version, exp = _project_with_completed_experiment(client, alice)
    resp = client.delete(
        f"/api/v1/projects/{project['id']}/experiments/{exp['id']}", headers=bob
    )
    assert resp.status_code == 404
    # artifacts untouched
    assert LocalObjectStorage().list_keys(f"experiments/{exp['id']}/")


def test_cleanup_never_touches_other_experiments(client, alice):
    project, version, exp = _project_with_completed_experiment(client, alice)
    storage = LocalObjectStorage()
    other_prefix = f"experiments/{uuid.uuid4()}/"
    storage.put(f"{other_prefix}model.joblib", __import__("io").BytesIO(b"x"))

    cleanup_experiment_artifacts(storage, uuid.UUID(exp["id"]))
    assert storage.exists(f"{other_prefix}model.joblib"), "unrelated artifacts must survive"
    storage.delete_prefix(other_prefix)


def test_cleanup_missing_files_is_safe():
    storage = LocalObjectStorage()
    report = cleanup_experiment_artifacts(storage, uuid.uuid4())
    assert report["deleted"] == 0 and report["failed"] == 0


def test_cleanup_rejects_traversal():
    storage = LocalObjectStorage()
    with pytest.raises(Exception):
        storage.delete_prefix("../outside/")
    with pytest.raises(Exception):
        storage.list_keys("/etc/")


def test_failed_training_cleans_partial_artifacts(client, alice, monkeypatch):
    """A run that wrote artifacts then failed must not leave them behind."""
    import app.services.experiments as svc
    project = client.post("/api/v1/projects", json={"name": "Fail", "description": "x"}, headers=alice).json()
    version = upload_dataset(client, alice, project["id"])

    real_run = svc.run_experiment

    def explode_after_artifacts(*a, **k):
        # simulate failure after training by raising inside the job
        raise RuntimeError("simulated mid-run failure")

    monkeypatch.setattr(svc, "run_experiment", explode_after_artifacts)
    exp = client.post(
        f"/api/v1/projects/{project['id']}/experiments",
        json={
            "name": "Will fail", "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"], "task_type": "classification",
            "target_column": "target", "train_fraction": 0.7,
            "validation_fraction": 0.15, "test_fraction": 0.15,
            "model_names": ["Logistic Regression"],
        },
        headers=alice,
    )
    assert exp.status_code == 201
    final = _wait_terminal(client, alice, project["id"], exp.json()["id"])
    assert final["status"] == "failed"
    assert "simulated mid-run failure" in (final.get("error") or "")
    # no artifact dir should exist for this experiment
    assert LocalObjectStorage().list_keys(f"experiments/{exp.json()['id']}/") == []
    monkeypatch.setattr(svc, "run_experiment", real_run)


# ---------------------------------------------------------------- P1-C

def test_project_delete_removes_dataset_files_and_artifacts(client, alice):
    project, version, exp = _project_with_completed_experiment(client, alice)
    storage = LocalObjectStorage()
    ds_key = version["file_path"] if "file_path" in version else None
    # file_path comes from dataset detail, not version payload; find via storage listing
    dataset_files = storage.list_keys(f"datasets/{version['dataset_id']}/")
    assert dataset_files, "expected uploaded CSV on disk"
    assert storage.list_keys(f"experiments/{exp['id']}/")

    resp = client.delete(f"/api/v1/projects/{project['id']}", headers=alice)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is True
    assert body["cleanup"]["dataset_files_deleted"] >= 1
    assert body["cleanup"]["artifact_files_deleted"] >= 1
    assert storage.list_keys(f"datasets/{version['dataset_id']}/") == []
    assert storage.list_keys(f"experiments/{exp['id']}/") == []


def test_project_delete_missing_files_still_succeeds(client, alice):
    project = client.post("/api/v1/projects", json={"name": "Empty", "description": "x"}, headers=alice).json()
    resp = client.delete(f"/api/v1/projects/{project['id']}", headers=alice)
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


def test_project_delete_is_owner_scoped(client, alice, bob):
    project, version, exp = _project_with_completed_experiment(client, alice)
    resp = client.delete(f"/api/v1/projects/{project['id']}", headers=bob)
    assert resp.status_code == 404
    assert LocalObjectStorage().list_keys(f"experiments/{exp['id']}/")


# ---------------------------------------------------------------- P1-D

def test_dataset_delete_preserves_experiment_history(client, alice):
    project, version, exp = _project_with_completed_experiment(client, alice)
    exp_id = exp["id"]

    resp = client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{version['dataset_id']}", headers=alice
    )
    assert resp.status_code in (200, 204), resp.text

    # experiment row + metrics + model results must survive
    got = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp_id}", headers=alice
    )
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["status"] == "completed"
    assert body["dataset_id"] is None
    assert body["dataset_version_id"] is None
    assert body["metrics"]["best_model_name"]

    ev = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp_id}/evaluation", headers=alice
    )
    assert ev.status_code == 200
    assert len(ev.json()["models"]) == 1

    rep = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp_id}/reproducibility", headers=alice
    )
    assert rep.status_code == 200
    assert rep.json()["dataset_sha256"] is None  # version deleted -> honest null

    art = client.get(
        f"/api/v1/projects/{project['id']}/experiments/{exp_id}/artifact", headers=alice
    )
    assert art.status_code == 200
    assert art.json()["available"] is True  # artifacts are independent of dataset files


def test_experiments_list_survives_dataset_delete(client, alice):
    project, version, exp = _project_with_completed_experiment(client, alice)
    client.delete(f"/api/v1/projects/{project['id']}/datasets/{version['dataset_id']}", headers=alice)
    listed = client.get(f"/api/v1/projects/{project['id']}/experiments", headers=alice)
    assert listed.status_code == 200
    assert any(e["id"] == exp["id"] for e in listed.json())


def test_dataset_delete_cross_user_still_404(client, alice, bob):
    project, version, exp = _project_with_completed_experiment(client, alice)
    resp = client.delete(
        f"/api/v1/projects/{project['id']}/datasets/{version['dataset_id']}", headers=bob
    )
    assert resp.status_code == 404
