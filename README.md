# Continuum

**Continuum** is an open-source framework designed to give AI agents persistent, evolving context. It allows systems to retain information across sessions, adapt to user behavior, and recall complex relationships without the overhead of manual context management.

[![PyPI](https://img.shields.io/pypi/v/continuum-context-hub?color=blue&label=pypi%20package)](https://pypi.org/project/continuum-context-hub/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Documentation](https://img.shields.io/badge/docs-continuum.ai-orange)](https://docs.continuum.ai)

---

## Overview

**Continuum** is built on a simple philosophy: **Design by developers, for developers.**

In the modern AI coding era, you shouldn't be locked into a single tool. Whether you're prototyping in **Cursor**, refining in **Windsurf**, coding in **VS Code**, or pair-programming with **Antigravity**, your context should travel with you.

Continuum acts as the universal memory layer that unifies these experiences. It ensures that the architectural decision you made in one agent is remembered when you switch to another, giving you the confidence to move freely between the best tools for the job.

## Key Advantages

### 🔄 **Freedom to Switch Tools**
Use the best AI coding assistant for each task without losing context. Start in **Cursor**, refine in **Windsurf**, debug in **VS Code**, or collaborate with **Antigravity**—your progress travels with you.

### 🤝 **True Agent Interoperability**
What one agent learns, the next one knows. No more:
- Re-explaining your architecture
- Repeating requirements
- Losing bug fix context
- Starting from scratch with each new session

### 🧠 **Intelligent Context Management**
Unlike simple vector databases, Continuum:
- **Promotes** important architectural decisions to long-term memory
- **Fades** temporary debugging logs and noise naturally
- **Prevents** context pollution that degrades agent performance
- **Adapts** to your project's evolving needs

### 🔒 **Privacy-First Architecture**
- Run locally or in your private cloud
- You own your data, not locked into vendor clouds
- Granular control over what gets stored and for how long

### ⚡ **Developer Experience**
- **Simple Integration**: Just add to your agent's system prompt
- **Graceful Degradation**: Continues working even if hub is unreachable
- **Minimal Overhead**: Only checkpoint meaningful progress, not every keystroke
- **Pluggable Backends**: Use Chroma, Postgres, Redis, or your own storage

## Installation

### Python

```bash
pip install continuum-context-hub
```

### TypeScript

```bash
npm install continuum-context-hub
```

## Usage Example

Continuum is designed to be integrated into your AI agent's system prompt. Here's how to instruct your agent to use it:

### Agent Instructions: Context Hub Integration

Include these instructions in your agent's system prompt:

```markdown
You are an AI agent working in a persistent development environment. You have access to a **Centralized Context Hub** that stores the history and context of this project.

## Your Goal
To ensure seamless continuity between sessions (e.g., if the user switches to a different model or IDE), you must **record your progress** and **retrieve past context**.

## Tools Available
You have access to a Python library `continuum.client`.

from continuum.client import hub

## Rules of Engagement

### 1. When to Push Context (Checkpoints)
Do NOT push every single file edit or thought. This creates noise.
**DO push a checkpoint when:**
- You complete a sub-task (e.g., "Implemented the login API").
- You encounter a tricky bug and find a solution (e.g., "Fixed the CORS issue by updating main.py").
- You are about to stop or ask the user for input.

**How to push:**
hub.push_checkpoint(
    summary="Completed the User Model",
    details="Added User class with id, name, email fields. Updated database schema."
)

### 2. When to Pull Context (Retrieval)
Before starting a complex task, check if there is relevant history.
**How to search:**
# Example: You are asked to fix a bug in Auth
results = hub.search_memory("auth login bug fix")
# Use 'results' to understand what was done previously

### 3. Failure Handling
If the Context Hub is unreachable, **proceed with your task**. Do not crash. Log a warning and continue.
```

## Architecture

Continuum is built on a modular architecture supporting:
1.  **Ingestion Pipeline**: Text, Code, JSON.
2.  **Storage Layer**: Pluggable backends (Chroma, Postgres, Redis).
3.  **Retrieval Engine**: Hybrid search (Dense + Sparse).

## Community & Support

*   **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/continuum-ai/continuum/issues).
*   **Discussions**: Join the conversation on our [Community Forum](https://github.com/continuum-ai/continuum/discussions).

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
