const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen, nativeImage } = require("electron");
const path = require("path");

const { loadSettings, saveSettings } = require("./settings");
const {
  checkHealth,
  streamChat,
  respondToPermission,
  ApiError,
} = require("./api-client");

const { spawn } = require("node-pty");

// This is Phase 13: a separate client of the Phase 7 API. No agent logic
// lives here -- this file only talks to the API and renders the UI. Do not
// import or re-implement anything from agent/ or tools/ in this process.

let mainWindow = null;
let tray = null;
let settings = null;
let currentConversationId = null;

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

app.on("second-instance", () => {
  showWindow();
});

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const { width: screenWidth } = display.workAreaSize;

  const winWidth = 640;
  const winHeight = 460;

  mainWindow = new BrowserWindow({
    width: winWidth,
    height: winHeight,
    minWidth: 420,
    minHeight: 320,
    x: Math.round((screenWidth - winWidth) / 2),
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
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));

  // Hide (don't destroy) on blur so the summon-and-dismiss flow feels like
  // a command palette rather than a normal app window.
  mainWindow.on("blur", () => {
    if (!mainWindow.webContents.isDevToolsOpened()) {
      hideWindow();
    }
  });

  mainWindow.on("close", (event) => {
    if (!app.isQuitting) {
      event.preventDefault();
      hideWindow();
    }
  });
}

function showWindow() {
  if (!mainWindow) return;
  mainWindow.show();
  mainWindow.webContents.send("nova:focus-input");
}

function hideWindow() {
  if (!mainWindow) return;
  mainWindow.hide();
}

function toggleWindow() {
  if (!mainWindow) return;
  if (mainWindow.isVisible()) {
    hideWindow();
  } else {
    showWindow();
  }
}

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

function registerShortcut() {
  globalShortcut.unregisterAll();
  const ok = globalShortcut.register(settings.globalShortcut, toggleWindow);
  if (!ok) {
    console.error(`Failed to register global shortcut: ${settings.globalShortcut}`);
  }
}

app.whenReady().then(() => {
  settings = loadSettings();
  createWindow();
  createTray();
  registerShortcut();
});

app.on("window-all-closed", (event) => {
  // Tray-resident app: don't quit when the window closes.
  event.preventDefault();
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  killAllTerminals();
});

// -----------------------------------------------------------------------------
// TERMINALS
// -----------------------------------------------------------------------------

const terminals = new Map();

const TERMINAL_CONFIG = {
  1: {
    cwd: "C:\\DEV\\nova",
  },
  2: {
    cwd: "C:\\DEV\\nova",
  },
};

function getVenvPath() {
  // Your Electron app is:
  // C:\DEV\nova\app
  //
  // If your venv is:
  // C:\DEV\nova\venv
  //
  // then ..\venv is correct.
  return path.resolve(__dirname, "..", "venv", "Scripts", "Activate.ps1");
}

function startTerminal(id) {
  const terminalId = String(id);

  // Don't create another PowerShell process if this terminal
  // is already running.
  if (terminals.has(terminalId)) {
    return {
      ok: true,
      alreadyRunning: true,
    };
  }

  // THIS was the missing variable.
  const config = TERMINAL_CONFIG[terminalId];

  if (!config) {
    return {
      ok: false,
      error: `Unknown terminal: ${terminalId}`,
    };
  }

  const venvPath = getVenvPath();

  const command = [
    `Set-Location -LiteralPath '${config.cwd}'`,
    `$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()`,
    `if (Test-Path -LiteralPath '${venvPath}') { . '${venvPath}' }`,
  ].join("; ");

  const ptyProcess = spawn(
    "powershell.exe",
    [
      "-NoLogo",
      "-NoExit",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      command,
    ],
    {
      name: "xterm-256color",
      cols: 100,
      rows: 30,
      cwd: config.cwd,
      env: {
        ...process.env,
        TERM_PROGRAM: "NOVA",
      },
    }
  );

  terminals.set(terminalId, ptyProcess);

  ptyProcess.onData((data) => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    mainWindow.webContents.send("nova:terminal-data", {
      id: terminalId,
      data,
    });
  });

  ptyProcess.onExit(({ exitCode, signal }) => {
    terminals.delete(terminalId);

    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    mainWindow.webContents.send("nova:terminal-exit", {
      id: terminalId,
      exitCode,
      signal,
    });
  });

  return {
    ok: true,
    alreadyRunning: false,
  };
}

function writeTerminal(id, data) {
  const terminalId = String(id);
  const terminal = terminals.get(terminalId);

  if (!terminal) {
    return {
      ok: false,
      error: `Terminal ${terminalId} is not running.`,
    };
  }

  terminal.write(data);

  return {
    ok: true,
  };
}

function resizeTerminal(id, cols, rows) {
  const terminal = terminals.get(String(id));

  if (!terminal) {
    return;
  }

  if (
    Number.isInteger(cols) &&
    Number.isInteger(rows) &&
    cols > 0 &&
    rows > 0
  ) {
    terminal.resize(cols, rows);
  }
}

function killTerminal(id) {
  const terminalId = String(id);
  const terminal = terminals.get(terminalId);

  if (!terminal) {
    return;
  }

  try {
    terminal.kill();
  } catch {
    // Ignore cleanup errors.
  }

  terminals.delete(terminalId);
}

function killAllTerminals() {
  for (const [id, terminal] of terminals) {
    try {
      terminal.kill();
    } catch {
      // Ignore cleanup errors.
    }
  }

  terminals.clear();
}

// ---- IPC: renderer <-> API -------------------------------------------------

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
    return { ok: false, error: err instanceof ApiError ? err.message : String(err) };
  }
});

ipcMain.handle(
  "nova:permission",
  async (_event, { conversationId, approved }) => {
    try {
      return await respondToPermission(
        settings.apiBaseUrl,
        conversationId,
        approved
      );
    } catch (err) {
      return {
        ok: false,
        error:
          err instanceof ApiError
            ? err.message
            : String(err),
      };
    }
  }
);

ipcMain.on("nova:send", async (event, { message, requestId }) => {
  const sender = event.sender;

  try {
    await streamChat(
      settings.apiBaseUrl,
      message,
      currentConversationId,
      (nova_event) => {
        console.log("NOVA EVENT:", nova_event);

        if (nova_event.type === "conversation_id" && nova_event.id) {
          currentConversationId = nova_event.id;
        }

        sender.send("nova:event", {
          requestId,
          ...nova_event,
        });
      }
    );

    sender.send("nova:stream-end", { requestId });
  } catch (err) {
    sender.send("nova:event", {
      requestId,
      type: "error",
      message: err instanceof ApiError ? err.message : String(err),
    });

    sender.send("nova:stream-end", { requestId });
  }
});

ipcMain.on("nova:new-conversation", () => {
  currentConversationId = null;
});

// ---- IPC: terminals ---------------------------------------------------------

ipcMain.handle("nova:terminal-start", (_event, id) => {
  return startTerminal(id);
});

ipcMain.on("nova:terminal-input", (_event, { id, data }) => {
  writeTerminal(id, data);
});

ipcMain.on("nova:terminal-resize", (_event, { id, cols, rows }) => {
  resizeTerminal(id, cols, rows);
});

ipcMain.on("nova:terminal-kill", (_event, id) => {
  killTerminal(id);
});