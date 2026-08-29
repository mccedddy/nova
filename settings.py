"""Load and validate NOVA's user-editable JSON settings."""

import json
from pathlib import Path


SETTINGS_PATH = Path(__file__).with_name("settings.json")

# These defaults are used when settings.json is missing, incomplete, or invalid.
# The Electron app should show these descriptions and valid ranges in its settings UI.
DEFAULTS = {
	"ollama_url": "http://localhost:11434/api/chat",
	"model": "qwen3.5:9b",
	"ollama_request_timeout": 120,
	"num_ctx": 229376,
	"num_predict": 8192,
	"max_iterations": 50,
	"max_retries": 2,
	"max_terminal_chars": 1000,
	"powershell_timeout": 20,
	"powershell_max_timeout": 120,
	"filesystem_timeout": 20,
	"filesystem_max_results": 40,
	"web_search_max_results": 5,
	"web_search_timeout": 12,
	"web_fetch_timeout": 15,
	"web_max_page_chars": 5000,
	"location_lookup_timeout": 8,
	"registry_max_values": 50,
	"registry_max_subkeys": 50,
	"system_powershell_timeout": 15,
	"disk_health_timeout": 20,
	"nvidia_smi_timeout": 10,
	"api_health_timeout": 3,
}

INTEGER_RANGES = {
	"ollama_request_timeout": (1, 600),
	"num_ctx": (1024, 131072),
	"num_predict": (1, 32768),
	"max_iterations": (1, 1000),
	"max_retries": (0, 10),
	"max_terminal_chars": (100, 100000),
	"powershell_timeout": (1, 120),
	"powershell_max_timeout": (1, 600),
	"filesystem_timeout": (1, 600),
	"filesystem_max_results": (1, 1000),
	"web_search_max_results": (1, 100),
	"web_search_timeout": (1, 120),
	"web_fetch_timeout": (1, 120),
	"web_max_page_chars": (100, 100000),
	"location_lookup_timeout": (1, 120),
	"registry_max_values": (1, 1000),
	"registry_max_subkeys": (1, 1000),
	"system_powershell_timeout": (1, 120),
	"disk_health_timeout": (1, 120),
	"nvidia_smi_timeout": (1, 120),
	"api_health_timeout": (1, 120),
}


def _load_settings():
	try:
		with SETTINGS_PATH.open("r", encoding="utf-8") as file:
			configured = json.load(file)
	except (OSError, json.JSONDecodeError):
		configured = {}

	if not isinstance(configured, dict):
		configured = {}

	settings = DEFAULTS.copy()
	for name, value in configured.items():
		if name not in DEFAULTS:
			continue
		if name in INTEGER_RANGES:
			if isinstance(value, bool) or not isinstance(value, int):
				continue
			minimum, maximum = INTEGER_RANGES[name]
			if not minimum <= value <= maximum:
				continue
		elif name in {"ollama_url", "model"} and not isinstance(value, str):
			continue
		settings[name] = value

	if settings["powershell_max_timeout"] < settings["powershell_timeout"]:
		settings["powershell_max_timeout"] = settings["powershell_timeout"]

	return settings


_SETTINGS = _load_settings()

OLLAMA_URL = _SETTINGS["ollama_url"]
MODEL = _SETTINGS["model"]
OLLAMA_REQUEST_TIMEOUT = _SETTINGS["ollama_request_timeout"]
NUM_CTX = _SETTINGS["num_ctx"]
NUM_PREDICT = _SETTINGS["num_predict"]
MAX_ITERATIONS = _SETTINGS["max_iterations"]
MAX_RETRIES = _SETTINGS["max_retries"]
MAX_TERMINAL_CHARS = _SETTINGS["max_terminal_chars"]
POWERSHELL_TIMEOUT = _SETTINGS["powershell_timeout"]
POWERSHELL_MAX_TIMEOUT = _SETTINGS["powershell_max_timeout"]
FILESYSTEM_TIMEOUT = _SETTINGS["filesystem_timeout"]
FILESYSTEM_MAX_RESULTS = _SETTINGS["filesystem_max_results"]
WEB_SEARCH_MAX_RESULTS = _SETTINGS["web_search_max_results"]
WEB_SEARCH_TIMEOUT = _SETTINGS["web_search_timeout"]
WEB_FETCH_TIMEOUT = _SETTINGS["web_fetch_timeout"]
WEB_MAX_PAGE_CHARS = _SETTINGS["web_max_page_chars"]
LOCATION_LOOKUP_TIMEOUT = _SETTINGS["location_lookup_timeout"]
REGISTRY_MAX_VALUES = _SETTINGS["registry_max_values"]
REGISTRY_MAX_SUBKEYS = _SETTINGS["registry_max_subkeys"]
SYSTEM_POWERSHELL_TIMEOUT = _SETTINGS["system_powershell_timeout"]
DISK_HEALTH_TIMEOUT = _SETTINGS["disk_health_timeout"]
NVIDIA_SMI_TIMEOUT = _SETTINGS["nvidia_smi_timeout"]
API_HEALTH_TIMEOUT = _SETTINGS["api_health_timeout"]
