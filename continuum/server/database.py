import json
import sqlite3
import threading
from datetime import datetime

from .config import DB_PATH, IMPORTANCE_SCORES, ensure_directories
from .models import (
    ContextItem,
    Importance,
    MemoryCategory,
    MemoryItem,
    Project,
    Session,
)

SCHEMA_VERSION = 1

# Module-level connection pool: one connection per thread for write serialization
_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            # Connection was closed; create a new one
            pass
    ensure_directories()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _local.conn = conn
    return conn


def init_db():
    conn = _connect()
    c = conn.cursor()

    # Legacy tables
    c.execute("""CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS context_items
                 (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, content TEXT,
                  metadata TEXT, timestamp TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id))""")

    # Schema version tracking
    c.execute("""CREATE TABLE IF NOT EXISTS schema_version
                 (version INTEGER PRIMARY KEY, applied_at TEXT)""")

    # V2 tables
    c.execute("""CREATE TABLE IF NOT EXISTS projects
                 (id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  path TEXT,
                  git_remote TEXT,
                  created_at TEXT NOT NULL,
                  metadata TEXT DEFAULT '{}')""")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_path ON projects(path) WHERE path IS NOT NULL")
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_git_remote ON projects(git_remote) WHERE git_remote IS NOT NULL"
    )  # noqa: E501

    c.execute("""CREATE TABLE IF NOT EXISTS memories
                 (id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  content TEXT NOT NULL,
                  category TEXT NOT NULL DEFAULT 'general',
                  importance TEXT NOT NULL DEFAULT 'medium',
                  source TEXT,
                  tags TEXT DEFAULT '[]',
                  metadata TEXT DEFAULT '{}',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  access_count INTEGER DEFAULT 0,
                  last_accessed TEXT,
                  FOREIGN KEY(project_id) REFERENCES projects(id))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)")

    # Record schema version
    c.execute("INSERT OR IGNORE INTO schema_version VALUES (?, ?)", (SCHEMA_VERSION, datetime.utcnow().isoformat()))

    conn.commit()


# --- Legacy functions (unchanged) ---


def create_session(session: Session):
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT INTO sessions VALUES (?, ?, ?)", (session.id, session.name, session.created_at.isoformat()))
    conn.commit()


def get_session(session_id: str) -> Session | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
    row = c.fetchone()
    if not row:
        return None

    session = Session(id=row[0], name=row[1], created_at=datetime.fromisoformat(row[2]))

    c.execute("SELECT * FROM context_items WHERE session_id = ? ORDER BY timestamp", (session_id,))
    items = []
    for item_row in c.fetchall():
        items.append(
            ContextItem(
                id=item_row[0],
                type=item_row[2],
                content=item_row[3],
                metadata=json.loads(item_row[4]),
                timestamp=datetime.fromisoformat(item_row[5]),
            )
        )
    session.items = items
    return session


def add_context_item(session_id: str, item: ContextItem):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO context_items VALUES (?, ?, ?, ?, ?, ?)",
        (item.id, session_id, item.type, item.content, json.dumps(item.metadata), item.timestamp.isoformat()),
    )
    conn.commit()


# --- V2 Project functions ---


def find_or_create_project(
    name: str, path: str | None = None, git_remote: str | None = None, metadata: dict | None = None
) -> Project:
    conn = _connect()
    c = conn.cursor()

    # Try to find by path first, then git_remote
    if path:
        c.execute("SELECT * FROM projects WHERE path = ?", (path,))
        row = c.fetchone()
        if row:
            return _row_to_project(row)

    if git_remote:
        c.execute("SELECT * FROM projects WHERE git_remote = ?", (git_remote,))
        row = c.fetchone()
        if row:
            return _row_to_project(row)

    # Create new project
    import uuid

    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        path=path,
        git_remote=git_remote,
        metadata=metadata or {},
    )
    c.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
        (
            project.id,
            project.name,
            project.path,
            project.git_remote,
            project.created_at.isoformat(),
            json.dumps(project.metadata),
        ),
    )
    conn.commit()
    return project


def get_project(project_id: str) -> Project | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = c.fetchone()
    if not row:
        return None
    return _row_to_project(row)


def list_projects() -> list[Project]:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = c.fetchall()
    return [_row_to_project(r) for r in rows]


def _row_to_project(row) -> Project:
    return Project(
        id=row[0],
        name=row[1],
        path=row[2],
        git_remote=row[3],
        created_at=datetime.fromisoformat(row[4]),
        metadata=json.loads(row[5]) if row[5] else {},
    )


# --- V2 Memory functions ---


def create_memory(memory: MemoryItem) -> MemoryItem:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            memory.id,
            memory.project_id,
            memory.content,
            memory.category.value,
            memory.importance.value,
            memory.source,
            json.dumps(memory.tags),
            json.dumps(memory.metadata),
            memory.created_at.isoformat(),
            memory.updated_at.isoformat(),
            memory.access_count,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
        ),
    )
    conn.commit()
    return memory


def get_memory(memory_id: str) -> MemoryItem | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
    row = c.fetchone()
    if not row:
        return None
    return _row_to_memory(row)


def update_memory(memory_id: str, **kwargs) -> MemoryItem | None:
    conn = _connect()
    c = conn.cursor()

    updates = []
    values = []
    for key, val in kwargs.items():
        if val is None:
            continue
        if key == "tags":
            updates.append("tags = ?")
            values.append(json.dumps(val))
        elif key == "metadata":
            updates.append("metadata = ?")
            values.append(json.dumps(val))
        elif key in ("category", "importance") and hasattr(val, "value"):
            updates.append(f"{key} = ?")
            values.append(val.value)
        else:
            updates.append(f"{key} = ?")
            values.append(val)

    if not updates:
        return get_memory(memory_id)

    updates.append("updated_at = ?")
    values.append(datetime.utcnow().isoformat())
    values.append(memory_id)

    c.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    return get_memory(memory_id)


def delete_memory(memory_id: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    deleted = c.rowcount > 0
    conn.commit()
    return deleted


def list_memories(
    project_id: str, category: str | None = None, importance_min: str | None = None, limit: int = 100
) -> list[MemoryItem]:
    conn = _connect()
    c = conn.cursor()

    query = "SELECT * FROM memories WHERE project_id = ?"
    params: list = [project_id]

    if category:
        query += " AND category = ?"
        params.append(category)

    if importance_min:
        min_score = IMPORTANCE_SCORES.get(importance_min, 0)
        matching = [k for k, v in IMPORTANCE_SCORES.items() if v >= min_score]
        placeholders = ",".join("?" * len(matching))
        query += f" AND importance IN ({placeholders})"
        params.extend(matching)

    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    rows = c.fetchall()
    return [_row_to_memory(r) for r in rows]


def record_memory_access(memory_id: str):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?", (now, memory_id))
    conn.commit()


def _row_to_memory(row) -> MemoryItem:
    return MemoryItem(
        id=row[0],
        project_id=row[1],
        content=row[2],
        category=MemoryCategory(row[3]),
        importance=Importance(row[4]),
        source=row[5],
        tags=json.loads(row[6]) if row[6] else [],
        metadata=json.loads(row[7]) if row[7] else {},
        created_at=datetime.fromisoformat(row[8]),
        updated_at=datetime.fromisoformat(row[9]),
        access_count=row[10] or 0,
        last_accessed=datetime.fromisoformat(row[11]) if row[11] else None,
    )
