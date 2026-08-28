"""
Retrieval + RBAC verification (read-only, no LLM).

For each (email, query) pair, loads the user, runs the real SearchService
semantic_search, and prints every returned chunk's owner + document + score.

Proves two things at once:
  1. A document's OWNER now retrieves their own chunks (fix works).
  2. A DIFFERENT employee never retrieves someone else's chunks (RBAC intact).

Usage:
    docker compose exec backend python -m scripts.verify_retrieval
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal, engine
from app.models.user import User
from app.services.search_service import SearchService

# (email, query) probes.
PROBES = [
    ("chiragbantwal4@gmail.com", "What does the 30-day Java placement roadmap cover?"),
    ("john@test.com", "What does the 30-day Java placement roadmap cover?"),
]

# Chirag's SPECIFIC Java document (by id, not name — another user may own a
# same-named copy legitimately). This exact document_id must NEVER appear for
# any user other than chirag.
CHIRAG_JAVA_DOC_ID = "a3a07e81-7e79-4f2a-8bd8-860379b749aa"


async def run() -> None:
    async with AsyncSessionLocal() as session:
        for email, query in PROBES:
            user = (
                await session.execute(
                    select(User).options(selectinload(User.role)).where(User.email == email)
                )
            ).scalar_one_or_none()

            print("\n" + "=" * 78)
            if user is None:
                print(f"SKIP  {email}: no such user")
                continue

            role = getattr(user.role, "name", "?")
            print(f"USER  {email}  (role={role}, id={user.id})")
            print(f"QUERY {query!r}")

            svc = SearchService(session)
            data = await svc.semantic_search(
                query=query,
                actor=user,
                top_k=10,
                min_score=None,
                ip_address="127.0.0.1",
            )

            print(f"RESULTS: {len(data.results)}")
            leaked = 0
            for r in data.results:
                flag = ""
                if str(r.document_id) == CHIRAG_JAVA_DOC_ID and email != "chiragbantwal4@gmail.com":
                    flag = "  <<< RBAC LEAK!"
                    leaked += 1
                print(
                    f"  - {r.document_name:42s} doc={str(r.document_id)[:8]} "
                    f"chunk#{r.chunk_number} sim={r.similarity:.3f}{flag}"
                )
            if email != "chiragbantwal4@gmail.com":
                verdict = "FAIL (leak)" if leaked else "PASS (no cross-user access)"
                print(f"RBAC CHECK: {verdict}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
