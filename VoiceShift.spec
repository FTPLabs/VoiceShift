# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — produces a single portable VoiceShift.exe

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=collect_dynamic_libs('sounddevice'),
    datas=[
        *collect_data_files('sounddevice'),
    ],
    hiddenimports=[
        'sounddevice',
        'scipy.signal',
        'scipy.signal.windows',
        'scipy.fft',
        'scipy.linalg',
        'scipy._lib._array_api',
        'scipy._lib.array_api_compat',
        'scipy._lib.array_api_compat.numpy',
        'numpy',
        'numpy.testing',
        'unittest',
        'unittest.case',
        'unittest.suite',
        'unittest.loader',
        'unittest.runner',
        'psutil',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'winreg',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'PIL', 'cv2',
        'pandas', 'IPython', 'notebook', 'jupyter',
        'pydoc',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='VoiceShift',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    version_file=None,
    uac_admin=False,
)
