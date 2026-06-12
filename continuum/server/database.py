import json
import threading
from datetime import datetime

import psycopg2
import psycopg2.extras

from .config import DATABASE_URL, EMBEDDING_DIM, IMPORTANCE_SCORES
from .models import (
    ContextItem,
    ExtractionCandidate,
    ExtractionRun,
    Importance,
    MemoryCategory,
    MemoryItem,
    Org,
    Project,
    Scope,
    Session,
)

SCHEMA_VERSION = 3  # Incremented for Postgres + pgvector migration

_local = threading.local()

# Built at module load time so the EMBEDDING_DIM f-string only runs once
_CREATE_MEMORIES_SQL = (
    "CREATE TABLE IF NOT EXISTS memories "
    "(id TEXT PRIMARY KEY, project_id TEXT, content TEXT NOT NULL, "
    "category TEXT NOT NULL DEFAULT 'general', importance TEXT NOT NULL DEFAULT 'medium', "
    "source TEXT, tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}', "
    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "access_count INTEGER DEFAULT 0, last_accessed TEXT, "
    "scope TEXT NOT NULL DEFAULT 'project', "
    "org_id TEXT REFERENCES orgs(id), "
    f"embedding vector({EMBEDDING_DIM}))"
)


def _connect() -> psycopg2.extensions.connection:
    conn = getattr(_local, "conn", None)
    if conn is not None and not conn.closed:
        try:
            with conn.cursor() as c:
                c.execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    from pgvector.psycopg2 import register_vector
    register_vector(conn)
    _local.conn = conn
    return conn


def _column_exists(c, table_name: str, col_name: str) -> bool:
    c.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = %s AND column_name = %s",
        (table_name, col_name),
    )
    return c.fetchone() is not None


def init_db():
    conn = _connect()
    c = conn.cursor()
    try:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except Exception:
        conn.rollback()
        conn = _connect()
        c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS sessions
                 (id TEXT PRIMARY KEY, name TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS context_items
                 (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, content TEXT,
                  metadata TEXT, timestamp TEXT,
                  FOREIGN KEY(session_id) REFERENCES sessions(id))""")

    c.execute("""CREATE TABLE IF NOT EXISTS schema_version
                 (version INTEGER PRIMARY KEY, applied_at TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS orgs
                 (id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  slug TEXT NOT NULL UNIQUE,
                  created_at TEXT NOT NULL,
                  metadata TEXT DEFAULT '{}')""")

    c.execute("""CREATE TABLE IF NOT EXISTS projects
                 (id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  path TEXT,
                  git_remote TEXT,
                  created_at TEXT NOT NULL,
                  metadata TEXT DEFAULT '{}',
                  org_id TEXT REFERENCES orgs(id))""")
    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_path
                 ON projects(path) WHERE path IS NOT NULL""")
    c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_git_remote
                 ON projects(git_remote) WHERE git_remote IS NOT NULL""")

    _migrate_projects_table(c)

    # Org standards — tech rules injected into every AI session for the org
    c.execute("""CREATE TABLE IF NOT EXISTS org_standards
                 (id TEXT PRIMARY KEY,
                  org_id TEXT REFERENCES orgs(id),
                  category TEXT NOT NULL DEFAULT 'general',
                  rule TEXT NOT NULL,
                  rationale TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_standards_org ON org_standards(org_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_standards_category ON org_standards(category)")

    c.execute(_CREATE_MEMORIES_SQL)
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_memories_org ON memories(org_id)")

    _migrate_memories_table(c)

    c.execute("""CREATE TABLE IF NOT EXISTS extraction_runs
                 (id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'running',
                  extractors_run TEXT DEFAULT '[]',
                  candidates_created INTEGER DEFAULT 0,
                  auto_saved INTEGER DEFAULT 0,
                  queued INTEGER DEFAULT 0,
                  started_at TEXT NOT NULL,
                  finished_at TEXT,
                  error TEXT)""")

    c.execute("""CREATE TABLE IF NOT EXISTS extraction_candidates
                 (id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  content TEXT NOT NULL,
                  category TEXT NOT NULL DEFAULT 'general',
                  importance TEXT NOT NULL DEFAULT 'medium',
                  source TEXT,
                  tags TEXT DEFAULT '[]',
                  confidence REAL DEFAULT 0.0,
                  extractor TEXT DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'pending',
                  created_at TEXT NOT NULL,
                  metadata TEXT DEFAULT '{}')""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_candidates_project ON extraction_candidates(project_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_candidates_status ON extraction_candidates(status)")

    c.execute(
        "INSERT INTO schema_version VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (SCHEMA_VERSION, datetime.utcnow().isoformat()),
    )

    conn.commit()


def _migrate_projects_table(c):
    if not _column_exists(c, "projects", "org_id"):
        c.execute("ALTER TABLE projects ADD COLUMN org_id TEXT REFERENCES orgs(id)")


def _migrate_memories_table(c):
    if not _column_exists(c, "memories", "scope"):
        c.execute("ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'project'")
    if not _column_exists(c, "memories", "org_id"):
        c.execute("ALTER TABLE memories ADD COLUMN org_id TEXT REFERENCES orgs(id)")
    if not _column_exists(c, "memories", "embedding"):
        c.execute(f"ALTER TABLE memories ADD COLUMN embedding vector({EMBEDDING_DIM})")


# --- Legacy functions ---


def create_session(session: Session):
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions VALUES (%s, %s, %s)",
        (session.id, session.name, session.created_at.isoformat()),
    )
    conn.commit()


def get_session(session_id: str) -> Session | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    row = c.fetchone()
    if not row:
        return None

    session = Session(id=row[0], name=row[1], created_at=datetime.fromisoformat(row[2]))

    c.execute("SELECT * FROM context_items WHERE session_id = %s ORDER BY timestamp", (session_id,))
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
        "INSERT INTO context_items VALUES (%s, %s, %s, %s, %s, %s)",
        (item.id, session_id, item.type, item.content, json.dumps(item.metadata), item.timestamp.isoformat()),
    )
    conn.commit()


# --- Org functions ---


def create_org(org: Org) -> Org:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orgs VALUES (%s, %s, %s, %s, %s)",
        (org.id, org.name, org.slug, org.created_at.isoformat(), json.dumps(org.metadata)),
    )
    conn.commit()
    return org


def get_org(org_id: str) -> Org | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM orgs WHERE id = %s", (org_id,))
    row = c.fetchone()
    return _row_to_org(row) if row else None


def get_org_by_slug(slug: str) -> Org | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM orgs WHERE slug = %s", (slug,))
    row = c.fetchone()
    return _row_to_org(row) if row else None


def list_orgs() -> list[Org]:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM orgs ORDER BY created_at DESC")
    return [_row_to_org(r) for r in c.fetchall()]


def _row_to_org(row) -> Org:
    return Org(
        id=row[0],
        name=row[1],
        slug=row[2],
        created_at=datetime.fromisoformat(row[3]),
        metadata=json.loads(row[4]) if row[4] else {},
    )


# --- V2 Project functions ---


def find_or_create_project(
    name: str,
    path: str | None = None,
    git_remote: str | None = None,
    metadata: dict | None = None,
    org_id: str | None = None,
) -> Project:
    conn = _connect()
    c = conn.cursor()

    if path:
        c.execute("SELECT * FROM projects WHERE path = %s", (path,))
        row = c.fetchone()
        if row:
            return _row_to_project(row)

    if git_remote:
        c.execute("SELECT * FROM projects WHERE git_remote = %s", (git_remote,))
        row = c.fetchone()
        if row:
            return _row_to_project(row)

    import uuid

    project = Project(
        id=str(uuid.uuid4()),
        name=name,
        path=path,
        git_remote=git_remote,
        org_id=org_id,
        metadata=metadata or {},
    )
    c.execute(
        "INSERT INTO projects VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (
            project.id,
            project.name,
            project.path,
            project.git_remote,
            project.created_at.isoformat(),
            json.dumps(project.metadata),
            project.org_id,
        ),
    )
    conn.commit()
    return project


def get_project(project_id: str) -> Project | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    row = c.fetchone()
    return _row_to_project(row) if row else None


def list_projects(org_id: str | None = None) -> list[Project]:
    conn = _connect()
    c = conn.cursor()
    if org_id:
        c.execute("SELECT * FROM projects WHERE org_id = %s ORDER BY created_at DESC", (org_id,))
    else:
        c.execute("SELECT * FROM projects ORDER BY created_at DESC")
    return [_row_to_project(r) for r in c.fetchall()]


def update_project_org(project_id: str, org_id: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE projects SET org_id = %s WHERE id = %s", (org_id, project_id))
    conn.commit()
    return c.rowcount > 0


def _row_to_project(row) -> Project:
    return Project(
        id=row[0],
        name=row[1],
        path=row[2],
        git_remote=row[3],
        created_at=datetime.fromisoformat(row[4]),
        metadata=json.loads(row[5]) if row[5] else {},
        org_id=row[6] if len(row) > 6 else None,
    )


# --- V2 Memory functions ---


def create_memory(memory: MemoryItem) -> MemoryItem:
    conn = _connect()
    c = conn.cursor()
    # embedding is NULL here — memory.py fills it in after encoding
    c.execute(
        "INSERT INTO memories VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)",
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
            memory.scope.value if hasattr(memory.scope, "value") else memory.scope,
            memory.org_id,
        ),
    )
    conn.commit()
    return memory


def get_memory(memory_id: str) -> MemoryItem | None:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, project_id, content, category, importance, source, tags, metadata, "
        "created_at, updated_at, access_count, last_accessed, scope, org_id "
        "FROM memories WHERE id = %s",
        (memory_id,),
    )
    row = c.fetchone()
    return _row_to_memory(row) if row else None


def update_memory(memory_id: str, **kwargs) -> MemoryItem | None:
    conn = _connect()
    c = conn.cursor()

    updates = []
    values = []
    for key, val in kwargs.items():
        if val is None:
            continue
        if key == "tags":
            updates.append("tags = %s")
            values.append(json.dumps(val))
        elif key == "metadata":
            updates.append("metadata = %s")
            values.append(json.dumps(val))
        elif key in ("category", "importance", "scope") and hasattr(val, "value"):
            updates.append(f"{key} = %s")
            values.append(val.value)
        else:
            updates.append(f"{key} = %s")
            values.append(val)

    if not updates:
        return get_memory(memory_id)

    updates.append("updated_at = %s")
    values.append(datetime.utcnow().isoformat())
    values.append(memory_id)

    c.execute(f"UPDATE memories SET {', '.join(updates)} WHERE id = %s", values)
    conn.commit()
    return get_memory(memory_id)


def delete_memory(memory_id: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
    deleted = c.rowcount > 0
    conn.commit()
    return deleted


def list_memories(
    project_id: str | None = None,
    org_id: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    importance_min: str | None = None,
    limit: int = 100,
) -> list[MemoryItem]:
    conn = _connect()
    c = conn.cursor()

    query = (
        "SELECT id, project_id, content, category, importance, source, tags, metadata, "
        "created_at, updated_at, access_count, last_accessed, scope, org_id "
        "FROM memories WHERE 1=1"
    )
    params: list = []

    if project_id:
        query += " AND project_id = %s"
        params.append(project_id)

    if org_id:
        query += " AND org_id = %s"
        params.append(org_id)

    if scope:
        query += " AND scope = %s"
        params.append(scope)

    if category:
        query += " AND category = %s"
        params.append(category)

    if importance_min:
        min_score = IMPORTANCE_SCORES.get(importance_min, 0)
        matching = [k for k, v in IMPORTANCE_SCORES.items() if v >= min_score]
        placeholders = ",".join(["%s"] * len(matching))
        query += f" AND importance IN ({placeholders})"
        params.extend(matching)

    query += " ORDER BY updated_at DESC LIMIT %s"
    params.append(limit)

    c.execute(query, params)
    return [_row_to_memory(r) for r in c.fetchall()]


def record_memory_access(memory_id: str):
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute(
        "UPDATE memories SET access_count = access_count + 1, last_accessed = %s WHERE id = %s",
        (now, memory_id),
    )
    conn.commit()


def _row_to_memory(row) -> MemoryItem:
    # Explicit column SELECT keeps indexes stable regardless of future schema additions
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
        scope=Scope(row[12]) if row[12] else Scope.project,
        org_id=row[13] if len(row) > 13 else None,
    )


# --- Extraction candidate functions ---


def create_candidate(candidate: ExtractionCandidate) -> ExtractionCandidate:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO extraction_candidates VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            candidate.id,
            candidate.project_id,
            candidate.content,
            candidate.category.value,
            candidate.importance.value,
            candidate.source,
            json.dumps(candidate.tags),
            candidate.confidence,
            candidate.extractor,
            candidate.status,
            candidate.created_at.isoformat(),
            json.dumps(candidate.metadata),
        ),
    )
    conn.commit()
    return candidate


def list_candidates(project_id: str, status: str | None = "pending") -> list[ExtractionCandidate]:
    conn = _connect()
    c = conn.cursor()
    if status:
        c.execute(
            "SELECT * FROM extraction_candidates WHERE project_id = %s AND status = %s ORDER BY confidence DESC",
            (project_id, status),
        )
    else:
        c.execute(
            "SELECT * FROM extraction_candidates WHERE project_id = %s ORDER BY confidence DESC",
            (project_id,),
        )
    return [_row_to_candidate(r) for r in c.fetchall()]


def update_candidate_status(candidate_id: str, status: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("UPDATE extraction_candidates SET status = %s WHERE id = %s", (status, candidate_id))
    conn.commit()
    return c.rowcount > 0


def get_candidate(candidate_id: str) -> ExtractionCandidate | None:
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT * FROM extraction_candidates WHERE id = %s", (candidate_id,))
    row = c.fetchone()
    return _row_to_candidate(row) if row else None


def _row_to_candidate(row) -> ExtractionCandidate:
    return ExtractionCandidate(
        id=row[0],
        project_id=row[1],
        content=row[2],
        category=MemoryCategory(row[3]),
        importance=Importance(row[4]),
        source=row[5],
        tags=json.loads(row[6]) if row[6] else [],
        confidence=row[7] or 0.0,
        extractor=row[8] or "",
        status=row[9],
        created_at=datetime.fromisoformat(row[10]),
        metadata=json.loads(row[11]) if row[11] else {},
    )


# --- Extraction run functions ---


def create_extraction_run(run: ExtractionRun) -> ExtractionRun:
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO extraction_runs VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            run.id,
            run.project_id,
            run.status,
            json.dumps(run.extractors_run),
            run.candidates_created,
            run.auto_saved,
            run.queued,
            run.started_at.isoformat(),
            run.finished_at.isoformat() if run.finished_at else None,
            run.error,
        ),
    )
    conn.commit()
    return run


def update_extraction_run(run_id: str, **kwargs) -> bool:
    conn = _connect()
    c = conn.cursor()
    updates = []
    values = []
    for key, val in kwargs.items():
        if key == "extractors_run":
            updates.append("extractors_run = %s")
            values.append(json.dumps(val))
        elif key == "finished_at" and val is not None:
            updates.append("finished_at = %s")
            values.append(val.isoformat() if hasattr(val, "isoformat") else val)
        else:
            updates.append(f"{key} = %s")
            values.append(val)
    if not updates:
        return False
    values.append(run_id)
    c.execute(f"UPDATE extraction_runs SET {', '.join(updates)} WHERE id = %s", values)
    conn.commit()
    return c.rowcount > 0


# --- Org standards functions ---


def upsert_standard(org_id: str, category: str, rule: str, rationale: str | None = None) -> str:
    import uuid
    conn = _connect()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    std_id = str(uuid.uuid4())
    c.execute(
        "INSERT INTO org_standards (id, org_id, category, rule, rationale, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT DO NOTHING",
        (std_id, org_id, category, rule, rationale, now, now),
    )
    conn.commit()
    return std_id


def list_standards(org_id: str, category: str | None = None) -> list[dict]:
    conn = _connect()
    c = conn.cursor()
    if category:
        c.execute(
            "SELECT id, category, rule, rationale, created_at FROM org_standards "
            "WHERE org_id = %s AND category = %s ORDER BY category, created_at",
            (org_id, category),
        )
    else:
        c.execute(
            "SELECT id, category, rule, rationale, created_at FROM org_standards "
            "WHERE org_id = %s ORDER BY category, created_at",
            (org_id,),
        )
    rows = c.fetchall()
    return [
        {"id": r[0], "category": r[1], "rule": r[2], "rationale": r[3], "created_at": r[4]}
        for r in rows
    ]


def delete_standard(standard_id: str) -> bool:
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM org_standards WHERE id = %s", (standard_id,))
    deleted = c.rowcount > 0
    conn.commit()
    return deleted
