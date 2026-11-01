"""Tests for the unified Streamlit workspace navigation."""

import streamlit as st

from ui import navigation


def test_navigation_contains_all_integrated_workspace_destinations():
    pages = [page for _section, items in navigation.NAVIGATION for page in items]
    assert pages == [
        "Mission Control",
        "Analyze area",
        "Copernicus Acquisition",
        "Live demo",
        "Geospatial Map",
        "Image processing",
        "Attack Lab",
        "Forensics & verification",
        "Verification",
        "Audit Logs",
        "Model Evaluation",
        "System details",
        "Copernicus configuration",
    ]


def test_navigation_sets_matching_analysis_modes(monkeypatch):
    session = {"workspace_page": "Mission Control", "dashboard_mode": "Analyze area"}
    monkeypatch.setattr(st, "session_state", session)
    navigation._select_page("Live demo")
    assert session == {"workspace_page": "Live demo", "dashboard_mode": "Live monitor"}
