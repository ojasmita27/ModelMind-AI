import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routers import auth, benchmarks, copilot, datasets, deployments, experiments, health, models, monitoring, projects, trust, explain
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, get_logger, log_event, request_id_ctx
from app.core.startup import diagnose_database, load_settings_or_exit

API_PREFIX = "/api/v1"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
http_log = get_logger("http")
app_log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings_or_exit()
    diag = diagnose_database(settings)
    log_event(
        app_log, "startup", version=__version__, environment=settings.environment,
        database=diag.target, db_reachable=diag.reachable,
        migrations_current=diag.migrations_current,
    )
    if diag.hint:
        log_event(app_log, "startup_attention", level=40, hint=diag.hint)

    # Start job queue for dataset processing
    from app.jobs import get_job_queue
    job_queue = get_job_queue()
    job_queue.start()

    yield

    # Stop job queue
    job_queue.stop()
    log_event(app_log, "shutdown")


def create_app() -> FastAPI:
    settings = load_settings_or_exit()
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # we use bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        finally:
            # Path only: never the query string, headers or body (they can carry secrets).
            log_event(
                http_log, "request", level=40 if status >= 500 else 20,
                method=request.method, path=request.url.path, status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            request_id_ctx.reset(token)

    register_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(projects.router, prefix=API_PREFIX)
    app.include_router(datasets.router, prefix=API_PREFIX)
    app.include_router(experiments.router, prefix=API_PREFIX)
    app.include_router(benchmarks.router, prefix=API_PREFIX)
    app.include_router(models.router, prefix=API_PREFIX)
    app.include_router(copilot.router, prefix=API_PREFIX)
    app.include_router(deployments.router, prefix=API_PREFIX)
    app.include_router(monitoring.router, prefix=API_PREFIX)
    app.include_router(trust.router, prefix=API_PREFIX)
    app.include_router(explain.router, prefix=API_PREFIX)
    return app


app = create_app()
