import math
from datetime import datetime
from typing import Any

import numpy as np

from .config import (
    EMBEDDING_MODEL,
    IMPORTANCE_SCORES,
    SEARCH_WEIGHT_FRESHNESS,
    SEARCH_WEIGHT_IMPORTANCE,
    SEARCH_WEIGHT_VECTOR,
    TEMPORAL_DECAY_RATE,
)

# Reuse the thread-local Postgres connection from database.py so embeddings
# are written in the same connection/transaction as the structured row.
from . import database


class Memory:
    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBEDDING_MODEL)
        return self._model

    def _encode(self, text: str) -> np.ndarray:
        return np.array(self.model.encode(text), dtype=np.float32)

    def _conn(self):
        return database._connect()

    # --- Legacy interface (unchanged behavior) ---

    def add(self, id: str, text: str, metadata: dict[str, Any]):
        embedding = self._encode(text)
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE memories SET embedding = %s WHERE id = %s", (embedding, id))
        conn.commit()

    def search(self, query: str, limit: int = 5, filters: dict[str, Any] = None) -> list[dict[str, Any]]:
        embedding = self._encode(query)
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, content, category, importance, source, updated_at "
            "FROM memories WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> %s LIMIT %s",
            (embedding, limit),
        )
        rows = c.fetchall()
        return [
            {
                "id": r[0],
                "content": r[1],
                "metadata": {"category": r[2], "importance": r[3], "source": r[4], "updated_at": r[5]},
                "distance": None,
            }
            for r in rows
        ]

    # --- V2 Project Memory interface ---

    def add_memory(self, memory_id: str, project_id: str, text: str, metadata: dict[str, Any]):
        embedding = self._encode(text)
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE memories SET embedding = %s WHERE id = %s", (embedding, memory_id))
        conn.commit()

    def delete_memory(self, memory_id: str, project_id: str):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE memories SET embedding = NULL WHERE id = %s", (memory_id,))
        conn.commit()

    def search_memories(
        self, query: str, project_id: str, limit: int = 10, where: dict | None = None
    ) -> list[dict[str, Any]]:
        embedding = self._encode(query)
        return self._ranked_search(embedding, limit, project_id=project_id)

    # --- V2 Org Memory interface ---

    def add_org_memory(self, memory_id: str, org_id: str, text: str, metadata: dict[str, Any]):
        embedding = self._encode(text)
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE memories SET embedding = %s WHERE id = %s", (embedding, memory_id))
        conn.commit()

    def delete_org_memory(self, memory_id: str, org_id: str):
        conn = self._conn()
        c = conn.cursor()
        c.execute("UPDATE memories SET embedding = NULL WHERE id = %s", (memory_id,))
        conn.commit()

    def search_org_memories(
        self, query: str, org_id: str, limit: int = 10, where: dict | None = None
    ) -> list[dict[str, Any]]:
        embedding = self._encode(query)
        return self._ranked_search(embedding, limit, org_id=org_id)

    def _ranked_search(
        self,
        query_embedding: np.ndarray,
        limit: int,
        project_id: str | None = None,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        fetch_limit = min(limit * 3, 50)
        conn = self._conn()
        c = conn.cursor()

        if project_id:
            c.execute(
                "SELECT id, content, category, importance, source, updated_at, "
                "1 - (embedding <=> %s) AS similarity "
                "FROM memories "
                "WHERE project_id = %s AND embedding IS NOT NULL "
                "ORDER BY embedding <=> %s LIMIT %s",
                (query_embedding, project_id, query_embedding, fetch_limit),
            )
        else:
            c.execute(
                "SELECT id, content, category, importance, source, updated_at, "
                "1 - (embedding <=> %s) AS similarity "
                "FROM memories "
                "WHERE org_id = %s AND scope = 'org' AND embedding IS NOT NULL "
                "ORDER BY embedding <=> %s LIMIT %s",
                (query_embedding, org_id, query_embedding, fetch_limit),
            )

        rows = c.fetchall()
        candidates = []

        for mem_id, content, category, importance, source, updated_at_str, similarity in rows:
            vector_score = float(similarity) if similarity is not None else 0.0
            importance_score = IMPORTANCE_SCORES.get(importance or "medium", 0.5)

            freshness_score = 1.0
            if updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str)
                    days_old = (datetime.utcnow() - updated_at).total_seconds() / 86400
                    freshness_score = math.exp(-TEMPORAL_DECAY_RATE * days_old)
                except (ValueError, TypeError):
                    pass

            combined_score = (
                SEARCH_WEIGHT_VECTOR * vector_score
                + SEARCH_WEIGHT_IMPORTANCE * importance_score
                + SEARCH_WEIGHT_FRESHNESS * freshness_score
            )

            candidates.append(
                {
                    "id": mem_id,
                    "content": content,
                    "metadata": {
                        "category": category,
                        "importance": importance,
                        "source": source or "",
                        "updated_at": updated_at_str or "",
                    },
                    "score": round(combined_score, 4),
                    "vector_score": round(vector_score, 4),
                    "importance_score": importance_score,
                    "freshness_score": round(freshness_score, 4),
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]


# Lazy singleton
_memory_store: Memory | None = None


def get_memory_store() -> Memory:
    global _memory_store
    if _memory_store is None:
        _memory_store = Memory()
    return _memory_store


class _LazyMemoryStore:
    def __getattr__(self, name):
        return getattr(get_memory_store(), name)


memory_store = _LazyMemoryStore()
