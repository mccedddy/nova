import psutil


def list_running_processes(limit=30, sort_by="memory"):
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
            # Processes can exit or become inaccessible during enumeration.
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
    # Network enumeration may require Administrator privileges on Windows.
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

    # Put active connections before listening sockets.
    results.sort(key=lambda c: c["status"] != "ESTABLISHED")

    total_count = len(results)
    limit = min(limit, 40)
    truncated = results[:limit]

    return {
        "connections": truncated,
        "shown": len(truncated),
        "total_connections": total_count,
        "truncated": total_count > limit,
    }