const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen, nativeImage } = require("electron");
const path = require("path");

const { loadSettings, saveSettings } = require("./settings");
const {
  startTerminal: startPtyTerminal,
  writeTerminal: writePtyTerminal,
  resizeTerminal: resizePtyTerminal,
  killTerminal: killPtyTerminal,
  killAllTerminals: killAllPtyTerminals,
} = require("./terminals");

let mainWindow = null;
let tray = null;
let settings = null;
let currentConversationId = null;

// Ensure single instance
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();
app.on("second-instance", () => showWindow());

class ApiError extends Error {}

// Check API health endpoint
async function checkHealth(baseUrl) {
  const res = await fetch(`${baseUrl}/health`, { method: "GET" });
  if (!res.ok) throw new ApiError(`Health check failed: HTTP ${res.status}`);
  return res.json();
}

// Stream chat events line-by-line from API
async function streamChat(baseUrl, message, conversationId, onEvent) {
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
    throw new ApiError(`Can't reach NOVA API at ${baseUrl}: ${err.message}`);
  }

  if (!res.ok || !res.body) throw new ApiError(`NOVA API returned HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    // Parse and emit each complete JSON line
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event = JSON.parse(trimmed);
        onEvent(event);
      } catch {
        onEvent({ type: "error", message: `Malformed event: ${trimmed.slice(0, 200)}` });
      }
    }
  }

  // Handle any trailing data
  const trailing = buffer.trim();
  if (trailing) {
    try {
      const event = JSON.parse(trailing);
      onEvent(event);
    } catch {
      onEvent({ type: "error", message: `Malformed event: ${trailing.slice(0, 200)}` });
    }
  }
}

// Respond to permission request
async function respondToPermission(baseUrl, conversationId, approved) {
  let res;
  try {
    res = await fetch(`${baseUrl}/permission`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, approved }),
    });
  } catch (err) {
    throw new ApiError(`Can't reach NOVA API at ${baseUrl}: ${err.message}`);
  }

  if (!res.ok) throw new ApiError(`NOVA API returned HTTP ${res.status}`);
  return res.json();
}

// Get agent model and tool settings
async function getAgentSettings(baseUrl) {
  const res = await fetch(`${baseUrl}/settings`);
  if (!res.ok) throw new ApiError(`GET /settings failed: ${res.status}`);
  return res.json();
}

// Save agent settings
async function saveAgentSettings(baseUrl, values) {
  const res = await fetch(`${baseUrl}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ values }),
  });
  if (!res.ok) throw new ApiError(`POST /settings failed: ${res.status}`);
  return res.json();
}

// ---- Window Management -------------------------------------------------------

// Create main Electron window with frameless transparent UI
function createWindow() {
  const display = screen.getPrimaryDisplay();
  const { width: screenWidth } = display.workAreaSize;

  mainWindow = new BrowserWindow({
    width: 640,
    height: 460,
    minWidth: 420,
    minHeight: 320,
    x: Math.round((screenWidth - 640) / 2),
    y: 96,
    frame: false,
    transparent: true,
    resizable: true,
    movable: true,
    show: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    hideOnBlur: true,
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  // Hide on blur for command-palette UX
  mainWindow.on("blur", () => {
    // if (!mainWindow.webContents.isDevToolsOpened()) hideWindow();
  });

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      hideWindow();
    }
  });
}



// Show and focus window
function showWindow() {
  if (!mainWindow) return;
  mainWindow.show();
  mainWindow.webContents.send("nova:focus-input");
}

// Hide window without closing
function hideWindow() {
  if (!mainWindow) return;
  mainWindow.hide();
}

// Toggle visibility
function toggleWindow() {
  if (!mainWindow) return;
  mainWindow.isVisible() ? hideWindow() : showWindow();
}

// Create system tray with menu
function createTray() {
  const iconPath = path.join(__dirname, "assets", "tray-icon.png");
  const icon = nativeImage.createFromPath(iconPath);
  tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon);
  tray.setToolTip("NOVA");

  const menu = Menu.buildFromTemplate([
    { label: "Show NOVA", click: showWindow },
    { label: `Shortcut: ${settings.globalShortcut}`, enabled: false },
    { type: "separator" },
    {
      label: "Quit NOVA",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(menu);
  tray.on("click", toggleWindow);
}

// Register global hotkey for window toggle
function registerShortcut() {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register(settings.globalShortcut, toggleWindow);
  if (!ok) console.error(`Failed to register global shortcut: ${settings.globalShortcut}`);
}

// ---- App Lifecycle ----------------------------------------------------------

app.whenReady().then(() => {
  settings = loadSettings();
  createWindow();
  createTray();
  registerShortcut();
});

// Keep app in tray when window closes
app.on("window-all-closed", (event) => event.preventDefault());

// Clean up on quit
app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  killAllPtyTerminals();
});

// ---- IPC: Chat & Settings ---------------------------------------------------

ipcMain.on("nova:hide", () => hideWindow());

ipcMain.handle("nova:get-settings", () => settings);

ipcMain.handle("nova:save-settings", (_event, partial) => {
  settings = saveSettings({ ...settings, ...partial });
  registerShortcut();
  return settings;
});

ipcMain.handle("nova:health", async () => {
  try {
    const result = await checkHealth(settings.apiBaseUrl);
    return { ok: true, ...result };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("nova:permission", async (_event, { conversationId, approved }) => {
  try {
    return await respondToPermission(settings.apiBaseUrl, conversationId, approved);
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// Stream chat messages and events to renderer
ipcMain.on("nova:send", async (event, { message, requestId }) => {
  const sender = event.sender;
  try {
    await streamChat(settings.apiBaseUrl, message, currentConversationId, (nova_event) => {
      if (nova_event.type === "conversation_id" && nova_event.id) {
        currentConversationId = nova_event.id;
      }
      sender.send("nova:event", { requestId, ...nova_event });
    });
    sender.send("nova:stream-end", { requestId });
  } catch (err) {
    sender.send("nova:event", { requestId, type: "error", message: err.message });
    sender.send("nova:stream-end", { requestId });
  }
});

ipcMain.on("nova:new-conversation", () => {
  currentConversationId = null;
});

ipcMain.handle("nova:get-agent-settings", async () => {
  try {
    const result = await getAgentSettings(settings.apiBaseUrl);
    return { ok: true, result };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

ipcMain.handle("nova:save-agent-settings", async (_event, values) => {
  try {
    const result = await saveAgentSettings(settings.apiBaseUrl, values);
    return { ok: true, result };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// ---- IPC: Terminals ---------------------------------------------------------

ipcMain.handle("nova:terminal-start", (_event, id) => {
  return startPtyTerminal(id, (termId, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("nova:terminal-data", { id: termId, data });
    }
  }, (termId, exitCode) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send("nova:terminal-exit", { id: termId, exitCode });
    }
  });
});

ipcMain.handle("nova:terminal-input", (_event, { id, data }) => {
  return writePtyTerminal(id, data);
});

ipcMain.handle("nova:terminal-resize", (_event, { id, cols, rows }) => {
  resizePtyTerminal(id, cols, rows);
  return { ok: true };
});

ipcMain.handle("nova:terminal-kill", (_event, id) => {
  killPtyTerminal(id);
  return { ok: true };
});
