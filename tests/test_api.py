"""Tests for the Continuum FastAPI endpoints using TestClient."""

import os
import tempfile

# Override storage paths before any continuum imports
_tmpdir = tempfile.mkdtemp(prefix="continuum_api_test_")
os.environ["CONTINUUM_HOME"] = _tmpdir
os.environ["CONTINUUM_DB_PATH"] = os.path.join(_tmpdir, "test.db")
os.environ["CONTINUUM_CHROMA_PATH"] = os.path.join(_tmpdir, "chroma_db")

from fastapi.testclient import TestClient

from continuum.server.main import app

client = TestClient(app)


def _create_project(name: str = "api-test-project") -> dict:
    path = tempfile.mkdtemp(prefix=f"{name}_", dir=_tmpdir)
    resp = client.post("/v2/projects", json={"name": name, "path": path})
    assert resp.status_code == 200
    return resp.json()


def _create_memory(project: dict | None = None) -> tuple[dict, dict]:
    if project is None:
        project = _create_project("mem-api-test")
    resp = client.post(
        "/v2/memories",
        json={
            "project_id": project["id"],
            "content": "Always use type hints",
            "category": "conventions",
            "importance": "high",
        },
    )
    assert resp.status_code == 200
    return resp.json(), project


class TestHealth:
    def test_root_returns_status(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert "version" in data


class TestProjects:
    def test_create_project(self):
        data = _create_project()
        assert data["name"] == "api-test-project"
        assert data["id"]

    def test_list_projects(self):
        resp = client.get("/v2/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_project(self):
        created = _create_project()
        resp = client.get(f"/v2/projects/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_nonexistent_project(self):
        resp = client.get("/v2/projects/nonexistent-id")
        assert resp.status_code == 404


class TestMemories:
    def test_create_memory(self):
        data, _ = _create_memory()
        assert data["content"] == "Always use type hints"
        assert data["category"] == "conventions"

    def test_get_memory(self):
        memory, _ = _create_memory()
        resp = client.get(f"/v2/memories/{memory['id']}")
        assert resp.status_code == 200
        assert resp.json()["content"] == "Always use type hints"

    def test_update_memory(self):
        memory, _ = _create_memory()
        resp = client.put(
            f"/v2/memories/{memory['id']}",
            json={
                "content": "Updated content",
                "importance": "critical",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Updated content"
        assert data["importance"] == "critical"

    def test_delete_memory(self):
        memory, _ = _create_memory()
        resp = client.delete(f"/v2/memories/{memory['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

        resp = client.get(f"/v2/memories/{memory['id']}")
        assert resp.status_code == 404

    def test_create_memory_invalid_project(self):
        resp = client.post(
            "/v2/memories",
            json={
                "project_id": "nonexistent",
                "content": "Should fail",
            },
        )
        assert resp.status_code == 404

    def test_search_memories(self):
        memory, project = _create_memory()
        resp = client.post(
            "/v2/memories/search",
            json={
                "query": "type hints conventions",
                "project_id": project["id"],
                "limit": 5,
            },
        )
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert any("type hints" in r["content"] for r in results)

    def test_project_context(self):
        _, project = _create_memory()
        resp = client.get(f"/v2/projects/{project['id']}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert data["memory_count"] > 0
