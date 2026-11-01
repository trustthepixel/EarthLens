"""Regression tests for the authored-text language scanner."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_language.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("English project documentation.\n", encoding="utf-8")
    return root


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [os.fspath(Path(os.sys.executable)), os.fspath(CHECKER), "--root", os.fspath(root)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_clean_english_file_passes(repo: Path) -> None:
    result = _run(repo)
    assert result.returncode == 0
    assert "Language check passed." in result.stdout


@pytest.mark.parametrize("french_line", ["A useful résumé.", "le fichier contient du texte."])
def test_french_text_fails_and_reports_only_file_and_line(repo: Path, french_line: str) -> None:
    (repo / "README.md").write_text("English line.\n" + french_line + "\n", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 1
    assert "README.md:2" in result.stdout
    assert french_line not in result.stdout


def test_lang_ok_line_is_allowed(repo: Path) -> None:
    (repo / "README.md").write_text("English heading.\nle texte permis # lang-ok\n", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0


def test_legacy_language_files_are_excluded(repo: Path) -> None:
    (repo / "tp").mkdir()
    (repo / "tp" / "attacks.py").write_text("le résultat est valide.\n", encoding="utf-8")
    result = _run(repo)
    assert result.returncode == 0


def test_dashboard_authored_text_is_english_and_legacy_reason_helper_is_single_escape():
    root = Path(__file__).resolve().parents[1]
    from scripts.check_language import _violations

    assert not _violations(root)
    helper = (root / 'ui' / 'language.py').read_text(encoding='utf-8')
    assert helper.count('# lang-ok') == 1
    assert 'streamlit.warning(str(reason))' in helper
