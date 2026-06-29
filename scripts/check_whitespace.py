#!/usr/bin/env python3
"""
check_whitespace.py -- detect whitespace, encoding, and indentation problems
in all src/*.py files.

Checks (errors -> exits 1):
  - Non-UTF-8 encoding
  - Trailing whitespace (spaces or tabs at end of line)
  - Mixed tabs and spaces in indentation on the same line
  - Null bytes
  - Invisible control characters

Warnings (logged but do not fail):
  - Windows CRLF line endings

Usage:
    python scripts/check_whitespace.py
"""
import re
import sys
from pathlib import Path

TRAILING_WS  = re.compile(r"[ \t]+$", re.MULTILINE)
MIXED_INDENT = re.compile(r"^( +\t|\t+ )", re.MULTILINE)
NULL_BYTE    = re.compile(r"\x00")
CTRL_CHARS   = re.compile(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]")

errors: list[str] = []
warnings: list[str] = []
checked = 0

for path in sorted(Path("src").glob("**/*.py")):
    checked += 1
    try:
        raw = path.read_bytes()
    except OSError as e:
        errors.append(f"{path}: cannot read -- {e}")
        continue

    if b"\r\n" in raw:
        warnings.append(f"{path}: CRLF line endings (recommend converting to LF)")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errors.append(f"{path}: not valid UTF-8 -- {e}")
        continue

    checks = {
        "trailing whitespace":    TRAILING_WS,
        "mixed tab/space indent": MIXED_INDENT,
        "null byte":              NULL_BYTE,
        "control character":      CTRL_CHARS,
    }
    for label, pat in checks.items():
        for m in pat.finditer(text):
            lineno = text[: m.start()].count("\n") + 1
            snippet = repr(m.group()[:30])
            errors.append(f"{path}:{lineno}: {label} -- {snippet}")

for w in warnings:
    print(f"WARN  {w}")
for e in errors:
    print(f" ERR  {e}")

print(f"\nChecked {checked} file(s).", end=" ")
if errors:
    print(f"{len(errors)} error(s) found.")
    sys.exit(1)
elif warnings:
    print(f"All OK ({len(warnings)} warning(s) above).")
else:
    print("All OK.")
