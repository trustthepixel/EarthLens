"""Runtime endpoint configuration tests."""

from types import SimpleNamespace

from tp import settings


def test_api_endpoint_uses_configured_health_url(monkeypatch):
    monkeypatch.setenv('TP_API_URL', 'https://ground.example/service/health?discard=1')
    assert settings.api_endpoint('ingest_v2') == 'https://ground.example/service/ingest_v2'


def test_api_endpoint_is_unset_without_configuration(monkeypatch):
    monkeypatch.delenv('TP_API_URL', raising=False)
    monkeypatch.setitem(__import__('sys').modules, 'streamlit', SimpleNamespace(secrets={}))
    assert settings.api_health_url() == ''
    assert settings.api_endpoint('ingest') == ''


def test_streamlit_secret_supplies_api_endpoint(monkeypatch):
    monkeypatch.delenv('TP_API_URL', raising=False)
    monkeypatch.setitem(
        __import__('sys').modules,
        'streamlit',
        SimpleNamespace(secrets={'TP_API_URL': 'https://ground.example/health'}),
    )
    assert settings.api_endpoint('events') == 'https://ground.example/events'


def test_source_private_key_loads_configured_secret(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode('utf-8')
    monkeypatch.setenv('TP_SOURCE_PRIVATE_KEY', pem)
    assert settings.source_private_key().public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    ) == key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
