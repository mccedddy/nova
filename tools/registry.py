import winreg

# only these root hives are allowed -- registry keys can be huge or
# sensitive, so we don't let the model wander outside known-safe roots
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

MAX_VALUES = 50
MAX_SUBKEYS = 50


def query_registry(key_path):
    # key_path expected like "HKLM\Software\Microsoft\Windows" or
    # "HKCU\Software\..." -- first segment must be an allowed hive
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
            break  # no more values
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
            break  # no more subkeys
    return {"items": items, "truncated": truncated}