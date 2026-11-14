from datetime import timedelta

from sqlalchemy import text

from app.core.security import create_access_token
from app.db.session import get_engine

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_register_returns_user_without_password(client):
    r = client.post(REGISTER, json={"email": "new@example.com", "password": "long-enough-pw"})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new@example.com"
    assert "id" in body and "created_at" in body
    assert "password" not in body and "password_hash" not in body


def test_password_is_stored_hashed(client):
    client.post(REGISTER, json={"email": "h@example.com", "password": "plain-text-pw-1"})
    with get_engine().connect() as conn:
        stored = conn.execute(text("SELECT password_hash FROM users WHERE email='h@example.com'")).scalar()
    assert stored.startswith("$argon2id$")
    assert "plain-text-pw-1" not in stored


def test_email_is_normalized_and_duplicates_rejected(client):
    assert client.post(REGISTER, json={"email": "Case@Example.com", "password": "long-enough-pw"}).status_code == 201
    r = client.post(REGISTER, json={"email": "case@example.COM", "password": "another-long-pw"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_register_validation(client):
    r = client.post(REGISTER, json={"email": "not-an-email", "password": "long-enough-pw"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = client.post(REGISTER, json={"email": "a@example.com", "password": "Zq9!x7"})
    assert r.status_code == 422
    assert "Zq9!x7" not in r.text  # the rejected password is not echoed back
    assert client.post(REGISTER, json={"email": "a@example.com"}).status_code == 422


def test_login_success_and_me(client):
    client.post(REGISTER, json={"email": "me@example.com", "password": "long-enough-pw"})
    r = client.post(LOGIN, json={"email": "ME@example.com", "password": "long-enough-pw"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    me = client.get(ME, headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "me@example.com"


def test_login_failures_are_indistinguishable(client):
    client.post(REGISTER, json={"email": "real@example.com", "password": "long-enough-pw"})
    wrong_pw = client.post(LOGIN, json={"email": "real@example.com", "password": "not-the-password"})
    no_user = client.post(LOGIN, json={"email": "ghost@example.com", "password": "not-the-password"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_me_requires_valid_token(client):
    r = client.get(ME)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"
    assert client.get(ME, headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = create_access_token("00000000-0000-0000-0000-000000000000", timedelta(seconds=-1))
    assert client.get(ME, headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_token_for_nonexistent_user_rejected(client):
    token = create_access_token("00000000-0000-0000-0000-000000000000")
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_with_non_uuid_subject_rejected(client):
    token = create_access_token("not-a-uuid")
    assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_password_length_limits(client):
    assert client.post(REGISTER, json={"email": "max@example.com", "password": "p" * 128}).status_code == 201
    r = client.post(REGISTER, json={"email": "max2@example.com", "password": "p" * 129})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_non_bearer_auth_scheme_rejected(client):
    assert client.get(ME, headers={"Authorization": "Basic dXNlcjpwYXNz"}).status_code == 401


def test_overlong_email_rejected(client):
    r = client.post(REGISTER, json={"email": "a" * 300 + "@example.com", "password": "long-enough-pw"})
    assert r.status_code == 422
