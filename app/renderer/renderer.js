(() => {
  // DOM elements
  const form = document.getElementById("prompt-form");
  const input = document.getElementById("prompt-input");
  const log = document.getElementById("log");
  const logContent = document.getElementById("log-content");
  const emptyState = document.getElementById("empty-state");
  const newConvoBtn = document.getElementById("new-convo");
  const connDot = document.getElementById("conn-dot");
  const statusHint = document.getElementById("status-hint");

  // Sidebar buttons and views
  const chatButton = document.getElementById("chat-button");
  const terminal1Button = document.getElementById("terminal-1-button");
  const terminal2Button = document.getElementById("terminal-2-button");
  const settingsButton = document.getElementById("settings-button");
  const memoryButton = document.getElementById("memory-button");
  const incognitoButton = document.getElementById("incognito-button");
  const memoryList = document.getElementById("memory-list");
  const chatView = document.getElementById("chat-view");
  const terminal1View = document.getElementById("terminal-1-view");
  const terminal2View = document.getElementById("terminal-2-view");
  const settingsView = document.getElementById("settings-view");
  const memoryView = document.getElementById("memory-view");
  const terminal1Container = document.getElementById("terminal-1-container");
  const terminal2Container = document.getElementById("terminal-2-container");

  // Theme
  document.documentElement.dataset.theme = "";

  // Manages conversation state and permissions
  class ConversationState {
    constructor() {
      this.id = null;
      this.requestId = null;
      this.activeTools = new Map();
      this.permissionPending = false;
      this.requestCounter = 0;
    }

    newRequest(text) {
      this.requestId = String(++this.requestCounter);
      return this.requestId;
    }

    endRequest() {
      this.requestId = null;
      this.activeTools.clear();
    }

    addToolStart(name, element) {
      this.activeTools.set(name, element);
    }

    getToolElement(name) {
      return this.activeTools.get(name);
    }

    deleteToolStart(name) {
      this.activeTools.delete(name);
    }

    startPermissionPrompt() {
      this.permissionPending = true;
    }

    endPermissionPrompt() {
      this.permissionPending = false;
    }
  }

  const state = new ConversationState();

  // Incognito is a client preference; the API treats it as authoritative per request.
  let incognito = false;

  // View switching
  const views = {
    chat: chatView,
    terminal1: terminal1View,
    terminal2: terminal2View,
    settings: settingsView,
    memory: memoryView,
  };

  const buttons = {
    chat: chatButton,
    terminal1: terminal1Button,
    terminal2: terminal2Button,
    settings: settingsButton,
    memory: memoryButton,
  };

  // Switch active view and focus appropriate element
  function switchView(viewName) {
    Object.entries(views).forEach(([name, view]) => {
      if (view) view.hidden = name !== viewName;
    });

    Object.entries(buttons).forEach(([name, button]) => {
      if (button) button.classList.toggle("active", name === viewName);
    });

    if (viewName === "chat" && input && !input.disabled) {
      input.focus();
    }
    if (viewName === "terminal1") focusTerminal("1");
    if (viewName === "terminal2") focusTerminal("2");
  }

  chatButton?.addEventListener("click", () => switchView("chat"));
  terminal1Button?.addEventListener("click", () => switchView("terminal1"));
  terminal2Button?.addEventListener("click", () => switchView("terminal2"));
  settingsButton?.addEventListener("click", () => {
    switchView("settings");
    loadSettingsView();
  });
  memoryButton?.addEventListener("click", () => {
    switchView("memory");
    loadMemoryView();
  });

  switchView("chat");

  // Scroll log to bottom
  function scrollToBottom() {
    log.scrollTop = log.scrollHeight;
  }

  // Auto-expand textarea height
  function resizeInput() {
    input.style.height = "auto";
    const maxHeight = 160;
    input.style.height = `${Math.min(input.scrollHeight, maxHeight)}px`;
  }

  // Remove empty state placeholder
  function clearEmptyState() {
    if (emptyState.parentElement) emptyState.remove();
  }

  // Add user message to chat
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

  // Add AI response to chat
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

  // Add error message to chat
  function addErrorLine(message) {
    clearEmptyState();
    const el = document.createElement("div");
    el.className = "error-line";
    el.textContent = message;
    logContent.appendChild(el);
    scrollToBottom();
  }

  // Add tool execution start indicator
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

    el.appendChild(dot);
    el.appendChild(label);
    el.dataset.display = display || name;

    logContent.appendChild(el);
    state.addToolStart(name, el);
    scrollToBottom();
  }

  // Mark tool as completed
  function addToolFinished(name, result, tier) {
    clearEmptyState();
    const existing = state.getToolElement(name);

    if (existing) {
      // Update running tool to finished state
      existing.className = "tool-line done";
      if (tier) existing.dataset.tier = tier;
      existing.innerHTML = "";

      const dot = document.createElement("span");
      dot.className = "status";
      const label = document.createElement("span");
      label.textContent = `${existing.dataset.display || name} (done)`;

      existing.appendChild(dot);
      existing.appendChild(label);
      state.deleteToolStart(name);
    } else {
      // Tool finished but wasn't tracked as running - add entry
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

  // Show permission request UI with approve/decline buttons
  function addPermissionRequest(evt) {
    state.startPermissionPrompt();
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

    // Handle approval/decline decision
    function finish(approved) {
      yesButton.disabled = true;
      noButton.disabled = true;

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

      window.nova.respondToPermission(state.id, approved).catch((err) => {
        addErrorLine(String(err));
      });

      state.endPermissionPrompt();
    }

    yesButton.addEventListener("click", () => finish(true));
    noButton.addEventListener("click", () => finish(false));
  }

  // Handle API events based on type
  function handleEvent(evt) {
    // Skip events from old requests or unrelated conversations
    if (evt.type !== "conversation_id" && evt.requestId !== state.requestId) {
      return;
    }

    switch (evt.type) {
      case "conversation_id":
        state.id = evt.id;
        break;
      case "session_mode":
        // The API is authoritative -- it rebuilds the conversation on a mode change.
        setIncognito(Boolean(evt.incognito), { persist: false });
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
      case "error":
        const errorText = evt.message || evt.text || JSON.stringify(evt);
        addErrorLine(errorText);
        break;
      default:
        if (evt.message || evt.text) {
          addErrorLine(evt.message || evt.text);
        }
    }
  }

  window.nova.onEvent(handleEvent);

  // Clean up after stream ends
  window.nova.onStreamEnd((payload) => {
    if (payload.requestId === state.requestId) {
      state.endRequest();
      input.disabled = false;
      input.focus();
      resizeInput();
    }
  });

  // Focus input on hotkey
  window.nova.onFocusInput(() => {
    switchView("chat");
    input.focus();
    input.select();
  });

  // Handle form submission
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    // Handle permission response Y/N
    if (state.permissionPending) {
      const answer = text.toLowerCase();
      if (answer !== "y" && answer !== "n") {
        addErrorLine("Please answer Y or N.");
        return;
      }
      input.value = "";
      resizeInput();
      await window.nova.respondToPermission(state.id, answer === "y");
      state.endPermissionPrompt();
      return;
    }

    // Send normal chat message
    if (state.requestId !== null) return;

    addUserBubble(text);
    input.value = "";
    resizeInput();
    input.disabled = true;

    const requestId = state.newRequest(text);
    window.nova.send(text, requestId, incognito);
  });

  input.addEventListener("input", resizeInput);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  // Settings management
  let settingsLoaded = false;
  let lastAgentRanges = {};
  let lastAgentBools = [];
  let lastAgentChoices = {};

  // Build dynamic agent settings field
  function buildAgentSettingRow(key, label, input) {
    const row = document.createElement("div");
    row.className = "settings-field-row";
    const labelEl = document.createElement("label");
    labelEl.textContent = label;
    labelEl.setAttribute("for", `field-agent-${key}`);
    input.id = `field-agent-${key}`;
    input.dataset.key = key;
    row.appendChild(labelEl);
    row.appendChild(input);
    return row;
  }

  // Populate agent settings form from API response
  function renderAgentSettingsForm(payload) {
    const { values, ranges, bools, choices } = payload;
    const container = document.getElementById("agent-settings-fields");
    container.innerHTML = "";
    const boolKeys = new Set(bools || []);

    for (const key of Object.keys(values)) {
      const isNumeric = Object.prototype.hasOwnProperty.call(ranges, key);
      const isBool = boolKeys.has(key);
      const options = choices ? choices[key] : null;
      let input;

      if (options && options.length) {
        // Enumerated string: a dropdown keeps the user from typing a value
        // the API will reject.
        input = document.createElement("select");
        for (const option of options) {
          const opt = document.createElement("option");
          opt.value = option;
          opt.textContent = option;
          input.appendChild(opt);
        }
        input.value = values[key];
      } else {
        input = document.createElement("input");
        if (isBool) {
          // Bools must render as checkboxes -- a text box would let the API
          // reject the value on save.
          input.type = "checkbox";
          input.checked = Boolean(values[key]);
        } else if (isNumeric) {
          input.type = "number";
          const [min, max] = ranges[key];
          input.min = min;
          input.max = max;
          input.value = values[key];
        } else {
          input.type = "text";
          input.value = values[key];
        }
      }

      container.appendChild(buildAgentSettingRow(key, key.replace(/_/g, " "), input));
    }
  }

  // Collect app settings from hardcoded form
  function collectAppSettings() {
    const out = {};
    document.querySelectorAll("#app-settings-section input[data-key]").forEach((input) => {
      const key = input.dataset.key;
      out[key] = input.type === "checkbox" ? input.checked : input.value;
    });
    return out;
  }

  // Collect agent settings from dynamic form
  function collectAgentSettings(ranges, bools) {
    const out = {};
    const boolKeys = new Set(bools || []);
    document.querySelectorAll("#agent-settings-section [data-key]").forEach((input) => {
      const key = input.dataset.key;
      if (boolKeys.has(key)) {
        out[key] = input.checked;
      } else if (input.tagName === "SELECT") {
        out[key] = input.value;
      } else if (Object.prototype.hasOwnProperty.call(ranges, key)) {
        const num = parseInt(input.value, 10);
        if (!Number.isNaN(num)) out[key] = num;
      } else {
        out[key] = input.value;
      }
    });
    return out;
  }

  // Set status message
  function setSettingsStatus(elId, text, isError) {
    const el = document.getElementById(elId);
    if (el) {
      el.textContent = text;
      el.classList.toggle("settings-status-error", Boolean(isError));
    }
  }

  // Load app and agent settings
  async function loadSettingsView() {
    if (settingsLoaded) return;
    settingsLoaded = true;

    // Load app settings into hardcoded inputs
    try {
      const appSettings = await window.nova.getSettings();
      Object.entries(appSettings).forEach(([key, value]) => {
        const input = document.getElementById(`field-${key}`);
        if (input) {
          input[input.type === "checkbox" ? "checked" : "value"] = value;
        }
      });
    } catch (err) {
      document.getElementById("app-settings-fields").innerHTML =
        `<p class="settings-error">Couldn't load app settings: ${err.message}</p>`;
    }

    // Load agent settings from API
    try {
      const res = await window.nova.getAgentSettings();
      if (!res.ok) throw new Error(res.error || "unknown error");
      lastAgentRanges = res.result.ranges || {};
      lastAgentBools = res.result.bools || [];
      lastAgentChoices = res.result.choices || {};
      renderAgentSettingsForm(res.result);
    } catch (err) {
      document.getElementById("agent-settings-fields").innerHTML =
        `<p class="settings-error">Couldn't reach NOVA's API: ${err.message}</p>`;
    }
  }

  // Save app settings
  document.getElementById("app-settings-save")?.addEventListener("click", async () => {
    const values = collectAppSettings();
    setSettingsStatus("app-settings-status", "Saving…", false);
    try {
      await window.nova.saveSettings(values);
      setSettingsStatus("app-settings-status", "Saved", false);
    } catch (err) {
      setSettingsStatus("app-settings-status", `Failed: ${err.message}`, true);
    }
  });

  // Save agent settings
  document.getElementById("agent-settings-save")?.addEventListener("click", async () => {
    const values = collectAgentSettings(lastAgentRanges, lastAgentBools);
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

  // Close on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      window.nova.hide();
    }
  });

  // ---- Incognito mode ------------------------------------------------------

  // Reflect incognito state in the sidebar button. Uses its own `on` class
  // rather than `active`, which switchView() owns for view buttons.
  function setIncognito(next, { persist = true } = {}) {
    incognito = Boolean(next);
    if (incognitoButton) {
      incognitoButton.classList.toggle("on", incognito);
      incognitoButton.setAttribute("aria-pressed", String(incognito));
      incognitoButton.title = incognito
        ? "Incognito mode is on -- nothing is being remembered"
        : "Incognito mode -- nothing is remembered";
    }
    if (persist) {
      // Persist so the mode survives a restart.
      window.nova.saveSettings({ incognito }).catch(() => {});
    }
  }

  incognitoButton?.addEventListener("click", () => {
    setIncognito(!incognito);
  });

  // Seed from saved client settings.
  window.nova.getSettings()
    .then((saved) => {
      if (saved && typeof saved.incognito === "boolean") {
        setIncognito(saved.incognito, { persist: false });
      }
    })
    .catch(() => {});

  // ---- Memory view ---------------------------------------------------------

  function renderMemoryList(entries) {
    if (!memoryList) return;
    memoryList.innerHTML = "";

    if (!entries.length) {
      const empty = document.createElement("p");
      empty.className = "settings-loading";
      empty.textContent = "NOVA is not remembering anything yet.";
      memoryList.appendChild(empty);
      return;
    }

    entries.forEach((entry) => {
      const row = document.createElement("div");
      row.className = "memory-item";

      const text = document.createElement("div");
      text.className = "memory-text";

      const key = document.createElement("span");
      key.className = "memory-key";
      key.textContent = entry.key;

      const value = document.createElement("span");
      value.className = "memory-value";
      value.textContent = entry.value;

      const meta = document.createElement("span");
      meta.className = "memory-meta";
      const when = (entry.updated || entry.created || "").replace("T", " ");
      meta.textContent = `${entry.source} · ${when}`;

      text.appendChild(key);
      text.appendChild(value);
      text.appendChild(meta);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "memory-delete";
      remove.textContent = "✕";
      remove.title = `Forget ${entry.key}`;
      remove.addEventListener("click", async () => {
        remove.disabled = true;
        const res = await window.nova.deleteMemory(entry.key);
        if (!res || res.ok === false) {
          remove.disabled = false;
          addErrorLine(
            `Could not forget ${entry.key}: ${(res && res.error) || "unknown error"}`
          );
          return;
        }
        loadMemoryView();
      });

      row.appendChild(text);
      row.appendChild(remove);
      memoryList.appendChild(row);
    });
  }

  // Always refetched on open -- unlike the settings view, memory changes
  // underneath the user as conversations happen.
  async function loadMemoryView() {
    if (!memoryList) return;
    memoryList.innerHTML = '<p class="settings-loading">Loading…</p>';

    const res = await window.nova.getMemory();
    if (!res || res.ok === false) {
      memoryList.innerHTML = "";
      const failed = document.createElement("p");
      failed.className = "settings-error";
      failed.textContent = `Could not load memory: ${(res && res.error) || "unknown error"}`;
      memoryList.appendChild(failed);
      return;
    }
    renderMemoryList((res.result && res.result.entries) || []);
  }

  // Start new conversation
  newConvoBtn.addEventListener("click", () => {
    window.nova.newConversation();
    state.id = null;
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

  // Terminal management
  const terminals = new Map();

  // Initialize xterm.js terminal in container
  function createTerminal(id, container) {
    if (!container) {
      console.error(`Terminal ${id}: container not found.`);
      return;
    }

    if (typeof window.Terminal !== "function") {
      console.error("xterm.js is not available");
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
    fitAddon.fit();

    // Resize terminal on container change
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

    // Start PTY in main process
    window.nova
      .terminalStart(id)
      .then((result) => {
        if (!result?.ok) {
          terminal.write(`\r\nFailed to start terminal: ${result?.error || "Unknown error"}\r\n`);
        }
      })
      .catch((err) => {
        terminal.write(`\r\nFailed to start terminal: ${err}\r\n`);
      });
  }

  // Focus terminal window
  function focusTerminal(id) {
    const entry = terminals.get(id);
    if (entry) entry.terminal.focus();
  }

  // Display terminal output
  window.nova.onTerminalData(({ id, data }) => {
    const entry = terminals.get(String(id));
    if (entry) entry.terminal.write(data);
  });

  // Display terminal exit message
  window.nova.onTerminalExit(({ id, exitCode }) => {
    const entry = terminals.get(String(id));
    if (entry) {
      entry.terminal.write(`\r\n\r\n[Process exited with code ${exitCode}]\r\n`);
    }
  });

  createTerminal("1", terminal1Container);
  createTerminal("2", terminal2Container);

  // Poll API and Ollama health status
  async function pollHealth() {
    try {
      const result = await window.nova.health();

      connDot.classList.remove("ok", "warning", "down");

      if (!result || result.ok === false) {
        connDot.classList.add("down");
        connDot.title = "NOVA API unreachable. Is the NOVA server running?\nStart it with 'python -m api.server'";
        statusHint.textContent = "API unreachable · Start it with 'python -m api.server'";
        return;
      }

      if (result.ollama_reachable === false) {
        connDot.classList.add("warning");
        connDot.title = "NOVA API connected.\n\nOllama is unreachable. Is the Ollama server running?\nStart it with 'ollama serve'";
        statusHint.textContent = "Ollama unreachable · Start it with 'ollama serve'";
        return;
      }

      connDot.classList.add("ok");
      connDot.title = "NOVA API and Ollama connected";
      statusHint.textContent = "Alt+Space to summon · Esc to dismiss";
    } catch {
      connDot.classList.remove("ok", "warning");
      connDot.classList.add("down");
      connDot.title = "NOVA API unreachable. Is the NOVA server running?\nStart it with 'python -m api.server'";
      statusHint.textContent = "API unreachable · Start it with 'python -m api.server'";
    }
  }

  pollHealth();
  setInterval(pollHealth, 15000);

  resizeInput();
  input.focus();
})();
