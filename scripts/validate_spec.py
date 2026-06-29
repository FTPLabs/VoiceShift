#!/usr/bin/env python3
"""
validate_spec.py — standalone VoiceShift.spec + rthook pre-build validator.

Detects every known class of PyInstaller build failure for this project
before pyinstaller runs, so the Windows CI runner is not wasted on
predictable errors.

Usage:
    python scripts/validate_spec.py          # from repo root
    python scripts/validate_spec.py --fix    # auto-fix what can be fixed

Exit codes: 0 = all good, 1 = validation errors found.
"""
import ast
import argparse
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "VoiceShift.spec"
RTHOOK = ROOT / "rthooks" / "rthook_fix_stdio.py"

PASS_COUNT = 0
FAIL_COUNT = 0
FIXES_APPLIED = 0


def check(name: str, fn, fix_fn=None, fix_mode: bool = False) -> bool:
    global PASS_COUNT, FAIL_COUNT, FIXES_APPLIED
    try:
        fn()
        print(f"  PASS  {name}")
        PASS_COUNT += 1
        return True
    except AssertionError as e:
        if fix_mode and fix_fn:
            try:
                fix_fn()
                FIXES_APPLIED += 1
                print(f"  FIXD  {name}  (auto-fixed)")
                PASS_COUNT += 1
                return True
            except Exception as fe:
                print(f"  FAIL  {name}")
                print(f"        {e}")
                print(f"        Auto-fix failed: {fe}")
        else:
            print(f"  FAIL  {name}")
            print(f"        {e}")
        FAIL_COUNT += 1
        return False


# ---------------------------------------------------------------------------
# Check 1: spec uses collect_all for numpy
# ---------------------------------------------------------------------------
def _check_collect_all_numpy():
    src = SPEC.read_text(encoding="utf-8")
    assert 'collect_all("numpy")' in src or "collect_all('numpy')" in src, (
        "VoiceShift.spec must call collect_all('numpy').\n"
        "        numpy>=1.23 uses __getattr__ lazy loading — any excluded numpy.*\n"
        "        submodule causes ModuleNotFoundError at runtime.\n"
        "        Fix: add  numpy_datas, numpy_bins, numpy_hidden = collect_all('numpy')\n"
        "        and spread *numpy_hidden into hiddenimports, remove all numpy.* from excludes."
    )


# ---------------------------------------------------------------------------
# Check 2: spec uses collect_all for scipy
# ---------------------------------------------------------------------------
def _check_collect_all_scipy():
    src = SPEC.read_text(encoding="utf-8")
    assert 'collect_all("scipy")' in src or "collect_all('scipy')" in src, (
        "VoiceShift.spec must call collect_all('scipy').\n"
        "        scipy triggers numpy lazy-loading via scipy._lib.array_api_compat.numpy,\n"
        "        which calls numpy.__getattr__ for every lazy-loadable numpy submodule.\n"
        "        Fix: add  scipy_datas, scipy_bins, scipy_hidden = collect_all('scipy')"
    )


# ---------------------------------------------------------------------------
# Check 3: no numpy.* or scipy.* in excludes block
# ---------------------------------------------------------------------------
def _check_no_numpy_in_excludes():
    src = SPEC.read_text(encoding="utf-8")
    in_excludes = False
    bad_lines = []
    for lineno, line in enumerate(src.splitlines(), 1):
        if "excludes=[" in line or "excludes = [" in line:
            in_excludes = True
        if in_excludes:
            stripped = line.strip()
            if (stripped.startswith('"numpy.') or stripped.startswith("'numpy.")
                    or stripped.startswith('"scipy.') or stripped.startswith("'scipy.")):
                bad_lines.append(f"line {lineno}: {stripped}")
            if stripped.startswith("]") and in_excludes:
                in_excludes = False
    assert not bad_lines, (
        "numpy/scipy submodules found in excludes:\n"
        + "\n".join(f"          {b}" for b in bad_lines)
        + "\n        NEVER exclude numpy.* or scipy.*. They use __getattr__ lazy loading.\n"
        + "        Use collect_all() instead — see pyinstaller-collect-all skill."
    )


# ---------------------------------------------------------------------------
# Check 4: rthook file exists
# ---------------------------------------------------------------------------
def _check_rthook_exists():
    assert RTHOOK.exists(), (
        f"{RTHOOK.name} is missing.\n"
        "        This hook prevents AttributeError: 'NoneType'.write in console=False builds\n"
        "        by replacing sys.stdout/stderr=None with an os.devnull sink.\n"
        "        Fix: create rthooks/rthook_fix_stdio.py"
    )


# ---------------------------------------------------------------------------
# Check 5: rthook parses cleanly (no IndentationError)
# ---------------------------------------------------------------------------
def _check_rthook_syntax():
    src = RTHOOK.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(RTHOOK))
    except SyntaxError as e:
        raise AssertionError(
            f"SyntaxError in rthook_fix_stdio.py: {e}\n"
            "        Cause: module-level code was indented (inherited from docstring).\n"
            "        Fix: ensure all import/if statements start at column 0."
        ) from e


def _fix_rthook_syntax():
    src = RTHOOK.read_text(encoding="utf-8")
    lines = src.splitlines()
    fixed = []
    in_docstring = False
    for line in lines:
        if line.strip().startswith('"""') or line.strip().startswith("'''"):
            in_docstring = not in_docstring
            fixed.append(line.lstrip() if not in_docstring else line)
        elif not in_docstring:
            fixed.append(line.lstrip())
        else:
            fixed.append(line)
    RTHOOK.write_text("\n".join(fixed) + "\n", encoding="utf-8")
    ast.parse(RTHOOK.read_text(encoding="utf-8"))  # verify


# ---------------------------------------------------------------------------
# Check 6: rthook module-level code at column 0
# ---------------------------------------------------------------------------
def _check_rthook_indentation():
    src = RTHOOK.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        if not line.strip() or line.strip().startswith("#") or line.strip().startswith('"""'):
            continue
        stripped = line.lstrip()
        if (stripped.startswith("import ") or stripped.startswith("if sys.")):
            indent = len(line) - len(stripped)
            if indent > 0 and i <= 25:
                raise AssertionError(
                    f"Line {i}: module-level statement indented {indent} spaces: {line!r}\n"
                    "        Runtime hooks must have all code at column 0.\n"
                    "        Cause: copy-paste from docstring context bleeds indentation."
                )


# ---------------------------------------------------------------------------
# Check 7: spec references rthook
# ---------------------------------------------------------------------------
def _check_spec_references_rthook():
    src = SPEC.read_text(encoding="utf-8")
    assert "rthook_fix_stdio" in src, (
        "VoiceShift.spec must list rthooks/rthook_fix_stdio.py in runtime_hooks.\n"
        "        Without it, console=False builds crash with AttributeError on numpy import."
    )


# ---------------------------------------------------------------------------
# Check 8: no deprecated block_cipher
# ---------------------------------------------------------------------------
def _check_no_block_cipher():
    src = SPEC.read_text(encoding="utf-8")
    assert "block_cipher" not in src, (
        "VoiceShift.spec contains deprecated 'block_cipher'.\n"
        "        Removed in PyInstaller 6.x. Remove it from Analysis() and PYZ()."
    )


# ---------------------------------------------------------------------------
# Check 9: spec imports collect_all from pyinstaller hooks
# ---------------------------------------------------------------------------
def _check_collect_all_import():
    src = SPEC.read_text(encoding="utf-8")
    assert "collect_all" in src and "from PyInstaller.utils.hooks import" in src, (
        "VoiceShift.spec must import collect_all from PyInstaller.utils.hooks.\n"
        "        Add: from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="VoiceShift spec pre-build validator")
    parser.add_argument("--fix", action="store_true", help="Auto-fix what can be fixed")
    args = parser.parse_args()
    fix = args.fix

    print("VoiceShift Pre-Build Spec Validator")
    print("=" * 52)

    check("spec: collect_all('numpy') present", _check_collect_all_numpy)
    check("spec: collect_all('scipy') present", _check_collect_all_scipy)
    check("spec: collect_all imported from PyInstaller.utils.hooks", _check_collect_all_import)
    check("spec: no numpy.*/scipy.* in excludes block", _check_no_numpy_in_excludes)
    check("spec: references rthook_fix_stdio", _check_spec_references_rthook)
    check("spec: no deprecated block_cipher", _check_no_block_cipher)
    check("rthook: file exists", _check_rthook_exists)
    check("rthook: parses cleanly (no IndentationError)", _check_rthook_syntax,
          fix_fn=_fix_rthook_syntax, fix_mode=fix)
    check("rthook: module-level code at column 0", _check_rthook_indentation,
          fix_fn=_fix_rthook_syntax, fix_mode=fix)

    print()
    print("=" * 52)
    total = PASS_COUNT + FAIL_COUNT
    if FIXES_APPLIED:
        print(f"Auto-fixed: {FIXES_APPLIED} issue(s)")
    print(f"Results: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")

    if FAIL_COUNT:
        print()
        print("Fix these issues before running pyinstaller.")
        print("See skills: pyinstaller-numpy-lazy-load, pyinstaller-rthook-indentation,")
        print("            pyinstaller-scipy-import-chain, pyinstaller-collect-all")
        sys.exit(1)
    else:
        print("All checks passed. Safe to run pyinstaller.")


if __name__ == "__main__":
    main()
