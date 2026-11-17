"""Dataset intelligence, cleaning workbench and preprocessing config tests."""
import io
import time

import pytest

P = "/api/v1/projects"

CSV = (
    "id,amount,segment,when,score\n"
    "1,10.5,A,2024-01-01,1\n"
    "2,20.0,A,2024-01-02,2\n"
    "3,,B,2024-01-03,3\n"
    "4,40.0,B,2024-01-04,4\n"
    "5,50.0,A,2024-01-05,5\n"
    "6,60.0,B,2024-01-06,6\n"
    "7,70.0,A,2024-01-07,7\n"
    "8,80.0,B,2024-01-08,8\n"
    "9,90.0,A,2024-01-09,9\n"
    "10,100.0,B,2024-01-10,10\n"
    "11,110.0,A,2024-01-11,11\n"
    "12,120.0,B,2024-01-12,12\n"
)


def _project(client, headers):
    r = client.post(P, json={"name": "Intel project"}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, headers, project_id, csv_text=CSV):
    r = client.post(
        f"{P}/{project_id}/datasets",
        headers=headers,
        data={"name": "intel.csv"},
        files={"file": ("intel.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _wait_profile(client, headers, project_id, dataset_id, version_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        v = client.get(f"{P}/{project_id}/datasets/{dataset_id}/versions/{version_id}", headers=headers)
        assert v.status_code == 200, v.text
        if v.json()["job_status"] in ("completed", "failed"):
            return v.json()
        time.sleep(0.2)
    raise AssertionError("profiling job did not finish")


def _intel_url(project_id, dataset_id, version_id):
    return f"{P}/{project_id}/datasets/{dataset_id}/versions/{version_id}"


def test_intelligence_endpoint_returns_real_stats(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    v = _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    assert v["job_status"] == "completed"

    r = client.get(f"{_intel_url(project['id'], version['dataset_id'], version['id'])}/intelligence", headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["row_count"] == 12
    assert body["column_count"] == 5
    assert 0 <= body["quality_score"] <= 100
    assert "quality_criteria" in body and "warnings" in body

    cols = {c["name"]: c for c in body["columns"]}
    assert cols["amount"]["type"] == "numeric"
    assert cols["amount"]["stats"]["mean"] == pytest.approx(68.227, abs=0.01)  # 750.5 / 11 non-null
    assert cols["amount"]["missing_count"] == 1
    assert cols["segment"]["type"] == "categorical"
    assert cols["id"]["is_identifier"] is True
    assert body["correlation"]["columns"] == ["id", "amount", "score"]


def test_intelligence_target_distribution_and_imbalance(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    r = client.get(
        f"{_intel_url(project['id'], version['dataset_id'], version['id'])}/intelligence?target_column=segment",
        headers=alice,
    )
    assert r.status_code == 200, r.text
    target = r.json()["target"]
    assert target["column"] == "segment"
    assert target["class_count"] == 2
    assert target["distribution"]["A"] == 6
    assert "imbalance_ratio" in target


def test_clean_preview_does_not_persist(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    base = _intel_url(project["id"], version["dataset_id"], version["id"])

    ops = {"drop_columns": ["id"], "missing": {"strategy": "numeric_median"}, "drop_duplicates": True}
    r = client.post(f"{base}/clean-preview", json=ops, headers=alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" not in body["columns"]
    assert body["shape_before"]["columns"] == 5
    assert body["shape_after"]["columns"] == 4
    assert any("Imputed" in line for line in body["transformation_log"])

    # No new version was created by the preview.
    versions = client.get(f"{P}/{project['id']}/datasets/{version['dataset_id']}/versions", headers=alice)
    assert len(versions.json()) == 1


def test_clean_creates_new_version_and_preserves_source(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    base = _intel_url(project["id"], version["dataset_id"], version["id"])

    ops = {
        "rename_columns": {"amount": "value"},
        "missing": {"strategy": "numeric_median"},
        "drop_duplicates": True,
        "scale": {"method": "standard"},
    }
    r = client.post(f"{base}/clean", json=ops, headers=alice)
    assert r.status_code == 201, r.text
    new_v = r.json()
    assert new_v["version_number"] == 2
    assert new_v["source"] == "cleaned"
    assert new_v["derived_from_version_id"] == version["id"]
    assert new_v["transformation_log"]

    # Source version untouched.
    src = client.get(f"{base}", headers=alice).json()
    assert src["version_number"] == 1 and src["source"] == "upload"

    # New version profiles and previews independently.
    _wait_profile(client, alice, project["id"], version["dataset_id"], new_v["id"])
    pv = client.get(f"{_intel_url(project['id'], version['dataset_id'], new_v['id'])}/preview?offset=0&limit=5", headers=alice)
    assert pv.status_code == 200, pv.text
    assert "value" in pv.json()["columns"]
    assert "amount" not in pv.json()["columns"]


def test_clean_rejects_empty_result_and_bad_ops(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    base = _intel_url(project["id"], version["dataset_id"], version["id"])

    r = client.post(f"{base}/clean", json={"drop_columns": ["id", "amount", "segment", "when", "score"]}, headers=alice)
    assert r.status_code == 422


def test_intelligence_and_clean_require_ownership(client, alice, bob):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    base = _intel_url(project["id"], version["dataset_id"], version["id"])

    assert client.get(f"{base}/intelligence", headers=bob).status_code == 404
    assert client.post(f"{base}/clean-preview", json={}, headers=bob).status_code == 404
    assert client.post(f"{base}/clean", json={}, headers=bob).status_code == 404
    assert client.get(f"{base}/preview?offset=0&limit=5", headers=bob).status_code == 404


def test_paginated_preview_offsets(client, alice):
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])
    base = _intel_url(project["id"], version["dataset_id"], version["id"])

    page1 = client.get(f"{base}/preview?offset=0&limit=5", headers=alice).json()
    page2 = client.get(f"{base}/preview?offset=5&limit=5", headers=alice).json()
    assert page1["total_rows"] == 12
    assert len(page1["rows"]) == 5 and len(page2["rows"]) == 5
    assert page1["rows"][0]["id"] == "1"
    assert page2["rows"][0]["id"] == "6"
    assert page2["has_more"] is True
    assert client.get(f"{base}/preview?offset=0&limit=0", headers=alice).status_code == 422


def test_experiment_accepts_and_persists_preprocessing_config(client, alice):
    """Preprocessing config is stored on the experiment and echoed back."""
    project = _project(client, alice)
    version = _upload(client, alice, project["id"])
    _wait_profile(client, alice, project["id"], version["dataset_id"], version["id"])

    payload = {
        "name": "preproc exp",
        "dataset_id": version["dataset_id"],
        "dataset_version_id": version["id"],
        "task_type": "regression",
        "target_column": "score",
        "model_names": ["Linear Regression"],
        "preprocessing": {"numeric_impute": "mean", "numeric_scale": "minmax"},
    }
    r = client.post(f"{P}/{project['id']}/experiments", json=payload, headers=alice)
    assert r.status_code == 201, r.text
    body = r.json()
    # User values win; documented defaults are merged in for reproducibility.
    pc = body["preprocessing_config"]
    assert pc["numeric_impute"] == "mean" and pc["numeric_scale"] == "minmax"
    assert pc["categorical_encode"] == "onehot"

    detail = client.get(f"{P}/{project['id']}/experiments/{body['id']}", headers=alice)
    assert detail.status_code == 200
    assert detail.json()["preprocessing_config"]["numeric_scale"] == "minmax"
