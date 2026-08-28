(() => {
  const form = document.getElementById("prompt-form");
  const input = document.getElementById("prompt-input");
  const log = document.getElementById("log");
  const logContent = document.getElementById("log-content");
  const emptyState = document.getElementById("empty-state");
  const newConvoBtn = document.getElementById("new-convo");
  const connDot = document.getElementById("conn-dot");
  const statusHint = document.getElementById("status-hint");

  let requestCounter = 0;
  let activeRequestId = null;
  // tool name -> the .tool-line element currently "running" for it, so a
  // matching tool_finished can flip the same line rather than adding a new one.
  const runningTools = new Map();

  function scrollToBottom() {
    log.scrollTop = log.scrollHeight;
  }

  function clearEmptyState() {
    if (emptyState.parentElement) emptyState.remove();
  }

  function addUserBubble(text) {
    clearEmptyState();
    const row = document.createElement("div");
    row.className = "row user";
    const bubble = document.createElement("div");
    bubble.className = "bubble user";
    bubble.textContent = text;
    row.appendChild(bubble);
    logContent.appendChild(row);
    scrollToBottom();
  }

  function addAnswerBubble(text) {
    clearEmptyState();
    const row = document.createElement("div");
    row.className = "row";
    const bubble = document.createElement("div");
    bubble.className = "bubble answer";
    bubble.textContent = text;
    row.appendChild(bubble);
    logContent.appendChild(row);
    scrollToBottom();
  }

  function addErrorLine(message) {
    clearEmptyState();
    const el = document.createElement("div");
    el.className = "error-line";
    el.textContent = message;
    logContent.appendChild(el);
    scrollToBottom();
  }

  function addToolStarted(name, args, tier, display) {
    clearEmptyState();
    const el = document.createElement("div");
    el.className = "tool-line running";
    if (tier) el.dataset.tier = tier;

    const dot = document.createElement("span");
    dot.className = "status";

    const label = document.createElement("span");
    const nameEl = document.createElement("span");
    nameEl.className = "tool-name";
    nameEl.textContent = display || name;
    label.appendChild(nameEl);
    const details = display || name;

    el.appendChild(dot);
    el.appendChild(label);
    el.dataset.display = details;
    logContent.appendChild(el);
    runningTools.set(name, el);
    scrollToBottom();
  }

  function addToolFinished(name, result, tier) {
    clearEmptyState();
    const existing = runningTools.get(name);

    if (existing) {
      existing.className = "tool-line done";
      if (tier) existing.dataset.tier = tier;
      existing.innerHTML = "";
      const dot = document.createElement("span");
      dot.className = "status";
      const label = document.createElement("span");
      label.textContent = `${existing.dataset.display || name} (done)`;
      existing.appendChild(dot);
      existing.appendChild(label);
      runningTools.delete(name);
    } else {
      const el = document.createElement("div");
      el.className = "tool-line done";
      if (tier) el.dataset.tier = tier;
      const dot = document.createElement("span");
      dot.className = "status";
      const label = document.createElement("span");
      const nameEl = document.createElement("span");
      nameEl.className = "tool-name";
      nameEl.textContent = name;
      label.appendChild(nameEl);
      label.appendChild(document.createTextNode(" (done)"));
      el.appendChild(dot);
      el.appendChild(label);
      logContent.appendChild(el);
    }
    scrollToBottom();
  }

  function evtDisplayForTool(name, args) {
    return args && args.display ? args.display : "";
  }

  function handleEvent(evt) {
    if (evt.requestId !== activeRequestId) return;

    switch (evt.type) {
      case "tool_started":
        addToolStarted(evt.name, evt.args, evt.tier, evt.display);
        break;
      case "tool_finished":
        addToolFinished(evt.name, evt.result, evt.tier);
        break;
      case "answer":
        addAnswerBubble(evt.text || "");
        break;
      case "error":
        addErrorLine(evt.message || "Something went wrong.");
        break;
      default:
        // Unknown/future event types (e.g. a Phase 8 confirmation prompt)
        // are shown generically rather than silently dropped.
        if (evt.message || evt.text) {
          addErrorLine(evt.message || evt.text);
        }
    }
  }

  window.nova.onEvent(handleEvent);

  window.nova.onStreamEnd((payload) => {
    if (payload.requestId === activeRequestId) {
      runningTools.clear();
      activeRequestId = null;
      input.disabled = false;
      input.focus();
    }
  });

  window.nova.onFocusInput(() => {
    input.focus();
    input.select();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || activeRequestId !== null) return;

    addUserBubble(text);
    input.value = "";
    input.disabled = true;

    requestCounter += 1;
    activeRequestId = String(requestCounter);
    window.nova.send(text, activeRequestId);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      window.nova.hide();
    }
  });

  newConvoBtn.addEventListener("click", () => {
    window.nova.newConversation();
    logContent.innerHTML = "";
    const el = document.createElement("div");
    el.className = "empty-state";
    el.id = "empty-state";
    el.innerHTML = "<p>New conversation.</p><p class=\"empty-sub\">Ask NOVA anything about this system.</p>";
    logContent.appendChild(el);
  });

  async function pollHealth() {
    try {
      const result = await window.nova.health();
      if (result.ok) {
        connDot.classList.add("ok");
        connDot.classList.remove("down");
        connDot.title = "NOVA API connected";
        statusHint.textContent = "Alt+Space to summon · Esc to dismiss";
      } else {
        connDot.classList.add("down");
        connDot.classList.remove("ok");
        connDot.title = result.error || "NOVA API unreachable";
        statusHint.textContent = "API unreachable -- is the NOVA server running?";
      }
    } catch {
      connDot.classList.add("down");
      connDot.classList.remove("ok");
    }
  }

  pollHealth();
  setInterval(pollHealth, 15000);
  input.focus();
})();
