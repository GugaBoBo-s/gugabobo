from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from gugabobo.adapters.onebot import OneBotMessageEvent, should_reply_to_event
from gugabobo.config import get_settings
from gugabobo.infra.logs import get_logger
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
        <p>
          <a href="/status">status</a> |
          <a href="/messages">messages</a> |
          <a href="/feedbacks">feedbacks</a>
        </p>
      </body>
    </html>
    """
    return HTMLResponse(html)


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
        "reply": agent.handle_message(
            request.message,
            source="api",
            user_id=request.user_id,
            conversation_id=request.conversation_id,
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
    reply_allowed = should_reply_to_event(event, settings.qq_group_wake_word_list)
    if not reply_allowed:
        route = agent.router.route(text)
        if route.skill == "feedback":
            feedback_id = agent.store.add_feedback(
                source=event.source,
                user_id=event.user_id,
                content=text,
            )
            logger.info("onebot feedback recorded id=%s source=%s", feedback_id, event.source)
            return {"status": "recorded", "feedback_id": feedback_id}
        return {"status": "ignored", "reason": "reply not allowed"}
    reply = agent.handle_message(
        text,
        source=event.source,
        user_id=event.user_id,
        conversation_id=event.conversation_id,
    )
    if settings.napcat_reply_enabled:
        client = NapCatClient()
        if event.message_type == "private":
            client.send_private_msg(event.user_id, reply)
        elif event.message_type == "group" and event.group_id:
            client.send_group_msg(event.group_id, reply)
    logger.info("onebot message handled source=%s user_id=%s", event.source, event.user_id)
    if settings.napcat_reply_enabled:
        return {"status": "ok", "sent": True}
    if settings.napcat_passive_reply_enabled:
        return {"status": "ok", "reply": reply, "sent": False, "passive_reply": True}
    return {"status": "ok", "sent": False, "reply_available": True}
