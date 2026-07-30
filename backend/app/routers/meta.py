from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..config import REPO_ROOT, get_settings

router = APIRouter(tags=["meta"])


class VersionResponse(BaseModel):
    version: str = Field(description="Running application version", examples=["0.1.0"])
    build_time: str = Field(
        default="", description="UTC ISO-8601 build timestamp, empty in dev", examples=[""]
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
        "wall-mounted kiosk displays current without anyone touching them."
    ),
)
def get_version() -> VersionResponse:
    s = get_settings()
    return VersionResponse(version=s.version, build_time=s.build_time)


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
