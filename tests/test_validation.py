from agent.loop import validate_tool_call

REGISTRY = {"add": lambda a, b: a + b}

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "add",
            "description": "Add two numbers",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        },
    }
]


def test_valid_args_pass_through():
    ok, result = validate_tool_call("add", {"a": 5, "b": 7}, REGISTRY, SCHEMAS)
    assert ok is True
    assert result == {"a": 5, "b": 7}


def test_missing_required_arg_detected():
    ok, result = validate_tool_call("add", {"a": 5}, REGISTRY, SCHEMAS)
    assert ok is False
    assert "missing required argument" in result
    assert "b" in result


def test_missing_multiple_required_args_detected():
    ok, result = validate_tool_call("add", {}, REGISTRY, SCHEMAS)
    assert ok is False
    assert "a" in result
    assert "b" in result


def test_unknown_tool_name_rejected():
    ok, result = validate_tool_call("delete_everything", {}, REGISTRY, SCHEMAS)
    assert ok is False
    assert "unknown tool" in result.lower()


def test_string_int_coerced_to_int():
    ok, result = validate_tool_call("add", {"a": "5", "b": "7"}, REGISTRY, SCHEMAS)
    assert ok is True
    assert result == {"a": 5, "b": 7}
    assert isinstance(result["a"], int)


def test_uncoercible_value_reported_as_error():
    ok, result = validate_tool_call("add", {"a": "not_a_number", "b": 7}, REGISTRY, SCHEMAS)
    assert ok is False
    assert "a" in result
    assert "integer" in result