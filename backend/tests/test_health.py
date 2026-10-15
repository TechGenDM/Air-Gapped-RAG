"""Tests for FastAPI health check endpoint."""

from fastapi import status


def test_health_check(client):
    """Verify that GET /health returns HTTP 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "air-gapped-rag-backend"
    assert "version" in data
