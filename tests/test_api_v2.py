"""API integration for both packet formats, using a stub analyzer so no model file is needed."""
import base64
import io
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

import api
from attacker.device_scenarios import tamper_device_packet
from tp.chain import ChainedSource
from tp.device_protocol import PACKET_LEN, DeviceGround, DeviceSource
from tp.provenance import AuditLog
from tests.test_engine_chain import StubAnalyzer

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'scene': 'S2_TEST', 'offset': 1000}


def _chip(seed=0):
    return np.random.default_rng(seed).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16)


class _Pipeline:
    """Minimal stand-in for TrustPipeline: real ground station, stub model."""

    def __init__(self, keys, score=0.0):
        from tp.engine import TrustPipeline
        self._pipe = TrustPipeline.__new__(TrustPipeline)
        self._pipe.analyzer = StubAnalyzer(score)
        self._pipe.source = None
        self._pipe.ground = DeviceGround(keys)
        self._pipe.audit_log = AuditLog()
        self.ground, self.audit_log = self._pipe.ground, self._pipe.audit_log

    def process(self, pkg, **kwargs):
        return self._pipe.process(pkg, **kwargs)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    device, legacy = DeviceSource(), ChainedSource()
    keys = {device.key_id: device.public_key, legacy.key_id: legacy.public_key}
    monkeypatch.setattr(api, '_pipeline', _Pipeline(keys))
    monkeypatch.setattr(api, 'EVENTS_PATH', tmp_path / 'events.jsonl')
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'data')
    return TestClient(api.app), device, legacy, tmp_path


def _post_v2(client, data, **headers):
    return client.post('/ingest_v2', content=data, headers={'content-type': 'application/octet-stream', **headers})


def test_v2_authentic_packet_is_trusted_and_event_is_recorded(setup):
    client, device, _, tmp = setup
    response = _post_v2(client, device.acquire(_chip(), META))
    assert response.status_code == 200
    body = response.json()
    assert body['status'] == 'TRUSTED' and body['chain'] == 'START' and body['provenance'] == 'VALID'
    events = client.get('/events').json()['events']
    assert len(events) == 1 and events[0]['scene'] == 'T32SNH_2026-05-01' and events[0]['chain'] == 'START'
    event_id = events[0]['event_id']
    assert (tmp / 'data' / f'{event_id}_rgb.png').exists() and (tmp / 'data' / f'{event_id}_heat.png').exists()
    assert body['copy_move'] is not None


def test_v2_pixel_tampering_is_compromised(setup):
    client, device, _, _ = setup
    data = bytearray(device.acquire(_chip(), META))
    data[-5] ^= 0xFF
    body = _post_v2(client, bytes(data), **{'x-attack-mode': 'pixels'}).json()
    assert body['status'] == 'COMPROMISED' and body['integrity'] == 'FAIL'


def test_v2_scenario_output_is_accepted_and_recorded_by_api(setup):
    client, device, _, _ = setup
    data = device.acquire(_chip(), META)
    modified = tamper_device_packet(data, 'pixels', np.random.default_rng(19))
    body = _post_v2(client, modified, **{'x-attack-mode': 'pixels'}).json()
    assert body['status'] == 'COMPROMISED' and body['integrity'] == 'FAIL'
    events = client.get('/events').json()['events']
    assert len(events) == 1
    assert events[0]['assumed_mode'] == 'pixels'
    assert events[0]['integrity'] == 'FAIL'


def test_v2_dropped_packet_is_suspicious(setup):
    client, device, _, _ = setup
    _post_v2(client, device.acquire(_chip(0), META))
    device.acquire(_chip(1), META)
    body = _post_v2(client, device.acquire(_chip(2), META)).json()
    assert body['status'] == 'SUSPICIOUS' and body['chain'] == 'GAP'


def test_v2_replay_is_compromised(setup):
    client, device, _, _ = setup
    data = device.acquire(_chip(), META)
    _post_v2(client, data)
    assert _post_v2(client, data).json()['status'] == 'COMPROMISED'


@pytest.mark.parametrize('size', [0, 100, PACKET_LEN - 1, PACKET_LEN + 1, PACKET_LEN * 2])
def test_v2_wrong_size_is_a_malformed_packet(setup, size):
    client, *_ = setup
    body = _post_v2(client, b'\0' * size).json()
    assert body['status'] == 'COMPROMISED' and body['reasons'] == ['Malformed packet']


def test_v2_garbage_with_correct_size_is_malformed(setup):
    client, *_ = setup
    assert _post_v2(client, b'\x01' * PACKET_LEN).json()['reasons'] == ['Malformed packet']


def test_legacy_json_endpoint_still_works_after_the_refactor(setup):
    client, _, legacy, _ = setup
    pkg = legacy.acquire(_chip(), META)
    stream = io.BytesIO()
    np.save(stream, pkg['pixels'], allow_pickle=False)
    body = {'pixels': base64.b64encode(stream.getvalue()).decode(), 'manifest': pkg['manifest'], 'signature': pkg['signature']}
    result = client.post('/ingest', json=body).json()
    assert result['status'] == 'TRUSTED' and result['chain'] == 'START'
    assert len(client.get('/events').json()['events']) == 1


def test_dashboard_analysis_uses_signed_packet_without_adding_live_event(setup):
    client, _, legacy, _ = setup
    package = legacy.acquire(_chip(3), {**META, 'epsg': 32632})
    response = client.post('/analyze', json={
        **_legacy_body(package),
        'cloud_ctx': {'cloudy': False},
    })
    assert response.status_code == 200
    body = response.json()
    assert body['result']['status'] == 'TRUSTED'
    assert body['result']['evidence']['chain'] == 'START'
    assert len(client.get('/events').json()['events']) == 0


def _legacy_body(package):
    stream = io.BytesIO()
    np.save(stream, package['pixels'], allow_pickle=False)
    return {
        'pixels': base64.b64encode(stream.getvalue()).decode('ascii'),
        'manifest': package['manifest'],
        'signature': package['signature'],
    }


def test_both_formats_can_interleave_with_independent_chains(setup):
    client, device, legacy, _ = setup
    pkg = legacy.acquire(_chip(), META)
    stream = io.BytesIO()
    np.save(stream, pkg['pixels'], allow_pickle=False)
    json_body = {'pixels': base64.b64encode(stream.getvalue()).decode(), 'manifest': pkg['manifest'], 'signature': pkg['signature']}
    assert client.post('/ingest', json=json_body).json()['chain'] == 'START'
    assert _post_v2(client, device.acquire(_chip(1), META)).json()['chain'] == 'START'
    assert _post_v2(client, device.acquire(_chip(2), META)).json()['chain'] == 'OK'
