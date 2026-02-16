"""Shared business logic for Continuum — used by FastAPI routes, MCP tools, and SDK."""

import logging
import os
import subprocess
from typing import List, Optional, Dict, Any

from continuum.server import database
from continuum.server.memory import get_memory_store
from continuum.server.models import (
    MemoryItem, MemoryCategory, Importance, Project, MemorySearch,
)
from continuum.server.config import IMPORTANCE_SCORES

logger = logging.getLogger(__name__)


class ContinuumService:
    def __init__(self):
        database.init_db()

    # --- Projects ---

    def find_or_create_project(self, name: Optional[str] = None,
                               path: Optional[str] = None,
                               git_remote: Optional[str] = None,
                               metadata: Optional[dict] = None) -> Project:
        if path:
            path = os.path.abspath(path)
        if not git_remote and path:
            git_remote = self._detect_git_remote(path)
        if not name:
            name = os.path.basename(path) if path else "unnamed"
        return database.find_or_create_project(
            name=name, path=path, git_remote=git_remote, metadata=metadata,
        )

    def get_project(self, project_id: str) -> Optional[Project]:
        return database.get_project(project_id)

    def list_projects(self) -> List[Project]:
        return database.list_projects()

    # --- Memories ---

    def store_memory(self, project_id: str, content: str,
                     category: MemoryCategory = MemoryCategory.general,
                     importance: Importance = Importance.medium,
                     source: Optional[str] = None,
                     tags: Optional[List[str]] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> MemoryItem:
        memory = MemoryItem(
            project_id=project_id,
            content=content,
            category=category,
            importance=importance,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
        )
        database.create_memory(memory)

        # Index in vector store; roll back SQLite row on failure
        vec_meta = {
            "category": category.value if hasattr(category, 'value') else category,
            "importance": importance.value if hasattr(importance, 'value') else importance,
            "source": source or "",
            "updated_at": memory.updated_at.isoformat(),
        }
        try:
            get_memory_store().add_memory(
                memory_id=memory.id, project_id=project_id,
                text=content, metadata=vec_meta,
            )
        except Exception:
            logger.exception("ChromaDB indexing failed for memory %s; rolling back SQLite row", memory.id)
            database.delete_memory(memory.id)
            raise

        return memory

    def search_memories(self, search: MemorySearch) -> List[Dict[str, Any]]:
        if not search.project_id:
            return []

        # Build optional ChromaDB where filter
        where: Optional[Dict] = None
        if search.categories:
            cat_values = [c.value for c in search.categories]
            if len(cat_values) == 1:
                where = {"category": cat_values[0]}
            else:
                where = {"category": {"$in": cat_values}}

        results = get_memory_store().search_memories(
            query=search.query,
            project_id=search.project_id,
            limit=search.limit,
            where=where,
        )

        # Filter by importance minimum if set
        if search.importance_min:
            min_score = IMPORTANCE_SCORES.get(search.importance_min.value, 0)
            results = [
                r for r in results
                if IMPORTANCE_SCORES.get(r["metadata"].get("importance", "medium"), 0.5) >= min_score
            ]

        # Record access for returned results
        for r in results:
            database.record_memory_access(r["id"])

        return results

    def get_memory(self, memory_id: str) -> Optional[MemoryItem]:
        return database.get_memory(memory_id)

    def update_memory(self, memory_id: str, **kwargs) -> Optional[MemoryItem]:
        # Snapshot the current state so we can revert on ChromaDB failure
        old_memory = database.get_memory(memory_id)
        if not old_memory:
            return None

        memory = database.update_memory(memory_id, **kwargs)
        if memory:
            # Re-index in vector store; revert SQLite on failure
            vec_meta = {
                "category": memory.category.value,
                "importance": memory.importance.value,
                "source": memory.source or "",
                "updated_at": memory.updated_at.isoformat(),
            }
            try:
                get_memory_store().add_memory(
                    memory_id=memory.id, project_id=memory.project_id,
                    text=memory.content, metadata=vec_meta,
                )
            except Exception:
                logger.exception("ChromaDB re-index failed for memory %s; reverting SQLite update", memory_id)
                # Revert to old state
                revert_fields = {
                    "content": old_memory.content,
                    "category": old_memory.category,
                    "importance": old_memory.importance,
                    "source": old_memory.source,
                    "tags": old_memory.tags,
                    "metadata": old_memory.metadata,
                }
                database.update_memory(memory_id, **revert_fields)
                raise
        return memory

    def delete_memory(self, memory_id: str) -> bool:
        memory = database.get_memory(memory_id)
        if memory:
            # Delete from ChromaDB first (idempotent, safe to retry)
            try:
                get_memory_store().delete_memory(memory_id, memory.project_id)
            except Exception:
                logger.warning("ChromaDB delete failed for memory %s; proceeding with SQLite delete", memory_id)
            deleted = database.delete_memory(memory_id)
            if not deleted:
                logger.warning("SQLite delete failed for memory %s after ChromaDB delete", memory_id)
            return deleted
        return database.delete_memory(memory_id)

    def get_project_briefing(self, project_id: str) -> Dict[str, Any]:
        project = database.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        memories = database.list_memories(project_id)
        grouped: Dict[str, list] = {}
        for m in memories:
            if m.importance == Importance.ephemeral:
                continue
            cat = m.category.value
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append({
                "id": m.id,
                "content": m.content,
                "importance": m.importance.value,
                "tags": m.tags,
                "updated_at": m.updated_at.isoformat(),
            })

        # Sort each category: critical first
        importance_order = {v: i for i, v in enumerate(IMPORTANCE_SCORES.keys())}
        for cat in grouped:
            grouped[cat].sort(key=lambda x: importance_order.get(x["importance"], 99))

        return {
            "project": project.model_dump(),
            "memory_count": len(memories),
            "categories": grouped,
        }

    # --- Helpers ---

    @staticmethod
    def _detect_git_remote(path: str) -> Optional[str]:
        try:
            result = subprocess.run(
                ["git", "-C", path, "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
