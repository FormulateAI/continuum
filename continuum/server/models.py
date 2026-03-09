import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# --- Legacy models (backward compatible) ---


class ContextItem(BaseModel):
    id: str = ""
    type: str  # "file", "diff", "instruction", "error"
    content: str
    metadata: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.now)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = str(uuid.uuid4())


class Session(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    items: list[ContextItem] = []


class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    filters: dict[str, Any] = {}


# --- V2 models ---


class MemoryCategory(str, Enum):
    architecture = "architecture"
    conventions = "conventions"
    patterns = "patterns"
    debugging = "debugging"
    decisions = "decisions"
    preferences = "preferences"
    general = "general"


class Importance(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    ephemeral = "ephemeral"


class ProjectCreate(BaseModel):
    name: str
    path: str | None = None
    git_remote: str | None = None
    metadata: dict[str, Any] = {}


class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    path: str | None = None
    git_remote: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = {}


class MemoryCreate(BaseModel):
    project_id: str
    content: str
    category: MemoryCategory = MemoryCategory.general
    importance: Importance = Importance.medium
    source: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class MemoryUpdate(BaseModel):
    content: str | None = None
    category: MemoryCategory | None = None
    importance: Importance | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    content: str
    category: MemoryCategory = MemoryCategory.general
    importance: Importance = Importance.medium
    source: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = 0
    last_accessed: datetime | None = None


class MemorySearch(BaseModel):
    query: str
    project_id: str | None = None
    categories: list[MemoryCategory] | None = None
    importance_min: Importance | None = None
    limit: int = 10
