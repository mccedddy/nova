from datetime import datetime
from uuid import uuid4
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests

from agent.loop_events import run_turn_events
from agent.prompts import SYSTEM_PROMPT
from settings import API_HEALTH_TIMEOUT

app = FastAPI(title="N.O.V.A. API")

CONVERSATIONS = {}


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


def _new_conversation():
    current_date = datetime.now().strftime("%A, %B %d, %Y, %I:%M %p")
    system_prompt_with_date = (
        f"{SYSTEM_PROMPT}\n\nToday's real date and time is {current_date}. "
        "Use this for any date/time-relative reasoning -- do not guess or assume what year or date it is."
    )
    return [{"role": "system", "content": system_prompt_with_date}]


@app.get("/health")
def health():
    ollama_ok = True
    try:
        requests.get("http://localhost:11434", timeout=API_HEALTH_TIMEOUT)
    except requests.exceptions.RequestException:
        ollama_ok = False
    return {"api": "ok", "ollama_reachable": ollama_ok}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    conv_id = req.conversation_id or str(uuid4())

    if conv_id not in CONVERSATIONS:
        CONVERSATIONS[conv_id] = _new_conversation()

    messages = CONVERSATIONS[conv_id]

    def event_stream():
        yield json.dumps({"type": "conversation_id", "id": conv_id}) + "\n"
        for event in run_turn_events(req.message, messages):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)