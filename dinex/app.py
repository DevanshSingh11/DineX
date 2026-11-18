from contextlib import asynccontextmanager
import logging
import secrets
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import ROOT, load_config
from .db import make_engine, migrate
from .gemini import AUDIO_LIMIT
from .routes import guest, media, platform, restaurant
from .security import Limits, password_hash

log = logging.getLogger("dinex")


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in {"GET", "HEAD", "OPTIONS"}:
            return await self.app(scope, receive, send)
        limit = (
            3 * 1024 * 1024 if scope["path"] == "/api/restaurant/images" else 192 * 1024
        )
        if scope["path"] == "/api/guest/assistant/transcribe":
            limit = AUDIO_LIMIT
        chunks = bytearray()
        while True:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                return
            chunks.extend(msg.get("body", b""))
            if len(chunks) > limit:
                return await JSONResponse(
                    {"detail": "This upload or request is too large."}, 413
                )(scope, receive, send)
            if not msg.get("more_body"):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(chunks), "more_body": False}

        return await self.app(scope, replay, send)


def create_app(cfg=None):
    cfg = cfg or load_config()
    engine = make_engine(cfg.database)

    @asynccontextmanager
    async def lifespan(app):
        migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="DineX Universal",
        version="1.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.cfg, app.state.engine, app.state.limits = cfg, engine, Limits()
    app.state.dummy_hash = password_hash(secrets.token_urlsafe(32))
    app.add_middleware(BodyLimit)

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if (
            request.url.path.startswith("/api/")
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and (
                request.headers.get("X-DineX") != "1"
                or request.headers.get("Origin") not in (None, cfg.public_url)
            )
        ):
            return JSONResponse(
                {"detail": "Use the configured DineX origin and request header."},
                status_code=403,
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' https: data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(_, exc):
        errors = [
            ".".join(str(i) for i in e["loc"][1:]) + " — " + e["msg"]
            for e in exc.errors()[:6]
        ]
        return JSONResponse(
            {"detail": "Check the input. " + " / ".join(errors)}, status_code=422
        )

    @app.get("/health")
    def health():
        with engine.connect() as con:
            con.exec_driver_sql("SELECT 1")
        return {"status": "ok", "application": "DineX Universal"}

    for module in (platform, restaurant, guest, media):
        app.include_router(module.router)
    web = ROOT / "web"
    app.mount("/static", StaticFiles(directory=web / "static"), name="static")

    def page(name):
        def serve():
            return FileResponse(web / name)

        return serve

    for path, filename in [
        ("/", "index.html"),
        ("/register", "register.html"),
        ("/platform", "workspace.html"),
        ("/restaurant", "workspace.html"),
        ("/kitchen", "workspace.html"),
        ("/t/{slug}/{table_id}", "guest.html"),
    ]:
        app.add_api_route(
            path, page(filename), methods=["GET"], include_in_schema=False
        )
    return app
