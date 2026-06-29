  # -*- mode: python ; coding: utf-8 -*-
  # PyInstaller spec — produces a single portable VoiceShift.exe
  #
  # Fixed issues:
  #   - Removed deprecated block_cipher / cipher= (removed in PyInstaller 6.x)
  #   - Added runtime hook to fix sys.stdout/stderr being None in windowed mode
  #     (prevents numpy.f2py.cfuncs crash: AttributeError: NoneType.write)
  #   - Excluded numpy.f2py and related modules (not needed, avoid import chain)
  #   - Added missing scipy compat hidden imports

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
          # numpy.f2py is a Fortran-wrapping toolkit — not needed at runtime.
          # Its import chain triggers sys.stdout.write() which is None in
          # windowed PyInstaller builds, causing the startup crash.
          'numpy.f2py',
          'numpy.f2py.auxfuncs',
          'numpy.f2py.cfuncs',
          'numpy.f2py.crackfortran',
          'numpy.f2py.f2py2e',
          'numpy.f2py.f90mod_rules',
          'numpy.distutils',
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
  