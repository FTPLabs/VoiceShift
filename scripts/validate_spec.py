#!/usr/bin/env python3
"""
validate_spec.py — standalone VoiceShift.spec + rthook pre-build validator.

Detects every known class of PyInstaller build failure for this project
before pyinstaller runs.

Known failure classes caught:
  1. numpy/scipy not collected with collect_all()     -> ModuleNotFoundError at runtime
  2. numpy.*/scipy.* in excludes                     -> ModuleNotFoundError via __getattr__
  3. stdlib modules in excludes (pydoc, inspect…)    -> ModuleNotFoundError (scipy._lib._docscrape)
  4. rthook_fix_stdio.py IndentationError            -> Analysis phase crash
  5. rthook module-level code not at column 0        -> IndentationError at runtime
  6. spec missing rthook reference                   -> AttributeError: NoneType.write
  7. deprecated block_cipher                         -> PyInstaller 6.x crash

Usage:
    python scripts/validate_spec.py          # from repo root
    python scripts/validate_spec.py --fix    # auto-fix rthook indentation

Exit codes: 0 = all good, 1 = validation errors found.
"""
import ast
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "VoiceShift.spec"
RTHOOK = ROOT / "rthooks" / "rthook_fix_stdio.py"

# stdlib modules that scipy internals are known to import at runtime.
# Excluding any of these causes ModuleNotFoundError even when your own code
# never imports them directly.
DANGEROUS_STDLIB_EXCLUDES = {
    "pydoc",       # scipy._lib._docscrape
    "inspect",     # scipy._lib._docscrape, many scipy internals
    "textwrap",    # scipy._lib._docscrape
    "difflib",     # scipy._lib._docscrape
    "doctest",     # scipy internals
    "pprint",      # scipy internals
    "reprlib",     # inspect (transitive)
    "dis",         # inspect (transitive)
    "opcode",      # dis (transitive)
    "tokenize",    # inspect (transitive)
    "token",       # tokenize (transitive)
    "ast",         # inspect (transitive)
}

PASS_COUNT = 0
FAIL_COUNT = 0
FIXES_APPLIED = 0


def check(name, fn, fix_fn=None, fix_mode=False):
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


def _excludes_block(src):
    """Extract lines inside the excludes=[...] block."""
    in_ex = False
    lines = []
    for lineno, line in enumerate(src.splitlines(), 1):
        if "excludes=[" in line or "excludes = [" in line:
            in_ex = True
        if in_ex:
            stripped = line.strip()
            # skip comment lines and blank lines
            if stripped and not stripped.startswith("#"):
                lines.append((lineno, stripped))
            if stripped.startswith("]") and len(lines) > 0:
                in_ex = False
    return lines


def _check_collect_all_numpy():
    src = SPEC.read_text(encoding="utf-8")
    assert 'collect_all("numpy")' in src or "collect_all('numpy')" in src, (
        "spec must call collect_all('numpy'). numpy>=1.23 uses __getattr__ lazy loading.\n"
        "        Fix: numpy_datas, numpy_bins, numpy_hidden = collect_all('numpy')"
    )


def _check_collect_all_scipy():
    src = SPEC.read_text(encoding="utf-8")
    assert 'collect_all("scipy")' in src or "collect_all('scipy')" in src, (
        "spec must call collect_all('scipy'). scipy triggers numpy __getattr__ chains.\n"
        "        Fix: scipy_datas, scipy_bins, scipy_hidden = collect_all('scipy')"
    )


def _check_collect_all_import():
    src = SPEC.read_text(encoding="utf-8")
    assert "collect_all" in src and "from PyInstaller.utils.hooks import" in src, (
        "spec must import collect_all.\n"
        "        Fix: from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_all"
    )


def _check_no_numpy_in_excludes():
    src = SPEC.read_text(encoding="utf-8")
    bad = []
    for lineno, s in _excludes_block(src):
        if s.startswith('"numpy.') or s.startswith("'numpy.") \
                or s.startswith('"scipy.') or s.startswith("'scipy."):
            bad.append(f"line {lineno}: {s}")
    assert not bad, (
        "numpy/scipy submodules in excludes will crash at runtime (lazy __getattr__):\n"
        + "\n".join(f"          {b}" for b in bad)
        + "\n        Remove them and use collect_all() instead."
    )


def _check_no_stdlib_in_excludes():
    src = SPEC.read_text(encoding="utf-8")
    bad = []
    for lineno, s in _excludes_block(src):
        for mod in DANGEROUS_STDLIB_EXCLUDES:
            if s in (f'"{mod}"', f"'{mod}'", f'"{mod}",', f"'{mod}',"):
                bad.append(f"line {lineno}: {s}  (needed by scipy at runtime)")
                break
    assert not bad, (
        "Stdlib modules in excludes block will crash scipy at runtime.\n"
        + "\n".join(f"          {b}" for b in bad)
        + "\n        Remove them — never exclude: " + ", ".join(sorted(DANGEROUS_STDLIB_EXCLUDES))
    )


def _check_spec_references_rthook():
    src = SPEC.read_text(encoding="utf-8")
    assert "rthook_fix_stdio" in src, (
        "spec must list rthooks/rthook_fix_stdio.py in runtime_hooks.\n"
        "        Without it, console=False builds crash: AttributeError: 'NoneType'.write"
    )


def _check_no_block_cipher():
    src = SPEC.read_text(encoding="utf-8")
    assert "block_cipher" not in src, (
        "spec contains deprecated 'block_cipher'. Removed in PyInstaller 6.x.\n"
        "        Remove from Analysis() and PYZ()."
    )


def _check_rthook_exists():
    assert RTHOOK.exists(), f"{RTHOOK.name} is missing — create rthooks/rthook_fix_stdio.py"


def _check_rthook_syntax():
    src = RTHOOK.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(RTHOOK))
    except SyntaxError as e:
        raise AssertionError(
            f"SyntaxError in rthook_fix_stdio.py: {e}\n"
            "        All import/if statements must start at column 0."
        ) from e


def _fix_rthook():
    src = RTHOOK.read_text(encoding="utf-8")
    fixed = [line.lstrip() for line in src.splitlines()]
    RTHOOK.write_text("\n".join(fixed) + "\n", encoding="utf-8")
    ast.parse(RTHOOK.read_text(encoding="utf-8"))


def _check_rthook_indentation():
    if not RTHOOK.exists():
        return
    src = RTHOOK.read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("import ") or stripped.startswith("if sys."):
            indent = len(line) - len(line.lstrip())
            if indent > 0 and i <= 30:
                raise AssertionError(
                    f"Line {i}: module-level statement indented {indent} spaces.\n"
                    "        All rthook code must start at column 0."
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    fix = args.fix

    print("VoiceShift Pre-Build Spec Validator")
    print("=" * 52)
    print(f"Spec:   {SPEC}")
    print(f"Rthook: {RTHOOK}")
    print()

    check("spec: collect_all('numpy') present", _check_collect_all_numpy)
    check("spec: collect_all('scipy') present", _check_collect_all_scipy)
    check("spec: collect_all imported", _check_collect_all_import)
    check("spec: no numpy.*/scipy.* in excludes", _check_no_numpy_in_excludes)
    check("spec: no stdlib modules in excludes", _check_no_stdlib_in_excludes)
    check("spec: references rthook_fix_stdio", _check_spec_references_rthook)
    check("spec: no deprecated block_cipher", _check_no_block_cipher)
    check("rthook: file exists", _check_rthook_exists)
    check("rthook: parses cleanly (no IndentationError)", _check_rthook_syntax,
          fix_fn=_fix_rthook, fix_mode=fix)
    check("rthook: module-level code at column 0", _check_rthook_indentation,
          fix_fn=_fix_rthook, fix_mode=fix)

    print()
    print("=" * 52)
    if FIXES_APPLIED:
        print(f"Auto-fixed: {FIXES_APPLIED} issue(s)")
    total = PASS_COUNT + FAIL_COUNT
    print(f"Results: {PASS_COUNT}/{total} passed, {FAIL_COUNT} failed")

    if FAIL_COUNT:
        print()
        print("Fix these before running pyinstaller.")
        print("Skills: pyinstaller-numpy-lazy-load, pyinstaller-scipy-import-chain,")
        print("        pyinstaller-collect-all, pyinstaller-rthook-indentation")
        sys.exit(1)
    else:
        print("All checks passed. Safe to run pyinstaller.")


if __name__ == "__main__":
    main()
