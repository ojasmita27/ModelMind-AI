import json
import logging

from app.core.logging import (
    REDACTED, JsonFormatter, TextFormatter, get_logger, log_event, redact_fields, scrub_text,
)

SECRET_URL = "postgresql+psycopg://modelmind:hunter2pw@localhost:5432/modelmind"
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlMTIz"


def test_scrub_text_removes_credentials():
    assert "hunter2pw" not in scrub_text(f"cannot connect to {SECRET_URL}")
    assert FAKE_JWT not in scrub_text(f"token was {FAKE_JWT}")
    assert "abc.def.ghi" not in scrub_text("Authorization: Bearer abc.def.ghi")


def test_sensitive_field_names_are_redacted():
    out = redact_fields({"password": "p", "access_token": "t", "SECRET_KEY": "s", "database_url": SECRET_URL,
                         "Authorization": "Bearer x", "user_id": "42"})
    assert out["user_id"] == "42"
    assert all(out[k] == REDACTED for k in ("password", "access_token", "SECRET_KEY", "database_url", "Authorization"))


def _record(**fields):
    r = logging.LogRecord("modelmind.t", logging.INFO, __file__, 1, "something_happened", None, None)
    r.fields = redact_fields(fields)
    return r


def test_text_and_json_formats_never_contain_secrets():
    rec = _record(password="hunter2pw", note=f"url {SECRET_URL}", user_id="u1")
    text_line = TextFormatter().format(rec)
    json_line = JsonFormatter().format(rec)
    for line in (text_line, json_line):
        assert "hunter2pw" not in line
    assert "user_id=u1" in text_line
    assert json.loads(json_line)["event"] == "something_happened"


def test_log_event_attaches_redacted_fields(caplog):
    caplog.set_level(logging.INFO, logger="modelmind")
    log_event(get_logger("unit"), "demo", password="hunter2pw", item="ok")
    rec = [r for r in caplog.records if r.getMessage() == "demo"][0]
    assert rec.fields == {"password": REDACTED, "item": "ok"}


def test_http_flow_logs_events_but_no_secrets(client, caplog):
    caplog.set_level(logging.INFO, logger="modelmind")
    pw = "very-secret-pw-123"
    client.post("/api/v1/auth/register", json={"email": "log@example.com", "password": pw})
    token = client.post("/api/v1/auth/login", json={"email": "log@example.com", "password": pw}).json()["access_token"]
    client.post("/api/v1/projects", json={"name": "P"}, headers={"Authorization": f"Bearer {token}"})
    client.get("/api/v1/projects?limit=5&offset=0", headers={"Authorization": f"Bearer {token}"})
    client.post("/api/v1/auth/login", json={"email": "log@example.com", "password": "wrong-password-1"})

    dump = " ".join(r.getMessage() + " " + str(getattr(r, "fields", "")) for r in caplog.records)
    for secret in (pw, token, "wrong-password-1", "log@example.com"):
        assert secret not in dump
    events = {r.getMessage() for r in caplog.records}
    assert {"request", "user_registered", "login_succeeded", "login_failed", "project_created"} <= events
    http = [r.fields for r in caplog.records if r.getMessage() == "request"]
    assert any(f["path"] == "/api/v1/projects" and f["method"] == "GET" and f["status"] == 200 for f in http)
    assert all("limit" not in str(f.get("path")) for f in http)  # query strings are never logged
