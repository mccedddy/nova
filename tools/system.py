import subprocess
import json
import psutil
from datetime import datetime, timedelta


def get_system_diagnostics():
    cpu = _get_cpu_info()
    ram = _get_ram_info()
    disks = _get_disk_info()
    os_info = _get_os_info()

    return {
        "cpu": cpu,
        "ram": ram,
        "disks": disks,
        "os": os_info,
    }


def _get_cpu_info():
    return {
        "usage_percent": psutil.cpu_percent(interval=0.5),
        "core_count_physical": psutil.cpu_count(logical=False),
        "core_count_logical": psutil.cpu_count(logical=True),
    }


def _get_ram_info():
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024 ** 3), 2),
        "used_gb": round(mem.used / (1024 ** 3), 2),
        "percent_used": mem.percent,
    }


def _get_disk_info():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except PermissionError:
            continue  # skip drives we can't read (e.g. empty CD drive)
        disks.append({
            "drive": part.device,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "percent_used": usage.percent,
        })
    return disks


def _get_os_info():
    # psutil doesn't give OS build/version directly -- pull that via
    # PowerShell instead, with a timeout in case it hangs
    try:
        result = subprocess.run(
            [
                "powershell", "-Command",
                "Get-CimInstance Win32_OperatingSystem | "
                "Select-Object Caption, Version, BuildNumber, LastBootUpTime | "
                "ConvertTo-Json"
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return {"error": f"PowerShell call failed: {result.stderr.strip()}"}

        data = json.loads(result.stdout)

        uptime = "unknown"
        last_boot_raw = data.get("LastBootUpTime")
        if last_boot_raw:
            # WMI dates come back as .NET JSON date format: /Date(1699999999000)/
            try:
                millis = int(last_boot_raw.strip("/Date()"))
                boot_time = datetime.fromtimestamp(millis / 1000)
                delta = datetime.now() - boot_time
                uptime = str(timedelta(seconds=int(delta.total_seconds())))
            except (ValueError, TypeError):
                pass

        return {
            "name": data.get("Caption", "unknown"),
            "version": data.get("Version", "unknown"),
            "build": data.get("BuildNumber", "unknown"),
            "uptime": uptime,
        }

    except subprocess.TimeoutExpired:
        return {"error": "PowerShell call timed out"}
    except (json.JSONDecodeError, Exception) as e:
        return {"error": f"failed to parse OS info: {e}"}

def get_gpu_driver_info():
    gpus = _get_gpu_info_wmi()
    nvidia_info = _try_nvidia_smi()

    if nvidia_info:
        for gpu in gpus:
            if "nvidia" in gpu["name"].lower():
                gpu["driver_version_nvidia_smi"] = nvidia_info.get("driver_version")
                gpu["vram_gb"] = nvidia_info.get("vram_gb", gpu["vram_gb"])  # override the unreliable WMI value

    return {"gpus": gpus}

def _get_gpu_info_wmi():
    try:
        result = subprocess.run(
            [
                "powershell", "-Command",
                "Get-CimInstance Win32_VideoController | "
                "Select-Object Name, DriverVersion, DriverDate, AdapterRAM | "
                "ConvertTo-Json"
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return [{"error": f"PowerShell call failed: {result.stderr.strip()}"}]

        data = json.loads(result.stdout)
        # WMI returns a single dict if there's only one GPU, or a list if
        # there are multiple -- normalize to always be a list
        if isinstance(data, dict):
            data = [data]

        gpus = []
        for entry in data:
            ram_bytes = entry.get("AdapterRAM")
            gpus.append({
                "name": entry.get("Name", "unknown"),
                "driver_version": entry.get("DriverVersion", "unknown"),
                "driver_date": entry.get("DriverDate", "unknown"),
                "vram_gb": round(ram_bytes / (1024 ** 3), 2) if ram_bytes else "unknown",
            })
        return gpus

    except subprocess.TimeoutExpired:
        return [{"error": "PowerShell call timed out"}]
    except (json.JSONDecodeError, Exception) as e:
        return [{"error": f"failed to parse GPU info: {e}"}]


def _try_nvidia_smi():
    # not all systems have an NVIDIA GPU / nvidia-smi installed -- this
    # is optional, silently return None if it's not available
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return {"driver_version": result.stdout.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

def _try_nvidia_smi():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version,memory.total",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip()
        driver_version, vram_mb = [p.strip() for p in line.split(",")]
        return {
            "driver_version": driver_version,
            "vram_gb": round(float(vram_mb) / 1024, 2),
        }
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None

def get_disk_health():
    try:
        result = subprocess.run(
            [
                "powershell", "-Command",
                "Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, "
                "MediaType, HealthStatus, OperationalStatus, Size | "
                "ConvertTo-Json"
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "access" in stderr.lower() or "denied" in stderr.lower():
                return {
                    "error": "Access denied -- disk health checks require running as Administrator."
                }
            return {"error": f"PowerShell call failed: {stderr}"}

        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]

        disks = []
        for entry in data:
            size_bytes = entry.get("Size")
            disks.append({
                "device_id": entry.get("DeviceId", "unknown"),
                "name": entry.get("FriendlyName", "unknown"),
                "media_type": entry.get("MediaType", "unknown"),  # SSD/HDD
                "health_status": entry.get("HealthStatus", "unknown"),
                "operational_status": entry.get("OperationalStatus", "unknown"),
                "size_gb": round(size_bytes / (1024 ** 3), 2) if size_bytes else "unknown",
            })

        return {"disks": disks}

    except subprocess.TimeoutExpired:
        return {"error": "PowerShell call timed out"}
    except (json.JSONDecodeError, Exception) as e:
        return {"error": f"failed to parse disk health info: {e}"}