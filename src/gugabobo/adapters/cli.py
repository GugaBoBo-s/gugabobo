import time

import typer
import uvicorn

from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger
from gugabobo.infra.runtime import build_agent

app = typer.Typer(help="gugabobo control CLI")
feedback_app = typer.Typer(help="Feedback commands")
messages_app = typer.Typer(help="Message commands")
config_app = typer.Typer(help="Configuration commands")
db_app = typer.Typer(help="Database commands")
app.add_typer(feedback_app, name="feedback")
app.add_typer(messages_app, name="messages")
app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")


def echo_mapping(data: dict[str, object]) -> None:
    for key, value in data.items():
        typer.echo(f"{key}: {value}")


@app.command()
def status() -> None:
    """Show runtime status."""
    echo_mapping(build_agent().status())


@app.command()
def chat(message: str = typer.Argument("")) -> None:
    """Send one message to gugabobo."""
    agent = build_agent()
    reply = agent.handle_message(message, source="cli", user_id="local")
    get_logger().info("cli chat user_id=local")
    typer.echo(reply)


@messages_app.command("list")
def messages_list(limit: int = 20) -> None:
    """List recent messages."""
    agent = build_agent()
    for item in agent.store.list_messages(limit=limit):
        typer.echo(
            f"#{item['id']} [{item['role']}] {item['content']} "
            f"({item['source']}:{item['user_id']})"
        )


@messages_app.command("show")
def messages_show(message_id: int) -> None:
    """Show one message."""
    agent = build_agent()
    message = agent.store.get_message(message_id)
    if not message:
        raise typer.BadParameter(f"message #{message_id} not found")
    echo_mapping(message)


@feedback_app.command("add")
def feedback_add(content: str) -> None:
    """Record one feedback item."""
    agent = build_agent()
    feedback_id = agent.store.add_feedback(source="cli", user_id="local", content=content)
    get_logger().info("feedback added id=%s source=cli", feedback_id)
    typer.echo(f"已记录反馈 #{feedback_id}。")


@feedback_app.command("list")
def feedback_list(limit: int = 20) -> None:
    """List recent feedback items."""
    agent = build_agent()
    for item in agent.store.list_feedbacks(limit=limit):
        typer.echo(f"#{item['id']} [{item['status']}] {item['content']} ({item['source']})")


@feedback_app.command("resolve")
def feedback_resolve(feedback_id: int) -> None:
    """Mark feedback as resolved."""
    if not build_agent().store.update_feedback_status(feedback_id, "resolved"):
        raise typer.BadParameter(f"feedback #{feedback_id} not found")
    get_logger().info("feedback resolved id=%s", feedback_id)
    typer.echo(f"已解决反馈 #{feedback_id}。")


@feedback_app.command("reopen")
def feedback_reopen(feedback_id: int) -> None:
    """Mark feedback as new."""
    if not build_agent().store.update_feedback_status(feedback_id, "new"):
        raise typer.BadParameter(f"feedback #{feedback_id} not found")
    get_logger().info("feedback reopened id=%s", feedback_id)
    typer.echo(f"已重新打开反馈 #{feedback_id}。")


@config_app.command("show")
def config_show() -> None:
    """Show effective configuration."""
    settings = get_settings()
    echo_mapping(
        {
            "env": settings.env,
            "data_dir": settings.data_dir,
            "db_path": settings.db_path,
            "log_dir": settings.log_dir,
            "api_host": settings.api_host,
            "api_port": settings.api_port,
            "admin_token": "***" if settings.admin_token else "",
            "owner_qq_ids": settings.owner_qq_ids,
            "napcat_api_url": settings.napcat_api_url,
            "napcat_access_token": "***" if settings.napcat_access_token else "",
            "napcat_reply_enabled": settings.napcat_reply_enabled,
            "qq_group_wake_words": settings.qq_group_wake_words,
            "llm_provider": settings.llm_provider,
            "moonshot_base_url": settings.moonshot_base_url,
            "moonshot_model": settings.moonshot_model,
            "moonshot_api_key": "***" if settings.moonshot_api_key else "",
            "llm_timeout_seconds": settings.llm_timeout_seconds,
        }
    )


@db_app.command("path")
def db_path() -> None:
    """Show database path."""
    typer.echo(get_settings().db_path)


@db_app.command("init")
def db_init() -> None:
    """Initialize database schema."""
    build_agent().store.init()
    typer.echo("database initialized")


@app.command()
def daemon(interval: int = 30) -> None:
    """Run a minimal long-lived daemon loop."""
    logger = get_logger()
    logger.info("daemon started interval=%s", interval)
    typer.echo("gugabobo daemon started")
    while True:
        status_data = build_agent().status()
        logger.info(
            "daemon heartbeat messages=%s feedbacks=%s",
            status_data["messages"],
            status_data["feedbacks"],
        )
        typer.echo(f"heartbeat messages={status_data['messages']} feedbacks={status_data['feedbacks']}")
        time.sleep(interval)


@app.command()
def api() -> None:
    """Run the local management API."""
    settings = get_settings()
    get_logger().info("api starting host=%s port=%s", settings.api_host, settings.api_port)
    uvicorn.run("gugabobo.api.server:app", host=settings.api_host, port=settings.api_port)
