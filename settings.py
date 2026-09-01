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
	"num_ctx": (1024, 229376),
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


def _validate_value(name, value):
	"""Return (ok, value) for a single setting, applying the same rules as _load_settings."""
	if name not in DEFAULTS:
		return False, None
	if name in INTEGER_RANGES:
		if isinstance(value, bool) or not isinstance(value, int):
			return False, None
		minimum, maximum = INTEGER_RANGES[name]
		if not minimum <= value <= maximum:
			return False, None
	elif name in {"ollama_url", "model"} and not isinstance(value, str):
		return False, None
	return True, value


def _read_raw():
	try:
		with SETTINGS_PATH.open("r", encoding="utf-8") as file:
			configured = json.load(file)
	except (OSError, json.JSONDecodeError):
		configured = {}
	return configured if isinstance(configured, dict) else {}


def _load_settings():
	configured = _read_raw()

	settings = DEFAULTS.copy()
	for name, value in configured.items():
		ok, validated = _validate_value(name, value)
		if ok:
			settings[name] = validated

	if settings["powershell_max_timeout"] < settings["powershell_timeout"]:
		settings["powershell_max_timeout"] = settings["powershell_timeout"]

	return settings


def save_settings(partial):
	"""Validate and persist a partial settings update to settings.json.

	Returns (merged_settings, rejected) -- rejected lists any keys that
	failed validation and were skipped rather than written.
	"""
	raw = _read_raw()
	rejected = []

	for name, value in partial.items():
		ok, validated = _validate_value(name, value)
		if ok:
			raw[name] = validated
		else:
			rejected.append(name)

	SETTINGS_PATH.write_text(json.dumps(raw, indent=2), encoding="utf-8")

	settings = DEFAULTS.copy()
	settings.update(raw)
	if settings["powershell_max_timeout"] < settings["powershell_timeout"]:
		settings["powershell_max_timeout"] = settings["powershell_timeout"]

	return settings, rejected


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
