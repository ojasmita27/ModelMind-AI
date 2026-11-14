import uuid

P = "/api/v1/projects"


def make(client, headers, name="Churn study", description="desc"):
    r = client.post(P, json={"name": name, "description": description}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_get(client, alice):
    p = make(client, alice)
    assert p["name"] == "Churn study" and p["description"] == "desc"
    assert uuid.UUID(p["id"])
    r = client.get(f"{P}/{p['id']}", headers=alice)
    assert r.status_code == 200 and r.json() == p


def test_create_trims_whitespace_and_description_optional(client, alice):
    r = client.post(P, json={"name": "  Spaced  "}, headers=alice)
    assert r.status_code == 201
    assert r.json()["name"] == "Spaced" and r.json()["description"] is None


def test_create_validation(client, alice):
    for body in ({"name": ""}, {"name": "   "}, {"name": "x" * 121}, {}, {"name": "ok", "description": "d" * 2001}):
        r = client.post(P, json=body, headers=alice)
        assert r.status_code == 422, body
        assert r.json()["error"]["code"] == "validation_error"


def test_list_only_returns_own_projects_newest_first(client, alice, bob):
    a1 = make(client, alice, "A1")
    a2 = make(client, alice, "A2")
    b1 = make(client, bob, "B1")
    mine = client.get(P, headers=alice).json()
    assert [p["id"] for p in mine] == [a2["id"], a1["id"]]
    assert [p["id"] for p in client.get(P, headers=bob).json()] == [b1["id"]]


def test_list_pagination(client, alice):
    for i in range(5):
        make(client, alice, f"P{i}")
    page1 = client.get(f"{P}?limit=2&offset=0", headers=alice).json()
    page2 = client.get(f"{P}?limit=2&offset=2", headers=alice).json()
    page3 = client.get(f"{P}?limit=2&offset=4", headers=alice).json()
    ids = [p["id"] for p in page1 + page2 + page3]
    assert len(ids) == 5 and len(set(ids)) == 5
    assert client.get(f"{P}?limit=0", headers=alice).status_code == 422
    assert client.get(f"{P}?limit=201", headers=alice).status_code == 422


def test_patch_partial_update(client, alice):
    p = make(client, alice)
    r = client.patch(f"{P}/{p['id']}", json={"name": "Renamed"}, headers=alice)
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed" and r.json()["description"] == "desc"
    assert r.json()["updated_at"] >= p["updated_at"]
    r = client.patch(f"{P}/{p['id']}", json={"description": None}, headers=alice)
    assert r.json()["description"] is None and r.json()["name"] == "Renamed"


def test_patch_validation(client, alice):
    p = make(client, alice)
    assert client.patch(f"{P}/{p['id']}", json={}, headers=alice).status_code == 422
    assert client.patch(f"{P}/{p['id']}", json={"name": None}, headers=alice).status_code == 422
    assert client.patch(f"{P}/{p['id']}", json={"name": ""}, headers=alice).status_code == 422
    assert client.get(f"{P}/{p['id']}", headers=alice).json()["name"] == "Churn study"


def test_delete(client, alice):
    p = make(client, alice)
    r = client.delete(f"{P}/{p['id']}", headers=alice)
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert client.get(f"{P}/{p['id']}", headers=alice).status_code == 404
    assert client.delete(f"{P}/{p['id']}", headers=alice).status_code == 404


def test_missing_project_is_404_with_envelope(client, alice):
    r = client.get(f"{P}/{uuid.uuid4()}", headers=alice)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_malformed_project_id_is_validation_error(client, alice):
    r = client.get(f"{P}/not-a-uuid", headers=alice)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


# ---------------- ownership ----------------

def test_other_users_project_looks_nonexistent(client, alice, bob):
    p = make(client, alice)
    url = f"{P}/{p['id']}"
    other = client.get(f"{P}/{uuid.uuid4()}", headers=bob)  # genuinely missing
    for resp in (
        client.get(url, headers=bob),
        client.patch(url, json={"name": "hacked"}, headers=bob),
        client.delete(url, headers=bob),
    ):
        assert resp.status_code == 404
        assert resp.json() == other.json()  # identical to "does not exist": no existence leak
    # and the owner's data is untouched
    mine = client.get(url, headers=alice).json()
    assert mine["name"] == "Churn study"


def test_all_project_routes_require_auth(client, alice):
    p = make(client, alice)
    url = f"{P}/{p['id']}"
    calls = [
        client.post(P, json={"name": "x"}),
        client.get(P),
        client.get(url),
        client.patch(url, json={"name": "x"}),
        client.delete(url),
    ]
    assert all(c.status_code == 401 for c in calls)
    assert client.get(url, headers=alice).status_code == 200  # still there


def test_client_cannot_set_owner_or_id(client, alice, bob):
    me = client.get("/api/v1/auth/me", headers=bob).json()
    r = client.post(P, json={"name": "mine", "owner_id": me["id"], "id": str(uuid.uuid4())}, headers=alice)
    assert r.status_code == 201
    assert [p["id"] for p in client.get(P, headers=bob).json()] == []
    assert len(client.get(P, headers=alice).json()) == 1


def test_deleting_user_cascades_to_projects(client, alice):
    from sqlalchemy import text
    from app.db.session import get_engine

    make(client, alice)
    with get_engine().begin() as conn:
        conn.execute(text("DELETE FROM users"))
        assert conn.execute(text("SELECT count(*) FROM projects")).scalar() == 0


def test_timestamps_are_timezone_aware_utc(client, alice):
    from datetime import datetime

    p = make(client, alice)
    for key in ("created_at", "updated_at"):
        parsed = datetime.fromisoformat(p[key].replace("Z", "+00:00"))
        assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
