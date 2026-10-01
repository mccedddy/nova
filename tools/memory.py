"""Tool wrappers for durable user memory.

The storage logic lives in agent/memory.py. These are the registry-facing
callables the model invokes, with the signatures the schemas declare.
"""

from agent.memory import forget as _forget
from agent.memory import remember as _remember


def remember(key, value):
    # Store a durable fact about the user so later conversations can use it.
    return _remember(key, value, source="explicit")


def forget(key):
    # Remove a previously stored fact by its key.
    return _forget(key)
