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
  let conversationId = null;
  let permissionPending = false;

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
    loadSettingsView();
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
    bubble.innerHTML = marked.parse(text);

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
  
  function addPermissionRequest(evt) {
    permissionPending = true;
    clearEmptyState();

    const row = document.createElement("div");
    row.className = "row";

    const bubble = document.createElement("div");
    bubble.className = "bubble answer";

    const details = document.createElement("ul");
    details.className = "permission-details";

    evt.details.split("\n").forEach((line) => {
      const item = document.createElement("li");
      item.innerHTML = marked.parse(line);
      details.appendChild(item);
    });

    const actions = document.createElement("div");
    actions.className = "permission-actions";

    const yesButton = document.createElement("button");
    yesButton.type = "button";
    yesButton.textContent = "✓ Approve";

    const noButton = document.createElement("button");
    noButton.type = "button";
    noButton.textContent = "✕ Decline";

    actions.appendChild(yesButton);
    actions.appendChild(noButton);

    bubble.appendChild(details);
    bubble.appendChild(actions);

    row.appendChild(bubble);
    logContent.appendChild(row);

    scrollToBottom();

    function finish(approved) {
      yesButton.disabled = true;
      noButton.disabled = true;
      permissionPending = false;

      if (approved) {
        yesButton.textContent = "✓ Approved";
        yesButton.classList.add("selected");
        yesButton.style.setProperty("--permission-color", "#4aa8d8");

        noButton.remove();
      } else {
        noButton.textContent = "✕ Declined";
        noButton.classList.add("selected");
        noButton.style.setProperty("--permission-color", "#d95353");

        yesButton.remove();
      }

      window.nova.respondToPermission(
        conversationId,
        approved
      ).catch((err) => {
        addErrorLine(String(err));
      });
    }

    yesButton.addEventListener("click", () => {
      finish(true);
    });

    noButton.addEventListener("click", () => {
      finish(false);
    });
  }

  function evtDisplayForTool(name, args) {
    return args && args.display ? args.display : "";
  }

  function handleEvent(evt) {
    if (
      evt.type !== "conversation_id" &&
      evt.requestId !== activeRequestId
    ) {
      return;
    }

    switch (evt.type) {
      case "conversation_id":
        conversationId = evt.id;
        break;

      case "tool_started":
        addToolStarted(evt.name, evt.args, evt.tier, evt.display);
        break;

      case "tool_finished":
        addToolFinished(evt.name, evt.result, evt.tier);
        break;

      case "answer":
        addAnswerBubble(evt.text || "");
        break;

      case "permission_requested":
        addPermissionRequest(evt);
        break;

      case "error": {
        const errorText =
          evt.message || evt.text || JSON.stringify(evt);

        addErrorLine(errorText);
        break;
      }

      default:
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

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const text = input.value.trim();

    if (!text) return;

    // ---------------------------------------------------------
    // Permission response
    // ---------------------------------------------------------

    if (permissionPending) {
      const answer = text.toLowerCase();

      if (answer !== "y" && answer !== "n") {
        addErrorLine("Please answer Y or N.");
        return;
      }

      input.value = "";
      resizeInput();

      permissionPending = false;

      await window.nova.respondToPermission(
        conversationId,
        answer === "y"
      );

      return;
    }

    // ---------------------------------------------------------
    // Normal chat
    // ---------------------------------------------------------

    if (activeRequestId !== null) return;

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
// Settings view
// ---------------------------------------------------------------------------

const APP_SETTINGS_FIELDS = [
  { key: "apiBaseUrl", label: "API base URL", type: "text" },
  { key: "globalShortcut", label: "Global shortcut", type: "text" },
  { key: "launchAtLogin", label: "Launch at login", type: "checkbox" },
  { key: "reduceMotion", label: "Reduce motion", type: "checkbox" },
];

let settingsLoaded = false;
let lastAgentRanges = {};

function buildFieldRow(key, label, inputEl) {
  const row = document.createElement("div");
  row.className = "settings-field-row";

  const labelEl = document.createElement("label");
  labelEl.textContent = label;
  labelEl.setAttribute("for", `field-${key}`);

  inputEl.id = `field-${key}`;
  inputEl.dataset.key = key;

  row.appendChild(labelEl);
  row.appendChild(inputEl);
  return row;
}

function renderAppSettingsForm(values) {
  const container = document.getElementById("app-settings-fields");
  container.innerHTML = "";

  for (const field of APP_SETTINGS_FIELDS) {
    const input = document.createElement("input");
    if (field.type === "checkbox") {
      input.type = "checkbox";
      input.checked = Boolean(values[field.key]);
    } else {
      input.type = "text";
      input.value = values[field.key] ?? "";
    }
    container.appendChild(buildFieldRow(field.key, field.label, input));
  }
}

function renderAgentSettingsForm(payload) {
  const { values, ranges } = payload;
  const container = document.getElementById("agent-settings-fields");
  container.innerHTML = "";

  for (const key of Object.keys(values)) {
    const isNumeric = Object.prototype.hasOwnProperty.call(ranges, key);
    const input = document.createElement("input");

    if (isNumeric) {
      input.type = "number";
      const [min, max] = ranges[key];
      input.min = min;
      input.max = max;
      input.value = values[key];
    } else {
      input.type = "text";
      input.value = values[key];
    }

    container.appendChild(buildFieldRow(key, key.replace(/_/g, " "), input));
  }
}

function collectAppSettingsValues() {
  const out = {};
  for (const field of APP_SETTINGS_FIELDS) {
    const input = document.getElementById(`field-${field.key}`);
    if (!input) continue;
    out[field.key] = field.type === "checkbox" ? input.checked : input.value;
  }
  return out;
}

function collectAgentSettingsValues(ranges) {
  const out = {};
  const container = document.getElementById("agent-settings-fields");
  container.querySelectorAll("input[data-key]").forEach((input) => {
    const key = input.dataset.key;
    if (Object.prototype.hasOwnProperty.call(ranges, key)) {
      const num = parseInt(input.value, 10);
      if (!Number.isNaN(num)) out[key] = num;
    } else {
      out[key] = input.value;
    }
  });
  return out;
}

function setSettingsStatus(elId, text, isError) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.textContent = text;
  el.classList.toggle("settings-status-error", Boolean(isError));
}

async function loadSettingsView() {
  if (settingsLoaded) return;
  settingsLoaded = true;

  try {
    const appSettings = await window.nova.getSettings();
    renderAppSettingsForm(appSettings);
  } catch (err) {
    document.getElementById("app-settings-fields").innerHTML =
      `<p class="settings-error">Couldn't load app settings: ${err.message}</p>`;
  }

  try {
    const res = await window.nova.getAgentSettings();
    if (!res.ok) throw new Error(res.error || "unknown error");
    lastAgentRanges = res.result.ranges || {};
    renderAgentSettingsForm(res.result);
  } catch (err) {
    document.getElementById("agent-settings-fields").innerHTML =
      `<p class="settings-error">Couldn't reach NOVA's API to load agent settings: ${err.message}</p>`;
  }
}

document.getElementById("app-settings-save")?.addEventListener("click", async () => {
  const values = collectAppSettingsValues();
  setSettingsStatus("app-settings-status", "Saving…", false);
  try {
    await window.nova.saveSettings(values);
    setSettingsStatus("app-settings-status", "Saved", false);
  } catch (err) {
    setSettingsStatus("app-settings-status", `Failed: ${err.message}`, true);
  }
});

document.getElementById("agent-settings-save")?.addEventListener("click", async () => {
  const values = collectAgentSettingsValues(lastAgentRanges);
  setSettingsStatus("agent-settings-status", "Saving…", false);
  try {
    const res = await window.nova.saveAgentSettings(values);
    if (!res.ok) throw new Error(res.error || "unknown error");
    if (res.result.rejected?.length) {
      setSettingsStatus(
        "agent-settings-status",
        `Saved, but rejected: ${res.result.rejected.join(", ")}`,
        true
      );
    } else {
      setSettingsStatus(
        "agent-settings-status",
        "Saved -- restart the API server for changes to take effect.",
        false
      );
    }
  } catch (err) {
    setSettingsStatus("agent-settings-status", `Failed: ${err.message}`, true);
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
    conversationId = null;

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

    const fitAddon = new window.FitAddon.FitAddon();

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

    terminal.loadAddon(fitAddon);

    terminal.open(container);

    // Initial sizing
    fitAddon.fit();

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });

    resizeObserver.observe(container);


    terminal.write("Starting NOVA terminal...\r\n");

    terminal.onData((data) => {
      window.nova.terminalInput(id, data);
    });

    terminals.set(id, {
      terminal,
      container,
      fitAddon,
      resizeObserver,
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
          "API unreachable · Start it with 'python -m api.server'";

        return;
      }

      if (result.ollama_reachable === false) {
        connDot.classList.add("warning");

        connDot.title =
          "NOVA API connected.\n\n" +
          "Ollama is unreachable. Is the Ollama server running?\n" +
          "Start it with 'ollama serve'";

        statusHint.textContent =
          "Ollama unreachable · Start it with 'ollama serve'";

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
        "API unreachable · Start it with 'python -m api.server'";
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