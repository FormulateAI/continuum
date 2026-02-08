"""Legacy v1 endpoints — preserved for backward compatibility."""

from fastapi import APIRouter, HTTPException
from typing import Optional
from ..models import Session, ContextItem, SearchQuery
from .. import database
from ..memory import memory_store
import uuid

router = APIRouter()

current_session_id: Optional[str] = None


@router.post("/session/start")
def start_session(name: str):
    global current_session_id
    session = Session(id=str(uuid.uuid4()), name=name)
    database.create_session(session)
    current_session_id = session.id
    return session


@router.get("/session/current")
def get_current_session():
    if not current_session_id:
        raise HTTPException(status_code=404, detail="No active session")
    session = database.get_session(current_session_id)
    if session:
        return session
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/context/add")
def add_context(item: ContextItem):
    if not current_session_id:
        raise HTTPException(status_code=400, detail="No active session. Start one first.")
    if database.get_session(current_session_id):
        database.add_context_item(current_session_id, item)
        metadata = item.metadata.copy()
        metadata["session_id"] = current_session_id
        metadata["type"] = item.type
        metadata["timestamp"] = item.timestamp.isoformat()
        memory_store.add(id=item.id, text=item.content, metadata=metadata)
        return {"status": "added", "item_id": item.id}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/context/search")
def search_context(query: SearchQuery):
    results = memory_store.search(query.query, query.limit, query.filters)
    return results


@router.get("/context/latest")
def get_latest_context(limit: int = 10):
    if not current_session_id:
        raise HTTPException(status_code=404, detail="No active session")
    session = database.get_session(current_session_id)
    if session:
        return session.items[-limit:]
    raise HTTPException(status_code=404, detail="Session not found")
