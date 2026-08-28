"""NOVA runtime settings.

Edit the values in this file when benchmarking or tuning NOVA. Values are
kept in Python so comments can explain what each setting controls.
"""

# Ollama connection and model settings.
OLLAMA_URL = "http://localhost:11434/api/chat"  # Ollama chat endpoint.
MODEL = "qwen3.5:9b"  # Model name installed in Ollama.
OLLAMA_REQUEST_TIMEOUT = 120  # Seconds to wait for one model response.

# Context and response generation settings sent to Ollama.
NUM_CTX = 65536  # Context window in tokens; examples: 16384, 32768, 65536.
NUM_PREDICT = 8192  # Maximum generated tokens; examples: 4096 or 8192.

# Agent-loop limits.
MAX_ITERATIONS = 50  # Maximum model/tool-response rounds in one user turn.
MAX_RETRIES = 2  # Validation retries for the same tool before giving up.
MAX_TERMINAL_CHARS = 1000  # Debug result characters shown before truncation.

# PowerShell execution settings.
POWERSHELL_TIMEOUT = 20  # Default command timeout in seconds.
POWERSHELL_MAX_TIMEOUT = 120  # Hard upper bound for a requested timeout.

# Filesystem scan settings.
FILESYSTEM_TIMEOUT = 20  # Maximum seconds spent scanning filesystem roots.
FILESYSTEM_MAX_RESULTS = 40  # Maximum files returned by a search.

# Web-search settings.
WEB_SEARCH_MAX_RESULTS = 5  # Results requested from each search backend.
WEB_SEARCH_TIMEOUT = 12  # Seconds allowed for a web search request.
WEB_FETCH_TIMEOUT = 15  # Seconds allowed to fetch one web page.
WEB_MAX_PAGE_CHARS = 5000  # Maximum extracted page characters returned to NOVA.
LOCATION_LOOKUP_TIMEOUT = 8  # Seconds allowed for IP geolocation.

# Registry and system-inspection limits.
REGISTRY_MAX_VALUES = 50  # Maximum values returned for one registry key.
REGISTRY_MAX_SUBKEYS = 50  # Maximum subkeys returned for one registry key.
SYSTEM_POWERSHELL_TIMEOUT = 15  # Default timeout for WMI system queries.
DISK_HEALTH_TIMEOUT = 20  # Timeout for the physical-disk health query.
NVIDIA_SMI_TIMEOUT = 10  # Timeout for the optional nvidia-smi query.

# API health-check settings.
API_HEALTH_TIMEOUT = 3  # Seconds to wait when checking whether Ollama is up.
