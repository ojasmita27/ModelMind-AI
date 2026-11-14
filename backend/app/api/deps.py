import uuid
from typing import Annotated, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import unauthorized
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

# auto_error=False so a missing header goes through our own error envelope.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
) -> User:
    if credentials is None:
        raise unauthorized()
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise unauthorized("Invalid or expired token.")
    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise unauthorized("Invalid or expired token.")
    user = db.get(User, user_id)
    if user is None:  # e.g. account deleted after the token was issued
        raise unauthorized("Invalid or expired token.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
