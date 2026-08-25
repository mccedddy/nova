import json
import unittest

from agent.client import extract_tool_calls
from agent.validation import validate_tool_call


class ExtractToolCallsTests(unittest.TestCase):
    def test_extracts_json_string_arguments(self):
        response = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "add",
                            "arguments": json.dumps({"a": 2, "b": 3}),
                        }
                    }
                ]
            }
        }

        self.assertEqual(
            extract_tool_calls(response),
            [{"name": "add", "arguments": {"a": 2, "b": 3}}],
        )

    def test_preserves_malformed_arguments_for_validation(self):
        response = {
            "message": {
                "tool_calls": [
                    {"function": {"name": "add", "arguments": "not json"}}
                ]
            }
        }

        self.assertEqual(
            extract_tool_calls(response),
            [{"name": "add", "arguments": {"_raw": "not json"}}],
        )


class ValidateToolCallTests(unittest.TestCase):
    SCHEMAS = [
        {
            "function": {
                "name": "add",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "integer"},
                        "b": {"type": "integer"},
                    },
                    "required": ["a", "b"],
                },
            }
        }
    ]

    def test_coerces_simple_scalar_arguments(self):
        ok, arguments = validate_tool_call(
            "add", {"a": "2", "b": 3}, {"add": lambda a, b: a + b}, self.SCHEMAS
        )

        self.assertTrue(ok)
        self.assertEqual(arguments, {"a": 2, "b": 3})

    def test_reports_missing_required_arguments(self):
        ok, error = validate_tool_call(
            "add", {"a": 2}, {"add": lambda a, b: a + b}, self.SCHEMAS
        )

        self.assertFalse(ok)
        self.assertIn("missing required argument", error)


if __name__ == "__main__":
    unittest.main()
