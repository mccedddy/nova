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

Endpoints: `GET /health`, `POST /chat` (NDJSON stream), `POST /permission`, `GET|POST /settings`.

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

## Configuration

- **`settings.json`** (project root) — model, context size, iteration/retry caps, and all tool timeouts/limits. Loaded and validated by `settings.py`. Invalid or out-of-range values silently fall back to defaults; `powershell_max_timeout` is clamped to be ≥ `powershell_timeout`.
- **Desktop client** settings are stored separately in `%LOCALAPPDATA%\NOVA\settings.json` (API URL, global shortcut).
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
  agent/                  # ReAct loop, client, prompts, permissions, annotations
  api/server.py           # FastAPI server
  tools/                  # 14 tool implementations + schemas
  app/                    # Electron desktop client
  tests/                  # pytest suite (mocked Ollama)
  docs/index.md           # file-by-file API reference
```

## Docs

- `AGENTS.md` — contributor conventions, run commands, and design decisions
- `docs/index.md` — file-by-file API reference (signatures, arguments, return shapes)

## Notes / current status

- The API is local-only (bound to `127.0.0.1:8000`) and has **no auth layer** — by design.
- Conversations are **in-memory only** (no persistence).
- Voice input/output and persistent memory are planned but not yet implemented.
