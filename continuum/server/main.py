from fastapi import FastAPI
from . import database
from .routes.legacy import router as legacy_router
from .routes.projects import router as projects_router
from .routes.memories import router as memories_router, context_router

app = FastAPI(title="Continuum", description="Universal AI Memory Layer")

# Initialize DB
database.init_db()

# Health check
@app.get("/")
def read_root():
    return {"status": "running", "service": "Continuum", "version": "0.2.0",
            "features": ["vector-search", "project-memories", "mcp"]}

# Legacy v1 routes
app.include_router(legacy_router)

# V2 routes
app.include_router(projects_router)
app.include_router(memories_router)
app.include_router(context_router)
