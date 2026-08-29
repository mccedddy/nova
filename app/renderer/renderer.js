(() => {
  const form = document.getElementById("prompt-form");
  const input = document.getElementById("prompt-input");
  const log = document.getElementById("log");
  const logContent = document.getElementById("log-content");
  const emptyState = document.getElementById("empty-state");
  const newConvoBtn = document.getElementById("new-convo");
  const connDot = document.getElementById("conn-dot");
  const statusHint = document.getElementById("status-hint");

  // Sidebar / tabs
  const chatButton = document.getElementById("chat-button");
  const terminal1Button = document.getElementById("terminal-1-button");
  const terminal2Button = document.getElementById("terminal-2-button");
  const settingsButton = document.getElementById("settings-button");

  const chatView = document.getElementById("chat-view");
  const terminal1View = document.getElementById("terminal-1-view");
  const terminal2View = document.getElementById("terminal-2-view");
  const settingsView = document.getElementById("settings-view");

  const terminal1Container =
  document.getElementById("terminal-1-container");

  const terminal2Container =
  document.getElementById("terminal-2-container");

  let requestCounter = 0;
  let activeRequestId = null;

  // tool name -> the .tool-line element currently "running" for it, so a
  // matching tool_finished can flip the same line rather than adding a new one.
  const runningTools = new Map();

  // ---------------------------------------------------------------------------
  // TAB SWITCHING
  // ---------------------------------------------------------------------------

  const views = {
    chat: chatView,
    terminal1: terminal1View,
    terminal2: terminal2View,
    settings: settingsView,
  };

  const buttons = {
    chat: chatButton,
    terminal1: terminal1Button,
    terminal2: terminal2Button,
    settings: settingsButton,
  };

  function switchView(viewName) {
    Object.entries(views).forEach(([name, view]) => {
      if (!view) return;
      view.hidden = name !== viewName;
    });

    Object.entries(buttons).forEach(([name, button]) => {
      if (!button) return;
      button.classList.toggle("active", name === viewName);
    });

    if (viewName === "chat" && input && !input.disabled) {
      input.focus();
    }

    if (viewName === "terminal1") {
      focusTerminal("1");
    }

    if (viewName === "terminal2") {
      focusTerminal("2");
    }
  }

  chatButton?.addEventListener("click", () => {
    switchView("chat");
  });

  terminal1Button?.addEventListener("click", () => {
    switchView("terminal1");
  });

  terminal2Button?.addEventListener("click", () => {
    switchView("terminal2");
  });

  settingsButton?.addEventListener("click", () => {
    switchView("settings");
  });

  // Start on Chat.
  switchView("chat");

  // ---------------------------------------------------------------------------
  // CHAT
  // ---------------------------------------------------------------------------

  function scrollToBottom() {
    log.scrollTop = log.scrollHeight;
  }

  function resizeInput() {
    input.style.height = "auto";
    const maxHeight = 160;
    input.style.height = `${Math.min(input.scrollHeight, maxHeight)}px`;
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

    if (tier) {
      el.dataset.tier = tier;
    }

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

      if (tier) {
        existing.dataset.tier = tier;
      }

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

      if (tier) {
        el.dataset.tier = tier;
      }

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

      case "error": {
        // Fallback to converting the entire object to text if message is missing
        const errorText =
          evt.message || evt.text || JSON.stringify(evt);

        addErrorLine(errorText);
        break;
      }

      default:
        // Unknown/future event types are shown generically rather than silently
        // dropped.
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

      resizeInput();
    }
  });

  window.nova.onFocusInput(() => {
    switchView("chat");

    input.focus();
    input.select();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const text = input.value.trim();

    if (!text || activeRequestId !== null) return;

    addUserBubble(text);

    input.value = "";
    resizeInput();

    input.disabled = true;

    requestCounter += 1;
    activeRequestId = String(requestCounter);

    window.nova.send(text, activeRequestId);
  });

  input.addEventListener("input", resizeInput);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // ---------------------------------------------------------------------------
  // GLOBAL KEYBOARD
  // ---------------------------------------------------------------------------

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      window.nova.hide();
    }
  });

  // ---------------------------------------------------------------------------
  // NEW CONVERSATION
  // ---------------------------------------------------------------------------

  newConvoBtn.addEventListener("click", () => {
    window.nova.newConversation();

    // Always return to chat when starting a new conversation.
    switchView("chat");

    logContent.innerHTML = "";

    const el = document.createElement("div");
    el.className = "empty-state";
    el.id = "empty-state";

    el.innerHTML =
      "<p>New conversation.</p>" +
      '<p class="empty-sub">Ask NOVA anything about this system.</p>';

    logContent.appendChild(el);
  });

  // ---------------------------------------------------------------------------
  // TERMINALS
  // ---------------------------------------------------------------------------

  const terminals = new Map();

  function createTerminal(id, container) {
    if (!container) {
      console.error(`Terminal ${id}: container not found.`);
      return;
    }

    if (typeof window.Terminal !== "function") {
      console.error("xterm.js is not available:", window.Terminal);
      container.textContent = "xterm.js failed to load.";
      return;
    }

    const terminal = new window.Terminal({
      cursorBlink: true,
      cursorStyle: "block",
      fontFamily: "Consolas, 'Courier New', monospace",
      fontSize: 13,
      convertEol: true,
      scrollback: 5000,
      theme: {
        background: "#0b0d10",
        foreground: "#d7dbe0",
        cursor: "#ffffff",
      },
    });

    terminal.open(container);

    terminal.write("Starting NOVA terminal...\r\n");

    terminal.onData((data) => {
      window.nova.terminalInput(id, data);
    });

    terminals.set(id, {
      terminal,
      container,
    });

    window.nova
      .terminalStart(id)
      .then((result) => {
        if (!result?.ok) {
          terminal.write(
            `\r\nFailed to start terminal: ${result?.error || "Unknown error"}\r\n`
          );
        }
      })
      .catch((err) => {
        terminal.write(
          `\r\nFailed to start terminal: ${err}\r\n`
        );
      });
  }

  function focusTerminal(id) {
    const entry = terminals.get(id);

    if (!entry) return;

    entry.terminal.focus();
  }

  window.nova.onTerminalData(({ id, data }) => {
    const entry = terminals.get(String(id));

    if (!entry) return;

    entry.terminal.write(data);
  });

  window.nova.onTerminalExit(({ id, exitCode }) => {
    const entry = terminals.get(String(id));

    if (!entry) return;

    entry.terminal.write(
      `\r\n\r\n[Process exited with code ${exitCode}]\r\n`
    );
  });

  createTerminal("1", terminal1Container);
  createTerminal("2", terminal2Container);

  // ---------------------------------------------------------------------------
  // API HEALTH
  // ---------------------------------------------------------------------------

  async function pollHealth() {
    try {
      const result = await window.nova.health();

      connDot.classList.remove("ok", "warning", "down");

      if (!result || result.ok === false) {
        connDot.classList.add("down");

        connDot.title =
          "NOVA API unreachable. Is the NOVA server running?\n" +
          "Start it with 'python -m api.server'";

        statusHint.textContent =
          "API unreachable · is the NOVA server running?";

        return;
      }

      if (result.ollama_reachable === false) {
        connDot.classList.add("warning");

        connDot.title =
          "NOVA API connected.\n\n" +
          "Ollama is unreachable. Is the Ollama server running?\n" +
          "Start it with 'ollama serve'";

        statusHint.textContent =
          "Ollama unreachable · is the Ollama server running?";

        return;
      }

      connDot.classList.add("ok");

      connDot.title =
        "NOVA API and Ollama connected";

      statusHint.textContent =
        "Alt+Space to summon · Esc to dismiss";

    } catch {
      connDot.classList.remove("ok", "warning");
      connDot.classList.add("down");

      connDot.title =
        "NOVA API unreachable. Is the NOVA server running?\n" +
        "Start it with 'python -m api.server'";

      statusHint.textContent =
        "API unreachable · is the NOVA server running?";
    }
  }

  // ---------------------------------------------------------------------------
  // INIT
  // ---------------------------------------------------------------------------

  pollHealth();
  setInterval(pollHealth, 15000);

  resizeInput();
  input.focus();
})();