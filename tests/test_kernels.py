"""Tests for the state-adaptive kernel bank and the parity tools."""
import glob

import numpy as np
import pytest

from scripts import kernel_stats
from tp import attacks
from tp.kernels import STATE_KERNELS, STATES, analyze_kernels, classify_state, reflectance

SAMPLES = sorted(glob.glob('samples/*.npy'))


def _chip(index):
    return np.load(SAMPLES[index])


def test_reflectance_follows_the_input_contract():
    chip = np.full((4, 256, 256), 3000, np.uint16)
    assert np.allclose(reflectance(chip, 1000), 0.2)
    assert reflectance(np.full((4, 256, 256), 65535, np.uint16), 0).max() == pytest.approx(1.5)
    with pytest.raises(ValueError):
        reflectance(np.zeros((3, 256, 256), np.uint16))


def test_state_classification_of_known_scenes():
    water = np.load('samples/chip_060.npy')
    cloudy = np.load('samples/chip_035.npy')
    assert classify_state(water)[0] == 'flat'
    assert classify_state(cloudy)[0] == 'cloudy'
    assert classify_state(_chip(0))[0] == 'textured'


def test_every_state_has_kernels_and_known_names():
    assert set(STATE_KERNELS) == set(STATES)
    report = analyze_kernels(_chip(0))
    assert report['kernels'] == list(STATE_KERNELS[report['state']])
    assert report['anomaly_map'].shape == (256, 256)
    assert 0.0 <= report['anomaly_map'].min() and report['anomaly_map'].max() <= 1.0
    assert set(report['layers']) == {'lowpass', 'highpass', 'dog', 'median', 'morph'}
    assert all(m.shape == (8, 8) for m in report['block_maps'].values())


def test_analysis_is_deterministic():
    chip = _chip(1)
    assert analyze_kernels(chip)['score'] == analyze_kernels(chip)['score']


def test_inpainting_scores_above_a_typical_authentic_chip():
    rng = np.random.default_rng(0)
    base = [analyze_kernels(attacks.benign(_chip(i), rng, vary=True))['score'] for i in range(8)]
    edited = []
    for i in range(8):
        out, _, _ = attacks.make_attack(_chip(i), _chip(i + 1), 'inpaint_ns', 'strong', rng, 1000)
        edited.append(analyze_kernels(out)['score'])
    assert np.mean(edited) > np.mean(base)


def test_flat_constant_chip_does_not_crash_and_is_flat():
    report = analyze_kernels(np.full((4, 256, 256), 1500, np.uint16))
    assert report['state'] == 'flat' and np.isfinite(report['score'])


def test_kernel_stats_roundtrip_and_parity(tmp_path):
    rows = kernel_stats.interior_statistics(_chip(0), 1000)
    assert len(rows) == 4 and all(r['laplacian_sigma'] > 0 for r in rows)
    a, b = tmp_path / 'a.csv', tmp_path / 'b.csv'
    kernel_stats.write_stats(a, rows)
    kernel_stats.write_stats(b, rows)
    assert kernel_stats.compare(a, b) == []
    changed = [dict(r) for r in rows]
    changed[0]['dog_rms'] *= 1.5
    kernel_stats.write_stats(b, changed)
    problems = kernel_stats.compare(a, b)
    assert len(problems) == 1 and 'dog_rms' in problems[0]
