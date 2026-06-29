"""
Persistent configuration and preset management.
Stores everything in %APPDATA%/VoiceShift/config.json
"""

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from typing import Optional
from audio_engine import VoiceParams

APP_NAME = "VoiceShift"

if sys.platform == "win32":
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
else:
    CONFIG_DIR = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")

CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class Preset:
    name: str
    params: dict        # serialised VoiceParams
    app_rules: list[str] = field(default_factory=list)   # process names this preset applies to
    excluded_apps: list[str] = field(default_factory=list)  # processes where voice is bypassed


@dataclass
class AppConfig:
    active: bool = True
    input_device: Optional[int] = None
    output_device: Optional[int] = None
    active_preset: str = "Default"
    presets: list[Preset] = field(default_factory=list)
    start_minimised: bool = True
    autostart: bool = False

    def get_preset(self, name: str) -> Optional[Preset]:
        for p in self.presets:
            if p.name == name:
                return p
        return None

    def upsert_preset(self, preset: Preset) -> None:
        for i, p in enumerate(self.presets):
            if p.name == preset.name:
                self.presets[i] = preset
                return
        self.presets.append(preset)

    def delete_preset(self, name: str) -> None:
        self.presets = [p for p in self.presets if p.name != name]
        if self.active_preset == name and self.presets:
            self.active_preset = self.presets[0].name


def _default_config() -> AppConfig:
    default_params = asdict(VoiceParams())
    return AppConfig(
        presets=[
            Preset(
                name="Default",
                params=default_params,
                app_rules=[],
                excluded_apps=[],
            ),
            Preset(
                name="Deep",
                params=asdict(VoiceParams(pitch_semitones=-4.0, formant_shift=0.85)),
                app_rules=[],
                excluded_apps=["discord.exe"],
            ),
            Preset(
                name="High",
                params=asdict(VoiceParams(pitch_semitones=5.0, formant_shift=1.2)),
                app_rules=[],
                excluded_apps=[],
            ),
            Preset(
                name="Robot",
                params=asdict(VoiceParams(robotic_amount=0.7, pitch_semitones=2.0)),
                app_rules=[],
                excluded_apps=[],
            ),
        ]
    )


def load() -> AppConfig:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        cfg = _default_config()
        save(cfg)
        return cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        presets = [
            Preset(
                name=p["name"],
                params=p.get("params", asdict(VoiceParams())),
                app_rules=p.get("app_rules", []),
                excluded_apps=p.get("excluded_apps", []),
            )
            for p in raw.get("presets", [])
        ]
        return AppConfig(
            active=raw.get("active", True),
            input_device=raw.get("input_device"),
            output_device=raw.get("output_device"),
            active_preset=raw.get("active_preset", "Default"),
            presets=presets or _default_config().presets,
            start_minimised=raw.get("start_minimised", True),
            autostart=raw.get("autostart", False),
        )
    except Exception:
        return _default_config()


def save(cfg: AppConfig) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = {
        "active": cfg.active,
        "input_device": cfg.input_device,
        "output_device": cfg.output_device,
        "active_preset": cfg.active_preset,
        "start_minimised": cfg.start_minimised,
        "autostart": cfg.autostart,
        "presets": [
            {
                "name": p.name,
                "params": p.params,
                "app_rules": p.app_rules,
                "excluded_apps": p.excluded_apps,
            }
            for p in cfg.presets
        ],
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def set_autostart(enabled: bool) -> None:
    """Add/remove VoiceShift from Windows registry autostart."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        exe = sys.executable if not getattr(sys, "frozen", False) else sys.executable
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe}" --minimised')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
    except Exception:
        pass
