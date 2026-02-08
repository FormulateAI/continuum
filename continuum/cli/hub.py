import typer
import requests
import sys
import json
from typing import Optional

app = typer.Typer(help="Continuum — Universal AI Memory Layer")
SERVER_URL = "http://localhost:8000"


# --- Legacy commands ---

@app.command()
def start(name: str):
    """Start a new context session."""
    try:
        response = requests.post(f"{SERVER_URL}/session/start", params={"name": name})
        response.raise_for_status()
        typer.echo(f"Session '{name}' started. ID: {response.json()['id']}")
    except requests.exceptions.ConnectionError:
        typer.echo("Error: Could not connect to Context Hub server. Is it running?")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def push(content: str, type: str = "instruction"):
    """Push a piece of context to the hub."""
    item = {
        "type": type,
        "content": content,
        "metadata": {}
    }
    try:
        response = requests.post(f"{SERVER_URL}/context/add", json=item)
        response.raise_for_status()
        typer.echo("Context added.")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def pull(limit: int = 10):
    """Pull the latest context."""
    try:
        response = requests.get(f"{SERVER_URL}/context/latest", params={"limit": limit})
        response.raise_for_status()
        items = response.json()
        for item in items:
            typer.echo(f"[{item['type']}] {item['timestamp']}")
            typer.echo(f"{item['content']}")
            typer.echo("-" * 20)
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def search(query: str, limit: int = 5):
    """Search context using semantic search."""
    try:
        payload = {"query": query, "limit": limit}
        response = requests.post(f"{SERVER_URL}/context/search", json=payload)
        response.raise_for_status()
        results = response.json()

        if not results:
            typer.echo("No matching context found.")
            return

        for item in results:
            typer.echo(f"[Score: {item['distance']:.4f}]")
            typer.echo(f"{item['content']}")
            typer.echo("-" * 20)

    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def status():
    """Check server status."""
    try:
        response = requests.get(f"{SERVER_URL}/")
        typer.echo(f"Server Status: {response.json()}")

        sess_resp = requests.get(f"{SERVER_URL}/session/current")
        if sess_resp.status_code == 200:
            typer.echo(f"Active Session: {sess_resp.json()['name']}")
        else:
            typer.echo("No active session.")

    except Exception as e:
        typer.echo(f"Error: {e}")


# --- V2 commands ---

@app.command()
def mcp():
    """Launch the Continuum MCP server (stdio transport)."""
    from continuum.mcp.server import mcp as mcp_server
    mcp_server.run(transport="stdio")


@app.command()
def init(
    path: str = typer.Argument(".", help="Project directory to register"),
    name: Optional[str] = typer.Option(None, help="Project name (defaults to directory name)"),
):
    """Register a project directory with Continuum."""
    import os
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
    import os
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
    import os
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
