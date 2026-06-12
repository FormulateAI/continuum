"""Continuum MCP Server — exposes memory tools for Claude Code, Cursor, etc."""

from mcp.server.fastmcp import FastMCP

from continuum.core.service import ContinuumService
from continuum.server import database
from continuum.server.models import Importance, MemoryCategory, MemorySearch

mcp = FastMCP(
    "Continuum",
    instructions="Universal AI memory layer — remember and recall project knowledge across tools and sessions",
)

service = ContinuumService()


@mcp.tool()
def remember(
    content: str,
    project_path: str,
    category: str = "general",
    importance: str = "medium",
    source: str = "",
    tags: str = "",
) -> str:
    """Store a learning, pattern, insight, convention, or decision as a persistent memory.

    Use this whenever you discover something worth remembering about a project:
    architecture decisions, coding conventions, debugging insights, user preferences, etc.

    Args:
        content: The memory content to store (be specific and actionable)
        project_path: Absolute path to the project directory
        category: One of: architecture, conventions, patterns, debugging, decisions, preferences, general
        importance: One of: critical, high, medium, low, ephemeral
        source: Where this memory came from (e.g. "user instruction", "code review", "debugging session")
        tags: Comma-separated tags for additional categorization
    """
    try:
        cat = MemoryCategory(category)
    except ValueError:
        cat = MemoryCategory.general

    try:
        imp = Importance(importance)
    except ValueError:
        imp = Importance.medium

    project = service.find_or_create_project(path=project_path)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    memory = service.store_memory(
        project_id=project.id,
        content=content,
        category=cat,
        importance=imp,
        source=source or None,
        tags=tag_list,
    )
    return f"Stored memory [{memory.id[:8]}] in project '{project.name}' ({cat.value}/{imp.value})"


@mcp.tool()
def recall(
    query: str,
    project_path: str,
    categories: str = "",
    limit: int = 5,
) -> str:
    """Search for relevant memories about a project using semantic search.

    Use this at the start of a session or when you need context about a project's
    architecture, conventions, past decisions, debugging history, etc.

    Args:
        query: Natural language description of what you're looking for
        project_path: Absolute path to the project directory
        categories: Comma-separated category filter (e.g. "architecture,conventions")
        limit: Maximum number of results to return
    """
    project = service.find_or_create_project(path=project_path)

    cat_list = None
    if categories:
        cat_list = []
        for c in categories.split(","):
            c = c.strip()
            try:
                cat_list.append(MemoryCategory(c))
            except ValueError:
                pass
        if not cat_list:
            cat_list = None

    search = MemorySearch(
        query=query,
        project_id=project.id,
        categories=cat_list,
        limit=limit,
    )
    results = service.search_memories(search)

    if not results:
        return f"No memories found for project '{project.name}' matching: {query}"

    lines = [f"Found {len(results)} memories for '{project.name}':\n"]
    for r in results:
        meta = r.get("metadata", {})
        cat = meta.get("category", "general")
        imp = meta.get("importance", "medium")
        lines.append(f"[{cat}/{imp}] (score: {r['score']}) {r['content']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_project_context(project_path: str) -> str:
    """Get a full project briefing — all important memories organized by category.

    Use this at the start of every session to load project context. Returns
    architecture decisions, coding conventions, known patterns, and more.

    Args:
        project_path: Absolute path to the project directory
    """
    project = service.find_or_create_project(path=project_path)
    briefing = service.get_project_briefing(project.id)

    if "error" in briefing:
        return f"Error: {briefing['error']}"

    categories = briefing.get("categories", {})
    if not categories:
        return (
            f"No memories stored yet for project '{project.name}'. Use 'remember' to start building project knowledge."  # noqa: E501
        )

    lines = [f"Project: {project.name} ({briefing['memory_count']} memories)\n"]

    for cat, memories in categories.items():
        lines.append(f"## {cat.title()}")
        for m in memories:
            prefix = f"[{m['importance']}]"
            lines.append(f"  {prefix} {m['content']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_org_standards(org_slug: str, category: str = "") -> str:
    """Get the organization's technology standards and rules.

    Returns the tech rules, architecture constraints, and coding standards that
    apply to every project in this org. Inject these at the start of every session.

    Args:
        org_slug: The org's unique slug identifier (e.g. "acme-corp")
        category: Optional category filter (e.g. "architecture", "conventions", "security")
    """
    org = database.get_org_by_slug(org_slug)
    if not org:
        return f"Org '{org_slug}' not found. Create it first with the REST API."

    standards = database.list_standards(org.id, category=category or None)
    if not standards:
        msg = f"No standards defined for org '{org.name}'"
        if category:
            msg += f" in category '{category}'"
        return msg + ". Add standards via the REST API or 'set_org_standard' tool."

    by_category: dict[str, list] = {}
    for s in standards:
        cat = s["category"]
        by_category.setdefault(cat, []).append(s)

    lines = [f"Org standards for {org.name}:\n"]
    for cat, items in sorted(by_category.items()):
        lines.append(f"## {cat.title()}")
        for s in items:
            line = f"  - {s['rule']}"
            if s.get("rationale"):
                line += f" ({s['rationale']})"
            lines.append(line)
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def set_org_standard(
    org_slug: str,
    rule: str,
    category: str = "general",
    rationale: str = "",
) -> str:
    """Add or update an org-wide technology standard or rule.

    Use this to codify decisions that apply across ALL projects in the org:
    which database to use, naming conventions, security requirements, etc.

    Args:
        org_slug: The org's unique slug identifier
        rule: The standard/rule to enforce (be specific and actionable)
        category: One of: architecture, conventions, patterns, security, general
        rationale: Why this standard exists (optional but recommended)
    """
    org = database.get_org_by_slug(org_slug)
    if not org:
        return f"Org '{org_slug}' not found."

    std_id = database.upsert_standard(
        org_id=org.id,
        category=category,
        rule=rule,
        rationale=rationale or None,
    )
    return f"Standard saved [{std_id[:8]}] in '{org.name}' under '{category}': {rule}"


@mcp.tool()
def forget(memory_id: str, project_path: str = "") -> str:
    """Remove an outdated or incorrect memory.

    Args:
        memory_id: The ID (or first 8 chars) of the memory to delete
        project_path: Optional project path for context (not required for deletion)
    """
    # Try full ID first, then partial match
    if service.delete_memory(memory_id):
        return f"Deleted memory {memory_id}"

    return f"Memory not found: {memory_id}. Use 'recall' to find the correct memory ID."
