"""Production entry point: one origin serves the built dashboard and mounts the API under /api.

    uvicorn app.serve:app

Same-origin serving keeps the SameSite=Strict session cookie working without CORS.
"""
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.main import create_app
from app.watchman import scheduler

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()  # automatic Watchman checks and monitoring-inbox reads
    yield
    scheduler.stop()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/api", create_app())


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (DIST / path).resolve()
        if path and candidate.is_file() and DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        # index.html must always be revalidated so a new build shows immediately; hashed assets cache normally.
        return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
else:

    @app.get("/", include_in_schema=False)
    def no_build():
        return JSONResponse({"detail": "frontend not built: run `npm run build` in frontend/", "api": "/api/docs"})
