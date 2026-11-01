"""Tests for the training-free copy-move check and its use by the engine."""
import glob

import numpy as np
import pytest

from tp.forensics import copy_move
from tests.test_engine_chain import META, StubAnalyzer, _pipeline

SAMPLES = sorted(glob.glob('samples/*.npy'))[:4]


def _paste(chip, flip=False, k=1):
    out = chip.copy()
    patch = np.rot90(chip[:, 20:84, 20:84], k, axes=(1, 2))
    if flip:
        patch = patch[:, :, ::-1]
    out[:, 150:214, 150:214] = patch
    return out


@pytest.mark.parametrize('path', SAMPLES)
def test_authentic_sample_has_no_duplicate(path):
    assert copy_move(np.load(path))[0] == 0.0


@pytest.mark.parametrize('flip', [False, True])
def test_pasted_copy_is_found(flip):
    chip = np.load(SAMPLES[0])
    score, block_map = copy_move(_paste(chip, flip=flip))
    assert score >= 8
    assert block_map.shape == (8, 8) and block_map.sum() > 0


def test_wrong_shape_is_rejected():
    with pytest.raises(ValueError):
        copy_move(np.zeros((4, 128, 128), np.uint16))


def test_flat_chip_gives_zero():
    assert copy_move(np.full((4, 256, 256), 1500, np.uint16))[0] == 0.0


def test_engine_raises_a_duplicated_region_to_suspicious_and_reports_evidence():
    pipeline = _pipeline(score=0.0)
    chip = _paste(np.load(SAMPLES[0]))
    result = pipeline.process(pipeline.acquire(chip, META))
    assert result['status'] == 'SUSPICIOUS'
    assert result['evidence']['copy_move'] >= 8
    assert any('Duplicated region' in reason for reason in result['reasons'])


def test_engine_keeps_authentic_sample_trusted():
    pipeline = _pipeline(score=0.0)
    result = pipeline.process(pipeline.acquire(np.load(SAMPLES[1]), META))
    assert result['status'] == 'TRUSTED' and not result['evidence']['copy_move']
