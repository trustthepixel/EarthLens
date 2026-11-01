"""Render inherited verification reasons without altering their wording."""

from __future__ import annotations


def render_legacy_reasons(streamlit, reasons):
    """Display verifier reasons exactly as returned by the legacy verifier."""
    for reason in reasons:
        streamlit.warning(str(reason))  # lang-ok: preserve legacy verification reasons verbatim.
