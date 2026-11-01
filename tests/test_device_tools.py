import json

import numpy as np
from fastapi.testclient import TestClient

import api
from api import load_trusted_keys
from attacker import device_feed
from scripts import make_device_key
from tests.test_api_v2 import _Pipeline
from tp.device_protocol import DeviceSource


def _samples(n=3):
    meta = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000}
    return [(f'chip_{i}', np.random.default_rng(i).integers(1000, 4000, (4, 256, 256), dtype=np.uint16), meta) for i in range(n)]


def test_device_key_tool_writes_matching_seed_public_key_and_header(tmp_path):
    seed_path, public_path, key_id = make_device_key.provision(tmp_path, 'esp32cam', c_header_path=tmp_path / 'fw' / 'device_seed.h')
    source = device_feed.make_source(seed_path, tmp_path / 'state.json')
    assert source.key_id == key_id
    assert key_id in load_trusted_keys(tmp_path / 'trusted_keys')
    header = (tmp_path / 'fw' / 'device_seed.h').read_text(encoding='utf-8')
    assert key_id in header and header.count('0x') == 32


def test_device_key_tool_refuses_to_overwrite_and_validates_name(tmp_path):
    make_device_key.provision(tmp_path, 'pi')
    for call in (lambda: make_device_key.provision(tmp_path, 'pi'), lambda: make_device_key.provision(tmp_path, 'Bad Name')):
        try:
            call()
        except (FileExistsError, ValueError):
            continue
        raise AssertionError('expected an error')
    assert make_device_key.main(['--root', str(tmp_path), '--name', 'pi']) == 1


def test_feed_signs_chains_persists_state_and_can_drop(tmp_path, monkeypatch):
    seed_path, _, key_id = make_device_key.provision(tmp_path, 'pi')
    keys = load_trusted_keys(tmp_path / 'trusted_keys')
    monkeypatch.setattr(api, '_pipeline', _Pipeline(keys))
    monkeypatch.setattr(api, 'EVENTS_PATH', tmp_path / 'events.jsonl')
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'data')
    client = TestClient(api.app)
    statuses = []

    def post(url, data, headers, timeout):
        response = client.post('/ingest_v2', content=data, headers=headers)
        statuses.append(response.json())
        return response

    state = tmp_path / 'state.json'
    device_feed.run('x', seed_path, state, interval=0, count=5, drop_every=3, samples=_samples(), post=post, sleep=lambda s: None)
    assert [s['chain'] for s in statuses] == ['START', 'OK', 'GAP', 'OK']  # packet 3 was dropped on purpose
    assert [s['status'] for s in statuses] == ['TRUSTED', 'TRUSTED', 'SUSPICIOUS', 'TRUSTED']
    assert json.loads(state.read_text(encoding='utf-8'))['counter'] == 5
    device_feed.run('x', seed_path, state, interval=0, count=1, samples=_samples(), post=post, sleep=lambda s: None)
    assert statuses[-1]['chain'] == 'OK'  # a restarted feed continues the chain


def test_feed_rejects_empty_samples(tmp_path):
    seed_path, *_ = make_device_key.provision(tmp_path, 'pi')
    try:
        device_feed.run('x', seed_path, tmp_path / 's.json', samples=[], post=None)
    except ValueError:
        return
    raise AssertionError('expected ValueError')
