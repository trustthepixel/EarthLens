"""Persistent map and mode state for Streamlit reruns."""

from __future__ import annotations


MODE_OPTIONS = ("Analyze area", "Live monitor")
DEFAULTS = {
    "workspace_page": "Mission Control",
    "dashboard_mode": "Analyze area",
    "map_center": {"lat": 34.0, "lng": 9.5},
    "map_zoom": 6,
    "basemap_override": "Auto",
    "area_point": None,
    "area_packet": None,
    "area_cloud": None,
    "area_result": None,
    "area_chip": None,
    "area_meta": None,
    "area_validation": None,
    "area_overlays": {},
    "area_show_rgb": True,
    "area_show_ndvi": False,
    "area_show_heatmap": False,
    "area_opacity": 0.65,
    "area_prepared_place": None,
    "area_truth": None,
    "area_attack_details": None,
    "area_original_chip": None,
    "area_original_meta": None,
    "area_original_result": None,
    "area_original_overlays": {},
    "area_original_path": None,
    "monitor_map_center": {"lat": 34.0, "lng": 9.5},
    "monitor_map_zoom": 6,
    "monitor_selected_place": None,
    "monitor_selected_event": None,
    "monitor_events": [],
    "monitor_event_cursor": 0,
    "monitor_alert_cutoff": 0,
    "monitor_api_connected": False,
    "monitor_recorded_index": -1,
    "monitor_source": "unknown",
    "monitor_opacity": 0.65,
    "monitor_auto_refresh": True,
}


def initialize(session_state) -> None:
    for key, value in DEFAULTS.items():
        if key not in session_state:
            session_state[key] = value.copy() if isinstance(value, dict) else value
    if session_state.get("dashboard_mode") not in MODE_OPTIONS:
        session_state["dashboard_mode"] = MODE_OPTIONS[0]


def mode_switch(streamlit) -> str:
    if hasattr(streamlit, "segmented_control"):
        selected = streamlit.segmented_control(
            "Mode",
            options=MODE_OPTIONS,
            key="dashboard_mode",
            label_visibility="collapsed",
        )
    else:
        selected = streamlit.radio(
            "Mode",
            options=MODE_OPTIONS,
            horizontal=True,
            key="dashboard_mode",
            label_visibility="collapsed",
        )
    return selected or MODE_OPTIONS[0]


def update_map_view(session_state, returned: dict | None) -> None:
    if not isinstance(returned, dict):
        return
    center = returned.get("center")
    if isinstance(center, dict):
        try:
            lat, lon = float(center["lat"]), float(center.get("lng", center.get("lon")))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                session_state["map_center"] = {"lat": lat, "lng": lon}
        except (KeyError, TypeError, ValueError):
            pass
    zoom = returned.get("zoom")
    if isinstance(zoom, (int, float)) and not isinstance(zoom, bool) and 1 <= zoom <= 19:
        session_state["map_zoom"] = int(round(zoom))


def update_area_click(session_state, point: dict | None) -> bool:
    if not isinstance(point, dict):
        return False
    try:
        lat = float(point.get("lat"))
        lon = float(point.get("lng", point.get("lon")))
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    current = session_state.get("area_point")
    if isinstance(current, dict) and abs(current["lat"] - lat) < 1e-6 and abs(current["lon"] - lon) < 1e-6:
        return False
    session_state["area_point"] = {"lat": lat, "lon": lon}
    session_state["area_result"] = None
    session_state["area_packet"] = None
    session_state["area_cloud"] = None
    session_state["area_chip"] = None
    session_state["area_meta"] = None
    session_state["area_validation"] = None
    session_state["area_overlays"] = {}
    session_state["area_prepared_place"] = None
    session_state["area_truth"] = None
    session_state["area_attack_details"] = None
    session_state["area_original_chip"] = None
    session_state["area_original_meta"] = None
    session_state["area_original_result"] = None
    session_state["area_original_overlays"] = {}
    session_state["area_original_path"] = None
    return True
