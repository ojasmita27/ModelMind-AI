"""Trust receipt: generation, integrity, reproducibility, immutability."""
import io
import json
import time

P = "/api/v1/projects"


def _train(client, headers):
    r = client.post(P, json={"name": "Trust project"}, headers=headers)
    project = r.json()
    csv = "a,b,label\n" + "".join(f"{i%5},{i%3},{'yes' if i%2 else 'no'}\n" for i in range(60))
    r = client.post(f"{P}/{project['id']}/datasets", headers=headers,
                    data={"name": "t.csv"}, files={"file": ("t.csv", io.BytesIO(csv.encode()), "text/csv")})
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
    assert d["status"] == "completed", d.get("error")
    return project, exp


def test_receipt_generation_and_verify(client, alice):
    project, exp = _train(client, alice)
    r = client.post(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=alice)
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["receipt_id"].startswith("TR-")
    assert len(rec["digest"]) == 64
    p = rec["payload"]
    assert p["dataset"]["available"] and p["dataset"]["sha256_checksum"]
    assert p["dataset"]["file_checksum_verified"] is True
    assert p["artifact"]["exists"] is True and p["artifact"]["sha256"]
    assert p["configuration"]["random_seed"] == 42
    assert p["model_results"] and p["model_results"][0]["model_name"]
    assert "scikit-learn" in p["environment"]["packages"]
    assert p["explainability"]["available"] is True
    assert "shap_treeexplainer" in p["explainability"]["methods"][0]
    assert p["explainability"]["computed_on_demand"] is True

    # Idempotent: second POST returns same receipt.
    r2 = client.post(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=alice)
    assert r2.json()["receipt_id"] == rec["receipt_id"] and r2.json()["already_existed"] is True

    # Verify -> history appended.
    v = client.post(f"{P}/{project['id']}/trust-receipts/{rec['receipt_id']}/verify", headers=alice)
    assert v.status_code == 200, v.text
    ver = v.json()["verification"]
    assert ver["checks"]["payload_digest_match"] is True
    assert ver["checks"]["dataset_checksum_match"] is True
    assert ver["checks"]["artifact_checksum_match"] is True
    assert ver["ok"] is True
    assert len(v.json()["verifications"]) == 1

    # Reproducibility
    rep = client.get(f"{P}/{project['id']}/trust-receipts/{rec['receipt_id']}/reproducibility", headers=alice).json()
    assert rep["status"] in ("reproducible", "partially_reproducible")
    assert all(c["status"] in ("pass", "fail", "unknown") for c in rep["checks"])


def test_receipt_get_and_list(client, alice):
    project, exp = _train(client, alice)
    rec = client.post(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=alice).json()
    g = client.get(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=alice)
    assert g.status_code == 200 and g.json()["receipt_id"] == rec["receipt_id"]
    lst = client.get(f"{P}/{project['id']}/trust-receipts", headers=alice).json()
    assert any(x["receipt_id"] == rec["receipt_id"] for x in lst["receipts"])


def test_receipt_requires_completed(client, alice):
    r = client.post(P, json={"name":"p"}, headers=alice); project = r.json()
    # fake experiment id -> 404 via get_owned_experiment
    import uuid
    r = client.post(f"{P}/{project['id']}/experiments/{uuid.uuid4()}/trust-receipt", headers=alice)
    assert r.status_code == 404


def test_receipt_ownership(client, alice, bob):
    project, exp = _train(client, alice)
    rec = client.post(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=alice).json()
    assert client.get(f"{P}/{project['id']}/experiments/{exp['id']}/trust-receipt", headers=bob).status_code == 404
    assert client.post(f"{P}/{project['id']}/trust-receipts/{rec['receipt_id']}/verify", headers=bob).status_code == 404


def test_canonical_determinism():
    from app.services.trust import _canonical, _digest
    a = {"b": 1, "a": [2, 3]}
    b = {"a": [2, 3], "b": 1}
    assert _canonical(a) == _canonical(b)
    assert _digest(a) == _digest(b)
    assert _digest({**a, "x": 1}) != _digest(a)
