import glob
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

def run(cmd, input_text=None):
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        input=input_text,
    )
    return result.stdout.strip()

def stream_cmd(cmd, log_callback, is_aborted=None, fail_str=None):
    """Run an ADB command and stream the output line by line dynamically.
    Checks is_aborted() periodically to terminate early, and aborts if `fail_str` is detected."""
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
    
    import select
    while True:
        if is_aborted and is_aborted():
            process.terminate()
            log_callback("⚠️ Process aborted by user.")
            return -1
            
        reads, _, _ = select.select([process.stdout], [], [], 0.1)
        if process.stdout in reads:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                log_callback(line.strip())
                if fail_str and fail_str in line:
                    process.terminate()
                    log_callback(f"❌ FATAL ERROR: Detected failure string '{fail_str}' in output!")
                    return -2
        elif process.poll() is not None:
            break
            
    return process.returncode

def get_all_device_serials():
    out = run("adb devices")
    lines = out.splitlines()
    serials = []
    for line in lines:
        if "device" in line and not line.startswith("List"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
    return serials

def get_adb_devices_with_usb():
    out = run("adb devices -l")
    devices = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        if state != "device":
            continue
        usb_path = None
        for part in parts[2:]:
            if part.startswith("usb:"):
                usb_path = part.replace("usb:", "", 1)
                break
        devices.append({"serial": serial, "usb": usb_path})
    return devices

def get_all_edl_serials():
    out = run("qdl list")
    logger.debug(f"[EDL] raw `qdl list` output: {out!r}")
    serials = []
    for line in out.splitlines():
        parts = line.strip().split()
        logger.debug(f"[EDL] line={line!r}  parts={parts}")
        if len(parts) >= 2 and ":" in parts[0]:
            serial = parts[1].strip()
            logger.debug(f"[EDL] matched serial={serial!r}")
            if serial and serial not in serials:
                serials.append(serial)
    logger.debug(f"[EDL] final serials={serials}")
    return serials

_hw_serial_cache = {}

_TRANSIENT_DEVICE_VALUE_MARKERS = (
    "error:",
    "device offline",
    "no devices/emulators found",
    "waiting for device",
    "unauthorized",
    "can't find service",
    "transport",
    "not found",
    "daemon not running",
)

def _safe_int(value, default=None):
    try:
        return int(str(value).strip())
    except Exception:
        return default

def _resolve_usb_path(busnum, devnum):
    for entry in glob.glob("/sys/bus/usb/devices/*"):
        bus_path = os.path.join(entry, "busnum")
        dev_path = os.path.join(entry, "devnum")
        if not os.path.exists(bus_path) or not os.path.exists(dev_path):
            continue
        try:
            with open(bus_path, "r", encoding="utf-8") as bf:
                b = _safe_int(bf.read())
            with open(dev_path, "r", encoding="utf-8") as df:
                d = _safe_int(df.read())
        except Exception:
            continue
        if b == busnum and d == devnum:
            return os.path.basename(entry)
    return None

def _read_sysfs_value(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return None

def _read_sysfs_int(path):
    value = _read_sysfs_value(path)
    return _safe_int(value)

def _get_hw_serial_from_sysfs_path(sysfs_path):
    cache_key = str(sysfs_path)
    devnum = _read_sysfs_int(Path(sysfs_path) / "devnum")
    cached = _hw_serial_cache.get(cache_key)
    if cached and cached.get("devnum") == devnum:
        return cached.get("serial")

    product = _read_sysfs_value(Path(sysfs_path) / "product")
    if product:
        match = re.search(r"_SN:([0-9a-fA-F]+)", product)
        if match:
            serial = match.group(1)
            _hw_serial_cache[cache_key] = {"devnum": devnum, "serial": serial}
            return serial

    serial = _read_sysfs_value(Path(sysfs_path) / "serial")
    if serial:
        _hw_serial_cache[cache_key] = {"devnum": devnum, "serial": serial}
        return serial

    return None

def get_usb_hw_serial_map():
    usb_map = {}
    root = Path("/sys/bus/usb/devices")
    if not root.exists():
        return usb_map
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith("usb"):
            continue
        hw_serial = _get_hw_serial_from_sysfs_path(entry)
        if hw_serial:
            usb_map[name] = hw_serial
    return usb_map

def clean_device_value(value):
    text = str(value or "").strip()
    lower = text.lower()
    if not text or lower in {"unknown", "n/a", "none", "null"}:
        return ""
    if any(marker in lower for marker in _TRANSIENT_DEVICE_VALUE_MARKERS):
        return ""
    return text

def get_device_property(serial, prop_name):
    if not serial or not prop_name:
        return ""
    return clean_device_value(run(f"adb -s {serial} shell getprop {prop_name}"))

def get_device_sw_serial(serial):
    for prop_name in (
        "ro.serialno",
        "ro.boot.serialno",
        "persist.sys.serialno",
        "persist.vendor.serialno",
    ):
        value = get_device_property(serial, prop_name)
        if value:
            return value
    return ""

def resolve_aio_serial(adb_serial=None, sw_serial=None, extra_candidates=None):
    candidates = [adb_serial, sw_serial]
    if extra_candidates:
        candidates.extend(extra_candidates)

    fallback = ""
    for candidate in candidates:
        value = clean_device_value(candidate)
        if len(value) != 14:
            continue
        if value.startswith("AT070AA"):
            return value
        if not fallback:
            fallback = value
    return fallback

def build_device_identity(adb_serial, usb_path=None, usb_hw_map=None, sw_serial=None):
    usb_hw_map = usb_hw_map if usb_hw_map is not None else get_usb_hw_serial_map()
    adb_value = clean_device_value(adb_serial)

    if usb_path is None and adb_value:
        serial_to_usb = {entry.get("serial"): entry.get("usb") for entry in get_adb_devices_with_usb()}
        usb_path = serial_to_usb.get(adb_value)

    hw_value = ""
    if usb_path:
        hw_value = clean_device_value(usb_hw_map.get(usb_path))

    # Production rule from the line: AIO serial and SW serial are the ADB serial.
    sw_value = adb_value or clean_device_value(sw_serial) or get_device_sw_serial(adb_serial)
    aio_value = adb_value or resolve_aio_serial(adb_value, sw_value)

    return {
        "adb_serial": adb_value or "n/a",
        "usb_path": clean_device_value(usb_path) or "n/a",
        "hw_serial": hw_value or "n/a",
        "sw_serial": sw_value or "n/a",
        "aio_serial": aio_value or "n/a",
    }

def get_usb_hardware_inventory():
    out = run("lsusb")
    if "lsusb" in out.lower() and "not found" in out.lower():
        return []

    devices = []
    for line in out.splitlines():
        match = re.search(r"Bus\\s+(\\d+)\\s+Device\\s+(\\d+):\\s+ID\\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", line)
        if not match:
            continue
        busnum = _safe_int(match.group(1))
        devnum = _safe_int(match.group(2))
        if busnum is None or devnum is None:
            continue

        hw_sn = None
        sn_match = re.search(r"_SN:([0-9a-fA-F]+)", line)
        if sn_match:
            hw_sn = sn_match.group(1)
        else:
            verbose = run(f"lsusb -v -s {busnum:03d}:{devnum:03d} 2>/dev/null")
            sn_match = re.search(r"_SN:([0-9a-fA-F]+)", verbose)
            if sn_match:
                hw_sn = sn_match.group(1)

        devices.append(
            {
                "busnum": busnum,
                "devnum": devnum,
                "vendor_id": match.group(3),
                "product_id": match.group(4),
                "usb_path": _resolve_usb_path(busnum, devnum),
                "hw_sn": hw_sn,
            }
        )
    return devices

def get_device_serial():
    serials = get_all_device_serials()
    return serials[0] if serials else None

def check_secure_boot(serial=None):
    cmd = "adb shell getprop ro.boot.verifiedbootstate"
    if serial:
        cmd = f"adb -s {serial} shell getprop ro.boot.verifiedbootstate"
    out = run(cmd)
    return out.strip()
