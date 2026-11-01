"""Engine integration of the hash chain, using a stub analyzer so no model file is needed."""
import numpy as np

from tp.chain import ChainedGround, ChainedSource
from tp.engine import TrustPipeline
from tp.provenance import AuditLog

META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'scene': 'S2_TEST', 'tile': 'T32SNH'}


class StubAnalyzer:
    def __init__(self, score=0.0):
        self.score = score

    def decision_thresholds(self):
        return 2.0, 6.0

    def analyze(self, pixels, offset):
        return {'score': self.score, 'latency_ms': 1.0, 'prob': np.zeros((256, 256), np.float32),
                'logits': np.zeros((256, 256), np.float32)}

    def trust_index(self, score):
        return 1.0 - min(score / 10.0, 1.0)

    def version_info(self):
        return {'onnx_sha256': 'stub', 'config_sha256': 'stub', 'variant': 'stub'}


def _pipeline(score=0.0):
    source = ChainedSource()
    pipeline = TrustPipeline.__new__(TrustPipeline)
    pipeline.analyzer = StubAnalyzer(score)
    pipeline.source = source
    pipeline.ground = ChainedGround(
        {source.key_id: source.public_key}, aoi_boxes=[(-180.0, -90.0, 180.0, 90.0)])
    pipeline.audit_log = AuditLog()
    return pipeline


def _chip(seed):
    return np.random.default_rng(seed).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16)


def test_chained_packets_are_trusted_and_report_chain_state():
    pipeline = _pipeline()
    first = pipeline.process(pipeline.acquire(_chip(0), META))
    second = pipeline.process(pipeline.acquire(_chip(1), META))
    assert first['status'] == 'TRUSTED' and first['evidence']['chain'] == 'START'
    assert second['status'] == 'TRUSTED' and second['evidence']['chain'] == 'OK'


def test_dropped_packet_makes_the_next_one_suspicious_in_the_engine():
    pipeline = _pipeline()
    pipeline.process(pipeline.acquire(_chip(0), META))
    pipeline.acquire(_chip(1), META)  # dropped before reaching the ground station
    result = pipeline.process(pipeline.acquire(_chip(2), META))
    assert result['evidence']['chain'] == 'GAP'
    assert result['status'] == 'SUSPICIOUS'
    assert any('chain gap' in reason for reason in result['reasons'])


def test_strong_model_score_still_compromises_a_chain_ok_packet():
    pipeline = _pipeline(score=9.0)
    pipeline.process(pipeline.acquire(_chip(0), META))
    result = pipeline.process(pipeline.acquire(_chip(1), META))
    assert result['evidence']['chain'] == 'OK' and result['status'] == 'COMPROMISED'


def test_replay_is_compromised_and_not_chain_checked():
    pipeline = _pipeline()
    packet = pipeline.acquire(_chip(0), META)
    pipeline.process(packet)
    result = pipeline.process(packet)
    assert result['status'] == 'COMPROMISED' and result['evidence']['chain'] == 'N/A'
