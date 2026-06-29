#!/usr/bin/env python3
"""
smoke_test.py -- platform-independent structural smoke tests for VoiceShift.

Does NOT require Windows, audio hardware, PyQt6, or scipy.
Tests: Python syntax, constants, critical bug fixes, spec integrity,
requirements pinning, quality scripts presence.

Usage:
    python scripts/smoke_test.py
"""
import ast
import sys
from pathlib import Path

PASS = 0
FAIL = 0


def test(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        print(f"  PASS  {name}")
        PASS += 1
    except Exception as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        FAIL += 1


def _all_syntax():
    for path in sorted(Path("src").glob("**/*.py")):
        src = path.read_text(encoding="utf-8")
        ast.parse(src, filename=str(path))


test("All src/*.py files parse as valid Python 3", _all_syntax)


def _config_constants():
    src = Path("src/config.py").read_text(encoding="utf-8")
    assert 'APP_NAME = "VoiceShift"' in src, "APP_NAME constant missing"
    assert "CONFIG_FILE" in src, "CONFIG_FILE constant missing"
    assert "CONFIG_DIR" in src, "CONFIG_DIR constant missing"


test("config.py -- required constants present", _config_constants)


def _voice_params_defaults():
    src = Path("src/audio_engine.py").read_text(encoding="utf-8")
    assert "pitch_semitones: float = 0.0" in src
    assert "formant_shift: float = 1.0" in src
    assert "volume_out: float = 1.0" in src
    assert "robotic_amount: float = 0.0" in src


test("audio_engine.py -- VoiceParams defaults correct", _voice_params_defaults)


def _openprocess_flags():
    src = Path("src/app_monitor.py").read_text(encoding="utf-8")
    assert "0x0410" in src, "OpenProcess must use 0x0410 (QUERY_INFO | VM_READ)"


test("app_monitor.py -- OpenProcess uses 0x0410", _openprocess_flags)


def _spec_no_block_cipher():
    src = Path("VoiceShift.spec").read_text(encoding="utf-8")
    assert "block_cipher" not in src, "VoiceShift.spec must not contain block_cipher"


test("VoiceShift.spec -- no deprecated block_cipher", _spec_no_block_cipher)


def _spec_uses_collect_all():
    """numpy/scipy use __getattr__ lazy loading (numpy>=1.23). collect_all() is
    the only safe bundling strategy — manual hiddenimports miss lazy-resolved
    submodules and cause ModuleNotFoundError at runtime."""
    src = Path("VoiceShift.spec").read_text(encoding="utf-8")
    assert 'collect_all' in src, (
        "VoiceShift.spec must use collect_all() for numpy and scipy. "
        "Manual hiddenimports break when numpy.__getattr__ lazy-loads submodules."
    )
    assert 'collect_all("numpy")' in src or 'collect_all('"'numpy'"')' in src, \
        "Missing: collect_all for numpy"
    assert 'collect_all("scipy")' in src or 'collect_all('"'scipy'"')' in src, \
        "Missing: collect_all for scipy"


test("VoiceShift.spec -- uses collect_all() for numpy and scipy", _spec_uses_collect_all)


def _spec_no_numpy_excludes():
    """NEVER exclude numpy.* or scipy.* submodules.
    numpy>=1.23 resolves them via __getattr__ — excluding any causes
    ModuleNotFoundError at runtime (numpy.f2py, numpy.testing, numpy.distutils…)."""
    src = Path("VoiceShift.spec").read_text(encoding="utf-8")
    in_excludes = False
    for lineno, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if "excludes=[" in line or 'excludes = [' in line:
            in_excludes = True
        if in_excludes:
            if ('numpy.' in stripped or 'scipy.' in stripped) and stripped.startswith('"'):
                raise AssertionError(
                    f"Line {lineno}: numpy/scipy submodule in excludes={stripped!r}. "
                    "numpy>=1.23 lazy-loads these via __getattr__; excluding them causes "
                    "ModuleNotFoundError at runtime. Use collect_all() instead."
                )
            # End of excludes block
            if stripped.startswith("]") or (in_excludes and "win_no_prefer" in line):
                in_excludes = False


test("VoiceShift.spec -- no numpy.*/scipy.* in excludes (lazy-load safety)", _spec_no_numpy_excludes)


def _rthook_exists():
    path = Path("rthooks/rthook_fix_stdio.py")
    assert path.exists(), f"{path} is missing -- required to fix stdio crash"
    src = path.read_text(encoding="utf-8")
    assert "sys.stdout" in src
    assert "sys.stderr" in src
    assert "os.devnull" in src


test("rthooks/rthook_fix_stdio.py -- exists and redirects stdio", _rthook_exists)


def _rthook_no_indentation():
    """Runtime hooks must have module-level code at column 0.
    Unexpected indentation causes IndentationError in PyInstaller Analysis phase."""
    path = Path("rthooks/rthook_fix_stdio.py")
    src = path.read_text(encoding="utf-8")
    # Must parse cleanly
    ast.parse(src, filename=str(path))
    # Module-level import/if statements must not be indented
    for i, line in enumerate(src.splitlines(), 1):
        if line and not line[0].isspace():
            continue  # unindented line — fine
        stripped = line.lstrip()
        if stripped.startswith("import ") or stripped.startswith("if sys."):
            # Check if this is inside a function/class (acceptable) or at module level (bad)
            # A simple heuristic: if any preceding non-blank, non-comment line has 0 indent
            # and is not a def/class, this is unexpectedly indented at module level
            indent = len(line) - len(stripped)
            if indent > 0 and i <= 20:  # first 20 lines — module-level region
                raise AssertionError(
                    f"Line {i}: module-level statement is indented ({indent} spaces): {line!r}. "
                    "Runtime hooks must have all code at column 0."
                )


test("rthooks/rthook_fix_stdio.py -- no unexpected indentation", _rthook_no_indentation)


def _spec_references_rthook():
    src = Path("VoiceShift.spec").read_text(encoding="utf-8")
    assert "rthook_fix_stdio" in src, "VoiceShift.spec must reference runtime hook"


test("VoiceShift.spec -- references runtime hook", _spec_references_rthook)


def _requirements_pinned():
    lns = [
        ln.strip()
        for ln in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    for line in lns:
        assert "==" in line, f"Dependency not pinned: {line!r}"


test("requirements.txt -- all dependencies pinned with ==", _requirements_pinned)


def _requirements_has_core_deps():
    src = Path("requirements.txt").read_text(encoding="utf-8")
    for dep in ["PyQt6", "sounddevice", "scipy", "numpy", "psutil"]:
        assert dep in src, f"Missing: {dep}"


test("requirements.txt -- all required packages present", _requirements_has_core_deps)


def _quality_scripts_exist():
    for name in ["check_syntax.py", "check_whitespace.py", "smoke_test.py"]:
        p = Path("scripts") / name
        assert p.exists(), f"Quality script missing: {p}"


test("scripts/ -- all quality scripts present", _quality_scripts_exist)


def _ci_has_quality_job():
    src = Path(".github/workflows/build.yml").read_text(encoding="utf-8")
    assert "quality" in src
    assert "check_syntax" in src or "Syntax" in src
    assert "check_whitespace" in src or "Whitespace" in src
    assert "smoke_test" in src or "Smoke" in src


test(".github/workflows/build.yml -- quality job with all checks", _ci_has_quality_job)


total = PASS + FAIL
print(f"\n{chr(61) * 52}")
print(f"Results: {PASS}/{total} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
