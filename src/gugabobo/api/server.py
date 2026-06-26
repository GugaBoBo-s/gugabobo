from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from gugabobo.adapters.onebot import OneBotMessageEvent
from gugabobo.adapters.telegram_runtime import handle_telegram_update
from gugabobo.api.dashboard import dashboard_html
from gugabobo.config import get_settings
from gugabobo.core.channel import ChannelContext
from gugabobo.infra.logs import get_logger, read_log_lines
from gugabobo.infra.napcat_client import NapCatClient
from gugabobo.infra.runtime import build_agent


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
        "table_counts": agent.store.table_counts(),
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
def messages(limit: int = 20) -> list[dict[str, object]]:
    agent = build_agent()
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
