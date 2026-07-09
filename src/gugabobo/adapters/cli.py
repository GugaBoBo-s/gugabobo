import time

import typer
import uvicorn

from gugabobo.adapters.telegram_runtime import handle_telegram_update
from gugabobo.config import get_settings
from gugabobo.core.channel import ChannelContext
from gugabobo.core.improvement import ImprovementError, ImprovementService
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
tasks_app = typer.Typer(help="Task commands")
improve_app = typer.Typer(help="Self-improvement commands")
pr_app = typer.Typer(help="Pull request commands")
app.add_typer(feedback_app, name="feedback")
app.add_typer(messages_app, name="messages")
app.add_typer(config_app, name="config")
app.add_typer(db_app, name="db")
app.add_typer(memory_app, name="memory")
app.add_typer(summary_app, name="summary")
app.add_typer(telegram_app, name="telegram")
app.add_typer(tasks_app, name="tasks")
app.add_typer(improve_app, name="improve")
app.add_typer(pr_app, name="pr")


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


@tasks_app.command("list")
def tasks_list(limit: int = 50) -> None:
    """List tasks."""
    for item in build_agent().store.list_tasks(limit=limit):
        typer.echo(f"#{item['id']} [{item['status']}] {item['title']} ({item['assigned_skill']})")


@tasks_app.command("show")
def tasks_show(task_id: int) -> None:
    """Show one task."""
    task = build_agent().store.get_task(task_id)
    if not task:
        raise typer.BadParameter(f"task #{task_id} not found")
    echo_mapping(task)


@improve_app.command("create")
def improve_create(
    feedback_id: int,
    scope: str = "",
    risk: str = typer.Option("normal", help="Risk level."),
) -> None:
    """Create an improvement task from a feedback item."""
    service = ImprovementService(build_agent().store)
    try:
        result = service.create_from_feedback(feedback_id, scope=scope, risk_level=risk)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        f"已创建改进任务 #{result.improvement_id}（task #{result.task_id}），来自反馈 #{feedback_id}。"
    )


@improve_app.command("list")
def improve_list(limit: int = 50) -> None:
    """List improvement tasks."""
    for item in build_agent().store.list_improvement_tasks(limit=limit):
        typer.echo(
            f"#{item['id']} [{item['approval_status']}/{item['runner_status']}] "
            f"{item['repo']} feedback=#{item['feedback_id']}"
        )


@improve_app.command("approve")
def improve_approve(improvement_id: int) -> None:
    """Approve an improvement task."""
    try:
        ImprovementService(build_agent().store).approve(improvement_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"已批准改进任务 #{improvement_id}。")


@improve_app.command("reject")
def improve_reject(improvement_id: int) -> None:
    """Reject an improvement task."""
    try:
        ImprovementService(build_agent().store).reject(improvement_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"已拒绝改进任务 #{improvement_id}。")


@improve_app.command("run")
def improve_run(improvement_id: int) -> None:
    """Run Claude Code in a sandbox for an approved improvement task."""
    try:
        outcome = ImprovementService(build_agent().store).run_improvement(improvement_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"改进任务 #{improvement_id} 运行结果：{outcome.status}（分支 {outcome.branch_name}）")
    if outcome.status == "changes_ready":
        typer.echo(f"生成 diff 长度：{len(outcome.diff)} 字符")
    elif outcome.status == "failed" and outcome.detail:
        typer.echo(f"失败详情：{outcome.detail}")


@improve_app.command("ship")
def improve_ship(improvement_id: int) -> None:
    """Run Claude Code in a sandbox, gate on checks, then push a pull request."""
    try:
        outcome = ImprovementService(build_agent().store).run_and_open_pull_request(improvement_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"改进任务 #{improvement_id} 结果：{outcome.status}（分支 {outcome.branch_name}）")
    if outcome.status == "pr_open":
        typer.echo(f"已创建 PR #{outcome.pr_number}: {outcome.pr_url}")
    elif outcome.status == "checks_failed":
        typer.echo("沙箱检查未通过，未开 PR。")


@improve_app.command("pr")
def improve_pr(improvement_id: int) -> None:
    """Open a pull request for an approved improvement task."""
    try:
        result = ImprovementService(build_agent().store).open_pull_request(improvement_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"已创建 PR #{result.number}: {result.url}")


@pr_app.command("list")
def pr_list(limit: int = 50) -> None:
    """List recorded pull requests."""
    for item in build_agent().store.list_pull_requests(limit=limit):
        typer.echo(
            f"#{item['id']} PR#{item['number']} [{item['status']}] "
            f"{item['github_owner']}/{item['github_repo']} {item['url']}"
        )


@pr_app.command("show")
def pr_show(pr_id: int) -> None:
    """Show one recorded pull request."""
    pull_request = build_agent().store.get_pull_request(pr_id)
    if not pull_request:
        raise typer.BadParameter(f"pull request #{pr_id} not found")
    echo_mapping(pull_request)


@pr_app.command("sync")
def pr_sync(pr_id: int) -> None:
    """Refresh a pull request's status and checks from GitHub."""
    try:
        status = ImprovementService(build_agent().store).sync_pull_request(pr_id)
    except ImprovementError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(
        f"PR #{status.number} 状态：{status.status}，检查：{status.checks_status}"
        + (f"，合并于 {status.merged_at}" if status.merged_at else "")
    )


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
            "napcat_dir": settings.napcat_dir,
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
            "github_token": "***" if settings.github_token else "",
            "github_owner": settings.github_owner,
            "github_repo": settings.github_repo,
            "github_api_url": settings.github_api_url,
            "git_author_name": settings.git_author_name,
            "git_author_email": settings.git_author_email,
            "sandbox_dir": settings.sandbox_dir,
            "claude_bin": settings.claude_bin,
            "claude_permission_mode": settings.claude_permission_mode,
            "claude_timeout_seconds": settings.claude_timeout_seconds,
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
