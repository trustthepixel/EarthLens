"""Exercise the API's direct attack and malformed-packet paths."""

import base64
import io
import json

import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

import api
from attacker.scenarios import MODES, tamper
from tp.engine import TrustPipeline
from tp.provenance import Ground, Source


def _sample():
    path = next(__import__('pathlib').Path('samples').glob('chip_*.npy'))
    return np.load(path, allow_pickle=False), json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))


def _body(pkg):
    stream = io.BytesIO()
    np.save(stream, pkg['pixels'], allow_pickle=False)
    return {'pixels': base64.b64encode(stream.getvalue()).decode(), 'manifest': pkg['manifest'], 'signature': pkg.get('signature')}


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    pixels, meta = _sample()
    source = Source()
    pipeline = TrustPipeline.ground_station({source.key_id: source.public_key})
    folder = tmp_path_factory.mktemp('api')
    private_path = folder / 'source.pem'
    private_path.write_bytes(source._sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))
    api._pipeline = pipeline
    api.EVENTS_PATH = folder / 'events.jsonl'
    return pixels, meta, source, pipeline, private_path


@pytest.fixture
def client(harness):
    harness[3].ground = Ground({harness[2].key_id: harness[2].public_key})
    return TestClient(api.app)


@pytest.mark.parametrize('mode', MODES)
def test_ingest_direct_scenarios(client, harness, mode):
    pixels, meta, source, pipeline, private_path = harness
    pkg = source.acquire(pixels, meta)
    loot = {}
    rng = np.random.default_rng(17)
    if mode == 'replay':
        first = client.post('/ingest', json=_body(tamper(pkg, mode, rng, loot=loot)))
        assert first.json()['status'] in {'TRUSTED', 'SUSPICIOUS'}
        following = source.acquire(pixels, meta)
        changed = tamper(following, mode, rng, loot=loot)
        result = client.post('/ingest', json=_body(changed)).json()
        assert result['status'] == 'COMPROMISED'
        return
    changed = tamper(pkg, mode, rng, stolen_key_path=private_path, loot=loot)
    response = client.post('/ingest', json=_body(changed), headers={'X-Attack-Mode': mode})
    assert response.status_code == 200
    result = response.json()
    assert {'status', 'reasons', 'score', 'trust', 'provenance', 'integrity', 'replay', 'changed_tiles'} <= result.keys()
    if mode in {'pixels', 'manifest_meta', 'manifest_rehash', 'resign'}:
        assert result['status'] == 'COMPROMISED'
    elif mode == 'strip':
        assert result['status'] in {'SUSPICIOUS', 'COMPROMISED'}
    elif mode == 'stolen_key':
        assert result['provenance'] == 'VALID'


def test_malformed_inputs_are_compromised(client, harness):
    _, meta, source, _, _ = harness
    valid = source.acquire(np.zeros((4, 256, 256), dtype=np.uint16), meta)
    wrong_shape = _body(valid)
    wrong = np.zeros((3, 256, 256), dtype=np.uint16)
    buff = io.BytesIO()
    np.save(buff, wrong, allow_pickle=False)
    wrong_shape['pixels'] = base64.b64encode(buff.getvalue()).decode()
    cases = [
        wrong_shape,
        {**_body(valid), 'pixels': '***invalid base64***'},
    ]
    for body in cases:
        result = client.post('/ingest', json=body).json()
        assert result['status'] == 'COMPROMISED' and result['reasons'] == ['Malformed packet']
    incomplete = client.post('/ingest', content=b'{"pixels":', headers={'content-type': 'application/json'}).json()
    assert incomplete['status'] == 'COMPROMISED' and incomplete['reasons'] == ['Malformed packet']
    oversized = client.post('/ingest', content=b' ' * (6 * 1024 * 1024 + 1), headers={'content-type': 'application/json'}).json()
    assert oversized['status'] == 'COMPROMISED' and oversized['reasons'] == ['Malformed packet']


def test_health_and_events(client):
    health = client.get('/health').json()
    assert health['ok'] is True
    assert 'resets when the server restarts' in health['anti_replay']
    assert client.get('/events?since=0').json()['events']


def test_event_enrichment_and_png_artifacts(client, harness, monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'events_data')
    pixels, meta, source, _, _ = harness
    pkg = source.acquire(pixels, meta)
    response = client.post('/ingest', json=_body(pkg), headers={'X-Attack-Mode': 'feed-label'})
    assert response.status_code == 200
    event = client.get('/events?since=0&limit=100').json()['events'][-1]
    assert event['lon'] == pkg['manifest']['geo'][0]
    assert event['lat'] == pkg['manifest']['geo'][1]
    assert event['place'] in {'Tunis', 'Beja', 'Kairouan', 'Sfax', 'Tozeur', 'Gabes', 'Sicily', 'unknown'}
    assert event['assumed_mode'] == 'feed-label'
    assert event['scene'] == pkg['manifest']['scene']
    assert event['date'] == pkg['manifest']['time_utc']
    assert not any(isinstance(value, list) and len(value) > 100 for value in event.values())
    assert (api.EVENTS_DATA_DIR / f"{event['event_id']}_rgb.png").is_file()
    assert (api.EVENTS_DATA_DIR / f"{event['event_id']}_heat.png").is_file()


def test_malformed_event_has_null_geo_and_no_png(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'events_data')
    response = client.post('/ingest', content=b'{bad', headers={'content-type': 'application/json'})
    assert response.json()['status'] == 'COMPROMISED'
    event = client.get('/events?since=0&limit=100').json()['events'][-1]
    assert event['lon'] is event['lat'] is None
    assert event['status_raw'] == 'COMPROMISED'
    assert not api.EVENTS_DATA_DIR.exists()


def test_reset_archives_stream_and_preserves_replay_memory(client, harness, monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'events_data')
    monkeypatch.setattr(api, 'EVENTS_ARCHIVE_DIR', tmp_path / 'events_archive')
    pixels, meta, source, pipeline, _ = harness
    pkg = source.acquire(pixels, meta)
    first = client.post('/ingest', json=_body(pkg)).json()
    assert first['status'] in {'TRUSTED', 'SUSPICIOUS'}
    assert pipeline.ground.seen_nonces
    reset = client.post('/reset-events')
    assert reset.status_code == 200
    assert not client.get('/events').json()['events']
    assert list(api.EVENTS_ARCHIVE_DIR.iterdir())
    replay = client.post('/ingest', json=_body(pkg)).json()
    assert replay['status'] == 'COMPROMISED'
    event = client.get('/events').json()['events'][0]
    assert event['replay'] is True


def test_events_endpoint_missing_file_and_limit(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api, 'EVENTS_PATH', tmp_path / 'absent.jsonl')
    assert client.get('/events?since=0&limit=2').json() == {'events': []}
    assert client.get('/events?limit=0').status_code == 400


def test_events_endpoint_ignores_partial_final_jsonl_line(client, monkeypatch, tmp_path):
    path = tmp_path / 'partial.jsonl'
    path.write_text('{"event_id":1,"status":"TRUSTED"}\n{"event_id":', encoding='utf-8')
    monkeypatch.setattr(api, 'EVENTS_PATH', path)
    assert client.get('/events').json()['events'] == [{'event_id': 1, 'status': 'TRUSTED'}]


def test_reset_events_rejects_non_local_client(harness):
    from fastapi.testclient import TestClient
    client = TestClient(api.app, client=('192.0.2.1', 5000))
    assert client.post('/reset-events').status_code == 403
