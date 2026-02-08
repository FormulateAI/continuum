from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


# --- Legacy models (backward compatible) ---

class ContextItem(BaseModel):
    id: str = ""
    type: str  # "file", "diff", "instruction", "error"
    content: str
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.now)

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = str(uuid.uuid4())

class Session(BaseModel):
    id: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    items: List[ContextItem] = []

class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    filters: Dict[str, Any] = {}


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
    path: Optional[str] = None
    git_remote: Optional[str] = None
    metadata: Dict[str, Any] = {}

class Project(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    path: Optional[str] = None
    git_remote: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = {}


class MemoryCreate(BaseModel):
    project_id: str
    content: str
    category: MemoryCategory = MemoryCategory.general
    importance: Importance = Importance.medium
    source: Optional[str] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}

class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[MemoryCategory] = None
    importance: Optional[Importance] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    content: str
    category: MemoryCategory = MemoryCategory.general
    importance: Importance = Importance.medium
    source: Optional[str] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    access_count: int = 0
    last_accessed: Optional[datetime] = None

class MemorySearch(BaseModel):
    query: str
    project_id: Optional[str] = None
    categories: Optional[List[MemoryCategory]] = None
    importance_min: Optional[Importance] = None
    limit: int = 10
