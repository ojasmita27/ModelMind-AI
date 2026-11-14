"""Configuration check. Run from the backend folder:  python -m app.check_config

Prints what the app will use (secrets never shown), tests the database connection and
reports whether migrations are applied. Exit code 0 = ready, non-zero = needs attention.
"""
import sys

from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.core.startup import diagnose_database, format_settings_error


def main() -> int:
    try:
        settings = Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        print(format_settings_error(exc), file=sys.stderr)
        return 2

    env_file = PROJECT_ROOT / ".env"
    print("ModelMind configuration check")
    print(f"  .env file     : {'found' if env_file.exists() else 'NOT found (using environment variables only)'}")
    print(f"  environment   : {settings.environment}")
    print(f"  SECRET_KEY    : set ({'placeholder-free' if 'CHANGE_ME' not in settings.secret_key else 'PLACEHOLDER'})")
    print(f"  token lifetime: {settings.access_token_expire_minutes} minutes")
    print(f"  CORS origins  : {', '.join(settings.cors_origin_list) or '(none)'}")
    print(f"  logging       : {settings.log_level} / {settings.log_format}")

    diag = diagnose_database(settings)
    print(f"  database      : {diag.backend} -> {diag.target}")
    print(f"  db reachable  : {'yes' if diag.reachable else 'NO'}")
    if diag.reachable:
        state = {True: "up to date", False: "NOT up to date", None: "unknown"}[diag.migrations_current]
        print(f"  migrations    : {state} (current={diag.current_revision}, head={diag.head_revision})")
    if diag.hint:
        print(f"\nAction needed: {diag.hint}")
    return 0 if diag.reachable and diag.migrations_current is not False else 1


if __name__ == "__main__":
    raise SystemExit(main())
