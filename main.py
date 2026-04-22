import sys
import os
from PyQt5.QtWidgets import QApplication

# Ensure python path includes our packages
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from gui.main_window import MainWindow

def main():
    startup_message = None
    data_root = os.environ.get("KEYS_FLASHER_DATA_ROOT")
    if not data_root:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop", "KeysFlasherData")
        subdirs = [
            os.path.join("firmwares", "user"),
            "keyboxes", "csrs", "logs", "errors", "meta_data",
        ]
        for d in subdirs:
            os.makedirs(os.path.join(desktop, d), exist_ok=True)
        os.environ["KEYS_FLASHER_DATA_ROOT"] = desktop
        data_root = desktop
        startup_message = (
            f"Data directory created at:\n{desktop}\n\n"
            f"Fill these folders before flashing:\n"
            f"  {desktop}/firmwares/user/   ← firmware files (qdl runs here)\n"
            f"  {desktop}/keyboxes/         ← keybox files"
        )
        print(f"[INFO] KEYS_FLASHER_DATA_ROOT not set. Created data directory at:", flush=True)
        print(f"       {desktop}", flush=True)
        print("", flush=True)
        print("  Fill these folders before flashing:", flush=True)
        print(f"    {desktop}/firmwares/user/   <-- firmware files (qdl runs here)", flush=True)
        print(f"    {desktop}/keyboxes/         <-- keybox files", flush=True)
        print("", flush=True)

    print(f"[ENV] KEYS_FLASHER_DATA_ROOT={data_root}", flush=True)

    rkp_tool_path = os.path.join(data_root, "rkp_factory_extraction_tool")
    rkp_missing = not os.path.isfile(rkp_tool_path)
    if rkp_missing:
        print(f"[WARN] rkp_factory_extraction_tool not found at: {rkp_tool_path}", flush=True)
        print(f"       CSR extraction will not work until it is placed there.", flush=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QMessageBox

    delay = 200
    if startup_message:
        QTimer.singleShot(delay, lambda: QMessageBox.information(window, "Data Directory Created", startup_message))
        delay += 100
    if rkp_missing:
        rkp_msg = (
            f"rkp_factory_extraction_tool not found.\n\n"
            f"CSR extraction will fail until the binary is placed at:\n"
            f"  {rkp_tool_path}"
        )
        QTimer.singleShot(delay, lambda: QMessageBox.warning(window, "Missing: rkp_factory_extraction_tool", rkp_msg))

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
