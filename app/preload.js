const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nova", {
  // ---------------------------------------------------------------------------
  // CHAT
  // ---------------------------------------------------------------------------

  send(message, requestId) {
    ipcRenderer.send("nova:send", { message, requestId });
  },

  newConversation() {
    ipcRenderer.send("nova:new-conversation");
  },

  // ---------------------------------------------------------------------------
  // WINDOW
  // ---------------------------------------------------------------------------

  hide() {
    ipcRenderer.send("nova:hide");
  },

  // ---------------------------------------------------------------------------
  // NOVA EVENTS
  // ---------------------------------------------------------------------------

  onEvent(callback) {
    ipcRenderer.on("nova:event", (_e, payload) => callback(payload));
  },

  onStreamEnd(callback) {
    ipcRenderer.on("nova:stream-end", (_e, payload) => callback(payload));
  },

  onFocusInput(callback) {
    ipcRenderer.on("nova:focus-input", () => callback());
  },

  // ---------------------------------------------------------------------------
  // API / SETTINGS
  // ---------------------------------------------------------------------------

  health() {
    return ipcRenderer.invoke("nova:health");
  },

  respondToPermission(conversationId, approved) {
    return ipcRenderer.invoke(
      "nova:permission",
      {
        conversationId,
        approved,
      }
    );
  },

    getSettings() {
    return ipcRenderer.invoke("nova:get-settings");
  },

  saveSettings(partial) {
    return ipcRenderer.invoke("nova:save-settings", partial);
  },

  getAgentSettings: () => ipcRenderer.invoke("nova:get-agent-settings"),
  saveAgentSettings: (values) => ipcRenderer.invoke("nova:save-agent-settings", values),

  // ---------------------------------------------------------------------------
  // TERMINALS
  // ---------------------------------------------------------------------------

  terminalStart(id) {
    return ipcRenderer.invoke("nova:terminal-start", id);
  },

  terminalInput(id, data) {
    ipcRenderer.send("nova:terminal-input", { id, data });
  },

  terminalResize(id, cols, rows) {
    ipcRenderer.send("nova:terminal-resize", {
      id,
      cols,
      rows,
    });
  },

  terminalKill(id) {
    ipcRenderer.send("nova:terminal-kill", id);
  },

  onTerminalData(callback) {
    ipcRenderer.on("nova:terminal-data", (_e, payload) => {
      callback(payload);
    });
  },

  onTerminalExit(callback) {
    ipcRenderer.on("nova:terminal-exit", (_e, payload) => {
      callback(payload);
    });
  },
});