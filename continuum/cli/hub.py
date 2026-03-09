import os

import typer

from continuum.server.config import CONTINUUM_PORT

app = typer.Typer(help="Continuum — Universal AI Memory Layer")


# --- V2 commands ---


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind to"),
    port: int | None = typer.Option(None, help="Port to listen on"),
):
    """Start the Continuum server."""
    import uvicorn

    uvicorn.run("continuum.server.main:app", host=host, port=port or CONTINUUM_PORT)


@app.command()
def push(
    content: str = typer.Argument(..., help="Memory content to store"),
    category: str = typer.Option("general", help="Memory category"),
    importance: str = typer.Option("medium", help="Importance level"),
    path: str = typer.Option(".", help="Project directory"),
):
    """Store a memory in the current project."""
    path = os.path.abspath(path)
    from continuum.core.service import ContinuumService

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)
    memory = svc.store_memory(
        project_id=project.id,
        content=content,
        category=category,
        importance=importance,
    )
    typer.echo(f"Memory stored (id: {memory.id[:8]})")


@app.command()
def pull(
    limit: int = typer.Option(20, help="Maximum memories to show"),
    path: str = typer.Option(".", help="Project directory"),
    category: str | None = typer.Option(None, help="Filter by category"),
):
    """List recent memories for the current project."""
    path = os.path.abspath(path)
    from continuum.core.service import ContinuumService
    from continuum.server import database

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)
    memories = database.list_memories(project.id, category=category, limit=limit)

    if not memories:
        typer.echo("No memories found.")
        return

    for m in memories:
        typer.echo(f"[{m.category.value}] [{m.importance.value}] {m.id[:8]}")
        typer.echo(f"  {m.content}")
        typer.echo(f"  Updated: {m.updated_at.isoformat()}")
        typer.echo("-" * 40)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, help="Maximum results"),
    path: str = typer.Option(".", help="Project directory"),
):
    """Search memories using semantic search."""
    path = os.path.abspath(path)
    from continuum.core.service import ContinuumService
    from continuum.server.models import MemorySearch

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)

    search_req = MemorySearch(query=query, project_id=project.id, limit=limit)
    results = svc.search_memories(search_req)

    if not results:
        typer.echo("No matching memories found.")
        return

    for r in results:
        typer.echo(f"[Score: {r['score']:.4f}] {r['id'][:8]}")
        typer.echo(f"  {r['content']}")
        typer.echo("-" * 40)


@app.command()
def status(
    path: str = typer.Option(".", help="Project directory"),
):
    """Show project info and memory counts."""
    path = os.path.abspath(path)
    from continuum.core.service import ContinuumService
    from continuum.server import database

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)

    memories = database.list_memories(project.id, limit=10000)
    typer.echo(f"Project: {project.name}")
    typer.echo(f"  ID:   {project.id[:8]}")
    typer.echo(f"  Path: {project.path}")
    if project.git_remote:
        typer.echo(f"  Remote: {project.git_remote}")
    typer.echo(f"  Total memories: {len(memories)}")

    # Count by category
    cat_counts: dict = {}
    for m in memories:
        cat = m.category.value
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    if cat_counts:
        typer.echo("  By category:")
        for cat, count in sorted(cat_counts.items()):
            typer.echo(f"    {cat}: {count}")


@app.command()
def mcp():
    """Launch the Continuum MCP server (stdio transport)."""
    from continuum.mcp.server import mcp as mcp_server

    mcp_server.run(transport="stdio")


@app.command()
def init(
    path: str = typer.Argument(".", help="Project directory to register"),
    name: str | None = typer.Option(None, help="Project name (defaults to directory name)"),
):
    """Register a project directory with Continuum."""
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        typer.echo(f"Error: '{path}' is not a directory.")
        raise typer.Exit(1)

    from continuum.core.service import ContinuumService

    svc = ContinuumService()
    project = svc.find_or_create_project(name=name, path=path)
    typer.echo(f"Project '{project.name}' registered (id: {project.id[:8]})")
    typer.echo(f"  Path: {project.path}")
    if project.git_remote:
        typer.echo(f"  Remote: {project.git_remote}")


@app.command()
def generate(
    path: str = typer.Argument(".", help="Project directory"),
    target: str = typer.Option("claude", help="Target format: claude, cursor, all"),
):
    """Generate tool configuration files from project memories."""
    path = os.path.abspath(path)

    from continuum.core.service import ContinuumService
    from continuum.generators.sync import SyncManager

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)
    manager = SyncManager(svc)

    targets = [target] if target != "all" else ["claude", "cursor"]
    for t in targets:
        outpath = manager.generate(project.id, path, t)
        if outpath:
            typer.echo(f"Generated: {outpath}")
        else:
            typer.echo(f"No memories to generate for target '{t}'.")


@app.command()
def sync(
    path: str = typer.Argument(".", help="Project directory"),
    target: str = typer.Option("claude", help="Target format: claude, cursor, all"),
):
    """Bidirectional sync between Continuum memories and tool config files."""
    path = os.path.abspath(path)

    from continuum.core.service import ContinuumService
    from continuum.generators.sync import SyncManager

    svc = ContinuumService()
    project = svc.find_or_create_project(path=path)
    manager = SyncManager(svc)

    targets = [target] if target != "all" else ["claude", "cursor"]
    for t in targets:
        result = manager.sync(project.id, path, t)
        if result.get("ingested"):
            typer.echo(f"Ingested {result['ingested']} new memories from {t} file")
        if result.get("generated"):
            typer.echo(f"Generated: {result['generated']}")
        if not result.get("ingested") and not result.get("generated"):
            typer.echo(f"[{t}] Already in sync.")


if __name__ == "__main__":
    app()
