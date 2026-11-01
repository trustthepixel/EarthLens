"""Integration tests for the trust pipeline."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tp.attacks import make_attack
from tp.engine import TrustPipeline, build_report
from tp.provenance import CHANNEL_ATTACKS, Source, channel_attack


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'samples'


def _sample(index=0):
    path = sorted(SAMPLES.glob('chip_*.npy'))[index]
    return np.load(path, allow_pickle=False), json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))


def _pipeline():
    return TrustPipeline('model')


@pytest.mark.parametrize('kind', CHANNEL_ATTACKS, ids=CHANNEL_ATTACKS)
def test_channel_attack_scenarios_use_real_sample_chips(kind):
    pipeline = _pipeline()
    chip, meta = _sample()
    packet = pipeline.acquire(chip, meta)
    old_packet = None
    if kind == 'replay':
        old_packet = copy.deepcopy(packet)
        first = pipeline.ground.verify(old_packet)
        assert first['provenance'] == 'VALID'
    attacked, _ = channel_attack(
        packet,
        kind,
        np.random.default_rng(531),
        donor=np.roll(chip, 23, axis=2),
        old_pkg=old_packet,
    )
    result = pipeline.process(attacked, kind=kind)
    assert result['status'] in {'TRUSTED', 'SUSPICIOUS', 'COMPROMISED'}
    assert result['evidence']['provenance'] in {'VALID', 'INVALID', 'UNKNOWN'}
    assert result['evidence']['integrity'] in {'PASS', 'FAIL', 'UNVERIFIED'}
    expected = {
        'pixels': ('VALID', 'FAIL', 'COMPROMISED'),
        'manifest_meta': ('INVALID', 'UNVERIFIED', 'COMPROMISED'),
        'manifest_rehash': ('INVALID', 'UNVERIFIED', 'COMPROMISED'),
        'resign': ('INVALID', 'UNVERIFIED', 'COMPROMISED'),
        'replay': ('VALID', 'PASS', 'COMPROMISED'),
        'strip': ('UNKNOWN', 'UNVERIFIED', 'SUSPICIOUS'),
    }
    provenance, integrity, status = expected[kind]
    assert result['evidence']['provenance'] == provenance
    assert result['evidence']['integrity'] == integrity
    if kind != 'strip':
        assert result['status'] == status


def test_authentic_sample_returns_structured_result():
    pipeline = _pipeline()
    chip, meta = _sample()
    stages = []
    result = pipeline.process(pipeline.acquire(chip, meta), progress_callback=stages.append)
    assert stages == ['Verifying packet...', 'Running the model...']
    assert result['status'] in {'TRUSTED', 'SUSPICIOUS'}
    assert result['status_raw'] in {'TRUSTED', 'SUSPICIOUS'}
    assert isinstance(result['reasons'], list)
    assert {'provenance', 'integrity', 'replay', 'plausible', 'changed_tiles', 'score', 'trust', 'latency_ms', 't_low', 't_high'} <= result['evidence'].keys()
    assert isinstance(result['prob'], list) and isinstance(result['logits'], list)
    assert result['evidence']['provenance'] == 'VALID'
    assert result['evidence']['integrity'] == 'PASS'


def test_valid_signature_with_suspicious_content_sets_conflict():
    pipeline = _pipeline()
    chip, meta = _sample()
    donor = np.roll(chip, 37, axis=2)
    tampered, mask, _ = make_attack(chip, donor, 'inpaint_ns', 'strong', np.random.default_rng(13), meta['offset'])
    assert mask.any()
    packet = pipeline.acquire(tampered, meta)
    result = pipeline.process(packet, kind='signed_pre_tamper')
    assert result['evidence']['provenance'] == 'VALID'
    assert result['evidence']['integrity'] == 'PASS'
    assert result['evidence']['score'] >= result['evidence']['t_low']
    assert result['conflict'] is True


def test_cloud_cap_downgrades_only_ai_compromise():
    pipeline = _pipeline()
    chip, meta = _sample()
    packet = pipeline.acquire(chip, meta)
    _, t_high = pipeline.analyzer.decision_thresholds()
    pipeline.analyzer.analyze = lambda pixels, offset: {
        'score': t_high + 0.5, 'prob': np.zeros((256, 256), dtype=np.float32),
        'logits': np.zeros((256, 256), dtype=np.float32), 'latency_ms': 1.0,
    }
    result = pipeline.process(packet, cloud_ctx={'cloudy': True})
    assert result['status_raw'] == 'COMPROMISED'
    assert result['status'] == 'SUSPICIOUS'
    assert 'Cloudy context: AI score alone, not escalated' in result['reasons']


def test_verification_occurs_once_per_call_and_replay_is_detected_on_second_call():
    pipeline = _pipeline()
    chip, meta = _sample()
    packet = pipeline.acquire(chip, meta)
    original_verify = pipeline.ground.verify
    calls = 0

    def counted_verify(pkg):
        nonlocal calls
        calls += 1
        return original_verify(pkg)

    pipeline.ground.verify = counted_verify
    first = pipeline.process(packet)
    assert calls == 1
    assert first['evidence']['replay'] is False
    second = pipeline.process(packet)
    assert calls == 2
    assert second['evidence']['replay'] is True
    assert second['status'] == 'COMPROMISED'


def test_malformed_packet_is_handled_as_compromised():
    pipeline = _pipeline()
    result = pipeline.process({'pixels': np.zeros((2, 8, 8), dtype=np.float32), 'manifest': {}, 'signature': None})
    assert result['status'] == 'COMPROMISED'
    assert 'Input could not be analysed' in result['reasons']
    assert result['prob'] is None and result['logits'] is None


def test_report_hash_covers_report_without_hash_field():
    pipeline = _pipeline()
    chip, meta = _sample()
    result = pipeline.process(pipeline.acquire(chip, meta))
    report = build_report(result, meta)
    digest = report.pop('report_sha256')
    canonical = json.dumps(report, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    assert digest == hashlib.sha256(canonical).hexdigest()
    assert report['model_version']['onnx_sha256']
    assert {'scene', 'date', 'tile', 'offset', 'status', 'raw_status', 'reasons', 'evidence', 'scores', 'thresholds', 'app_version', 'timestamp_utc'} <= report.keys()
