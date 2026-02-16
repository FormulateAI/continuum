import requests
import os
from typing import Optional, Dict, Any, List

from continuum.server.config import CONTINUUM_PORT


class ContinuumClient:
    def __init__(self, server_url: str = None):
        if server_url is None:
            server_url = f"http://localhost:{CONTINUUM_PORT}"
        self.server_url = server_url
        self.project_id: Optional[str] = None

    def connect(self):
        """Check connection to the server."""
        try:
            response = requests.get(f"{self.server_url}/")
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def get_or_create_project(self, name: str, path: Optional[str] = None) -> Dict[str, Any]:
        """Create or retrieve a project, storing its ID for subsequent calls."""
        payload: Dict[str, Any] = {"name": name}
        if path:
            payload["path"] = os.path.abspath(path)
        response = requests.post(f"{self.server_url}/v2/projects", json=payload)
        response.raise_for_status()
        project = response.json()
        self.project_id = project["id"]
        return project

    def push_checkpoint(self, summary: str, details: str = "",
                        metadata: Dict[str, Any] = None,
                        category: str = "general",
                        importance: str = "medium") -> bool:
        """Push a memory checkpoint to Continuum via v2 API."""
        if not self.project_id:
            print("Warning: No project set. Call get_or_create_project() first.")
            return False

        content = f"{summary}\n\n{details}".strip() if details else summary

        payload: Dict[str, Any] = {
            "project_id": self.project_id,
            "content": content,
            "category": category,
            "importance": importance,
            "source": "agent_sdk",
            "tags": [],
            "metadata": metadata or {},
        }

        try:
            response = requests.post(f"{self.server_url}/v2/memories", json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Warning: Failed to push checkpoint to Continuum: {e}")
            return False

    def search_memory(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Search for relevant memories via v2 API."""
        if not self.project_id:
            print("Warning: No project set. Call get_or_create_project() first.")
            return []

        payload: Dict[str, Any] = {
            "query": query,
            "project_id": self.project_id,
            "limit": limit,
        }
        try:
            response = requests.post(f"{self.server_url}/v2/memories/search", json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Warning: Failed to search Continuum: {e}")
            return []


# Global instance for easy import
hub = ContinuumClient()
