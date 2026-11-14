from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import conflict
from app.core.security import (
    DUMMY_HASH,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from app.db.models import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, email: str, password: str) -> User:
    email = normalize_email(email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise conflict("An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous registrations; the unique constraint wins
        db.rollback()
        raise conflict("An account with this email already exists.")
    return user


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    if user is None:
        verify_password(password, DUMMY_HASH)  # equalize timing; result intentionally ignored
        return None
    if not verify_password(password, user.password_hash):
        return None
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    return user
