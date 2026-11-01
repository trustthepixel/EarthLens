"""Build map workspace summaries only from current application state."""

from __future__ import annotations

from ui.panel_monitor import _event_id, _seconds_ago, status_counts, visible_events


def _value(value, suffix=""):
    if value is None:
        return "Unavailable"
    return f"{value}{suffix}"


def map_summary(mode: str, session, ctx: dict) -> dict:
    """Return data-backed context for the map's compact workspace card."""
    if mode == "Live monitor":
        events = visible_events(
            session.get("monitor_events", []), session.get("monitor_alert_cutoff", 0)
        )
        counts = status_counts(events)
        latest = max(events, key=_event_id) if events else None
        place = str(latest.get("place") or "unknown") if latest else "No packets yet"
        elapsed = _seconds_ago(latest) if latest else None
        seconds = f"{elapsed} s ago" if elapsed is not None else "Unavailable"
        source = session.get("monitor_source")
        return {
            "mode": mode,
            "title": "Ground station activity",
            "subtitle": "Recorded session" if source == "recorded" else "Local ground station",
            "status": str(latest.get("status", "NOT ANALYZED")).upper() if latest else "NOT ANALYZED",
            "metrics": [
                {"label": "Visible events", "value": str(len(events))},
                {"label": "Latest place", "value": place},
                {"label": "Last packet", "value": seconds},
                {"label": "Trusted / Suspicious / Compromised", "value": f"{counts['TRUSTED']} / {counts['SUSPICIOUS']} / {counts['COMPROMISED']}"},
            ],
            "recorded": source == "recorded",
        }

    result = session.get("area_result")
    meta = session.get("area_meta") or {}
    evidence = (result or {}).get("evidence") or {}
    point = session.get("area_point")
    if meta:
        subtitle = " | ".join(str(part) for part in (meta.get("scene"), meta.get("date")) if part)
    elif point:
        subtitle = f"Selected area: {float(point['lat']):.5f}, {float(point['lon']):.5f}"
    else:
        subtitle = "Select an area on the map to begin."
    source = session.get("area_last_source")
    if source == "prepared":
        source_text = "Prepared scene"
    elif source == "live":
        source_text = "Copernicus acquisition"
    else:
        source_text = str(session.get("area_data_source") or "No source selected")
    return {
        "mode": mode,
        "title": "Trust engine" if result else "Analysis workspace",
        "subtitle": subtitle,
        "status": str(result.get("status", "NOT ANALYZED")).upper() if result else "NOT ANALYZED",
        "metrics": [
            {"label": "Score", "value": _value(evidence.get("score"))},
            {"label": "Trust index", "value": _value(evidence.get("trust"))},
            {"label": "Model latency", "value": _value(evidence.get("latency_ms"), " ms")},
            {"label": "Image source", "value": source_text},
        ],
        "recorded": False,
    }
