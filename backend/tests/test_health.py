def test_health_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "up"}


def test_liveness_does_not_need_database(client):
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_request_id_header_and_security_header(client):
    r = client.get("/api/v1/health/live")
    assert len(r.headers["x-request-id"]) >= 8
    assert r.headers["x-content-type-options"] == "nosniff"


def test_safe_incoming_request_id_is_echoed_unsafe_is_replaced(client):
    assert client.get("/api/v1/health/live", headers={"X-Request-ID": "trace-123"}).headers["x-request-id"] == "trace-123"
    evil = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id with spaces <script>"})
    assert evil.headers["x-request-id"] != "bad id with spaces <script>"
