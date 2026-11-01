"""Live event polling, alert controls, and event details."""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlparse

import requests
import streamlit as st

from tp.sentinel_live import preview_footprint
from ui.status import STATUS_COLORS, status_badge
from ui.language import render_legacy_reasons
from tp.settings import api_health_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_SESSION_PATH = PROJECT_ROOT / 'demo_session' / 'events.json'


def _project_path(path):
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(PROJECT_ROOT)
        return resolved
    except (OSError, ValueError):
        return None


EVENTS_DATA_DIR = _project_path(os.environ.get('TP_EVENTS_DATA_DIR', 'events_data')) or PROJECT_ROOT / 'events_data'
STATUS_KEYS = ('TRUSTED', 'SUSPICIOUS', 'COMPROMISED')


def latest_by_place(events):
    """Reduce event history to the highest event_id for each place."""
    latest = {}
    for event in sorted(events, key=lambda row: _event_id(row), reverse=True):
        place = str(event.get('place') or 'unknown')
        latest.setdefault(place, event)
    return latest


def _event_id(event):
    try:
        return int(event.get('event_id', event.get('seq', 0)))
    except (TypeError, ValueError, AttributeError):
        return 0


def _validated_event_id(event):
    value = event.get('event_id') if isinstance(event, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,11}', value):
        return int(value)
    return None


def visible_events(events, cutoff=0):
    return [event for event in events if _event_id(event) >= int(cutoff)]


def status_counts(events):
    counts = {status: 0 for status in STATUS_KEYS}
    for event in events:
        status = str(event.get('status', '')).upper()
        if status in counts:
            counts[status] += 1
    return counts


def load_recorded_events(path=DEMO_SESSION_PATH):
    safe_path = _project_path(path)
    if safe_path is None:
        return []
    try:
        value = json.loads(safe_path.read_text(encoding='utf-8'))
        events = value.get('events', []) if isinstance(value, dict) else value
        return [row for row in events if isinstance(row, dict)] if isinstance(events, list) else []
    except (OSError, ValueError, TypeError):
        return []


def _health_url():
    return api_health_url()


def _events_url(health_url):
    parsed = urlparse(health_url)
    if parsed.path.rstrip('/').endswith('/health'):
        path = parsed.path.rstrip('/')[:-len('/health')] + '/events'
    else:
        path = parsed.path.rstrip('/') + '/events'
    return parsed._replace(path=path or '/events').geturl()


def poll_api(get=None, health_url=None, since=0):
    """Return a health result and new events, using a one-second timeout."""
    get = get or requests.get
    url = health_url or _health_url()
    try:
        health = get(url, timeout=1.0)
        if health.status_code != 200 or not health.json().get('ok', True):
            return False, []
        response = get(_events_url(url), params={'since': int(since), 'limit': 1000}, timeout=1.0)
        response.raise_for_status()
        rows = response.json().get('events', [])
        return True, [row for row in rows if isinstance(row, dict)]
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return False, []


def _is_cloud():
    return os.environ.get('TP_RECORDED_ONLY') == '1'


def _local_api(url):
    return urlparse(url).hostname in {'127.0.0.1', 'localhost', '::1'}


def _time_text(event):
    value = event.get('time_utc', event.get('time', ''))
    return str(value).replace('T', ' ').replace('+00:00', ' UTC')


def _seconds_ago(event):
    value = event.get('time_utc', event.get('time'))
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()))
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=600, max_entries=32, show_spinner=False)
def _cached_png_uri(path_text, file_size, modified_ns):
    try:
        data = base64.b64encode(Path(path_text).read_bytes()).decode('ascii')
    except OSError:
        return None
    return f'data:image/png;base64,{data}'


def _image_uri(directory, event_id, suffix):
    if not isinstance(event_id, int) or isinstance(event_id, bool) or event_id < 1:
        return None
    if suffix not in {'rgb', 'heat'}:
        return None
    root = _project_path(directory)
    if root is None:
        return None
    path = _project_path(root / f'{event_id}_{suffix}.png')
    if path is None:
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    return _cached_png_uri(str(path), stat.st_size, stat.st_mtime_ns)


def event_overlays(event, recorded=False):
    event_id = _validated_event_id(event)
    if event_id is None:
        return {}
    directory = DEMO_SESSION_PATH.parent if recorded else EVENTS_DATA_DIR
    try:
        lon, lat = float(event['lon']), float(event['lat'])
        corners = preview_footprint(lon, lat)
        bounds = [[min(point[1] for point in corners), min(point[0] for point in corners)],
                  [max(point[1] for point in corners), max(point[0] for point in corners)]]
    except (KeyError, TypeError, ValueError):
        bounds = None
    output = {}
    rgb = _image_uri(directory, event_id, 'rgb')
    if rgb and bounds:
        output['True colour'] = {'image': rgb, 'bounds': bounds, 'show': True}
    heat = _image_uri(directory, event_id, 'heat')
    if heat and bounds and str(event.get('status', '')).upper() != 'TRUSTED':
        output['Forgery heatmap'] = {'image': heat, 'bounds': bounds, 'show': True}
    return output


def _render_detail(event):
    st.markdown(status_badge(event.get('status', 'UNKNOWN'), small=True), unsafe_allow_html=True)
    st.markdown(f"**{event.get('place', 'unknown')}** | {event.get('scene') or 'Unknown scene'} | {_time_text(event)}")
    st.caption(f"Date: {event.get('date') or 'Unknown'}")
    score, low, high = event.get('score'), event.get('t_low'), event.get('t_high')
    st.caption(f"Score: {score if score is not None else 'N/A'} vs thresholds {low if low is not None else 'N/A'} / {high if high is not None else 'N/A'}")
    st.caption(f"Trust index: {event.get('trust', 'N/A')}")
    st.caption(f"Provenance: {event.get('provenance', 'UNKNOWN')} | Integrity: {event.get('integrity', 'UNVERIFIED')} | Replay: {event.get('replay', False)} | Plausibility: {event.get('plausible', 'Unknown')}")
    st.caption(f"Hash chain: {event.get('chain', 'N/A')} | Copy-move matches: {event.get('copy_move_matches', 'N/A')}")
    reasons = event.get('reasons') or []
    if reasons:
        st.markdown('**Reasons**')
        render_legacy_reasons(st, reasons)
    st.caption(f"Changed tiles: {len(event.get('changed_tiles') or [])}")
    st.caption(f"Scenario label (not evidence): {event.get('assumed_mode', 'unknown')}")
    if str(event.get('status')).upper() == 'COMPROMISED' and event.get('integrity') == 'FAIL':
        st.error('Pixels differ from what the source signed')
    if event.get('provenance') == 'VALID' and score is not None and low is not None and float(score) >= float(low):
        st.warning('CONFLICT: the source signature is valid, but image content is suspicious.')
    st.download_button('Download event (JSON)', json.dumps(event, ensure_ascii=True, indent=2),
                       file_name=f"event_{_event_id(event)}.json", mime='application/json',
                       key=f"monitor_download_{_event_id(event)}")


def _render_alerts(events, ctx, auto_refresh):
    session = st.session_state
    cutoff = int(session.get('monitor_alert_cutoff', 0))
    visible = visible_events(events, cutoff)
    latest = latest_by_place(visible)
    session['monitor_place_latest'] = latest
    counts = status_counts(visible)
    st.markdown('<div class="tp-section-label">Live monitor</div>', unsafe_allow_html=True)
    latest_event = max(visible, key=_event_id) if visible else None
    st.markdown(f"**Last packet: {_seconds_ago(latest_event)} s ago**" if latest_event and _seconds_ago(latest_event) is not None else '**Last packet: N/A**')
    cols = st.columns(3)
    for column, status in zip(cols, STATUS_KEYS):
        color = STATUS_COLORS[status]
        column.markdown(f'<div class="tp-monitor-count" style="--count-color:{color}"><b>{counts[status]}</b><span>{status.title()}</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tp-section-label">Active alerts</div>', unsafe_allow_html=True)
    rows = sorted(visible, key=_event_id, reverse=True)[:10]
    if not rows:
        st.caption('No events are available yet.')
    for event in rows:
        cols = st.columns([0.18, 1.3, 1.05, 1.0, 0.75, 0.65], vertical_alignment='center')
        status = str(event.get('status', 'UNKNOWN')).upper()
        color = STATUS_COLORS.get(status, '#8FA1BF')
        cols[0].markdown(f'<span class="tp-legend-dot" style="background:{color}"></span>', unsafe_allow_html=True)
        cols[1].write(str(event.get('place') or 'unknown'))
        cols[2].caption(_time_text(event))
        cols[3].caption(status.title())
        score = event.get('score')
        cols[4].caption(f'{float(score):.2f}' if isinstance(score, (int, float)) else 'N/A')
        if cols[5].button('Zoom', key=f"monitor_zoom_{_event_id(event)}"):
            place = str(event.get('place') or 'unknown')
            session['monitor_selected_place'] = place
            session['monitor_selected_event'] = _event_id(event)
            place_data = next((row for row in ctx.get('prepared_places', []) if row.get('place') == place), None)
            if place_data:
                lon, lat = place_data['center']
            else:
                lon, lat = event.get('lon', 9.5), event.get('lat', 34.0)
            session['monitor_map_center'] = {'lat': float(lat), 'lng': float(lon)}
            session['monitor_map_zoom'] = 13
            st.rerun(scope='app')
    selected = next((event for event in visible if _event_id(event) == session.get('monitor_selected_event')), None)
    if selected is None and session.get('monitor_selected_place'):
        selected = latest.get(session['monitor_selected_place'])
    if selected is None and visible:
        selected = max(visible, key=_event_id)
        session['monitor_selected_event'] = _event_id(selected)
        session['monitor_selected_place'] = str(selected.get('place') or 'unknown')
    if selected:
        st.markdown('<div class="tp-section-label">Selected event</div>', unsafe_allow_html=True)
        _render_detail(selected)
        st.session_state['monitor_selected_overlays'] = event_overlays(selected, session.get('monitor_source') == 'recorded')
        st.slider('Overlay opacity', 0.1, 1.0, key='monitor_opacity')
    else:
        st.session_state['monitor_selected_overlays'] = {}


def render(ctx: dict) -> None:
    session = st.session_state
    st.markdown('<div class="tp-section-label">Live monitor</div>', unsafe_allow_html=True)
    auto_refresh = st.toggle('Auto refresh', key='monitor_auto_refresh', help='Poll the API every 3 seconds. Use Refresh now to redraw the map without resetting its view.')
    if st.button('Refresh now', key='monitor_refresh_now'):
        st.rerun()

    def refresh_panel():
        health_url = _health_url()
        api_connected = False
        new_events = []
        cloud = _is_cloud()
        if not cloud:
            api_connected, new_events = poll_api(health_url=health_url, since=session.get('monitor_event_cursor', 0))
        old_source = session.get('monitor_source')
        if api_connected:
            session['monitor_source'] = 'live'
            session['monitor_api_connected'] = True
            existing = session.get('monitor_events', []) if old_source == 'live' else []
            all_events = {_event_id(row): row for row in existing}
            for row in new_events:
                all_events[_event_id(row)] = row
                session['monitor_event_cursor'] = max(int(session.get('monitor_event_cursor', 0)), int(row.get('seq', _event_id(row) - 1)) + 1)
            session['monitor_events'] = sorted(all_events.values(), key=_event_id)[-5000:]
        else:
            session['monitor_api_connected'] = False
            session['monitor_source'] = 'recorded'
            recorded = load_recorded_events()
            if recorded:
                now = time.monotonic()
                index = int(session.get('monitor_recorded_index', -1))
                last_advance = float(session.get('monitor_recorded_advance_at', 0.0))
                if index < 0:
                    index = 0
                    session['monitor_recorded_advance_at'] = now
                elif now - last_advance >= 3.0:
                    index = (index + 1) % len(recorded)
                    session['monitor_recorded_advance_at'] = now
                session['monitor_recorded_index'] = index
                session['monitor_events'] = recorded[:index + 1]
            else:
                session['monitor_events'] = []
        events = session.get('monitor_events', [])
        if not api_connected:
            st.warning('Ground-station API is unavailable. Showing a recorded session.')
            st.caption('Set TP_API_URL to the backend /health endpoint to connect the live monitor.')
            if not load_recorded_events():
                st.info('No recorded session is available. Run scripts/record_session.py after processing API events.')
        else:
            st.success('API connected')
        if session.get('monitor_source') == 'recorded':
            st.markdown('<span class="tp-threat-badge small">RECORDED SESSION</span>', unsafe_allow_html=True)
        if st.button('Clear alerts', key='monitor_clear_alerts'):
            current = visible_events(events)
            session['monitor_alert_cutoff'] = max((_event_id(row) for row in current), default=0) + 1
            if api_connected and _local_api(health_url):
                try:
                    requests.post(health_url.replace('/health', '/reset-events'), timeout=1.0)
                except requests.RequestException:
                    pass
            session['monitor_events'] = [] if session.get('monitor_source') == 'recorded' else events
            session['monitor_selected_event'] = None
            session['monitor_selected_place'] = None
            st.rerun(scope='app')
        _render_alerts(events, ctx, auto_refresh)

        # st_folium remounts its iframe on a full app rerun. Refreshing the list
        # every three seconds is stable; map changes apply on the manual button.
        if old_source != session.get('monitor_source'):
            st.rerun(scope='app')

    fragment_interval = 3 if auto_refresh or _is_cloud() or session.get('monitor_source') == 'recorded' else None
    st.fragment(run_every=fragment_interval)(refresh_panel)()
