"""Aggregated V1 API router."""

from fastapi import APIRouter

from app.api.v1.answer import router as answer_router
from app.api.v1.documents import router as documents_router
from app.api.v1.search import router as search_router

api_router = APIRouter()
api_router.include_router(documents_router)
api_router.include_router(search_router)
api_router.include_router(answer_router)

