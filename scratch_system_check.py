# scratch_system_check.py
from tools.system import get_system_diagnostics
import json

print(json.dumps(get_system_diagnostics(), indent=2))