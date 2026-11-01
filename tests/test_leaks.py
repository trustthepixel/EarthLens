"""Regression tests for the tracked-file leak scanner."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_leaks.py"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@users.noreply.github.com")
    (root / "scripts").mkdir()
    shutil.copy2(CHECKER, root / "scripts" / "check_leaks.py")
    (root / "README.md").write_text("Safe project text.\n", encoding="utf-8")
    _git(root, "add", "README.md", "scripts/check_leaks.py")
    _git(root, "commit", "-qm", "fixture")
    return root


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [os.fspath(Path(os.sys.executable)), os.fspath(CHECKER), "--root", os.fspath(root)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_clean_tracked_file_passes(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 0
    assert "Leak check passed." in result.stdout


@pytest.mark.parametrize(
    ("content", "pattern_type"),
    [
        ("C:" + chr(92) + "Users" + chr(92) + "someone", "Windows user path"),
        ("/" + "home" + "/" + "someone/private", "Unix home path"),
        ("kaggle/input/" + "datasets/private", "Kaggle dataset path"),
        ("contact@" + "example" + ".com", "email address"),
    ],
)
def test_private_pattern_fails_without_echoing_content(repo: Path, content: str, pattern_type: str) -> None:
    (repo / "sample.txt").write_text(content, encoding="utf-8")
    _git(repo, "add", "sample.txt")
    result = _run(repo)
    assert result.returncode == 1
    assert "sample.txt: " + pattern_type in result.stdout
    assert content not in result.stdout


def test_leakword_fails(repo: Path) -> None:
    secret_word = "private" + "marker"
    (repo / ".leakwords").write_text(secret_word + "\n", encoding="utf-8")
    (repo / "sample.txt").write_text("prefix " + secret_word + " suffix", encoding="utf-8")
    _git(repo, "add", ".leakwords", "sample.txt")
    result = _run(repo)
    assert result.returncode == 1
    assert "sample.txt: leakword" in result.stdout
    assert secret_word not in result.stdout


def test_tracked_model_path_fails(repo: Path) -> None:
    (repo / "model").mkdir()
    (repo / "model" / "weights.txt").write_text("binary not required", encoding="utf-8")
    _git(repo, "add", "model/weights.txt")
    result = _run(repo)
    assert result.returncode == 1
    assert "model/weights.txt: prohibited tracked path" in result.stdout


def test_staged_deletion_of_prohibited_path_is_not_a_tracked_violation(repo: Path) -> None:
    (repo / "model").mkdir()
    path = repo / "model" / "weights.txt"
    path.write_text("removed local artifact", encoding="utf-8")
    _git(repo, "add", "model/weights.txt")
    _git(repo, "commit", "-qm", "add temporary model artifact")
    _git(repo, "rm", "model/weights.txt")

    result = _run(repo)

    assert result.returncode == 0
    assert "Leak check passed." in result.stdout


def test_staged_untracking_of_local_model_does_not_scan_retained_local_file(repo: Path) -> None:
    (repo / "model").mkdir()
    path = repo / "model" / "weights.txt"
    path.write_text("local artifact retained outside Git", encoding="utf-8")
    _git(repo, "add", "model/weights.txt")
    _git(repo, "commit", "-qm", "add temporary model artifact")
    _git(repo, "rm", "--cached", "model/weights.txt")

    result = _run(repo)

    assert path.is_file()
    assert result.returncode == 0
    assert "Leak check passed." in result.stdout


def test_allowed_github_noreply_address_passes(repo: Path) -> None:
    (repo / "contact.txt").write_text("tp-team@users.noreply.github.com", encoding="utf-8")
    _git(repo, "add", "contact.txt")
    result = _run(repo)
    assert result.returncode == 0


def test_staged_untracked_content_is_scanned(repo: Path) -> None:
    path = repo / "staged.txt"
    path.write_text("temporary " + "/" + "home" + "/" + "private", encoding="utf-8")
    _git(repo, "add", "staged.txt")
    result = _run(repo)
    assert result.returncode == 1
    assert "staged.txt: Unix home path" in result.stdout
