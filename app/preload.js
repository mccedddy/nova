const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nova", {
  // Send chat message to API
  send(message, requestId) {
    ipcRenderer.send("nova:send", { message, requestId });
  },

  // Start new conversation
  newConversation() {
    ipcRenderer.send("nova:new-conversation");
  },

  // Hide main window
  hide() {
    return ipcRenderer.send("nova:hide");
  },

  // Listen for API events
  onEvent(callback) {
    ipcRenderer.on("nova:event", (_e, payload) => callback(payload));
  },

  // Listen for stream end
  onStreamEnd(callback) {
    ipcRenderer.on("nova:stream-end", (_e, payload) => callback(payload));
  },

  // Listen for input focus request
  onFocusInput(callback) {
    ipcRenderer.on("nova:focus-input", () => callback());
  },

  // Check API and Ollama health
  health() {
    return ipcRenderer.invoke("nova:health");
  },

  // Send permission response to API
  respondToPermission(conversationId, approved) {
    return ipcRenderer.invoke("nova:permission", { conversationId, approved });
  },

  // Get app settings
  getSettings() {
    return ipcRenderer.invoke("nova:get-settings");
  },

  // Save app settings
  saveSettings(partial) {
    return ipcRenderer.invoke("nova:save-settings", partial);
  },

  // Get agent model/tool settings
  getAgentSettings() {
    return ipcRenderer.invoke("nova:get-agent-settings");
  },

  // Save agent settings
  saveAgentSettings(values) {
    return ipcRenderer.invoke("nova:save-agent-settings", values);
  },

  // Start terminal instance
  terminalStart(id) {
    return ipcRenderer.invoke("nova:terminal-start", id);
  },

  // Send input to terminal
  terminalInput(id, data) {
    return ipcRenderer.invoke("nova:terminal-input", { id, data });
  },

  // Resize terminal
  terminalResize(id, cols, rows) {
    return ipcRenderer.invoke("nova:terminal-resize", { id, cols, rows });
  },

  // Kill terminal
  terminalKill(id) {
    return ipcRenderer.invoke("nova:terminal-kill", id);
  },

  // Listen for terminal output
  onTerminalData(callback) {
    ipcRenderer.on("nova:terminal-data", (_e, payload) => callback(payload));
  },

  // Listen for terminal exit
  onTerminalExit(callback) {
    ipcRenderer.on("nova:terminal-exit", (_e, payload) => callback(payload));
  },
});