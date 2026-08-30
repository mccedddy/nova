// Thin client for the Phase 7 NOVA API from the Electron main process.
//
// The API returns newline-delimited JSON: one event object per line, e.g.
//   {"type": "tool_started", "name": "...", "args": {...}}
//   {"type": "tool_finished", "name": "...", "result": {...}}
//   {"type": "answer", "text": "..."}
//   {"type": "error", "message": "..."}
//
// Some events may also carry an optional "tier" field ("read" | "modify" |
// "destructive") once the API surfaces Phase 8 permission context to
// clients -- the renderer already knows how to color those, so no client
// changes should be needed when that lands.

class ApiError extends Error {}

async function checkHealth(baseUrl) {
  const res = await fetch(`${baseUrl}/health`, { method: "GET" });
  if (!res.ok) {
    throw new ApiError(`Health check failed: HTTP ${res.status}`);
  }
  return res.json();
}

// Streams chat events one at a time via onEvent(event). Resolves when the
// stream ends normally; rejects on a network-level failure. Malformed
// individual lines are reported as synthetic "error" events rather than
// aborting the whole stream, since one bad line shouldn't hide the rest.
async function streamChat(baseUrl, message, conversationId, onEvent) {
  //   console.log("SENDING CHAT:", {
  //   message,
  //   conversationId,
  // });
  let res;
  try {
    res = await fetch(`${baseUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId || undefined,
      }),
    });
  } catch (err) {
    throw new ApiError(`Can't reach the NOVA API at ${baseUrl}: ${err.message}`);
  }

  if (!res.ok || !res.body) {
    throw new ApiError(`NOVA API returned HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop(); // last element may be a partial line -- keep it

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      emitLine(trimmed, onEvent);
    }
  }

  const trailing = buffer.trim();
  if (trailing) {
    emitLine(trailing, onEvent);
  }
}

async function respondToPermission(baseUrl, conversationId, approved) {
  let res;

  try {
    res = await fetch(`${baseUrl}/permission`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        approved,
      }),
    });
  } catch (err) {
    throw new ApiError(
      `Can't reach the NOVA API at ${baseUrl}: ${err.message}`
    );
  }

  if (!res.ok) {
    throw new ApiError(
      `NOVA API returned HTTP ${res.status}`
    );
  }

  return res.json();
}

function emitLine(line, onEvent) {
  try {
    const event = JSON.parse(line);
    onEvent(event);
  } catch (err) {
    onEvent({ type: "error", message: `Malformed event from API: ${line.slice(0, 200)}` });
  }
}

module.exports = {
  checkHealth,
  streamChat,
  respondToPermission,
  ApiError,
};
