"""
PyInstaller runtime hook — executed before any user code is imported.

Fixes: AttributeError: 'NoneType' object has no attribute 'write'

Root cause: numpy.f2py.cfuncs (imported transitively via scipy) calls
sys.stdout.write() at module level. In console=False PyInstaller builds,
sys.stdout and sys.stderr are both None, causing the crash on startup.

Solution: replace None stdio handles with a null sink before imports begin.
This hook is listed in VoiceShift.spec under runtime_hooks.
"""
import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
