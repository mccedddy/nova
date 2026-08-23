"""
Thin wrapper around Ollama's /api/chat endpoint.

Known quirk (confirmed against qwen2.5-coder:14b on Ollama 0.30.10):
Even when a `tools` list is passed, the model sometimes emits a tool call
as tool-call-shaped text inside `message.content` (either raw JSON, or
wrapped in <tool_call>...</tool_call> tags per the qwen chat template)
instead of Ollama promoting it to the structured `message.tool_calls` field.

So every response has to be checked on BOTH paths:
  1. native: message["tool_calls"]
  2. fallback: try to parse message["content"] as a tool call shape
"""

import json
import re
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen2.5-coder:14b"

_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)


def chat(messages, tools=None, stream=False, timeout=120):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools

    response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def extract_tool_calls(response_json):
    message = response_json.get("message", {})

    native_calls = message.get("tool_calls")
    if native_calls:
        extracted = []
        for call in native_calls:
            func = call.get("function", {})
            name = func.get("name")
            args = func.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            extracted.append({"name": name, "arguments": args or {}})
        return extracted

    content = message.get("content", "")
    if not content:
        return []

    candidate = content.strip()

    tag_match = _TOOL_CALL_TAG_RE.search(candidate)
    if tag_match:
        candidate = tag_match.group(1)

    parsed = _try_parse_tool_json(candidate)
    if parsed is not None:
        return [parsed]

    return []


def _try_parse_tool_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = re.sub(r"^json\s*", "", text, flags=re.IGNORECASE).strip()

    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None

    if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
        return {"name": obj["name"], "arguments": obj["arguments"] or {}}

    return None


def get_final_text(response_json):
    return response_json.get("message", {}).get("content", "")