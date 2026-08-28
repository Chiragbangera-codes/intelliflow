"""
Embedding / FAISS reconciliation CLI — heals the "chunks exist but no
embeddings" gap by delegating to app.services.reindex_service.

This is a thin command-line wrapper. All logic lives in
`reindex_all_embeddings()` so the CLI, the Celery task
(`tasks.reindex_all_embeddings`), and the admin endpoint all share one
implementation.

Run (from the repo root):
    docker compose exec backend python -m scripts.reconcile_embeddings

The API and worker processes now auto-reload the FAISS index when the on-disk
file changes (VectorStoreService mtime check), so a restart is no longer
strictly required for the rebuild to take effect on live queries. Restarting is
still harmless if you prefer a clean slate:
    docker compose restart backend worker
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.core.database import AsyncSessionLocal, engine
from app.services.reindex_service import reindex_all_embeddings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("reconcile")


async def _run() -> dict:
    async with AsyncSessionLocal() as session:
        report = await reindex_all_embeddings(session)
    await engine.dispose()
    return report


def main() -> None:
    report = asyncio.run(_run())
    print("\n================ RECONCILIATION REPORT ================")
    print(json.dumps({k: v for k, v in report.items() if k != "per_document"}, indent=2))
    print("=======================================================\n")


if __name__ == "__main__":
    main()
