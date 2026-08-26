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
            "num_ctx": 32768,
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


def chat_stream(messages, tools=None, timeout=120, on_token=None):
    # Stream content to the terminal while returning the same shape as chat().
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": 32768,
        },
    }
    if tools:
        payload["tools"] = tools

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=timeout, stream=True)
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

    accumulated_content = ""
    final_tool_calls = None
    final_thinking = ""

    try:
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)

            message = chunk.get("message", {})

            content_piece = message.get("content", "")
            if content_piece:
                accumulated_content += content_piece
                if on_token:
                    on_token(content_piece)

            thinking_piece = message.get("thinking", "")
            if thinking_piece:
                final_thinking += thinking_piece

            if message.get("tool_calls"):
                final_tool_calls = message["tool_calls"]

            if chunk.get("done"):
                break
    except requests.exceptions.RequestException as e:
        raise OllamaUnavailableError(f"Connection lost while streaming: {e}")

    # Normalize the streamed response so the rest of the agent is transport-agnostic.
    return {
        "message": {
            "role": "assistant",
            "content": accumulated_content,
            "thinking": final_thinking,
            "tool_calls": final_tool_calls,
        },
        "done": True,
    }


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