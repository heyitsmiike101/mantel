import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .bootstrap import ensure_defaults
from .config import get_settings
from .db import SessionLocal, engine
from .errors import register_error_handlers
from .models import Base
from .routers import (
    accounts,
    calendars,
    dashboard,
    events,
    meta,
    sync,
    users,
)
from .routers import (
    settings as settings_router,
)
from .services import scheduler

settings = get_settings()

STATIC_DIR = next(
    (
        p
        for p in (Path("/app/static"), Path(__file__).resolve().parents[2] / "frontend" / "dist")
        if p.is_dir()
    ),
    None,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_defaults(db)
    tasks = scheduler.start(asyncio.get_running_loop())
    try:
        yield
    finally:
        await scheduler.stop(tasks)


app = FastAPI(
    title="Family Calendar API",
    version=settings.version,
    description=(
        "Self-hosted family calendar. No authentication: this API is designed to run on a "
        "trusted home network. Every feature in the UI is backed by an endpoint here, so "
        "external tools and AI agents can do anything the app can do.\n\n"
        "See `/api/ai-guide` for a task-oriented guide written for LLM agents."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(meta.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(calendars.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")


if STATIC_DIR:
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """SPA fallback. index.html is served no-cache so a redeployed build is picked up
        immediately; Vite's content-hashed assets are safe to cache forever."""
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": "Unknown API route"}},
            )
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(
            STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, must-revalidate"}
        )
