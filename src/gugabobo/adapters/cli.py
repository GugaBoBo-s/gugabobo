import time

import typer
import uvicorn

from gugabobo.adapters.telegram_runtime import handle_telegram_update
from gugabobo.config import get_settings
from gugabobo.core.channel import ChannelContext
from gugabobo.infra.telegram_client import TelegramClient
from gugabobo.infra.logs import get_logger
from gugabobo.infra.runtime import build_agent

app = typer.Typer(help="gugabobo control CLI")
feedback_app = typer.Typer(help="Feedback commands")
messages_app = typer.Typer(help="Message commands")
config_app = typer.Typer(help="Configuration commands")
db_app = typer.Typer(help="Database commands")
memory_app = typer.Typer(help="Long-term memory commands")
summary_app = typer.Typer(help="Conversation summary commands")
telegram_app = typer.Typer(help="Telegram adapter commands")
app.add_typer(feedback_app, name="feedback")
app.add_typer(messages_app, name="messages")
app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(memory_app, name="memory")
app.add_typer(summary_app, name="summary")
app.add_typer(telegram_app, name="telegram")


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
    reply = agent.handle_context_message(message, ChannelContext.local())
    get_logger().info("cli chat user_id=local")
    typer.echo(reply)


@messages_app.command("list")
def messages_list(limit: int = 20) -> None:
    """List recent messages."""
    agent = build_agent()
    for item in agent.store.list_messages(limit=limit):
        typer.echo(
            f"#{item['id']} [{item['role']}] {item['content']} "
            f"({item['conversation_id']})"
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


@memory_app.command("add")
def memory_add(
    content: str,
    subject: str = "global",
    memory_type: str = "note",
    importance: int = 5,
) -> None:
    """Add one long-term memory item."""
    memory_id = build_agent().store.add_memory_item(
        subject=subject,
        content=content,
        memory_type=memory_type,
        importance=importance,
    )
    typer.echo(f"已添加记忆 #{memory_id}。")


@memory_app.command("list")
def memory_list(subject: str | None = None, limit: int = 20) -> None:
    """List long-term memory items."""
    for item in build_agent().store.list_memory_items(subject=subject, limit=limit):
        typer.echo(
            f"#{item['id']} [{item['subject']}/{item['memory_type']}/"
            f"{item['importance']}] {item['content']}"
        )


@summary_app.command("set")
def summary_set(conversation_id: str, summary: str, updated_until_message_id: int = 0) -> None:
    """Set one conversation summary."""
    build_agent().store.upsert_conversation_summary(
        conversation_id=conversation_id,
        summary=summary,
        updated_until_message_id=updated_until_message_id,
    )
    typer.echo(f"已更新会话摘要：{conversation_id}")


@summary_app.command("show")
def summary_show(conversation_id: str) -> None:
    """Show one conversation summary."""
    summary = build_agent().store.get_conversation_summary(conversation_id)
    if not summary:
        raise typer.BadParameter(f"summary for {conversation_id} not found")
    echo_mapping(summary)


@summary_app.command("list")
def summary_list(limit: int = 20) -> None:
    """List conversation summaries."""
    for item in build_agent().store.list_conversation_summaries(limit=limit):
        typer.echo(f"{item['conversation_id']}: {item['summary']}")


@telegram_app.command("poll")
def telegram_poll(
    send: bool = typer.Option(False, "--send", help="Send replies through Telegram."),
    timeout: int = typer.Option(30, help="Long polling timeout in seconds."),
) -> None:
    """Run Telegram local polling."""
    settings = get_settings()
    client = TelegramClient()
    if not client.configured:
        raise typer.BadParameter("GUGABOBO_TELEGRAM_BOT_TOKEN is not configured")
    effective_send = send or settings.telegram_reply_enabled
    offset: int | None = None
    typer.echo(
        "telegram polling started "
        f"(send={effective_send}, timeout={timeout}, bot={settings.telegram_bot_username or 'unknown'})"
    )
    while True:
        updates = client.get_updates(offset=offset, timeout=timeout)
        for update in updates:
            update_id = int(update.get("update_id", 0))
            offset = update_id + 1
            result = handle_telegram_update(
                update,
                agent=build_agent(),
                settings=settings,
                send_reply=effective_send,
                client=client,
            )
            typer.echo(f"telegram update {update_id}: {result}")


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
            "config_file_path": settings.config_file_path,
            "api_host": settings.api_host,
            "api_port": settings.api_port,
            "admin_token": "***" if settings.admin_token else "",
            "owner_qq_ids": settings.owner_qq_ids,
            "owner_telegram_ids": settings.owner_telegram_ids,
            "napcat_api_url": settings.napcat_api_url,
            "napcat_access_token": "***" if settings.napcat_access_token else "",
            "napcat_reply_enabled": settings.napcat_reply_enabled,
            "napcat_passive_reply_enabled": settings.napcat_passive_reply_enabled,
            "qq_group_wake_words": settings.qq_group_wake_words,
            "telegram_bot_token": "***" if settings.telegram_bot_token else "",
            "telegram_bot_username": settings.telegram_bot_username,
            "telegram_webhook_secret": "***" if settings.telegram_webhook_secret else "",
            "telegram_reply_enabled": settings.telegram_reply_enabled,
            "telegram_group_wake_words": settings.telegram_group_wake_words,
            "llm_provider": settings.llm_provider,
            "moonshot_base_url": settings.moonshot_base_url,
            "moonshot_model": settings.moonshot_model,
            "moonshot_api_key": "***" if settings.moonshot_api_key else "",
            "deepseek_base_url": settings.deepseek_base_url,
            "deepseek_model": settings.deepseek_model,
            "deepseek_api_key": "***" if settings.deepseek_api_key else "",
            "llm_timeout_seconds": settings.llm_timeout_seconds,
            "llm_context_messages": settings.llm_context_messages,
            "llm_memory_items": settings.llm_memory_items,
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
