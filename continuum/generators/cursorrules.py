"""Generate .cursorrules from Continuum project memories."""

import os
from typing import Any

from .base import MARKER, BaseFileGenerator


class CursorRulesGenerator(BaseFileGenerator):
    def get_file_path(self, project_dir: str) -> str:
        return os.path.join(project_dir, ".cursorrules")

    def generate(self, memories_by_category: dict[str, list[dict[str, Any]]]) -> str:
        lines = ["# Project Rules (Continuum)", ""]

        order = ["conventions", "architecture", "patterns", "decisions", "debugging", "preferences", "general"]

        for cat in order:
            memories = memories_by_category.get(cat)
            if not memories:
                continue
            lines.append(f"## {cat.title()}")
            lines.append("")
            for m in memories:
                lines.append(f"- {m['content']}")
            lines.append("")

        return "\n".join(lines)

    def parse_user_content(self, file_content: str) -> str:
        if MARKER in file_content:
            return file_content.split(MARKER)[0]
        return file_content
