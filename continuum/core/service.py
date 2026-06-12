"""Shared business logic for Continuum — used by FastAPI routes, MCP tools, and SDK."""

import logging
import os
import subprocess
from typing import Any

from continuum.server import database
from continuum.server.config import IMPORTANCE_SCORES
from continuum.server.memory import get_memory_store
from continuum.server.models import (
    Importance,
    MemoryCategory,
    MemoryItem,
    MemorySearch,
    Org,
    OrgCreate,
    Project,
    Scope,
)

logger = logging.getLogger(__name__)


class ContinuumService:
    def __init__(self):
        database.init_db()

    # --- Orgs ---

    def create_org(self, data: OrgCreate) -> Org:
        org = Org(name=data.name, slug=data.slug, metadata=data.metadata)
        return database.create_org(org)

    def get_org(self, org_id: str) -> Org | None:
        return database.get_org(org_id)

    def get_org_by_slug(self, slug: str) -> Org | None:
        return database.get_org_by_slug(slug)

    def list_orgs(self) -> list[Org]:
        return database.list_orgs()

    def link_project_to_org(self, project_id: str, org_id: str) -> bool:
        return database.update_project_org(project_id, org_id)

    # --- Projects ---

    def find_or_create_project(
        self,
        name: str | None = None,
        path: str | None = None,
        git_remote: str | None = None,
        metadata: dict | None = None,
        org_id: str | None = None,
    ) -> Project:
        if path:
            path = os.path.abspath(path)
        if not git_remote and path:
            git_remote = self._detect_git_remote(path)
        if not name:
            name = os.path.basename(path) if path else "unnamed"
        return database.find_or_create_project(
            name=name,
            path=path,
            git_remote=git_remote,
            metadata=metadata,
            org_id=org_id,
        )

    def get_project(self, project_id: str) -> Project | None:
        return database.get_project(project_id)

    def list_projects(self, org_id: str | None = None) -> list[Project]:
        return database.list_projects(org_id=org_id)

    # --- Memories ---

    def store_memory(
        self,
        project_id: str | None,
        content: str,
        category: MemoryCategory = MemoryCategory.general,
        importance: Importance = Importance.medium,
        source: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        scope: Scope = Scope.project,
        org_id: str | None = None,
    ) -> MemoryItem:
        memory = MemoryItem(
            project_id=project_id,
            org_id=org_id,
            scope=scope,
            content=content,
            category=category,
            importance=importance,
            source=source,
            tags=tags or [],
            metadata=metadata or {},
        )
        database.create_memory(memory)

        vec_meta = {
            "category": category.value if hasattr(category, "value") else category,
            "importance": importance.value if hasattr(importance, "value") else importance,
            "source": source or "",
            "updated_at": memory.updated_at.isoformat(),
        }
        try:
            if scope == Scope.org and org_id:
                get_memory_store().add_org_memory(
                    memory_id=memory.id,
                    org_id=org_id,
                    text=content,
                    metadata=vec_meta,
                )
            elif project_id:
                get_memory_store().add_memory(
                    memory_id=memory.id,
                    project_id=project_id,
                    text=content,
                    metadata=vec_meta,
                )
        except Exception:
            logger.exception("pgvector indexing failed for memory %s; rolling back Postgres row", memory.id)
            database.delete_memory(memory.id)
            raise

        return memory

    def store_org_memory(
        self,
        org_id: str,
        content: str,
        category: MemoryCategory = MemoryCategory.general,
        importance: Importance = Importance.medium,
        source: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        return self.store_memory(
            project_id=None,
            content=content,
            category=category,
            importance=importance,
            source=source,
            tags=tags,
            metadata=metadata,
            scope=Scope.org,
            org_id=org_id,
        )

    def search_memories(self, search: MemorySearch) -> list[dict[str, Any]]:
        if not search.project_id and not search.org_id:
            return []

        where: dict | None = None
        if search.categories:
            cat_values = [c.value for c in search.categories]
            if len(cat_values) == 1:
                where = {"category": cat_values[0]}
            else:
                where = {"category": {"$in": cat_values}}

        results = []

        # Project-level search
        if search.project_id:
            project_results = get_memory_store().search_memories(
                query=search.query,
                project_id=search.project_id,
                limit=search.limit,
                where=where,
            )
            for r in project_results:
                r["scope"] = "project"
            results.extend(project_results)

        # Org-level fallback / addition
        if search.include_org and search.org_id:
            org_results = get_memory_store().search_org_memories(
                query=search.query,
                org_id=search.org_id,
                limit=search.limit,
                where=where,
            )
            for r in org_results:
                r["scope"] = "org"
            results.extend(org_results)
        elif search.include_org and search.project_id:
            # Look up the project's org
            project = database.get_project(search.project_id)
            if project and project.org_id:
                org_results = get_memory_store().search_org_memories(
                    query=search.query,
                    org_id=project.org_id,
                    limit=search.limit,
                    where=where,
                )
                for r in org_results:
                    r["scope"] = "org"
                results.extend(org_results)

        # Filter by importance minimum
        if search.importance_min:
            min_score = IMPORTANCE_SCORES.get(search.importance_min.value, 0)
            results = [
                r for r in results if IMPORTANCE_SCORES.get(r["metadata"].get("importance", "medium"), 0.5) >= min_score
            ]

        # Deduplicate and re-rank
        seen = set()
        unique = []
        for r in results:
            if r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Record access
        for r in unique[: search.limit]:
            database.record_memory_access(r["id"])

        return unique[: search.limit]

    def get_memory(self, memory_id: str) -> MemoryItem | None:
        return database.get_memory(memory_id)

    def update_memory(self, memory_id: str, **kwargs) -> MemoryItem | None:
        old_memory = database.get_memory(memory_id)
        if not old_memory:
            return None

        memory = database.update_memory(memory_id, **kwargs)
        if memory:
            vec_meta = {
                "category": memory.category.value,
                "importance": memory.importance.value,
                "source": memory.source or "",
                "updated_at": memory.updated_at.isoformat(),
            }
            try:
                if memory.scope == Scope.org and memory.org_id:
                    get_memory_store().add_org_memory(
                        memory_id=memory.id,
                        org_id=memory.org_id,
                        text=memory.content,
                        metadata=vec_meta,
                    )
                elif memory.project_id:
                    get_memory_store().add_memory(
                        memory_id=memory.id,
                        project_id=memory.project_id,
                        text=memory.content,
                        metadata=vec_meta,
                    )
            except Exception:
                logger.exception("pgvector re-index failed for memory %s; reverting Postgres update", memory_id)
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
            try:
                if memory.scope == Scope.org and memory.org_id:
                    get_memory_store().delete_org_memory(memory_id, memory.org_id)
                elif memory.project_id:
                    get_memory_store().delete_memory(memory_id, memory.project_id)
            except Exception:
                logger.warning("pgvector delete failed for memory %s; proceeding with Postgres delete", memory_id)
            deleted = database.delete_memory(memory_id)
            return deleted
        return database.delete_memory(memory_id)

    def get_project_briefing(self, project_id: str) -> dict[str, Any]:
        project = database.get_project(project_id)
        if not project:
            return {"error": "Project not found"}

        memories = database.list_memories(project_id=project_id)
        grouped: dict[str, list] = {}
        for m in memories:
            if m.importance == Importance.ephemeral:
                continue
            cat = m.category.value
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(
                {
                    "id": m.id,
                    "content": m.content,
                    "importance": m.importance.value,
                    "tags": m.tags,
                    "updated_at": m.updated_at.isoformat(),
                    "scope": m.scope.value if hasattr(m.scope, "value") else m.scope,
                }
            )

        importance_order = {v: i for i, v in enumerate(IMPORTANCE_SCORES.keys())}
        for cat in grouped:
            grouped[cat].sort(key=lambda x: importance_order.get(x["importance"], 99))

        org_categories: dict[str, list] = {}
        if project.org_id:
            org_memories = database.list_memories(org_id=project.org_id, scope="org")
            for m in org_memories:
                if m.importance == Importance.ephemeral:
                    continue
                cat = m.category.value
                if cat not in org_categories:
                    org_categories[cat] = []
                org_categories[cat].append(
                    {
                        "id": m.id,
                        "content": m.content,
                        "importance": m.importance.value,
                        "tags": m.tags,
                        "updated_at": m.updated_at.isoformat(),
                        "scope": "org",
                    }
                )

        return {
            "project": project.model_dump(),
            "memory_count": len(memories),
            "categories": grouped,
            "org_categories": org_categories,
        }

    # --- Helpers ---

    @staticmethod
    def _detect_git_remote(path: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", path, "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None
