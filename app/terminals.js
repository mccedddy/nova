const { spawn } = require("node-pty");
const path = require("path");

// Manages PTY terminal instances
const terminals = new Map();

const TERMINAL_CONFIG = {
  1: { cwd: "C:\\DEV\\nova" },
  2: { cwd: "C:\\DEV\\nova" },
};

// Get venv activation script path
function getVenvPath() {
  return path.resolve(__dirname, "..", "venv", "Scripts", "Activate.ps1");
}

// Start a terminal and attach data/exit handlers
function startTerminal(id, onData, onExit) {
  const terminalId = String(id);

  if (terminals.has(terminalId)) {
    return { ok: true, alreadyRunning: true };
  }

  const config = TERMINAL_CONFIG[terminalId];
  if (!config) {
    return { ok: false, error: `Unknown terminal: ${terminalId}` };
  }

  const venvPath = getVenvPath();
  const command = [
    `Set-Location -LiteralPath '${config.cwd}'`,
    `$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()`,
    `if (Test-Path -LiteralPath '${venvPath}') { . '${venvPath}' }`,
  ].join("; ");

  // Spawn PowerShell with venv activation
  const ptyProcess = spawn(
    "powershell.exe",
    ["-NoLogo", "-NoExit", "-ExecutionPolicy", "Bypass", "-Command", command],
    {
      name: "xterm-256color",
      cols: 100,
      rows: 30,
      cwd: config.cwd,
      env: { ...process.env, TERM_PROGRAM: "NOVA" },
    }
  );

  terminals.set(terminalId, ptyProcess);

  // Forward PTY output to renderer
  ptyProcess.onData((data) => onData(terminalId, data));
  ptyProcess.onExit(({ exitCode, signal }) => {
    terminals.delete(terminalId);
    onExit(terminalId, exitCode, signal);
  });

  return { ok: true, alreadyRunning: false };
}

// Write data to terminal input
function writeTerminal(id, data) {
  const terminal = terminals.get(String(id));
  if (!terminal) {
    return { ok: false, error: `Terminal ${id} is not running` };
  }
  terminal.write(data);
  return { ok: true };
}

// Resize terminal dimensions
function resizeTerminal(id, cols, rows) {
  const terminal = terminals.get(String(id));
  if (!terminal) return;

  if (Number.isInteger(cols) && Number.isInteger(rows) && cols > 0 && rows > 0) {
    terminal.resize(cols, rows);
  }
}

// Kill terminal and clean up
function killTerminal(id) {
  const terminal = terminals.get(String(id));
  if (!terminal) return;

  try {
    terminal.kill();
  } catch {
    // Ignore cleanup errors
  }
  terminals.delete(String(id));
}

// Kill all terminals on shutdown
function killAllTerminals() {
  for (const [, terminal] of terminals) {
    try {
      terminal.kill();
    } catch {
      // Ignore cleanup errors
    }
  }
  terminals.clear();
}

module.exports = {
  startTerminal,
  writeTerminal,
  resizeTerminal,
  killTerminal,
  killAllTerminals,
};
