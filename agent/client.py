import json
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"


class OllamaUnavailableError(Exception):
    pass


def chat(messages, tools=None, stream=False, timeout=120):
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": stream,
        "options": {
            "num_ctx": 65536, #16384 32768 49152 65536 98304 131072 
            "num_predict": 8192 #8192 or 4096 
        },
    }
    if tools:
        payload["tools"] = tools

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


def get_thinking(response_json):
    return response_json.get("message", {}).get("thinking", "")