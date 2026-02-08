import math
from datetime import datetime
from typing import List, Dict, Any, Optional

from .config import (
    CHROMA_PATH, ensure_directories, IMPORTANCE_SCORES,
    SEARCH_WEIGHT_VECTOR, SEARCH_WEIGHT_IMPORTANCE, SEARCH_WEIGHT_FRESHNESS,
    TEMPORAL_DECAY_RATE,
)


class Memory:
    def __init__(self, persist_directory: Optional[str] = None):
        self._persist_directory = persist_directory or str(CHROMA_PATH)
        self._client = None
        self._model = None
        self._collections: Dict[str, Any] = {}

    @property
    def client(self):
        if self._client is None:
            ensure_directories()
            import chromadb
            from chromadb.config import Settings
            self._client = chromadb.Client(Settings(
                persist_directory=self._persist_directory,
                is_persistent=True,
            ))
        return self._client

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model

    def _get_collection(self, name: str = "continuum"):
        if name not in self._collections:
            self._collections[name] = self.client.get_or_create_collection(name=name)
        return self._collections[name]

    def _project_collection_name(self, project_id: str) -> str:
        return f"project_{project_id[:8]}"

    # --- Legacy interface (unchanged behavior) ---

    def add(self, id: str, text: str, metadata: Dict[str, Any]):
        embedding = self.model.encode(text).tolist()
        collection = self._get_collection("continuum")
        collection.add(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[id],
        )

    def search(self, query: str, limit: int = 5,
               filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        query_embedding = self.model.encode(query).tolist()
        where_clause = filters if filters else None
        collection = self._get_collection("continuum")
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_clause,
        )
        formatted = []
        if results['ids']:
            for i in range(len(results['ids'][0])):
                formatted.append({
                    "id": results['ids'][0][i],
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i],
                    "distance": results['distances'][0][i] if results['distances'] else None,
                })
        return formatted

    # --- V2 Memory interface ---

    def add_memory(self, memory_id: str, project_id: str, text: str,
                   metadata: Dict[str, Any]):
        embedding = self.model.encode(text).tolist()
        col_name = self._project_collection_name(project_id)
        collection = self._get_collection(col_name)
        collection.upsert(
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
            ids=[memory_id],
        )

    def delete_memory(self, memory_id: str, project_id: str):
        col_name = self._project_collection_name(project_id)
        collection = self._get_collection(col_name)
        try:
            collection.delete(ids=[memory_id])
        except Exception:
            pass

    def search_memories(self, query: str, project_id: str,
                        limit: int = 10,
                        where: Optional[Dict] = None) -> List[Dict[str, Any]]:
        query_embedding = self.model.encode(query).tolist()
        col_name = self._project_collection_name(project_id)
        collection = self._get_collection(col_name)

        # Fetch more candidates than needed for re-ranking
        fetch_limit = min(limit * 3, 50)
        try:
            count = collection.count()
            if count == 0:
                return []
            fetch_limit = min(fetch_limit, count)
        except Exception:
            pass

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=fetch_limit,
            where=where if where else None,
        )

        if not results['ids'] or not results['ids'][0]:
            return []

        candidates = []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i] if results['metadatas'] else {}
            distance = results['distances'][0][i] if results['distances'] else 1.0
            # Convert distance to similarity (ChromaDB returns L2 distance)
            vector_score = 1.0 / (1.0 + distance)

            # Importance score
            importance_val = meta.get("importance", "medium")
            importance_score = IMPORTANCE_SCORES.get(importance_val, 0.5)

            # Temporal freshness score
            freshness_score = 1.0
            updated_at_str = meta.get("updated_at")
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

            candidates.append({
                "id": results['ids'][0][i],
                "content": results['documents'][0][i],
                "metadata": meta,
                "score": round(combined_score, 4),
                "vector_score": round(vector_score, 4),
                "importance_score": importance_score,
                "freshness_score": round(freshness_score, 4),
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]


# Lazy singleton
_memory_store = None


def get_memory_store() -> Memory:
    global _memory_store
    if _memory_store is None:
        _memory_store = Memory()
    return _memory_store


# Backward-compatible alias — lazy so SentenceTransformer isn't loaded at import
class _LazyMemoryStore:
    def __getattr__(self, name):
        return getattr(get_memory_store(), name)

memory_store = _LazyMemoryStore()
