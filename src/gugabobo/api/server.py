import asyncio
import hmac
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from aiogram.types import Update

from gugabobo.adapters.onebot import OneBotMessageEvent
from gugabobo.adapters.telegram import TelegramIncomingMessage
from gugabobo.adapters.telegram_runtime import TelegramNotificationWorker, TelegramService
from gugabobo.api.dashboard import dashboard_html
from gugabobo.config import get_settings
from gugabobo.core.access import context_with_access_role, evaluate_access, role_can_use_skill
from gugabobo.core.channel import ChannelContext
from gugabobo.core.code_review import OrganizationCodeReviewService
from gugabobo.core.deployment import DeploymentError, DeploymentService
from gugabobo.core.github_issues import GitHubIssueAutomationService
from gugabobo.core.improvement import ImprovementError, ImprovementService
from gugabobo.core.lifecycle import (
    LifecycleError,
    PullRequestLifecycleService,
    is_merge_command,
)
from gugabobo.infra.container_runtime import ContainerRuntime
from gugabobo.infra.env_file import EnvFile
from gugabobo.infra.images import urls_to_data_uris
from gugabobo.infra.logs import get_logger, read_log_lines
from gugabobo.infra.llm import build_agent_runtime
from gugabobo.infra.local_workspace import LocalWorkspace
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.runtime import RuntimeManager, build_agent


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"



@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    notification_task = None
    if settings.telegram_bot_token:
        worker = TelegramNotificationWorker(build_agent().store)
        notification_task = asyncio.create_task(worker.run())
    try:
        yield
    finally:
        if notification_task is not None:
            notification_task.cancel()
            with suppress(asyncio.CancelledError):
                await notification_task


app = FastAPI(
    title="gugabobo API",
    version="0.1.0",
    default_response_class=Utf8JSONResponse,
    lifespan=lifespan,
)
ListLimit = Annotated[int, Query(ge=1, le=500)]


class ChatRequest(BaseModel):
    message: str
    user_id: str = "api"
    conversation_id: str | None = None


class FeedbackCreateRequest(BaseModel):
    content: str
    user_id: str = "api"


class FeedbackStatusRequest(BaseModel):
    status: str


class DashboardChatRequest(BaseModel):
    message: str
    user_id: str = "dashboard"
    conversation_id: str | None = None


class MemoryCreateRequest(BaseModel):
    subject: str = "global"
    content: str
    memory_type: str = "note"
    importance: int = 5


class MemoryUpdateRequest(BaseModel):
    subject: str
    content: str
    memory_type: str
    importance: int


class SummarySetRequest(BaseModel):
    conversation_id: str
    summary: str
    updated_until_message_id: int = 0


class AccessRuleRequest(BaseModel):
    platform: str
    user_id: str
    role: str = "user"
    display_name: str = ""
    notes: str = ""


class ConfigUpdateRequest(BaseModel):
    values: dict[str, object]


class DangerousActionRequest(BaseModel):
    confirm_text: str = ""


class ImprovementCreateRequest(BaseModel):
    feedback_id: int
    scope: str = ""
    risk_level: str = "normal"


class OpenAIChatCompletionRequest(BaseModel):
    model: str = "gugabobo"
    messages: list[dict[str, object]]
    temperature: float = 0.7
    max_tokens: int | None = None


class OpenAIResponsesRequest(BaseModel):
    model: str = "gugabobo"
    input: str | list[dict[str, object]]
    temperature: float = 0.7
    max_output_tokens: int | None = None


def dashboard_owner_context() -> ChannelContext:
    return ChannelContext(
        platform="web",
        channel_type="webhook",
        source="dashboard",
        user_id="admin",
        conversation_id="dashboard:admin",
        is_owner=True,
        is_wake_triggered=True,
    )


def add_dashboard_audit(
    action: str,
    target: str = "",
    status: str = "ok",
    risk_level: str = "normal",
    detail: str = "",
) -> None:
    build_agent().store.add_audit_log(
        actor_source="dashboard",
        actor_user_id="admin",
        action=action,
        target=target,
        status=status,
        risk_level=risk_level,
        detail=detail[:1000],
    )


def require_danger_confirmation(
    request: DangerousActionRequest | None,
    expected_text: str,
) -> None:
    if request is None or request.confirm_text != expected_text:
        raise HTTPException(
            status_code=400,
            detail=f"High-risk action requires confirm_text={expected_text}",
        )


def require_admin_token(x_gugabobo_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    configured_token = (settings.admin_token or "").strip()
    if not configured_token or configured_token == "change-me":
        raise HTTPException(status_code=503, detail="Admin token is not configured")
    if x_gugabobo_admin_token is None or not hmac.compare_digest(
        x_gugabobo_admin_token,
        configured_token,
    ):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def require_tabhere_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    configured_token = settings.tabhere_api_key.strip()
    if not settings.tabhere_enabled or not configured_token:
        raise HTTPException(status_code=503, detail="TabHere 接口未启用或没有配置 API key。")
    prefix = "Bearer "
    presented = authorization[len(prefix) :] if authorization and authorization.startswith(prefix) else ""
    if not presented or not hmac.compare_digest(presented, configured_token):
        raise HTTPException(status_code=401, detail="TabHere API key 无效。")


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content or "")
    parts: list[str] = []
    for part in content:
        if isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _normalized_openai_messages(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for message in messages:
        role = str(message.get("role", "user") or "user")
        if role not in {"system", "user", "assistant"}:
            continue
        normalized.append({"role": role, "content": _message_text(message.get("content"))})
    return LocalWorkspace().expand_file_references(normalized)


def _run_tabhere_completion(
    messages: list[dict[str, object]],
    temperature: float,
    max_tokens: int | None,
) -> tuple[str, str]:
    client = build_agent_runtime()
    if not client.configured:
        raise HTTPException(status_code=503, detail="对话模型尚未配置，TabHere 无法生成补全。")
    try:
        result = client.run_messages(
            _normalized_openai_messages(messages),
            temperature=max(0.0, min(temperature, 2.0)),
            max_tokens=max_tokens,
        )
    except Exception as error:
        get_logger().warning("TabHere completion failed: %s", error)
        raise HTTPException(status_code=502, detail="上游模型补全失败，请检查模型配置和日志。") from error
    return str(result.output), result.model or client.model


@app.get("/")
def root() -> HTMLResponse:
    status_data = build_agent().status()
    html = f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>gugabobo</title>
        <style>
          body {{ font-family: system-ui, sans-serif; margin: 40px; line-height: 1.5; }}
          code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }}
        </style>
      </head>
      <body>
        <h1>gugabobo</h1>
        <p>status: <code>{status_data["status"]}</code></p>
        <p>messages: <code>{status_data["messages"]}</code></p>
        <p>feedbacks: <code>{status_data["feedbacks"]}</code></p>
        <p><a href="/docs">API docs</a></p>
        <p><a href="/dashboard">Dashboard</a></p>
        <p>
          <a href="/status">status</a> |
          <a href="/messages">messages</a> |
          <a href="/feedbacks">feedbacks</a>
        </p>
      </body>
    </html>
    """
    return HTMLResponse(html)


@app.get("/dashboard")
def dashboard() -> HTMLResponse:
    return HTMLResponse(dashboard_html())


@app.get("/dashboard-data")
def dashboard_data(
    conversation_id: str | None = None,
    memory_subject: str | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    settings = get_settings()
    agent = build_agent()
    runtime_manager = RuntimeManager()
    runtime_data = runtime_manager.status()
    status_data = agent.status()
    status_data["memory_items"] = agent.store.count_memory_items()
    status_data["conversation_summaries"] = agent.store.count_conversation_summaries()
    status_data["access_rules"] = agent.store.count_access_rules()
    status_data["audit_logs"] = agent.store.count_audit_logs()
    return {
        "status": status_data,
        "config": {
            "llm_provider": settings.llm_provider,
            "llm_context_messages": settings.llm_context_messages,
            "llm_history_token_budget": settings.llm_history_token_budget,
            "llm_summary_trigger_tokens": settings.llm_summary_trigger_tokens,
            "llm_summary_keep_recent_tokens": settings.llm_summary_keep_recent_tokens,
            "llm_memory_items": settings.llm_memory_items,
            "napcat_reply_enabled": settings.napcat_reply_enabled,
            "napcat_passive_reply_enabled": settings.napcat_passive_reply_enabled,
            "telegram_reply_enabled": settings.telegram_reply_enabled,
            "github_review_enabled": settings.github_review_enabled,
            "github_organization": settings.github_organization,
            "github_issue_enabled": settings.github_issue_enabled,
            "auto_deploy_enabled": settings.auto_deploy_enabled,
        },
        "conversations": agent.store.list_conversations(limit=20),
        "messages": (
            agent.store.list_conversation_messages(conversation_id, limit=50)
            if conversation_id
            else agent.store.list_messages(limit=50)
        ),
        "feedbacks": agent.store.list_feedbacks(limit=20),
        "memories": agent.store.list_memory_items(subject=memory_subject, limit=50),
        "summaries": agent.store.list_conversation_summaries(limit=20),
        "access_rules": agent.store.list_access_rules(limit=50),
        "audit_logs": agent.store.list_audit_logs(limit=50),
        "tasks": agent.store.list_tasks(limit=50),
        "improvements": agent.store.list_improvement_tasks(limit=50),
        "pull_requests": agent.store.list_pull_requests(limit=50),
        "code_reviews": agent.store.list_code_reviews(limit=50),
        "github_issue_runs": agent.store.list_github_issue_runs(limit=50),
        "execution_runs": agent.store.list_execution_runs(limit=100),
        "merge_authorizations": agent.store.list_merge_authorizations(limit=50),
        "improvement_reflections": agent.store.list_improvement_reflections(limit=50),
        "deployment_records": agent.store.list_deployment_records(limit=50),
        "owner_notifications": agent.store.list_owner_notifications(limit=50),
        "outbound_drafts": agent.store.list_outbound_drafts(limit=50),
        "table_counts": agent.store.table_counts(),
        "runtime": runtime_data,
        "qq_diagnostics": runtime_manager.qq_diagnostics(agent.store),
        "telegram_diagnostics": runtime_manager.telegram_diagnostics(
            agent.store,
            runtime_data["telegram_polling"],
        ),
        "logs": read_log_lines(limit=80),
    }


@app.get("/logs")
def logs(limit: ListLimit = 100) -> dict[str, object]:
    return {"lines": read_log_lines(limit=limit)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, object]:
    return build_agent().status()


@app.get("/runtime/status")
def runtime_status(_: None = Depends(require_admin_token)) -> dict[str, object]:
    return RuntimeManager().status()


@app.get("/diagnostics/qq")
def qq_diagnostics(_: None = Depends(require_admin_token)) -> dict[str, object]:
    agent = build_agent()
    return RuntimeManager().qq_diagnostics(agent.store)


@app.get("/diagnostics/telegram")
def telegram_diagnostics(_: None = Depends(require_admin_token)) -> dict[str, object]:
    agent = build_agent()
    return RuntimeManager().telegram_diagnostics(agent.store)


@app.get("/dashboard-control/config")
def dashboard_control_config(_: None = Depends(require_admin_token)) -> dict[str, object]:
    settings = get_settings()
    return {
        "values": {
            "GUGABOBO_OWNER_QQ_IDS": settings.owner_qq_ids,
            "GUGABOBO_OWNER_TELEGRAM_IDS": settings.owner_telegram_ids,
            "GUGABOBO_NAPCAT_DIR": str(settings.napcat_dir),
            "GUGABOBO_NAPCAT_API_URL": settings.napcat_api_url,
            "GUGABOBO_NAPCAT_REPLY_ENABLED": settings.napcat_reply_enabled,
            "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED": settings.napcat_passive_reply_enabled,
            "GUGABOBO_QQ_GROUP_WAKE_WORDS": settings.qq_group_wake_words,
            "GUGABOBO_TELEGRAM_BOT_USERNAME": settings.telegram_bot_username,
            "GUGABOBO_TELEGRAM_REPLY_ENABLED": settings.telegram_reply_enabled,
            "GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS": settings.telegram_group_wake_words,
            "GUGABOBO_TELEGRAM_PROXY": settings.telegram_proxy,
            "GUGABOBO_TELEGRAM_COMMUNITY_GROUP_URL": settings.telegram_community_group_url,
            "GUGABOBO_TELEGRAM_COMPANION_BOT_URL": settings.telegram_companion_bot_url,
            "GUGABOBO_TELEGRAM_ANNOUNCEMENT_CHANNEL_URL": (
                settings.telegram_announcement_channel_url
            ),
            "GUGABOBO_TELEGRAM_SUMMARY_BOT_URL": settings.telegram_summary_bot_url,
            "GUGABOBO_TELEGRAM_DEVELOPER_GUGABOBO_URL": (
                settings.telegram_developer_gugabobo_url
            ),
            "GUGABOBO_TELEGRAM_DEVELOPER_SCARLETKC_URL": (
                settings.telegram_developer_scarletkc_url
            ),
            "GUGABOBO_TELEGRAM_GITHUB_SCARLETKC_URL": settings.telegram_github_scarletkc_url,
            "GUGABOBO_TELEGRAM_GITHUB_FOGMOE_URL": settings.telegram_github_fogmoe_url,
            "GUGABOBO_TELEGRAM_GITHUB_GEYUGONG_URL": settings.telegram_github_geyugong_url,
            "GUGABOBO_TELEGRAM_GITHUB_GUGABOBO_URL": settings.telegram_github_gugabobo_url,
            "GUGABOBO_GITHUB_OWNER": settings.github_owner,
            "GUGABOBO_GITHUB_REPO": settings.github_repo,
            "GUGABOBO_GITHUB_API_URL": settings.github_api_url,
            "GUGABOBO_GITHUB_REVIEW_ENABLED": settings.github_review_enabled,
            "GUGABOBO_GITHUB_ORGANIZATION": settings.github_organization,
            "GUGABOBO_GITHUB_REVIEW_INTERVAL_SECONDS": settings.github_review_interval_seconds,
            "GUGABOBO_GITHUB_REVIEW_MAX_FILES": settings.github_review_max_files,
            "GUGABOBO_GITHUB_REVIEW_MAX_PATCH_CHARS": settings.github_review_max_patch_chars,
            "GUGABOBO_GITHUB_ISSUE_ENABLED": settings.github_issue_enabled,
            "GUGABOBO_GITHUB_ISSUE_INTERVAL_SECONDS": settings.github_issue_interval_seconds,
            "GUGABOBO_GITHUB_ISSUE_MAX_PER_SCAN": settings.github_issue_max_per_scan,
            "GUGABOBO_GITHUB_ISSUE_MIN_CONFIDENCE": settings.github_issue_min_confidence,
            "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_ENABLED": settings.github_issue_auto_fix_enabled,
            "GUGABOBO_GITHUB_ISSUE_AUTO_FIX_REPOSITORIES": settings.github_issue_auto_fix_repositories,
            "GUGABOBO_AUTO_DEPLOY_ENABLED": settings.auto_deploy_enabled,
            "GUGABOBO_LLM_PROVIDER": settings.llm_provider,
            "GUGABOBO_MOONSHOT_BASE_URL": settings.moonshot_base_url,
            "GUGABOBO_MOONSHOT_MODEL": settings.moonshot_model,
            "GUGABOBO_DEEPSEEK_BASE_URL": settings.deepseek_base_url,
            "GUGABOBO_DEEPSEEK_MODEL": settings.deepseek_model,
            "GUGABOBO_OPENAI_BASE_URL": settings.openai_base_url,
            "GUGABOBO_OPENAI_MODEL": settings.openai_model,
            "GUGABOBO_LLM_TIMEOUT_SECONDS": settings.llm_timeout_seconds,
            "GUGABOBO_LLM_CONTEXT_MESSAGES": settings.llm_context_messages,
            "GUGABOBO_LLM_MEMORY_ITEMS": settings.llm_memory_items,
            "GUGABOBO_LLM_HISTORY_TOKEN_BUDGET": settings.llm_history_token_budget,
            "GUGABOBO_LLM_SUMMARY_TRIGGER_TOKENS": settings.llm_summary_trigger_tokens,
            "GUGABOBO_LLM_SUMMARY_KEEP_RECENT_TOKENS": settings.llm_summary_keep_recent_tokens,
            "GUGABOBO_RUNNER_CONTAINER_RUNTIME": settings.runner_container_runtime,
            "GUGABOBO_RUNNER_CONTAINER_IMAGE": settings.runner_container_image,
            "GUGABOBO_CLAUDE_BASE_URL": settings.claude_base_url,
            "GUGABOBO_CODE_CLAUDE_MODEL": settings.code_claude_model,
            "GUGABOBO_CODE_OPENAI_MODEL": settings.code_openai_model,
            "GUGABOBO_CODE_DEEPSEEK_MODEL": settings.code_deepseek_model,
            "GUGABOBO_CODE_DEEPSEEK_RUNNER_MODEL": settings.code_deepseek_runner_model,
            "GUGABOBO_CODE_MODEL_TIMEOUT_SECONDS": settings.code_model_timeout_seconds,
        },
        "secrets": {
            "GUGABOBO_ADMIN_TOKEN": bool(settings.admin_token),
            "GUGABOBO_GITHUB_TOKEN": bool(settings.github_token),
            "GUGABOBO_NAPCAT_ACCESS_TOKEN": bool(settings.napcat_access_token),
            "GUGABOBO_TELEGRAM_BOT_TOKEN": bool(settings.telegram_bot_token),
            "GUGABOBO_TELEGRAM_WEBHOOK_SECRET": bool(settings.telegram_webhook_secret),
            "GUGABOBO_MOONSHOT_API_KEY": bool(settings.moonshot_api_key),
            "GUGABOBO_DEEPSEEK_API_KEY": bool(settings.deepseek_api_key),
            "GUGABOBO_OPENAI_API_KEY": bool(settings.openai_api_key),
            "GUGABOBO_CLAUDE_AUTH_TOKEN": bool(settings.claude_auth_token),
        },
    }


@app.post("/dashboard-control/config")
def dashboard_control_update_config(
    request: ConfigUpdateRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        updated = EnvFile(get_settings().config_file_path).update(request.values)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    get_settings.cache_clear()
    add_dashboard_audit(
        "config.update",
        "env",
        detail=",".join(sorted(updated.keys())),
    )
    return {
        "updated": updated,
        "restart_recommended": True,
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    agent = build_agent()
    return {
        "reply": agent.handle_context_message(
            request.message,
            ChannelContext.api(
                user_id=request.user_id,
                conversation_id=request.conversation_id,
            ),
        )
    }


@app.get("/v1/models")
def openai_models(_: None = Depends(require_tabhere_token)) -> dict[str, object]:
    model = build_agent_runtime().model
    return {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "gugabobo"}]}


@app.post("/v1/chat/completions")
def openai_chat_completions(
    request: OpenAIChatCompletionRequest,
    _: None = Depends(require_tabhere_token),
) -> dict[str, object]:
    content, model = _run_tabhere_completion(
        request.messages, request.temperature, request.max_tokens
    )
    created = int(time.time())
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


@app.post("/v1/responses")
def openai_responses(
    request: OpenAIResponsesRequest,
    _: None = Depends(require_tabhere_token),
) -> dict[str, object]:
    if isinstance(request.input, str):
        messages = [{"role": "user", "content": request.input}]
    else:
        messages = request.input
    content, model = _run_tabhere_completion(
        messages, request.temperature, request.max_output_tokens
    )
    response_id = f"resp_{uuid.uuid4().hex}"
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output_text": content,
        "output": [
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": content, "annotations": []}],
            }
        ],
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


@app.get("/messages")
def messages(
    limit: ListLimit = 20,
    conversation_id: str | None = None,
) -> list[dict[str, object]]:
    agent = build_agent()
    if conversation_id:
        return agent.store.list_conversation_messages(conversation_id, limit=limit)
    return agent.store.list_messages(limit=limit)


@app.get("/messages/{message_id}")
def message(message_id: int) -> dict[str, object]:
    agent = build_agent()
    result = agent.store.get_message(message_id)
    if not result:
        raise HTTPException(status_code=404, detail="Message not found")
    return result


@app.get("/feedbacks")
def feedbacks(limit: ListLimit = 20) -> list[dict[str, object]]:
    agent = build_agent()
    return agent.store.list_feedbacks(limit=limit)


@app.get("/memories")
def memories(subject: str | None = None, limit: ListLimit = 20) -> list[dict[str, object]]:
    return build_agent().store.list_memory_items(subject=subject, limit=limit)


@app.get("/access-rules")
def access_rules(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_access_rules(limit=limit)


@app.get("/audit-logs")
def audit_logs(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_audit_logs(limit=limit)


@app.get("/tasks")
def tasks(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_tasks(limit=limit)


@app.get("/tasks/{task_id}")
def task(task_id: int) -> dict[str, object]:
    result = build_agent().store.get_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@app.get("/improvements")
def improvements(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_improvement_tasks(limit=limit)


@app.get("/prs")
def pull_requests(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_pull_requests(limit=limit)


@app.get("/code-reviews")
def code_reviews(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_code_reviews(limit=limit)


@app.post("/code-reviews/scan")
def scan_code_reviews(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = OrganizationCodeReviewService(build_agent().store).tick()
    add_dashboard_audit(
        "code_review.scan",
        get_settings().github_organization,
        status=str(result["status"]),
        detail=(
            f"repositories={result['repositories']},pull_requests={result['pull_requests']},"
            f"reviewed={result['reviewed']},errors={result['errors']}"
        ),
    )
    return result


@app.get("/github-issues")
def github_issue_runs(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_github_issue_runs(limit=limit)


@app.post("/github-issues/scan")
def scan_github_issues(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = GitHubIssueAutomationService(build_agent().store).tick()
    add_dashboard_audit(
        "github_issue.scan",
        get_settings().github_organization,
        status=str(result["status"]),
        detail=(
            f"repositories={result['repositories']},issues={result['issues']},"
            f"worthwhile={result['worthwhile']},pull_requests={result['pull_requests']},"
            f"errors={result['errors']}"
        ),
    )
    return result


@app.post("/executions/{run_type}/{run_id}/cancel")
def cancel_execution(
    run_type: str,
    run_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "CANCEL")
    if run_type not in {"code_review", "github_issue", "improvement"}:
        raise HTTPException(status_code=404, detail="Execution type not found")
    store = build_agent().store
    record = store.request_execution_cancel(run_type, run_id)
    if record is None:
        raise HTTPException(status_code=409, detail="Execution is not running")
    container_name = str(record.get("container_name", ""))
    container_stopped = ContainerRuntime().stop(container_name) if container_name else False
    add_dashboard_audit(
        "execution.cancel",
        f"{run_type}:{run_id}",
        risk_level="high",
        detail=f"container_stopped={container_stopped}",
    )
    return {
        "run_type": run_type,
        "run_id": run_id,
        "status": "cancel_requested",
        "container_stopped": container_stopped,
    }


@app.post("/executions/{run_type}/{run_id}/retry")
def retry_execution(
    run_type: str,
    run_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "RETRY")
    if run_type not in {"code_review", "github_issue", "improvement"}:
        raise HTTPException(status_code=404, detail="Execution type not found")
    if not build_agent().store.request_execution_retry(run_type, run_id):
        raise HTTPException(
            status_code=409,
            detail="Only failed, cancelled, or stale executions can be retried",
        )
    add_dashboard_audit(
        "execution.retry",
        f"{run_type}:{run_id}",
        risk_level="high",
    )
    return {"run_type": run_type, "run_id": run_id, "status": "retry_requested"}


@app.get("/prs/{pr_id}")
def pull_request(pr_id: int) -> dict[str, object]:
    result = build_agent().store.get_pull_request(pr_id)
    if not result:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return result


@app.get("/merge-authorizations")
def merge_authorizations(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_merge_authorizations(limit=limit)


@app.get("/improvement-reflections")
def improvement_reflections(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_improvement_reflections(limit=limit)


@app.get("/deployments")
def deployments(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_deployment_records(limit=limit)


@app.get("/owner-notifications")
def owner_notifications(limit: ListLimit = 50) -> list[dict[str, object]]:
    return build_agent().store.list_owner_notifications(limit=limit)


@app.post("/prs/{pr_id}/sync")
def sync_pull_request(
    pr_id: int,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        status = ImprovementService(build_agent().store).sync_pull_request(
            pr_id, actor_source="dashboard", actor_user_id="admin"
        )
    except ImprovementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "pull_request_id": status.pull_request_id,
        "number": status.number,
        "status": status.status,
        "checks_status": status.checks_status,
        "merged_at": status.merged_at,
    }


@app.post("/prs/{pr_id}/approve-merge")
def approve_pull_request_merge(
    pr_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "MERGE")
    agent = build_agent()
    record = agent.store.get_pull_request(pr_id)
    if not record:
        raise HTTPException(status_code=404, detail="Pull request not found")
    try:
        outcome = PullRequestLifecycleService(agent.store).approve_merge_record(
            pr_id,
            dashboard_owner_context(),
            f"dashboard approve PR #{record['number']}",
        )
    except LifecycleError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "pull_request_id": pr_id,
        "number": outcome.pr_number,
        "status": outcome.status,
        "checks_status": outcome.checks_status,
        "message": outcome.message,
    }


@app.post("/prs/{pr_id}/reject-merge")
def reject_pull_request_merge(
    pr_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "REJECT")
    agent = build_agent()
    record = agent.store.get_pull_request(pr_id)
    if not record:
        raise HTTPException(status_code=404, detail="Pull request not found")
    try:
        outcome = PullRequestLifecycleService(agent.store).reject_merge_record(
            pr_id,
            dashboard_owner_context(),
            f"dashboard reject PR #{record['number']}",
        )
    except LifecycleError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "pull_request_id": pr_id,
        "number": outcome.pr_number,
        "status": outcome.status,
        "checks_status": outcome.checks_status,
        "message": outcome.message,
    }


@app.post("/prs/sync-all")
def sync_all_pull_requests(
    _: None = Depends(require_admin_token),
) -> dict[str, int]:
    return PullRequestLifecycleService(build_agent().store).tick()


@app.post("/deployments/record-current")
def record_current_deployment(
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "DEPLOYED")
    try:
        outcome = DeploymentService(build_agent().store).record_current(
            actor_source="dashboard",
            actor_user_id="admin",
        )
    except DeploymentError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "current_revision": outcome.current_revision,
        "examined": outcome.examined,
        "deployed": outcome.deployed,
        "pending": outcome.pending,
    }


@app.post("/improvements")
def create_improvement(
    request: ImprovementCreateRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, int]:
    service = ImprovementService(build_agent().store)
    try:
        result = service.create_from_feedback(
            request.feedback_id,
            scope=request.scope,
            risk_level=request.risk_level,
            actor_source="dashboard",
            actor_user_id="admin",
        )
    except ImprovementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"task_id": result.task_id, "improvement_id": result.improvement_id}


@app.post("/improvements/{improvement_id}/approve")
def approve_improvement(
    improvement_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "APPROVE")
    try:
        ImprovementService(build_agent().store).approve(
            improvement_id, actor_source="dashboard", actor_user_id="admin"
        )
    except ImprovementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"improvement_id": improvement_id, "approval_status": "approved"}


@app.post("/improvements/{improvement_id}/run")
def run_improvement(
    improvement_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "RUN")
    try:
        outcome = ImprovementService(build_agent().store).run_improvement(
            improvement_id,
            actor_source="dashboard",
            actor_user_id="admin",
        )
    except ImprovementError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "improvement_id": improvement_id,
        "status": outcome.status,
        "branch_name": outcome.branch_name,
        "detail": outcome.detail,
        "diff": outcome.diff,
    }


@app.post("/improvements/{improvement_id}/ship")
def ship_improvement(
    improvement_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "SHIP")
    try:
        outcome = ImprovementService(build_agent().store).run_and_open_pull_request(
            improvement_id,
            actor_source="dashboard",
            actor_user_id="admin",
        )
    except ImprovementError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "improvement_id": improvement_id,
        "status": outcome.status,
        "branch_name": outcome.branch_name,
        "detail": outcome.detail,
        "pr_number": outcome.pr_number,
        "pr_url": outcome.pr_url,
    }


@app.post("/improvements/{improvement_id}/reject")
def reject_improvement(
    improvement_id: int,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    try:
        ImprovementService(build_agent().store).reject(
            improvement_id, actor_source="dashboard", actor_user_id="admin"
        )
    except ImprovementError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"improvement_id": improvement_id, "approval_status": "rejected"}


@app.post("/improvements/{improvement_id}/pull-request")
def open_improvement_pull_request(
    improvement_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "OPEN")
    try:
        result = ImprovementService(build_agent().store).open_pull_request(
            improvement_id, actor_source="dashboard", actor_user_id="admin"
        )
    except ImprovementError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "improvement_id": improvement_id,
        "pull_request_id": result.pull_request_id,
        "number": result.number,
        "url": result.url,
        "branch_name": result.branch_name,
        "status": result.status,
    }


@app.post("/feedbacks")
def create_feedback(request: FeedbackCreateRequest) -> dict[str, int]:
    agent = build_agent()
    feedback_id = agent.store.add_feedback(
        source="api",
        user_id=request.user_id,
        content=request.content,
    )
    return {"id": feedback_id}


@app.patch("/feedbacks/{feedback_id}")
def update_feedback(feedback_id: int, request: FeedbackStatusRequest) -> dict[str, object]:
    allowed_statuses = {"new", "triaged", "resolved", "ignored"}
    if request.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid feedback status")
    agent = build_agent()
    if not agent.store.update_feedback_status(feedback_id, request.status):
        raise HTTPException(status_code=404, detail="Feedback not found")
    return {"id": feedback_id, "status": request.status}


@app.post("/dashboard-control/chat")
def dashboard_control_chat(
    request: DashboardChatRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, str]:
    agent = build_agent()
    reply = agent.handle_context_message(
        request.message,
        ChannelContext(
            platform="web",
            channel_type="webhook",
            source="dashboard",
            user_id=request.user_id,
            conversation_id=request.conversation_id or f"dashboard:{request.user_id}",
            is_owner=True,
            is_wake_triggered=True,
        ),
    )
    add_dashboard_audit(
        "chat.test",
        request.conversation_id or f"dashboard:{request.user_id}",
    )
    return {"reply": reply}


@app.post("/dashboard-control/memories")
def dashboard_control_add_memory(
    request: MemoryCreateRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, int]:
    memory_id = build_agent().store.add_memory_item(
        subject=request.subject,
        content=request.content,
        memory_type=request.memory_type,
        importance=request.importance,
        source="dashboard",
    )
    add_dashboard_audit("memory.create", f"memory:{memory_id}", detail=request.subject)
    return {"id": memory_id}


@app.patch("/dashboard-control/memories/{memory_id}")
def dashboard_control_update_memory(
    memory_id: int,
    request: MemoryUpdateRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    if not build_agent().store.update_memory_item(
        memory_id=memory_id,
        subject=request.subject,
        content=request.content,
        memory_type=request.memory_type,
        importance=request.importance,
    ):
        raise HTTPException(status_code=404, detail="Memory not found")
    add_dashboard_audit("memory.update", f"memory:{memory_id}", detail=request.subject)
    return {"id": memory_id}


@app.delete("/dashboard-control/memories/{memory_id}")
def dashboard_control_delete_memory(
    memory_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "DELETE")
    if not build_agent().store.delete_memory_item(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    add_dashboard_audit("memory.delete", f"memory:{memory_id}", risk_level="high")
    return {"id": memory_id, "deleted": True}


@app.post("/dashboard-control/summaries")
def dashboard_control_set_summary(
    request: SummarySetRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, str]:
    build_agent().store.upsert_conversation_summary(
        conversation_id=request.conversation_id,
        summary=request.summary,
        updated_until_message_id=request.updated_until_message_id,
    )
    add_dashboard_audit("summary.upsert", request.conversation_id)
    return {"conversation_id": request.conversation_id}


@app.delete("/dashboard-control/summaries/{conversation_id}")
def dashboard_control_delete_summary(
    conversation_id: str,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "DELETE")
    if not build_agent().store.delete_conversation_summary(conversation_id):
        raise HTTPException(status_code=404, detail="Summary not found")
    add_dashboard_audit("summary.delete", conversation_id, risk_level="high")
    return {"conversation_id": conversation_id, "deleted": True}


@app.delete("/dashboard-control/conversations/{conversation_id}/messages")
def dashboard_control_clear_conversation_messages(
    conversation_id: str,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "CLEAR")
    deleted = build_agent().store.delete_conversation_messages(conversation_id)
    add_dashboard_audit(
        "conversation.messages.delete",
        conversation_id,
        risk_level="high",
        detail=str(deleted),
    )
    return {"conversation_id": conversation_id, "deleted": deleted}


@app.post("/dashboard-control/access-rules")
def dashboard_control_upsert_access_rule(
    request: AccessRuleRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, int]:
    allowed_roles = {"owner", "trusted", "user", "blocked"}
    if request.role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Invalid access role")
    rule_id = build_agent().store.upsert_access_rule(
        platform=request.platform,
        user_id=request.user_id,
        role=request.role,
        display_name=request.display_name,
        notes=request.notes,
    )
    add_dashboard_audit(
        "access_rule.upsert",
        f"{request.platform}:{request.user_id}",
        detail=request.role,
    )
    return {"id": rule_id}


@app.delete("/dashboard-control/access-rules/{rule_id}")
def dashboard_control_delete_access_rule(
    rule_id: int,
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "DELETE")
    if not build_agent().store.delete_access_rule(rule_id):
        raise HTTPException(status_code=404, detail="Access rule not found")
    add_dashboard_audit("access_rule.delete", f"access_rule:{rule_id}", risk_level="high")
    return {"id": rule_id, "deleted": True}


@app.post("/dashboard-control/runtime/telegram/start")
def dashboard_control_start_telegram_polling(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = RuntimeManager().start_telegram_polling()
    add_dashboard_audit("runtime.telegram.start", status=str(result.get("status", "ok")))
    return result


@app.post("/dashboard-control/runtime/telegram/stop")
def dashboard_control_stop_telegram_polling(
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "STOP")
    result = RuntimeManager().stop_telegram_polling()
    add_dashboard_audit(
        "runtime.telegram.stop",
        status=str(result.get("status", "ok")),
        risk_level="high",
    )
    return result


@app.post("/dashboard-control/runtime/napcat/start")
def dashboard_control_start_napcat(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = RuntimeManager().start_napcat()
    add_dashboard_audit("runtime.napcat.start", status=str(result.get("status", "ok")))
    return result


@app.post("/dashboard-control/runtime/napcat/stop")
def dashboard_control_stop_napcat(
    request: DangerousActionRequest | None = None,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    require_danger_confirmation(request, "STOP")
    result = RuntimeManager().stop_napcat()
    add_dashboard_audit(
        "runtime.napcat.stop",
        status=str(result.get("status", "ok")),
        risk_level="high",
    )
    return result


@app.post("/dashboard-control/diagnostics/onebot-test")
def dashboard_control_onebot_test(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    event = OneBotMessageEvent.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": "dashboard-diagnostic",
            "raw_message": "ping",
            "message": "ping",
        }
    )
    context = event.to_channel_context(
        owner_ids=get_settings().owner_qq_id_set,
        group_wake_words=get_settings().qq_group_wake_word_list,
    )
    result = {
        "status": "ok",
        "mode": "parse_only",
        "reply_sent": False,
        "conversation_id": context.conversation_id,
        "reply_allowed": context.is_wake_triggered,
    }
    add_dashboard_audit("diagnostic.onebot_test", status="ok", detail="parse_only")
    return result


@app.post("/dashboard-control/diagnostics/telegram-test")
def dashboard_control_telegram_test(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    update = Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "date": 1,
                "from": {
                    "id": 1,
                    "is_bot": False,
                    "first_name": "dashboard",
                    "username": "dashboard_test",
                },
                "chat": {"id": 1, "type": "private"},
                "text": "ping",
            },
        }
    )
    incoming = TelegramIncomingMessage.from_update(update)
    if incoming is None:
        raise HTTPException(status_code=500, detail="Telegram diagnostic update is invalid")
    settings = get_settings()
    context = incoming.to_channel_context(
        owner_ids=settings.owner_telegram_id_set,
        group_wake_words=settings.telegram_group_wake_word_list,
        bot_username=settings.telegram_bot_username,
    )
    result = {
        "status": "ok",
        "mode": "parse_only",
        "reply_sent": False,
        "conversation_id": context.conversation_id,
        "reply_allowed": context.is_wake_triggered,
    }
    add_dashboard_audit("diagnostic.telegram_test", status="ok", detail="parse_only")
    return result


@app.post("/dashboard-control/diagnostics/telegram-getme")
async def dashboard_control_telegram_get_me(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = await RuntimeManager().telegram_get_me()
    add_dashboard_audit(
        "diagnostic.telegram_getme",
        status=str(result.get("status", "ok")),
        detail=str(result),
    )
    return result


@app.patch("/dashboard-control/feedbacks/{feedback_id}")
def dashboard_control_update_feedback(
    feedback_id: int,
    request: FeedbackStatusRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    result = update_feedback(feedback_id, request)
    add_dashboard_audit("feedback.update", f"feedback:{feedback_id}", detail=request.status)
    return result


@app.post("/onebot/v11/events")
def onebot_event(payload: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    logger = get_logger()
    event = OneBotMessageEvent.from_payload(payload)
    if event.post_type != "message":
        return {"status": "ignored", "reason": "non-message event"}
    text = event.text_content()
    image_urls = event.image_urls()
    if not text and not image_urls:
        return {"status": "ignored", "reason": "empty message"}
    agent = build_agent()
    context = event.to_channel_context(
        owner_ids=settings.owner_qq_id_set,
        group_wake_words=settings.qq_group_wake_word_list,
    )
    access = evaluate_access(context, agent.store)
    if not access.allowed:
        logger.info(
            "onebot message ignored source=%s user_id=%s reason=%s",
            context.source,
            context.user_id,
            access.reason,
        )
        return {"status": "ignored", "reason": access.reason}
    context = context_with_access_role(context, access)
    reply_allowed = context.is_wake_triggered or (
        context.is_owner and is_merge_command(text)
    )
    if not reply_allowed:
        route = agent.router.route(text)
        if route.skill == "feedback":
            if not role_can_use_skill(access.role, "feedback"):
                return {"status": "ignored", "reason": "insufficient role"}
            feedback_id = agent.store.add_feedback(
                source=context.source,
                user_id=context.user_id,
                content=text,
            )
            logger.info("onebot feedback recorded id=%s source=%s", feedback_id, context.source)
            return {"status": "recorded", "feedback_id": feedback_id}
        return {"status": "ignored", "reason": "reply not allowed"}
    images = urls_to_data_uris(image_urls) if image_urls else None
    reply = agent.handle_context_message(text, context, images=images)
    if settings.napcat_reply_enabled:
        client = NapCatClient()
        if context.channel_type == "private":
            client.send_private_msg(context.user_id, reply)
        elif context.channel_type == "group" and context.group_id:
            client.send_group_msg(context.group_id, reply)
    logger.info("onebot message handled source=%s user_id=%s", context.source, context.user_id)
    if settings.napcat_reply_enabled:
        return {"status": "ok", "sent": True}
    if settings.napcat_passive_reply_enabled:
        return {"status": "ok", "reply": reply, "sent": False, "passive_reply": True}
    return {"status": "ok", "sent": False, "reply_available": True}


@app.post("/telegram/events")
async def telegram_event(
    payload: dict[str, object],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    async with TelegramService(
        agent=build_agent(),
        settings=settings,
        send_replies=settings.telegram_reply_enabled,
    ) as service:
        return await service.process_raw_update(payload)
