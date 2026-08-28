const { app, BrowserWindow, Tray, Menu, globalShortcut, ipcMain, screen, nativeImage } = require("electron");
const path = require("path");

const { loadSettings, saveSettings } = require("./settings");
const { checkHealth, streamChat, ApiError } = require("./api-client");

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
});

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

ipcMain.on("nova:send", async (event, { message, requestId }) => {
  const sender = event.sender;

  try {
    await streamChat(settings.apiBaseUrl, message, currentConversationId, (nova_event) => {
      if (nova_event.conversation_id) {
        currentConversationId = nova_event.conversation_id;
      }
      sender.send("nova:event", { requestId, ...nova_event });
    });
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
