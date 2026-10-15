"""FastAPI entry point for Air-Gapped RAG backend service."""

import logging

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.schemas.health import HealthResponse

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("air_gapped_rag")


def create_app() -> FastAPI:
    """Initialize and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.project_name,
        version=settings.version,
        description="Local-first, air-gapped PDF processing and question-answering backend.",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS for local development (Next.js frontend)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @application.get(
        "/health",
        response_model=HealthResponse,
        status_code=status.HTTP_200_OK,
        tags=["system"],
        summary="System health status",
    )
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            app="air-gapped-rag-backend",
            version=settings.version,
        )

    # Mount V1 API router
    application.include_router(api_router, prefix=settings.api_v1_str)

    return application


app = create_app()
