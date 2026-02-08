"""Abstract base class for tool-specific file generators."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


MARKER = "<!-- CONTINUUM:MANAGED - DO NOT EDIT BELOW THIS LINE -->"


class BaseFileGenerator(ABC):
    @abstractmethod
    def get_file_path(self, project_dir: str) -> str:
        """Return the absolute path to the generated file."""
        ...

    @abstractmethod
    def generate(self, memories_by_category: Dict[str, List[Dict[str, Any]]]) -> str:
        """Generate the managed section content from memories."""
        ...

    @abstractmethod
    def parse_user_content(self, file_content: str) -> str:
        """Extract user-written content above the marker."""
        ...

    def detect_marker(self, file_content: str) -> bool:
        """Check if the file already has a Continuum marker."""
        return MARKER in file_content

    def build_full_content(self, user_content: str,
                           managed_content: str) -> str:
        """Combine user content and managed section."""
        parts = []
        if user_content.strip():
            parts.append(user_content.rstrip())
            parts.append("")
        parts.append(MARKER)
        parts.append("")
        parts.append(managed_content.rstrip())
        parts.append("")
        return "\n".join(parts)

    def read_existing(self, filepath: str) -> Optional[str]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return None

    def write(self, filepath: str, content: str):
        import os
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
