"""Monitoring: drift stats, health, labels, performance, ownership."""
import io
import time

import numpy as np
import pytest

from app.services.monitoring import psi

P = "/api/v1/projects"


def test_psi_identical_and_shifted():
    a = np.random.default_rng(0).normal(0, 1, 500)
    assert abs(psi(a, a.copy())) < 0.05
    b = np.random.default_rng(1).normal(3, 1, 500)  # shifted
    assert psi(a, b) > 0.25


def _deploy(client, headers):
    r = client.post(P, json={"name": "Mon project"}, headers=headers)
    project = r.json()
    csv = "a,b,label\n" + "".join(f"{i%10},{i%7},{'yes' if i%2 else 'no'}\n" for i in range(120))
    r = client.post(f"{P}/{project['id']}/datasets", headers=headers,
                    data={"name": "m.csv"}, files={"file": ("m.csv", io.BytesIO(csv.encode()), "text/csv")})
    v = r.json()
    dl = time.time() + 40
    while time.time() < dl:
        vv = client.get(f"{P}/{project['id']}/datasets/{v['dataset_id']}/versions/{v['id']}", headers=headers).json()
        if vv["job_status"] in ("completed", "failed"):
            break
        time.sleep(0.25)
    r = client.post(f"{P}/{project['id']}/experiments", json={
        "name": "exp", "dataset_id": v["dataset_id"], "dataset_version_id": v["id"],
        "task_type": "classification", "target_column": "label", "model_names": ["Decision Tree"],
    }, headers=headers)
    exp = r.json()
    dl = time.time() + 120
    while time.time() < dl:
        d = client.get(f"{P}/{project['id']}/experiments/{exp['id']}", headers=headers).json()
        if d["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)
    # register -> validate -> staging -> production -> deploy
    r = client.post(f"{P}/{project['id']}/models/register", json={"experiment_id": exp["id"]}, headers=headers)
    ver = r.json()
    client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/validate", headers=headers)
    client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/transition", json={"to_status": "staging"}, headers=headers)
    client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/transition", json={"to_status": "production"}, headers=headers)
    dep = client.post(f"{P}/{project['id']}/models/{ver['model_id']}/versions/{ver['id']}/deploy", json={}, headers=headers).json()
    return project, dep


def _predict_many(client, headers, pid, dep_id, n, a_range=(0, 10)):
    rids = []
    for i in range(n):
        a = a_range[0] + (i % (a_range[1] - a_range[0] + 1))
        r = client.post(f"{P}/{pid}/deployments/{dep_id}/predict",
                        json={"features": {"a": a, "b": i % 7}}, headers=headers)
        assert r.status_code == 200, r.text
        rids.append(r.json()["request_id"])
    return rids


def test_monitoring_insufficient_samples(client, alice):
    project, dep = _deploy(client, alice)
    base = f"{P}/{project['id']}/deployments/{dep['id']}/monitoring"
    _predict_many(client, alice, project["id"], dep["id"], 5)
    r = client.post(f"{base}/run", json={}, headers=alice)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "insufficient_data"
    assert body["health_status"] == "insufficient_data"


def test_monitoring_drift_and_labels(client, alice):
    project, dep = _deploy(client, alice)
    base = f"{P}/{project['id']}/deployments/{dep['id']}/monitoring"
    # In-distribution predictions (a in 0..9 matches training range).
    rids = _predict_many(client, alice, project["id"], dep["id"], 35)
    r = client.post(f"{base}/run", json={}, headers=alice)
    body = r.json()
    assert body["status"] == "completed"
    assert body["sample_count"] == 35
    feats = {f["feature"]: f for f in body["summary"]["features"]}
    assert "a" in feats and feats["a"]["type"] == "numeric"
    assert "psi" in feats["a"]

    # Ingest labels for first 10 predictions, then performance should be measured.
    labels = [{"request_id": rid, "label": "yes" if i % 2 == 0 else "no"} for i, rid in enumerate(rids[:10])]
    r = client.post(f"{base}/labels", json={"labels": labels}, headers=alice)
    assert r.json()["added"] == 10
    # duplicates skipped
    r = client.post(f"{base}/labels", json={"labels": labels[:3]}, headers=alice)
    assert r.json()["skipped_duplicates"] == 3
    # unknown request id rejected
    r = client.post(f"{base}/labels", json={"labels": [{"request_id": "bogus", "label": "x"}]}, headers=alice)
    assert r.status_code == 422

    # Second run picks up performance via labels on overlapping window? Window = all records;
    # performance matches labels within window.
    r = client.post(f"{base}/run", json={}, headers=alice)
    body = r.json()
    perf = body["summary"].get("performance", {})
    # 10 labels < 5? matched=10 >=5 -> measured
    assert perf.get("status") == "measured", perf
    assert "accuracy" in perf and "f1" in perf


def test_monitoring_drift_detected(client, alice):
    project, dep = _deploy(client, alice)
    base = f"{P}/{project['id']}/deployments/{dep['id']}/monitoring"
    # Reference 'a' ranges 0..9; send shifted values 50..59 -> PSI should be high.
    rids = _predict_many(client, alice, project["id"], dep["id"], 35, a_range=(50, 59))
    r = client.post(f"{base}/run", json={}, headers=alice)
    body = r.json()
    assert body["status"] == "completed"
    feats = {f["feature"]: f for f in body["summary"]["features"]}
    assert feats["a"]["psi"] is not None and feats["a"]["psi"] > 0.25
    assert body["health_status"] in ("warning", "critical")


def test_monitoring_ownership_and_config(client, alice, bob):
    project, dep = _deploy(client, alice)
    base = f"{P}/{project['id']}/deployments/{dep['id']}/monitoring"
    assert client.get(f"{base}/config", headers=bob).status_code == 404
    assert client.post(f"{base}/run", json={}, headers=bob).status_code == 404

    # Config update
    r = client.put(f"{base}/config", json={"thresholds": {"psi_warning": 0.2}}, headers=alice)
    assert r.status_code == 200 and r.json()["thresholds"]["psi_warning"] == 0.2
    r = client.put(f"{base}/config", json={"thresholds": {"psi_warning": 99}}, headers=alice)
    assert r.status_code == 422
