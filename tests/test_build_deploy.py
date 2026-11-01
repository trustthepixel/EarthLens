"""Test key deployment-preflight rules independently from the Git checkout."""

from scripts.build_deploy import _protected_tracked_paths, _requirement_issues


def test_portable_pinned_runtime_requirements():
    valid = 'streamlit==1.66.1\nonnxruntime==1.31.1\n'
    assert _requirement_issues(valid) == []
    issues = _requirement_issues('torch==2.0\npywin32==1.0\nrequests\n')
    assert len(issues) == 3


def test_protected_tracked_paths_are_reported_without_echoing_names():
    issues = _protected_tracked_paths(['model/detector.onnx', 'keys/private.pem', '.env', 'app.py'])
    assert issues == ['tracked model artifact', 'tracked key artifact', 'tracked environment file']
