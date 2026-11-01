import copy

import numpy as np
import pytest

from tp.chain import GENESIS, ChainedGround, ChainedSource, decide_chained, link_hash
from tp.provenance import Ground, Source, canonical

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'scene': 'S2_TEST', 'tile': 'T32SNH'}


def _chip(seed=0):
    return np.random.default_rng(seed).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16)


def _pair():
    source = ChainedSource()
    return source, ChainedGround({source.key_id: source.public_key})


def test_first_packet_starts_chain_and_following_packets_link():
    source, ground = _pair()
    states = [ground.verify(source.acquire(_chip(i), META))['chain'] for i in range(4)]
    assert states == ['START', 'OK', 'OK', 'OK']


def test_first_manifest_references_genesis():
    source, _ = _pair()
    assert source.acquire(_chip(), META)['manifest']['prev_hash'] == GENESIS


def test_chained_packets_still_verify_as_valid_and_intact():
    source, ground = _pair()
    result = ground.verify(source.acquire(_chip(), META))
    assert result['provenance'] == 'VALID'
    assert result['integrity'] == 'PASS'


def test_dropped_packet_is_reported_as_gap_and_chain_resynchronises():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    source.acquire(_chip(1), META)  # never reaches the ground station
    gap = ground.verify(source.acquire(_chip(2), META))
    assert gap['chain'] == 'GAP'
    assert '1 packet(s) missing' in ' '.join(gap['reasons'])
    assert ground.verify(source.acquire(_chip(3), META))['chain'] == 'OK'


def test_gap_raises_trusted_packet_to_suspicious_only():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    source.acquire(_chip(1), META)
    ver = ground.verify(source.acquire(_chip(2), META))
    assert decide_chained(ver, 0.0, 2.0, 6.0)[0] == 'SUSPICIOUS'


def test_forged_link_with_consecutive_counter_is_a_fork_and_compromised():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    forged = source.acquire(_chip(1), META)
    forged['manifest']['prev_hash'] = '1' * 64
    forged['signature'] = source._sk.sign(canonical(forged['manifest'])).hex()
    ver = ground.verify(forged)
    assert ver['chain'] == 'FORK'
    assert decide_chained(ver, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_editing_prev_hash_without_the_key_breaks_the_signature():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    packet = source.acquire(_chip(1), META)
    packet['manifest']['prev_hash'] = '2' * 64
    ver = ground.verify(packet)
    assert ver['provenance'] == 'INVALID'
    assert ver['chain'] == 'N/A'


def test_replayed_packet_is_not_chain_checked_and_head_is_unchanged():
    source, ground = _pair()
    first = source.acquire(_chip(0), META)
    ground.verify(first)
    head = dict(ground.heads)
    ver = ground.verify(copy.deepcopy(first))
    assert ver['replay'] is True and ver['chain'] == 'N/A'
    assert ground.heads == head


def test_pixel_tampering_in_transit_is_still_caught_by_hash_and_keeps_chain_intact():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    packet = source.acquire(_chip(1), META)
    packet['pixels'] = packet['pixels'].copy()
    packet['pixels'][0, :32, :32] = 0
    ver = ground.verify(packet)
    assert ver['integrity'] == 'FAIL' and ver['chain'] == 'OK'
    assert decide_chained(ver, 0.0, 2.0, 6.0)[0] == 'COMPROMISED'


def test_unchained_source_is_reported_absent_and_decision_is_unchanged():
    source = Source()
    ground = ChainedGround({source.key_id: source.public_key})
    ver = ground.verify(source.acquire(_chip(), META))
    assert ver['chain'] == 'ABSENT'
    assert decide_chained(ver, 0.0, 2.0, 6.0)[0] == 'TRUSTED'


def test_unknown_signer_is_not_chain_checked():
    trusted = ChainedSource()
    rogue = ChainedSource()
    ground = ChainedGround({trusted.key_id: trusted.public_key})
    ver = ground.verify(rogue.acquire(_chip(), META))
    assert ver['provenance'] == 'INVALID' and ver['chain'] == 'N/A'


def test_plain_ground_still_accepts_chained_packets():
    source = ChainedSource()
    ground = Ground({source.key_id: source.public_key})
    result = ground.verify(source.acquire(_chip(), META))
    assert result['provenance'] == 'VALID' and result['integrity'] == 'PASS'


@pytest.mark.parametrize('status', ['TRUSTED', 'SUSPICIOUS', 'COMPROMISED'])
def test_chain_evidence_never_lowers_an_existing_status(status):
    ver = {'reasons': [], 'integrity': 'PASS', 'provenance': 'VALID', 'replay': False,
           'plausible': True, 'chain': 'GAP'}
    score = {'TRUSTED': 0.0, 'SUSPICIOUS': 3.0, 'COMPROMISED': 9.0}[status]
    result, _ = decide_chained(ver, score, 2.0, 6.0)
    order = ['TRUSTED', 'SUSPICIOUS', 'COMPROMISED']
    assert order.index(result) >= order.index(status)


def test_link_hash_depends_on_signature():
    source = ChainedSource()
    packet = source.acquire(_chip(), META)
    other = '00' * 64
    assert link_hash(packet['manifest'], packet['signature']) != link_hash(packet['manifest'], other)


def test_source_with_unknown_head_restarts_chain_without_false_alarm():
    source, ground = _pair()
    ground.verify(source.acquire(_chip(0), META))
    source.head = None  # state lost, for example after an upgrade
    restart = source.acquire(_chip(1), META)
    assert 'prev_hash' not in restart['manifest']
    assert ground.verify(restart)['chain'] == 'ABSENT'
    assert ground.verify(source.acquire(_chip(2), META))['chain'] == 'OK'
