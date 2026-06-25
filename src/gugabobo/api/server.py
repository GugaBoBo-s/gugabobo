from fastapi import FastAPI
from pydantic import BaseModel

from gugabobo.infra.runtime import build_agent

app = FastAPI(title="gugabobo API", version="0.1.0")


class ChatRequest(BaseModel):
    message: str
    user_id: str = "api"


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


@app.get("/feedbacks")
def feedbacks(limit: int = 20) -> list[dict[str, object]]:
    agent = build_agent()
    return agent.store.list_feedbacks(limit=limit)

