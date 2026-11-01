import json
from pathlib import Path

import numpy as np
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.make_tpx2_vectors import OUT, build, vector_pixels
from tp.chain import GENESIS, decide_chained
from tp.device_protocol import (HEADER_LEN, PACKET_LEN, DeviceGround, DeviceSource, build_packet, parse_packet,
                                unpack_header)

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000}


def _chip(seed=0):
    return np.random.default_rng(seed).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16)


def _pair(**kwargs):
    source = DeviceSource()
    return source, DeviceGround({source.key_id: source.public_key}, **kwargs)


def _verify(ground, data):
    return ground.verify(parse_packet(data))


def test_packet_has_the_documented_size():
    assert HEADER_LEN == 121
    assert PACKET_LEN == 121 + 64 + 4 * 256 * 256 * 2
    source, _ = _pair()
    assert len(source.acquire(_chip(), META)) == PACKET_LEN


def test_header_round_trip_keeps_every_field():
    source, _ = _pair()
    fields = unpack_header(source.acquire(_chip(), META, nonce=bytes(range(8)))[:HEADER_LEN])
    assert fields['counter'] == 1 and fields['prev_hash'] == GENESIS
    assert fields['geo'] == [10.18, 36.8] and fields['time_utc'] == '2026-05-01'
    assert fields['tile'] == 'T32SNH' and fields['offset'] == 1000 and fields['shape'] == [4, 256, 256]
    assert fields['nonce'] == bytes(range(8)).hex() and fields['sensor'] == 'SENTINEL-2-L2A'


def test_authentic_packets_are_valid_intact_and_chained():
    source, ground = _pair()
    results = [_verify(ground, source.acquire(_chip(i), META)) for i in range(3)]
    assert [r['chain'] for r in results] == ['START', 'OK', 'OK']
    assert all(r['provenance'] == 'VALID' and r['integrity'] == 'PASS' and not r['replay'] for r in results)
    assert all(decide_chained(r, 0.0, 2.0, 6.0)[0] == 'TRUSTED' for r in results)


def test_pixel_edit_in_transit_fails_the_hash():
    source, ground = _pair()
    data = bytearray(source.acquire(_chip(), META))
    data[-1] ^= 0xFF
    result = _verify(ground, bytes(data))
    assert result['provenance'] == 'VALID' and result['integrity'] == 'FAIL'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


@pytest.mark.parametrize('index', [4, 12, 16, 48, 80, 88, 96, 100, 108, 109, 117])
def test_any_header_bit_flip_breaks_the_signature(index):
    source, ground = _pair()
    data = bytearray(source.acquire(_chip(), META))
    data[index] ^= 0x01
    try:
        packet = parse_packet(bytes(data))
    except ValueError:
        return  # rejected earlier, also acceptable
    result = ground.verify(packet)
    assert result['provenance'] == 'INVALID'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_rogue_signer_is_unknown():
    _, ground = _pair()
    rogue = DeviceSource()
    result = _verify(ground, rogue.acquire(_chip(), META))
    assert result['provenance'] == 'INVALID' and 'unknown key' in ' '.join(result['reasons'])


def test_stripped_signature_is_unknown_provenance():
    source, ground = _pair()
    packet = parse_packet(source.acquire(_chip(), META))
    packet['signature'] = None
    result = ground.verify(packet)
    assert result['provenance'] == 'UNKNOWN'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'SUSPICIOUS'


def test_replay_is_detected_and_not_chain_checked():
    source, ground = _pair()
    data = source.acquire(_chip(), META)
    _verify(ground, data)
    result = _verify(ground, data)
    assert result['replay'] and result['chain'] == 'N/A'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_dropped_packet_is_a_chain_gap():
    source, ground = _pair()
    _verify(ground, source.acquire(_chip(0), META))
    source.acquire(_chip(1), META)
    result = _verify(ground, source.acquire(_chip(2), META))
    assert result['chain'] == 'GAP'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'SUSPICIOUS'


def test_forged_link_is_a_fork_even_when_correctly_signed():
    source, ground = _pair()
    _verify(ground, source.acquire(_chip(0), META))
    source.head = '3' * 64  # a compromised node claims a different predecessor
    result = _verify(ground, source.acquire(_chip(1), META))
    assert result['chain'] == 'FORK'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_stolen_key_signs_valid_forgery_that_only_the_model_can_catch():
    sk = Ed25519PrivateKey.generate()
    honest, thief = DeviceSource(sk), DeviceSource(sk)
    ground = DeviceGround({honest.key_id: honest.public_key})
    _verify(ground, honest.acquire(_chip(0), META))
    thief.counter, thief.head = honest.counter, honest.head
    result = _verify(ground, thief.acquire(_chip(9), META))
    assert result['provenance'] == 'VALID' and result['integrity'] == 'PASS' and result['chain'] == 'OK'
    assert decide_chained(result, 0.0, 2.0, 6.0)[0] == 'TRUSTED'
    assert decide_chained(result, 9.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_future_date_and_unexpected_place_are_implausible():
    source, ground = _pair(aoi_boxes=[(8.0, 30.0, 12.0, 38.0)])
    future = _verify(ground, source.acquire(_chip(), {**META, 'date': '2999-01-01'}))
    assert not future['plausible']
    elsewhere = _verify(ground, source.acquire(_chip(), {**META, 'lon': 100.0, 'lat': 10.0}))
    assert not elsewhere['plausible']
    assert decide_chained(elsewhere, 0.0, 2.0, 6.0)[0] == 'SUSPICIOUS'


def test_dictionary_fields_are_not_trusted_over_the_signed_header():
    source, ground = _pair()
    packet = parse_packet(source.acquire(_chip(), META))
    packet['manifest']['counter'] = 999
    packet['manifest']['key_id'] = 'ff' * 8
    result = ground.verify(packet)
    assert result['provenance'] == 'VALID'
    assert ground.last_counter[source.key_id] == 1


@pytest.mark.parametrize('size', [0, 10, PACKET_LEN - 1, PACKET_LEN + 1])
def test_wrong_length_is_rejected(size):
    with pytest.raises(ValueError):
        parse_packet(b'\0' * size)


def test_bad_magic_is_rejected():
    source, _ = _pair()
    data = bytearray(source.acquire(_chip(), META))
    data[0] = ord('X')
    with pytest.raises(ValueError):
        parse_packet(bytes(data))


def test_malformed_header_hex_is_unknown_not_a_crash():
    _, ground = _pair()
    result = ground.verify({'pixels': _chip(), 'manifest': {'format': 'TPX2', 'header_hex': 'zz'}, 'signature': 'aa'})
    assert result['provenance'] == 'UNKNOWN' and result['reasons']


def test_legacy_json_packets_still_verify_through_the_same_ground():
    from tp.chain import ChainedSource
    legacy = ChainedSource()
    ground = DeviceGround({legacy.key_id: legacy.public_key})
    meta = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'scene': 'S', 'tile': 'T32SNH'}
    result = ground.verify(legacy.acquire(_chip(), meta))
    assert result['provenance'] == 'VALID' and result['chain'] == 'START'


def test_committed_test_vectors_match_the_generator():
    assert json.loads(Path(OUT).read_text(encoding='utf-8')) == json.loads(json.dumps(build()))


def test_vector_packets_verify_with_the_published_public_key():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    vectors = json.loads(Path(OUT).read_text(encoding='utf-8'))
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(vectors['public_key_hex']))
    for item in vectors['packets']:
        pub.verify(bytes.fromhex(item['signature_hex']), bytes.fromhex(item['header_hex']))
    sk = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(vectors['seed_hex']))
    data, _ = build_packet(sk, 1, GENESIS, vector_pixels(0), vectors['meta'], nonce=bytes.fromhex(vectors['packets'][0]['nonce_hex']))
    assert data[:HEADER_LEN].hex() == vectors['packets'][0]['header_hex']
