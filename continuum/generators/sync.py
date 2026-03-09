"""Bidirectional sync between Continuum memories and tool config files."""

import hashlib
from typing import Any

from continuum.server.models import Importance, MemoryCategory

from .claude_md import ClaudeMdGenerator
from .cursorrules import CursorRulesGenerator

GENERATORS = {
    "claude": ClaudeMdGenerator(),
    "cursor": CursorRulesGenerator(),
}


class SyncManager:
    def __init__(self, service):
        self.service = service

    def generate(self, project_id: str, project_dir: str, target: str) -> str | None:
        gen = GENERATORS.get(target)
        if not gen:
            return None

        briefing = self.service.get_project_briefing(project_id)
        categories = briefing.get("categories", {})
        if not categories:
            return None

        managed = gen.generate(categories)
        filepath = gen.get_file_path(project_dir)

        existing = gen.read_existing(filepath)
        user_content = ""
        if existing:
            user_content = gen.parse_user_content(existing)

        full = gen.build_full_content(user_content, managed)
        gen.write(filepath, full)
        return filepath

    def sync(self, project_id: str, project_dir: str, target: str) -> dict[str, Any]:
        gen = GENERATORS.get(target)
        if not gen:
            return {}

        result: dict[str, Any] = {}
        filepath = gen.get_file_path(project_dir)
        existing = gen.read_existing(filepath)

        # --- Inbound: parse user content above marker, ingest as memories ---
        if existing and gen.detect_marker(existing):
            user_content = gen.parse_user_content(existing).strip()
            if user_content:
                ingested = self._ingest_user_content(project_id, user_content, target)
                if ingested:
                    result["ingested"] = ingested

        # --- Outbound: generate managed section ---
        outpath = self.generate(project_id, project_dir, target)
        if outpath:
            result["generated"] = outpath

        return result

    def _ingest_user_content(self, project_id: str, content: str, source: str) -> int:
        """Parse user-written lines and store as memories if they're new."""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        count = 0

        for line in lines:
            # Skip headings and empty markers
            if line.startswith("#") or line.startswith("<!--"):
                continue
            # Strip leading bullet
            text = line.lstrip("-*").strip()
            if not text or len(text) < 5:
                continue

            # Check for duplicates via content hash
            content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
            existing = self.service.search_memories(_build_search(text, project_id, limit=1))
            # If top result is very similar (high score), skip
            if existing and existing[0].get("score", 0) > 0.85:
                continue

            self.service.store_memory(
                project_id=project_id,
                content=text,
                category=MemoryCategory.general,
                importance=Importance.medium,
                source=f"file-sync:{source}",
                metadata={"content_hash": content_hash},
            )
            count += 1

        return count


def _build_search(query: str, project_id: str, limit: int = 1):
    from continuum.server.models import MemorySearch

    return MemorySearch(query=query, project_id=project_id, limit=limit)
