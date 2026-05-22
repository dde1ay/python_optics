from __future__ import annotations

import os
import sys
import winreg
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ZemaxConnection:
    zosapi: Any
    application: Any
    system: Any
    zemax_dir: str


def find_zemax_root() -> str:
    registry_locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Zemax"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Zemax"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Zemax"),
    ]
    for hive, subkey in registry_locations:
        key = None
        try:
            key = winreg.OpenKey(winreg.ConnectRegistry(None, hive), subkey, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, "ZemaxRoot")
            net_helper = os.path.join(value, r"ZOS-API\Libraries\ZOSAPI_NetHelper.dll")
            if os.path.exists(net_helper):
                return value
        except FileNotFoundError:
            pass
        finally:
            if key is not None:
                winreg.CloseKey(key)

    user_profile = os.environ.get("USERPROFILE", "")
    candidates = [
        os.path.join(user_profile, "Documents", "Zemax"),
        os.path.join(user_profile, "Documents", "Ansys Zemax"),
        r"C:\Users\Public\Documents\Zemax",
        r"C:\ProgramData\Zemax",
    ]
    for candidate in candidates:
        net_helper = os.path.join(candidate, r"ZOS-API\Libraries\ZOSAPI_NetHelper.dll")
        if os.path.exists(net_helper):
            return candidate

    raise FileNotFoundError(
        "Cannot find ZemaxRoot or ZOSAPI_NetHelper.dll. "
        f"Searched registry keys {[path for _, path in registry_locations]} and {candidates}"
    )


def load_zosapi(path_to_install: str = "") -> tuple[Any, str]:
    try:
        import clr
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing pythonnet module. Install it with 'python -m pip install pythonnet' "
            f"using the same Python executable: {sys.executable}"
        ) from exc

    zemax_root = find_zemax_root()
    net_helper = os.path.join(zemax_root, r"ZOS-API\Libraries\ZOSAPI_NetHelper.dll")
    if not os.path.exists(net_helper):
        raise FileNotFoundError(f"ZOSAPI_NetHelper.dll not found: {net_helper}")

    clr.AddReference(net_helper)
    import ZOSAPI_NetHelper  # type: ignore

    if not ZOSAPI_NetHelper.ZOSAPI_Initializer.Initialize(path_to_install):
        raise RuntimeError("Cannot find OpticStudio. Verify the OpticStudio installation.")

    zemax_dir = ZOSAPI_NetHelper.ZOSAPI_Initializer.GetZemaxDirectory()
    for dll_name in ("ZOSAPI.dll", "ZOSAPI_Interfaces.dll"):
        dll_path = os.path.join(zemax_dir, dll_name)
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"Expected ZOSAPI assembly not found: {dll_path}")
        clr.AddReference(dll_path)

    import ZOSAPI  # type: ignore

    return ZOSAPI, zemax_dir


def connect_opticstudio(standalone: bool = False, instance: int = 0, path_to_install: str = "") -> ZemaxConnection:
    zosapi, zemax_dir = load_zosapi(path_to_install)
    connection = zosapi.ZOSAPI_Connection()
    if connection is None:
        raise RuntimeError("Unable to initialize .NET connection to ZOSAPI.")

    if standalone:
        application = connection.CreateNewApplication()
    else:
        application = connection.ConnectAsExtension(instance)
    if application is None:
        mode = "standalone application" if standalone else "Interactive Extension"
        raise RuntimeError(f"Unable to acquire ZOSAPI application via {mode}.")

    if not application.IsValidLicenseForAPI:
        raise RuntimeError(
            "License is not valid for ZOSAPI use. For extension mode, enable "
            "'Programming > Interactive Extension' in OpticStudio."
        )

    system = application.PrimarySystem
    if system is None:
        raise RuntimeError("Unable to acquire PrimarySystem.")

    print(f"Found OpticStudio at: {zemax_dir}")
    print("Connected to OpticStudio")
    print("Serial #:", application.SerialCode)
    return ZemaxConnection(zosapi=zosapi, application=application, system=system, zemax_dir=zemax_dir)


def ensure_output_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

