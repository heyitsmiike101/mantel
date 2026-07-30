from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _envelope(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


_CODES = {
    400: "bad_request",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    500: "internal_error",
}


def register_error_handlers(app: FastAPI) -> None:
    """Every error response uses the same {"error": {"code", "message"}} envelope so
    API consumers (including AI agents) can handle failures uniformly."""

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail
        code = _CODES.get(exc.status_code, "error")
        if isinstance(detail, dict):
            code = detail.get("code", code)
            detail = detail.get("message", "")
        return _envelope(code, str(detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return _envelope("validation_error", str(exc.errors()), 422)
