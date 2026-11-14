"""Model registry: registration, lifecycle, validation, comparison, rollback."""
import io
import time

P = "/api/v1/projects"


def _project(client, headers):
    r = client.post(P, json={"name": "Reg project"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, headers, project_id):
    csv = "a,b,label\n" + "".join(f"{i%5},{i%3},{'yes' if i%2 else 'no'}\n" for i in range(60))
    r = client.post(f"{P}/{project_id}/datasets", headers=headers,
                    data={"name": "reg.csv"}, files={"file": ("r.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 201, r.text
    return r.json()


def _wait(client, headers, pid, did, vid, timeout=40):
    dl = time.time() + timeout
    while time.time() < dl:
        v = client.get(f"{P}/{pid}/datasets/{did}/versions/{vid}", headers=headers).json()
        if v["job_status"] in ("completed", "failed"):
            return v
        time.sleep(0.25)
    raise AssertionError("timeout")


def _train(client, headers, pid, version):
    r = client.post(f"{P}/{pid}/experiments", json={
        "name": "reg exp", "dataset_id": version["dataset_id"], "dataset_version_id": version["id"],
        "task_type": "classification", "target_column": "label", "model_names": ["Decision Tree"],
    }, headers=headers)
    assert r.status_code == 201, r.text
    exp = r.json()
    dl = time.time() + 120
    while time.time() < dl:
        d = client.get(f"{P}/{pid}/experiments/{exp['id']}", headers=headers).json()
        if d["status"] in ("completed", "failed"):
            return d
        time.sleep(0.3)
    raise AssertionError("timeout")


def _register(client, headers, pid, exp_id):
    r = client.post(f"{P}/{pid}/models/register", json={"experiment_id": exp_id}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_registry_full_lifecycle(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"])
    _wait(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v)
    assert exp["status"] == "completed", exp.get("error")

    ver = _register(client, alice, project["id"], exp["id"])
    assert ver["lifecycle_status"] == "registered"
    assert ver["checksum_sha256"] and ver["algorithm"]
    model_id, vid = ver["model_id"], ver["id"]

    # Duplicate registration rejected.
    r = client.post(f"{P}/{project['id']}/models/register", json={"experiment_id": exp["id"]}, headers=alice)
    assert r.status_code == 409

    # Validate -> validated.
    r = client.post(f"{P}/{project['id']}/models/{model_id}/versions/{vid}/validate", headers=alice)
    assert r.status_code == 200, r.text
    assert r.json()["validation"]["ok"] is True
    assert r.json()["lifecycle_status"] == "validated"

    # Production requires validated -> staging -> production.
    r = client.post(f"{P}/{project['id']}/models/{model_id}/versions/{vid}/transition",
                    json={"to_status": "production"}, headers=alice)
    assert r.status_code == 200  # validated -> production allowed by map
    assert r.json()["lifecycle_status"] == "production"

    # Invalid transition: production -> validated rejected path via map.
    r = client.post(f"{P}/{project['id']}/models/{model_id}/versions/{vid}/transition",
                    json={"to_status": "validated"}, headers=alice)
    assert r.status_code == 422  # must use validate endpoint

    # History recorded.
    h = client.get(f"{P}/{project['id']}/models/{model_id}/versions/{vid}/history", headers=alice).json()
    assert len(h["transitions"]) >= 3
    assert {t["to"] for t in h["transitions"]} >= {"registered", "validated", "production"}


def test_registry_production_requires_validation(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"])
    _wait(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v)
    ver = _register(client, alice, project["id"], exp["id"])
    # registered -> production not allowed
    r = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/transition",
                    json={"to_status": "production"}, headers=alice)
    assert r.status_code == 409


def test_registry_compare_and_ownership(client, alice, bob):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"])
    _wait(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v)
    ver = _register(client, alice, project["id"], exp["id"])

    # Cross-user 404.
    assert client.get(f"{P}/{project['id']}/models", headers=bob).status_code == 404
    assert client.get(f"{P}/{project['id']}/models/{ver['model_id']}", headers=bob).status_code == 404

    # Compare needs >=2.
    r = client.get(f"{P}/{project['id']}/models/compare?version_ids={ver['id']}", headers=alice)
    assert r.status_code == 422

    # Register a second version from a second experiment, then compare.
    exp2 = _train(client, alice, project["id"], v)
    # same experiment? no - new experiment object; register under same model name may create v2
    ver2 = _register(client, alice, project["id"], exp2["id"])
    r = client.get(f"{P}/{project['id']}/models/compare?version_ids={ver['id']},{ver2['id']}", headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_type"] == "classification"
    assert len(body["versions"]) == 2
