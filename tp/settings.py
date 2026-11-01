"""Resolve runtime settings from environment variables or Streamlit secrets."""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def get_setting(name: str, default: str = "") -> str:
    """Read a non-secret or secret setting without embedding deployment values."""
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        import streamlit as st

        value = str(st.secrets.get(name, "")).strip()
    except Exception:
        value = ""
    return value or default


def api_health_url() -> str:
    """Return the configured backend health URL, or an empty string if unset."""
    return get_setting("TP_API_URL")


def api_endpoint(path: str) -> str:
    """Build a backend endpoint from the configured health URL."""
    health_url = api_health_url()
    if not health_url:
        return ""
    parsed = urlparse(health_url)
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/health"):
        base_path = base_path[:-len("/health")]
    endpoint_path = "/" + path.lstrip("/")
    return urlunparse(parsed._replace(path=base_path + endpoint_path, params="", query="", fragment=""))


def source_private_key() -> Ed25519PrivateKey | None:
    """Load the optional source signing key from deployment secret configuration."""
    configured = get_setting("TP_SOURCE_PRIVATE_KEY")
    if not configured:
        return None
    try:
        key = serialization.load_pem_private_key(configured.replace("\\n", "\n").encode("utf-8"), password=None)
    except (TypeError, ValueError) as exc:
        raise ValueError("TP_SOURCE_PRIVATE_KEY must contain a valid Ed25519 private key.") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("TP_SOURCE_PRIVATE_KEY must contain an Ed25519 private key.")
    return key

