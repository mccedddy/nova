import threading

from agent.client import chat, extract_tool_calls, get_final_text, OllamaUnavailableError
from agent.permissions import (
    PermissionDenied,
    execute_tool,
    request_confirmation,
    classify_operation,
    RiskTier,
    confirmation_details,
)
from agent.annotations import annotate_result, is_execution_failure, needs_verification
from agent.tool_registry import TOOL_REGISTRY
from tools.tool_schemas import TOOL_SCHEMAS
from settings import MAX_ITERATIONS, MAX_RETRIES, MAX_TERMINAL_CHARS

# Progress message templates for tool calls
TOOL_PROGRESS_MESSAGES = {
    "get_system_diagnostics": "Analyzing system diagnostics",
    "list_running_processes": "Checking running processes",
    "get_network_connections": "Checking network connections",
    "get_gpu_driver_info": "Analyzing GPU and driver information",
    "get_disk_health": "Checking disk health",
    "query_registry": "Inspecting the Windows registry",
    "list_installed_apps": "Checking installed applications",
    "search_files": "Searching files",
    "get_folder_size": "Calculating folder size",
    "analyze_file_relevance": "Analyzing file information",
    "web_search": "Searching the web for information",
    "fetch_page": "Checking information from web",
    "get_approximate_location": "Checking location",
}

# Type coercion map for argument validation
TYPE_MAP = {
    "integer": int,
    "number": float,
    "string": str,
    "boolean": bool,
}


# Manages async permission requests from API calls
class PermissionManager:
    def __init__(self):
        self.pending = {}
    
    def create_request(self, conversation_id, details):
        # Create a permission request that can be resolved later
        event = threading.Event()
        self.pending[conversation_id] = {"event": event, "approved": False}
        return event
    
    def resolve(self, conversation_id, approved):
        # Resolve a pending permission request
        req = self.pending.get(conversation_id)
        if req:
            req["approved"] = approved
            req["event"].set()
            return True
        return False
    
    def get_approval(self, conversation_id):
        # Check if permission was approved
        return self.pending.get(conversation_id, {}).get("approved", False)
    
    def cleanup(self, conversation_id):
        # Remove resolved permission request
        self.pending.pop(conversation_id, None)


# Container for pending async permission request
class PendingPermission:
    def __init__(self, details, event):
        self.details = details
        self.event = event
        self.approved = False


permission_manager = PermissionManager()


def resolve_permission(conversation_id, approved):
    # Resolve a permission request from API endpoint
    return permission_manager.resolve(conversation_id, approved)


def _find_schema(name, schemas):
    # Find tool schema by name
    for schema in schemas:
        if schema["function"]["name"] == name:
            return schema
    return None


def validate_tool_call(name, args, registry, schemas):
    # Validate tool call name and arguments against registry and schemas
    if name not in registry:
        return False, f"unknown tool '{name}' -- not in the available tool list"
    
    schema = _find_schema(name, schemas)
    if schema is None:
        return True, args  # Proceed if schema drifts from registry
    
    params = schema["function"]["parameters"]
    properties = params.get("properties", {})
    required = params.get("required", [])
    
    # Check for missing required arguments
    missing = [p for p in required if p not in args]
    if missing:
        return False, f"missing required argument(s): {', '.join(missing)}"
    
    # Coerce types when possible
    coerced = dict(args)
    for key, value in args.items():
        expected_type = properties.get(key, {}).get("type")
        py_type = TYPE_MAP.get(expected_type)
        
        if py_type is None:
            continue
        if isinstance(value, py_type):
            continue
        
        try:
            coerced[key] = py_type(value)
        except (ValueError, TypeError):
            return False, f"argument '{key}' should be {expected_type}, got {value!r}"
    
    return True, coerced


def _format_tool_description(name, arguments):
    # Build descriptive progress message for a tool call
    message = TOOL_PROGRESS_MESSAGES.get(name, "Working")
    arguments = arguments or {}
    
    if name == "list_running_processes" and arguments.get("sort_by"):
        return f"{message} sorted by {arguments['sort_by']}"
    if name == "query_registry" and arguments.get("key_path"):
        return f"{message} at {arguments['key_path']}"
    if name == "search_files":
        pattern = arguments.get("pattern")
        root_path = arguments.get("root_path")
        if pattern and root_path:
            return f"{message} for {pattern} in {root_path}"
        if pattern:
            return f"{message} for {pattern}"
    if name == "get_folder_size" and arguments.get("path"):
        return f"{message} for {arguments['path']}"
    if name == "analyze_file_relevance" and arguments.get("path"):
        return f"{message} in {arguments['path']}"
    if name == "web_search" and arguments.get("query"):
        return f"{message} for {arguments['query']}"
    if name == "fetch_page" and arguments.get("url"):
        return f"{message} at {arguments['url']}"
    if name == "execute_powershell" and arguments.get("command"):
        timeout = arguments.get("timeout", 20)
        return f"Executing PowerShell command: '{arguments['command']}' with {timeout} seconds timeout"
    
    return message


def format_tool_progress(tool_number, name, arguments):
    # Format progress indicator with tool number and description
    return f"{tool_number}. {_format_tool_description(name, arguments)}"


def _truncate_for_terminal(text, max_chars=MAX_TERMINAL_CHARS):
    # Truncate output for terminal display
    text = str(text)
    if len(text) <= max_chars:
        return text
    remaining = len(text) - max_chars
    return text[:max_chars] + f"\n... (+{remaining} more characters, full data available to the model)"


def _summarize_gathered_results(messages):
    # Generate final summary when tool-call limit reached
    synthesis_messages = messages + [{
        "role": "user",
        "content": (
            "The tool-call limit has been reached. Answer the original user request now "
            "using only the confirmed information already gathered. State clearly what "
            "could not be verified. Do not call any tools."
        ),
    }]
    try:
        response = chat(synthesis_messages, tools=[])
    except OllamaUnavailableError:
        return None
    
    final_text = get_final_text(response)
    return final_text.strip() or None


def run_turn_core(user_input, messages, conversation_id=None, sync_confirm_callback=None):
    # Main orchestration loop: chat, extract tools, validate, get permissions, execute, annotate
    messages.append({"role": "user", "content": user_input})
    failure_counts = {}
    command_failure_counts = {}
    tool_call_counter = 0
    
    for _ in range(MAX_ITERATIONS):
        # Chat with LLM
        try:
            response = chat(messages, tools=TOOL_SCHEMAS)
        except OllamaUnavailableError as e:
            messages.pop()
            yield {"type": "error", "text": str(e)}
            return
        
        tool_calls = extract_tool_calls(response)
        
        # If no tools called, return final answer
        if not tool_calls:
            final_text = get_final_text(response)
            
            if not final_text.strip():
                yield {
                    "type": "error",
                    "text": (
                        "I gathered information but ran out of room to summarize it "
                        "(too much data from the tool results). Try asking a more "
                        "specific question, like checking one folder or location at a time."
                    ),
                }
                return
            
            messages.append({"role": "assistant", "content": final_text})
            yield {"type": "answer", "text": final_text}
            return
        
        messages.append(response["message"])
        
        # Process each tool call
        for call in tool_calls:
            name = call["name"]
            args = call["arguments"]
            tool_call_counter += 1
            
            # Emit tool start event
            yield {
                "type": "tool_started",
                "name": name,
                "args": args,
                "display": format_tool_progress(tool_call_counter, name, args),
            }
            
            # Validate tool call
            ok, validated = validate_tool_call(name, args, TOOL_REGISTRY, TOOL_SCHEMAS)
            permission_error = False
            
            if ok:
                try:
                    # Classify risk tier and handle permissions
                    tier = classify_operation(name, validated)
                    
                    if tier is not RiskTier.READ:
                        # Permission needed for modify/destructive operations
                        details = confirmation_details(name, validated, tier)
                        
                        if sync_confirm_callback:
                            # Terminal: sync callback for user approval
                            approved = sync_confirm_callback(details)
                            if not approved:
                                raise PermissionDenied(f"user declined this action:\n{details}")
                        else:
                            # API: async event-based approval flow
                            event = permission_manager.create_request(conversation_id, details)
                            
                            yield {
                                "type": "permission_requested",
                                "name": name,
                                "args": validated,
                                "details": details,
                                "tier": tier.value,
                            }
                            
                            event.wait()  # Wait for resolve_permission() call
                            
                            if not permission_manager.get_approval(conversation_id):
                                raise PermissionDenied(f"user declined this action:\n{details}")
                            
                            permission_manager.cleanup(conversation_id)
                    
                    # Execute tool
                    result = execute_tool(name, validated, TOOL_REGISTRY)
                
                except PermissionDenied as e:
                    ok = False
                    permission_error = True
                    validated = str(e)
                
                except Exception as e:
                    ok = False
                    validated = str(e)
            
            # Annotate results based on execution status
            if ok and is_execution_failure(name, result):
                command_failure_counts[name] = command_failure_counts.get(name, 0) + 1
                result = annotate_result(result, "recovery", command_failure_counts[name])
            elif ok and needs_verification(name, validated):
                result = annotate_result(result, "verification")
            
            # Build error messages if tool failed
            if not ok:
                if permission_error:
                    result = f"error: {validated}"
                else:
                    failure_counts[name] = failure_counts.get(name, 0) + 1
                    if failure_counts[name] > MAX_RETRIES:
                        result = f"error: {validated} -- giving up on '{name}' after {MAX_RETRIES} retries"
                    else:
                        result = f"error: {validated} -- please retry with corrected arguments"
            
            # Emit tool finish event
            yield {"type": "tool_finished", "name": name, "result": str(result)}
            
            # Add result to message history
            messages.append({"role": "tool", "content": str(result)})
            
            # Stop on permission denial
            if permission_error:
                yield {"type": "error", "text": "The action was not executed because confirmation was declined."}
                return
    
    # Tool limit reached - try to summarize
    final_text = _summarize_gathered_results(messages)
    
    if final_text:
        messages.append({"role": "assistant", "content": final_text})
        yield {"type": "answer", "text": final_text}
    else:
        yield {"type": "error", "text": "I gathered information but couldn't produce a final answer from it."}


def run_turn(user_input, messages, show_debug_tools=False, show_full_output=False):
    # Terminal interface: consumes events, prints progress, returns final answer
    for event in run_turn_core(user_input, messages, sync_confirm_callback=request_confirmation):
        if event["type"] == "tool_started":
            print(event["display"])
            if show_debug_tools:
                print(f"→ calling {event['name']}({event['args']})")
        
        elif event["type"] == "tool_finished":
            if show_debug_tools:
                displayed_result = (
                    event["result"]
                    if show_full_output
                    else _truncate_for_terminal(event["result"])
                )
                print(f"← result: {displayed_result}")
        
        elif event["type"] == "answer":
            return event["text"]
        
        elif event["type"] == "error":
            # Pop user input if error before processing
            if messages and messages[-1]["role"] == "user":
                messages.pop()
            # Don't add warning icon for permission messages
            if event["text"].startswith("The action was not executed"):
                return event["text"]
            return f"⚠ {event['text']}"


def run_turn_events(user_input, messages, conversation_id):
    # API interface: yields events for WebSocket streaming with async permission flow
    for event in run_turn_core(user_input, messages, conversation_id=conversation_id):
        yield event
