from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.runs import router as runs_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

if settings.sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn, environment=settings.environment, traces_sample_rate=0.0
        )
    except Exception as e:  # pragma: no cover
        logger.warning("sentry_init_failed", error=str(e))

app = FastAPI(title="DOME Governed Agent Flow", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared security headers + request id (house middleware), if available.
try:
    from dome_core.middleware import RequestIDMiddleware, SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)
except Exception as e:  # pragma: no cover
    logger.warning("house_middleware_unavailable", error=str(e))


@app.get("/api/v1/health")
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0", "environment": settings.environment}


app.include_router(runs_router, prefix="/api/v1")
