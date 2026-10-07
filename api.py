from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from analytics_engine.config import get_settings
from analytics_engine.engine import AnalyticsQueryEngine


app = FastAPI(
    title="Intelligent Analytics Query Engine",
    version="2.0.0",
    description="Natural-language analytics powered by GenAI planning and deterministic DuckDB execution.",
)


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=4000)


@lru_cache(maxsize=1)
def _engine() -> AnalyticsQueryEngine:
    return AnalyticsQueryEngine(get_settings())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/query")
def query(request: QueryRequest) -> dict:
    try:
        return _engine().answer(request.query).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
