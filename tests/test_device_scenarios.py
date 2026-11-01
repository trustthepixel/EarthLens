"""Regression tests for applying the shared attack modes to TPX2 packets."""

import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attacker.device_scenarios import tamper_device_packet
from tp.chain import decide_chained
from tp.device_protocol import DeviceGround, DeviceSource, parse_packet


META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000}


def _pixels(seed=0):
    return np.random.default_rng(seed).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16)


def _packet(sk=None):
    source = DeviceSource(sk)
    return source, source.acquire(_pixels(), META)


def test_binary_modes_keep_the_existing_status_semantics(tmp_path):
    source, original = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    rng = np.random.default_rng(91)

    pixels = tamper_device_packet(original, 'pixels', rng)
    result = ground.verify(parse_packet(pixels))
    assert result['provenance'] == 'VALID' and result['integrity'] == 'FAIL'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'

    source, original = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    meta = tamper_device_packet(original, 'manifest_meta', rng)
    assert ground.verify(parse_packet(meta))['provenance'] == 'INVALID'

    source, original = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    rehashed = tamper_device_packet(original, 'manifest_rehash', rng)
    assert ground.verify(parse_packet(rehashed))['provenance'] == 'INVALID'

    source, original = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    forged = tamper_device_packet(original, 'resign', rng)
    assert ground.verify(parse_packet(forged))['provenance'] == 'INVALID'

    source, original = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    stripped = parse_packet(tamper_device_packet(original, 'strip', rng))
    assert stripped['signature'] is None
    result = ground.verify(stripped)
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'SUSPICIOUS'


def test_binary_replay_and_stolen_key_modes(tmp_path):
    source, first = _packet()
    ground = DeviceGround({source.key_id: source.public_key})
    loot = {}
    replay_first = tamper_device_packet(first, 'replay', np.random.default_rng(1), loot=loot)
    assert replay_first == first
    ground.verify(parse_packet(replay_first))
    replay_second = tamper_device_packet(first, 'replay', np.random.default_rng(2), loot=loot)
    assert replay_second == first
    assert ground.verify(parse_packet(replay_second))['replay'] is True

    key_path = tmp_path / 'source.pem'
    key_path.write_bytes(source._sk.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))
    second = source.acquire(_pixels(2), META)
    forged = tamper_device_packet(second, 'stolen_key', np.random.default_rng(3),
                                  stolen_key_path=key_path, loot={})
    checked = ground.verify(parse_packet(forged))
    assert checked['provenance'] == 'VALID' and checked['integrity'] == 'PASS'
    assert checked['chain'] == 'OK'


@pytest.mark.parametrize('probability,expected_changed', [(0.0, False), (1.0, True)])
def test_binary_target_probability(probability, expected_changed):
    source, original = _packet()
    places = {'Tunis': {'lon': META['lon'], 'lat': META['lat']}}
    changed = tamper_device_packet(original, 'manifest_meta', np.random.default_rng(5),
                                   target='Tunis', probability=probability, place_centers=places)
    assert (changed != original) is expected_changed


def test_binary_target_skips_packets_outside_thirty_kilometres():
    _, original = _packet()
    places = {'Tunis': {'lon': 11.0, 'lat': META['lat']}}
    changed = tamper_device_packet(original, 'manifest_meta', np.random.default_rng(5),
                                   target='Tunis', probability=1.0, place_centers=places)
    assert changed == original


def test_binary_input_is_not_mutated_and_bad_length_is_rejected():
    _, original = _packet()
    before = bytes(original)
    tamper_device_packet(original, 'manifest_meta', np.random.default_rng(7))
    assert original == before
    with pytest.raises(ValueError, match='length'):
        tamper_device_packet(b'bad', 'pixels', np.random.default_rng(7))
