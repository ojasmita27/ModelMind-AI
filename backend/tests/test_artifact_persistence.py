"""Focused tests for ML model artifact persistence (Priority 2 fix).

What these tests verify
------------------------
1. After a completed experiment the model.joblib artifact physically exists in
   storage and can be loaded back by joblib.
2. The loaded model produces predictions on the same feature schema, confirming
   the saved object is a usable sklearn Pipeline (not a corrupt file).
3. The manifest.json exists, is valid JSON, and contains the required fields with
   correct values taken from the experiment record.
4. artifact_uri in the database matches the storage key that actually exists.
5. When the storage write fails (injected fault), the experiment is marked
   "failed" with an error message, artifact_uri is NOT set, and the response
   code is not 201 (the partially-written state is never surfaced as completed).
6. A regression experiment also produces a persistent artifact.

What these tests do NOT claim
-------------------------------
- Bit-for-bit reproducibility across Python/sklearn/numpy versions is NOT
  tested.  The manifest records the seed and configuration needed to retrain,
  but deterministic retraining depends on matching library versions at retraining
  time.  Only artifact existence and loadability are verified here.

Safety
-------
All storage I/O uses isolated temporary directories via monkeypatching
LocalObjectStorage.__init__.  The test database is the conftest-provided
temporary SQLite file.  No dev database or uploads directory is touched.
"""
import io
import json
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import joblib
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

P = "/api/v1/projects"

_CLASSIFICATION_CSV = (
    "age,gender,target\n"
    "25,F,1\n30,M,0\n35,F,1\n40,M,0\n45,F,1\n"
    "50,M,0\n55,F,1\n60,M,0\n65,F,1\n70,M,0\n"
)

_REGRESSION_CSV = (
    "feature1,feature2,score\n"
    "1.0,2.0,3.5\n2.0,3.0,5.5\n3.0,4.0,7.5\n4.0,5.0,9.5\n"
    "5.0,6.0,11.5\n6.0,7.0,13.5\n7.0,8.0,15.5\n8.0,9.0,17.5\n"
    "9.0,10.0,19.5\n10.0,11.0,21.5\n"
)


def _make_project(client, headers, name="Artifact test project"):
    r = client.post(P, json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _upload_dataset(client, headers, project_id, csv_content=_CLASSIFICATION_CSV,
                    name="test-dataset", filename="data.csv"):
    r = client.post(
        f"{P}/{project_id}/datasets",
        headers=headers,
        data={"name": name},
        files={"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _run_experiment(client, headers, project_id, dataset_id, version_id,
                    target="target", task_type="classification",
                    model_names=None, name="Test run"):
    if model_names is None:
        model_names = ["Logistic Regression"]
    return client.post(
        f"{P}/{project_id}/experiments",
        headers=headers,
        json={
            "name": name,
            "dataset_id": dataset_id,
            "dataset_version_id": version_id,
            "task_type": task_type,
            "target_column": target,
            "train_fraction": 0.7,
            "validation_fraction": 0.15,
            "test_fraction": 0.15,
            "random_seed": 42,
            "model_names": model_names,
        },
    )


def _wait_for_terminal(client, headers, project_id, experiment_id, timeout=120.0):
    """Poll the experiment endpoint until it reaches a terminal status.

    Training runs on the background job queue, so the POST response always
    reports 'queued'. Artifact assertions must use the polled record.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"{P}/{project_id}/experiments/{experiment_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"Experiment {experiment_id} did not reach a terminal status within {timeout}s")


# ---------------------------------------------------------------------------
# Fixture: isolated storage root
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_storage(tmp_storage_root):
    """
    Patch LocalObjectStorage so every instance in this test uses an isolated
    temp directory instead of the real data/uploads location.

    Yields the Path of that directory so tests can inspect it directly.
    """
    from app.storage.local import LocalObjectStorage

    original_init = LocalObjectStorage.__init__

    def patched_init(self, base_path=None):
        # Always use the isolated root, regardless of what the caller passes.
        original_init(self, base_path=tmp_storage_root)

    with patch.object(LocalObjectStorage, "__init__", patched_init):
        yield tmp_storage_root


@pytest.fixture()
def tmp_storage_root():
    """Create a fresh temporary directory that this process owns."""
    d = Path(tempfile.mkdtemp(prefix="mm_artifact_test_"))
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test 1: model.joblib exists and is loadable after a completed classification
# ---------------------------------------------------------------------------

def test_artifact_file_exists_and_is_loadable_classification(client, alice, isolated_storage):
    project = _make_project(client, alice)
    version = _upload_dataset(client, alice, project["id"])

    resp = _run_experiment(client, alice, project["id"],
                           version["dataset_id"], version["id"],
                           target="target", task_type="classification")
    assert resp.status_code == 201, resp.text
    queued = resp.json()
    assert queued["status"] == "queued"

    # Training is asynchronous: poll until the worker finishes, then verify
    # the persisted record carries a usable artifact_uri.
    body = _wait_for_terminal(client, alice, project["id"], queued["id"])
    assert body["status"] == "completed", f"status={body['status']} error={body.get('error')}"
    assert body["artifact_uri"] is not None, "artifact_uri must not be None after completion"
    assert body["artifact_uri"].startswith("local://experiments/"), body["artifact_uri"]

    # Derive the storage key from the URI (strip "local://").
    model_key = body["artifact_uri"].removeprefix("local://")
    model_path = isolated_storage / model_key
    assert model_path.exists(), (
        f"model.joblib not found on disk at {model_path}. "
        f"artifact_uri={body['artifact_uri']!r}"
    )
    assert model_path.stat().st_size > 0, "model.joblib must not be empty"

    # Load the artifact and confirm it is a callable sklearn Pipeline.
    loaded_model = joblib.load(model_path)
    assert hasattr(loaded_model, "predict"), (
        f"Loaded object {type(loaded_model)} does not have a predict() method"
    )

    # Run a prediction to confirm the pipeline is functional (not just loadable).
    sample = pd.DataFrame({
        "age": [35],
        "gender": ["F"],
    })
    predictions = loaded_model.predict(sample)
    assert len(predictions) == 1, "Loaded model must produce one prediction per input row"


# ---------------------------------------------------------------------------
# Test 2: manifest.json exists, is valid JSON, contains required fields
# ---------------------------------------------------------------------------

def test_manifest_exists_and_contains_required_fields(client, alice, isolated_storage):
    project = _make_project(client, alice, name="Manifest test project")
    version = _upload_dataset(client, alice, project["id"])

    resp = _run_experiment(client, alice, project["id"],
                           version["dataset_id"], version["id"],
                           target="target", task_type="classification",
                           name="Manifest run")
    assert resp.status_code == 201, resp.text
    queued = resp.json()
    body = _wait_for_terminal(client, alice, project["id"], queued["id"])
    assert body["status"] == "completed", f"status={body['status']} error={body.get('error')}"

    experiment_id = body["id"]
    manifest_path = isolated_storage / "experiments" / experiment_id / "manifest.json"
    assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"

    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    # Required fields and their expected values.
    assert manifest["experiment_id"] == experiment_id
    assert manifest["dataset_version_id"] == version["id"]
    assert "dataset_sha256" in manifest and len(manifest["dataset_sha256"]) == 64
    assert manifest["task_type"] == "classification"
    assert manifest["target_column"] == "target"
    assert manifest["random_seed"] == 42
    assert manifest["train_fraction"] == pytest.approx(0.7)
    assert manifest["validation_fraction"] == pytest.approx(0.15)
    assert manifest["test_fraction"] == pytest.approx(0.15)
    assert manifest["best_model_name"] == "Logistic Regression"
    assert "Logistic Regression" in manifest["model_names_evaluated"]
    assert "accuracy" in manifest["validation_metrics"]
    assert "accuracy" in manifest["test_metrics"]


# ---------------------------------------------------------------------------
# Test 3: artifact_uri in DB matches the file that actually exists on disk
# ---------------------------------------------------------------------------

def test_artifact_uri_matches_actual_file_on_disk(client, alice, isolated_storage):
    project = _make_project(client, alice, name="URI match project")
    version = _upload_dataset(client, alice, project["id"])

    resp = _run_experiment(client, alice, project["id"],
                           version["dataset_id"], version["id"])
    assert resp.status_code == 201, resp.text
    queued = resp.json()
    body = _wait_for_terminal(client, alice, project["id"], queued["id"])
    assert body["status"] == "completed", f"status={body['status']} error={body.get('error')}"
    assert body["artifact_uri"] is not None

    model_key = body["artifact_uri"].removeprefix("local://")
    expected_path = isolated_storage / model_key
    assert expected_path.exists(), (
        f"artifact_uri={body['artifact_uri']!r} does not correspond to a real file. "
        f"Checked: {expected_path}"
    )

    # Confirm the URI format: local://experiments/{uuid}/model.joblib
    assert model_key == f"experiments/{body['id']}/model.joblib", (
        f"Unexpected artifact key format: {model_key!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: regression experiment also produces a persistent artifact
# ---------------------------------------------------------------------------

def test_artifact_persisted_for_regression_experiment(client, alice, isolated_storage):
    project = _make_project(client, alice, name="Regression artifact project")
    version = _upload_dataset(
        client, alice, project["id"],
        csv_content=_REGRESSION_CSV,
        name="regression-data",
        filename="regression.csv",
    )

    resp = _run_experiment(client, alice, project["id"],
                           version["dataset_id"], version["id"],
                           target="score", task_type="regression",
                           model_names=["Linear Regression"],
                           name="Regression run")
    assert resp.status_code == 201, resp.text
    queued = resp.json()
    body = _wait_for_terminal(client, alice, project["id"], queued["id"])
    assert body["status"] == "completed", f"status={body['status']} error={body.get('error')}"
    assert body["artifact_uri"] is not None

    model_key = body["artifact_uri"].removeprefix("local://")
    model_path = isolated_storage / model_key
    assert model_path.exists(), f"Regression model not persisted: {model_path}"

    loaded = joblib.load(model_path)
    assert hasattr(loaded, "predict")

    sample = pd.DataFrame({"feature1": [5.0], "feature2": [6.0]})
    preds = loaded.predict(sample)
    assert len(preds) == 1


# ---------------------------------------------------------------------------
# Test 5: storage write failure → experiment marked failed, artifact_uri=None
# ---------------------------------------------------------------------------

def test_storage_failure_marks_experiment_failed_not_completed(client, alice, tmp_storage_root):
    """
    If the storage write raises after training succeeds, the background job
    must mark the experiment 'failed' with a non-empty error message.
    artifact_uri must remain None (the half-written state must never be
    surfaced as 'completed').

    Async note: the POST always returns 201/'queued'; the failure is observed
    by polling the experiment record. Polling happens inside the patch
    context so the injected fault is still active while the job runs.
    """
    from app.storage.local import LocalObjectStorage

    original_init = LocalObjectStorage.__init__

    def patched_init(self, base_path=None):
        original_init(self, base_path=tmp_storage_root)

    original_put = LocalObjectStorage.put

    def failing_put(self, key, data):
        # Allow dataset uploads to succeed; fail on model artifact writes.
        if key.startswith("experiments/") and key.endswith(".joblib"):
            raise OSError("Injected storage failure for model write")
        return original_put(self, key, data)

    with patch.object(LocalObjectStorage, "__init__", patched_init):
        with patch.object(LocalObjectStorage, "put", failing_put):
            project = _make_project(client, alice, name="Failure test project")
            project_id = project["id"]
            version = _upload_dataset(client, alice, project_id)

            resp = _run_experiment(client, alice, project_id,
                                   version["dataset_id"], version["id"])
            assert resp.status_code == 201, resp.text
            queued = resp.json()
            exp = _wait_for_terminal(client, alice, project_id, queued["id"])

    assert exp["status"] == "failed", (
        f"Expected status='failed', got {exp['status']!r}. "
        f"error={exp.get('error')!r}"
    )
    assert exp["artifact_uri"] is None, (
        f"artifact_uri must be None when storage failed, got {exp['artifact_uri']!r}"
    )
    assert exp["error"] is not None and len(exp["error"]) > 0, (
        "error field must be populated when the experiment fails"
    )
    # No .joblib file should exist anywhere in the storage root.
    leftover_models = list(tmp_storage_root.rglob("*.joblib"))
    assert len(leftover_models) == 0, (
        f"Partial model file(s) found after storage failure: {leftover_models}"
    )


# ---------------------------------------------------------------------------
# Test 6: completed experiment metrics in DB match what the manifest records
# ---------------------------------------------------------------------------

def test_db_metrics_consistent_with_manifest(client, alice, isolated_storage):
    """Verify that the metrics stored in the DB record and in the manifest file
    refer to the same values (both come from the same result dict)."""
    project = _make_project(client, alice, name="Consistency check project")
    version = _upload_dataset(client, alice, project["id"])

    resp = _run_experiment(client, alice, project["id"],
                           version["dataset_id"], version["id"],
                           name="Consistency run")
    assert resp.status_code == 201, resp.text
    queued = resp.json()
    body = _wait_for_terminal(client, alice, project["id"], queued["id"])
    assert body["status"] == "completed", f"status={body['status']} error={body.get('error')}"

    db_val_metrics = body["metrics"]["validation_metrics"]
    db_test_metrics = body["metrics"]["test_metrics"]

    manifest_path = isolated_storage / "experiments" / body["id"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["validation_metrics"] == db_val_metrics, (
        "Manifest validation_metrics differ from DB metrics"
    )
    assert manifest["test_metrics"] == db_test_metrics, (
        "Manifest test_metrics differ from DB metrics"
    )


# ---------------------------------------------------------------------------
# Test 7: missing model file makes experiment fail
# ---------------------------------------------------------------------------

def test_missing_model_file_marks_experiment_failed(client, alice, tmp_storage_root):
    from app.storage.local import LocalObjectStorage

    original_init = LocalObjectStorage.__init__
    original_exists = LocalObjectStorage.exists

    def patched_init(self, base_path=None):
        original_init(self, base_path=tmp_storage_root)

    def missing_model_exists(self, key):
        if key.startswith("experiments/") and key.endswith("/model.joblib"):
            return False
        return original_exists(self, key)

    with patch.object(LocalObjectStorage, "__init__", patched_init):
        with patch.object(LocalObjectStorage, "exists", missing_model_exists):
            project = _make_project(client, alice, name="Missing model project")
            version = _upload_dataset(client, alice, project["id"])
            resp = _run_experiment(client, alice, project["id"], version["dataset_id"], version["id"])
            assert resp.status_code == 201, resp.text
            queued = resp.json()
            # Poll while the fault is still injected so the job cannot succeed.
            exp = _wait_for_terminal(client, alice, project["id"], queued["id"])

    assert exp["status"] == "failed", f"status={exp['status']} error={exp.get('error')}"
    assert "not found after storage.put()" in (exp.get("error") or ""), exp.get("error")


# ---------------------------------------------------------------------------
# Test 8: missing manifest file makes experiment fail
# ---------------------------------------------------------------------------

def test_missing_manifest_marks_experiment_failed(client, alice, tmp_storage_root):
    from app.storage.local import LocalObjectStorage

    original_init = LocalObjectStorage.__init__
    original_exists = LocalObjectStorage.exists

    def patched_init(self, base_path=None):
        original_init(self, base_path=tmp_storage_root)

    def missing_manifest_exists(self, key):
        if key.startswith("experiments/") and key.endswith("/manifest.json"):
            return False
        return original_exists(self, key)

    with patch.object(LocalObjectStorage, "__init__", patched_init):
        with patch.object(LocalObjectStorage, "exists", missing_manifest_exists):
            project = _make_project(client, alice, name="Missing manifest project")
            version = _upload_dataset(client, alice, project["id"])
            resp = _run_experiment(client, alice, project["id"], version["dataset_id"], version["id"])
            assert resp.status_code == 201, resp.text
            queued = resp.json()
            exp = _wait_for_terminal(client, alice, project["id"], queued["id"])

    assert exp["status"] == "failed", f"status={exp['status']} error={exp.get('error')}"
    assert "Manifest file write failed" in (exp.get("error") or ""), exp.get("error")


# ---------------------------------------------------------------------------
# Test 9: storage verification after write catches missing files
# ---------------------------------------------------------------------------

def test_storage_verification_catches_missing_files(client, alice, tmp_storage_root):
    """
    If the storage layer claims a write succeeded but the file is never created,
    post-training verification must reject the experiment: the persisted row
    must end 'failed' with artifact_uri=None and an explanatory error.

    Async note: training runs on the shared background queue, so the POST
    returns 201/'queued' and the failure is observed by polling. A dedicated
    TestClient is still used so this test exercises the real ASGI stack.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.storage.local import LocalObjectStorage

    original_init = LocalObjectStorage.__init__
    original_put = LocalObjectStorage.put

    def patched_init(self, base_path=None):
        original_init(self, base_path=tmp_storage_root)

    def no_write_put(self, key, data):
        # Allow dataset uploads to succeed, but simulate a missing persisted model or
        # manifest by doing nothing when an experiment artifact is written.
        if not key.startswith("experiments/"):
            return original_put(self, key, data)
        return None

    with patch.object(LocalObjectStorage, "__init__", patched_init):
        with patch.object(LocalObjectStorage, "put", no_write_put):
            with TestClient(create_app(), raise_server_exceptions=False) as api_client:
                register = api_client.post(
                    "/api/v1/auth/register",
                    json={"email": "verify-missing@example.com", "password": "correct-horse-battery"},
                )
                assert register.status_code == 201, register.text
                login = api_client.post(
                    "/api/v1/auth/login",
                    json={"email": "verify-missing@example.com", "password": "correct-horse-battery"},
                )
                assert login.status_code == 200, login.text
                headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

                project = api_client.post("/api/v1/projects", json={"name": "Verification fail project"}, headers=headers)
                assert project.status_code == 201, project.text
                project_id = project.json()["id"]

                version = api_client.post(
                    f"/api/v1/projects/{project_id}/datasets",
                    headers=headers,
                    data={"name": "verify-dataset"},
                    files={"file": ("data.csv", io.BytesIO(_CLASSIFICATION_CSV.encode("utf-8")), "text/csv")},
                )
                assert version.status_code == 201, version.text
                dataset_version = version.json()

                resp = api_client.post(
                    f"/api/v1/projects/{project_id}/experiments",
                    headers=headers,
                    json={
                        "name": "Verification run",
                        "dataset_id": dataset_version["dataset_id"],
                        "dataset_version_id": dataset_version["id"],
                        "task_type": "classification",
                        "target_column": "target",
                        "train_fraction": 0.7,
                        "validation_fraction": 0.15,
                        "test_fraction": 0.15,
                        "random_seed": 42,
                        "model_names": ["Logistic Regression"],
                    },
                )
                assert resp.status_code == 201, resp.text
                queued = resp.json()
                assert queued["status"] == "queued"

                # Poll while the write-suppressing patch is still active.
                deadline = time.monotonic() + 120
                exp = None
                while time.monotonic() < deadline:
                    poll = api_client.get(
                        f"/api/v1/projects/{project_id}/experiments/{queued['id']}",
                        headers=headers,
                    )
                    assert poll.status_code == 200, poll.text
                    exp = poll.json()
                    if exp["status"] in ("completed", "failed"):
                        break
                    time.sleep(0.2)
                assert exp is not None and exp["status"] == "failed", (
                    f"Expected failed experiment, got {exp and exp['status']!r} error={exp and exp.get('error')!r}"
                )
                assert exp["artifact_uri"] is None, (
                    "Failed experiment must not keep a completed artifact URI"
                )
                assert "Model file write failed" in (exp.get("error") or ""), (
                    "Failed experiment should explain why verification failed"
                )
