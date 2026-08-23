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

def get_network_connections(limit=30):
    # netstat-style: local/remote address, port, owning process.
    # psutil.net_connections() often needs admin rights on Windows --
    # if it's denied, report that clearly instead of crashing, per the
    # plan's explicit warning about this tool.
    try:
        conns = psutil.net_connections(kind="inet")
    except psutil.AccessDenied:
        return {
            "error": "Access denied -- this requires running as Administrator.",
            "connections": [],
        }
    except Exception as e:
        return {"error": f"Failed to read network connections: {e}", "connections": []}

    results = []
    for conn in conns:
        try:
            proc_name = psutil.Process(conn.pid).name() if conn.pid else "unknown"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc_name = "unknown"

        results.append({
            "pid": conn.pid,
            "process_name": proc_name,
            "status": conn.status,
            "local_address": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "unknown",
            "remote_address": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "none",
        })

    # prioritize established connections (more likely what someone's
    # asking about -- "what's using my network") over listening sockets
    results.sort(key=lambda c: c["status"] != "ESTABLISHED")

    total_count = len(results)
    limit = min(limit, 40)  # same context-window safety cap as processes
    truncated = results[:limit]

    return {
        "connections": truncated,
        "shown": len(truncated),
        "total_connections": total_count,
        "truncated": total_count > limit,
    }