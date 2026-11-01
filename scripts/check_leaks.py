"""Check tracked and staged files for private data and prohibited artifacts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
FORBIDDEN_PATHS = {"model", "docs", "legacy", "data_raw", "keys"}
FORBIDDEN_SUFFIXES = {".pem", ".onnx", ".pt", ".npz"}
IGNORED_FILES = {"AGENTS.md", "scripts/check_leaks.py"}


def _git_names(root: Path, *args: str) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {name.decode("utf-8", errors="surrogateescape") for name in result.stdout.split(b"\0") if name}


def _violations(root: Path) -> list[tuple[str, str]]:
    names = _git_names(root, "ls-files", "-z")
    staged = _git_names(root, "diff", "--cached", "--name-only", "-z")
    deleted = _git_names(root, "diff", "--cached", "--name-only", "--diff-filter=D", "-z")
    names = (names | staged) - deleted
    leakwords_path = root / ".leakwords"
    leakwords = []
    if leakwords_path.is_file():
        leakwords = [line.strip() for line in leakwords_path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]

    found: set[tuple[str, str]] = set()
    for name in sorted(names):
        normalized = name.replace("\\", "/").lstrip("./")
        if normalized in IGNORED_FILES:
            continue
        parts = normalized.split("/")
        if any(part.casefold() in FORBIDDEN_PATHS for part in parts) or Path(normalized).suffix.casefold() in FORBIDDEN_SUFFIXES:
            found.add((name, "prohibited tracked path"))

        file_path = root / Path(name)
        try:
            resolved = file_path.resolve(strict=True)
            resolved.relative_to(root.resolve())
            if not resolved.is_file():
                continue
            if resolved.suffix.casefold() == ".npy":
                continue
            raw = resolved.read_bytes()
        except (OSError, ValueError):
            continue
        if b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="replace")
        if "C:\\Users" in text:
            found.add((name, "Windows user path"))
        if "/home/" in text:
            found.add((name, "Unix home path"))
        if "kaggle/input/datasets/" in text:
            found.add((name, "Kaggle dataset path"))
        for address in EMAIL_RE.findall(text):
            lowered = address.casefold()
            if not lowered.endswith(("users.noreply.github.com", "users.noreply.huggingface.co")):
                found.add((name, "email address"))
                break
        if any(word in text for word in leakwords):
            found.add((name, "leakword"))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (defaults to current directory)")
    args = parser.parse_args()
    try:
        violations = _violations(args.root.resolve())
    except subprocess.CalledProcessError:
        print("Leak check could not read the Git index.", file=sys.stderr)
        return 2
    for filename, pattern_type in violations:
        print(f"{filename}: {pattern_type}")
    if violations:
        print(f"Leak check failed: {len(violations)} violation(s).")
        return 1
    print("Leak check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
