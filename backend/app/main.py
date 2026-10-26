import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import context
from app.config import get_settings
from app.db import SessionLocal
from app.errors import APIError, api_error_handler
from app.routers import agents, audit, auth, demo, gateway, guardian, ops, policies, rules
from app.vocab import Decision

log = logging.getLogger("consent_court")


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    # Anything unexpected is a refusal, never an accidental approval.
    log.exception("unhandled error: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "something went wrong; no action was authorized",
                                                            "decision": Decision.BLOCK, "executed": False}})


async def database_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    # Fail closed: if state cannot be read or written, nothing is authorized.
    log.error("database error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "DATABASE_UNAVAILABLE", "message": "service temporarily unavailable; no action was authorized",
                           "decision": Decision.BLOCK, "executed": False}},
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Kavach API", version="2.0.0-m1")
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(SQLAlchemyError, database_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Agent-Key", "X-Consent-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        if not rid or len(rid) > 64 or not rid.replace("-", "").isalnum():
            rid = uuid.uuid4().hex
        token = context.correlation_id.set(rid)
        try:
            response = await call_next(request)
        finally:
            context.correlation_id.reset(token)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    for r in (auth.router, agents.router, rules.router, policies.router, guardian.router, gateway.router, audit.router,
              ops.router, demo.router):
        app.include_router(r)

    @app.get("/health", tags=["ops"])
    def health():
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
            return {"status": "ok", "database": "ok"}
        except SQLAlchemyError:
            return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})

    return app


app = create_app()
