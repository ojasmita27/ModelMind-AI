"""Research Copilot tests: grounded answers, ownership, missing context."""
import io
import time

P = "/api/v1/projects"


def _setup(client, headers):
    r = client.post(P, json={"name": "Copilot project"}, headers=headers)
    assert r.status_code == 201, r.text
    project = r.json()
    csv = "a,b,label\n" + "".join(f"{i%5},{i%3},{'yes' if i%2 else 'no'}\n" for i in range(60))
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
        "name": "exp1", "dataset_id": v["dataset_id"], "dataset_version_id": v["id"],
        "task_type": "classification", "target_column": "label", "model_names": ["Decision Tree"],
    }, headers=headers)
    exp = r.json()
    dl = time.time() + 120
    while time.time() < dl:
        d = client.get(f"{P}/{project['id']}/experiments/{exp['id']}", headers=headers).json()
        if d["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)
    return project, exp


def test_ask_grounded_best_model(client, alice):
    project, _ = _setup(client, alice)
    r = client.post(f"{P}/{project['id']}/copilot/ask",
                    json={"question": "Which model performed best and why?"}, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "exp1" in body["answer"] or "Decision Tree" in body["answer"]
    assert body["evidence"], "grounded answer must cite evidence"
    assert body["mode"] == "grounded_rules"


def test_ask_missing_context(client, alice):
    r = client.post(P, json={"name": "Empty"}, headers=alice)
    project = r.json()
    r = client.post(f"{P}/{project['id']}/copilot/ask",
                    json={"question": "Is my registered model ready for production?"}, headers=alice)
    assert r.status_code == 200
    assert "No registered models" in r.json()["answer"]


def test_ask_validation(client, alice, bob):
    project, _ = _setup(client, alice)
    # empty question
    assert client.post(f"{P}/{project['id']}/copilot/ask", json={"question": ""}, headers=alice).status_code == 422
    # ownership
    assert client.post(f"{P}/{project['id']}/copilot/ask", json={"question": "hi"}, headers=bob).status_code == 404
    assert client.get(f"{P}/{project['id']}/copilot/context", headers=bob).status_code == 404


def test_report_generation(client, alice):
    project, _ = _setup(client, alice)
    r = client.post(f"{P}/{project['id']}/copilot/report", json={}, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    titles = [s["title"] for s in body["sections"]]
    assert "Experiments" in titles and "Limitations" in titles
    exp_section = next(s for s in body["sections"] if s["title"] == "Experiments")
    assert exp_section["status"] == "ok" and "exp1" in exp_section["content"]
