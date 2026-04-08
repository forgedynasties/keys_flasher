import os
import time
import threading
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtWidgets import *

from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt, QPoint, QEvent
from PyQt5.QtGui import QColor, QFont, QIcon, QPixmap

from core.app_paths import get_app_root, get_data_root
from core.adb_utils import (
    run,
    stream_cmd,
    get_all_device_serials,
    get_adb_devices_with_usb,
    get_usb_hw_serial_map,
    get_all_edl_serials,
    check_secure_boot,
    build_device_identity,
)
from core.keybox_utils import find_keybox_in_folder, generate_keybox_from_standard
from core.csr_utils import generate_csr
from core.report_utils import save_metadata, generate_session_report

class StageIndicator(QWidget):
    """A custom widget to show the status of a specific flashing stage or device."""
    def __init__(
        self,
        name,
        action_callback=None,
        action_text="Export CSR",
        secondary_action_callback=None,
        secondary_action_text="Install Keybox",
        tertiary_action_callback=None,
        tertiary_action_text="Flash Firmware",
        expandable=False
    ):
        super().__init__()
        self.action_callback = action_callback
        self.secondary_action_callback = secondary_action_callback
        self.tertiary_action_callback = tertiary_action_callback
        self.expandable = expandable

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(2)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(5, 5, 5, 5)

        self.timer = QTimer()
        self.timer.timeout.connect(self.toggle_blink)
        self.is_visible = True

        if self.expandable:
            self.toggle_btn = QToolButton()
            self.toggle_btn.setArrowType(Qt.RightArrow)
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.clicked.connect(self.toggle_details)
            header_layout.addWidget(self.toggle_btn)
            self.setCursor(Qt.PointingHandCursor)
        
        self.bar = QLabel()
        self.bar.setFixedSize(40, 10)
        self.set_state("blue")
        
        self.label = QLabel(name)
        self.label.setFont(QFont("Arial", 11, QFont.Bold))
        
        header_layout.addWidget(self.bar)
        header_layout.addWidget(self.label)
        
        if self.action_callback and not self.expandable:
            self.action_btn = QPushButton(action_text)
            self.action_btn.setFixedWidth(108)
            self.action_btn.setStyleSheet(
                "font-size: 11px;"
                "font-weight: 600;"
                "padding: 4px 8px;"
                "color: #FFFFFF;"
                "background-color: #2563EB;"
                "border: 1px solid #1D4ED8;"
                "border-radius: 5px;"
            )
            self.action_btn.clicked.connect(self.action_callback)
            header_layout.addWidget(self.action_btn)

        if self.secondary_action_callback and not self.expandable:
            self.secondary_action_btn = QPushButton(secondary_action_text)
            self.secondary_action_btn.setFixedWidth(108)
            self.secondary_action_btn.setStyleSheet(
                "font-size: 11px;"
                "font-weight: 600;"
                "padding: 4px 8px;"
                "color: #FFFFFF;"
                "background-color: #0284C7;"
                "border: 1px solid #0369A1;"
                "border-radius: 5px;"
            )
            self.secondary_action_btn.clicked.connect(self.secondary_action_callback)
            header_layout.addWidget(self.secondary_action_btn)

        if self.tertiary_action_callback and not self.expandable:
            self.tertiary_action_btn = QPushButton(tertiary_action_text)
            self.tertiary_action_btn.setFixedWidth(118)
            self.tertiary_action_btn.setStyleSheet(
                "font-size: 11px;"
                "font-weight: 600;"
                "padding: 4px 8px;"
                "color: #FFFFFF;"
                "background-color: #F59E0B;"
                "border: 1px solid #D97706;"
                "border-radius: 5px;"
            )
            self.tertiary_action_btn.clicked.connect(self.tertiary_action_callback)
            header_layout.addWidget(self.tertiary_action_btn)
            
        header_layout.addStretch()
        root_layout.addLayout(header_layout)

        if self.expandable:
            self.details_widget = QWidget()
            self.details_widget.setStyleSheet(
                "background-color: #0F172A;"
                "border: 1px solid #334155;"
                "border-radius: 8px;"
            )
            details_layout = QVBoxLayout(self.details_widget)
            details_layout.setContentsMargins(12, 8, 12, 8)
            details_layout.setSpacing(6)

            self.hw_serial_label = QLabel("HW Serial: n/a")
            self.hw_serial_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #E2E8F0; border: none;")
            details_layout.addWidget(self.hw_serial_label)

            self.sw_serial_label = QLabel("SW Serial: n/a")
            self.sw_serial_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #E2E8F0; border: none;")
            details_layout.addWidget(self.sw_serial_label)

            self.aio_serial_label = QLabel("AIO Serial (14-char): n/a")
            self.aio_serial_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #E2E8F0; border: none;")
            details_layout.addWidget(self.aio_serial_label)

            self.keybox_ready_status_label = QLabel("Keybox Ready: Pending")
            self.keybox_ready_status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1; border: none;")
            details_layout.addWidget(self.keybox_ready_status_label)

            self.keybox_flashed_status_label = QLabel("Keybox Flashed: Pending")
            self.keybox_flashed_status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1; border: none;")
            details_layout.addWidget(self.keybox_flashed_status_label)

            self.csr_generated_status_label = QLabel("CSR Generated: Pending")
            self.csr_generated_status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1; border: none;")
            details_layout.addWidget(self.csr_generated_status_label)

            self.csr_pulled_status_label = QLabel("CSR Pulled: Pending")
            self.csr_pulled_status_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1; border: none;")
            details_layout.addWidget(self.csr_pulled_status_label)

            if self.action_callback or self.secondary_action_callback or self.tertiary_action_callback:
                actions_layout = QHBoxLayout()
                actions_layout.setContentsMargins(0, 4, 0, 0)
                actions_layout.setSpacing(6)

                if self.action_callback:
                    self.action_btn = QPushButton(action_text)
                    self.action_btn.setFixedWidth(108)
                    self.action_btn.setStyleSheet(
                        "font-size: 11px;"
                        "font-weight: 600;"
                        "padding: 4px 8px;"
                        "color: #FFFFFF;"
                        "background-color: #2563EB;"
                        "border: 1px solid #1D4ED8;"
                        "border-radius: 5px;"
                    )
                    self.action_btn.clicked.connect(self.action_callback)
                    actions_layout.addWidget(self.action_btn)

                if self.secondary_action_callback:
                    self.secondary_action_btn = QPushButton(secondary_action_text)
                    self.secondary_action_btn.setFixedWidth(108)
                    self.secondary_action_btn.setStyleSheet(
                        "font-size: 11px;"
                        "font-weight: 600;"
                        "padding: 4px 8px;"
                        "color: #FFFFFF;"
                        "background-color: #0284C7;"
                        "border: 1px solid #0369A1;"
                        "border-radius: 5px;"
                    )
                    self.secondary_action_btn.clicked.connect(self.secondary_action_callback)
                    actions_layout.addWidget(self.secondary_action_btn)

                if self.tertiary_action_callback:
                    self.tertiary_action_btn = QPushButton(tertiary_action_text)
                    self.tertiary_action_btn.setFixedWidth(118)
                    self.tertiary_action_btn.setStyleSheet(
                        "font-size: 11px;"
                        "font-weight: 600;"
                        "padding: 4px 8px;"
                        "color: #FFFFFF;"
                        "background-color: #F59E0B;"
                        "border: 1px solid #D97706;"
                        "border-radius: 5px;"
                    )
                    self.tertiary_action_btn.clicked.connect(self.tertiary_action_callback)
                    actions_layout.addWidget(self.tertiary_action_btn)

                actions_layout.addStretch()
                details_layout.addLayout(actions_layout)

            self.details_widget.setVisible(False)
            root_layout.addWidget(self.details_widget)

        self.setLayout(root_layout)
        # Keep each device row compact in list layouts.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, state):
        self.timer.stop()
        if state == "blue":
            self.bar.setStyleSheet("background-color: #2196F3; border-radius: 2px;") # Blue
        elif state == "green":
            self.bar.setStyleSheet("background-color: #4CAF50; border-radius: 2px;") # Green
        elif state == "red":
            self.bar.setStyleSheet("background-color: #F44336; border-radius: 2px;") # Red
        elif state == "edl":
            self.bar.setStyleSheet("background-color: #F59E0B; border-radius: 2px;") # Amber
        elif state == "blinking":
            self.bar.setStyleSheet("background-color: #FFEB3B; border-radius: 2px;") # Yellow/Blink
            self.timer.start(500)

    def toggle_blink(self):
        if self.is_visible:
            self.bar.setStyleSheet("background-color: transparent; border-radius: 2px; border: 1px solid #FFEB3B;")
        else:
            self.bar.setStyleSheet("background-color: #FFEB3B; border-radius: 2px;")
        self.is_visible = not self.is_visible

    def set_action_enabled(self, enabled):
        if hasattr(self, "action_btn"):
            self.action_btn.setEnabled(enabled)
        if hasattr(self, "secondary_action_btn"):
            self.secondary_action_btn.setEnabled(enabled)
        if hasattr(self, "tertiary_action_btn"):
            self.tertiary_action_btn.setEnabled(enabled)

    def toggle_details(self):
        if not self.expandable:
            return
        is_open = self.toggle_btn.isChecked()
        self.toggle_btn.setArrowType(Qt.DownArrow if is_open else Qt.RightArrow)
        self.details_widget.setVisible(is_open)

    def mousePressEvent(self, event):
        if self.expandable and event.button() == Qt.LeftButton:
            self.toggle_btn.toggle()
            self.toggle_details()
        super().mousePressEvent(event)

    def _status_color(self, status):
        status_text = (status or "").strip().lower()
        if status_text in {"done", "pass", "flashed", "found", "generated", "ready"}:
            return "#22C55E"
        if status_text in {"running", "flashing"}:
            return "#38BDF8"
        if status_text in {"failed", "fail", "invalid serial"}:
            return "#F87171"
        if status_text in {"skipped"}:
            return "#94A3B8"
        return "#FBBF24"

    def _set_status_line(self, label, prefix, value):
        text_value = value if value else "Pending"
        color = self._status_color(text_value)
        label.setText(f"{prefix}: {text_value}")
        label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color}; border: none;")

    def _set_identity_line(self, label, prefix, value):
        text_value = value if value else "n/a"
        label.setText(f"{prefix}: {text_value}")
        label.setStyleSheet("font-size: 12px; font-weight: 600; color: #E2E8F0; border: none;")

    def set_identity_fields(self, hw_serial=None, sw_serial=None, aio_serial=None):
        if not self.expandable:
            return
        if hw_serial is not None:
            self._set_identity_line(self.hw_serial_label, "HW Serial", hw_serial)
        if sw_serial is not None:
            self._set_identity_line(self.sw_serial_label, "SW Serial", sw_serial)
        if aio_serial is not None:
            self._set_identity_line(self.aio_serial_label, "AIO Serial (14-char)", aio_serial)

    def set_progress_fields(
        self,
        keybox_ready_status=None,
        keybox_flashed_status=None,
        csr_generated_status=None,
        csr_pulled_status=None
    ):
        if not self.expandable:
            return

        if keybox_ready_status is not None:
            self._set_status_line(self.keybox_ready_status_label, "Keybox Ready", keybox_ready_status)
        if keybox_flashed_status is not None:
            self._set_status_line(self.keybox_flashed_status_label, "Keybox Flashed", keybox_flashed_status)
        if csr_generated_status is not None:
            self._set_status_line(self.csr_generated_status_label, "CSR Generated", csr_generated_status)
        if csr_pulled_status is not None:
            self._set_status_line(self.csr_pulled_status_label, "CSR Pulled", csr_pulled_status)

    def clear_process_details(self):
        if not self.expandable:
            return
        self._set_status_line(self.keybox_ready_status_label, "Keybox Ready", "Pending")
        self._set_status_line(self.keybox_flashed_status_label, "Keybox Flashed", "Pending")
        self._set_status_line(self.csr_generated_status_label, "CSR Generated", "Pending")
        self._set_status_line(self.csr_pulled_status_label, "CSR Pulled", "Pending")

class FlasherThread(QThread):
    """Background thread to handle the long-running flashing process without freezing the GUI."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    stage_signal = pyqtSignal(str, str) # stage_name, state
    finished_signal = pyqtSignal(bool, str)
    results_signal = pyqtSignal(object)
    device_signal = pyqtSignal(str, str) # serial, state
    activity_signal = pyqtSignal(str, str) # serial or ALL, activity text
    device_step_signal = pyqtSignal(str, str, str) # serial, step, status (running/pass/fail/info)

    SERIAL_PREFIX = "AT070"
    SERIAL_MIN_SUFFIX_LENGTH = 7
    SERIAL_PATTERN_LABEL = "AT070XXXXXXX"
    DEVICE_READY_TIMEOUT_SECONDS = 300
    POLL_INTERVAL_SECONDS = 2
    READY_LOG_INTERVAL_SECONDS = 10

    def __init__(self, target_serials, keybox_base_path=None, session_start_ts=None, device_identity=None):
        super().__init__()
        self.target_serials = target_serials[:8]
        self.keybox_base_path = keybox_base_path
        self.session_start_ts = session_start_ts if session_start_ts is not None else time.time()
        self.data_root = get_data_root()
        self._is_aborted = False
        self.device_identity = dict(device_identity or {})
        
    def abort(self):
        self._is_aborted = True

    def check_abort(self):
        return self._is_aborted

    def emit_weighted_progress(self, stage_fraction=0.0):
        """Overall progress = completed devices + current device internal stage fraction."""
        total = max(self.total_target_devices, 1)
        clamped_fraction = max(0.0, min(stage_fraction, 1.0))
        progress = int(((self.completed_target_devices + clamped_fraction) / total) * 100)
        self.progress_signal.emit(max(0, min(progress, 100)))

    @staticmethod
    def format_elapsed(seconds):
        total_seconds = max(0, int(seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def serial_matches_required_pattern(self, serial):
        serial_text = str(serial or "").strip()
        return (
            serial_text.startswith(self.SERIAL_PREFIX)
            and len(serial_text) >= (len(self.SERIAL_PREFIX) + self.SERIAL_MIN_SUFFIX_LENGTH)
        )

    @staticmethod
    def is_transient_adb_state(output):
        text = (output or "").strip().lower()
        if not text:
            return True
        transient_markers = (
            "error:",
            "error: closed",
            "closed",
            "device offline",
            "no devices/emulators found",
            "error: device",
            "waiting for device",
            "unauthorized",
            "can't find service",
            "more than one device",
            "transport",
            "not found",
            "failed to get feature set",
            "connection reset",
            "connection refused",
            "daemon not running",
            "adb server version"
        )
        return any(marker in text for marker in transient_markers)

    def read_prop(self, serial, prop_name):
        return run(f"adb -s {serial} shell getprop {prop_name}").strip()

    def resolve_device_identity(self, serial):
        identity = build_device_identity(
            serial,
            usb_path=self.device_identity.get("usb_path"),
            sw_serial=self.device_identity.get("sw_serial"),
        )
        for field in ("adb_serial", "usb_path", "hw_serial", "sw_serial", "aio_serial"):
            current_value = identity.get(field)
            fallback_value = self.device_identity.get(field)
            if current_value in (None, "", "n/a") and fallback_value:
                identity[field] = fallback_value
        self.device_identity.update(identity)
        return identity

    def is_boot_completed(self, serial):
        """
        Consider boot complete when `sys.boot_completed=1`.
        Some builds also expose `dev.bootcomplete=1`; if present and readable,
        it must not contradict completion.
        Returns (ready_bool, detail_text_for_logging_or_errors).
        """
        sys_boot = self.read_prop(serial, "sys.boot_completed")
        if self.is_transient_adb_state(sys_boot):
            return False, f"sys.boot_completed={sys_boot or 'N/A'}"

        dev_boot = self.read_prop(serial, "dev.bootcomplete")
        if self.is_transient_adb_state(dev_boot):
            return False, f"dev.bootcomplete={dev_boot or 'N/A'}"

        if sys_boot == "1" and (dev_boot in ("", "1")):
            return True, f"sys.boot_completed={sys_boot}, dev.bootcomplete={dev_boot or 'N/A'}"

        return False, f"sys.boot_completed={sys_boot or 'N/A'}, dev.bootcomplete={dev_boot or 'N/A'}"

    def wait_until_device_ready(self, serial, timeout_seconds):
        """
        Wait until the device is available on ADB, boot-complete, and secure boot prop is readable.
        Returns (secure_state, error_or_none).
        """
        start_time = time.time()
        last_secure_response = ""
        last_boot_response = ""
        last_log_time = 0

        while time.time() - start_time < timeout_seconds:
            if self.check_abort():
                return None, "aborted"

            if serial not in get_all_device_serials():
                now = time.time()
                if now - last_log_time >= self.READY_LOG_INTERVAL_SECONDS:
                    self.log_signal.emit(f"Waiting for {serial} to reappear on ADB...")
                    last_log_time = now
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue

            adb_state = run(f"adb -s {serial} get-state").strip()
            if self.is_transient_adb_state(adb_state) or adb_state.lower() != "device":
                last_boot_response = f"adb get-state={adb_state or 'N/A'}"
                now = time.time()
                if now - last_log_time >= self.READY_LOG_INTERVAL_SECONDS:
                    self.log_signal.emit(
                        f"Waiting for stable ADB transport on {serial}... (last state: {adb_state or 'N/A'})"
                    )
                    last_log_time = now
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue

            boot_ready, boot_detail = self.is_boot_completed(serial)
            last_boot_response = boot_detail
            if not boot_ready:
                now = time.time()
                if now - last_log_time >= self.READY_LOG_INTERVAL_SECONDS:
                    self.log_signal.emit(
                        f"Waiting for {serial} Android boot completion... (last: {boot_detail})"
                    )
                    last_log_time = now
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue

            secure_state = check_secure_boot(serial)
            last_secure_response = secure_state
            if self.is_transient_adb_state(secure_state):
                now = time.time()
                if now - last_log_time >= self.READY_LOG_INTERVAL_SECONDS:
                    self.log_signal.emit(
                        f"Waiting for {serial} to become fully ready... (last response: {secure_state})"
                    )
                    last_log_time = now
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue

            return secure_state, None

        if last_secure_response:
            return None, last_secure_response
        if last_boot_response:
            return None, last_boot_response
        return None, "Timed out while waiting for device readiness."

    def emit_activity(self, serial, activity):
        self.activity_signal.emit(serial, activity)

    def emit_step(self, serial, step, status):
        self.device_step_signal.emit(serial, step, status)

    def ensure_keybox_for_serial(self, serial):
        keybox_dir = os.path.join(self.data_root, "keyboxes")
        direct_path = os.path.join(keybox_dir, f"{serial}.xml")
        if os.path.exists(direct_path):
            return direct_path, "found"

        if not self.serial_matches_required_pattern(serial):
            self.log_signal.emit(
                f"Skipping keybox generation for {serial}: serial must match {self.SERIAL_PATTERN_LABEL}."
            )
            return None, None

        standard_path = os.path.join(keybox_dir, "standard.xml")
        self.log_signal.emit(
            f"Keybox for {serial} not found. Generating at runtime from {standard_path}..."
        )
        generated_path = generate_keybox_from_standard(serial, keybox_dir)
        if generated_path:
            self.log_signal.emit(f"Generated keybox for {serial}: {generated_path}")
            return generated_path, "generated"

        # Keep XML-scan fallback for backward compatibility with older keybox sets.
        matched_path = find_keybox_in_folder(serial, keybox_dir)
        if matched_path:
            return matched_path, "found"
        return None, None

    def append_result(self, results, serial, success, message, details=None):
        identity = self.resolve_device_identity(serial)
        result_entry = {
            "serial": serial,
            "success": success,
            "message": message,
            "hw_serial": identity.get("hw_serial", "n/a"),
            "sw_serial": identity.get("sw_serial", "n/a"),
            "aio_serial": identity.get("aio_serial", "n/a"),
        }
        results.append(result_entry)

        metadata_details = {
            "message": message,
            "hw_serial": result_entry["hw_serial"],
            "sw_serial": result_entry["sw_serial"],
            "aio_serial": result_entry["aio_serial"],
        }
        if details:
            metadata_details.update(details)
        if not success:
            metadata_details.setdefault("error", message)
        save_metadata(serial, success, metadata_details)

    def fail_device(self, results, serial, message, stage_name=None):
        self.log_signal.emit(f"❌ {message}")
        self.emit_step(serial, message, "fail")
        if stage_name:
            self.stage_signal.emit(stage_name, "red")
        self.device_signal.emit(serial, "red")
        self.append_result(results, serial, False, message)

    def complete_device_success(self, results, serial, message="Completed Successfully"):
        self.stage_signal.emit("CSR Pulled", "green")
        self.device_signal.emit(serial, "green")
        self.emit_activity(serial, "Completed")
        self.emit_step(serial, "Completed Successfully", "pass")
        self.append_result(results, serial, True, message)
        self.emit_weighted_progress(1.0)
        return True

    def process_single_device(self, serial, results):
        self.log_signal.emit(f"\n>>> PROCESSING DEVICE: {serial} <<<")
        identity = self.resolve_device_identity(serial)
        self.log_signal.emit(
            "Device Identity "
            f"({serial}) -> HW: {identity.get('hw_serial', 'n/a')} | "
            f"SW: {identity.get('sw_serial', 'n/a')} | "
            f"AIO: {identity.get('aio_serial', 'n/a')}"
        )
        self.device_signal.emit(serial, "blinking")
        self.stage_signal.emit("Serial No Matched", "blue")
        self.stage_signal.emit("Keybox Flashed", "blue")
        self.stage_signal.emit("CSR Pulled", "blue")
        self.emit_weighted_progress(0.05)

        if self.check_abort():
            self.fail_device(results, serial, "Process aborted by user.")
            return

        # 1. Check secure boot on this device.
        self.emit_activity(serial, "Waiting for device to become ready")
        self.emit_step(serial, "Waiting for device to become ready", "running")
        self.stage_signal.emit("Serial No Matched", "blinking")
        self.emit_weighted_progress(0.20)
        secure_state, ready_error = self.wait_until_device_ready(serial, self.DEVICE_READY_TIMEOUT_SECONDS)
        if ready_error:
            if ready_error == "aborted":
                self.fail_device(results, serial, "Process aborted by user.", "Serial No Matched")
                return False
            current_msg = f"Device not ready within {self.DEVICE_READY_TIMEOUT_SECONDS // 60} minutes."
            if ready_error:
                current_msg += f" Last ADB response: {ready_error}"
            self.fail_device(results, serial, current_msg, "Serial No Matched")
            return False

        self.emit_activity(serial, "Checking secure boot")
        self.emit_step(serial, "Checking secure boot", "running")
        self.log_signal.emit(f"Secure Boot State ({serial}): {secure_state}")
        if "green" not in secure_state.lower() and "locked" not in secure_state.lower() and "true" not in secure_state.lower():
            self.fail_device(results, serial, f"Secure Boot NOT active ({secure_state})", "Serial No Matched")
            return False
        self.stage_signal.emit("Serial No Matched", "green")
        self.emit_step(serial, "Secure boot verified", "pass")
        self.emit_weighted_progress(0.30)

        if self.check_abort():
            self.fail_device(results, serial, "Process aborted by user.")
            return

        # 2. Try CSR extraction directly via RKP tool before keybox.
        self.emit_activity(serial, "Trying CSR extraction before keybox")
        self.emit_step(serial, "Generating CSR", "running")
        self.emit_step(serial, "Pulling CSR to PC", "running")
        self.stage_signal.emit("CSR Pulled", "blinking")
        self.emit_weighted_progress(0.40)
        precheck_success, precheck_msg = generate_csr(serial, self.log_signal.emit, self.check_abort)
        if self.check_abort() or (precheck_msg and "aborted" in precheck_msg.lower()):
            self.fail_device(results, serial, "Process aborted by user.")
            return False
        if precheck_success:
            self.log_signal.emit(
                f"CSR generated for {serial} without keybox installation. Skipping keybox flashing."
            )
            self.stage_signal.emit("Keybox Flashed", "green")
            self.emit_step(serial, "Keybox skipped", "info")
            self.emit_step(serial, "CSR Generated", "pass")
            self.emit_step(serial, "CSR Pulled to PC", "pass")
            return self.complete_device_success(
                results, serial, "CSR extracted before keybox. Keybox installation skipped."
            )

        self.log_signal.emit(
            f"CSR not available yet for {serial} ({precheck_msg}). Proceeding with keybox flashing."
        )
        self.emit_step(serial, "CSR pre-check unavailable", "info")
        self.stage_signal.emit("CSR Pulled", "blue")
        self.emit_weighted_progress(0.45)

        # 3. Resolve or generate keybox.
        self.emit_activity(serial, "Preparing keybox")
        self.emit_step(serial, "Preparing keybox", "running")
        self.stage_signal.emit("Keybox Flashed", "blinking")
        self.emit_weighted_progress(0.55)
        keybox_path, keybox_source = self.ensure_keybox_for_serial(serial)
        if not keybox_path:
            self.fail_device(results, serial, "Keybox XML not found and generation failed.", "Keybox Flashed")
            return False

        self.log_signal.emit(f"Using Keybox: {keybox_path}")
        if keybox_source == "generated":
            self.emit_step(serial, "Keybox generated", "pass")
        else:
            self.emit_step(serial, "Keybox found", "pass")
        self.emit_weighted_progress(0.62)

        # 4. Flash keybox.
        self.emit_activity(serial, "Flashing keybox")
        self.emit_step(serial, "Flashing keybox", "running")
        self.emit_weighted_progress(0.72)
        run(f"adb -s {serial} root")
        time.sleep(2)

        self.log_signal.emit("Pushing keybox XML...")
        push_ret = stream_cmd(
            f"adb -s {serial} push \"{keybox_path}\" /data/keymaster_keybox.xml",
            self.log_signal.emit,
            self.check_abort
        )
        if push_ret != 0:
            self.fail_device(results, serial, "Failed to push keybox XML.", "Keybox Flashed")
            return False

        self.log_signal.emit("Installing keybox...")
        cmd = f'adb -s {serial} shell "LD_LIBRARY_PATH=/vendor/lib64/hw /vendor/bin/KmInstallKeybox /data/keymaster_keybox.xml {serial} true"'
        ret_code = stream_cmd(cmd, self.log_signal.emit, self.check_abort, fail_str="InstallKeybox Failed")
        if ret_code != 0:
            self.fail_device(results, serial, "KmInstallKeybox Failed", "Keybox Flashed")
            return False

        self.stage_signal.emit("Keybox Flashed", "green")
        self.emit_step(serial, "Keybox flashed", "pass")
        self.emit_weighted_progress(0.84)

        if self.check_abort():
            self.fail_device(results, serial, "Process aborted by user.")
            return

        # 5. Generate and pull CSR.
        self.emit_activity(serial, "Generating CSR")
        self.emit_step(serial, "Generating CSR", "running")
        self.emit_step(serial, "Pulling CSR to PC", "running")
        self.stage_signal.emit("CSR Pulled", "blinking")
        self.emit_weighted_progress(0.90)
        success, csr_msg = generate_csr(serial, self.log_signal.emit, self.check_abort)
        if not success:
            if "pull" in csr_msg.lower():
                self.emit_step(serial, "CSR Pulled to PC", "fail")
            else:
                self.emit_step(serial, "CSR Generated", "fail")
            self.fail_device(results, serial, f"CSR Pull Failed: {csr_msg}", "CSR Pulled")
            return False

        self.emit_step(serial, "CSR Generated", "pass")
        self.emit_step(serial, "CSR Pulled to PC", "pass")
        return self.complete_device_success(results, serial, "Completed Successfully")

    def run(self):
        try:
            self.log_signal.emit("--- Starting Multi-Device Flash Process ---")
            run("adb start-server")

            if not self.target_serials:
                self.finished_signal.emit(False, "No devices were available to process.")
                return

            self.total_target_devices = len(self.target_serials)
            self.completed_target_devices = 0
            self.emit_weighted_progress(0.0)
            self.log_signal.emit(f"Target devices captured at START FLASHING: {self.total_target_devices}")

            results = []
            processed_or_handled = set()
            self.emit_activity("ALL", "Processing selected devices (reboot disabled)")
            self.log_signal.emit(
                f"Processing {len(self.target_serials)} selected device(s) directly without reboot..."
            )

            for serial in self.target_serials:
                if self.check_abort():
                    self.finished_signal.emit(False, "Process aborted.")
                    return

                if serial in processed_or_handled:
                    continue

                if not self.serial_matches_required_pattern(serial):
                    msg = f"Serial does not match required pattern {self.SERIAL_PATTERN_LABEL}. Marked FAIL."
                    self.log_signal.emit(f"⚠️ {serial}: {msg}")
                    self.emit_activity(serial, "Invalid serial pattern")
                    self.emit_step(serial, "Invalid serial pattern", "fail")
                    self.device_signal.emit(serial, "red")
                    self.append_result(results, serial, False, msg)
                    processed_or_handled.add(serial)
                    self.completed_target_devices += 1
                    self.emit_weighted_progress(0.0)
                    continue

                try:
                    self.process_single_device(serial, results)
                except Exception as device_error:
                    self.fail_device(results, serial, f"Exception: {device_error}")

                processed_or_handled.add(serial)
                self.completed_target_devices += 1
                self.emit_weighted_progress(0.0)

            # Safety pass: ensure every initially captured device has a terminal result.
            result_serials = {r["serial"] for r in results}
            for serial in self.target_serials:
                if serial not in result_serials:
                    msg = "Device ended without terminal status. Marked FAIL."
                    self.log_signal.emit(f"❌ {serial}: {msg}")
                    self.emit_step(serial, msg, "fail")
                    self.device_signal.emit(serial, "red")
                    self.append_result(results, serial, False, msg)

            # Final Phase: Reporting and truthful session outcome.
            report = generate_session_report(results)
            self.log_signal.emit(report)
            # Report explicit PASS/FAIL counts for clarity
            passed = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))
            total = len({r['serial'] for r in results})
            self.log_signal.emit(f"Processed initial devices: TOTAL={total} | PASSED={passed} | FAILED={failed}")
            elapsed = self.format_elapsed(time.time() - self.session_start_ts)
            self.log_signal.emit(f"Total Elapsed Time (from START FLASHING click): {elapsed}")
            self.progress_signal.emit(100)

            overall_success = bool(results) and all(r["success"] for r in results)
            final_msg = "All connected devices processed." if overall_success else "Processing finished with failures. Check session report."
            self.results_signal.emit(results)
            self.finished_signal.emit(overall_success, final_msg)

        except Exception as e:
            elapsed = self.format_elapsed(time.time() - self.session_start_ts)
            self.log_signal.emit(f"Total Elapsed Time (from START FLASHING click): {elapsed}")
            self.results_signal.emit([])
            self.finished_signal.emit(False, f"Fatal Exception: {str(e)}")


class FirmwareFlasherThread(QThread):
    """Background thread to handle parallel EDL firmware flashing."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    stage_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(bool, str)
    results_signal = pyqtSignal(object)
    device_list_signal = pyqtSignal(object)
    device_progress_signal = pyqtSignal(str, int, str)  # edl_serial, percent, state
    device_image_signal = pyqtSignal(str, str)  # edl_serial, current_image

    EDL_DISCOVERY_TIMEOUT_SECONDS = 45
    EDL_DISCOVERY_POLL_SECONDS = 2

    def __init__(self, barcode_serial="", adb_targets=None, edl_targets=None, allowed_edl_serials=None):
        super().__init__()
        self.barcode_serial = barcode_serial
        self.adb_targets = list(adb_targets) if adb_targets is not None else None
        self.edl_targets = list(edl_targets) if edl_targets is not None else None
        self.allowed_edl_serials = [
            str(serial).strip()
            for serial in (allowed_edl_serials or [])
            if str(serial).strip() and str(serial).strip().lower() != "n/a"
        ]
        self.app_root = get_app_root()
        self.data_root = get_data_root()
        self.firmware_dir = os.path.join(self.data_root, "firmwares", "A15-v1.50-user", "qfil_download_emmc")
        self._is_aborted = False
        self._progress_lock = threading.Lock()
        self._device_progress = {}
        self._super_flash_counts = {}

    def abort(self):
        self._is_aborted = True

    def check_abort(self):
        return self._is_aborted

    def parse_qdl_serials(self):
        return get_all_edl_serials()

    def update_device_progress(self, edl_serial, percent, state):
        clamped = max(0, min(int(percent), 100))
        with self._progress_lock:
            self._device_progress[edl_serial] = clamped
            avg_progress = int(sum(self._device_progress.values()) / max(len(self._device_progress), 1))
        self.device_progress_signal.emit(edl_serial, clamped, state)
        self.progress_signal.emit(avg_progress)

    def map_qdl_line_to_progress(self, edl_serial, line):
        text = (line or "").lower()
        if "waiting for programmer" in text:
            return 12
        if "successfully erased" in text:
            return 22
        if "flashed \"modem" in text:
            return 32
        if "flashed \"boot" in text:
            return 42
        if "flashed \"super\"" in text:
            with self._progress_lock:
                count = self._super_flash_counts.get(edl_serial, 0) + 1
                self._super_flash_counts[edl_serial] = count
            return min(50 + (count * 4), 90)
        if "flashed \"userdata\"" in text:
            return 96
        if "partition 0 is now bootable" in text:
            return 100
        return None

    @staticmethod
    def infer_current_image(line):
        text = (line or "").strip()
        lower_text = text.lower()
        marker = 'flashed "'
        if marker in lower_text:
            start = lower_text.find(marker)
            if start >= 0:
                remainder = text[start + len(marker):]
                end = remainder.find('"')
                if end > 0:
                    return remainder[:end]
        if "waiting for programmer" in lower_text:
            return "programmer"
        if "successfully erased" in lower_text:
            return "erase"
        return None

    def flash_single_edl_device(self, edl_serial):
        self.log_signal.emit(f"[EDL:{edl_serial}] Starting firmware flash...")
        self.update_device_progress(edl_serial, 8, "running")
        self.device_image_signal.emit(edl_serial, "initializing")

        def handle_qdl_log(line):
            self.log_signal.emit(f"[EDL:{edl_serial}] {line}")
            image = self.infer_current_image(line)
            if image:
                self.device_image_signal.emit(edl_serial, image)
            progress = self.map_qdl_line_to_progress(edl_serial, line)
            if progress is not None:
                self.update_device_progress(edl_serial, progress, "running")

        qdl_cmd = (
            f'cd "{self.firmware_dir}" && '
            f"echo 123456 | sudo -S qdl -S {edl_serial} -s emmc "
            "prog_firehose_ddr.elf rawprogram_unsparse0.xml patch0.xml"
        )
        ret_code = stream_cmd(qdl_cmd, handle_qdl_log, self.check_abort)

        if self.check_abort():
            self.update_device_progress(edl_serial, self._device_progress.get(edl_serial, 0), "aborted")
            self.device_image_signal.emit(edl_serial, "aborted")
            return False, "Aborted by user."
        if ret_code == 0:
            self.update_device_progress(edl_serial, 100, "done")
            self.device_image_signal.emit(edl_serial, "completed")
            return True, "Firmware flashed successfully."

        self.update_device_progress(edl_serial, self._device_progress.get(edl_serial, 0), "failed")
        self.device_image_signal.emit(edl_serial, "failed")
        return False, f"QDL flashing failed with return code: {ret_code}"

    def run(self):
        firmware_start_ts = time.time()
        try:
            self.progress_signal.emit(3)
            self.log_signal.emit("\n--- Starting Parallel EDL Firmware Flashing Process ---")
            self.stage_signal.emit("User Firmware Done", "blinking")

            if not os.path.exists(self.firmware_dir):
                self.stage_signal.emit("User Firmware Done", "red")
                self.finished_signal.emit(False, f"Firmware directory not found: {self.firmware_dir}")
                return

            adb_serials = self.adb_targets if self.adb_targets is not None else get_all_device_serials()[:8]
            edl_serials = []

            if self.edl_targets is not None:
                edl_serials = list(self.edl_targets)
                if not edl_serials:
                    self.stage_signal.emit("User Firmware Done", "red")
                    self.finished_signal.emit(False, "No EDL devices provided for flashing.")
                    return
                self.log_signal.emit(f"Using provided EDL targets: {', '.join(edl_serials)}")
            elif adb_serials:
                self.log_signal.emit(f"ADB devices selected for EDL reboot: {len(adb_serials)}")
                for serial in adb_serials:
                    if self.check_abort():
                        self.stage_signal.emit("User Firmware Done", "red")
                        self.finished_signal.emit(False, "Firmware flashing aborted by user.")
                        return
                    self.log_signal.emit(f"Rebooting {serial} to EDL...")
                    run(f"adb -s {serial} reboot edl")

                self.progress_signal.emit(12)
                self.log_signal.emit("Waiting for EDL devices via `qdl list`...")

                deadline = time.time() + self.EDL_DISCOVERY_TIMEOUT_SECONDS
                last_log_ts = 0
                target_count = len(adb_serials)
                allowed_set = set(self.allowed_edl_serials)
                matched_edl_serials = []
                if allowed_set:
                    self.log_signal.emit(
                        "Restricting firmware flashing to approved EDL/HW serials: "
                        + ", ".join(sorted(allowed_set))
                    )
                while time.time() < deadline:
                    if self.check_abort():
                        self.stage_signal.emit("User Firmware Done", "red")
                        self.finished_signal.emit(False, "Firmware flashing aborted by user.")
                        return
                    edl_serials = self.parse_qdl_serials()
                    if allowed_set:
                        matched_edl_serials = [serial for serial in edl_serials if serial in allowed_set]
                    else:
                        matched_edl_serials = list(edl_serials)
                    if len(matched_edl_serials) >= target_count:
                        edl_serials = matched_edl_serials[:target_count]
                        break
                    now = time.time()
                    if now - last_log_ts >= 5:
                        if allowed_set:
                            self.log_signal.emit(
                                f"Detected approved EDL devices: {len(matched_edl_serials)}/{target_count}"
                            )
                        else:
                            self.log_signal.emit(f"Detected EDL devices: {len(edl_serials)}/{target_count}")
                        last_log_ts = now
                    time.sleep(self.EDL_DISCOVERY_POLL_SECONDS)

                if allowed_set:
                    edl_serials = matched_edl_serials[:target_count]

                if not edl_serials:
                    self.stage_signal.emit("User Firmware Done", "red")
                    if allowed_set:
                        self.finished_signal.emit(
                            False,
                            "No approved EDL devices detected from `qdl list` after reboot.",
                        )
                    else:
                        self.finished_signal.emit(False, "No EDL devices detected from `qdl list` after reboot.")
                    return

                if len(edl_serials) < target_count:
                    if allowed_set:
                        self.log_signal.emit(
                            f"⚠️ Only {len(edl_serials)} approved EDL devices detected for {target_count} ADB targets. Proceeding with approved devices only."
                        )
                    else:
                        self.log_signal.emit(
                            f"⚠️ Only {len(edl_serials)} EDL devices detected for {target_count} ADB devices. Proceeding with detected EDL devices."
                        )
            else:
                self.log_signal.emit("No ADB devices found. Checking `qdl list` for devices already in EDL mode...")
                edl_serials = self.parse_qdl_serials()[:8]
                if not edl_serials:
                    self.stage_signal.emit("User Firmware Done", "red")
                    self.finished_signal.emit(False, "No ADB devices and no EDL devices found in `qdl list`.")
                    return
                self.progress_signal.emit(12)
                self.log_signal.emit(
                    f"Detected {len(edl_serials)} EDL device(s) already in EDL mode. Flashing directly."
                )

            self.log_signal.emit(f"EDL targets: {', '.join(edl_serials)}")
            self.device_list_signal.emit(edl_serials)

            with self._progress_lock:
                self._device_progress = {serial: 0 for serial in edl_serials}
                self._super_flash_counts = {serial: 0 for serial in edl_serials}
            for edl_serial in edl_serials:
                self.device_progress_signal.emit(edl_serial, 0, "queued")

            results = []
            max_workers = max(1, len(edl_serials))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(self.flash_single_edl_device, serial): serial for serial in edl_serials}
                for future in as_completed(futures):
                    serial = futures[future]
                    try:
                        success, message = future.result()
                    except Exception as ex:
                        success, message = False, f"Exception: {ex}"
                    results.append({"serial": serial, "edl_serial": serial, "success": success, "message": message})

            result_serials = {result["serial"] for result in results}
            for serial in edl_serials:
                if serial not in result_serials:
                    results.append(
                        {
                            "serial": serial,
                            "edl_serial": serial,
                            "success": False,
                            "message": "No terminal result captured.",
                        }
                    )

                report = generate_session_report(results)
                elapsed = FlasherThread.format_elapsed(time.time() - firmware_start_ts)
                firmware_report = f"{report.rstrip()}\nFirmware Flash Elapsed Time: {elapsed}\n"
            self.log_signal.emit("--- Parallel Firmware Flash Report ---")
            self.log_signal.emit(firmware_report)

            overall_success = bool(results) and all(result["success"] for result in results)
            self.progress_signal.emit(100)
            self.results_signal.emit(results)
            self.stage_signal.emit("User Firmware Done", "green" if overall_success else "red")
            final_msg = (
                f"Parallel firmware flashing completed successfully. Total firmware flash time: {elapsed}."
                if overall_success
                else f"Parallel firmware flashing finished with failures. Check report. Total firmware flash time: {elapsed}."
            )
            self.finished_signal.emit(overall_success, final_msg)

        except Exception as e:
            self.results_signal.emit([])
            self.stage_signal.emit("User Firmware Done", "red")
            self.finished_signal.emit(False, f"Error during EDL Firmware flash: {str(e)}")

class CSRExtractorThread(QThread):
    """Background thread to handle on-demand CSR extraction from the device."""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    stage_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, serial):
        super().__init__()
        self.serial = serial
        self.data_root = get_data_root()
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def check_abort(self):
        return self._is_aborted

    def run(self):
        try:
            self.progress_signal.emit(10)
            self.log_signal.emit(f"\n--- Starting On-Demand CSR Extraction for {self.serial} ---")
            self.stage_signal.emit("CSR Exported", "blinking")
            
            from core.csr_utils import generate_csr
            success, message = generate_csr(self.serial, self.log_signal.emit, self.check_abort)
            
            if success:
                self.progress_signal.emit(100)
                self.stage_signal.emit("CSR Exported", "green")
                self.finished_signal.emit(True, message)
            else:
                self.stage_signal.emit("CSR Exported", "red")
                self.finished_signal.emit(False, message)
        except Exception as e:
            self.finished_signal.emit(False, f"Error during CSR extraction: {str(e)}")


class KeyboxInstallerThread(QThread):
    """Background thread for on-demand keybox installation on one device."""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, serial):
        super().__init__()
        self.serial = serial
        self._is_aborted = False

    def abort(self):
        self._is_aborted = True

    def check_abort(self):
        return self._is_aborted

    def ensure_keybox_for_serial(self):
        keybox_dir = os.path.join(self.data_root, "keyboxes")
        direct_path = os.path.join(keybox_dir, f"{self.serial}.xml")
        if os.path.exists(direct_path):
            return direct_path

        serial_text = str(self.serial or "").strip()
        if not (
            serial_text.startswith(FlasherThread.SERIAL_PREFIX)
            and len(serial_text) >= (len(FlasherThread.SERIAL_PREFIX) + FlasherThread.SERIAL_MIN_SUFFIX_LENGTH)
        ):
            return None

        standard_path = os.path.join(keybox_dir, "standard.xml")
        self.log_signal.emit(
            f"Keybox for {self.serial} not found. Generating from {standard_path}..."
        )
        generated_path = generate_keybox_from_standard(self.serial, keybox_dir)
        if generated_path:
            self.log_signal.emit(f"Generated keybox for {self.serial}: {generated_path}")
            return generated_path

        return find_keybox_in_folder(self.serial, keybox_dir)

    def run(self):
        try:
            self.log_signal.emit(f"\n--- Starting On-Demand Keybox Install for {self.serial} ---")
            if self.check_abort():
                self.finished_signal.emit(False, "Process aborted by user.")
                return

            keybox_path = self.ensure_keybox_for_serial()
            if not keybox_path:
                self.finished_signal.emit(False, "Keybox XML not found and generation failed.")
                return

            self.log_signal.emit(f"Using Keybox: {keybox_path}")
            if self.check_abort():
                self.finished_signal.emit(False, "Process aborted by user.")
                return

            run(f"adb -s {self.serial} root")
            time.sleep(2)

            self.log_signal.emit("Pushing keybox XML...")
            push_ret = stream_cmd(
                f"adb -s {self.serial} push \"{keybox_path}\" /data/keymaster_keybox.xml",
                self.log_signal.emit,
                self.check_abort
            )
            if push_ret != 0:
                if self.check_abort() or push_ret == -1:
                    self.finished_signal.emit(False, "Process aborted by user.")
                else:
                    self.finished_signal.emit(False, "Failed to push keybox XML.")
                return

            if self.check_abort():
                self.finished_signal.emit(False, "Process aborted by user.")
                return

            self.log_signal.emit("Installing keybox...")
            cmd = (
                f'adb -s {self.serial} shell '
                f'"LD_LIBRARY_PATH=/vendor/lib64/hw /vendor/bin/KmInstallKeybox /data/keymaster_keybox.xml {self.serial} true"'
            )
            ret_code = stream_cmd(cmd, self.log_signal.emit, self.check_abort, fail_str="InstallKeybox Failed")
            if ret_code != 0:
                if self.check_abort() or ret_code == -1:
                    self.finished_signal.emit(False, "Process aborted by user.")
                else:
                    self.finished_signal.emit(False, "KmInstallKeybox Failed")
                return

            self.finished_signal.emit(True, "Keybox installed successfully.")
        except Exception as e:
            self.finished_signal.emit(False, f"Error during keybox install: {str(e)}")



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.app_root = get_app_root()
        self.data_root = get_data_root()

        self.setWindowTitle("Professional Keybox Flashing Tool")
        self.resize(800, 600)
        self.last_known_serial = None # Track for reset logic
        self.seen_connected_serials = set()
        self.generated_keyboxes = set()
        self.failed_keybox_generation = set()
        self.active_csr_serial = None
        self.active_keybox_serial = None
        self.device_process_state = {}
        self.status_table_row_map = {}
        self.device_log_views = {}
        self.current_device_log_serials = []
        self.parallel_flasher_threads = {}
        self.parallel_results = {}
        self.parallel_device_progress = {}
        self.parallel_serials = []
        self.parallel_completed_count = 0
        self.parallel_session_start_ts = None
        self.firmware_status_row_map = {}
        self.latest_firmware_results = []
        self.combined_firmware_context = None
        self.log_folder = os.path.join(self.data_root, "logs")
        os.makedirs(self.log_folder, exist_ok=True)
        self.session_log_file = None

        # Set Application Icon
        icon_path = os.path.join(self.app_root, "app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # UI Styling Setup
        self.setup_ui()
        
        # Status Polling
        self.device_check_timer = QTimer()
        self.device_check_timer.timeout.connect(self.check_device_status)
        self.device_check_timer.start(2000) # Check every 2s

    def setup_ui(self):
        main_h_layout = QHBoxLayout()
        
        # --- Left Side: Controls ---
        left_panel = QWidget()
        main_layout = QVBoxLayout(left_panel)
        main_layout.setSpacing(15)
        
        # --- Top Section ---
        header_layout = QHBoxLayout()
        
        # Logo
        logo_label = QLabel()
        logo_path = os.path.join(self.app_root, "aio.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            logo_label.setPixmap(pixmap.scaled(150, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        header_layout.addWidget(logo_label)
        header_layout.addSpacing(10)
        
        title = QLabel("Keybox Flashing & CSR Extraction Station")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header_layout.addWidget(title)
        
        self.status_label = QLabel("🔴 Device Disconnected")
        self.status_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.status_label.setStyleSheet("color: red;")
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)

        # Manual flash is triggered by clicking the Connected Devices area.
        
        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.create_separator())

        # --- Action Section ---
        action_layout = QHBoxLayout()
        self.start_btn = QPushButton("START FLASHING")
        self.start_btn.setFont(QFont("Arial", 14, QFont.Bold))
        self.start_btn.setMinimumHeight(45)
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white; border-radius: 5px;")
        self.start_btn.clicked.connect(self.start_process)
        action_layout.addWidget(self.start_btn)
        
        self.abort_btn = QPushButton("ABORT")
        self.abort_btn.setFont(QFont("Arial", 14, QFont.Bold))
        self.abort_btn.setMinimumHeight(45)
        self.abort_btn.setStyleSheet("background-color: #F44336; color: white; border-radius: 5px;")
        self.abort_btn.setEnabled(False)
        self.abort_btn.clicked.connect(self.abort_process)
        action_layout.addWidget(self.abort_btn)
        
        main_layout.addLayout(action_layout)
        
        # Keybox Progress Bar
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setFormat("Keybox Progress: %p%")
        main_layout.addWidget(self.progress)

        main_layout.addWidget(self.create_separator())

        # --- Log Section ---
        self.log_group = QGroupBox("Execution Logs")
        log_group_layout = QVBoxLayout()
        log_toolbar_layout = QHBoxLayout()
        log_toolbar_layout.addStretch()

        self.clear_logs_btn = QPushButton("Clear Logs")
        self.clear_logs_btn.setStyleSheet("background-color: #607D8B; color: white; padding: 5px; border-radius: 3px;")
        self.clear_logs_btn.clicked.connect(self.clear_logs)
        log_toolbar_layout.addWidget(self.clear_logs_btn)
        log_group_layout.addLayout(log_toolbar_layout)

        self.log_stack = QStackedWidget()

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 10))
        # Use white logs on a dark background; error lines will be colored red
        self.log.setStyleSheet("background-color: #1E1E1E; color: #FFFFFF;")
        self.log_stack.addWidget(self.log)

        self.device_logs_scroll = QScrollArea()
        self.device_logs_scroll.setWidgetResizable(True)
        self.device_logs_container = QWidget()
        self.device_logs_grid = QGridLayout(self.device_logs_container)
        self.device_logs_grid.setContentsMargins(0, 0, 0, 0)
        self.device_logs_grid.setSpacing(8)
        self.device_logs_scroll.setWidget(self.device_logs_container)
        self.log_stack.addWidget(self.device_logs_scroll)
        self.log_stack.setCurrentWidget(self.log)

        log_group_layout.addWidget(self.log_stack)
        self.log_group.setLayout(log_group_layout)

        # Live status table (tick/cross summary)
        self.status_table_group = QGroupBox("Live Status Table")
        status_table_layout = QVBoxLayout()
        self.status_table = QTableWidget(0, 4)
        self.status_table.setHorizontalHeaderLabels(["SN", "KeyBox Flashed", "CSR Generated", "CSR Pulled"])
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.status_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.status_table.setFocusPolicy(Qt.NoFocus)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.horizontalHeader().setStretchLastSection(True)
        self.status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.status_table.setStyleSheet(
            "QTableWidget {"
            "background-color: #0B1220;"
            "alternate-background-color: #121A2B;"
            "color: #E2E8F0;"
            "gridline-color: #334155;"
            "font-size: 12px;"
            "font-weight: 600;"
            "}"
            "QHeaderView::section {"
            "background-color: #1E293B;"
            "color: #F8FAFC;"
            "font-size: 12px;"
            "font-weight: 700;"
            "padding: 4px;"
            "border: 1px solid #334155;"
            "}"
        )
        status_table_layout.addWidget(self.status_table)
        self.status_table_group.setLayout(status_table_layout)
        self.status_table_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.status_table_group.setMinimumHeight(190)
        self.adjust_status_table_panel_width()
        main_layout.addWidget(self.log_group, 1)
        
        main_layout.addWidget(self.create_separator())

        # --- EDL Flashing Section (Now at bottom) ---
        self.edl_flash_btn = QPushButton("FLASH USER FIRMWARE")
        self.edl_flash_btn.setFont(QFont("Arial", 14, QFont.Bold))
        self.edl_flash_btn.setMinimumHeight(45)
        self.edl_flash_btn.setStyleSheet("background-color: #9C27B0; color: white; border-radius: 5px;")
        self.edl_flash_btn.setEnabled(True) # Enabled by default now
        self.edl_flash_btn.clicked.connect(self.start_edl_flash)
        self.edl_flash_btn.setVisible(False)
        main_layout.addWidget(self.edl_flash_btn)

        self.qdl_progress = QProgressBar()
        self.qdl_progress.setValue(0)
        self.qdl_progress.setTextVisible(True)
        self.qdl_progress.setFormat("QDL Progress: %p%")
        main_layout.addWidget(self.qdl_progress)
 
        main_h_layout.addWidget(left_panel, 70)
        
        # --- Right Side: Status Sidebar ---
        self.sidebar = QGroupBox("Process Status")
        sidebar_layout = QVBoxLayout()
        
        self.stages = {
            "Serial No Matched": StageIndicator("Serial No Matched"),
            "Keybox Flashed": StageIndicator("Keybox Flashed"),
            "CSR Pulled": StageIndicator("CSR Pulled")
        }
        
        self.process_label = QLabel("Currently Processing: None")
        self.process_label.setFont(QFont("Arial", 10, QFont.Bold))
        self.process_label.setStyleSheet("color: #FF9800;")
        sidebar_layout.addWidget(self.process_label)
        
        self.sub_status_label = QLabel("Status: Idle")
        self.sub_status_label.setFont(QFont("Arial", 9))
        self.sub_status_label.setStyleSheet("color: #9E9E9E;")
        sidebar_layout.addWidget(self.sub_status_label)
        
        sidebar_layout.addWidget(self.create_separator())
        
        # Connected Devices Section (Key flashing mode)
        self.connected_devices_group = QGroupBox("Connected Devices Status")
        connected_devices_layout = QVBoxLayout(self.connected_devices_group)
        connected_devices_layout.setContentsMargins(8, 8, 8, 8)
        connected_devices_layout.setSpacing(8)

        self.devices_layout = QVBoxLayout()
        self.devices_layout.setContentsMargins(0, 0, 0, 0)
        self.devices_layout.setSpacing(6)
        self.devices_layout.setAlignment(Qt.AlignTop)
        self.device_indicators = {} # serial -> StageIndicator
        connected_devices_layout.addLayout(self.devices_layout)
        connected_devices_layout.addWidget(self.status_table_group)

        # Manual Flash popup (hidden). Triggered from header 'Manual Flash' link.
        self.manual_popup = QFrame(self, Qt.Popup)
        self.manual_popup.setStyleSheet(
            "background-color: #0B1220; border: 1px solid #334155; border-radius: 8px;"
        )
        popup_layout = QVBoxLayout(self.manual_popup)
        popup_layout.setContentsMargins(12, 12, 12, 12)
        popup_layout.setSpacing(8)

        title_lbl = QLabel("Flash User Firmware")
        title_lbl.setFont(QFont("Arial", 11, QFont.Bold))
        title_lbl.setStyleSheet("color: #E2E8F0;")
        popup_layout.addWidget(title_lbl)

        self.manual_device_list = QListWidget()
        self.manual_device_list.setSelectionMode(QAbstractItemView.MultiSelection)
        popup_layout.addWidget(self.manual_device_list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.manual_popup_flash_btn = QPushButton("Flash User Firmware")
        self.manual_popup_flash_btn.setStyleSheet(
            "background-color: #9C27B0; color: white; border-radius: 5px; padding: 6px 12px;"
        )
        self.manual_popup_flash_btn.clicked.connect(self._manual_popup_flash_selected)
        btn_row.addWidget(self.manual_popup_flash_btn)

        self.manual_popup_cancel_btn = QPushButton("Cancel")
        self.manual_popup_cancel_btn.setStyleSheet(
            "background-color: #607D8B; color: white; border-radius: 5px; padding: 6px 12px;"
        )
        self.manual_popup_cancel_btn.clicked.connect(lambda: self.manual_popup.hide())
        btn_row.addWidget(self.manual_popup_cancel_btn)
        popup_layout.addLayout(btn_row)

        self.manual_popup.setVisible(False)

        # Make status label clickable to open manual flash popup
        self.status_label.setCursor(Qt.PointingHandCursor)
        self.status_label.installEventFilter(self)
        
        # Firmware Status Section (Firmware flashing mode)
        self.firmware_status_group = QGroupBox("Firmware Flash Status")
        firmware_status_layout = QVBoxLayout(self.firmware_status_group)
        self.firmware_status_table = QTableWidget(0, 4)
        self.firmware_status_table.setHorizontalHeaderLabels(["EDL Serial", "Current Image", "Progress", "State"])
        self.firmware_status_table.verticalHeader().setVisible(False)
        self.firmware_status_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.firmware_status_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.firmware_status_table.setFocusPolicy(Qt.NoFocus)
        self.firmware_status_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.firmware_status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.firmware_status_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.firmware_status_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        firmware_status_layout.addWidget(self.firmware_status_table)

        self.sidebar_mode_stack = QStackedWidget()
        self.sidebar_mode_stack.addWidget(self.connected_devices_group)
        self.sidebar_mode_stack.addWidget(self.firmware_status_group)
        self.sidebar_mode_stack.setCurrentWidget(self.connected_devices_group)
        sidebar_layout.addWidget(self.sidebar_mode_stack)

        sidebar_layout.addStretch()
        self.sidebar.setLayout(sidebar_layout)
        main_h_layout.addWidget(self.sidebar, 30)
        
        self.setLayout(main_h_layout)

    def create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line

    def show_connected_devices_panel(self):
        if hasattr(self, "sidebar_mode_stack"):
            self.sidebar_mode_stack.setCurrentWidget(self.connected_devices_group)

    def show_firmware_status_panel(self):
        if hasattr(self, "sidebar_mode_stack"):
            self.sidebar_mode_stack.setCurrentWidget(self.firmware_status_group)

    def reset_firmware_status_table(self):
        self.firmware_status_table.setRowCount(0)
        self.firmware_status_row_map = {}

    def ensure_firmware_status_row(self, serial):
        if serial in self.firmware_status_row_map:
            return self.firmware_status_row_map[serial]

        row = self.firmware_status_table.rowCount()
        self.firmware_status_table.insertRow(row)
        self.firmware_status_row_map[serial] = row

        serial_item = QTableWidgetItem(serial)
        serial_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.firmware_status_table.setItem(row, 0, serial_item)
        self.firmware_status_table.setItem(row, 1, QTableWidgetItem("Queued"))
        self.firmware_status_table.setItem(row, 2, QTableWidgetItem("0%"))
        self.firmware_status_table.setItem(row, 3, QTableWidgetItem("QUEUED"))
        return row

    def set_firmware_status_targets(self, serials):
        self.reset_firmware_status_table()
        for serial in serials:
            self.ensure_firmware_status_row(serial)

    def update_firmware_status(self, serial, progress=None, state=None, image=None):
        row = self.ensure_firmware_status_row(serial)
        if image is not None:
            item = QTableWidgetItem(str(image))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.firmware_status_table.setItem(row, 1, item)
        if progress is not None:
            item = QTableWidgetItem(f"{int(progress)}%")
            item.setTextAlignment(Qt.AlignCenter)
            self.firmware_status_table.setItem(row, 2, item)
        if state is not None:
            item = QTableWidgetItem(str(state).upper())
            item.setTextAlignment(Qt.AlignCenter)
            self.firmware_status_table.setItem(row, 3, item)

    @staticmethod
    def normalize_identity_value(value):
        text = str(value or "").strip()
        return text if text else "n/a"

    def resolve_identity_for_serial(self, serial, usb_path=None, usb_to_hw=None):
        existing = self.device_process_state.get(serial, {})
        identity = build_device_identity(
            serial,
            usb_path=usb_path,
            usb_hw_map=usb_to_hw,
            sw_serial=existing.get("sw_serial"),
        )
        for field in ("adb_serial", "usb_path", "hw_serial", "sw_serial", "aio_serial"):
            current_value = identity.get(field)
            fallback_value = existing.get(field)
            if current_value in (None, "", "n/a") and fallback_value:
                identity[field] = fallback_value
        return identity

    def device_display_title(self, serial):
        state = self.device_process_state.get(serial, {})
        aio_serial = self.normalize_identity_value(state.get("aio_serial"))
        hw_serial = self.normalize_identity_value(state.get("hw_serial"))
        title_aio = aio_serial if aio_serial != "n/a" else serial
        return f"AIO: {title_aio} | HW: {hw_serial}"

    def apply_device_identity_to_state(self, serial, identity):
        self._ensure_device_process_state(serial)
        state = self.device_process_state[serial]
        state["adb_serial"] = self.normalize_identity_value(identity.get("adb_serial", serial))
        state["usb_path"] = self.normalize_identity_value(identity.get("usb_path"))
        state["hw_serial"] = self.normalize_identity_value(identity.get("hw_serial"))
        state["sw_serial"] = self.normalize_identity_value(identity.get("sw_serial"))
        state["aio_serial"] = self.normalize_identity_value(identity.get("aio_serial"))

        indicator = self.device_indicators.get(serial)
        if indicator:
            indicator.label.setText(self.device_display_title(serial))
            indicator.set_identity_fields(
                hw_serial=state["hw_serial"],
                sw_serial=state["sw_serial"],
                aio_serial=state["aio_serial"],
            )

    def format_identity_summary(self, entry):
        aio_serial = self.normalize_identity_value(entry.get("aio_serial") or entry.get("serial"))
        hw_serial = self.normalize_identity_value(entry.get("hw_serial"))
        sw_serial = self.normalize_identity_value(entry.get("sw_serial"))
        return f"AIO: {aio_serial} | HW: {hw_serial} | SW: {sw_serial}"

    def _log_color_for_text(self, text):
        # Use word-boundary checks to avoid accidental matches inside other words
        lower = (text or "").lower()
        if text and "❌" in text:
            return "#F87171"
        # match standalone error/fail/failed words
        if re.search(r"\b(error|failed|fail)\b", lower):
            return "#F87171"
        # explicit pass markers
        if re.search(r"\b(pass|passed|success|ok|done|completed)\b", lower):
            return "#22C55E"
        return None

    def _append_colored_log(self, view, text, normal_color):
        color = self._log_color_for_text(text) or normal_color
        view.setTextColor(QColor(color))
        view.append(text)
        # reset color back to normal for subsequent non-colored inserts
        view.setTextColor(QColor(normal_color))

    def log_msg(self, msg):
        text = str(msg)
        # default logs in white, errors will be colored red by _log_color_for_text
        self._append_colored_log(self.log, text, "#FFFFFF")
        self._append_to_session_log(text)

        if text.startswith("[EDL:"):
            closing = text.find("]")
            if closing > 5:
                edl_serial = text[5:closing].strip()
                line = text[closing + 1:].strip() or text
                if edl_serial in self.device_log_views:
                    self._append_colored_log(self.device_log_views[edl_serial], line, "#90EE90")
        elif text.startswith("["):
            closing = text.find("]")
            if closing > 1:
                serial = text[1:closing].strip()
                line = text[closing + 1:].strip() or text
                if serial in self.device_log_views:
                    self._append_colored_log(self.device_log_views[serial], line, "#90EE90")

    def _get_log_file_path(self, prefix, serials=None):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        serial_part = "" if not serials else "_" + "-".join([str(s).replace("/", "-") for s in (serials if isinstance(serials, (list, tuple)) else [serials])][:3])
        file_name = f"{prefix}_{timestamp}{serial_part}.log"
        return os.path.join(self.log_folder, file_name)

    def _create_log_file(self, prefix, serials=None):
        log_path = self._get_log_file_path(prefix, serials)
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"=== Session Log - {datetime.datetime.now().isoformat()} ===\n")
        except Exception:
            pass
        self.session_log_file = log_path
        return log_path

    def _append_to_session_log(self, message):
        if not self.session_log_file:
            return
        try:
            with open(self.session_log_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} {message}\n")
        except Exception:
            pass

    def log_msg_for_device(self, serial, msg):
        self._append_colored_log(self.log, f"[{serial}] {msg}", "#FFFFFF")
        log_view = self.device_log_views.get(serial)
        if log_view:
            self._append_colored_log(log_view, msg, "#FFFFFF")
        self._append_to_session_log(f"[{serial}] {msg}")

    def clear_device_log_grid(self):
        while self.device_logs_grid.count():
            item = self.device_logs_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.device_log_views = {}
        self.current_device_log_serials = []

    def build_device_log_grid(self, serials):
        serials = list(serials[:8])
        if serials == self.current_device_log_serials:
            if serials:
                self.log_stack.setCurrentWidget(self.device_logs_scroll)
            else:
                self.log_stack.setCurrentWidget(self.log)
            return

        preserved_logs = {}
        for serial, view in self.device_log_views.items():
            if serial in serials:
                preserved_logs[serial] = view.toPlainText()

        self.clear_device_log_grid()
        if not serials:
            self.log_stack.setCurrentWidget(self.log)
            return

        total = len(serials)
        if total <= 1:
            columns = 1
        elif total <= 4:
            columns = 2
        else:
            columns = 3

        for idx, serial in enumerate(serials):
            tile = QGroupBox(f"SN: {serial}")
            tile.setStyleSheet(
                "QGroupBox {"
                "margin-top: 16px;"
                "padding-top: 8px;"
                "font-size: 11px;"
                "font-weight: 700;"
                "}"
                "QGroupBox::title {"
                "subcontrol-origin: margin;"
                "subcontrol-position: top left;"
                "left: 10px;"
                "padding: 4px 8px 6px 8px;"
                "}"
            )
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(8, 12, 8, 8)
            tile_layout.setSpacing(4)

            text = QTextEdit()
            text.setReadOnly(True)
            text.setFont(QFont("Consolas", 9))
            # Device logs use white text by default; errors highlighted red by logic
            text.setStyleSheet("background-color: #121212; color: #FFFFFF;")
            if serial in preserved_logs and preserved_logs[serial]:
                text.setPlainText(preserved_logs[serial])
            tile_layout.addWidget(text)
            self.device_log_views[serial] = text

            row = idx // columns
            col = idx % columns
            self.device_logs_grid.addWidget(tile, row, col)

        self.current_device_log_serials = serials
        self.log_stack.setCurrentWidget(self.device_logs_scroll)

    def update_parallel_progress_bar(self):
        if not self.parallel_device_progress:
            self.progress.setValue(0)
            return
        avg = int(sum(self.parallel_device_progress.values()) / len(self.parallel_device_progress))
        self.progress.setValue(max(0, min(avg, 100)))

    def is_any_flasher_running(self):
        single_running = hasattr(self, "flasher_thread") and self.flasher_thread.isRunning()
        if single_running:
            return True
        for thread in self.parallel_flasher_threads.values():
            if thread.isRunning():
                return True
        return False
        
    def set_stage_status(self, stage_name, state):
        if stage_name in self.stages:
            self.stages[stage_name].set_state(state)

    def clear_logs(self):
        """Clears the execution log view."""
        self.log.clear()
        for log_view in self.device_log_views.values():
            log_view.clear()

    def set_firmware_device_targets(self, serials):
        self.set_firmware_status_targets(serials)
        self.build_device_log_grid(serials)

    def update_firmware_device_progress(self, serial, progress, state):
        self.update_firmware_status(serial, progress=progress, state=state)

    def update_firmware_device_image(self, serial, image):
        self.update_firmware_status(serial, image=image)

    def check_device_status(self):
        """Periodically check all connected devices."""
        adb_devices = get_adb_devices_with_usb()[:8]
        serials = [d["serial"] for d in adb_devices]
        edl_serials = get_all_edl_serials()[:8]
        actual_serials = set(serials)
        fw_running = hasattr(self, "fw_thread") and self.fw_thread.isRunning()
        flasher_running = self.is_any_flasher_running()
        csr_running = hasattr(self, "csr_thread") and self.csr_thread.isRunning()

        if serials or edl_serials:
            adb_count = len(serials)
            self.status_label.setText(f"🟢 {adb_count} ADB devices connected")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("🔴 Device Disconnected")
            self.status_label.setStyleSheet("color: red;")

        # Keep execution logs in sync only while no flashing flow is active to avoid layout flicker.
        if not fw_running and not flasher_running and not csr_running:
            self.build_device_log_grid(serials)

        # Auto-generate keybox for newly connected devices.
        new_serials = actual_serials - self.seen_connected_serials
        for serial in sorted(new_serials):
            self.ensure_keybox_for_device(serial)

        self.generated_keyboxes.intersection_update(actual_serials)
        self.failed_keybox_generation.intersection_update(actual_serials)
        self.seen_connected_serials = actual_serials

        # Keep sidebar device list synced while no flasher is running.
        if not flasher_running and not csr_running and not fw_running:
            expected_ui_keys = set(serials) | {f"EDL:{s}" for s in edl_serials}
            current_ui_keys = set(self.device_indicators.keys())
            if current_ui_keys != expected_ui_keys:
                self.reset_device_list(adb_devices, edl_serials)

        self.last_known_serial = serials[0] if serials else None

    def serial_matches_required_pattern(self, serial):
        serial_text = str(serial or "").strip()
        return (
            serial_text.startswith(FlasherThread.SERIAL_PREFIX)
            and len(serial_text) >= (len(FlasherThread.SERIAL_PREFIX) + FlasherThread.SERIAL_MIN_SUFFIX_LENGTH)
        )

    def ensure_keybox_for_device(self, serial):
        if serial in self.generated_keyboxes or serial in self.failed_keybox_generation:
            return

        if not self.serial_matches_required_pattern(serial):
            self.log_msg(
                f"⚠️ {serial}: Serial does not match {FlasherThread.SERIAL_PATTERN_LABEL}. Keybox not generated."
            )
            self.failed_keybox_generation.add(serial)
            self.update_device_process_details(
                serial,
                current="Invalid serial pattern",
                result="FAIL",
                append_event="FAIL: Serial pattern mismatch",
                keybox_ready_status="Invalid Serial",
                keybox_flashed_status="Skipped",
                csr_generated_status="Skipped",
                csr_pulled_status="Skipped"
            )
            return

        keybox_dir = os.path.join(self.data_root, "keyboxes")
        direct_path = os.path.join(keybox_dir, f"{serial}.xml")
        if os.path.exists(direct_path):
            self.generated_keyboxes.add(serial)
            self.log_msg(f"Keybox ready for {serial}: {direct_path}")
            self.update_device_process_details(
                serial,
                current="Keybox ready",
                result="WAITING",
                append_event="INFO: Keybox file found",
                keybox_ready_status="Found"
            )
            return

        generated = generate_keybox_from_standard(serial, keybox_dir)
        if generated:
            self.generated_keyboxes.add(serial)
            self.log_msg(f"Auto-generated keybox for {serial}: {generated}")
            self.update_device_process_details(
                serial,
                current="Keybox generated",
                result="WAITING",
                append_event="INFO: Keybox generated from standard.xml",
                keybox_ready_status="Generated"
            )
        else:
            self.failed_keybox_generation.add(serial)
            standard_path = os.path.join(keybox_dir, "standard.xml")
            self.log_msg(f"❌ Failed to auto-generate keybox for {serial}. Missing or invalid {standard_path}.")
            self.update_device_process_details(
                serial,
                current="Keybox generation failed",
                result="FAIL",
                append_event="FAIL: Could not generate keybox",
                keybox_ready_status="Failed",
                keybox_flashed_status="Skipped",
                csr_generated_status="Skipped",
                csr_pulled_status="Skipped"
            )

    def set_device_action_buttons_enabled(self, enabled):
        for indicator in self.device_indicators.values():
            indicator.set_action_enabled(enabled)

    def _ensure_device_process_state(self, serial):
        if serial not in self.device_process_state:
            self.device_process_state[serial] = {
                "serial": serial,
                "adb_serial": serial,
                "usb_path": "n/a",
                "hw_serial": "n/a",
                "sw_serial": "n/a",
                "aio_serial": "n/a",
                "keybox_ready_status": "Pending",
                "keybox_flashed_status": "Pending",
                "csr_generated_status": "Pending",
                "csr_pulled_status": "Pending",
                "current": "Idle",
                "result": "Waiting",
                "history": []
            }

    def _refresh_device_details_ui(self, serial):
        indicator = self.device_indicators.get(serial)
        state = self.device_process_state.get(serial)
        if not indicator or not state:
            return

        indicator.label.setText(self.device_display_title(serial))
        indicator.set_identity_fields(
            hw_serial=state.get("hw_serial", "n/a"),
            sw_serial=state.get("sw_serial", "n/a"),
            aio_serial=state.get("aio_serial", "n/a"),
        )
        indicator.clear_process_details()
        indicator.set_progress_fields(
            keybox_ready_status=state.get("keybox_ready_status", "Pending"),
            keybox_flashed_status=state.get("keybox_flashed_status", "Pending"),
            csr_generated_status=state.get("csr_generated_status", "Pending"),
            csr_pulled_status=state.get("csr_pulled_status", "Pending")
        )

    def _status_symbol_and_color(self, status_value):
        value = (status_value or "").strip().lower()
        if value in {"done", "pass", "flashed", "found", "generated", "ready"}:
            return "✓", "#22C55E"
        if value in {"failed", "fail", "invalid serial", "skipped"}:
            return "✗", "#F87171"
        if value in {"running", "flashing"}:
            return "…", "#38BDF8"
        return "-", "#94A3B8"

    def adjust_status_table_panel_width(self):
        self.status_table.resizeColumnsToContents()
        self.status_table.setMinimumWidth(0)
        self.status_table.setMaximumWidth(16777215)
        self.status_table_group.setMinimumWidth(0)
        self.status_table_group.setMaximumWidth(16777215)

    def ensure_status_table_row(self, serial):
        if serial in self.status_table_row_map:
            return self.status_table_row_map[serial]

        row = self.status_table.rowCount()
        self.status_table.insertRow(row)
        self.status_table_row_map[serial] = row

        serial_item = QTableWidgetItem(serial)
        serial_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        serial_item.setForeground(QColor("#F8FAFC"))
        self.status_table.setItem(row, 0, serial_item)
        # Keep SN column sized from actual serial content (not only header text).
        required_width = self.status_table.fontMetrics().horizontalAdvance(serial) + 28
        current_width = self.status_table.columnWidth(0)
        self.status_table.setColumnWidth(0, max(required_width, current_width))
        self.adjust_status_table_panel_width()
        self.status_table.setRowHeight(row, 24)
        return row

    def _set_status_table_cell(self, row, col, status_value):
        symbol, color = self._status_symbol_and_color(status_value)
        item = QTableWidgetItem(symbol)
        item.setTextAlignment(Qt.AlignCenter)
        item.setForeground(QColor(color))
        font = item.font()
        font.setBold(True)
        font.setPointSize(13)
        item.setFont(font)
        self.status_table.setItem(row, col, item)

    def refresh_status_table_row(self, serial):
        state = self.device_process_state.get(serial)
        if not state:
            return
        row = self.ensure_status_table_row(serial)
        self._set_status_table_cell(row, 1, state.get("keybox_flashed_status", "Pending"))
        self._set_status_table_cell(row, 2, state.get("csr_generated_status", "Pending"))
        self._set_status_table_cell(row, 3, state.get("csr_pulled_status", "Pending"))
        self.adjust_status_table_panel_width()

    def rebuild_status_table(self, serials):
        self.status_table.setRowCount(0)
        self.status_table_row_map = {}
        for serial in serials:
            self.ensure_status_table_row(serial)
            self.refresh_status_table_row(serial)

    def update_device_process_details(
        self,
        serial,
        current=None,
        result=None,
        append_event=None,
        keybox_ready_status=None,
        keybox_flashed_status=None,
        keybox_status=None,
        csr_generated_status=None,
        csr_pulled_status=None
    ):
        self._ensure_device_process_state(serial)
        state = self.device_process_state[serial]

        # Backward compatibility for previous callers that used keybox_status.
        if keybox_ready_status is None and keybox_status is not None:
            keybox_ready_status = keybox_status

        if current is not None:
            state["current"] = current
        if result is not None:
            state["result"] = result
        if keybox_ready_status is not None:
            state["keybox_ready_status"] = keybox_ready_status
        if keybox_flashed_status is not None:
            state["keybox_flashed_status"] = keybox_flashed_status
        if csr_generated_status is not None:
            state["csr_generated_status"] = csr_generated_status
        if csr_pulled_status is not None:
            state["csr_pulled_status"] = csr_pulled_status
        if append_event:
            if not state["history"] or state["history"][-1] != append_event:
                state["history"].append(append_event)
            state["history"] = state["history"][-6:]

        self._refresh_device_details_ui(serial)
        self.refresh_status_table_row(serial)

    def update_device_step_status(self, serial, step, status):
        status_upper = status.upper()
        if status == "running":
            result = "RUNNING"
            event = f"RUNNING: {step}"
        elif status == "pass":
            result = "PASS"
            event = f"PASS: {step}"
        elif status == "fail":
            result = "FAIL"
            event = f"FAIL: {step}"
        else:
            result = status_upper
            event = f"{status_upper}: {step}"
        step_lower = step.lower()
        keybox_ready_status = None
        keybox_flashed_status = None
        csr_generated_status = None
        csr_pulled_status = None

        if "keybox generated" in step_lower:
            keybox_ready_status = "Generated" if status != "fail" else "Failed"
        elif "keybox found" in step_lower:
            keybox_ready_status = "Found" if status != "fail" else "Failed"
        elif "keybox skipped" in step_lower:
            keybox_flashed_status = "Skipped"
        elif "invalid serial pattern" in step_lower:
            keybox_ready_status = "Invalid Serial"
            keybox_flashed_status = "Skipped"
            csr_generated_status = "Skipped"
            csr_pulled_status = "Skipped"
        elif "flashing keybox" in step_lower:
            if status == "running":
                keybox_flashed_status = "Running"
            elif status == "fail":
                keybox_flashed_status = "Failed"
        elif "keybox flashed" in step_lower:
            if status == "pass":
                keybox_flashed_status = "Done"
            elif status == "fail":
                keybox_flashed_status = "Failed"
        elif "keybox" in step_lower and status == "fail":
            keybox_flashed_status = "Failed"

        if "generating csr" in step_lower:
            csr_generated_status = "Running" if status != "fail" else "Failed"
        elif "csr generated" in step_lower:
            if status == "pass":
                csr_generated_status = "Done"
            elif status == "fail":
                csr_generated_status = "Failed"

        if "pulling csr" in step_lower:
            csr_pulled_status = "Running" if status != "fail" else "Failed"
        elif "csr pulled to pc" in step_lower:
            if status == "running":
                csr_pulled_status = "Running"
            elif status == "pass":
                csr_pulled_status = "Done"
            elif status == "fail":
                csr_pulled_status = "Failed"
        elif "csr pull" in step_lower and status == "fail":
            csr_pulled_status = "Failed"
        elif "csr" in step_lower and status == "fail":
            csr_generated_status = "Failed"
        elif "csr pre-check unavailable" in step_lower:
            csr_generated_status = "Pending"
            csr_pulled_status = "Pending"

        if "device not ready within" in step_lower:
            keybox_ready_status = "Skipped"
            keybox_flashed_status = "Skipped"
            csr_generated_status = "Skipped"
            csr_pulled_status = "Skipped"

        self.update_device_process_details(
            serial,
            current=step,
            result=result,
            append_event=event,
            keybox_ready_status=keybox_ready_status,
            keybox_flashed_status=keybox_flashed_status,
            csr_generated_status=csr_generated_status,
            csr_pulled_status=csr_pulled_status
        )

    def reset_device_list(self, adb_devices, edl_serials):
        """Clears and rebuilds the device indicators list."""
        adb_devices = adb_devices[:8]
        edl_serials = edl_serials[:8]
        serials = [d["serial"] for d in adb_devices]
        usb_to_hw = get_usb_hw_serial_map()
        preserved_state = {}
        usb_by_serial = {device["serial"]: device.get("usb") for device in adb_devices}
        for serial in serials:
            state = dict(
                self.device_process_state.get(
                    serial,
                    {
                        "serial": serial,
                        "adb_serial": serial,
                        "usb_path": "n/a",
                        "hw_serial": "n/a",
                        "sw_serial": "n/a",
                        "aio_serial": "n/a",
                        "keybox_ready_status": "Pending",
                        "keybox_flashed_status": "Pending",
                        "csr_generated_status": "Pending",
                        "csr_pulled_status": "Pending",
                        "current": "Idle",
                        "result": "Waiting",
                        "history": []
                    }
                )
            )
            state.update(
                self.resolve_identity_for_serial(serial, usb_path=usb_by_serial.get(serial), usb_to_hw=usb_to_hw)
            )
            preserved_state[serial] = state

        for i in reversed(range(self.devices_layout.count())): 
            self.devices_layout.itemAt(i).widget().setParent(None)
        self.device_indicators = {}
        self.device_process_state = preserved_state
        self.rebuild_status_table(serials)
        
        for device in adb_devices:
            s = device["serial"]
            indicator = StageIndicator(
                self.device_display_title(s),
                action_callback=lambda checked=False, serial=s: self.generate_csr_for_device(serial),
                action_text="Generate CSR",
                secondary_action_callback=lambda checked=False, serial=s: self.install_keybox_for_device(serial),
                secondary_action_text="Install Keybox",
                tertiary_action_callback=lambda checked=False, serial=s: self.start_edl_flash(adb_targets=[serial]),
                tertiary_action_text="Flash Firmware",
                expandable=True
            )
            indicator.set_state("blue")
            self.devices_layout.addWidget(indicator)
            self.device_indicators[s] = indicator
            self._ensure_device_process_state(s)
            self.apply_device_identity_to_state(s, self.device_process_state.get(s, {}))
            self._refresh_device_details_ui(s)

        for edl_serial in edl_serials:
            indicator = StageIndicator(
                f"EDL: {edl_serial}",
                action_callback=lambda checked=False, serial=edl_serial: self.start_edl_flash(edl_targets=[serial]),
                action_text="Flash Firmware",
                expandable=False
            )
            indicator.set_state("edl")
            indicator.label.setStyleSheet("color: #F59E0B; font-weight: 700;")
            self.devices_layout.addWidget(indicator)
            self.device_indicators[f"EDL:{edl_serial}"] = indicator

    def update_device_ui_status(self, serial, state):
        """Updates the specific circular/bar indicator for a device."""
        if serial in self.device_indicators:
            self.device_indicators[serial].set_state(state)
            if state == "blinking":
                self.process_label.setText(f"Currently Processing: {serial}")
                self.update_device_process_details(serial, result="RUNNING")
            elif state == "green":
                self.update_device_process_details(serial, result="PASS")
            elif state == "red":
                self.update_device_process_details(serial, result="FAIL")

    def update_processing_activity(self, serial, activity):
        if serial == "ALL":
            self.process_label.setText("Currently Processing: Multi-Device Session")
        elif serial:
            self.process_label.setText(f"Currently Processing: {serial}")
            self.update_device_process_details(serial, current=activity, result="RUNNING", append_event=f"RUNNING: {activity}")
        else:
            self.process_label.setText("Currently Processing: None")
        self.sub_status_label.setText(f"Status: {activity}")

    def reset_ui_indicators(self):
        """Resets all progress bars and stage indicators to their initial state."""
        self.progress.setValue(0)
        self.qdl_progress.setValue(0)
        for stage in self.stages.values():
            stage.set_state("blue")
        self.process_label.setText("Currently Processing: None")
        self.sub_status_label.setText("Status: Idle")
        
        # Clear device indicators
        for i in reversed(range(self.devices_layout.count())): 
            self.devices_layout.itemAt(i).widget().setParent(None)
        self.device_indicators = {}
        self.device_process_state = {}
        self.status_table.setRowCount(0)
        self.status_table_row_map = {}

    def start_process(self):
        adb_devices = get_adb_devices_with_usb()[:8]
        serials = [device["serial"] for device in adb_devices]
        if not serials:
            QMessageBox.warning(self, "No Devices", "No devices detected via ADB. Please connect devices first.")
            return

        self.show_connected_devices_panel()

        session_start_ts = time.time()
        self.parallel_serials = list(serials)
        self.parallel_results = {}
        self.parallel_device_progress = {serial: 0 for serial in serials}
        self.parallel_completed_count = 0
        self.parallel_session_start_ts = session_start_ts
        self.parallel_flasher_threads = {}
        self.latest_firmware_results = []
        self.combined_firmware_context = None
        usb_to_hw = get_usb_hw_serial_map()

        for device in adb_devices:
            serial = device["serial"]
            identity = self.resolve_identity_for_serial(serial, usb_path=device.get("usb"), usb_to_hw=usb_to_hw)
            self.ensure_keybox_for_device(serial)
            self.device_process_state[serial] = {
                "serial": serial,
                "adb_serial": identity.get("adb_serial", serial),
                "usb_path": identity.get("usb_path", "n/a"),
                "hw_serial": identity.get("hw_serial", "n/a"),
                "sw_serial": identity.get("sw_serial", "n/a"),
                "aio_serial": identity.get("aio_serial", "n/a"),
                "keybox_ready_status": self.device_process_state.get(serial, {}).get("keybox_ready_status", "Pending"),
                "keybox_flashed_status": "Pending",
                "csr_generated_status": "Pending",
                "csr_pulled_status": "Pending",
                "current": "Queued for flashing",
                "result": "WAITING",
                "history": ["INFO: Queued for flashing"]
            }
            self._refresh_device_details_ui(serial)
            self.refresh_status_table_row(serial)

        # Disable UI elements during flash
        self.start_btn.setEnabled(False)
        self.start_btn.setText("FLASHING IN PROGRESS...")
        self.start_btn.setStyleSheet("background-color: #FF9800; color: white;")
        self.edl_flash_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.set_device_action_buttons_enabled(False)
        self.progress.setValue(0)
        self.qdl_progress.setValue(0)
        self.session_log_file = self._create_log_file("parallel_flash", serials)
        self.log.clear()
        self.build_device_log_grid(serials)
        
        # Reset indicators
        for stage in self.stages.values():
            stage.set_state("blue")
            
        self.log_msg("Initializing Parallel Multi-Device Flash Process...")

        for serial in serials:
            thread = FlasherThread(
                [serial],
                session_start_ts=session_start_ts,
                device_identity=dict(self.device_process_state.get(serial, {})),
            )
            self.parallel_flasher_threads[serial] = thread
            thread.log_signal.connect(lambda msg, s=serial: self.log_msg_for_device(s, msg))
            thread.progress_signal.connect(lambda value, s=serial: self.on_parallel_device_progress(s, value))
            thread.stage_signal.connect(self.set_stage_status)
            thread.device_signal.connect(self.update_device_ui_status)
            thread.activity_signal.connect(self.update_processing_activity)
            thread.device_step_signal.connect(self.update_device_step_status)
            thread.results_signal.connect(lambda results, s=serial: self.on_parallel_device_results(s, results))
            thread.finished_signal.connect(lambda success, msg, s=serial: self.on_parallel_device_finished(s, success, msg))
            thread.finished_signal.connect(thread.deleteLater)
            thread.start()

    def on_parallel_device_progress(self, serial, value):
        if serial not in self.parallel_device_progress:
            return
        self.parallel_device_progress[serial] = max(0, min(int(value), 100))
        self.update_parallel_progress_bar()

    def on_parallel_device_results(self, serial, results):
        if not isinstance(results, list) or not results:
            return
        for entry in results:
            if isinstance(entry, dict) and entry.get("serial") == serial:
                self.parallel_results[serial] = entry
                return
        first_entry = results[0]
        if isinstance(first_entry, dict):
            state = self.device_process_state.get(serial, {})
            self.parallel_results[serial] = {
                "serial": serial,
                "success": bool(first_entry.get("success")),
                "message": first_entry.get("message", "Completed"),
                "hw_serial": first_entry.get("hw_serial", state.get("hw_serial", "n/a")),
                "sw_serial": first_entry.get("sw_serial", state.get("sw_serial", "n/a")),
                "aio_serial": first_entry.get("aio_serial", state.get("aio_serial", serial)),
            }

    def on_parallel_device_finished(self, serial, success, result_msg):
        self.parallel_device_progress[serial] = 100
        self.update_parallel_progress_bar()

        if serial not in self.parallel_results:
            state = self.device_process_state.get(serial, {})
            self.parallel_results[serial] = {
                "serial": serial,
                "success": bool(success),
                "message": result_msg,
                "hw_serial": state.get("hw_serial", "n/a"),
                "sw_serial": state.get("sw_serial", "n/a"),
                "aio_serial": state.get("aio_serial", serial),
            }

        final_entry = self.parallel_results[serial]
        final_status = "PASS" if final_entry.get("success") else "FAIL"
        self.log_msg_for_device(serial, f"--- FINAL RESULT: {final_status} - {final_entry.get('message', result_msg)} ---")

        self.parallel_completed_count += 1
        if self.parallel_completed_count >= len(self.parallel_serials):
            self.finalize_parallel_flashing()

    def finalize_parallel_flashing(self):
        ordered_results = []
        for serial in self.parallel_serials:
            state = self.device_process_state.get(serial, {})
            ordered_results.append(
                self.parallel_results.get(
                    serial,
                    {
                        "serial": serial,
                        "success": False,
                        "message": "No terminal result captured.",
                        "hw_serial": state.get("hw_serial", "n/a"),
                        "sw_serial": state.get("sw_serial", "n/a"),
                        "aio_serial": state.get("aio_serial", serial),
                    }
                )
            )

        report = generate_session_report(ordered_results)
        elapsed_base = self.parallel_session_start_ts if self.parallel_session_start_ts is not None else time.time()
        elapsed = FlasherThread.format_elapsed(time.time() - elapsed_base)

        self.log_msg("--- Parallel Flashing Session Report ---")
        self.log_msg(report)
        self.log_msg(f"Processed devices in parallel: {len(ordered_results)}/{len(self.parallel_serials)}")
        self.log_msg(f"Total Elapsed Time (from START FLASHING click): {elapsed}")

        self.parallel_flasher_threads = {}
        eligible_results = [entry for entry in ordered_results if entry.get("success")]
        skipped_results = [entry for entry in ordered_results if not entry.get("success")]

        if eligible_results:
            self.log_msg("--- Devices Eligible For User Firmware ---")
            for entry in eligible_results:
                self.log_msg(f"{self.format_identity_summary(entry)} | READY FOR USER FIRMWARE")

        if skipped_results:
            self.log_msg("--- User Firmware Skipped For Failed Devices ---")
            for entry in skipped_results:
                self.log_msg(
                    f"{self.format_identity_summary(entry)} | SKIPPED | {entry.get('message', 'Unknown error')}"
                )

        eligible_serials = [entry["serial"] for entry in eligible_results]
        if not eligible_serials:
            self.on_process_finished(
                False,
                "No devices completed keybox/CSR successfully, so user firmware flashing was skipped.",
            )
            return

        self.log_msg(
            f"Starting automatic user firmware flashing for {len(eligible_serials)} eligible device(s)..."
        )
        self._begin_firmware_flash(
            adb_targets=eligible_serials,
            combined_context={
                "phase1_results": ordered_results,
                "eligible_results": eligible_results,
                "skipped_results": skipped_results,
            },
        )

    def on_firmware_results(self, results):
        self.latest_firmware_results = list(results) if isinstance(results, list) else []

    def _begin_firmware_flash(self, adb_targets=None, edl_targets=None, combined_context=None):
        adb_serials = []
        edl_serials = None
        allowed_edl_serials = []
        if edl_targets is not None:
            edl_serials = list(edl_targets)[:8]
        else:
            adb_serials = list(adb_targets)[:8] if adb_targets is not None else get_all_device_serials()[:8]
            if combined_context is not None:
                allowed_edl_serials = [
                    self.normalize_identity_value(entry.get("hw_serial"))
                    for entry in combined_context.get("eligible_results", [])
                ]
            else:
                allowed_edl_serials = [
                    self.normalize_identity_value(self.resolve_identity_for_serial(serial).get("hw_serial"))
                    for serial in adb_serials
                ]
            allowed_edl_serials = [serial for serial in allowed_edl_serials if serial != "n/a"]

        self.latest_firmware_results = []
        self.combined_firmware_context = combined_context
        self.show_firmware_status_panel()

        self.start_btn.setEnabled(False)
        if combined_context is not None:
            self.start_btn.setText("USER FIRMWARE IN PROGRESS...")
            self.start_btn.setStyleSheet("background-color: #673AB7; color: white;")

        self.edl_flash_btn.setEnabled(False)
        if combined_context is not None:
            self.edl_flash_btn.setText("USER FIRMWARE IN PROGRESS...")
        else:
            self.edl_flash_btn.setText("EDL FLASHING IN PROGRESS...")
        self.edl_flash_btn.setStyleSheet("background-color: #673AB7; color: white;")
        self.abort_btn.setEnabled(True)
        self.qdl_progress.setValue(0)

        if edl_serials is not None:
            self.set_firmware_device_targets(edl_serials)
            self.build_device_log_grid([])
        elif adb_serials:
            self.set_firmware_device_targets(adb_serials)
        else:
            self.reset_firmware_status_table()
            self.build_device_log_grid([])

        target_serials = edl_serials if edl_serials is not None else adb_serials
        if target_serials and combined_context is None:
            self.session_log_file = self._create_log_file("edl_firmware", target_serials)

        if combined_context is not None:
            self.log_msg("Initializing Automatic User Firmware Flash...")
        else:
            self.log_msg("Initializing Parallel EDL Firmware Flash...")

        self.fw_thread = FirmwareFlasherThread(
            "",
            adb_targets=adb_serials,
            edl_targets=edl_serials,
            allowed_edl_serials=allowed_edl_serials,
        )
        self.fw_thread.log_signal.connect(self.log_msg)
        self.fw_thread.progress_signal.connect(self.qdl_progress.setValue)
        self.fw_thread.stage_signal.connect(self.set_stage_status)
        self.fw_thread.results_signal.connect(self.on_firmware_results)
        self.fw_thread.device_list_signal.connect(self.set_firmware_device_targets)
        self.fw_thread.device_progress_signal.connect(self.update_firmware_device_progress)
        self.fw_thread.device_image_signal.connect(self.update_firmware_device_image)
        self.fw_thread.finished_signal.connect(self.on_edl_flash_finished)
        self.fw_thread.start()

    def _find_matching_firmware_result(self, keybox_entry, firmware_results, used_indexes):
        candidate_values = {
            self.normalize_identity_value(keybox_entry.get("serial")),
            self.normalize_identity_value(keybox_entry.get("aio_serial")),
            self.normalize_identity_value(keybox_entry.get("hw_serial")),
            self.normalize_identity_value(keybox_entry.get("sw_serial")),
        }
        candidate_values.discard("n/a")

        for idx, firmware_entry in enumerate(firmware_results):
            if idx in used_indexes:
                continue
            firmware_values = {
                self.normalize_identity_value(firmware_entry.get("serial")),
                self.normalize_identity_value(firmware_entry.get("edl_serial")),
            }
            firmware_values.discard("n/a")
            if candidate_values.intersection(firmware_values):
                used_indexes.add(idx)
                return firmware_entry
        return None

    def build_combined_start_results(self, keybox_results, firmware_results):
        firmware_results = list(firmware_results or [])
        used_indexes = set()
        combined_results = []

        for keybox_entry in keybox_results:
            final_entry = dict(keybox_entry)
            firmware_entry = None

            if keybox_entry.get("success"):
                firmware_entry = self._find_matching_firmware_result(keybox_entry, firmware_results, used_indexes)
                if firmware_entry:
                    final_entry["success"] = bool(firmware_entry.get("success"))
                    final_entry["message"] = (
                        "Keybox/CSR passed; User firmware: "
                        f"{firmware_entry.get('message', 'Completed')}"
                    )
                    final_entry["firmware_edl_serial"] = firmware_entry.get("serial", "n/a")
                else:
                    final_entry["success"] = False
                    final_entry["message"] = (
                        "Keybox/CSR passed; User firmware result could not be matched to this device."
                    )
                    final_entry["firmware_edl_serial"] = "n/a"
            else:
                final_entry["success"] = False
                final_entry["message"] = (
                    f"{keybox_entry.get('message', 'Keybox/CSR failed')} | User firmware skipped."
                )
                final_entry["firmware_edl_serial"] = "n/a"

            metadata_details = {
                "message": final_entry.get("message", ""),
                "hw_serial": final_entry.get("hw_serial", "n/a"),
                "sw_serial": final_entry.get("sw_serial", "n/a"),
                "aio_serial": final_entry.get("aio_serial", final_entry.get("serial", "n/a")),
                "firmware_edl_serial": final_entry.get("firmware_edl_serial", "n/a"),
                "firmware_status": "PASS" if keybox_entry.get("success") and final_entry.get("success") else (
                    "SKIPPED" if not keybox_entry.get("success") else "FAIL"
                ),
            }
            if not final_entry["success"]:
                metadata_details["error"] = final_entry.get("message", "")
            save_metadata(final_entry["serial"], final_entry["success"], metadata_details)
            combined_results.append(final_entry)

        unmatched_firmware = [
            entry for idx, entry in enumerate(firmware_results) if idx not in used_indexes
        ]
        return combined_results, unmatched_firmware

    def start_edl_flash(self, checked=False, adb_targets=None, edl_targets=None):
        if hasattr(self, "fw_thread") and self.fw_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Firmware flashing is already in progress.")
            return

        if self.is_any_flasher_running():
            QMessageBox.warning(self, "Busy", "Keybox flashing is in progress.")
            return

        if hasattr(self, "csr_thread") and self.csr_thread.isRunning():
            QMessageBox.warning(self, "Busy", "CSR extraction is in progress.")
            return
        self.progress.setValue(0)
        self._begin_firmware_flash(adb_targets=adb_targets, edl_targets=edl_targets)

    def start_manual_flash(self):
        """Handler for Manual Flash -> Flash User Firmware on all connected devices (ADB or EDL)."""
        # Confirm with user
        if hasattr(self, "fw_thread") and getattr(self, "fw_thread").isRunning():
            QMessageBox.warning(self, "Busy", "Firmware flashing is already in progress.")
            return
        if self.is_any_flasher_running():
            QMessageBox.warning(self, "Busy", "Keybox flashing is in progress.")
            return

        # Gather current connected devices and start firmware flash for all of them
        adb_serials = get_all_device_serials()[:8]
        edl_serials = get_all_edl_serials()[:8]

        # If any ADB devices present, prefer to reboot them into EDL for flashing (FirmwareFlasherThread handles this)
        if adb_serials:
            self.log_msg(f"Manual Flash: initiating user firmware flash for ADB devices: {', '.join(adb_serials)}")
            self.start_edl_flash(adb_targets=adb_serials)
            return

        # Otherwise if EDL devices present, flash them directly
        if edl_serials:
            self.log_msg(f"Manual Flash: initiating user firmware flash for EDL devices: {', '.join(edl_serials)}")
            self.start_edl_flash(edl_targets=edl_serials)
            return

        QMessageBox.information(self, "No Devices", "No ADB or EDL devices detected to flash.")

    def toggle_manual_popup(self):
        """Show/hide the manual flash popup positioned under the status label."""
        if self.manual_popup.isVisible():
            self.manual_popup.hide()
            return
        # populate device list
        self.manual_device_list.clear()
        adb_serials = get_all_device_serials()[:32]
        edl_serials = get_all_edl_serials()[:32]
        for s in adb_serials:
            item = QListWidgetItem(f"ADB: {s}")
            item.setData(Qt.UserRole, ("adb", s))
            item.setCheckState(Qt.Unchecked)
            self.manual_device_list.addItem(item)
        for s in edl_serials:
            item = QListWidgetItem(f"EDL: {s}")
            item.setData(Qt.UserRole, ("edl", s))
            item.setCheckState(Qt.Unchecked)
            self.manual_device_list.addItem(item)

        # position under status label
        pos = self.status_label.mapToGlobal(QPoint(0, self.status_label.height()))
        self.manual_popup.move(pos)
        self.manual_popup.show()

    def _manual_popup_flash_selected(self):
        """Collect selected devices from popup and start flashing them."""
        adb_targets = []
        edl_targets = []
        for idx in range(self.manual_device_list.count()):
            itm = self.manual_device_list.item(idx)
            if itm.checkState() == Qt.Checked:
                typ, serial = itm.data(Qt.UserRole)
                if typ == "adb":
                    adb_targets.append(serial)
                else:
                    edl_targets.append(serial)

        self.manual_popup.hide()

        if not adb_targets and not edl_targets:
            QMessageBox.information(self, "No Selection", "Please select one or more devices to flash.")
            return

        # start flashing only the selected devices
        if adb_targets:
            self.log_msg(f"Manual Flash (selected): initiating user firmware flash for ADB devices: {', '.join(adb_targets)}")
            self.start_edl_flash(adb_targets=adb_targets)
            return
        if edl_targets:
            self.log_msg(f"Manual Flash (selected): initiating user firmware flash for EDL devices: {', '.join(edl_targets)}")
            self.start_edl_flash(edl_targets=edl_targets)

    def start_manual_flash_for_selected(self, selected_serials):
        """Alternative programmatic entrypoint: split selected serials into ADB/EDL and start flash."""
        adb_all = set(get_all_device_serials())
        adb_targets = [s for s in selected_serials if s in adb_all]
        edl_targets = [s for s in selected_serials if s not in adb_all]
        if adb_targets:
            self.start_edl_flash(adb_targets=adb_targets)
            return
        if edl_targets:
            self.start_edl_flash(edl_targets=edl_targets)

    def eventFilter(self, obj, event):
        """Handle clicks on connected devices group to open the manual popup."""
        if obj is getattr(self, 'status_label', None):
            if event.type() == QEvent.MouseButtonRelease:
                # toggle popup under the status label
                self.toggle_manual_popup()
                return True
        return super().eventFilter(obj, event)

    def install_keybox_for_device(self, serial):
        if self.is_any_flasher_running():
            QMessageBox.warning(self, "Busy", "Please wait for flashing to complete before installing keybox.")
            return

        if hasattr(self, "fw_thread") and self.fw_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Firmware flashing is in progress.")
            return

        if hasattr(self, "csr_thread") and self.csr_thread.isRunning():
            QMessageBox.warning(self, "Busy", "CSR extraction is already in progress.")
            return

        if hasattr(self, "keybox_thread") and self.keybox_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Keybox installation is already in progress.")
            return

        self.start_btn.setEnabled(False)
        self.edl_flash_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.set_device_action_buttons_enabled(False)
        self.progress.setValue(0)

        self.active_keybox_serial = serial
        self.log_msg_for_device(serial, f"Initializing On-Demand Keybox Install for {serial}...")
        self.update_device_ui_status(serial, "blinking")
        self.update_device_process_details(
            serial,
            current="Flashing keybox",
            result="RUNNING",
            append_event="RUNNING: Flashing keybox",
            keybox_flashed_status="Running"
        )
        self.update_processing_activity(serial, "Flashing keybox")

        self.keybox_thread = KeyboxInstallerThread(serial)
        self.keybox_thread.log_signal.connect(lambda msg, s=serial: self.log_msg_for_device(s, msg))
        self.keybox_thread.finished_signal.connect(self.on_keybox_installed)
        self.keybox_thread.start()

    def on_keybox_installed(self, success, result_msg):
        serial = self.active_keybox_serial
        self.active_keybox_serial = None

        self.start_btn.setEnabled(True)
        self.edl_flash_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.abort_btn.setText("ABORT")
        self.set_device_action_buttons_enabled(True)

        self.log_msg(result_msg)
        self.update_processing_activity(None, "Idle")

        if serial:
            self.update_device_ui_status(serial, "green" if success else "red")
            if success:
                self.update_device_process_details(
                    serial,
                    current="Keybox flashed",
                    result="PASS",
                    append_event="PASS: Keybox flashed",
                    keybox_flashed_status="Done"
                )
                QMessageBox.information(self, "Success", f"Keybox installed successfully for {serial}.")
            else:
                self.update_device_process_details(
                    serial,
                    current="Keybox flashing failed",
                    result="FAIL",
                    append_event="FAIL: Keybox flashing failed",
                    keybox_flashed_status="Failed"
                )
                QMessageBox.critical(self, "Failed", result_msg)

    def generate_csr_for_device(self, serial):
        if self.is_any_flasher_running():
            QMessageBox.warning(self, "Busy", "Please wait for flashing to complete before generating CSR.")
            return

        if hasattr(self, "fw_thread") and self.fw_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Firmware flashing is in progress.")
            return

        if hasattr(self, "keybox_thread") and self.keybox_thread.isRunning():
            QMessageBox.warning(self, "Busy", "Keybox installation is already in progress.")
            return

        if hasattr(self, "csr_thread") and self.csr_thread.isRunning():
            QMessageBox.warning(self, "Busy", "CSR extraction already in progress.")
            return

        # Disable UI
        self.start_btn.setEnabled(False)
        self.edl_flash_btn.setEnabled(False)
        self.abort_btn.setEnabled(True)
        self.set_device_action_buttons_enabled(False)
        self.progress.setValue(0)
        
        self.active_csr_serial = serial
        self.log_msg(f"Initializing On-Demand CSR Extraction for {serial}...")
        self.update_device_ui_status(serial, "blinking")
        self.update_device_process_details(
            serial,
            current="Generating CSR",
            result="RUNNING",
            append_event="RUNNING: Generating CSR",
            csr_generated_status="Running",
            csr_pulled_status="Running"
        )
        self.update_processing_activity(serial, "Generating CSR")
        
        self.csr_thread = CSRExtractorThread(serial)
        self.csr_thread.log_signal.connect(self.log_msg)
        self.csr_thread.finished_signal.connect(self.on_csr_extracted)
        self.csr_thread.start()

    def on_csr_extracted(self, success, result_msg):
        serial = self.active_csr_serial
        self.active_csr_serial = None

        self.start_btn.setEnabled(True)
        self.edl_flash_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.abort_btn.setText("ABORT")
        self.set_device_action_buttons_enabled(True)
        
        self.log_msg(result_msg)
        self.update_processing_activity(None, "Idle")

        if serial:
            self.update_device_ui_status(serial, "green" if success else "red")
            if success:
                self.update_device_process_details(
                    serial,
                    current="CSR pulled to PC",
                    result="PASS",
                    append_event="PASS: CSR generated",
                    csr_generated_status="Done",
                    csr_pulled_status="Done"
                )
            else:
                self.update_device_process_details(
                    serial,
                    current="CSR generation failed",
                    result="FAIL",
                    append_event="FAIL: CSR generation failed",
                    csr_generated_status="Failed",
                    csr_pulled_status="Failed"
                )

        if success:
            if serial:
                source_path = os.path.join(self.data_root, "csrs", f"csr_{serial}.json")
                QMessageBox.information(self, "Export Successful", f"CSR saved to: {source_path}")
        else:
            QMessageBox.critical(self, "Export Error", result_msg)

    def abort_process(self):
        aborted = False
        running_parallel = [thread for thread in self.parallel_flasher_threads.values() if thread.isRunning()]
        if running_parallel:
            self.log_msg("🛑 Abort signal received! Attempting to halt parallel flashing...")
            for thread in running_parallel:
                thread.abort()
            aborted = True

        if hasattr(self, 'flasher_thread') and self.flasher_thread.isRunning():
            self.log_msg("🛑 Abort signal received! Attempting to halt process...")
            self.flasher_thread.abort()
            aborted = True
        
        if hasattr(self, 'fw_thread') and self.fw_thread.isRunning():
            self.log_msg("🛑 Abort signal received for EDL Flash!")
            self.fw_thread.abort()
            aborted = True

        if hasattr(self, 'csr_thread') and self.csr_thread.isRunning():
            self.log_msg("🛑 Abort signal received for CSR Extraction!")
            self.csr_thread.abort()
            aborted = True

        if hasattr(self, 'keybox_thread') and self.keybox_thread.isRunning():
            self.log_msg("🛑 Abort signal received for Keybox Installation!")
            self.keybox_thread.abort()
            aborted = True

        if aborted:
            self.parallel_flasher_threads = {}
            self.combined_firmware_context = None
            self.latest_firmware_results = []
            self.abort_btn.setEnabled(False)
            self.abort_btn.setText("ABORTING...")
            # User requested reset on abort
            self.reset_ui_indicators()
            self.show_connected_devices_panel()
            self.set_device_action_buttons_enabled(True)
            self.start_btn.setEnabled(True)
            self.start_btn.setText("START FLASHING")
            self.start_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            self.edl_flash_btn.setText("FLASH USER FIRMWARE")
            self.edl_flash_btn.setEnabled(True)
            self.edl_flash_btn.setStyleSheet("background-color: #9C27B0; color: white;")

    def on_process_finished(self, success, result_msg):
        self.combined_firmware_context = None
        self.latest_firmware_results = []
        self.show_connected_devices_panel()
        # Re-enable UI
        self.start_btn.setEnabled(True)
        self.start_btn.setText("START FLASHING")
        self.start_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        self.abort_btn.setEnabled(False)
        self.abort_btn.setText("ABORT")
        self.set_device_action_buttons_enabled(True)
        
        self.log_msg(result_msg)
        self.update_processing_activity(None, "Idle")
        
        # Enable EDL button regardless of success/failure
        self.edl_flash_btn.setEnabled(True)
        self.edl_flash_btn.setText("FLASH USER FIRMWARE")
        self.edl_flash_btn.setStyleSheet("background-color: #9C27B0; color: white;")

        if success:
            QMessageBox.information(self, "Success", result_msg)
            self.progress.setValue(100)
        else:
            QMessageBox.critical(self, "Failed", result_msg)
            self.progress.setValue(100)

    def on_edl_flash_finished(self, success, result_msg):
        if self.combined_firmware_context is not None:
            context = self.combined_firmware_context
            combined_results, unmatched_firmware = self.build_combined_start_results(
                context.get("phase1_results", []),
                self.latest_firmware_results,
            )
            self.log_msg("--- Final Production Flash Report ---")
            self.log_msg(generate_session_report(combined_results))
            if unmatched_firmware:
                self.log_msg("--- Unmatched Firmware Results ---")
                for entry in unmatched_firmware:
                    self.log_msg(
                        f"EDL Serial: {entry.get('serial', 'n/a')} | {entry.get('message', 'No details')}"
                    )

            overall_success = (
                bool(combined_results)
                and all(entry.get("success") for entry in combined_results)
                and not unmatched_firmware
            )
            final_msg = (
                "Start flashing completed successfully for all selected devices, including user firmware."
                if overall_success
                else "Start flashing finished with failures or skipped firmware. Check the final production report."
            )
            self.combined_firmware_context = None
            self.latest_firmware_results = []
            self.on_process_finished(overall_success, final_msg)
            self.qdl_progress.setValue(100 if success else max(self.qdl_progress.value(), 0))
            return

        self.latest_firmware_results = []
        self.show_connected_devices_panel()
        self.start_btn.setEnabled(True)
        self.edl_flash_btn.setEnabled(True)
        self.edl_flash_btn.setText("FLASH USER FIRMWARE")
        self.edl_flash_btn.setStyleSheet("background-color: #9C27B0; color: white;")
        self.abort_btn.setEnabled(False)
        self.abort_btn.setText("ABORT")
        self.set_device_action_buttons_enabled(True)
        
        self.log_msg(result_msg)
        
        if success:
            QMessageBox.information(self, "Success", "Parallel EDL Firmware Flashing Completed!")
            self.qdl_progress.setValue(100)
        else:
            QMessageBox.critical(self, "Failed", result_msg)
            self.qdl_progress.setValue(max(self.qdl_progress.value(), 0))
