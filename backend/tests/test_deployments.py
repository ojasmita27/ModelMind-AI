"""Deployment & prediction API tests."""
import io
import time

P = "/api/v1/projects"


def _setup_trained(client, headers, task="classification", models=None):
    r = client.post(P, json={"name": "Deploy project"}, headers=headers)
    project = r.json()
    if task == "classification":
        csv = "a,b,label\n" + "".join(f"{i%5},{i%3},{'yes' if i%2 else 'no'}\n" for i in range(60))
        target = "label"
    else:
        csv = "a,b,target\n" + "".join(f"{i%5},{i%3},{i*2}\n" for i in range(60))
        target = "target"
    r = client.post(f"{P}/{project['id']}/datasets", headers=headers,
                    data={"name": "d.csv"}, files={"file": ("d.csv", io.BytesIO(csv.encode()), "text/csv")})
    v = r.json()
    dl = time.time() + 40
    while time.time() < dl:
        vv = client.get(f"{P}/{project['id']}/datasets/{v['dataset_id']}/versions/{v['id']}", headers=headers).json()
        if vv["job_status"] in ("completed", "failed"):
            break
        time.sleep(0.25)
    r = client.post(f"{P}/{project['id']}/experiments", json={
        "name": "exp", "dataset_id": v["dataset_id"], "dataset_version_id": v["id"],
        "task_type": task, "target_column": target, "model_names": models or ["Decision Tree" if task == "classification" else "Linear Regression"],
    }, headers=headers)
    exp = r.json()
    dl = time.time() + 120
    while time.time() < dl:
        d = client.get(f"{P}/{project['id']}/experiments/{exp['id']}", headers=headers).json()
        if d["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)
    return project, exp, v


def _to_production(client, headers, pid, exp_id):
    r = client.post(f"{P}/{pid}/models/register", json={"experiment_id": exp_id}, headers=headers)
    assert r.status_code == 201, r.text
    ver = r.json()
    r = client.post(f"{P}/{pid}/models/{ver['model_id']}/versions/{ver['id']}/validate", headers=headers)
    assert r.json()["validation"]["ok"], r.text
    r = client.post(f"{P}/{pid}/models/{ver['model_id']}/versions/{ver['id']}/transition",
                    json={"to_status": "staging"}, headers=headers)
    r = client.post(f"{P}/{pid}/models/{ver['model_id']}/versions/{ver['id']}/transition",
                    json={"to_status": "production"}, headers=headers)
    assert r.status_code == 200, r.text
    return ver


def test_deploy_and_predict_classification(client, alice):
    project, exp, _ = _setup_trained(client, alice)
    ver = _to_production(client, alice, project["id"], exp["id"])

    r = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy",
                    json={}, headers=alice)
    assert r.status_code == 201, r.text
    dep = r.json()
    assert dep["status"] == "active"
    assert dep["model_name"] and dep["version_number"]

    # Duplicate deploy rejected.
    r = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=alice)
    assert r.status_code == 409

    r = client.post(f"{P}/{project['id']}/deployments/{dep['id']}/predict",
                    json={"features": {"a": 1, "b": 2}}, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deployment_id"] == dep["id"]
    assert body["prediction"] in ("yes", "no")
    assert "probabilities" in body
    assert body["duration_ms"] >= 0 and body["request_id"]

    # History persisted.
    h = client.get(f"{P}/{project['id']}/deployments/{dep['id']}/predictions", headers=alice).json()
    assert h["total"] == 1 and h["records"][0]["status"] == "completed"


def test_deploy_rejects_unvalidated(client, alice):
    project, exp, _ = _setup_trained(client, alice)
    # registered only, not production
    r = client.post(f"{P}/{project['id']}/models/register", json={"experiment_id": exp["id"]}, headers=alice)
    ver = r.json()
    r = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=alice)
    assert r.status_code == 409


def test_predict_invalid_and_stopped(client, alice):
    project, exp, _ = _setup_trained(client, alice)
    ver = _to_production(client, alice, project["id"], exp["id"])
    dep = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=alice).json()

    # missing feature
    r = client.post(f"{P}/{project['id']}/deployments/{dep['id']}/predict", json={"features": {"a": 1}}, headers=alice)
    assert r.status_code == 422

    # stop -> predict rejected
    r = client.post(f"{P}/{project['id']}/deployments/{dep['id']}/stop", headers=alice)
    assert r.status_code == 200 and r.json()["status"] == "stopped"
    r = client.post(f"{P}/{project['id']}/deployments/{dep['id']}/predict", json={"features": {"a": 1, "b": 2}}, headers=alice)
    assert r.status_code == 409


def test_predict_regression(client, alice):
    project, exp, _ = _setup_trained(client, alice, task="regression", models=["Linear Regression"])
    ver = _to_production(client, alice, project["id"], exp["id"])
    dep = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=alice).json()
    r = client.post(f"{P}/{project['id']}/deployments/{dep['id']}/predict", json={"features": {"a": 3, "b": 4}}, headers=alice)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["prediction"], (int, float))


def test_deployment_ownership(client, alice, bob):
    project, exp, _ = _setup_trained(client, alice)
    ver = _to_production(client, alice, project["id"], exp["id"])
    dep = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=alice).json()
    assert client.get(f"{P}/{project['id']}/deployments", headers=bob).status_code == 404
    assert client.post(f"{P}/{project['id']}/deployments/{dep['id']}/predict", json={"features": {"a": 1, "b": 2}}, headers=bob).status_code == 404
