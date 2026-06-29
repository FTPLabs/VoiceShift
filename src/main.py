"""
VoiceShift — entry point.
Usage:
    python main.py [--minimised]
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

def main():
    parser = argparse.ArgumentParser(description="VoiceShift")
    parser.add_argument("--minimised", action="store_true", help="Start minimised to tray")
    args = parser.parse_args()

    from PyQt6.QtWidgets import QApplication
    import config as cfg
    from audio_engine import AudioEngine
    from gui import MainWindow, STYLE

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("VoiceShift")
    app.setStyleSheet(STYLE)

    app_config = cfg.load()

    if args.minimised:
        app_config.start_minimised = True

    engine = AudioEngine()
    engine.set_devices(app_config.input_device, app_config.output_device)

    if app_config.active:
        engine.start()

    window = MainWindow(engine, app_config)  # noqa: F841

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
