const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("nova", {
  send(message, requestId) {
    ipcRenderer.send("nova:send", { message, requestId });
  },
  newConversation() {
    ipcRenderer.send("nova:new-conversation");
  },
  hide() {
    ipcRenderer.send("nova:hide");
  },
  onEvent(callback) {
    ipcRenderer.on("nova:event", (_e, payload) => callback(payload));
  },
  onStreamEnd(callback) {
    ipcRenderer.on("nova:stream-end", (_e, payload) => callback(payload));
  },
  onFocusInput(callback) {
    ipcRenderer.on("nova:focus-input", () => callback());
  },
  health() {
    return ipcRenderer.invoke("nova:health");
  },
  getSettings() {
    return ipcRenderer.invoke("nova:get-settings");
  },
  saveSettings(partial) {
    return ipcRenderer.invoke("nova:save-settings", partial);
  },
});
