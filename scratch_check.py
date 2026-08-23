# scratch_network_check.py
from tools.processes import get_network_connections
import json

print(json.dumps(get_network_connections(), indent=2))