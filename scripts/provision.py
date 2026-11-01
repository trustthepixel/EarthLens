"""Provision an Ed25519 source keypair without displaying private material."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]


def _restrict_private_file(path: Path) -> None:
    if os.name == 'nt':
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], check=True, capture_output=True, text=True)
        sid = next(row[-1] for row in csv.reader(identity.stdout.splitlines()) if row and row[-1].startswith('S-1-'))
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(F)'], check=True, capture_output=True)
    else:
        path.chmod(0o600)


def provision(root: Path, force: bool = False) -> tuple[Path, Path, str]:
    private_path = root / 'keys' / 'source_private.pem'
    public_path = root / 'trusted_keys' / 'source.pem'
    if not force and (private_path.exists() or public_path.exists()):
        raise FileExistsError('A source key already exists; use --force to replace it.')
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    public_bytes = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    try:
        private_path.write_bytes(private_bytes)
        _restrict_private_file(private_path)
        public_path.write_bytes(public_bytes)
    except Exception:
        private_path.unlink(missing_ok=True)
        raise
    from tp.provenance import public_key_id
    return private_path, public_path, public_key_id(private.public_key())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='replace an existing source keypair')
    parser.add_argument('--root', type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        private, public, key_id = provision(args.root, args.force)
    except Exception as exc:
        print(f'Provisioning failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1
    print(f'Private key created at {private.relative_to(args.root).as_posix()} (restricted permissions).')
    print(f'Public key created at {public.relative_to(args.root).as_posix()} (key id {key_id}).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
