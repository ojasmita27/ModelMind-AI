"""Explainability: global importance + local explanations."""
import io
import time

P = "/api/v1/projects"


def _train_tree(client, headers):
    r = client.post(P, json={"name": "XAI project"}, headers=headers)
    project = r.json()
    csv = "a,b,label\n" + "".join(f"{i%10},{i%7},{'yes' if i%2 else 'no'}\n" for i in range(80))
    r = client.post(f"{P}/{project['id']}/datasets", headers=headers,
                    data={"name": "x.csv"}, files={"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")})
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


def test_global_explain_importance(client, alice):
    project, exp = _train_tree(client, alice)
    r = client.get(f"{P}/{project['id']}/experiments/{exp['id']}/explain/global", headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] in ("shap_treeexplainer", "shap_treeexplainer_transformed", "permutation_importance")
    assert body["importances"], "must return real importances"
    assert body["disclaimer"]
    # every importance is a finite number
    for k, v in body["importances"].items():
        assert isinstance(v, (int, float))


def test_local_explain_contributions(client, alice):
    project, exp = _train_tree(client, alice)
    r = client.post(f"{P}/{project['id']}/experiments/{exp['id']}/explain/local",
                    json={"features": {"a": 5, "b": 3}}, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["method"] == "leave_one_feature_out"
    assert body["prediction"]["prediction"] in ("yes", "no")
    contribs = body["contributions"]
    assert {c["feature"] for c in contribs} == {"a", "b"}
    assert all(0 <= c["delta"] <= 1 for c in contribs)


def test_explain_ownership(client, alice, bob):
    project, exp = _train_tree(client, alice)
    assert client.get(f"{P}/{project['id']}/experiments/{exp['id']}/explain/global", headers=bob).status_code == 404
