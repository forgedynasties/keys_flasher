import json
import os
import datetime
from core.app_paths import get_data_root

DATA_ROOT = get_data_root()

def save_metadata(serial, status, details=None):
    """Saves process result metadata to data_root/meta_data/<serial>.json."""
    directory = os.path.join(DATA_ROOT, "meta_data")
    os.makedirs(directory, exist_ok=True)
    
    data = {
        "serial": serial,
        "status": "PASS" if status else "FAIL",
        "timestamp": datetime.datetime.now().isoformat(),
        "details": details or {}
    }
    
    file_path = os.path.join(directory, f"{serial}.json")
    try:
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving metadata for {serial}: {e}")
        return False

def generate_session_report(results):
    """
    Generates a formatted summary report for the UI logs.
    'results' is a list of dicts: {'serial': str, 'success': bool, 'message': str}
    """
    report = "\n" + "="*40 + "\n"
    report += "       MULTI-DEVICE SESSION REPORT\n"
    report += "="*40 + "\n"
    report += f"Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    report += "-"*40 + "\n"
    
    passed = 0
    failed = 0
    
    for r in results:
        status_str = "✅ PASS" if r['success'] else "❌ FAIL"
        if r['success']: passed += 1
        else: failed += 1
        aio_serial = r.get("aio_serial") or r.get("serial", "n/a")
        hw_serial = r.get("hw_serial") or "n/a"
        sw_serial = r.get("sw_serial") or "n/a"
        report += (
            f"AIO: {aio_serial:14} | HW: {hw_serial:12} | "
            f"SW: {sw_serial:14} | {status_str} | {r.get('message', '')}\n"
        )
    
    report += "-"*40 + "\n"
    report += f"TOTAL: {len(results)} | PASSED: {passed} | FAILED: {failed}\n"
    report += "="*40 + "\n"
    
    return report
