import json
import requests

from settings import MODEL, OLLAMA_REQUEST_TIMEOUT, OLLAMA_URL, NUM_CTX, NUM_PREDICT


class OllamaUnavailableError(Exception):
    pass


def chat(messages, tools=None, stream=False, timeout=OLLAMA_REQUEST_TIMEOUT, num_predict=None, think=None):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT if num_predict is None else num_predict,
        },
    }
    if tools:
        payload["tools"] = tools
    # Only sent when explicitly requested, so the main agent's payload is
    # unchanged. Memory extraction sets think=False: on hybrid reasoning models
    # (qwen3.5 and similar) thinking otherwise consumes the entire num_predict
    # budget and the reply comes back with zero characters.
    if think is not None:
        payload["think"] = think

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        raise OllamaUnavailableError(
            "Can't reach Ollama at localhost:11434. Is 'ollama serve' running?"
        )
    except requests.exceptions.Timeout:
        raise OllamaUnavailableError(
            f"Ollama didn't respond within {timeout}s -- it may be overloaded or stuck."
        )
    except requests.exceptions.HTTPError:
        detail = response.text[:500]
        raise OllamaUnavailableError(
            f"Ollama returned {response.status_code}: {detail}"
        )

    return response.json()

def extract_tool_calls(response_json):
    message = response_json.get("message", {})

    native_calls = message.get("tool_calls")
    if not native_calls:
        return []

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


def get_final_text(response_json):
    return response_json.get("message", {}).get("content", "")