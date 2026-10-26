from fastapi import Request
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra


def not_found(what: str = "resource") -> APIError:
    # 404 rather than 403 for other users' records, so ids cannot be probed.
    return APIError(404, "NOT_FOUND", f"{what} not found")


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message, **exc.extra}})
