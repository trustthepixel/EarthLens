"""Coverage for targeted attacks, the packet feed, and menu URL generation."""

import json

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import api
from attacker.attack_menu import build_mode_url
from attacker.feed import run, select_feed
from attacker.scenarios import should_target, tamper
from scripts.record_session import record
from tp.engine import TrustPipeline
from tp.provenance import Source


def test_target_radius_and_probability(tmp_path):
    places = {'Tunis': {'lon': 10.2, 'lat': 36.85}}
    rng = np.random.default_rng(2)
    assert should_target({'geo': [10.2, 36.85]}, 'Tunis', 1, rng, places)
    assert not should_target({'geo': [11.2, 36.85]}, 'Tunis', 1, rng, places)
    assert not should_target({'geo': [10.2, 36.85]}, 'Tunis', 0, rng, places)
    assert should_target({'geo': [0, 0]}, 'all', 1, rng, places)


def test_tamper_obeys_target_and_probability(tmp_path):
    places = {'Tunis': {'lon': 10.2, 'lat': 36.85}}
    packet = {'pixels': np.zeros((4, 256, 256), dtype=np.uint16), 'manifest': {'geo': [10.2, 36.85], 'scene': 'S'}}
    unchanged = tamper(packet, 'manifest_meta', np.random.default_rng(4), target='Tunis', probability=0,
                       place_centers=places)
    changed = tamper(packet, 'manifest_meta', np.random.default_rng(4), target='Tunis', probability=1,
                     place_centers=places)
    outside = tamper({**packet, 'manifest': {'geo': [11.2, 36.85], 'scene': 'S'}}, 'manifest_meta',
                     np.random.default_rng(4), target='Tunis', place_centers=places)
    assert unchanged['manifest']['scene'] == 'S'
    assert changed['manifest']['scene'].startswith('ALTERED_')
    assert outside['manifest']['scene'] == 'S'


def test_feed_direct_sends_six_packets_to_testclient(tmp_path, monkeypatch):
    monkeypatch.setenv('TP_API_URL', 'http://127.0.0.1:8000/health')
    pixels = np.full((4, 256, 256), 1200, dtype=np.uint16)
    meta = {'date': '2023-10-10', 'lon': 10.2, 'lat': 36.85, 'scene': 'FEED_TEST',
            'tile': 'T31TCJ', 'r0': 0, 'c0': 0, 'offset': 1000}
    private = Ed25519PrivateKey.generate()
    source = Source(sk=private)
    api._pipeline = TrustPipeline.ground_station({source.key_id: source.public_key})
    monkeypatch.setattr(api, 'EVENTS_PATH', tmp_path / 'events.jsonl')
    monkeypatch.setattr(api, 'EVENTS_DATA_DIR', tmp_path / 'events_data')
    key_path, counter_path = tmp_path / 'source.pem', tmp_path / 'counter.txt'
    key_path.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    entries = [{'place': 'Tunis', 'pixels': pixels, 'meta': meta},
               {'place': 'Beja', 'pixels': pixels, 'meta': {**meta, 'scene': 'FEED_TEST_BEJA'}}]
    assert [place for place, _ in select_feed(entries)] == ['Beja', 'Tunis']
    client = TestClient(api.app)
    sent = run(direct=True, count=6, post=lambda url, **kwargs: client.post(url, json=kwargs['json']),
               sleep=lambda _interval: None, entries=entries,
               source_paths=(key_path, counter_path))
    assert sent == 6
    assert len(client.get('/events?limit=20').json()['events']) == 6
    assert counter_path.read_text(encoding='utf-8') == '6'


def test_attack_menu_builds_control_url_without_network():
    url = build_mode_url('http://192.168.56.101:8080/', 'pixels', 'spectral', 'medium', 'Tunis', 0.25)
    assert url == ('http://192.168.56.101:8080/__mode?m=pixels&family=spectral&sev=medium&target=Tunis&p=0.25')


def test_record_session_exports_latest_events_and_images(tmp_path):
    from PIL import Image
    events = tmp_path / 'events.jsonl'
    events.write_text('\n'.join(json.dumps({'event_id': number, 'scene': f'S{number}'}) for number in range(1, 4)), encoding='utf-8')
    data = tmp_path / 'events_data'
    data.mkdir()
    Image.new('RGB', (8, 8), 'red').save(data / '3_rgb.png')
    Image.new('RGBA', (8, 8), (255, 0, 0, 80)).save(data / '3_heat.png')
    output = tmp_path / 'demo_session'
    count, size = record(1, events, data, output)
    exported = json.loads((output / 'events.json').read_text(encoding='utf-8'))['events']
    assert count == 1 and size < 3 * 1024 * 1024
    assert exported[0]['event_id'] == 3 and exported[0]['rgb_image'] == '3_rgb.png'
    assert (output / '3_heat.png').is_file()
