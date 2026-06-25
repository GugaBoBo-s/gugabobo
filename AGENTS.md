# AGENTS.md / CLAUDE.md

## Language

Always respond to the user in Simplified Chinese.

## Project

`gugabobo` is a cloud-first autonomous agent prototype.

The long-term architecture is:

- one persistent cloud-side gugabobo core
- multiple adapters such as CLI, QQ, GitHub, X, and dashboard
- shared persona, memory, policy, routing, and improvement flow
- self-improvement through sandboxed code changes and GitHub pull requests

The current repository is at P0. Keep changes focused on the minimal core unless the user explicitly asks to expand the milestone.

## Current P0 Scope

Implemented or expected in this milestone:

- Python package under `src/gugabobo`
- CLI adapter
- Core agent
- Persona
- Router
- SQLite-backed memory and feedback store
- FastAPI management API
- Minimal daemon loop
- Tests for core and API behavior

Do not add QQ, X, Xiaohongshu, Claude Code runner, dashboard frontend, Redis, Celery, Docker Compose, or vector database unless requested.

## Development Commands

Use the local virtual environment for this repo because another global editable `gugabobo` package may exist on the machine.

```powershell
cd D:\0code\gugabobo
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run lint:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
```

Try the CLI:

```powershell
.\.venv\Scripts\gugabobo.exe status
.\.venv\Scripts\gugabobo.exe chat "你好"
.\.venv\Scripts\gugabobo.exe feedback add "回复太长"
.\.venv\Scripts\gugabobo.exe feedback list
```

Run the API:

```powershell
.\.venv\Scripts\gugabobo.exe api
```

## Code Guidelines

- Prefer small, milestone-aligned changes.
- Keep the core independent from platform adapters.
- Keep adapters thin. They should translate platform input/output and call the core.
- Store durable state through `MemoryStore`; avoid ad hoc files for runtime state.
- Keep tests close to behavior: core routing, persistence, CLI/API contracts.
- Avoid broad refactors unless they directly support the requested work.
- Use explicit types for public functions and constructors.
- Keep secrets out of Git. Use `.env` locally and `.env.example` for documented settings.

## Git Guidelines

- `main` is the canonical branch.
- Do not push directly to a different remote unless the user asks.
- Do not rewrite history unless the user explicitly asks.
- Keep commits focused and describe the behavior changed.

Remote repository:

```text
https://github.com/GugaBoBo-s/gugabobo
```

Visibility:

```text
PRIVATE
```
