TYPE_MAP = {
    "integer": int,
    "number": float,
    "string": str,
    "boolean": bool,
}


def validate_tool_call(name, args, registry, schemas):
    # Return validated arguments, or an error message for the model to retry.

    if name not in registry:
        return False, f"unknown tool '{name}' -- not in the available tool list"

    schema = _find_schema(name, schemas)
    if schema is None:
        # Keep the loop usable if registry and schema metadata drift apart.
        return True, args

    params = schema["function"]["parameters"]
    properties = params.get("properties", {})
    required = params.get("required", [])

    missing = [p for p in required if p not in args]
    if missing:
        return False, f"missing required argument(s): {', '.join(missing)}"

    coerced = dict(args)
    for key, value in args.items():
        expected_type = properties.get(key, {}).get("type")
        py_type = TYPE_MAP.get(expected_type)

        if py_type is None:
            continue

        if isinstance(value, py_type):
            continue

        # Coerce simple scalar mismatches when Python can do so safely.
        try:
            coerced[key] = py_type(value)
        except (ValueError, TypeError):
            return False, f"argument '{key}' should be {expected_type}, got {value!r}"

    return True, coerced


def _find_schema(name, schemas):
    for schema in schemas:
        if schema["function"]["name"] == name:
            return schema
    return None