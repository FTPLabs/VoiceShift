#!/usr/bin/env python3
  """
  check_syntax.py — validate Python syntax in all src/*.py files using ast.parse.
  Exits with code 1 if any file has a syntax error.

  Usage:
      python scripts/check_syntax.py
  """
  import ast
  import sys
  from pathlib import Path

  errors = []
  checked = 0

  for path in sorted(Path("src").glob("**/*.py")):
      checked += 1
      try:
          source = path.read_text(encoding="utf-8")
          ast.parse(source, filename=str(path))
          print(f"  OK  {path}")
      except SyntaxError as e:
          errors.append((path, e))
          print(f" ERR  {path}:{e.lineno}: {e.msg}")
      except UnicodeDecodeError as e:
          errors.append((path, e))
          print(f" ERR  {path}: encoding error — {e}")

  print(f"\nChecked {checked} file(s).", end=" ")
  if errors:
      print(f"{len(errors)} syntax error(s) found.")
      sys.exit(1)
  else:
      print("All files OK.")
  