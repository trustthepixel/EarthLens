"""Tests for runtime-derived workspace summaries and map cards."""

from ui.map_view import _workspace_summary_html
from ui.workspace import map_summary


def test_analyze_summary_uses_current_session_evidence():
    session = {
        'area_result': {
            'status': 'SUSPICIOUS',
            'evidence': {'score': 2.75, 'trust': 41.0, 'latency_ms': 18.2},
        },
        'area_meta': {'scene': 'scene-from-packet', 'date': '2026-10-30'},
        'area_last_source': 'prepared',
    }

    summary = map_summary('Analyze area', session, {'prepared_places': []})

    assert summary['status'] == 'SUSPICIOUS'
    assert summary['subtitle'] == 'scene-from-packet | 2026-10-30'
    assert {item['label']: item['value'] for item in summary['metrics']} == {
        'Score': '2.75',
        'Trust index': '41.0',
        'Model latency': '18.2 ms',
        'Image source': 'Prepared scene',
    }


def test_live_summary_uses_visible_events_and_marks_recorded_source():
    session = {
        'monitor_source': 'recorded',
        'monitor_alert_cutoff': 5,
        'monitor_events': [
            {'event_id': 4, 'status': 'COMPROMISED', 'place': 'Old place'},
            {'event_id': 5, 'status': 'TRUSTED', 'place': 'Current place',
             'time_utc': '2026-11-01T00:00:00+00:00'},
        ],
    }

    summary = map_summary('Live monitor', session, {})
    metrics = {item['label']: item['value'] for item in summary['metrics']}

    assert summary['status'] == 'TRUSTED'
    assert summary['recorded'] is True
    assert metrics['Visible events'] == '1'
    assert metrics['Latest place'] == 'Current place'
    assert metrics['Trusted / Suspicious / Compromised'] == '1 / 0 / 0'


def test_map_card_escapes_packet_fields_and_uses_status_palette():
    rendered = _workspace_summary_html({
        'mode': 'Live monitor',
        'title': '<script>bad()</script>',
        'subtitle': 'source <unknown>',
        'status': 'COMPROMISED',
        'metrics': [{'label': 'Latest place', 'value': '<img src=x>'}],
        'recorded': True,
    })

    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered
    assert '&lt;img src=x&gt;' in rendered
    assert '#EF4444' in rendered
    assert 'RECORDED SESSION' in rendered
