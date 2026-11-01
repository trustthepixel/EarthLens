"""Single-page map dashboard entry point."""

from __future__ import annotations

import json
from pathlib import Path

import requests
import streamlit as st
from streamlit_folium import st_folium
import time

from tp.engine import TrustPipeline
from tp.model_fetch import ensure_model
from tp.selftest import run_selftest
from tp.chain import ChainedSource
from tp.settings import api_health_url, get_setting, source_private_key
from tp.pack import list_places, load_pack
from ui import map_view, navigation, panel_analyze, panel_kernel_analysis, panel_monitor, state, status, theme, workspace


st.set_page_config(
    page_title="earthLens",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _local_startup_context(load_model: bool = True) -> dict:
    errors: list[str] = []
    pipeline = None
    source_key = None
    source_error = None
    try:
        source_key = source_private_key()
    except ValueError as exc:
        source_error = str(exc)
    source = ChainedSource(sk=source_key)
    if source_key is not None:
        source.counter = time.time_ns()
        source.head = None
    selftest_result = None
    if load_model:
        try:
            with st.spinner("Downloading the model from Hugging Face"):
                ensure_model()
            pipeline = TrustPipeline(source=source)
            selftest_result = run_selftest()
            if not selftest_result.get("ok"):
                errors.append(str(selftest_result.get("error", "The model self-test failed.")))
        except Exception:
            errors.append(
                "The ONNX model could not be loaded. Check that its files and configuration are available; "
                "if download failed, check network access and HF_MODEL_REPO."
            )

    return {
        "pipeline": pipeline,
        "source": source,
        "selftest_result": selftest_result,
        "model_errors": errors,
        "local_model_ok": pipeline is not None and not errors,
        "api_source_configured": source_key is not None and source_error is None,
        "source_error": source_error,
        "source_key_id": source.key_id,
    }


@st.cache_data(ttl=5, show_spinner=False)
def _backend_health(api_url: str) -> dict:
    if not api_url:
        return {"ok": False, "trusted_key_ids": []}
    try:
        response = requests.get(api_url, timeout=3.0)
        body = response.json() if response.status_code == 200 else {}
        return {
            "ok": response.status_code == 200 and bool(body.get("ok")),
            "trusted_key_ids": body.get("trusted_key_ids", []),
        }
    except (requests.RequestException, ValueError, AttributeError):
        return {"ok": False, "trusted_key_ids": []}


@st.cache_data(ttl=60, show_spinner=False)
def _active_basemap():
    return map_view.probe_basemap()


def _startup_context() -> dict:
    api_url = api_health_url()
    # A configured backend owns model download and inference; do not load another
    # ONNX copy in the Streamlit process. Local inference is the no-API path.
    local = _local_startup_context(load_model=not bool(api_url))
    health = _backend_health(api_url)
    api_connected = health["ok"]
    local_model_ok = local["local_model_ok"]
    model_ok = api_connected if api_url else local_model_ok
    api_source_configured = local["api_source_configured"]
    api_source_trusted = local["source_key_id"] in health["trusted_key_ids"]
    analysis_available = (
        api_connected and api_source_configured and api_source_trusted if api_url else local_model_ok
    )
    errors = list(local["model_errors"])
    if api_url and api_connected and not api_source_configured:
        errors.append(local.get("source_error") or "TP_SOURCE_PRIVATE_KEY is not configured for backend packet verification.")
    elif api_url and api_connected and not api_source_trusted:
        errors.append("The backend does not trust the configured source key. Provision its matching public key.")
    if api_url and not api_connected:
        errors.append("Configured backend API is unavailable. Check TP_API_URL and the backend health endpoint.")

    return {
        "pipeline": local["pipeline"],
        "source": local["source"],
        "selftest_result": local["selftest_result"],
        "model_ok": model_ok,
        "analysis_available": analysis_available,
        "model_errors": errors,
        "active_basemap": _active_basemap(),
        "internet_ok": _active_basemap() != map_view.NO_TILES,
        "api_connected": api_connected,
        "api_configured": bool(api_url),
        "api_source_configured": api_source_configured,
        "api_source_trusted": api_source_trusted,
        "pack_available": (Path(__file__).resolve().parent / "unseen_pack" / "index.json").is_file(),
    }


@st.cache_resource(show_spinner=False)
def _offline_pack_entries() -> list[dict]:
    return load_pack()


@st.cache_resource(show_spinner=False)
def _offline_pack_places() -> list[dict]:
    return list_places()


state.initialize(st.session_state)
ctx = _startup_context()
try:
    ctx["pack_entries"] = _offline_pack_entries()
    ctx["prepared_places"] = _offline_pack_places()
except Exception:
    ctx["pack_entries"] = []
    ctx["prepared_places"] = []
    ctx["pack_available"] = False

theme.inject_theme(st)
model_text = "Model OK" if ctx["model_ok"] else "Model unavailable"
internet_text = "Internet OK" if ctx["internet_ok"] else "Internet offline"
api_text = "API connected" if ctx["api_connected"] else "API unavailable" if ctx["api_configured"] else "API not configured"
workspace_page = navigation.render(model_text=model_text, internet_text=internet_text, api_text=api_text)

page_descriptions = {
    "Mission Control": "Deterministic provenance and machine vision working together to verify every pixel in transit.",
    "Analyze area": "Select an area and inspect a fixed 256 × 256 Sentinel-2 chip at 10 m resolution.",
    "Copernicus Acquisition": "Monitor incoming Sentinel-2 scenes, cloud cover, and acquisition health before analysis.",
    "Live demo": "Review signed observations received by the configured ground-station API.",
    "Geospatial Map": "Explore the selected analysis location, prepared scenes, and current image layers.",
    "Image processing": "Inspect the true-colour composite, NDVI, model score, and forgery heatmap.",
    "Attack Lab": "Apply controlled tampering to an analyzed chip and observe the verification evidence.",
    "Forensics & verification": "Review source provenance, pixel integrity, replay, hash-chain, and model evidence.",
    "Verification": "Inspect the latest packet decision and the evidence supporting its trust status.",
    "Audit Logs": "Inspect live backend events or clearly labeled recorded events when the service is unavailable.",
    "Model Evaluation": "Review model readiness and measured evidence from the latest processed observation.",
    "System details": "Check service health and runtime configuration without exposing private keys.",
    "Copernicus configuration": "Choose the live or prepared data source and acquisition for the selected area.",
}
workspace_page = workspace_page if workspace_page in page_descriptions else "Mission Control"
selected_mode = st.session_state.get("dashboard_mode", "Analyze area")
if workspace_page == "Mission Control":
    selected_mode = selected_mode if selected_mode in state.MODE_OPTIONS else state.MODE_OPTIONS[0]
elif workspace_page == "Live demo":
    selected_mode = "Live monitor"
else:
    selected_mode = "Analyze area"

ground_status = "GROUND STATION ONLINE" if ctx["api_connected"] else (
    "GROUND STATION OFFLINE" if ctx["api_configured"] else "GROUND STATION NOT CONFIGURED"
)
alerts = [
    event for event in st.session_state.get("monitor_events", [])
    if str(event.get("status", "")).upper() in {"SUSPICIOUS", "COMPROMISED"}
]
with st.container(key="tp-topbar"):
    top_left, top_right = st.columns([1.7, 1.0], vertical_alignment="center")
    with top_left:
        st.markdown(
            '<div class="tp-topbar-crumb">earthLens <span>›</span> WORKSPACE</div>'
            f'<div class="tp-topbar-title">{workspace_page}</div>',
            unsafe_allow_html=True,
        )
    with top_right:
        st.markdown(
            '<div class="tp-topbar-right">'
            f'<span class="tp-ground-status"><i class="{("online" if ctx["api_connected"] else "offline")}"></i>{ground_status}</span>'
            f'<span class="tp-topbar-alert">Alerts <b>{len(alerts)}</b></span>'
            '<span class="tp-topbar-avatar">TP</span>'
            '</div>',
            unsafe_allow_html=True,
        )

section_name = "Integrity analysis" if workspace_page in {
    "Image processing", "Attack Lab", "Forensics & verification", "Verification", "Audit Logs", "Model Evaluation"
} else "System" if workspace_page in {"System details", "Copernicus configuration"} else "Operations"
section_eyebrow = f"{section_name.upper()} / {('INGESTION' if workspace_page == 'Copernicus Acquisition' else workspace_page.upper())}"
st.markdown(
    '<div class="tp-workspace-header">'
    f'<div class="tp-workspace-eyebrow">{section_eyebrow}</div>'
    f'<h1 class="tp-workspace-title">{workspace_page}</h1>'
    f'<div class="tp-workspace-description">{page_descriptions[workspace_page]}</div>'
    '</div>',
    unsafe_allow_html=True,
)

show_map = workspace_page in {"Mission Control", "Analyze area", "Copernicus Acquisition", "Live demo", "Geospatial Map", "Copernicus configuration"}
map_result = None
active_basemap = ctx["active_basemap"]
monitor_mode = workspace_page == "Live demo" or (workspace_page == "Mission Control" and selected_mode == "Live monitor")

if show_map:
    left_panel, map_panel = st.columns([0.42, 0.58], gap="small", vertical_alignment="top")
    with left_panel:
        with st.container(border=True, key="tp-workspace-controls"):
            if workspace_page == "Mission Control":
                selected_mode = state.mode_switch(st)
                monitor_mode = selected_mode == "Live monitor"
                if selected_mode == "Analyze area":
                    panel_analyze.render(ctx)
                    panel_kernel_analysis.render()
                else:
                    panel_monitor.render(ctx)
            elif workspace_page in {"Analyze area", "Copernicus Acquisition", "Copernicus configuration"}:
                panel_analyze.render(ctx)
                if workspace_page == "Copernicus configuration":
                    st.caption("Changes apply to the existing Analyze area workflow.")
            elif workspace_page == "Live demo":
                panel_monitor.render(ctx)
            else:
                point = st.session_state.get("area_point")
                if point:
                    st.caption(f"Selected point: {point['lat']:.5f}, {point['lon']:.5f}")
                else:
                    st.info("Click the map to select a location. The input remains fixed at 256 × 256 pixels and 10 m.")
                panel_analyze.render_image_processing()

            if not ctx["model_ok"]:
                details = " ".join(ctx["model_errors"]) or "The model self-test did not pass."
                st.warning(f"Model unavailable: {details}")
            elif ctx["api_configured"] and not ctx["api_source_configured"]:
                st.warning("Set TP_SOURCE_PRIVATE_KEY to a key whose public key is trusted by the backend to analyze through the API.")
            elif ctx["api_configured"] and not ctx["api_source_trusted"]:
                st.warning("The backend does not trust the configured source key. Provision its matching public key before analysis.")

        st.markdown(
            '<div class="tp-signature-note">Signature simulated at the source: '
            'Sentinel-2 is not signed by Copernicus.</div>',
            unsafe_allow_html=True,
        )

    with map_panel:
        with st.container(border=True, key="tp-map-workspace"):
            basemap_options = [map_view.AUTO, *map_view.BASEMAPS, map_view.NO_TILES]
            override = st.selectbox("Basemap", basemap_options, key="basemap_override")
            active_basemap = ctx["active_basemap"] if override == map_view.AUTO else override
            st.caption(f"Basemap · {active_basemap}")

        if monitor_mode:
            latest = st.session_state.get("monitor_place_latest", {})
            monitor_places = [{**place, "status": latest.get(place["place"], {}).get("status")}
                              for place in ctx.get("prepared_places", [])]
            active_center = st.session_state["monitor_map_center"]
            active_zoom = st.session_state["monitor_map_zoom"]
            active_overlays = st.session_state.get("monitor_selected_overlays", {})
        else:
            monitor_places = None
            active_center = st.session_state["map_center"]
            active_zoom = st.session_state["map_zoom"]
            active_overlays = st.session_state.get("area_overlays")

        map_object = map_view.build_map(
            center=active_center,
            zoom=active_zoom,
            basemap=active_basemap,
            point=None if monitor_mode else st.session_state.get("area_point"),
            result=None if monitor_mode else st.session_state.get("area_result"),
            meta=None if monitor_mode else st.session_state.get("area_meta"),
            overlays=active_overlays,
            workspace_summary=workspace.map_summary(selected_mode, st.session_state, ctx),
            opacity=st.session_state.get("monitor_opacity", 0.65) if monitor_mode else st.session_state.get("area_opacity", 0.65),
            prepared_places=None if monitor_mode else ctx.get("prepared_places"),
            monitor_places=monitor_places,
            monitor_selected_place=st.session_state.get("monitor_selected_place") if monitor_mode else None,
            recorded_session=monitor_mode and st.session_state.get("monitor_source") == "recorded",
        )
        with st.container(key="tp-map-component"):
            map_result = st_folium(
                map_object,
                key="trust_pixel_main_map",
                height=900,
                width=None,
                use_container_width=True,
                returned_objects=["center", "zoom", "last_clicked", "last_object_clicked"],
            )
else:
    with st.container(key="tp-full-workspace"):
        if workspace_page == "Image processing":
            panel_analyze.render_image_processing()
            panel_kernel_analysis.render()
        elif workspace_page == "Attack Lab":
            panel_analyze.render_attack_lab(ctx)
        elif workspace_page in {"Forensics & verification", "Verification"}:
            panel_analyze.render_forensics(api_configured=ctx["api_configured"])
        elif workspace_page == "Audit Logs":
            connected, events = panel_monitor.poll_api(health_url=api_health_url(), since=0)
            if connected:
                st.success("Ground station online. Showing live backend events.")
            else:
                st.warning("The backend is unavailable. Showing a recorded session, if one exists.")
                events = panel_monitor.load_recorded_events()
            if events:
                audit_rows = [{key: event.get(key) for key in (
                    "event_id", "time_utc", "status", "place", "scene", "provenance", "integrity", "replay", "chain"
                )} for event in events]
                st.dataframe(audit_rows, hide_index=True, use_container_width=True)
                st.download_button(
                    "Download visible audit events",
                    data=json.dumps(audit_rows, ensure_ascii=True, indent=2),
                    file_name="trust_the_pixel_audit_events.json",
                    mime="application/json",
                )
            else:
                st.info("No audit events are available yet.")
        elif workspace_page == "Model Evaluation":
            if ctx.get("api_configured"):
                st.success("The configured backend health check reports its ONNX pipeline ready." if ctx["api_connected"] else "The configured backend is unavailable; no backend inference result can be produced.")
            elif ctx.get("selftest_result") and ctx["selftest_result"].get("ok"):
                report = ctx["selftest_result"]
                score_col, prob_col, latency_col = st.columns(3)
                score_col.metric("Max score difference", f"{report['max_abs_diff']:.5f}")
                prob_col.metric("Max probability difference", f"{report['max_prob_diff']:.5f}")
                latency_col.metric("Mean latency", f"{report['ms_mean']:.1f} ms")
            else:
                st.warning("Model evaluation is unavailable until the configured model runtime passes its readiness check.")
            result = st.session_state.get("area_result") or {}
            evidence = result.get("evidence") or {}
            if evidence:
                st.metric("Model score", evidence.get("score", "Unavailable"))
                st.metric("Trust index", evidence.get("trust", "Unavailable"))
                st.caption(f"Status: {result.get('status', 'Unavailable')} · Latency: {evidence.get('latency_ms', 'Unavailable')} ms")
        elif workspace_page == "System details":
            st.markdown('<div class="tp-section-label">Platform status</div>', unsafe_allow_html=True)
            service_col, model_col, data_col = st.columns(3)
            service_col.metric("Backend API", "Connected" if ctx["api_connected"] else "Unavailable" if ctx["api_configured"] else "Not configured")
            model_col.metric("Model runtime", "Ready" if ctx["model_ok"] else "Unavailable")
            data_col.metric("Offline pack", "Ready" if ctx["pack_available"] else "Unavailable")
            st.markdown('<div class="tp-section-label">Configured services</div>', unsafe_allow_html=True)
            st.write(f"Hugging Face repository configured: {'Yes' if get_setting('HF_MODEL_REPO') else 'No'}")
            st.write(f"Source signing key configured: {'Yes' if ctx['api_source_configured'] else 'No'}")
            st.write(f"Source key trusted by backend: {'Yes' if ctx['api_source_trusted'] else 'No'}")
            if not ctx["api_configured"]:
                st.info("To connect this dashboard, configure TP_API_URL with the reachable backend /health URL and TP_SOURCE_PRIVATE_KEY in the same PowerShell window used to start Streamlit, then restart Streamlit.")
            elif not ctx["api_connected"]:
                st.warning("The backend URL is configured, but its health response is not ready. Confirm the API is running and that /health reports ok: true.")
            elif not ctx["api_source_configured"]:
                st.info("The API is online. Configure TP_SOURCE_PRIVATE_KEY in the Streamlit process to submit signed area-analysis packets.")
            elif not ctx["api_source_trusted"]:
                st.info("The source key is configured but not trusted by the backend. Provision its matching public key in the backend trusted-key directory.")
            if ctx.get("model_errors"):
                st.warning(" ".join(ctx["model_errors"]))
            st.caption("Private keys and credentials are never displayed in this workspace.")

    st.markdown(
        '<div class="tp-signature-note">Signature simulated at the source: '
        'Sentinel-2 is not signed by Copernicus.</div>',
        unsafe_allow_html=True,
    )
clicked = (map_result or {}).get("last_object_clicked") or (map_result or {}).get("last_clicked")
if monitor_mode:
    old_map_center = dict(st.session_state["monitor_map_center"])
    old_map_zoom = st.session_state["monitor_map_zoom"]
    if isinstance(map_result, dict):
        center = map_result.get("center")
        if isinstance(center, dict):
            try:
                lat = float(center["lat"])
                lon = float(center.get("lng", center.get("lon")))
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    st.session_state["monitor_map_center"] = {"lat": lat, "lng": lon}
            except (KeyError, TypeError, ValueError):
                pass
        zoom = map_result.get("zoom")
        if isinstance(zoom, (int, float)) and not isinstance(zoom, bool) and 1 <= zoom <= 19:
            st.session_state["monitor_map_zoom"] = int(round(zoom))
    view_changed = (st.session_state["monitor_map_center"] != old_map_center
                    or st.session_state["monitor_map_zoom"] != old_map_zoom)
    place_changed = False
    if clicked:
        try:
            click_lon = float(clicked.get("lng", clicked.get("lon")))
            click_lat = float(clicked.get("lat"))
            from tp.pack import _distance_km
            candidates = [(_distance_km(click_lon, click_lat, *place["center"]), place)
                          for place in monitor_places]
            if candidates:
                distance, place = min(candidates, key=lambda item: item[0])
                if distance <= 4.0:
                    event = st.session_state.get("monitor_place_latest", {}).get(place["place"])
                    event_id = int(event["event_id"]) if event else None
                    lon, lat = place["center"]
                    target_center = {"lat": float(lat), "lng": float(lon)}
                    place_changed = (
                        st.session_state.get("monitor_selected_place") != place["place"]
                        or st.session_state.get("monitor_selected_event") != event_id
                        or st.session_state["monitor_map_center"] != target_center
                        or st.session_state["monitor_map_zoom"] != 13
                    )
                    st.session_state["monitor_selected_place"] = place["place"]
                    st.session_state["monitor_selected_event"] = event_id
                    st.session_state["monitor_map_center"] = target_center
                    st.session_state["monitor_map_zoom"] = 13
        except (TypeError, ValueError, KeyError):
            pass
    if view_changed or place_changed:
        st.rerun()
else:
    old_map_center = dict(st.session_state["map_center"])
    old_map_zoom = st.session_state["map_zoom"]
    state.update_map_view(st.session_state, map_result)
    view_changed = (st.session_state["map_center"] != old_map_center
                    or st.session_state["map_zoom"] != old_map_zoom)
    point_changed = False
    old_prepared_place = st.session_state.get("area_prepared_place")
    if clicked and st.session_state.get("area_data_source") == "Prepared unseen data (offline)":
        try:
            click_lon = float(clicked.get("lng", clicked.get("lon")))
            click_lat = float(clicked.get("lat"))
            candidates = []
            for place in ctx.get("prepared_places", []):
                lon, lat = place["center"]
                from math import asin, cos, radians, sin, sqrt
                p1, p2 = radians(click_lat), radians(float(lat))
                value = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(float(lon) - click_lon) / 2) ** 2
                candidates.append((6371.0088 * 2 * asin(min(1.0, sqrt(value))), place))
            if candidates and min(candidates, key=lambda item: item[0])[0] <= 30.0:
                place = min(candidates, key=lambda item: item[0])[1]
                center_lon, center_lat = place["center"]
                point_changed = state.update_area_click(st.session_state, {"lat": center_lat, "lng": center_lon})
                st.session_state["area_prepared_place"] = place["place"]
            else:
                st.session_state["area_prepared_place"] = None
                point_changed = state.update_area_click(st.session_state, clicked)
        except (TypeError, ValueError, KeyError):
            point_changed = state.update_area_click(st.session_state, clicked)
    else:
        point_changed = state.update_area_click(st.session_state, clicked)
    if point_changed or view_changed or old_prepared_place != st.session_state.get("area_prepared_place"):
        st.rerun()
