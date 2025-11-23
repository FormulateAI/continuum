from fastapi import FastAPI, HTTPException
from typing import List, Optional
from .models import Session, ContextItem, SearchQuery
from . import database
from .memory import memory_store
import uuid

app = FastAPI(title="Continuum", description="Centralized Context Layer for AI Coding")

# Initialize DB
database.init_db()

# Simple in-memory tracker for "active" session ID for this server instance
# In a real multi-user scenario, this would be per-user or token-based
current_session_id: Optional[str] = None

@app.get("/")
def read_root():
    return {"status": "running", "service": "Continuum", "features": ["vector-search"]}

@app.post("/session/start")
def start_session(name: str):
    global current_session_id
    session = Session(id=str(uuid.uuid4()), name=name)
    database.create_session(session)
    current_session_id = session.id
    return session

@app.get("/session/current")
def get_current_session():
    if not current_session_id:
        raise HTTPException(status_code=404, detail="No active session")
    
    session = database.get_session(current_session_id)
    if session:
        return session
    raise HTTPException(status_code=404, detail="Session not found")

@app.post("/context/add")
def add_context(item: ContextItem):
    if not current_session_id:
        raise HTTPException(status_code=400, detail="No active session. Start one first.")
    
    # Verify session exists
    if database.get_session(current_session_id):
        # 1. Add to SQLite
        database.add_context_item(current_session_id, item)
        
        # 2. Add to Vector Store (Memory)
        # We include session_id in metadata so we can filter by it later if needed
        metadata = item.metadata.copy()
        metadata["session_id"] = current_session_id
        metadata["type"] = item.type
        metadata["timestamp"] = item.timestamp.isoformat()
        
        memory_store.add(id=item.id, text=item.content, metadata=metadata)
        
        return {"status": "added", "item_id": item.id}
            
    raise HTTPException(status_code=404, detail="Session not found")

@app.post("/context/search")
def search_context(query: SearchQuery):
    results = memory_store.search(query.query, query.limit, query.filters)
    return results

@app.get("/context/latest")
def get_latest_context(limit: int = 10):
    if not current_session_id:
        raise HTTPException(status_code=404, detail="No active session")
    
    session = database.get_session(current_session_id)
    if session:
        return session.items[-limit:]
            
    raise HTTPException(status_code=404, detail="Session not found")
