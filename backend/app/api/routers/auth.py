from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.core.errors import unauthorized
from app.core.logging import get_logger, log_event
from app.core.security import create_access_token
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession):
    user = auth_service.register_user(db, body.email, body.password)
    log_event(log, "user_registered", user_id=str(user.id))
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, db: DbSession):
    user = auth_service.authenticate(db, body.email, body.password)
    if user is None:
        log_event(log, "login_failed", level=30)  # no email: it is personal data
        raise unauthorized("Incorrect email or password.")
    log_event(log, "login_succeeded", user_id=str(user.id))
    return TokenOut(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser):
    return current_user
