from uuid import uuid4
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests

from agent import memory as memory_store
from agent.loop import (
    run_turn_events,
    resolve_permission,
)
from agent.prompts import build_system_prompt
from settings import (
    API_HEALTH_TIMEOUT,
    BOOL_KEYS,
    DEFAULTS,
    INTEGER_RANGES,
    STRING_CHOICES,
    _load_settings,
    save_settings,
)

app = FastAPI(title="N.O.V.A. API")

CONVERSATIONS = {}

# Conversation ids currently in incognito mode. Tracked separately from
# CONVERSATIONS because that dict holds only message lists.
INCOGNITO = set()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    incognito: bool = False

class PermissionRequest(BaseModel):
    conversation_id: str
    approved: bool

class SettingsUpdate(BaseModel):
    values: dict

def _new_conversation(incognito=False):
    return [{"role": "system", "content": build_system_prompt(incognito)}]


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

    # A mode change rebuilds the conversation: the memory block is baked into
    # messages[0], so toggling mid-conversation would otherwise leave the
    # previous mode's memory visible to the model.
    mode_changed = (conv_id in INCOGNITO) != req.incognito
    fresh = conv_id not in CONVERSATIONS or mode_changed

    if fresh:
        CONVERSATIONS[conv_id] = _new_conversation(req.incognito)

    if req.incognito:
        INCOGNITO.add(conv_id)
    else:
        INCOGNITO.discard(conv_id)

    messages = CONVERSATIONS[conv_id]

    def event_stream():
        yield json.dumps({"type": "conversation_id", "id": conv_id}) + "\n"
        if fresh:
            yield json.dumps({"type": "session_mode", "incognito": req.incognito}) + "\n"
        for event in run_turn_events(
            req.message,
            messages,
            conv_id,
            incognito=req.incognito,
        ):
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@app.post("/permission")
def permission_endpoint(req: PermissionRequest):
    resolved = resolve_permission(
        req.conversation_id,
        req.approved,
    )

    if not resolved:
        return {
            "ok": False,
            "error": "No pending permission request.",
        }

    return {
        "ok": True,
        "approved": req.approved,
    }

@app.get("/settings")
def get_settings():
    return {
        "values": _load_settings(),
        "defaults": DEFAULTS,
        "ranges": INTEGER_RANGES,
        "bools": sorted(BOOL_KEYS),
        "choices": {k: list(v) for k, v in STRING_CHOICES.items()},
    }

@app.post("/settings")
def update_settings(req: SettingsUpdate):
    merged, rejected = save_settings(req.values)
    return {
        "ok": True,
        "values": merged,
        "rejected": rejected,
        "restart_required": True,
    }

@app.get("/memory")
def read_memory():
    return memory_store.list_entries()

@app.delete("/memory/{key}")
def delete_memory(key: str):
    result = memory_store.forget(key)
    if result.get("forgotten"):
        return {"ok": True, "deleted": result}
    return {"ok": False, "deleted": None, "error": result.get("error", "")}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)