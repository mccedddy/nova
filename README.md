# N.O.V.A.

**Native Operating-system Virtual Assistant** — a local Windows AI assistant powered by Ollama. NOVA inspects and controls your system through native, permission-gated tools and answers in natural language.

> Screenshot placeholder — add a screenshot of the desktop UI here.

## What it does

- **System diagnostics** — CPU, RAM, disk, GPU, and OS info
- **Process & network insight** — running processes, network connections
- **Registry & installed apps** — query registry keys, list installed software
- **Filesystem** — search files, folder sizes, file-relevance / temp-cache signals
- **Web integration** — web search + page fetching for current information
- **Dynamic PowerShell** — escape hatch for anything without a dedicated tool, gated by risk tier
- **Memory** — remembers durable facts between conversations, viewable and deletable in the client; incognito mode turns it off
- **Two interfaces** — a terminal CLI and an Electron desktop UI

## Architecture

NOVA is built as three separate layers that only talk over well-defined boundaries:

```
┌─────────────────────────────────────────────────────────┐
│  Electron desktop client (app/)                         │
│  └─ chat UI · terminals · settings · tray · hotkey      │
└──────────────────────────────┬──────────────────────────┘
                               │ NDJSON events over HTTP
┌──────────────────────────────▼──────────────────────────┐
│  Local Python API (api/server.py) 127.0.0.1:8000        │
└──────────────────────────────┬──────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────┐
│  Agent core (agent/ + tools/)                           │
│  └─ ReAct loop · tool validation · permissions · Ollama │
└─────────────────────────────────────────────────────────┘
```

The desktop client consumes the API and **never runs Python tools directly**. The agent core runs the tool-calling loop against Ollama.

## Requirements

- Windows 10/11
- [Ollama](https://ollama.com/) running on `localhost:11434` with a model pulled (default `qwen3.5:9b`, configurable in `settings.json`)
- Python 3.10+
- Node.js (for the Electron desktop client)

Optional: an `OLLAMA_API_KEY` in `.env` enables the tier-2 web search fallback (see `tools/websearch.py`).

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Make sure Ollama is running and the model is pulled
ollama serve
ollama pull qwen3.5:9b

# 4. (Optional) Desktop client dependencies -- node-pty may need native compilation
cd app
npm install
npm rebuild node-pty
```

## Usage

### Terminal client

```bash
python main.py
python main.py --debug-tools            # show raw tool names/args/results
python main.py --debug-tools --full-output  # untruncated tool results
```

Type `exit` or `quit` (or Ctrl+C) to leave.

### API server (needed for the desktop client)

```bash
python api/server.py     # uvicorn on 127.0.0.1:8000
```

Endpoints: `GET /health`, `POST /chat` (NDJSON stream), `POST /permission`,
`GET|POST /settings`, `GET /memory`, `DELETE /memory/{key}`.

### Desktop client

```bash
cd app
npm start
```

The app runs in the system tray with a global shortcut (default `Alt+Space`) to toggle the window. It includes a chat view, two PowerShell terminals, and a settings panel.

### Permissions

Every tool that can change system state is classified into a risk tier and **enforced in Python, never by the model**:

- **READ** — inspects only, auto-executes
- **MODIFY** — changes something, requires confirmation
- **DESTRUCTIVE / SYSTEM-LEVEL** — delete/format/restart, requires explicit confirmation

`execute_powershell` commands are classified per-command by regex (`agent/permissions.py`); anything unrecognized defaults to MODIFY for safety.

`remember` / `forget` are a deliberate exception: they write to disk but auto-execute, because the write is scoped to NOVA's own gitignored store and is trivially reversible — a DESTRUCTIVE prompt every time you express a preference would be noise. They are kept out of `READ_ONLY_TOOLS` so that set stays honest, and incognito mode is the opt-out.

## Memory and incognito

NOVA can keep short durable facts (name, preferred shell, standing preferences) between conversations:

- The model calls `remember`/`forget` when you state something worth keeping.
- Autocapture additionally distills facts after a turn, controlled by `memory_autocapture_mode` in `settings.json`:
  - `"trigger"` (default) only inspects messages that sound like a standing preference (`from now on…`, `always…`, `call me…`). Free — non-matching turns don't cost a model call.
  - `"always"` lets the model judge **every** turn, so plainly-stated facts ("I mostly use Neovim") are kept without trigger phrasing. Costs one short model call per turn, run in the background so it never delays a reply.
  - To turn memory off entirely, set `memory_enabled: false`.
- Stored facts are injected into each **new** conversation. The desktop client has a **Memory** panel where you can read exactly what's been kept and delete anything you don't want.
- **Incognito mode** (sidebar toggle) suppresses both reads and writes for that conversation. The refusal happens in Python before the tool runs, so it doesn't depend on the model cooperating.

Two honest caveats:

- Autocapture is **best-effort**. On a local 9B model it catches roughly 3 in 5 trigger-phrased turns, so a fact you phrased carefully may still slip through. If something wasn't saved, say "remember that …" and it's stored immediately and reliably.
- Every capture attempt is recorded in `memory.log` (project root). If a fact you expected to be kept isn't showing up, that file will say whether the trigger never fired or the extraction found nothing — the two look identical from the outside.
- The store is `memory.json` in the project root — gitignored, because it's personal data.

## Configuration

- **`settings.json`** (project root) — model, context size, iteration/retry caps, and all tool timeouts/limits. Loaded and validated by `settings.py`. Invalid or out-of-range values silently fall back to defaults; `powershell_max_timeout` is clamped to be ≥ `powershell_timeout`.
- **Desktop client** settings are stored separately in `%LOCALAPPDATA%\NOVA\settings.json` (API URL, global shortcut, incognito mode).
- Agent settings changed from the desktop UI are written to `settings.json` but require **restarting the API server** to take effect.

## Testing

```bash
pytest
```

Tests mock the Ollama client — no live model or server is needed. See the `tests/` directory.

## Project layout

```
nova/
  main.py                 # terminal CLI entry point
  settings.py             # settings loader/validator
  settings.json           # runtime config
  agent/                  # ReAct loop, client, prompts, permissions, annotations, memory
  api/server.py           # FastAPI server
  tools/                  # 16 tool implementations + schemas
  app/                    # Electron desktop client
  tests/                  # pytest suite (mocked Ollama)
  docs/index.md           # file-by-file API reference
```

## Docs

- `AGENTS.md` — contributor conventions, run commands, and design decisions
- `docs/index.md` — file-by-file API reference (signatures, arguments, return shapes)

## Notes / current status

- The API is local-only (bound to `127.0.0.1:8000`) and has **no auth layer** — by design.
- Conversations are **in-memory only** (transcripts are never persisted).
- **Memory is persistent**: durable user facts live in `memory.json` (gitignored), are
  injected into new conversations, and are viewable/deletable in the desktop client's
  Memory panel. **Incognito mode** suppresses both reads and writes for a conversation,
  and is enforced in Python rather than asked for politely in the prompt.
- Voice input/output is planned but not yet implemented.
