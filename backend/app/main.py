import asyncio
import logging
import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import Settings, get_settings
from app.db import create_engine, create_sessionmaker, ping
from app.errors import DomainError, TooManyRequestsError
from app.events import EventBus
from app.poller import Poller
from app.runner import Runner
from app.security import CSRF_HEADER, SecretCipher, csrf_header_ok

logger = logging.getLogger(__name__)

# The Vite build is copied here in the Docker image. In development the Vite dev server
# serves the frontend instead, so this directory may not exist.
STATIC_DIR = Path(__file__).parent / "static"
HEALTHZ_TIMEOUT_SECONDS = 3

RequestHandler = Callable[[Request], Awaitable[Response]]


def create_app(settings: Settings | None = None, *, poll: bool = True) -> FastAPI:
    """`poll=False` leaves State polling off (for tests that drive the Poller directly)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved = settings or get_settings()
        engine = create_engine(resolved.database_url)
        app.state.settings = resolved
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        app.state.cipher = SecretCipher(resolved.secret_key.get_secret_value())
        bus = app.state.bus = EventBus()
        poller = app.state.poller = Poller(app.state.sessionmaker, app.state.cipher, bus)
        runner = Runner(
            app.state.sessionmaker, app.state.cipher, bus, on_feature_run=poller.poll_soon
        )
        app.state.runner = runner
        if interrupted := await runner.recover():
            logger.warning("Marked %d unfinished runs as interrupted", interrupted)
        if poll:
            poller.start()
        try:
            yield
        finally:
            await poller.stop()
            await runner.shutdown()
            bus.close()
            await engine.dispose()

    app = FastAPI(
        title="runpad",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )

    @app.get("/healthz", include_in_schema=False)
    async def healthz(request: Request) -> JSONResponse:
        try:
            async with asyncio.timeout(HEALTHZ_TIMEOUT_SECONDS):
                await ping(request.app.state.engine)
        except Exception:
            logger.warning("Health check failed: database unreachable", exc_info=True)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.middleware("http")
    async def require_csrf_header(request: Request, call_next: RequestHandler) -> Response:
        if not csrf_header_ok(request.method, request.url.path, dict(request.headers)):
            return JSONResponse({"detail": f"Missing {CSRF_HEADER} header"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        headers = {}
        if isinstance(exc, TooManyRequestsError):
            headers["Retry-After"] = str(exc.retry_after_seconds)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)

    app.include_router(api_router)

    @app.api_route(
        "/api/{path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def api_not_found(path: str) -> None:
        raise HTTPException(status_code=404, detail="Not found")

    if STATIC_DIR.is_dir():
        _mount_frontend(app, STATIC_DIR)

    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the built single-page app, falling back to index.html for client routes."""
    # Not in Python's table; browsers expect it for the web app manifest.
    mimetypes.add_type("application/manifest+json", ".webmanifest")
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")
    index = static_dir / "index.html"
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
