import io
import time

from app.db.models import Dataset, DatasetVersion
from app.db.session import get_sessionmaker

P = "/api/v1/projects"


def make_project(client, headers, name="Demo project"):
    r = client.post(P, json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def upload_dataset(client, headers, project_id, name="Sales data", description="demo"):
    csv = "customer_id,amount,segment\n1,100,retail\n2,200,retail\n3,300,enterprise\n"
    return client.post(
        f"{P}/{project_id}/datasets",
        headers=headers,
        data={"name": name, "description": description},
        files={"file": ("sales.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )


def test_dataset_upload_and_ownership(client, alice, bob):
    project = make_project(client, alice)
    r = upload_dataset(client, alice, project["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dataset_id"] == body["dataset_id"]
    assert body["job_status"] in {"pending", "processing", "completed", "failed"}

    listing = client.get(f"{P}/{project['id']}/datasets", headers=alice)
    assert listing.status_code == 200
    assert [d["name"] for d in listing.json()] == ["Sales data"]

    other_project = make_project(client, bob)
    other_resp = client.get(f"{P}/{other_project['id']}/datasets", headers=alice)
    assert other_resp.status_code == 404

    missing = client.get(f"{P}/{project['id']}/datasets/{body['dataset_id']}", headers=bob)
    assert missing.status_code == 404


def test_dataset_upload_requires_csv_file_and_validates_name(client, alice):
    project = make_project(client, alice)
    r = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": " "},
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"


def test_dataset_upload_invalid_csv_file_returns_safe_validation_error(client, alice):
    project = make_project(client, alice)
    r = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "Bad file"},
        files={"file": ("notes.txt", io.BytesIO(b"hello world"), "text/plain")},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert "not allowed" in body["error"]["message"].lower()


def test_dataset_preview_returns_real_csv_columns(client, alice):
    project = make_project(client, alice)
    csv = "customer_id,amount,churn\n1,100,yes\n2,200,no\n"
    upload = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "Churn data", "description": "demo"},
        files={"file": ("churn.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert upload.status_code == 201, upload.text

    preview = None
    for _ in range(30):
        preview = client.get(f"{P}/{project['id']}/datasets/{upload.json()['dataset_id']}/preview", headers=alice)
        if preview.status_code == 200:
            break
        time.sleep(0.2)
    assert preview is not None and preview.status_code == 200, preview.text if preview else "preview request never succeeded"
    body = preview.json()
    assert body["columns"] == ["customer_id", "amount", "churn"]
    assert len(body["rows"]) == 1


def test_dataset_row_count_covers_file_larger_than_8kb(client, alice):
    """row_count must count every data row, not just those inside the first 8 KB."""
    project = make_project(client, alice)
    # ~25 bytes/row * 500 rows > 12 KB, well past the old 8192-byte window.
    rows = ["id,note,value"] + [f"{i},{'x' * 15},{i * 1.5}" for i in range(500)]
    csv_bytes = ("\n".join(rows) + "\n").encode("utf-8")
    assert len(csv_bytes) > 8192

    r = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "Big CSV", "description": "demo"},
        files={"file": ("big.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["row_count"] == 500, body
    assert body["column_count"] == 3


def test_dataset_row_count_with_utf8_bom(client, alice):
    project = make_project(client, alice)
    csv_bytes = "\ufeffa,b\n1,2\n3,4\n5,6\n".encode("utf-8")
    r = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "BOM CSV", "description": "demo"},
        files={"file": ("bom.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["row_count"] == 3


def test_dataset_upload_rejects_header_only_and_empty_files(client, alice):
    project = make_project(client, alice)
    for name, payload in (
        ("header-only.csv", b"a,b,c\n"),
        ("empty.csv", b""),
    ):
        r = client.post(
            f"{P}/{project['id']}/datasets",
            headers=alice,
            data={"name": f"Bad {name}", "description": "demo"},
            files={"file": (name, io.BytesIO(payload), "text/csv")},
        )
        assert r.status_code == 422, (name, r.text)
        assert r.json()["error"]["code"] == "validation_error"


def test_dataset_duplicate_csv_returns_conflict_and_keeps_database_consistent(client, alice):
    project = make_project(client, alice)
    csv = "customer_id,amount,segment\n1,100,retail\n2,200,retail\n"

    first = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "Sales data", "description": "demo"},
        files={"file": ("sales.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "Sales data", "description": "demo"},
        files={"file": ("sales.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "conflict"
    assert "already exists" in second.json()["error"]["message"].lower()

    with get_sessionmaker()() as db:
        dataset_count = db.query(Dataset).count()
        version_count = db.query(DatasetVersion).count()
    assert dataset_count == 1
    assert version_count == 1


def test_dataset_upload_allows_distinct_csv_files(client, alice):
    project = make_project(client, alice)

    first = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "A", "description": "demo"},
        files={"file": ("a.csv", io.BytesIO(b"id,value\n1,10\n"), "text/csv")},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{P}/{project['id']}/datasets",
        headers=alice,
        data={"name": "B", "description": "demo"},
        files={"file": ("b.csv", io.BytesIO(b"id,value\n2,20\n"), "text/csv")},
    )
    assert second.status_code == 201, second.text

    listing = client.get(f"{P}/{project['id']}/datasets", headers=alice)
    assert listing.status_code == 200
    assert len(listing.json()) == 2


def test_dataset_duplicate_upload_does_not_expose_other_users_data(client, alice, bob):
    alice_project = make_project(client, alice)
    bob_project = make_project(client, bob)
    csv = "customer_id,amount\n1,100\n"

    first = client.post(
        f"{P}/{alice_project['id']}/datasets",
        headers=alice,
        data={"name": "Alice dataset", "description": "demo"},
        files={"file": ("shared.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert first.status_code == 201, first.text

    duplicate = client.post(
        f"{P}/{bob_project['id']}/datasets",
        headers=bob,
        data={"name": "Bob duplicate", "description": "demo"},
        files={"file": ("shared.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert duplicate.status_code == 409, duplicate.text
    body = duplicate.json()
    assert body["error"]["code"] == "conflict"
    assert "alice" not in body["error"]["message"].lower()
    assert "dataset_id" not in str(body)

    alice_listing = client.get(f"{P}/{alice_project['id']}/datasets", headers=alice)
    assert alice_listing.status_code == 200
    assert len(alice_listing.json()) == 1
