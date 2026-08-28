// Minimal client-side settings for the Phase 13 desktop shell.
//
// This intentionally stays small: just enough to make the shortcut and API
// endpoint configurable without editing source. Phase 14 replaces this with
// the full settings.json + settings.py system (model/context/timeout config,
// Ollama + API process control, restart-required handling, etc). Don't grow
// this file with Phase 14 concerns -- add a new module instead.

const fs = require("fs");
const path = require("path");
const { app } = require("electron");

const DEFAULTS = {
  apiBaseUrl: "http://127.0.0.1:8000",
  globalShortcut: "Alt+Space",
  launchAtLogin: false,
  reduceMotion: false,
};

function settingsPath() {
  return path.join(app.getPath("userData"), "settings.json");
}

function loadSettings() {
  const file = settingsPath();
  try {
    const raw = fs.readFileSync(file, "utf-8");
    const parsed = JSON.parse(raw);
    return { ...DEFAULTS, ...parsed };
  } catch (err) {
    // Missing or invalid file -- fall back to defaults rather than crash.
    return { ...DEFAULTS };
  }
}

function saveSettings(settings) {
  const file = settingsPath();
  const merged = { ...DEFAULTS, ...settings };
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(merged, null, 2), "utf-8");
  return merged;
}

module.exports = { DEFAULTS, loadSettings, saveSettings, settingsPath };
