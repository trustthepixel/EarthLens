import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tp.provenance import AuditLog, CHANNEL_ATTACKS, Ground, Source, channel_attack, decide


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'samples'


def _sample_packet(source, sample_path):
    chip = np.load(sample_path, allow_pickle=False)
    metadata_path = sample_path.with_suffix('.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    return source.acquire(chip, metadata)


def test_sample_packets_verify_as_valid_and_intact():
    sample_paths = sorted(SAMPLES.glob('chip_*.npy'))
    assert sample_paths, 'No sample chips are available'
    source = Source()
    ground = Ground({source.key_id: source.public_key})

    for sample_path in sample_paths:
        packet = _sample_packet(source, sample_path)
        result = ground.verify(packet)
        assert result['provenance'] == 'VALID', sample_path.name
        assert result['integrity'] == 'PASS', sample_path.name


@pytest.mark.parametrize(
    ('kind', 'expected'),
    [
        ('pixels', 'COMPROMISED'),
        ('manifest_meta', 'COMPROMISED'),
        ('manifest_rehash', 'COMPROMISED'),
        ('resign', 'COMPROMISED'),
        ('replay', 'COMPROMISED'),
        ('strip', 'SUSPICIOUS'),
    ],
)
def test_channel_attack_decisions(kind, expected):
    sample_path = sorted(SAMPLES.glob('chip_*.npy'))[0]
    source = Source()
    ground = Ground({source.key_id: source.public_key})
    original = _sample_packet(source, sample_path)
    old_packet = None
    if kind == 'replay':
        old_packet = original
        first_result = ground.verify(old_packet)
        assert first_result['provenance'] == 'VALID'

    attacked, _ = channel_attack(
        original,
        kind,
        np.random.default_rng(531),
        donor=np.roll(original['pixels'], 23, axis=2),
        old_pkg=old_packet,
    )
    result = ground.verify(attacked)
    status, _ = decide(result, 0.0, 1.445, 4.796)
    assert status == expected


def _audit_log():
    audit = AuditLog()
    for value in ('first', 'second', 'third'):
        audit.add({'event': value})
    return audit


def test_audit_log_detects_record_modification():
    audit = _audit_log()
    assert audit.verify()
    changed = copy.deepcopy(audit)
    changed.entries[1]['record']['event'] = 'altered'
    assert not changed.verify()


def test_audit_log_detects_deletion():
    audit = _audit_log()
    del audit.entries[1]
    assert not audit.verify()


def test_audit_log_detects_permutation():
    audit = _audit_log()
    audit.entries.reverse()
    assert not audit.verify()


def test_audit_log_detects_insertion():
    audit = _audit_log()
    audit.entries.insert(1, {'t': '2020-01-01T00:00:00Z', 'prev': '0' * 64, 'record': {}, 'hash': 'f' * 64})
    assert not audit.verify()


def test_audit_log_suffix_truncation_is_not_detected_without_an_anchor():
    """The chain can verify a remaining prefix because no external anchor records its former tip."""
    audit = _audit_log()
    audit.entries.pop()
    assert audit.verify()


def test_runtime_imports_do_not_load_torch():
    code = "import sys; import tp.attacks; import tp.provenance; assert 'torch' not in sys.modules"
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr



