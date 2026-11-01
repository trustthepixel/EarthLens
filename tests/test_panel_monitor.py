"""Live monitor reduction and dashboard interaction tests."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import map_view, panel_monitor


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / 'app.py'


def _events():
    return [
        {'event_id': 1, 'seq': 0, 'time_utc': '2026-10-28T10:00:00+00:00', 'status': 'TRUSTED',
         'place': 'Tunis', 'lon': 10.20, 'lat': 36.85, 'score': 0.1, 'trust': 99.0,
         'provenance': 'VALID', 'integrity': 'PASS', 'replay': False, 'changed_tiles': [],
         'scene': 'scene-tunis', 'date': '2026-10-27', 'assumed_mode': 'passthrough'},
        {'event_id': 2, 'seq': 1, 'time_utc': '2026-10-28T10:00:01+00:00', 'status': 'SUSPICIOUS',
         'place': 'Beja', 'lon': 9.18, 'lat': 36.73, 'score': 3.0, 'trust': 60.0,
         'provenance': 'VALID', 'integrity': 'PASS', 'replay': False, 'changed_tiles': [],
         'scene': 'scene-beja', 'date': '2026-10-27', 'assumed_mode': 'pixels'},
        {'event_id': 3, 'seq': 2, 'time_utc': '2026-10-28T10:00:02+00:00', 'status': 'COMPROMISED',
         'place': 'Sfax', 'lon': 10.74, 'lat': 34.74, 'score': 8.0, 'trust': 2.0,
         'provenance': 'INVALID', 'integrity': 'FAIL', 'replay': False, 'changed_tiles': [1],
         'scene': 'scene-sfax', 'date': '2026-10-27', 'assumed_mode': 'manifest_meta'},
    ]


def test_latest_by_place_uses_highest_event_id_not_input_order():
    rows = [
        {'event_id': 5, 'place': 'Tunis', 'status': 'SUSPICIOUS'},
        {'event_id': 8, 'place': 'Beja', 'status': 'TRUSTED'},
        {'event_id': 2, 'place': 'Tunis', 'status': 'TRUSTED'},
        {'event_id': 7, 'place': 'Tunis', 'status': 'COMPROMISED'},
    ]
    latest = panel_monitor.latest_by_place(rows)
    assert latest['Tunis']['event_id'] == 7
    assert latest['Beja']['event_id'] == 8


def test_recorded_session_contains_compact_png_overlays():
    rows = panel_monitor.load_recorded_events()
    assert rows
    overlays = panel_monitor.event_overlays(rows[0], recorded=True)
    assert 'True colour' in overlays
    assert overlays['True colour']['image'].startswith('data:image/png;base64,')
    assert 'Forgery heatmap' not in overlays
    assert sum(path.stat().st_size for path in (ROOT / 'demo_session').iterdir() if path.is_file()) < 3 * 1024 * 1024


def test_event_png_paths_require_integer_ids_and_project_containment(tmp_path):
    assert panel_monitor.event_overlays({'event_id': '../1'}) == {}
    assert set(panel_monitor.event_overlays({'event_id': 1, 'rgb_file': '../../secret.png'})) <= {'True colour', 'Forgery heatmap'}
    assert panel_monitor._image_uri(tmp_path, 1, 'rgb') is None
    assert panel_monitor._image_uri(ROOT, 1, '../secret') is None


def test_monitor_app_counters_pulse_and_clear_alerts(monkeypatch):
    monkeypatch.setattr(map_view, 'probe_basemap', lambda: map_view.NO_TILES)
    import streamlit_folium

    rendered_maps = []
    monkeypatch.setattr(streamlit_folium, 'st_folium',
                        lambda map_object, **kwargs: rendered_maps.append(map_object) or {})
    events = _events()
    monkeypatch.setattr(panel_monitor, 'poll_api', lambda **kwargs: (True, events))
    monkeypatch.setattr(panel_monitor, 'load_recorded_events', lambda: [])

    app = AppTest.from_file(str(APP_PATH), default_timeout=90)
    app.session_state['dashboard_mode'] = 'Live monitor'
    app.run()
    assert not app.exception, app.exception
    assert len(rendered_maps) == 1
    html = rendered_maps[-1].get_root().render()
    assert html.count('animation:tp-pulse') == 1
    assert 'Ground station activity' in html
    assert 'Latest place' in html and 'Sfax' in html
    assert 'Visible events' in html and '>3</b>' in html

    counter_html = '\n'.join(item.value for item in app.markdown if 'tp-monitor-count' in item.value)
    assert '<b>1</b><span>Trusted</span>' in counter_html
    assert '<b>1</b><span>Suspicious</span>' in counter_html
    assert '<b>1</b><span>Compromised</span>' in counter_html

    app.button(key='monitor_clear_alerts').click().run()
    assert not app.exception, app.exception
    assert app.session_state['monitor_alert_cutoff'] == 4
    counter_html = '\n'.join(item.value for item in app.markdown if 'tp-monitor-count' in item.value)
    assert all(f'<b>0</b><span>{name}</span>' in counter_html
               for name in ('Trusted', 'Suspicious', 'Compromised'))
    assert all('scene-' not in item.value for item in app.markdown)


def test_monitor_app_shows_recorded_session_when_api_is_unreachable(monkeypatch):
    monkeypatch.setattr(map_view, 'probe_basemap', lambda: map_view.NO_TILES)
    import streamlit_folium

    rendered_maps = []
    monkeypatch.setattr(streamlit_folium, 'st_folium',
                        lambda map_object, **kwargs: rendered_maps.append(map_object) or {})
    monkeypatch.setattr(panel_monitor, 'poll_api', lambda **kwargs: (False, []))
    monkeypatch.setattr(panel_monitor, 'load_recorded_events', lambda: _events())

    app = AppTest.from_file(str(APP_PATH), default_timeout=90)
    app.session_state['dashboard_mode'] = 'Live monitor'
    app.run()
    assert not app.exception, app.exception
    banner = 'Ground-station API is unavailable. Showing a recorded session.'
    assert any(banner in item.value for item in app.warning)
    assert any('RECORDED SESSION' in item.value for item in app.markdown)
    assert rendered_maps[-1].get_root().render().count('RECORDED SESSION') >= 1
