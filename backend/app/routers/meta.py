from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import REPO_ROOT, get_settings
from ..db import get_db
from ..services import update_check

router = APIRouter(tags=["meta"])


class VersionResponse(BaseModel):
    version: str = Field(description="Running application version", examples=["0.1.0"])
    build_time: str = Field(
        default="", description="UTC ISO-8601 build timestamp, empty in dev", examples=[""]
    )
    latest_version: str | None = Field(
        default=None,
        description="Newest released version found on GitHub, or null if never checked",
        examples=["0.5.10"],
    )
    update_available: bool = Field(
        default=False,
        description="True when latest_version is newer than the running version",
    )
    checked_at: datetime | None = Field(
        default=None, description="When GitHub was last successfully asked (UTC ISO-8601)"
    )
    release_url: str | None = Field(
        default=None,
        description="GitHub page for latest_version: the compare page when an update exists",
    )


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Current application version",
    description=(
        "Clients poll this endpoint to detect deployments. When the returned `version` differs "
        "from the one the page loaded with, the browser hard-reloads itself. This keeps "
        "wall-mounted kiosk displays current without anyone touching them.\n\n"
        "Also reports whether a newer release exists on GitHub. The server asks GitHub once a "
        "day (`UPDATE_CHECK_ENABLED=false` turns that off and makes no network calls); "
        "`latest_version`, `checked_at` and `release_url` are null until the first check "
        "succeeds. Nothing is ever updated automatically."
    ),
)
def get_version(db: Session = Depends(get_db)) -> VersionResponse:
    s = get_settings()
    # A stale answer left in the database from before the check was switched off must not
    # keep advertising an update.
    status = update_check.get_status(db) if s.update_check_enabled else update_check.UpdateStatus()
    latest = status.latest_version
    return VersionResponse(
        version=s.version,
        build_time=s.build_time,
        latest_version=latest,
        update_available=update_check.is_newer(latest, s.version),
        checked_at=update_check.checked_at_utc(status),
        release_url=update_check.release_url(s.update_check_repo, latest, s.version)
        if latest
        else None,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get(
    "/ai-guide",
    response_class=PlainTextResponse,
    summary="Implementation guide for AI agents",
    description=(
        "Returns a markdown guide written for LLM agents that need to read from or write to "
        "this calendar. Pair it with /api/openapi.json for the full machine-readable schema."
    ),
)
def ai_guide() -> str:
    for candidate in (REPO_ROOT / "docs" / "ai-guide.md", Path("/app/docs/ai-guide.md")):
        try:
            return candidate.read_text()
        except OSError:
            continue
    return "# AI guide unavailable\n\nSee /api/openapi.json for the full API schema.\n"
