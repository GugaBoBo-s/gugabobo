# AGENTS.md / CLAUDE.md

## Language

Always respond to the user in Simplified Chinese.

## Project

`gugabobo` is a cloud-first autonomous agent platform.

The long-term architecture is:

- one persistent cloud-side gugabobo core
- multiple adapters such as CLI, QQ, Telegram, API, GitHub, and dashboard
- shared persona, memory, policy, routing, and improvement flow
- self-improvement through sandboxed code changes and GitHub pull requests

P0 through P4 are operational. The current milestone is P5: hardening the
self-improvement lifecycle and recording its outcomes. Keep changes focused on
that milestone unless the user explicitly changes the scope.

## Current P5 Scope

The current system includes:

- a shared core agent, persona, router, policy, context, and SQLite memory layer
- CLI, QQ/NapCat, Telegram, FastAPI, and Dashboard adapters
- per-user and per-conversation context with summaries and long-term memory
- administrative controls, diagnostics, audit records, and outbound approvals
- an approval-gated self-improvement workflow that creates GitHub pull requests
- a Docker-only Claude Code runner with isolated checks and no host fallback
- systemd deployment for the API and Telegram polling services

Current P5 work should prioritize:

- reflection records after pull request merge or rejection
- deployment records tied to pull requests and server revisions
- stale-run recovery and cancellation
- policy checks for generated diffs
- structured token and cost records for coding runs

Do not automatically merge pull requests or deploy generated code. Do not add
Redis, Celery, Docker Compose, a vector database, X, or Xiaohongshu unless the
requested work requires it.

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
- Keep self-improvement approval-gated, branch-only, containerized, and auditable.
- Keep tests close to behavior: core routing, persistence, adapters, API contracts, and policy boundaries.
- Avoid broad refactors unless they directly support the requested work.
- Use explicit types for public functions and constructors.
- Keep secrets out of Git. Use `.env` locally and `.env.example` for documented settings.

## Comment Guidelines

- Do not add code comments unless they are strictly necessary, such as explaining a counterintuitive edge case.
- Prefer meaningful variable names and type declarations over comments.
- Function docstrings should only describe what the function does and what it returns, not how it works.

## Git Guidelines

- `main` is the canonical branch.
- Do not push directly to a different remote unless the user asks.
- Do not rewrite history unless the user explicitly asks.
- Keep commits focused and describe the behavior changed.

## Commit Message Format

```text
<type>(<scope>): <short description>

# Optional: a longer description explaining why the change was made.
```

Types:

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Refactor without behavior change |
| `chore` | Configuration, dependencies, tooling |
| `docs` | Documentation |
| `release` | Version release |

Remote repository:

```text
https://github.com/GugaBoBo-s/gugabobo
```

Visibility:

```text
PRIVATE
```
