import os
from core.adb_utils import stream_cmd, run
from core.app_paths import get_data_root

DATA_ROOT = get_data_root()


def _save_csr_error(serial, log_callback, error_message, output=None, is_aborted=None):
    if is_aborted and is_aborted():
        return

    lines = []
    if error_message:
        lines.append(error_message.strip())
    if output:
        lines.append("--- TOOL OUTPUT ---")
        lines.append(output.strip())
    error_text = "\n".join([line for line in lines if line]).strip() + "\n"

    device_error_path = f"/data/csr_error_{serial}.txt"
    log_callback(f"Saving CSR error log on device: {device_error_path}")
    run(f'adb -s {serial} shell "cat > {device_error_path}"', input_text=error_text)

    host_error_dir = os.path.join(DATA_ROOT, "errors")
    os.makedirs(host_error_dir, exist_ok=True)
    host_error_path = os.path.join(host_error_dir, f"csr_error_{serial}.txt")
    log_callback("Pulling CSR error log to PC...")
    pull_ret = stream_cmd(f"adb -s {serial} pull {device_error_path} {host_error_path}", log_callback, is_aborted)
    if pull_ret != 0:
        log_callback("❌ Failed to pull CSR error log to PC.")
    else:
        log_callback(f"✅ CSR error log saved to: {host_error_path}")

def generate_csr(serial, log_callback, is_aborted=None):
    if is_aborted and is_aborted(): return False, "Process aborted."
    
    # 1. Pre-check device connectivity
    from core.adb_utils import get_all_device_serials
    if serial not in get_all_device_serials():
        log_callback(f"❌ ERROR: Device {serial} not detected via ADB!")
        return False, f"ADB: device {serial} not found. Please check connection."
    
    log_callback(f"Checking Root for {serial}...")
    run(f"adb -s {serial} root")
    
    # 2. Check for tool on PC
    log_callback("Pushing rkp_factory_extraction_tool to device...")
    rkp_tool_path = os.path.join(DATA_ROOT, "rkp_factory_extraction_tool")
    if not os.path.exists(rkp_tool_path):
        log_callback(f"❌ ERROR: {rkp_tool_path} not found on local PC!")
        return False, "Missing Tool: rkp_factory_extraction_tool is missing."
        
    ret = stream_cmd(f"adb -s {serial} push {rkp_tool_path} /data/", log_callback, is_aborted)
    if ret != 0:
        return False, f"Failed to push tool to {serial}."
    
    if is_aborted and is_aborted(): return False, "Process aborted."
    
    log_callback("Setting permissions...")
    run(f"adb -s {serial} shell chmod +x /data/rkp_factory_extraction_tool")
    run(f"adb -s {serial} shell setenforce 0")
    
    if is_aborted and is_aborted(): return False, "Process aborted."
    
    # 3. Execute CSR Generation on device
    log_callback("Executing CSR Generation on device...")
    cmd = f'adb -s {serial} shell "cd /data && ./rkp_factory_extraction_tool --output_format build+csr > csr_{serial}.json 2>&1"'
    ret = stream_cmd(cmd, log_callback, is_aborted)
    
    if is_aborted and is_aborted(): return False, "Process aborted."
    
    # Read the output file from the device to check for errors
    output = run(f'adb -s {serial} shell "cat /data/csr_{serial}.json"')
    
    if "Attestation IDs are missing or malprovisioned" in output:
        log_callback("❌ ERROR: Device is missing Attestation IDs.")
        msg = "Device Error: Attestation IDs are missing or malprovisioned."
        _save_csr_error(serial, log_callback, msg, output, is_aborted)
        return False, msg
    
    if "Unable to build CSR" in output or "error" in output.lower():
        log_callback(f"❌ ERROR encountered in tool output.")
        msg = "Extraction Error in tool output."
        _save_csr_error(serial, log_callback, msg, output, is_aborted)
        return False, msg

    if ret != 0:
        msg = f"CSR Generation tool failed with exit code {ret}."
        log_callback(f"❌ ERROR: {msg}")
        _save_csr_error(serial, log_callback, msg, output, is_aborted)
        return False, msg

    # 4. Pull result
    dest_path = os.path.join(DATA_ROOT, "csrs", f"csr_{serial}.json")
    log_callback(f"Pulling CSR to PC...")
    ret = stream_cmd(f"adb -s {serial} pull /data/csr_{serial}.json {dest_path}", log_callback, is_aborted)
    
    if is_aborted and is_aborted(): return False, "Process aborted."
    
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        log_callback(f"✅ CSR Successfully Saved: {os.path.basename(dest_path)}\n")
        return True, "CSR Extracted successfully!"
    else:
        log_callback("❌ Failed to pull CSR.")
        return False, "Pull Failed."
