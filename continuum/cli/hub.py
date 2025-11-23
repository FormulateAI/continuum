import typer
import requests
import sys
import json
from typing import Optional

app = typer.Typer()
SERVER_URL = "http://localhost:8000"

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

if __name__ == "__main__":
    app()
