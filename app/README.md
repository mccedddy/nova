# NOVA Desktop (Phase 13)

Windows desktop client for N.O.V.A. It is a **separate client** of the
Phase 7 local API -- no agent/tool logic is duplicated here. This process
only does three things: shows a summon-able prompt window, streams events
from `POST /chat`, and renders them.

## Setup

```
cd nova-desktop
npm install
npm start
```

Requires the NOVA API (Phase 7) running locally, default `http://127.0.0.1:8000`.
Change the base URL later via `nova.saveSettings({ apiBaseUrl: "..." })` --
a real settings UI for this arrives in Phase 14.

## How it behaves

- **Alt+Space** (configurable) toggles a small floating window, centered
  near the top of the primary display -- summon, ask, dismiss.
- Losing focus or pressing **Esc** hides the window; it keeps running in
  the system tray rather than quitting, so the shortcut stays live.
- Conversation stays in memory in the main process only (`conversation_id`
  round-tripped from the API), matching the API's own in-memory-only scope.
  "New conversation" clears it client-side.
- The dot in the footer reflects a `GET /health` poll every 15s.

## Design notes

The palette and layout aren't decorative choices, they're mapped straight
onto how NOVA already reasons about risk:

- Teal = **READ**-tier tool activity (auto-executes, shown quietly).
- Amber = **MODIFY**-tier, red = **DESTRUCTIVE**-tier -- reserved for when
  the API starts including a `tier` field on tool/confirmation events. The
  renderer already switches on `evt.tier`, so no client change should be
  needed when Phase 8's confirmation flow gets surfaced here.
- Fonts are Windows-native only (Segoe UI / Cascadia Code) -- this is a
  Windows-only, offline-first tool, so it should look like it ships with
  the OS rather than pulling in a web font.
- The tool log renders like a system log line (monospace, colored left
  rule) rather than chat bubbles, since "what is NOVA doing to my machine
  right now" is the thing a user actually wants to track at a glance.

## Event contract expected from the API

One JSON object per line from `POST /chat`:

```
{"type": "tool_started", "name": "...", "args": {...}}
{"type": "tool_finished", "name": "...", "result": {...}}
{"type": "answer", "text": "..."}
{"type": "error", "message": "..."}
```

Optional `"tier": "read" | "modify" | "destructive"` and
`"conversation_id": "..."` are read if present; both are safe to omit today.

## Known stubs / what's intentionally not here yet

- **Settings UI** -- `settings.js` persists a small JSON file already
  (`apiBaseUrl`, `globalShortcut`, `launchAtLogin`, `reduceMotion`), but
  there's no window to edit it yet. That's Phase 14.
- **Ollama/API process control, log panels** -- Phase 14.
- **Voice input/output** -- Phase 15.
- **Launch at login** -- setting exists in the schema, not wired to
  `app.setLoginItemSettings` yet.
- No app/tray icon is code-signed; expect a SmartScreen prompt on first
  run of a packaged build until that's set up.

## Packaging

`npm run dist` uses `electron-builder` to produce a Windows installer
(`electron-builder` and `electron` are devDependencies -- install with
network access before running this on a real machine, this sandbox has
none).
