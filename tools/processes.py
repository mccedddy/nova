import psutil


def list_running_processes(limit=30, sort_by="memory"):
    # sort_by: "memory" (default) or "name"
    processes = []

    for proc in psutil.process_iter(["pid", "name", "memory_info", "exe"]):
        try:
            info = proc.info
            mem_bytes = info["memory_info"].rss if info["memory_info"] else 0
            processes.append({
                "pid": info["pid"],
                "name": info["name"],
                "memory_mb": round(mem_bytes / (1024 ** 2), 2),
                "exe_path": info["exe"] or "unknown",
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # process exited mid-scan, or we don't have permission to read
            # it (common for system/other-user processes) -- skip silently,
            # this isn't a real error, just an expected gap
            continue

    if sort_by == "name":
        processes.sort(key=lambda p: p["name"].lower())
    else:
        processes.sort(key=lambda p: p["memory_mb"], reverse=True)

    total_count = len(processes)
    truncated = processes[:limit]

    return {
        "processes": truncated,
        "shown": len(truncated),
        "total_running": total_count,
        "truncated": total_count > limit,
    }