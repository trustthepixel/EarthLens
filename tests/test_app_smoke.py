"""AppTest coverage for the unified workspace and persistent map shell."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import map_view


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _use_unavailable_backend(monkeypatch):
    monkeypatch.setenv("TP_API_URL", "http://127.0.0.1:1/health")


def test_app_starts_with_one_map_two_modes_and_signature_notice(monkeypatch):
    _use_unavailable_backend(monkeypatch)
    monkeypatch.setattr(map_view, "probe_basemap", lambda: map_view.NO_TILES)
    import streamlit_folium

    rendered_maps = []
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda map_object, **kwargs: rendered_maps.append((map_object, kwargs)) or {})
    app = AppTest.from_file(str(APP_PATH), default_timeout=90).run()

    assert not app.exception, app.exception
    controls = app.get("segmented_control")
    assert len(controls) == 1
    assert list(controls[0].options) == ["Analyze area", "Live monitor"]

    visible_text = "\n".join(element.value for element in app.markdown)
    assert "Signature simulated at the source: Sentinel-2 is not signed by Copernicus." in visible_text

    assert len(rendered_maps) == 1
    assert rendered_maps[0][1]["key"] == "trust_pixel_main_map"
    map_html = rendered_maps[0][0].get_root().render()
    assert 'Analysis workspace' in map_html
    assert 'Select an area on the map to begin.' in map_html

    source = APP_PATH.read_text(encoding="utf-8")
    assert "st.navigation" not in source
    assert "st.Page" not in source
    assert "dashboard_pages" not in source
    assert not (ROOT / "dashboard_pages").exists()


def test_both_modes_render_and_buttons_are_labeled(monkeypatch):
    _use_unavailable_backend(monkeypatch)
    monkeypatch.setattr(map_view, "probe_basemap", lambda: map_view.NO_TILES)
    import streamlit_folium
    monkeypatch.setattr(streamlit_folium, "st_folium", lambda map_object, **kwargs: {})
    app = AppTest.from_file(str(APP_PATH), default_timeout=90).run()
    assert not app.exception, app.exception
    assert all(button.label.strip() for button in app.button)
    app.segmented_control[0].set_value("Live monitor").run()
    assert not app.exception, app.exception
    rendered = "\n".join(item.value for item in app.warning)
    assert "Ground-station API is unavailable" in rendered or any(
        "API connected" in item.value for item in app.success
    )
    assert all(button.label.strip() for button in app.button)


def test_sidebar_exposes_all_integrated_workspaces():
    from ui.navigation import NAVIGATION

    pages = [page for _section, items in NAVIGATION for page in items]
    assert pages == [
        "Mission Control",
        "Analyze area",
        "Live demo",
        "Geospatial map",
        "Image processing",
        "Attack Lab",
        "Forensics & verification",
        "Audit logs",
        "Model Evaluation",
        "System details",
    ]


def test_configured_backend_is_the_only_model_runtime(monkeypatch):
    import app as dashboard

    calls = []
    local = {
        "pipeline": None,
        "source": object(),
        "selftest_result": None,
        "model_errors": [],
        "local_model_ok": False,
        "api_source_configured": True,
        "source_error": None,
        "source_key_id": "trusted-source",
    }
    monkeypatch.setattr(dashboard, "api_health_url", lambda: "https://api.example/health")
    monkeypatch.setattr(
        dashboard,
        "_local_startup_context",
        lambda load_model: calls.append(load_model) or local,
    )
    monkeypatch.setattr(
        dashboard,
        "_backend_health",
        lambda url: {"ok": True, "trusted_key_ids": ["trusted-source"]},
    )
    monkeypatch.setattr(dashboard, "_active_basemap", lambda: map_view.NO_TILES)

    context = dashboard._startup_context()

    assert calls == [False]
    assert context["api_connected"] is True
    assert context["model_ok"] is True
    assert context["analysis_available"] is True
