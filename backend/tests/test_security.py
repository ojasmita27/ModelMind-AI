from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_argon2id_and_not_plaintext():
    h = hash_password("my-secret-password")
    assert h.startswith("$argon2id$")
    assert "my-secret-password" not in h


def test_hashes_are_salted():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password():
    h = hash_password("right-password")
    assert verify_password("right-password", h) is True
    assert verify_password("wrong-password", h) is False
    assert verify_password("anything", "not-a-valid-hash") is False


def test_token_roundtrip():
    assert decode_access_token(create_access_token("user-123")) == "user-123"


def test_expired_token_rejected():
    assert decode_access_token(create_access_token("u", timedelta(seconds=-5))) is None


def test_tampered_token_rejected():
    token = create_access_token("u")
    assert decode_access_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB")) is None


def test_token_signed_with_other_key_rejected():
    forged = jwt.encode({"sub": "u", "exp": 4102444800}, "x" * 40, algorithm="HS256")
    assert decode_access_token(forged) is None


def test_alg_none_token_rejected():
    forged = jwt.encode({"sub": "u", "exp": 4102444800}, key=None, algorithm="none")
    assert decode_access_token(forged) is None


def test_token_without_subject_or_expiry_rejected():
    s = get_settings()
    no_sub = jwt.encode({"exp": 4102444800}, s.secret_key, algorithm=s.jwt_algorithm)
    no_exp = jwt.encode({"sub": "u"}, s.secret_key, algorithm=s.jwt_algorithm)
    assert decode_access_token(no_sub) is None
    assert decode_access_token(no_exp) is None


def test_placeholder_secret_is_rejected(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("SECRET_KEY", "CHANGE_ME_generate_a_random_value_of_32_or_more_characters")
    with pytest.raises(Exception, match="CHANGE_ME"):
        Settings()
