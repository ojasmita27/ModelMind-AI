"""What-If analysis & counterfactual tests."""
import io
import time

P = "/api/v1/projects"


def _project(client, headers):
    r = client.post(P, json={"name": "WI project"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, headers, project_id, csv_text):
    r = client.post(
        f"{P}/{project_id}/datasets",
        headers=headers,
        data={"name": "wi.csv"},
        files={"file": ("wi.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _wait_version(client, headers, project_id, dataset_id, version_id, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = client.get(f"{P}/{project_id}/datasets/{dataset_id}/versions/{version_id}", headers=headers)
        if v.status_code == 200 and v.json()["job_status"] in ("completed", "failed"):
            return v.json()
        time.sleep(0.25)
    raise AssertionError("profiling did not finish")


def _train(client, headers, project_id, version, task_type, target, models):
    r = client.post(
        f"{P}/{project_id}/experiments",
        json={
            "name": "wi exp", "dataset_id": version["dataset_id"],
            "dataset_version_id": version["id"], "task_type": task_type,
            "target_column": target, "model_names": models,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    exp = r.json()
    deadline = time.time() + 120
    while time.time() < deadline:
        d = client.get(f"{P}/{project_id}/experiments/{exp['id']}", headers=headers).json()
        if d["status"] in ("completed", "failed"):
            return d
        time.sleep(0.3)
    raise AssertionError("experiment did not finish")


CLASSIF_CSV = "f1,f2,cat,label\n" + "".join(
    f"{i%10},{(i*3)%10},{'x' if i%2 else 'y'},{'yes' if i%3==0 else 'no'}\n" for i in range(90)
)
REG_CSV = "a,b,target\n" + "".join(f"{i%8},{(i*5)%9},{i*2 + (i%3)}\n" for i in range(90))


def _wi_url(project_id, exp_id):
    return f"{P}/{project_id}/experiments/{exp_id}/what-if"


def test_whatif_classification_predict_and_schema(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], CLASSIF_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "classification", "label", ["Decision Tree"])
    assert exp["status"] == "completed", exp.get("error")

    s = client.get(f"{_wi_url(project['id'], exp['id'])}/schema", headers=alice)
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["task_type"] == "classification"
    names = {f["name"] for f in body["features"]}
    assert {"f1", "f2", "cat"} <= names and "label" not in names
    f1 = next(f for f in body["features"] if f["name"] == "f1")
    assert f1["type"] == "numeric" and "min" in f1 and "max" in f1
    cat = next(f for f in body["features"] if f["name"] == "cat")
    assert cat["type"] == "categorical" and set(cat["categories"]) == {"x", "y"}

    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": 5, "f2": 3, "cat": "x"}}, headers=alice)
    assert r.status_code == 200, r.text
    out = r.json()["output"]
    assert out["prediction"] in ("yes", "no", True, False, 0, 1) or isinstance(out["prediction"], str)
    assert "probabilities" in out  # DecisionTree predicts proba? No -> may be absent; don't assert


def test_whatif_rejects_invalid_inputs(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], CLASSIF_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "classification", "label", ["Decision Tree"])
    assert exp["status"] == "completed", exp.get("error")

    # Missing feature
    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": 1}}, headers=alice)
    assert r.status_code == 422
    # Unknown feature
    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": 1, "f2": 2, "cat": "x", "hack": 1}}, headers=alice)
    assert r.status_code == 422
    # Invalid categorical
    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": 1, "f2": 2, "cat": "bogus"}}, headers=alice)
    assert r.status_code == 422
    # Non-numeric for numeric
    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": "abc", "f2": 2, "cat": "x"}}, headers=alice)
    assert r.status_code == 422


def test_whatif_regression_predict(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], REG_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "regression", "target", ["Linear Regression"])
    assert exp["status"] == "completed", exp.get("error")

    r = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"a": 3, "b": 4}}, headers=alice)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["output"]["prediction"], (int, float))


def test_counterfactual_classification(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], CLASSIF_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "classification", "label", ["Decision Tree", "Random Forest"])
    assert exp["status"] == "completed", exp.get("error")

    s = client.get(f"{_wi_url(project['id'], exp['id'])}/schema", headers=alice).json()
    classes = [str(c) for c in (s["classes"] or [])]
    assert classes

    feats = {"f1": 0, "f2": 0, "cat": "x"}
    orig = client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": feats}, headers=alice).json()
    orig_pred = str(orig["output"]["prediction"])
    # Pick the OTHER class as the counterfactual goal.
    goal_class = next((c for c in classes if c != orig_pred), classes[-1])

    r = client.post(
        f"{_wi_url(project['id'], exp['id'])}/counterfactual",
        json={"features": feats, "goal": {"class": goal_class}, "n_candidates": 3, "seed": 7},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["goal"]["class"] == goal_class
    assert "model-space" in body["note"] or "not guaranteed" in body["note"]
    assert len(body["counterfactuals"]) <= 3
    for cf in body["counterfactuals"]:
        assert str(cf["prediction"]["prediction"]) == goal_class
        assert cf["changed_features"], "counterfactual must change at least one feature"
        assert 0 <= cf["distance"] <= 1
        assert 0 <= cf["feasibility"] <= 1


def test_counterfactual_immutable_and_validation(client, alice):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], CLASSIF_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "classification", "label", ["Decision Tree"])
    assert exp["status"] == "completed", exp.get("error")

    feats = {"f1": 0, "f2": 0, "cat": "x"}
    s = client.get(f"{_wi_url(project['id'], exp['id'])}/schema", headers=alice).json()
    classes = [str(c) for c in (s["classes"] or [])]
    goal_class = classes[-1]

    r = client.post(
        f"{_wi_url(project['id'], exp['id'])}/counterfactual",
        json={"features": feats, "goal": {"class": goal_class}, "immutable": ["f1", "f2", "cat"], "n_candidates": 5},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # All features immutable -> no mutable features -> no counterfactuals possible.
    assert body["counterfactuals"] == []

    # Invalid goal class
    r = client.post(
        f"{_wi_url(project['id'], exp['id'])}/counterfactual",
        json={"features": feats, "goal": {"class": "nonexistent"}},
        headers=alice,
    )
    assert r.status_code == 422


def test_whatif_ownership_and_unready(client, alice, bob):
    project = _project(client, alice)
    v = _upload(client, alice, project["id"], CLASSIF_CSV)
    _wait_version(client, alice, project["id"], v["dataset_id"], v["id"])
    exp = _train(client, alice, project["id"], v, "classification", "label", ["Decision Tree"])
    assert exp["status"] == "completed"

    assert client.get(f"{_wi_url(project['id'], exp['id'])}/schema", headers=bob).status_code == 404
    assert client.post(f"{_wi_url(project['id'], exp['id'])}/predict", json={"features": {"f1": 1, "f2": 2, "cat": "x"}}, headers=bob).status_code == 404
    assert client.post(f"{_wi_url(project['id'], exp['id'])}/counterfactual", json={"features": {"f1": 1, "f2": 2, "cat": "x"}, "goal": {"class": "yes"}}, headers=bob).status_code == 404
