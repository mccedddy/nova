import winreg

# Restrict reads to the supported root hives.
ALLOWED_HIVES = {
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKEY_LOCAL_MACHINE": winreg.HKEY_LOCAL_MACHINE,
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
    "HKEY_CLASSES_ROOT": winreg.HKEY_CLASSES_ROOT,
    "HKU": winreg.HKEY_USERS,
    "HKEY_USERS": winreg.HKEY_USERS,
}

UNINSTALL_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]

MAX_VALUES = 50
MAX_SUBKEYS = 50


def query_registry(key_path):
    # The first path segment identifies the allowed root hive.
    parts = key_path.strip("\\").split("\\", 1)
    if len(parts) < 1 or parts[0].upper() not in ALLOWED_HIVES:
        return {
            "error": (
                f"Invalid or disallowed root hive in '{key_path}'. "
                f"Must start with one of: HKLM, HKCU, HKCR, HKU."
            )
        }

    hive = ALLOWED_HIVES[parts[0].upper()]
    subpath = parts[1] if len(parts) > 1 else ""

    try:
        with winreg.OpenKey(hive, subpath, 0, winreg.KEY_READ) as key:
            values = _read_values(key)
            subkeys = _read_subkeys(key)

            return {
                "key_path": key_path,
                "values": values["items"],
                "values_truncated": values["truncated"],
                "subkeys": subkeys["items"],
                "subkeys_truncated": subkeys["truncated"],
            }

    except FileNotFoundError:
        return {"error": f"Registry key not found: {key_path}"}
    except PermissionError:
        return {"error": f"Access denied reading registry key: {key_path}"}
    except OSError as e:
        return {"error": f"Failed to read registry key: {e}"}


def _read_values(key):
    items = []
    truncated = False
    i = 0
    while True:
        try:
            name, value, _ = winreg.EnumValue(key, i)
            if i < MAX_VALUES:
                items.append({"name": name or "(default)", "value": str(value)})
            else:
                truncated = True
            i += 1
        except OSError:
            break
    return {"items": items, "truncated": truncated}


def _read_subkeys(key):
    items = []
    truncated = False
    i = 0
    while True:
        try:
            name = winreg.EnumKey(key, i)
            if i < MAX_SUBKEYS:
                items.append(name)
            else:
                truncated = True
            i += 1
        except OSError:
            break
    return {"items": items, "truncated": truncated}

def list_installed_apps():
    # Include machine-wide, 32-bit, and per-user uninstall locations.
    apps = []
    errors = []

    for hive, path in UNINSTALL_PATHS:
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as uninstall_key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(uninstall_key, i)
                    except OSError:
                        break

                    app = _read_app_entry(uninstall_key, subkey_name)
                    if app:
                        apps.append(app)
                    i += 1

        except FileNotFoundError:
            continue
        except PermissionError:
            errors.append(f"Access denied reading {path}")
        except OSError as e:
            errors.append(f"Failed to read {path}: {e}")

    # Deduplicate entries that appear in multiple uninstall locations.
    seen = set()
    unique_apps = []
    for app in sorted(apps, key=lambda a: a["name"].lower()):
        key = (app["name"], app["version"])
        if key not in seen:
            seen.add(key)
            unique_apps.append(app)

    result = {"apps": unique_apps, "count": len(unique_apps)}
    if errors:
        result["errors"] = errors
    return result


def _read_app_entry(uninstall_key, subkey_name):
    try:
        with winreg.OpenKey(uninstall_key, subkey_name, 0, winreg.KEY_READ) as app_key:
            name = _get_value(app_key, "DisplayName")
            if not name:
                return None

            return {
                "name": name,
                "version": _get_value(app_key, "DisplayVersion") or "unknown",
                "publisher": _get_value(app_key, "Publisher") or "unknown",
                "install_date": _get_value(app_key, "InstallDate") or "unknown",
            }
    except OSError:
        return None


def _get_value(key, name):
    try:
        value, _ = winreg.QueryValueEx(key, name)
        return value
    except FileNotFoundError:
        return None