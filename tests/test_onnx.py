import json
import time
from pathlib import Path

import numpy as np
import pytest

from tp.onnx_analyzer import ModelContractError, OnnxAnalyzer
from tp.selftest import run_selftest


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / 'model'
GOLDEN_PATH = MODEL_DIR / 'golden.npz'


def _artifacts_available():
    return all((MODEL_DIR / name).is_file() for name in ('config.json', 'detector.onnx', 'golden.npz'))


@pytest.fixture(scope='module')
def analyzer():
    if not _artifacts_available():
        pytest.skip('Local ONNX model or golden reference is missing.')
    return OnnxAnalyzer(MODEL_DIR)


def test_golden_selftest_passes():
    if not _artifacts_available():
        pytest.skip('golden.npz is missing; ONNX self-test was skipped.')
    result = run_selftest(MODEL_DIR)
    assert result['ok'], result
    assert result['max_abs_diff'] < 1e-2
    assert result['n'] > 0


def test_analyze_rejects_wrong_shape_and_dtype(analyzer):
    with pytest.raises(ValueError, match=r'shape \(4, 256, 256\)'):
        analyzer.analyze(np.zeros((4, 255, 256), dtype=np.uint16), 1000)
    with pytest.raises(TypeError, match='dtype uint16'):
        analyzer.analyze(np.zeros((4, 256, 256), dtype=np.float32), 1000)


def test_batch_and_single_scores_match(analyzer):
    if not GOLDEN_PATH.is_file():
        pytest.skip('golden.npz is missing; batch comparison was skipped.')
    with np.load(GOLDEN_PATH, allow_pickle=False) as archive:
        chips = archive['pixels'][:4]
        offsets = archive['offsets'][:4]
    batch = analyzer.analyze_batch(chips, offsets, batch_size=3)
    singles = [analyzer.analyze(chip, int(offset)) for chip, offset in zip(chips, offsets)]
    np.testing.assert_allclose(
        [result['score'] for result in batch],
        [result['score'] for result in singles],
        rtol=0.0,
        atol=1e-4,
    )


def test_mean_single_chip_latency_over_twenty_runs(analyzer, record_property):
    if not GOLDEN_PATH.is_file():
        pytest.skip('golden.npz is missing; latency measurement was skipped.')
    with np.load(GOLDEN_PATH, allow_pickle=False) as archive:
        chip = archive['pixels'][0]
        offset = int(archive['offsets'][0])
    timings = []
    for _ in range(20):
        started = time.perf_counter()
        analyzer.analyze(chip, offset)
        timings.append((time.perf_counter() - started) * 1000.0)
    mean_ms = float(np.mean(timings))
    record_property('mean_single_chip_latency_ms_over_20_runs', mean_ms)
    print(f'Mean single-chip latency over 20 runs: {mean_ms:.3f} ms')


def test_incomplete_calibration_fails_clearly(tmp_path):
    (tmp_path / 'config.json').write_text(json.dumps({'calibration': {'t_low': 1.0}}), encoding='utf-8')
    with pytest.raises(ModelContractError, match='calibration is incomplete'):
        OnnxAnalyzer(tmp_path)


def test_version_info_contains_runtime_and_file_hashes(analyzer):
    info = analyzer.version_info()
    assert len(info['onnx_sha256']) == 64
    assert len(info['config_sha256']) == 64
    assert info['t_low'] < info['t_high']
    assert info['onnxruntime_version']
    assert info['model_size_mb'] > 0
    assert info['variant'] == 'M1'

