"""
PyQt6 system-tray UI for VoiceShift.
Compact floating panel with full parameter control.
"""

import threading
from dataclasses import asdict
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QColor, QPainter, QPixmap, QAction
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QComboBox, QPushButton, QSystemTrayIcon,
    QMenu, QCheckBox, QFrame, QScrollArea, QLineEdit,
    QInputDialog, QMessageBox,
)

from app_monitor import AppMonitor
from audio_engine import AudioEngine, VoiceParams
import config as cfg

APP_VERSION = "2.0.0"
ACCENT = "#6C63FF"
BG = "#0F0F12"
BG2 = "#1A1A20"
BG3 = "#242430"
TEXT = "#E8E8F0"
TEXT_DIM = "#666680"
SUCCESS = "#4CAF50"
DANGER = "#EF5350"
WARN = "#FF9800"


def _make_tray_icon(active: bool) -> QIcon:
    pix = QPixmap(22, 22)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(ACCENT if active else TEXT_DIM)
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(7, 1, 8, 12, 4, 4)
    p.setPen(color)
    p.drawArc(4, 8, 14, 10, 0, 180 * 16)
    p.drawLine(11, 18, 11, 21)
    p.drawLine(8, 21, 14, 21)
    p.end()
    return QIcon(pix)


STYLE = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}}
QLabel {{ background: transparent; }}
QSlider::groove:horizontal {{
    height: 3px;
    background: {BG3};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QComboBox {{
    background: {BG2};
    border: 1px solid {BG3};
    border-radius: 6px;
    padding: 4px 8px;
    color: {TEXT};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {BG2};
    selection-background-color: {ACCENT};
    border: 1px solid {BG3};
}}
QPushButton {{
    background: {BG2};
    border: 1px solid {BG3};
    border-radius: 6px;
    padding: 5px 12px;
    color: {TEXT};
}}
QPushButton:hover {{ background: {BG3}; border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {ACCENT}; color: #fff; }}
QPushButton#primary {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #fff;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: #7C73FF; }}
QPushButton#active_off {{
    background: {BG2};
    border: 1px solid {BG3};
    color: {TEXT};
    font-weight: 600;
}}
QPushButton#active_off:hover {{ background: {BG3}; border-color: {ACCENT}; }}
QPushButton#danger {{ border-color: {DANGER}; color: {DANGER}; }}
QPushButton#danger:hover {{ background: {DANGER}; color: #fff; }}
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border-radius: 3px;
    border: 1px solid {BG3};
    background: {BG2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QFrame#sep {{
    background: {BG3};
    max-height: 1px;
    border: none;
}}
QFrame#section {{
    background: {BG2};
    border-radius: 6px;
    border: 1px solid {BG3};
}}
QScrollArea {{ border: none; }}
QLineEdit {{
    background: {BG2};
    border: 1px solid {BG3};
    border-radius: 6px;
    padding: 4px 8px;
    color: {TEXT};
}}
"""


def _sep() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    f.setFrameShape(QFrame.Shape.HLine)
    return f


def _label(text: str, dim: bool = False, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    if dim:
        lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
    if bold:
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
    return lbl


class Signals(QObject):
    engine_toggled = pyqtSignal(bool)


class MainWindow(QMainWindow):
    def __init__(self, engine: AudioEngine, app_config: cfg.AppConfig):
        super().__init__()
        self._engine = engine
        self._cfg = app_config
        self._signals = Signals()
        self._preview_running = False

        self.setWindowTitle("VoiceShift")
        self.setFixedWidth(340)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._build_ui()
        self._build_tray()
        self._update_power_btn()
        self._apply_current_preset()
        self._refresh_devices()

        self._monitor = AppMonitor(self._on_foreground_app)
        self._monitor.start()

        self._ticker = QTimer(self)
        self._ticker.timeout.connect(self._update_status_dot)
        self._ticker.start(1000)

        if self._cfg.start_minimised:
            self.hide()
        else:
            self.show()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setStyleSheet(f"background: {BG}; border-radius: 12px;")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Title bar
        title_row = QHBoxLayout()
        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        title_lbl = _label("VoiceShift", bold=True)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {TEXT}; letter-spacing: 1px;"
        )
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            f"background: transparent; border: none; color: {TEXT_DIM}; font-size: 16px;"
        )
        close_btn.clicked.connect(self.hide)
        title_row.addWidget(self._status_dot)
        title_row.addSpacing(6)
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(close_btn)
        lay.addLayout(title_row)
        lay.addWidget(_sep())

        # Power + Preview
        toggle_row = QHBoxLayout()
        self._power_btn = QPushButton("▶  Start")
        self._power_btn.setObjectName("active_off")
        self._power_btn.setFixedHeight(34)
        self._power_btn.clicked.connect(self._toggle_engine)
        self._preview_btn = QPushButton("▶ Preview 2s")
        self._preview_btn.setFixedHeight(34)
        self._preview_btn.clicked.connect(self._run_preview)
        toggle_row.addWidget(self._power_btn, 2)
        toggle_row.addWidget(self._preview_btn, 1)
        lay.addLayout(toggle_row)

        # Active app
        self._app_lbl = _label("Active: —", dim=True)
        lay.addWidget(self._app_lbl)
        lay.addWidget(_sep())

        # Preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(_label("Preset", dim=True))
        self._preset_combo = QComboBox()
        self._preset_combo.currentTextChanged.connect(self._on_preset_selected)
        preset_row.addWidget(self._preset_combo, 1)
        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(48)
        save_btn.clicked.connect(self._save_preset)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.clicked.connect(self._new_preset)
        del_btn = QPushButton("×")
        del_btn.setObjectName("danger")
        del_btn.setFixedWidth(28)
        del_btn.clicked.connect(self._delete_preset)
        preset_row.addWidget(save_btn)
        preset_row.addWidget(add_btn)
        preset_row.addWidget(del_btn)
        lay.addLayout(preset_row)
        lay.addWidget(_sep())

        # Scrollable sliders
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        slay = QVBoxLayout(inner)
        slay.setContentsMargins(2, 4, 2, 4)
        slay.setSpacing(6)

        # — Voice shape —
        slay.addWidget(self._section_label("VOICE SHAPE"))
        self._pitch_sl, r = self._slider_row("Pitch", -12, 12, 0, 1, "st")
        slay.addLayout(r)
        self._formant_sl, r = self._slider_row("Formant", 50, 200, 100, 5, "%")
        slay.addLayout(r)

        # — Character —
        slay.addWidget(self._section_label("CHARACTER"))
        self._robot_sl, r = self._slider_row("Robotic", 0, 100, 0, 5, "%")
        slay.addLayout(r)
        self._reverb_sl, r = self._slider_row("Reverb", 0, 100, 0, 5, "%")
        slay.addLayout(r)

        # — EQ —
        slay.addWidget(self._section_label("EQ"))
        self._hpf_sl, r = self._slider_row("Lo-cut", 20, 500, 80, 10, "Hz")
        slay.addLayout(r)
        self._lpf_sl, r = self._slider_row("Hi-cut", 4000, 20000, 16000, 500, "Hz")
        slay.addLayout(r)

        # — Dynamics —
        slay.addWidget(self._section_label("DYNAMICS"))
        self._gate_sl, r = self._slider_row("Gate", -80, -10, -50, 5, "dB")
        slay.addLayout(r)
        self._comp_thr_sl, r = self._slider_row("Comp.Thr", -40, 0, -24, 1, "dB")
        slay.addLayout(r)
        self._comp_rat_sl, r = self._slider_row("Comp.Rat", 10, 100, 40, 5, ":10")
        slay.addLayout(r)

        # — Output —
        slay.addWidget(self._section_label("OUTPUT"))
        self._vol_sl, r = self._slider_row("Volume", 0, 200, 100, 5, "%")
        slay.addLayout(r)

        scroll.setWidget(inner)
        scroll.setFixedHeight(310)
        lay.addWidget(scroll)

        # Connect all sliders
        for sl in [
            self._pitch_sl, self._formant_sl, self._robot_sl, self._reverb_sl,
            self._hpf_sl, self._lpf_sl,
            self._gate_sl, self._comp_thr_sl, self._comp_rat_sl,
            self._vol_sl,
        ]:
            sl.valueChanged.connect(self._on_slider_changed)

        lay.addWidget(_sep())

        # Devices
        lay.addWidget(_label("Devices", dim=True))
        in_row = QHBoxLayout()
        in_row.addWidget(_label("In", dim=True))
        self._in_combo = QComboBox()
        self._in_combo.currentIndexChanged.connect(self._on_device_changed)
        in_row.addWidget(self._in_combo, 1)
        lay.addLayout(in_row)
        out_row = QHBoxLayout()
        out_row.addWidget(_label("Out", dim=True))
        self._out_combo = QComboBox()
        self._out_combo.currentIndexChanged.connect(self._on_device_changed)
        out_row.addWidget(self._out_combo, 1)
        lay.addLayout(out_row)
        lay.addWidget(_sep())

        # Bypass apps
        lay.addWidget(_label("Bypass for apps (process names, comma-separated):", dim=True))
        self._excl_edit = QLineEdit()
        self._excl_edit.setPlaceholderText("discord.exe, chrome.exe")
        lay.addWidget(self._excl_edit)
        lay.addWidget(_sep())

        # Options
        opts_row = QHBoxLayout()
        self._autostart_cb = QCheckBox("Autostart")
        self._autostart_cb.setChecked(self._cfg.autostart)
        self._autostart_cb.stateChanged.connect(self._on_autostart)
        self._minimised_cb = QCheckBox("Start to tray")
        self._minimised_cb.setChecked(self._cfg.start_minimised)
        self._minimised_cb.stateChanged.connect(
            lambda v: setattr(self._cfg, "start_minimised", bool(v))
        )
        opts_row.addWidget(self._autostart_cb)
        opts_row.addWidget(self._minimised_cb)
        opts_row.addStretch()
        lay.addLayout(opts_row)

        ver_lbl = _label(f"v{APP_VERSION}", dim=True)
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(ver_lbl)

        self._refresh_preset_combo()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1.5px; margin-top: 4px;"
        )
        return lbl

    def _slider_row(self, label: str, mn: int, mx: int, val: int,
                    step: int, unit: str):
        row = QHBoxLayout()
        row.setSpacing(6)
        lbl = _label(label, dim=True)
        lbl.setFixedWidth(58)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(mn, mx)
        sl.setValue(val)
        sl.setSingleStep(step)
        sl.setPageStep(step * 5)
        val_lbl = QLabel(f"{val}{unit}")
        val_lbl.setFixedWidth(56)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        val_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        sl.setProperty("val_lbl", val_lbl)
        sl.setProperty("unit", unit)
        sl.valueChanged.connect(lambda v, lbl=val_lbl, u=unit: lbl.setText(f"{v}{u}"))
        row.addWidget(lbl)
        row.addWidget(sl, 1)
        row.addWidget(val_lbl)
        return sl, row

    def _build_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(_make_tray_icon(self._engine.is_active))
        self._tray.setToolTip("VoiceShift")
        menu = QMenu()
        self._tray_toggle_action = QAction("Enable", self)
        self._tray_toggle_action.triggered.connect(self._toggle_engine)
        menu.addAction(self._tray_toggle_action)
        open_action = QAction("Open", self)
        open_action.triggered.connect(self._show_window)
        menu.addAction(open_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ------------------------------------------------------------------
    # Logic
    # ------------------------------------------------------------------

    def _refresh_preset_combo(self):
        self._preset_combo.blockSignals(True)
        self._preset_combo.clear()
        for p in self._cfg.presets:
            self._preset_combo.addItem(p.name)
        idx = self._preset_combo.findText(self._cfg.active_preset)
        if idx >= 0:
            self._preset_combo.setCurrentIndex(idx)
        self._preset_combo.blockSignals(False)

    def _refresh_devices(self):
        devices = AudioEngine.list_devices()
        self._in_combo.blockSignals(True)
        self._out_combo.blockSignals(True)
        self._in_combo.clear()
        self._out_combo.clear()
        self._in_combo.addItem("Default", None)
        self._out_combo.addItem("Default", None)
        for d in devices:
            if d["max_input"] > 0:
                self._in_combo.addItem(d["name"][:38], d["index"])
            if d["max_output"] > 0:
                self._out_combo.addItem(d["name"][:38], d["index"])
        # Restore saved devices
        if self._cfg.input_device is not None:
            for i in range(self._in_combo.count()):
                if self._in_combo.itemData(i) == self._cfg.input_device:
                    self._in_combo.setCurrentIndex(i)
                    break
        if self._cfg.output_device is not None:
            for i in range(self._out_combo.count()):
                if self._out_combo.itemData(i) == self._cfg.output_device:
                    self._out_combo.setCurrentIndex(i)
                    break
        self._in_combo.blockSignals(False)
        self._out_combo.blockSignals(False)

    def _apply_current_preset(self):
        preset = self._cfg.get_preset(self._cfg.active_preset)
        if not preset:
            return
        p = preset.params

        sliders_vals = [
            (self._pitch_sl,    int(p.get("pitch_semitones", 0))),
            (self._formant_sl,  int(p.get("formant_shift", 1.0) * 100)),
            (self._robot_sl,    int(p.get("robotic_amount", 0.0) * 100)),
            (self._reverb_sl,   int(p.get("reverb_amount", 0.0) * 100)),
            (self._hpf_sl,      int(p.get("highpass_freq", 80.0))),
            (self._lpf_sl,      int(p.get("lowpass_freq", 16000.0))),
            (self._gate_sl,     int(p.get("noise_gate_db", -50))),
            (self._comp_thr_sl, int(p.get("compressor_threshold", -24))),
            (self._comp_rat_sl, int(p.get("compressor_ratio", 4.0) * 10)),
            (self._vol_sl,      int(p.get("volume_out", 1.0) * 100)),
        ]

        for sl, val in sliders_vals:
            sl.blockSignals(True)
            sl.setValue(val)
            sl.blockSignals(False)
            val_lbl = sl.property("val_lbl")
            unit = sl.property("unit")
            if val_lbl and unit:
                val_lbl.setText(f"{val}{unit}")

        self._excl_edit.setText(", ".join(preset.excluded_apps))
        self._push_params_to_engine()

    def _current_voice_params(self) -> VoiceParams:
        return VoiceParams(
            pitch_semitones=float(self._pitch_sl.value()),
            formant_shift=self._formant_sl.value() / 100.0,
            robotic_amount=self._robot_sl.value() / 100.0,
            reverb_amount=self._reverb_sl.value() / 100.0,
            highpass_freq=float(self._hpf_sl.value()),
            lowpass_freq=float(self._lpf_sl.value()),
            noise_gate_db=float(self._gate_sl.value()),
            compressor_threshold=float(self._comp_thr_sl.value()),
            compressor_ratio=self._comp_rat_sl.value() / 10.0,
            volume_out=self._vol_sl.value() / 100.0,
        )

    def _push_params_to_engine(self):
        self._engine.set_params(self._current_voice_params())

    def _toggle_engine(self):
        if self._engine.is_active:
            self._engine.stop()
            self._cfg.active = False
        else:
            try:
                self._engine.start()
                self._cfg.active = True
            except Exception as e:
                QMessageBox.critical(self, "VoiceShift", f"Failed to start audio:\n{e}")
                return
        self._update_power_btn()
        self._tray.setIcon(_make_tray_icon(self._engine.is_active))
        cfg.save(self._cfg)

    def _update_power_btn(self):
        if self._engine.is_active:
            self._power_btn.setText("■  Stop")
            self._power_btn.setObjectName("primary")
            self._tray_toggle_action.setText("Disable")
        else:
            self._power_btn.setText("▶  Start")
            self._power_btn.setObjectName("active_off")
            self._tray_toggle_action.setText("Enable")
        # Force style refresh
        self._power_btn.style().unpolish(self._power_btn)
        self._power_btn.style().polish(self._power_btn)

    def _run_preview(self):
        if self._preview_running:
            return
        self._preview_running = True
        self._preview_btn.setText("● Recording…")
        self._preview_btn.setEnabled(False)
        was_active = self._engine.is_active
        if was_active:
            self._engine.stop()

        def _do():
            try:
                self._engine.preview_once(2.0)
            except Exception as e:
                logger_err = f"Preview error: {e}"
                logger_err  # noqa: F841 — logged below
            finally:
                self._preview_running = False
                if was_active:
                    try:
                        self._engine.start()
                    except Exception:
                        pass
                self._preview_btn.setText("▶ Preview 2s")
                self._preview_btn.setEnabled(True)

        threading.Thread(target=_do, daemon=True).start()

    def _on_slider_changed(self):
        self._push_params_to_engine()

    def _on_preset_selected(self, name: str):
        self._cfg.active_preset = name
        self._apply_current_preset()
        cfg.save(self._cfg)

    def _save_preset(self):
        name = self._preset_combo.currentText()
        excl = [s.strip() for s in self._excl_edit.text().split(",") if s.strip()]
        preset = cfg.Preset(
            name=name,
            params=asdict(self._current_voice_params()),
            app_rules=[],
            excluded_apps=excl,
        )
        self._cfg.upsert_preset(preset)
        cfg.save(self._cfg)

    def _new_preset(self):
        name, ok = QInputDialog.getText(self, "New Preset", "Preset name:")
        if ok and name.strip():
            excl = [s.strip() for s in self._excl_edit.text().split(",") if s.strip()]
            preset = cfg.Preset(
                name=name.strip(),
                params=asdict(self._current_voice_params()),
                app_rules=[],
                excluded_apps=excl,
            )
            self._cfg.upsert_preset(preset)
            self._cfg.active_preset = name.strip()
            cfg.save(self._cfg)
            self._refresh_preset_combo()

    def _delete_preset(self):
        name = self._preset_combo.currentText()
        if len(self._cfg.presets) <= 1:
            QMessageBox.warning(self, "VoiceShift", "Cannot delete the last preset.")
            return
        self._cfg.delete_preset(name)
        cfg.save(self._cfg)
        self._refresh_preset_combo()
        self._apply_current_preset()

    def _on_device_changed(self):
        in_idx = self._in_combo.currentData()
        out_idx = self._out_combo.currentData()
        self._cfg.input_device = in_idx
        self._cfg.output_device = out_idx
        self._engine.set_devices(in_idx, out_idx)
        cfg.save(self._cfg)

    def _on_autostart(self, state: int):
        enabled = bool(state)
        self._cfg.autostart = enabled
        cfg.set_autostart(enabled)
        cfg.save(self._cfg)

    def _on_foreground_app(self, process: Optional[str]):
        if process:
            self._app_lbl.setText(f"Active: {process}")
        else:
            self._app_lbl.setText("Active: —")

        preset = self._cfg.get_preset(self._cfg.active_preset)
        if not preset or not self._engine.is_active:
            return

        excluded = [e.lower() for e in preset.excluded_apps]
        if process and process.lower() in excluded:
            p = self._engine.get_params()
            p.volume_out = 0.0
            self._engine.set_params(p)
        else:
            self._push_params_to_engine()

    def _update_status_dot(self):
        if self._engine.is_active:
            self._status_dot.setStyleSheet(f"color: {SUCCESS}; font-size: 14px;")
        else:
            self._status_dot.setStyleSheet(f"color: {DANGER}; font-size: 14px;")

    # ------------------------------------------------------------------
    # Tray / window
    # ------------------------------------------------------------------

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self._monitor.stop()
        self._engine.stop()
        cfg.save(self._cfg)
        QApplication.quit()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
