"""Dataset intelligence findings endpoint tests."""
import io
import time

P = "/api/v1/projects"


def _make_dataset(client, headers, name, csv):
    r = client.post(P, json={"name": name}, headers=headers)
    project = r.json()
    r = client.post(f"{P}/{project['id']}/datasets", headers=headers,
                    data={"name": "d.csv"}, files={"file": ("d.csv", io.BytesIO(csv.encode()), "text/csv")})
    v = r.json()
    dl = time.time() + 40
    while time.time() < dl:
        vv = client.get(f"{P}/{project['id']}/datasets/{v['dataset_id']}/versions/{v['id']}", headers=headers).json()
        if vv["job_status"] in ("completed", "failed"):
            break
        time.sleep(0.25)
    assert vv["job_status"] == "completed", vv.get("job_error")
    return project, v


def _findings(client, headers, project, v, target=None):
    qs = f"?target_column={target}" if target else ""
    r = client.get(f"{P}/{project['id']}/datasets/{v['dataset_id']}/versions/{v['id']}/findings{qs}", headers=headers)
    return r


def test_findings_detects_defects(client, alice):
    csv = "id,num,cat,label\n"
    for i in range(120):
        missing = "" if i % 10 == 0 else str(i)
        outlier = "99999" if i == 5 else str(i % 50)
        dup = "7" if i % 40 == 0 else str(i % 3)
        csv += f"{i},{missing},{outlier},{dup},{'yes' if i % 20 else 'no'}\n"
    csv += "119,,7,7,no\n"  # exact duplicate row variant
    project, v = _make_dataset(client, alice, "P", csv)
    r = _findings(client, alice, project, v, target="label")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] >= 120
    cats = {f["category"] for f in body["findings"]}
    assert "missing_values" in cats
    assert "class_imbalance" in cats
    assert "leakage_indicator" in cats  # id column is all-unique
    for f in body["findings"]:
        assert f["method"] and f["explanation"] and f["recommendation"]
        assert f["severity"] in ("critical", "warning", "info")
        assert "confidence" in f


def test_findings_constant_and_cardinality(client, alice):
    rows = ["c,k,label"] + [f"same,cat{i%150},x" for i in range(120)]
    project, v = _make_dataset(client, alice, "P2", "\n".join(rows))
    r = _findings(client, alice, project, v)
    assert r.status_code == 200
    cats = {f["category"] for f in r.json()["findings"]}
    assert "constant_feature" in cats
    assert "high_cardinality" in cats


def test_findings_ownership_and_404(client, alice, bob):
    project, v = _make_dataset(client, alice, "P3", "a,b\n1,x\n2,y\n3,x\n")
    assert _findings(client, bob, project, v).status_code == 404
    assert client.get(f"{P}/{project['id']}/datasets/{v['dataset_id']}/versions/00000000-0000-0000-0000-000000000000/findings", headers=alice).status_code in (404, 422)


def test_findings_clean_dataset(client, alice):
    csv = "a,b,label\n" + "".join(f"{i},{i*2},{'p' if i%2 else 'n'}\n" for i in range(50))
    project, v = _make_dataset(client, alice, "P4", csv)
    r = _findings(client, alice, project, v)
    assert r.status_code == 200
    body = r.json()
    # no missing/outliers/duplicates/constant on clean data; imbalance may appear (50/50 is fine)
    bad = {f["category"] for f in body["findings"]} & {"missing_values", "duplicates", "constant_feature", "outliers"}
    assert not bad, body["findings"]
