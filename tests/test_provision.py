"""Verify safe key provisioning in an isolated temporary directory."""

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from scripts.provision import provision
from tp.provenance import public_key_id


def test_provisions_pair_and_refuses_overwrite(tmp_path):
    private, public, key_id = provision(tmp_path)
    assert private.exists() and public.exists()
    loaded_private = serialization.load_pem_private_key(private.read_bytes(), password=None)
    loaded_public = serialization.load_pem_public_key(public.read_bytes())
    assert public_key_id(loaded_private.public_key()) == key_id == public_key_id(loaded_public)
    assert 'PRIVATE KEY' in private.read_text(encoding='ascii')
    with pytest.raises(FileExistsError):
        provision(tmp_path)


def test_force_replaces_pair(tmp_path):
    private, public, key_id = provision(tmp_path)
    previous = key_id
    _, _, current = provision(tmp_path, force=True)
    assert current != previous
    assert public.exists() and private.exists()
