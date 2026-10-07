from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    dataset_dir: Path = Path(os.getenv("DATASET_DIR", "dataset"))
    model: str = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    max_repair_attempts: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "1"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "5000"))
    enable_feedback_embeddings: bool = _env_bool("ENABLE_FEEDBACK_EMBEDDINGS", True)
    embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def get_settings(dataset_dir: str | Path | None = None) -> Settings:
    base = Settings()
    if dataset_dir is None:
        return base
    return Settings(
        dataset_dir=Path(dataset_dir),
        model=base.model,
        max_repair_attempts=base.max_repair_attempts,
        max_result_rows=base.max_result_rows,
        enable_feedback_embeddings=base.enable_feedback_embeddings,
        embedding_model=base.embedding_model,
    )
