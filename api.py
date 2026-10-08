from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from analytics_engine.config import get_settings
from analytics_engine.engine import AnalyticsQueryEngine


app = FastAPI(
    title="Intelligent Analytics Query Engine",
    version="2.1.0",
    description="Natural-language analytics powered by GenAI planning and deterministic DuckDB execution.",
)

FRONTEND = Path(__file__).resolve().parent / "frontend" / "index.html"


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)


@lru_cache(maxsize=1)
def _engine() -> AnalyticsQueryEngine:
    return AnalyticsQueryEngine(get_settings())


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND)


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "provider": settings.provider,
        "model": settings.model,
    }


@app.post("/query")
def query(request: QueryRequest) -> dict:
    try:
        return _engine().answer(request.query).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
