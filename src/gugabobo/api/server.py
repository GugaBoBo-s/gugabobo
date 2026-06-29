from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from gugabobo.adapters.onebot import OneBotMessageEvent
from gugabobo.adapters.telegram_runtime import handle_telegram_update
from gugabobo.api.dashboard import dashboard_html
from gugabobo.config import get_settings
from gugabobo.core.access import evaluate_access
from gugabobo.core.channel import ChannelContext
from gugabobo.infra.env_file import EnvFile
from gugabobo.infra.logs import get_logger, read_log_lines
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.runtime import RuntimeManager, build_agent


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="gugabobo API", version="0.1.0", default_response_class=Utf8JSONResponse)


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


def require_admin_token(x_gugabobo_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if settings.admin_token and x_gugabobo_admin_token != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


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
def dashboard_data() -> dict[str, object]:
    settings = get_settings()
    agent = build_agent()
    status_data = agent.status()
    status_data["memory_items"] = agent.store.count_memory_items()
    status_data["conversation_summaries"] = agent.store.count_conversation_summaries()
    status_data["access_rules"] = agent.store.count_access_rules()
    return {
        "status": status_data,
        "config": {
            "llm_provider": settings.llm_provider,
            "llm_context_messages": settings.llm_context_messages,
            "llm_memory_items": settings.llm_memory_items,
            "napcat_reply_enabled": settings.napcat_reply_enabled,
            "napcat_passive_reply_enabled": settings.napcat_passive_reply_enabled,
            "telegram_reply_enabled": settings.telegram_reply_enabled,
        },
        "conversations": agent.store.list_conversations(limit=20),
        "messages": agent.store.list_messages(limit=20),
        "feedbacks": agent.store.list_feedbacks(limit=20),
        "memories": agent.store.list_memory_items(limit=20),
        "summaries": agent.store.list_conversation_summaries(limit=20),
        "access_rules": agent.store.list_access_rules(limit=50),
        "table_counts": agent.store.table_counts(),
        "runtime": RuntimeManager().status(),
        "qq_diagnostics": RuntimeManager().qq_diagnostics(agent.store),
        "logs": read_log_lines(limit=80),
    }


@app.get("/logs")
def logs(limit: int = 100) -> dict[str, object]:
    return {"lines": read_log_lines(limit=limit)}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, object]:
    return build_agent().status()


@app.get("/runtime/status")
def runtime_status() -> dict[str, object]:
    return RuntimeManager().status()


@app.get("/diagnostics/qq")
def qq_diagnostics() -> dict[str, object]:
    agent = build_agent()
    return RuntimeManager().qq_diagnostics(agent.store)


@app.get("/dashboard-control/config")
def dashboard_control_config(_: None = Depends(require_admin_token)) -> dict[str, object]:
    settings = get_settings()
    return {
        "values": {
            "GUGABOBO_OWNER_QQ_IDS": settings.owner_qq_ids,
            "GUGABOBO_OWNER_TELEGRAM_IDS": settings.owner_telegram_ids,
            "GUGABOBO_NAPCAT_API_URL": settings.napcat_api_url,
            "GUGABOBO_NAPCAT_REPLY_ENABLED": settings.napcat_reply_enabled,
            "GUGABOBO_NAPCAT_PASSIVE_REPLY_ENABLED": settings.napcat_passive_reply_enabled,
            "GUGABOBO_QQ_GROUP_WAKE_WORDS": settings.qq_group_wake_words,
            "GUGABOBO_TELEGRAM_BOT_USERNAME": settings.telegram_bot_username,
            "GUGABOBO_TELEGRAM_REPLY_ENABLED": settings.telegram_reply_enabled,
            "GUGABOBO_TELEGRAM_GROUP_WAKE_WORDS": settings.telegram_group_wake_words,
            "GUGABOBO_LLM_PROVIDER": settings.llm_provider,
            "GUGABOBO_MOONSHOT_BASE_URL": settings.moonshot_base_url,
            "GUGABOBO_MOONSHOT_MODEL": settings.moonshot_model,
            "GUGABOBO_DEEPSEEK_BASE_URL": settings.deepseek_base_url,
            "GUGABOBO_DEEPSEEK_MODEL": settings.deepseek_model,
            "GUGABOBO_LLM_TIMEOUT_SECONDS": settings.llm_timeout_seconds,
            "GUGABOBO_LLM_CONTEXT_MESSAGES": settings.llm_context_messages,
            "GUGABOBO_LLM_MEMORY_ITEMS": settings.llm_memory_items,
        },
        "secrets": {
            "GUGABOBO_ADMIN_TOKEN": bool(settings.admin_token),
            "GUGABOBO_NAPCAT_ACCESS_TOKEN": bool(settings.napcat_access_token),
            "GUGABOBO_TELEGRAM_BOT_TOKEN": bool(settings.telegram_bot_token),
            "GUGABOBO_TELEGRAM_WEBHOOK_SECRET": bool(settings.telegram_webhook_secret),
            "GUGABOBO_MOONSHOT_API_KEY": bool(settings.moonshot_api_key),
            "GUGABOBO_DEEPSEEK_API_KEY": bool(settings.deepseek_api_key),
        },
    }


@app.post("/dashboard-control/config")
def dashboard_control_update_config(
    request: ConfigUpdateRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    updated = EnvFile(get_settings().config_file_path).update(request.values)
    get_settings.cache_clear()
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


@app.get("/messages")
def messages(
    limit: int = 20,
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
def feedbacks(limit: int = 20) -> list[dict[str, object]]:
    agent = build_agent()
    return agent.store.list_feedbacks(limit=limit)


@app.get("/memories")
def memories(subject: str | None = None, limit: int = 20) -> list[dict[str, object]]:
    return build_agent().store.list_memory_items(subject=subject, limit=limit)


@app.get("/access-rules")
def access_rules(limit: int = 50) -> list[dict[str, object]]:
    return build_agent().store.list_access_rules(limit=limit)


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
    return {"id": memory_id}


@app.delete("/dashboard-control/memories/{memory_id}")
def dashboard_control_delete_memory(
    memory_id: int,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    if not build_agent().store.delete_memory_item(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
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
    return {"conversation_id": request.conversation_id}


@app.delete("/dashboard-control/summaries/{conversation_id}")
def dashboard_control_delete_summary(
    conversation_id: str,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    if not build_agent().store.delete_conversation_summary(conversation_id):
        raise HTTPException(status_code=404, detail="Summary not found")
    return {"conversation_id": conversation_id, "deleted": True}


@app.delete("/dashboard-control/conversations/{conversation_id}/messages")
def dashboard_control_clear_conversation_messages(
    conversation_id: str,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    deleted = build_agent().store.delete_conversation_messages(conversation_id)
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
    return {"id": rule_id}


@app.delete("/dashboard-control/access-rules/{rule_id}")
def dashboard_control_delete_access_rule(
    rule_id: int,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    if not build_agent().store.delete_access_rule(rule_id):
        raise HTTPException(status_code=404, detail="Access rule not found")
    return {"id": rule_id, "deleted": True}


@app.post("/dashboard-control/runtime/telegram/start")
def dashboard_control_start_telegram_polling(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return RuntimeManager().start_telegram_polling()


@app.post("/dashboard-control/runtime/telegram/stop")
def dashboard_control_stop_telegram_polling(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return RuntimeManager().stop_telegram_polling()


@app.post("/dashboard-control/diagnostics/onebot-test")
def dashboard_control_onebot_test(
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return onebot_event(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": "ping",
            "message": "ping",
        }
    )


@app.patch("/dashboard-control/feedbacks/{feedback_id}")
def dashboard_control_update_feedback(
    feedback_id: int,
    request: FeedbackStatusRequest,
    _: None = Depends(require_admin_token),
) -> dict[str, object]:
    return update_feedback(feedback_id, request)


@app.post("/onebot/v11/events")
def onebot_event(payload: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    logger = get_logger()
    event = OneBotMessageEvent.from_payload(payload)
    if event.post_type != "message":
        return {"status": "ignored", "reason": "non-message event"}
    text = event.text_content()
    if not text:
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
    reply_allowed = context.is_wake_triggered
    if not reply_allowed:
        route = agent.router.route(text)
        if route.skill == "feedback":
            feedback_id = agent.store.add_feedback(
                source=context.source,
                user_id=context.user_id,
                content=text,
            )
            logger.info("onebot feedback recorded id=%s source=%s", feedback_id, context.source)
            return {"status": "recorded", "feedback_id": feedback_id}
        return {"status": "ignored", "reason": "reply not allowed"}
    reply = agent.handle_context_message(text, context)
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
def telegram_event(
    payload: dict[str, object],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, object]:
    settings = get_settings()
    if settings.telegram_webhook_secret:
        if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
            raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")
    return handle_telegram_update(
        payload,
        agent=build_agent(),
        settings=settings,
        send_reply=settings.telegram_reply_enabled,
    )
