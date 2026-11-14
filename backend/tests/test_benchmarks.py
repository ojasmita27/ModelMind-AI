"""Benchmark catalog, import and hyperparameter tuning tests."""
import io
import time

P = "/api/v1/projects"


def _project(client, headers):
    r = client.post(P, json={"name": "Bench project"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _wait_profile(client, headers, project_id, dataset_id, version_id, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = client.get(f"{P}/{project_id}/datasets/{dataset_id}/versions/{version_id}", headers=headers)
        if v.status_code == 200 and v.json()["job_status"] in ("completed", "failed"):
            return v.json()
        time.sleep(0.25)
    raise AssertionError("profiling did not finish")


def test_catalog_lists_all_nine_datasets(client, alice):
    r = client.get("/api/v1/benchmarks", headers=alice)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 9
    ids = {i["id"] for i in items}
    assert {
        "breast-cancer-wisconsin", "bank-marketing", "adult-income", "telco-churn",
        "wine-quality-classification", "california-housing", "diabetes",
        "bike-sharing", "wine-quality-regression",
    } <= ids
    for item in items:
        assert item["task_type"] in ("classification", "regression")
        assert item["target_column"]
        assert item["source"] and item["license"] and item["citation"]
        assert "loader" not in item  # internals not exposed


def test_catalog_filters(client, alice):
    r = client.get("/api/v1/benchmarks?task_type=regression", headers=alice)
    assert all(i["task_type"] == "regression" for i in r.json())
    assert len(r.json()) == 4
    r = client.get("/api/v1/benchmarks?search=churn", headers=alice)
    assert [i["id"] for i in r.json()] == ["telco-churn"]
    r = client.get("/api/v1/benchmarks?task_type=bogus", headers=alice)
    assert r.status_code == 422


def test_benchmark_detail_404(client, alice):
    assert client.get("/api/v1/benchmarks/nonexistent", headers=alice).status_code == 404


def test_import_sklearn_benchmark_end_to_end(client, alice):
    """Breast Cancer Wisconsin loads locally via sklearn — real data, real profiling."""
    project = _project(client, alice)
    r = client.post(f"/api/v1/benchmarks/breast-cancer-wisconsin/import?project_id={project['id']}", headers=alice)
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["source"] == "benchmark"
    assert version["version_number"] == 1
    assert version["row_count"] == 569  # real dataset size
    assert version["column_count"] == 31  # 30 features + target

    profiled = _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    assert profiled["job_status"] == "completed", profiled.get("job_error")

    # Duplicate import is rejected.
    r2 = client.post(f"/api/v1/benchmarks/breast-cancer-wisconsin/import?project_id={project['id']}", headers=alice)
    assert r2.status_code == 409


def test_import_requires_project_ownership(client, alice, bob):
    project = _project(client, alice)
    r = client.post(f"/api/v1/benchmarks/breast-cancer-wisconsin/import?project_id={project['id']}", headers=bob)
    assert r.status_code == 404


def test_experiment_with_tuning_persists_params_and_duration(client, alice):
    """Tuning config flows through create -> train -> persisted per-model results."""
    project = _project(client, alice)
    csv_text = (
        "f1,f2,label\n" + "".join(
            f"{i%7},{i%5},{'yes' if i%2 else 'no'}\n" for i in range(60)
        )
    )
    up = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "tuning.csv"},
        files={"file": ("t.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert up.status_code == 201, up.text
    version = up.json()
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])

    payload = {
        "name": "tuned run",
        "dataset_id": version["dataset_id"],
        "dataset_version_id": version["id"],
        "task_type": "classification",
        "target_column": "label",
        "model_names": ["Decision Tree", "KNN"],
        "tuning": {"enabled": True, "n_iter": 3, "cv": 3},
    }
    r = client.post(f"{P}/{project['id']}/experiments", json=payload, headers=alice)
    assert r.status_code == 201, r.text
    exp = r.json()
    assert exp["tuning_config"]["enabled"] is True

    deadline = time.time() + 120
    final = None
    while time.time() < deadline:
        d = client.get(f"{P}/{project['id']}/experiments/{exp['id']}", headers=alice).json()
        if d["status"] in ("completed", "failed"):
            final = d
            break
        time.sleep(0.3)
    assert final and final["status"] == "completed", final and final.get("error")

    ev = client.get(f"{P}/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice).json()
    for m in ev["models"]:
        if m["status"] == "completed":
            assert m["training_duration_ms"] is not None and m["training_duration_ms"] > 0
            # Decision Tree and KNN both have grids -> best_params recorded.
            assert m["best_params"], f"{m['model_name']} missing best_params"


def test_experiment_without_tuning_has_null_params(client, alice):
    project = _project(client, alice)
    csv_text = "x,y\n" + "".join(f"{i},{i*2}\n" for i in range(40))
    up = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "plain.csv"},
        files={"file": ("p.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    version = up.json()
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    r = client.post(
        f"{P}/{project['id']}/experiments",
        json={
            "name": "plain run", "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"], "task_type": "regression",
            "target_column": "y", "model_names": ["Linear Regression"],
        },
        headers=alice,
    )
    exp = r.json()
    deadline = time.time() + 90
    while time.time() < deadline:
        d = client.get(f"{P}/{project['id']}/experiments/{exp['id']}", headers=alice).json()
        if d["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)
    ev = client.get(f"{P}/{project['id']}/experiments/{exp['id']}/evaluation", headers=alice).json()
    m = ev["models"][0]
    assert m["status"] == "completed"
    assert m["best_params"] is None  # no tuning requested
