# backend/app/core/errors.py
"""Coded API errors: {"detail": {"code": "<code>", "message": "<text>"}}.

This is the error shape of the campus API and of every endpoint added since.
``CodedErrorRoute`` makes request-validation failures (missing fields, wrong
types, malformed JSON) use the same shape with code ``invalid_request`` instead
of FastAPI's default list, without changing older routers.
"""

from typing import Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


def api_error(status_code: int, code: str, message: str, headers: dict | None = None, **extra: Any) -> HTTPException:
    detail = {"code": code, "message": message, **extra}
    return HTTPException(status_code=status_code, detail=detail, headers=headers)


def _clean_errors(errors) -> list[dict]:
    """Validation errors without "input"/"ctx": they can echo request values such as passwords."""
    cleaned = []
    for error in errors:
        cleaned.append({
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        })
    return cleaned


def validation_error_response(exc: RequestValidationError) -> JSONResponse:
    errors = _clean_errors(exc.errors())
    if errors:
        first = errors[0]
        loc = first["loc"]
        # Drop the leading "body"/"query" segment: "body.email" -> "email".
        field = ".".join(loc[1:]) if len(loc) > 1 else (loc[0] if loc else "")
        message = f"{field}: {first['msg']}" if field else first["msg"]
    else:
        message = "Invalid request"
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_request", "message": message, "errors": errors}},
    )


class CodedErrorRoute(APIRoute):
    """APIRoute whose request-validation failures use the coded error shape."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError as exc:
                return validation_error_response(exc)

        return handler
