from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class ContextItem(BaseModel):
    id: str = ""
    type: str  # "file", "diff", "instruction", "error"
    content: str
    metadata: Dict[str, Any] = {}
    timestamp: datetime = datetime.now()

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = str(uuid.uuid4())

class Session(BaseModel):
    id: str
    name: str
    created_at: datetime = datetime.now()
    items: List[ContextItem] = []

class SearchQuery(BaseModel):
    query: str
    limit: int = 5
    filters: Dict[str, Any] = {}
