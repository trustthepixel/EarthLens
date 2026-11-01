"""Run deployment preflight checks and print an OK/FAILED report."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from scripts.check_language import _violations as language_violations
from scripts.check_leaks import _violations as leak_violations

WINDOWS_ONLY = {
    'pywin32', 'pypiwin32', 'pywin32ctypes', 'windows-curses', 'pywinpty',
    'wincertstore', 'win-inet-pton',
}
PACKAGE_LINE = re.compile(r'^([A-Za-z0-9_.-]+)')


def _git_files(root: Path, *args: str) -> list[str]:
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', *args], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [name.decode('utf-8', errors='surrogateescape') for name in result.stdout.split(b'\0') if name]


def _requirement_issues(requirements: str) -> list[str]:
    issues = []
    for line_number, raw in enumerate(requirements.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('-'):
            continue
        match = PACKAGE_LINE.match(line)
        if not match:
            issues.append(f'line {line_number}: invalid package entry')
            continue
        package = match.group(1).casefold().replace('_', '-').replace('.', '-')
        compact = re.sub(r'[-_.]', '', package)
        normalized_windows_only = {re.sub(r'[-_.]', '', name.casefold()) for name in WINDOWS_ONLY}
        if compact.startswith('torch') or package in WINDOWS_ONLY or compact in normalized_windows_only:
            issues.append(f'line {line_number}: prohibited runtime package')
        if '==' not in line:
            issues.append(f'line {line_number}: dependency is not pinned')
    return issues


def _protected_tracked_paths(paths: list[str]) -> list[str]:
    issues = []
    for name in paths:
        normalized = name.replace('\\', '/').casefold()
        parts = normalized.split('/')
        if parts[0] == 'model':
            issues.append('tracked model artifact')
        private_suffixes = {'.pem', '.key', '.ppk', '.p12', '.pfx'}
        if 'keys' in parts or 'trusted_keys' in parts or Path(normalized).suffix in private_suffixes:
            issues.append('tracked key artifact')
        if any(part == '.env' or part.startswith('.env.') for part in parts):
            issues.append('tracked environment file')
    return issues


def build_report(root: str | Path = '.') -> tuple[list[tuple[str, bool, str]], int]:
    project = Path(root).resolve()
    checks: list[tuple[str, bool, str]] = []
    checks.append(('Root app.py exists', (project / 'app.py').is_file(), 'app.py must be at the repository root.'))
    requirements_path = project / 'requirements.txt'
    requirement_issues = _requirement_issues(requirements_path.read_text(encoding='utf-8') if requirements_path.is_file() else '')
    checks.append(('Runtime requirements are portable and pinned', requirements_path.is_file() and not requirement_issues,
                   '; '.join(requirement_issues) if requirement_issues else ''))

    try:
        tracked = _git_files(project)
        all_files = _git_files(project, '--cached', '--others', '--exclude-standard')
        protected = _protected_tracked_paths(tracked)
        checks.append(('No tracked model, key, or environment files', not protected,
                       f'{len(protected)} protected tracked path(s) found.' if protected else ''))
    except (OSError, subprocess.CalledProcessError):
        tracked, all_files = [], []
        checks.append(('Git index is readable', False, 'Run this check inside the project Git repository.'))

    try:
        leaks = leak_violations(project)
        checks.append(('Leak and personal-data check', not leaks,
                       f'{len(leaks)} leak/security issue(s) found.' if leaks else ''))
    except (OSError, subprocess.CalledProcessError):
        checks.append(('Leak and personal-data check', False, 'The existing leak checker could not inspect Git files.'))
    language = language_violations(project)
    checks.append(('Project language check', not language,
                   f'{len(language)} non-English line(s) found.' if language else ''))

    chip_count = len(list((project / 'samples').glob('chip_*.npy')))
    checks.append(('Sample chip limit (20)', chip_count <= 20, f'{chip_count} chip file(s).'))

    unseen_files = list((project / 'unseen_pack').glob('chip_*.npy'))
    unseen_count = len(unseen_files)
    checks.append(('Unseen pack chip limit (21)', unseen_count <= 21, f'{unseen_count} chip file(s).'))
    unseen_bytes = sum(path.stat().st_size for path in (project / 'unseen_pack').glob('*') if path.is_file())
    unseen_ok = unseen_bytes <= 15 * 1024 * 1024
    checks.append(('Unseen pack size limit (15 MiB)', unseen_ok, f'{unseen_bytes / (1024 * 1024):.2f} MiB.'))

    total_bytes = 0
    for name in set(all_files):
        path = project / name
        try:
            if path.is_file():
                total_bytes += path.stat().st_size
        except OSError:
            continue
    size_ok = total_bytes < 100 * 1024 * 1024
    checks.append(('Deployment repository size (< 100 MB)', size_ok, f'{total_bytes / 1_000_000:.2f} MB.'))

    failures = sum(not passed for _, passed, _ in checks)
    return checks, failures


def main() -> int:
    checks, failures = build_report(Path(__file__).resolve().parents[1])
    print('Deployment preflight report')
    for label, passed, detail in checks:
        print(f"{'OK' if passed else 'FAILED'} - {label}" + (f': {detail}' if detail else ''))
    print('OK - Deployment preflight passed.' if failures == 0 else f'FAILED - {failures} check(s) need attention.')
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
