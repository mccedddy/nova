TYPE_MAP = {
    "integer": int,
    "number": float,
    "string": str,
    "boolean": bool,
}


def validate_tool_call(name, args, registry, schemas):
    # returns (ok: bool, result: dict or str)
    # if ok is True, result is the (possibly coerced) args dict to call with
    # if ok is False, result is an error message to feed back to the model

    if name not in registry:
        return False, f"unknown tool '{name}' -- not in the available tool list"

    schema = _find_schema(name, schemas)
    if schema is None:
        # shouldn't normally happen if registry and schemas stay in sync,
        # but don't crash if it does -- just skip arg-level checks
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
            continue  # unknown/unspecified type -- don't try to coerce

        if isinstance(value, py_type):
            continue  # already correct type

        # try a simple coercion (e.g. "5" -> 5) -- if it fails, report it
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