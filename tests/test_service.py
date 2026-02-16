"""Tests for ContinuumService with isolated temp storage."""

import os
import tempfile
import pytest

# Override storage paths before any continuum imports
_tmpdir = tempfile.mkdtemp(prefix="continuum_test_")
os.environ["CONTINUUM_HOME"] = _tmpdir
os.environ["CONTINUUM_DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["CONTINUUM_CHROMA_PATH"] = os.path.join(_tmpdir, "chroma_db")

from continuum.core.service import ContinuumService
from continuum.server.models import MemoryCategory, Importance, MemorySearch


@pytest.fixture(autouse=True)
def service():
    """Provide a fresh ContinuumService instance (shares the temp DB across tests)."""
    return ContinuumService()


class TestProjects:
    def test_create_project(self, service):
        project = service.find_or_create_project(name="test-proj", path=_tmpdir)
        assert project.name == "test-proj"
        assert project.id

    def test_idempotent_creation(self, service):
        p1 = service.find_or_create_project(name="idempotent", path=_tmpdir)
        p2 = service.find_or_create_project(name="idempotent", path=_tmpdir)
        assert p1.id == p2.id

    def test_get_project(self, service):
        p = service.find_or_create_project(name="get-test", path=os.path.join(_tmpdir, "get-test"))
        fetched = service.get_project(p.id)
        assert fetched is not None
        assert fetched.name == "get-test"

    def test_list_projects(self, service):
        projects = service.list_projects()
        assert isinstance(projects, list)


class TestMemories:
    def _ensure_project(self, service):
        return service.find_or_create_project(name="mem-test", path=os.path.join(_tmpdir, "mem-test"))

    def test_store_memory(self, service):
        project = self._ensure_project(service)
        memory = service.store_memory(
            project_id=project.id,
            content="Use pytest for all tests",
            category=MemoryCategory.conventions,
            importance=Importance.high,
        )
        assert memory.id
        assert memory.content == "Use pytest for all tests"
        assert memory.category == MemoryCategory.conventions
        assert memory.importance == Importance.high

    def test_get_memory(self, service):
        project = self._ensure_project(service)
        stored = service.store_memory(
            project_id=project.id,
            content="Retrieve this memory",
        )
        fetched = service.get_memory(stored.id)
        assert fetched is not None
        assert fetched.content == "Retrieve this memory"

    def test_update_memory(self, service):
        project = self._ensure_project(service)
        memory = service.store_memory(
            project_id=project.id,
            content="Before update",
        )
        updated = service.update_memory(memory.id, content="After update")
        assert updated is not None
        assert updated.content == "After update"

    def test_delete_memory(self, service):
        project = self._ensure_project(service)
        memory = service.store_memory(
            project_id=project.id,
            content="Delete me",
        )
        assert service.delete_memory(memory.id) is True
        assert service.get_memory(memory.id) is None

    def test_search_memories(self, service):
        project = self._ensure_project(service)
        service.store_memory(
            project_id=project.id,
            content="We use snake_case for Python function names",
            category=MemoryCategory.conventions,
        )
        search = MemorySearch(query="naming conventions python", project_id=project.id)
        results = service.search_memories(search)
        assert isinstance(results, list)
        # The memory should appear in results
        assert any("snake_case" in r["content"] for r in results)

    def test_project_briefing(self, service):
        project = self._ensure_project(service)
        service.store_memory(
            project_id=project.id,
            content="Architecture: microservices",
            category=MemoryCategory.architecture,
            importance=Importance.high,
        )
        briefing = service.get_project_briefing(project.id)
        assert "categories" in briefing
        assert briefing["memory_count"] > 0

    def test_briefing_filters_ephemeral(self, service):
        project = self._ensure_project(service)
        service.store_memory(
            project_id=project.id,
            content="Ephemeral note",
            importance=Importance.ephemeral,
        )
        briefing = service.get_project_briefing(project.id)
        # Ephemeral memories should not appear in categorized briefing
        for memories in briefing["categories"].values():
            for m in memories:
                assert m["importance"] != "ephemeral"
