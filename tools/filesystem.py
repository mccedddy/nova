import subprocess
import json
import os
import time

DEFAULT_TIMEOUT = 20  # seconds -- hard cap so a huge search can't hang forever
MAX_RESULTS = 100


def search_files(pattern, root_path=None):
    # if no root given, search common locations rather than the whole C:
    # drive (slow last resort, per the plan) -- model must explicitly pass
    # root_path="C:\\" if it wants a full-drive search
    roots = [root_path] if root_path else _default_roots()

    all_matches = []
    truncated_by_time = False
    truncated_by_count = False
    start_time = time.time()

    for root in roots:
        if time.time() - start_time > DEFAULT_TIMEOUT:
            truncated_by_time = True
            break

        remaining_time = DEFAULT_TIMEOUT - (time.time() - start_time)
        matches, hit_time_limit = _search_one_root(root, pattern, remaining_time)
        all_matches.extend(matches)

        if hit_time_limit:
            truncated_by_time = True

        if len(all_matches) >= MAX_RESULTS:
            truncated_by_count = True
            all_matches = all_matches[:MAX_RESULTS]
            break

    return {
        "pattern": pattern,
        "roots_searched": roots,
        "matches": all_matches,
        "count": len(all_matches),
        "truncated_by_time": truncated_by_time,
        "truncated_by_count": truncated_by_count,
    }


def _default_roots():
    user_profile = os.environ.get("USERPROFILE", r"C:\Users")
    return [
        user_profile,
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]


def _search_one_root(root, pattern, timeout):
    # uses PowerShell's Get-ChildItem -Recurse, generally faster than
    # Python's os.walk for large directory trees on Windows
    if not os.path.exists(root):
        return [], False

    ps_command = (
        f"Get-ChildItem -Path '{root}' -Recurse -Filter '{pattern}' "
        f"-ErrorAction SilentlyContinue -File | "
        f"Select-Object -First {MAX_RESULTS} FullName, Length | "
        f"ConvertTo-Json"
    )

    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [], True

    if result.returncode != 0 or not result.stdout.strip():
        return [], False

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [], False

    if isinstance(data, dict):
        data = [data]

    matches = []
    for entry in data:
        size_bytes = entry.get("Length")
        matches.append({
            "path": entry.get("FullName", "unknown"),
            "size_mb": round(size_bytes / (1024 ** 2), 2) if size_bytes else "unknown",
        })

    return matches, False