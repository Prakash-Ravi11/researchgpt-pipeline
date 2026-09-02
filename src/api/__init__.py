"""ResearchGPT API package.

Re-exports the FastAPI app from `src.api.main` so both of these work:
    uvicorn src.api:app --reload
    uvicorn src.api.main:app --reload
"""
from src.api.main import app

__all__ = ["app"]
