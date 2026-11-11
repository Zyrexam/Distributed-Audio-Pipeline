import asyncio
import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST

from app.auth.routes import router as auth_router
from app.config import get_settings, setup_logging
from app.infrastructure.database import db
from app.infrastructure.metrics import render_metrics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.open()
    for _ in range(20):
        if db.is_healthy():
            logger.info("PostgreSQL is healthy")
            break
        await asyncio.sleep(1)
    else:
        logger.warning("PostgreSQL not healthy after 20s - continuing")
    yield
    db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Distributed Audio Pipeline",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
    )

    # Bearer-token API: no cookies/sessions, so credentials are off.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(psycopg.Error)
    async def database_error_handler(request: Request, exc: psycopg.Error):
        logger.exception("Database error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503, content={"detail": "database unavailable"}
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"detail": "internal server error"}
        )

    app.include_router(auth_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(
            content=render_metrics(), media_type=CONTENT_TYPE_LATEST
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
