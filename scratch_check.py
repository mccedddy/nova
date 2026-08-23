# scratch_processes_check.py
from tools.processes import list_running_processes
import json

print(json.dumps(list_running_processes(), indent=2))