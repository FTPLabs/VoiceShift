# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — produces a single portable VoiceShift.exe
#
# Fixed issues:
#   - Removed deprecated cipher= parameter (removed in PyInstaller 6.x)
#   - Added runtime hook to fix sys.stdout/stderr being None in windowed mode
#     (prevents numpy.f2py.cfuncs crash: AttributeError: NoneType.write)
#   - numpy.f2py is NO LONGER excluded — scipy._lib.array_api_compat.numpy
#     triggers numpy lazy-loading which resolves numpy.f2py via __getattr__.
#     Excluding it causes ModuleNotFoundError at runtime. The runtime hook
#     already neutralises the stdout crash, so f2py can be safely bundled.

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

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
        'scipy.signal.windows._windows',
        'scipy.fft',
        'scipy.linalg',
        'scipy.linalg._basic',
        'scipy._lib._util',
        'scipy._lib._array_api',
        'scipy._lib.array_api_compat',
        'scipy._lib.array_api_compat.numpy',
        'numpy',
        'numpy.core',
        'numpy.core._multiarray_umath',
        'numpy.lib',
        'numpy.lib.stride_tricks',
        'numpy.f2py',
        'psutil',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'winreg',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks/rthook_fix_stdio.py'],
    excludes=[
        'tkinter', 'matplotlib', 'PIL', 'cv2',
        'pandas', 'IPython', 'notebook', 'jupyter',
        'pydoc',
        'numpy.testing',
        'unittest',
        'unittest.case',
        'unittest.suite',
        'unittest.loader',
        'unittest.runner',
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
    name='VoiceShift',
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