# gugabobo

`gugabobo` is a cloud-first autonomous agent prototype. The first milestone focuses on a minimal core that can run locally or on a server, keep SQLite-backed memory, expose a small API, and provide a CLI control surface.

## P0 scope

- CLI entrypoint
- Core agent with shared persona
- SQLite memory and feedback store
- FastAPI health/status API
- Long-running daemon loop
- Basic tests

## Quick start

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
gugabobo status
gugabobo chat "你好"
gugabobo feedback add "回复太长"
gugabobo api
```

## Configuration

Copy `.env.example` to `.env` when you need custom local settings.

