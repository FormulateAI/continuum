import sqlite3
import json
from datetime import datetime
from typing import List, Optional
from .models import Session, ContextItem

DB_PATH = "continuum.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS context_items
                 (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, content TEXT, 
                  metadata TEXT, timestamp TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id))''')
    conn.commit()
    conn.close()

def create_session(session: Session):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions VALUES (?, ?, ?)", 
              (session.id, session.name, session.created_at.isoformat()))
    conn.commit()
    conn.close()

def get_session(session_id: str) -> Optional[Session]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    if not row:
        return None
    
    session = Session(id=row[0], name=row[1], created_at=datetime.fromisoformat(row[2]))
    
    # Load items
    c.execute("SELECT * FROM context_items WHERE session_id = ? ORDER BY timestamp", (session_id,))
    items = []
    for item_row in c.fetchall():
        items.append(ContextItem(
            id=item_row[0],
            type=item_row[2],
            content=item_row[3],
            metadata=json.loads(item_row[4]),
            timestamp=datetime.fromisoformat(item_row[5])
        ))
    session.items = items
    conn.close()
    return session

def add_context_item(session_id: str, item: ContextItem):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO context_items VALUES (?, ?, ?, ?, ?, ?)",
              (item.id, session_id, item.type, item.content, 
               json.dumps(item.metadata), item.timestamp.isoformat()))
    conn.commit()
    conn.close()
