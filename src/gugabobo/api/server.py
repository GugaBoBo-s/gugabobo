from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gugabobo.infra.runtime import build_agent

app = FastAPI(title="gugabobo API", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    user_id: str = "api"


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
        <p><a href="/status">status</a> | <a href="/feedbacks">feedbacks</a></p>
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
    return {"reply": agent.handle_message(request.message, source="api", user_id=request.user_id)}


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
