import requests
import os
from typing import Optional, Dict, Any

class ContinuumClient:
    def __init__(self, server_url: str = "http://localhost:8000"):
        self.server_url = server_url
        self.session_id = None

    def connect(self):
        """Check connection to the server."""
        try:
            response = requests.get(f"{self.server_url}/")
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False

    def push_checkpoint(self, summary: str, details: str = "", metadata: Dict[str, Any] = None):
        """
        Push a 'checkpoint' to Continuum.
        Use this when you complete a meaningful task.
        """
        if metadata is None:
            metadata = {}
        
        metadata["source"] = "agent_sdk"
        metadata["type"] = "checkpoint"
        
        payload = {
            "type": "checkpoint",
            "content": f"{summary}\n\n{details}",
            "metadata": metadata
        }
        
        try:
            response = requests.post(f"{self.server_url}/context/add", json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Warning: Failed to push checkpoint to Continuum: {e}")
            return False

    def search_memory(self, query: str, limit: int = 3):
        """
        Search for relevant past context to help with the current task.
        """
        payload = {"query": query, "limit": limit}
        try:
            response = requests.post(f"{self.server_url}/context/search", json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Warning: Failed to search Continuum: {e}")
            return []

# Global instance for easy import
hub = ContinuumClient()
