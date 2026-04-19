from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_dir


def resolve_cache_db_path() -> Path:
    """Return the filesystem path to the embedding cache SQLite file.

    Honors the GURU_EMBED_CACHE_PATH environment variable for test isolation.
    Otherwise uses platformdirs.user_cache_dir('guru') / 'embeddings.db'.
    """
    env = os.environ.get("GURU_EMBED_CACHE_PATH")
    if env:
        return Path(env)
    return Path(user_cache_dir("guru")) / "embeddings.db"


def uvicorn_log_config() -> dict:
    """Build a uvicorn log_config that propagates to the root logger.

    By setting propagate=True and removing custom handlers, uvicorn logs
    flow through the root logger's handlers (stderr + optional file),
    giving a unified log format and destination.
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {
            "uvicorn": {"level": "INFO", "propagate": True},
            "uvicorn.error": {"level": "INFO", "propagate": True},
            "uvicorn.access": {"level": "INFO", "propagate": True},
        },
    }
