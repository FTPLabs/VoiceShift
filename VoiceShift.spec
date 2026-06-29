# -*- mode: python ; coding: utf-8 -*-
# VoiceShift.spec — single-file portable exe
#
# IMPORTANT: numpy and scipy use __getattr__-based lazy loading (numpy >= 1.23).
# Any submodule listed in `excludes` that gets resolved via __getattr__ at
# runtime will produce:  ModuleNotFoundError: No module named 'numpy.<X>'
# even if it is never explicitly imported by application code.
#
# FIX: use collect_all() for both numpy and scipy.  This bundles every
# submodule so __getattr__ resolution always succeeds.  The runtime hook
# neutralises the sys.stdout crash that originally motivated the f2py exclude.
#
# RULE: NEVER add numpy.* or scipy.* to `excludes`.

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all

# Exhaustively collect numpy + scipy so lazy-loading via __getattr__ works.
numpy_datas,   numpy_bins,   numpy_hidden   = collect_all("numpy")
scipy_datas,   scipy_bins,   scipy_hidden   = collect_all("scipy")

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=(
        collect_dynamic_libs("sounddevice")
        + numpy_bins
        + scipy_bins
    ),
    datas=[
        *collect_data_files("sounddevice"),
        *numpy_datas,
        *scipy_datas,
    ],
    hiddenimports=[
        "sounddevice",
        "psutil",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "winreg",
        "ctypes.wintypes",
        *numpy_hidden,
        *scipy_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["rthooks/rthook_fix_stdio.py"],
    excludes=[
        # Only exclude packages with ZERO connection to the dependency chain.
        # NEVER list numpy.* or scipy.* here — they use __getattr__ lazy loading
        # (numpy >= 1.23): any excluded submodule causes ModuleNotFoundError at
        # runtime when scipy triggers lazy resolution via __getattr__.
        "tkinter",
        "matplotlib",
        "PIL",
        "cv2",
        "pandas",
        "IPython",
        "notebook",
        "jupyter",
        "pydoc",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VoiceShift",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version_file=None,
    uac_admin=False,
)