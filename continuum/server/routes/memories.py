"""V2 Memory endpoints."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from ...core.service import ContinuumService
from ..models import MemoryCreate, MemoryUpdate, MemoryItem, MemorySearch

router = APIRouter(prefix="/v2/memories", tags=["memories"])
service = ContinuumService()


@router.post("", response_model=MemoryItem)
def create_memory(body: MemoryCreate):
    project = service.get_project(body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return service.store_memory(
        project_id=body.project_id,
        content=body.content,
        category=body.category,
        importance=body.importance,
        source=body.source,
        tags=body.tags,
        metadata=body.metadata,
    )


@router.get("/{memory_id}", response_model=MemoryItem)
def get_memory(memory_id: str):
    memory = service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.put("/{memory_id}", response_model=MemoryItem)
def update_memory(memory_id: str, body: MemoryUpdate):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    memory = service.update_memory(memory_id, **updates)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/{memory_id}")
def delete_memory(memory_id: str):
    if not service.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"status": "deleted", "id": memory_id}


@router.post("/search")
def search_memories(body: MemorySearch):
    return service.search_memories(body)


# Project context briefing
context_router = APIRouter(prefix="/v2/projects", tags=["projects"])


@context_router.get("/{project_id}/context")
def get_project_context(project_id: str) -> Dict[str, Any]:
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return service.get_project_briefing(project_id)
