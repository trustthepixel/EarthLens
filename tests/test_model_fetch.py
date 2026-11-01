"""Test model acquisition behavior without network access."""

import json
import sys
from types import SimpleNamespace

import pytest

from tp import model_fetch


def _valid_config():
    return json.dumps({'calibration': {'t_low': 1.0}}).encode()


def test_downloads_only_absent_or_empty_files(monkeypatch, tmp_path):
    monkeypatch.setenv('HF_MODEL_REPO', 'test/public-model')
    (tmp_path / 'detector.onnx').write_bytes(b'existing')
    (tmp_path / 'golden.npz').write_bytes(b'')
    downloaded = []

    def fake_download(repo_id, filename, repo_type, etag_timeout):
        assert repo_id == 'test/public-model' and repo_type == 'model'
        assert etag_timeout == 10
        downloaded.append(filename)
        path = tmp_path / f'cached-{filename}'
        path.write_bytes(_valid_config() if filename == 'config.json' else b'artifact')
        return str(path)

    monkeypatch.setattr(model_fetch, 'hf_hub_download', fake_download)
    assert model_fetch.ensure_model(tmp_path) == tmp_path
    assert downloaded == ['config.json', 'golden.npz']
    assert (tmp_path / 'detector.onnx').read_bytes() == b'existing'
    assert (tmp_path / 'golden.npz').read_bytes() == b'artifact'


def test_complete_model_survives_network_error_silently(monkeypatch, tmp_path):
    monkeypatch.setenv('HF_MODEL_REPO', 'test/public-model')
    for name in model_fetch.MODEL_FILES:
        (tmp_path / name).write_bytes(_valid_config() if name == 'config.json' else b'existing')

    def fail_download(**kwargs):
        raise OSError('offline')

    monkeypatch.setattr(model_fetch, 'hf_hub_download', fail_download)
    assert model_fetch.ensure_model(tmp_path) == tmp_path


def test_complete_local_model_does_not_require_repository_setting(monkeypatch, tmp_path):
    monkeypatch.delenv('HF_MODEL_REPO', raising=False)
    monkeypatch.setitem(sys.modules, 'streamlit', SimpleNamespace(secrets={}))
    for name in model_fetch.MODEL_FILES:
        (tmp_path / name).write_bytes(_valid_config() if name == 'config.json' else b'artifact')
    assert model_fetch.ensure_model(tmp_path) == tmp_path


def test_incomplete_model_network_failure_is_clear(monkeypatch, tmp_path):
    monkeypatch.setenv('HF_MODEL_REPO', 'test/public-model')
    monkeypatch.setattr(model_fetch, 'hf_hub_download', lambda **kwargs: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(model_fetch.ModelUnavailable, match=r"Could not fetch 'detector.onnx'.*OSError"):
        model_fetch.ensure_model(tmp_path)


def test_config_requires_calibration(monkeypatch, tmp_path):
    monkeypatch.setenv('HF_MODEL_REPO', 'test/public-model')
    for name in model_fetch.MODEL_FILES:
        (tmp_path / name).write_bytes(b'{}' if name == 'config.json' else b'artifact')
    with pytest.raises(model_fetch.ModelUnavailable, match='calibration'):
        model_fetch.ensure_model(tmp_path)


def test_repository_resolution_requires_explicit_configuration(monkeypatch):
    monkeypatch.setenv('HF_MODEL_REPO', 'owner/model')
    assert model_fetch.resolve_model_repo() == 'owner/model'
    monkeypatch.delenv('HF_MODEL_REPO')
    monkeypatch.setitem(sys.modules, 'streamlit', SimpleNamespace(secrets={}))
    with pytest.raises(model_fetch.ModelUnavailable, match='HF_MODEL_REPO is not configured'):
        model_fetch.resolve_model_repo()


def test_repository_resolution_uses_streamlit_secret(monkeypatch):
    monkeypatch.delenv('HF_MODEL_REPO', raising=False)
    monkeypatch.setitem(sys.modules, 'streamlit', SimpleNamespace(secrets={'HF_MODEL_REPO': 'secret/repo'}))
    assert model_fetch.resolve_model_repo() == 'secret/repo'
