"""Live telemetry cards panel for HeadMouseAI dashboard.

Presents facial tracking telemetry, eye blink state machines, and hands-free gesture
diagnostics in a clean, stable, jitter-free layout.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class StatusBadge(QLabel):
    """Semantic status indicator pill label with cached stylesheet styling."""

    def __init__(self, text: str = "OFF", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.setMinimumWidth(76)
        self._current_category: Optional[str] = None
        self.set_state("NORMAL", text)

    def set_state(self, category: str, text: str) -> None:
        """Set badge style based on semantic category without unnecessary restyling."""
        self.setText(text)
        cat_upper = category.upper()

        if cat_upper == self._current_category:
            return  # Category unchanged: skip CSS re-parse and layout invalidation

        self._current_category = cat_upper

        if cat_upper in ("ACTIVE", "ENABLED", "OK"):
            bg = "#0B2E22"
            color = "#6EE7B7"
            border = "#059669"
        elif cat_upper in ("SCROLL", "ZOOM"):
            bg = "#1A2B4C"
            color = "#93C5FD"
            border = "#3B82F6"
        elif cat_upper in ("EMERGENCY_STOP", "ERROR", "MISS"):
            bg = "#381318"
            color = "#FCA5A5"
            border = "#DC2626"
        elif cat_upper in ("CLOSED",):
            bg = "#3B1425"
            color = "#F472B6"
            border = "#DB2777"
        elif cat_upper in ("WARNING", "CALIBRATING", "LOCKED", "DRAG"):
            bg = "#332109"
            color = "#FDE68A"
            border = "#D97706"
        else:  # DISABLED, OFF, NONE, NORMAL
            bg = "#202226"
            color = "#CBD5E1"
            border = "#353942"

        self.setStyleSheet(
            f"background-color: {bg}; color: {color}; border: 1px solid {border}; "
            f"border-radius: 6px; font-weight: 600; font-size: 11px; padding: 2px 8px;"
        )


class TelemetryCardsWidget(QWidget):
    """Fixed-width real-time status sidebar displaying tracking telemetry with zero layout jitter."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(380)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 2, 4, 2)
        main_layout.setSpacing(8)

        # ---------------- Section 1: System & Tracking ---------------- #
        grp_sys = QGroupBox("System && Tracking")
        layout_sys = QGridLayout(grp_sys)
        layout_sys.setContentsMargins(10, 12, 10, 8)
        layout_sys.setHorizontalSpacing(10)
        layout_sys.setVerticalSpacing(6)

        layout_sys.addWidget(self._make_label("Face Detect:"), 0, 0)
        self.badge_face = StatusBadge("SEARCHING")
        layout_sys.addWidget(self.badge_face, 0, 1)

        layout_sys.addWidget(self._make_label("Real Mouse:"), 0, 2)
        self.badge_real_mouse = StatusBadge("DISABLED")
        layout_sys.addWidget(self.badge_real_mouse, 0, 3)

        layout_sys.addWidget(self._make_label("Cursor Lock:"), 1, 0)
        self.badge_pos_lock = StatusBadge("OFF")
        layout_sys.addWidget(self.badge_pos_lock, 1, 1)

        layout_sys.addWidget(self._make_label("Calibration:"), 1, 2)
        self.badge_calib = StatusBadge("CALIBRATING")
        layout_sys.addWidget(self.badge_calib, 1, 3)

        layout_sys.addWidget(self._make_label("Screen Pos:"), 2, 0)
        self.lbl_screen_pos = QLabel("(0, 0)")
        self.lbl_screen_pos.setStyleSheet("color: #60A5FA; font-weight: 600; font-family: Consolas, monospace;")
        self.lbl_screen_pos.setMinimumWidth(80)
        layout_sys.addWidget(self.lbl_screen_pos, 2, 1)

        layout_sys.addWidget(self._make_label("Head Delta:"), 2, 2)
        self.lbl_rel_disp = QLabel("+0.00, +0.00")
        self.lbl_rel_disp.setStyleSheet("color: #E4E4E7; font-family: Consolas, monospace; font-size: 11px;")
        self.lbl_rel_disp.setMinimumWidth(80)
        layout_sys.addWidget(self.lbl_rel_disp, 2, 3)

        self.progress_calib = QProgressBar()
        self.progress_calib.setFixedHeight(8)
        self.progress_calib.setTextVisible(False)
        self.progress_calib.setVisible(False)
        layout_sys.addWidget(self.progress_calib, 3, 0, 1, 4)

        main_layout.addWidget(grp_sys)

        # ---------------- Section 2: Eyes & Clicks ---------------- #
        grp_eyes = QGroupBox("Eyes && Click Gestures")
        layout_eyes = QGridLayout(grp_eyes)
        layout_eyes.setContentsMargins(10, 12, 10, 8)
        layout_eyes.setHorizontalSpacing(10)
        layout_eyes.setVerticalSpacing(6)

        layout_eyes.addWidget(self._make_label("Left Wink (L):"), 0, 0)
        self.lbl_eye_l = QLabel("EAR: 0.28 [OPEN]")
        self.lbl_eye_l.setStyleSheet("color: #34D399; font-weight: 600; font-family: Consolas, monospace; font-size: 11px;")
        layout_eyes.addWidget(self.lbl_eye_l, 0, 1, 1, 3)

        layout_eyes.addWidget(self._make_label("Right Wink (R):"), 1, 0)
        self.lbl_eye_r = QLabel("EAR: 0.28 [OPEN]")
        self.lbl_eye_r.setStyleSheet("color: #34D399; font-weight: 600; font-family: Consolas, monospace; font-size: 11px;")
        layout_eyes.addWidget(self.lbl_eye_r, 1, 1, 1, 3)

        layout_eyes.addWidget(self._make_label("Drag & Drop:"), 2, 0)
        self.badge_drag = StatusBadge("INACTIVE")
        layout_eyes.addWidget(self.badge_drag, 2, 1)

        layout_eyes.addWidget(self._make_label("Last Click:"), 2, 2)
        self.badge_click_event = StatusBadge("NONE")
        layout_eyes.addWidget(self.badge_click_event, 2, 3)

        layout_eyes.addWidget(self._make_label("Bilateral:"), 3, 0)
        self.badge_suppress = StatusBadge("OFF")
        layout_eyes.addWidget(self.badge_suppress, 3, 1)

        main_layout.addWidget(grp_eyes)

        # ---------------- Section 3: Hands-Free Gestures ---------------- #
        grp_gesture = QGroupBox("Hands-Free Scroll && Zoom")
        layout_gest = QGridLayout(grp_gesture)
        layout_gest.setContentsMargins(10, 12, 10, 8)
        layout_gest.setHorizontalSpacing(10)
        layout_gest.setVerticalSpacing(6)

        layout_gest.addWidget(self._make_label("Active Mode:"), 0, 0)
        self.badge_mode = StatusBadge("NORMAL")
        layout_gest.addWidget(self.badge_mode, 0, 1)

        layout_gest.addWidget(self._make_label("Smile / Teeth:"), 0, 2)
        self.badge_teeth = StatusBadge("NO")
        layout_gest.addWidget(self.badge_teeth, 0, 3)

        layout_gest.addWidget(self._make_label("Eyebrows:"), 1, 0)
        self.lbl_eyebrows = QLabel("L:NORM  R:NORM")
        self.lbl_eyebrows.setStyleSheet("color: #E4E4E7; font-weight: 600; font-family: Consolas, monospace; font-size: 11px;")
        layout_gest.addWidget(self.lbl_eyebrows, 1, 1)

        layout_gest.addWidget(self._make_label("Head Tilt:"), 1, 2)
        self.badge_head_dir = StatusBadge("NEUTRAL")
        layout_gest.addWidget(self.badge_head_dir, 1, 3)

        layout_gest.addWidget(self._make_label("Action:"), 2, 0)
        self.badge_gest_act = StatusBadge("NONE")
        layout_gest.addWidget(self.badge_gest_act, 2, 1)

        layout_gest.addWidget(self._make_label("Geometry:"), 3, 0)
        self.lbl_mouth_geom = QLabel("W/IOD: 0.52 (base: 0.52) | O/IOD: 0.005")
        self.lbl_mouth_geom.setStyleSheet("color: #A1A1AA; font-family: Consolas, monospace; font-size: 10px;")
        layout_gest.addWidget(self.lbl_mouth_geom, 3, 1, 1, 3)

        layout_gest.addWidget(self._make_label("Reject Diag:"), 4, 0)
        self.lbl_diag_rej = QLabel("NONE")
        self.lbl_diag_rej.setStyleSheet("color: #FBBF24; font-weight: 500; font-family: Consolas, monospace; font-size: 10px;")
        layout_gest.addWidget(self.lbl_diag_rej, 4, 1, 1, 3)

        main_layout.addWidget(grp_gesture)

        # ---------------- Section 4: Performance & Resources ---------------- #
        grp_perf = QGroupBox("Performance && Resources")
        layout_perf = QGridLayout(grp_perf)
        layout_perf.setContentsMargins(10, 12, 10, 8)
        layout_perf.setHorizontalSpacing(10)
        layout_perf.setVerticalSpacing(6)

        layout_perf.addWidget(self._make_label("FPS / Latency:"), 0, 0)
        self.lbl_fps_lat = QLabel("0.0 FPS | 0.0 ms")
        self.lbl_fps_lat.setStyleSheet("color: #60A5FA; font-weight: 600; font-family: Consolas, monospace; font-size: 11px;")
        layout_perf.addWidget(self.lbl_fps_lat, 0, 1, 1, 3)

        layout_perf.addWidget(self._make_label("AI Inference:"), 1, 0)
        self.lbl_inference = QLabel("0.0 ms")
        self.lbl_inference.setStyleSheet("color: #34D399; font-weight: 600; font-family: Consolas, monospace; font-size: 11px;")
        layout_perf.addWidget(self.lbl_inference, 1, 1)

        layout_perf.addWidget(self._make_label("Track Quality:"), 1, 2)
        self.badge_tracking_quality = StatusBadge("OPTIMAL")
        layout_perf.addWidget(self.badge_tracking_quality, 1, 3)

        layout_perf.addWidget(self._make_label("CPU Load:"), 2, 0)
        self.lbl_cpu = QLabel("0.0 %")
        self.lbl_cpu.setStyleSheet("color: #E4E4E7; font-family: Consolas, monospace; font-size: 11px;")
        self.lbl_cpu.setMinimumWidth(76)
        layout_perf.addWidget(self.lbl_cpu, 2, 1)

        layout_perf.addWidget(self._make_label("RAM Usage:"), 2, 2)
        self.lbl_ram = QLabel("0.0 MB")
        self.lbl_ram.setStyleSheet("color: #E4E4E7; font-family: Consolas, monospace; font-size: 11px;")
        self.lbl_ram.setMinimumWidth(76)
        layout_perf.addWidget(self.lbl_ram, 2, 3)

        layout_perf.addWidget(self._make_label("Camera Res:"), 3, 0)
        self.lbl_res = QLabel("640x480")
        self.lbl_res.setStyleSheet("color: #A1A1AA; font-family: Consolas, monospace; font-size: 11px;")
        layout_perf.addWidget(self.lbl_res, 3, 1, 1, 3)

        main_layout.addWidget(grp_perf)
        main_layout.addStretch(1)

        # Set clean column widths so labels and values never overlap
        for lyt in (layout_sys, layout_eyes, layout_gest, layout_perf):
            lyt.setColumnMinimumWidth(0, 95)
            lyt.setColumnMinimumWidth(1, 105)
            lyt.setColumnMinimumWidth(2, 95)
            lyt.setColumnMinimumWidth(3, 105)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #CBD5E1; font-size: 11px; font-weight: 600;")
        return lbl

    def update_telemetry(self, t: dict) -> None:
        """Update all telemetry badges and labels with smooth, stable updates."""
        # Section 1: System & Tracking
        has_face = t.get("has_face", False)
        self.badge_face.set_state("OK" if has_face else "MISS", "LOCKED (OK)" if has_face else "FACE LOST")

        if t.get("emergency_stopped", False):
            self.badge_real_mouse.set_state("EMERGENCY_STOP", "STOPPED")
        elif t.get("real_mouse_enabled", False):
            self.badge_real_mouse.set_state("ENABLED", "ENABLED")
        else:
            self.badge_real_mouse.set_state("DISABLED", "DISABLED")

        pos_locked = t.get("position_locked", False)
        self.badge_pos_lock.set_state("LOCKED" if pos_locked else "OFF", "LOCKED" if pos_locked else "NORMAL")

        is_calib = t.get("is_calibrated", False)
        is_calibrating = t.get("is_calibrating", False)
        if is_calibrating:
            self.badge_calib.set_state("CALIBRATING", "CALIBRATING")
            prog = int(t.get("calib_progress", 0.0) * 100)
            self.progress_calib.setValue(prog)
            if not self.progress_calib.isVisible():
                self.progress_calib.setVisible(True)
        else:
            self.badge_calib.set_state("OK" if is_calib else "WARNING", "CALIBRATED" if is_calib else "UNCALIBRATED")
            if self.progress_calib.isVisible():
                self.progress_calib.setVisible(False)

        sx = t.get("screen_x") or 0
        sy = t.get("screen_y") or 0
        self.lbl_screen_pos.setText(f"({sx}, {sy})")

        dx = t.get("rel_dx")
        dx = 0.0 if dx is None else float(dx)
        dy = t.get("rel_dy")
        dy = 0.0 if dy is None else float(dy)
        self.lbl_rel_disp.setText(f"{dx:+.2f}, {dy:+.2f}")

        # Section 2: Eyes & Clicks
        l_ear = t.get("left_ear")
        l_ear = 0.0 if l_ear is None else float(l_ear)
        r_ear = t.get("right_ear")
        r_ear = 0.0 if r_ear is None else float(r_ear)
        l_st = t.get("left_eye_state") or "OPEN"
        r_st = t.get("right_eye_state") or "OPEN"
        self.lbl_eye_l.setText(f"EAR: {l_ear:.2f} [{l_st}]")
        self.lbl_eye_r.setText(f"EAR: {r_ear:.2f} [{r_st}]")

        is_drag = t.get("is_dragging", False)
        self.badge_drag.set_state("DRAG" if is_drag else "OFF", "ACTIVE" if is_drag else "INACTIVE")

        blk = t.get("blink_event") or "NONE"
        self.badge_click_event.set_state("ACTIVE" if blk and blk != "NONE" else "OFF", str(blk))

        supp = t.get("suppression_active", False)
        self.badge_suppress.set_state("WARNING" if supp else "OFF", "SUPPRESSED" if supp else "NORMAL")

        # Section 3: Gestures
        mode = t.get("mode") or "NORMAL"
        self.badge_mode.set_state(mode, mode)

        teeth = t.get("teeth_visible", False)
        self.badge_teeth.set_state("ACTIVE" if teeth else "OFF", "SHOWN" if teeth else "NOT VISIBLE")

        l_eb = t.get("left_eb_state") or "NORMAL"
        r_eb = t.get("right_eb_state") or "NORMAL"
        self.lbl_eyebrows.setText(f"L:[{l_eb[:4]}] R:[{r_eb[:4]}]")

        head_dir = t.get("head_direction") or "NEUTRAL"
        self.badge_head_dir.set_state("ACTIVE" if head_dir != "NEUTRAL" else "NORMAL", head_dir)

        act = t.get("gesture_action") or t.get("last_zoom_action") or t.get("last_scroll_action") or "READY"
        self.badge_gest_act.set_state("ACTIVE" if act != "READY" else "NORMAL", str(act))

        mw = t.get("mouth_width_ratio")
        mw = 0.0 if mw is None else float(mw)
        mwb = t.get("mouth_width_baseline")
        mwb = 0.0 if mwb is None else float(mwb)
        mo = t.get("mouth_open_ratio")
        mo = 0.0 if mo is None else float(mo)
        self.lbl_mouth_geom.setText(f"W: {mw:.2f} (b: {mwb:.2f}) | O: {mo:.3f}")

        rej = t.get("gesture_reject_reason") or "NONE"
        self.lbl_diag_rej.setText(str(rej)[:28])

        # Section 4: Performance & Resources
        fps = t.get("fps")
        fps = 0.0 if fps is None else float(fps)
        lat = t.get("latency_ms")
        lat = 0.0 if lat is None else float(lat)
        self.lbl_fps_lat.setText(f"{fps:.1f} FPS | {lat:.1f} ms")

        inf_ms = t.get("inference_ms")
        inf_ms = 0.0 if inf_ms is None else float(inf_ms)
        self.lbl_inference.setText(f"{inf_ms:.1f} ms")

        trk_status = str(t.get("tracking_status") or "OPTIMAL")
        cat = "OK" if trk_status == "OPTIMAL" else ("WARNING" if trk_status == "TRACKING" else "DISABLED")
        self.badge_tracking_quality.set_state(cat, trk_status)

        cpu = t.get("cpu_percent")
        cpu = 0.0 if cpu is None else float(cpu)
        self.lbl_cpu.setText(f"{cpu:.1f} %")

        ram = t.get("ram_mb")
        ram = 0.0 if ram is None else float(ram)
        self.lbl_ram.setText(f"{ram:.1f} MB")

        res = t.get("camera_resolution") or "640x480"
        self.lbl_res.setText(str(res))
