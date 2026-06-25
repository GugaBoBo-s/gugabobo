import time

import typer
import uvicorn

from gugabobo.config import get_settings
from gugabobo.infra.runtime import build_agent

app = typer.Typer(help="gugabobo control CLI")
feedback_app = typer.Typer(help="Feedback commands")
app.add_typer(feedback_app, name="feedback")


@app.command()
def status() -> None:
    """Show runtime status."""
    typer.echo(build_agent().status())


@app.command()
def chat(message: str = typer.Argument("")) -> None:
    """Send one message to gugabobo."""
    agent = build_agent()
    typer.echo(agent.handle_message(message, source="cli", user_id="local"))


@feedback_app.command("add")
def feedback_add(content: str) -> None:
    """Record one feedback item."""
    agent = build_agent()
    feedback_id = agent.store.add_feedback(source="cli", user_id="local", content=content)
    typer.echo(f"已记录反馈 #{feedback_id}。")


@feedback_app.command("list")
def feedback_list(limit: int = 20) -> None:
    """List recent feedback items."""
    agent = build_agent()
    for item in agent.store.list_feedbacks(limit=limit):
        typer.echo(f"#{item['id']} [{item['status']}] {item['content']} ({item['source']})")


@app.command()
def daemon(interval: int = 30) -> None:
    """Run a minimal long-lived daemon loop."""
    typer.echo("gugabobo daemon started")
    while True:
        status_data = build_agent().status()
        typer.echo(f"heartbeat messages={status_data['messages']} feedbacks={status_data['feedbacks']}")
        time.sleep(interval)


@app.command()
def api() -> None:
    """Run the local management API."""
    settings = get_settings()
    uvicorn.run("gugabobo.api.server:app", host=settings.api_host, port=settings.api_port)

