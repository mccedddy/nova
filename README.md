# N.O.V.A.

N.O.V.A. is a terminal-based, read-only Windows inspection assistant backed by
Ollama tool calling. It reports local system facts and can use web search when
the system prompt requires current or unfamiliar information.

## Setup

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start Ollama with the configured model, then run:

```powershell
python main.py
```

Use `python main.py --debug-tools` to display tool calls and results. Enter
`exit` or `quit` to leave.

## Development

Run the dependency-free helper tests with:

```powershell
python -m unittest discover -s tests -v
```

The agent loop lives in `agent/loop.py`; callable tool registration is kept in
`agent/tool_registry.py`; implementations are grouped under `tools/`.
