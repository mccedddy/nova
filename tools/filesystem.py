import subprocess
import json
import os
import time
from datetime import datetime

# Path fragments used to report temp/cache signals.
TEMP_CACHE_PATTERNS = [
    r"\appdata\local\temp",
    r"\temp",
    r"\cache",
    r"\crashdumps",
    r"\appdata\local\microsoft\windows\inetcache",
    r"\appdata\local\google\chrome\user data\default\cache",
    r"\appdata\local\bravesoftware\brave-browser\user data\default\cache",
]

DEFAULT_TIMEOUT = 20
MAX_RESULTS = 40


def search_files(pattern, root_path=None):
    # Default roots avoid an unexpectedly expensive full-drive search.
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
    # PowerShell handles recursive Windows file enumeration efficiently.
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

def get_folder_size(path):
    # Use a time budget because recursive scans can be expensive.
    if not os.path.exists(path):
        return {"error": f"Path does not exist: {path}"}

    start_time = time.time()

    total = _get_total_size(path, DEFAULT_TIMEOUT)
    if total is None:
        return {"error": f"Timed out calculating size for {path}"}

    remaining_time = max(DEFAULT_TIMEOUT - (time.time() - start_time), 5)
    largest_items = _get_largest_items(path, remaining_time)

    return {
        "path": path,
        "total_size_gb": round(total / (1024 ** 3), 2),
        "largest_items": largest_items["items"],
        "largest_items_truncated_by_time": largest_items["truncated_by_time"],
    }


def _get_total_size(path, timeout):
    ps_command = (
        f"(Get-ChildItem -Path '{path}' -Recurse -File "
        f"-ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum"
    )
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None

    output = result.stdout.strip()
    if not output:
        return 0
    try:
        return int(float(output))
    except ValueError:
        return 0


def _get_largest_items(path, timeout):
    # Report the largest immediate entries to keep the result compact.
    ps_command = (
        f"Get-ChildItem -Path '{path}' -ErrorAction SilentlyContinue | "
        f"ForEach-Object {{ "
        f"  if ($_.PSIsContainer) {{ "
        f"    $size = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | "
        f"      Measure-Object -Property Length -Sum).Sum; "
        f"    [PSCustomObject]@{{ Name=$_.FullName; SizeBytes=$size; IsFolder=$true }} "
        f"  }} else {{ "
        f"    [PSCustomObject]@{{ Name=$_.FullName; SizeBytes=$_.Length; IsFolder=$false }} "
        f"  }} "
        f"}} | Sort-Object SizeBytes -Descending | Select-Object -First 10 | ConvertTo-Json"
    )

    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"items": [], "truncated_by_time": True}

    if result.returncode != 0 or not result.stdout.strip():
        return {"items": [], "truncated_by_time": False}

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"items": [], "truncated_by_time": False}

    if isinstance(data, dict):
        data = [data]

    items = []
    for entry in data:
        size_bytes = entry.get("SizeBytes") or 0
        items.append({
            "path": entry.get("Name", "unknown"),
            "type": "folder" if entry.get("IsFolder") else "file",
            "size_gb": round(size_bytes / (1024 ** 3), 3),
        })

    return {"items": items, "truncated_by_time": False}

def analyze_file_relevance(path):
    if not os.path.exists(path):
        return {"error": f"Path does not exist: {path}"}

    try:
        stat = os.stat(path)
    except OSError as e:
        return {"error": f"Failed to read file info: {e}"}

    last_accessed = datetime.fromtimestamp(stat.st_atime)
    last_modified = datetime.fromtimestamp(stat.st_mtime)
    now = datetime.now()

    path_lower = path.lower()
    in_temp_cache_path = any(pattern in path_lower for pattern in TEMP_CACHE_PATTERNS)

    locked = _check_if_locked(path)

    return {
        "path": path,
        "days_since_accessed": (now - last_accessed).days,
        "days_since_modified": (now - last_modified).days,
        "in_temp_or_cache_path": in_temp_cache_path,
        "appears_locked_by_another_process": locked,
        "size_mb": round(stat.st_size / (1024 ** 2), 3) if os.path.isfile(path) else "n/a (folder)",
    }


def _check_if_locked(path):
    # An exclusive open is a useful signal, but cannot identify the locking process.
    if os.path.isdir(path):
        return "n/a (folder)"

    try:
        with open(path, "r+b"):
            pass
        return False
    except PermissionError:
        return True
    except OSError:
        return "unknown"  # e.g. file vanished between the exists check and here