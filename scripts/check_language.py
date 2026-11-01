"""Reject common French text in project-authored user-facing files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ACCENTED = re.compile(r"[éèêàùçôîÉÈÊÀÙÇÔÎ]")
FRENCH_WORD = re.compile(r"\b(?:le|la|les|des|une|pour|avec|erreur|scène|résultat)\b", re.IGNORECASE)
INCLUDED_GLOBS = (
    "app.py",
    "ui/*.py",
    "dashboard_pages/*.py",
    "assets/*",
    "README.md",
    "DEVELOPMENT_LOGS.md",
    "scripts/*.md",
    "attacker/README.md",
    "space_static/*.html",
    "tp/*.py",
)
EXCLUDED_TP = {"tp/attacks.py", "tp/provenance.py", "tp/sentinel_live.py"}


def _files(root: Path) -> list[Path]:
    found: set[Path] = set()
    for pattern in INCLUDED_GLOBS:
        candidate = root / pattern
        if candidate.is_file():
            found.add(candidate)
        else:
            found.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(path for path in found if path.relative_to(root).as_posix() not in EXCLUDED_TP)


def _violations(root: Path) -> list[tuple[str, int]]:
    issues = []
    for path in _files(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(lines, 1):
            if "# lang-ok" in line:
                continue
            if ACCENTED.search(line) or FRENCH_WORD.search(line):
                issues.append((path.relative_to(root).as_posix(), line_number))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root (defaults to current directory)")
    root = parser.parse_args().root.resolve()
    violations = _violations(root)
    for filename, line_number in violations:
        print(f"{filename}:{line_number}")
    if violations:
        print(f"Language check failed: {len(violations)} issue(s).")
        return 1
    print("Language check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
