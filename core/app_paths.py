import os
import sys


def _looks_like_data_root(path):
    if not path or not os.path.isdir(path):
        return False
    markers = ("keyboxes", "firmwares", "rkp_factory_extraction_tool", "csrs")
    for marker in markers:
        if os.path.exists(os.path.join(path, marker)):
            return True
    return False


def _iter_candidate_roots():
    env_root = os.environ.get("KEYS_FLASHER_ROOT")
    if env_root:
        yield env_root

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield meipass

    exe_dir = None
    try:
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    except Exception:
        exe_dir = None

    if exe_dir:
        yield exe_dir
        yield os.path.dirname(exe_dir)

    yield os.getcwd()
    yield os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    yield "/usr/share/keys_flasher"


def get_data_root():
    env_data = os.environ.get("KEYS_FLASHER_DATA_ROOT")
    if env_data:
        return os.path.abspath(env_data)

    for root in _iter_candidate_roots():
        if not root:
            continue
        data_dir = os.path.join(root, "data")
        if _looks_like_data_root(data_dir):
            return os.path.abspath(data_dir)
        if _looks_like_data_root(root):
            return os.path.abspath(root)

    env_root = os.environ.get("KEYS_FLASHER_ROOT")
    if env_root:
        return os.path.abspath(os.path.join(env_root, "data"))

    return os.path.abspath(os.path.join(os.getcwd(), "data"))


def get_app_root():
    env_root = os.environ.get("KEYS_FLASHER_ROOT")
    if env_root:
        return os.path.abspath(env_root)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return os.path.abspath(meipass)

    for root in _iter_candidate_roots():
        if not root:
            continue
        if os.path.exists(os.path.join(root, "app_icon.ico")) or os.path.exists(os.path.join(root, "aio.png")):
            return os.path.abspath(root)

    return os.path.abspath(os.path.join(get_data_root(), ".."))
