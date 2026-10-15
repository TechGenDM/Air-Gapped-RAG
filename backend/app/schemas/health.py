"""Health check response schema."""

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check payload."""

    model_config = ConfigDict(frozen=True)

    status: str = Field(..., description="Service health status", examples=["ok"])
    app: str = Field(..., description="Application name", examples=["air-gapped-rag-backend"])
    version: str = Field(..., description="Application version", examples=["0.1.0"])
