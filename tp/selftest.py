"""Compare local ONNX inference with the checked-in golden reference."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from tp.onnx_analyzer import ModelContractError, OnnxAnalyzer


SCORE_TOLERANCE = 1e-2


def run_selftest(model_dir: str | Path = 'model') -> dict[str, Any]:
    model_path = Path(model_dir)
    golden_path = model_path / 'golden.npz'
    if not golden_path.is_file():
        raise ModelContractError('Golden reference golden.npz is missing.')

    try:
        with np.load(golden_path, allow_pickle=False) as archive:
            required = ('pixels', 'offsets', 'scores', 'probs')
            missing = [key for key in required if key not in archive.files]
            if missing:
                raise ModelContractError('golden.npz is incomplete; missing: ' + ', '.join(missing))
            pixels = np.asarray(archive['pixels'])
            offsets = np.asarray(archive['offsets'])
            golden_scores = np.asarray(archive['scores'], dtype=np.float32).reshape(-1)
            golden_probs = np.asarray(archive['probs'], dtype=np.float32)
    except (OSError, ValueError) as exc:
        if isinstance(exc, ModelContractError):
            raise
        raise ModelContractError(f'Could not read golden.npz: {exc.__class__.__name__}.') from exc

    if pixels.dtype != np.uint16 or pixels.ndim != 4 or pixels.shape[1:] != (4, 256, 256):
        raise ModelContractError('golden.npz pixels must have dtype uint16 and shape (N, 4, 256, 256).')
    count = len(pixels)
    if offsets.ndim != 1 or len(offsets) != count or len(golden_scores) != count:
        raise ModelContractError('golden.npz offsets and scores must contain one value per chip.')
    try:
        golden_probs = golden_probs.reshape(count, 256, 256)
    except ValueError as exc:
        raise ModelContractError('golden.npz probs must contain one (256, 256) map per chip.') from exc

    analyzer = OnnxAnalyzer(model_dir=model_path)
    scores = []
    probabilities = []
    latencies = []
    for chip, offset in zip(pixels, offsets):
        result = analyzer.analyze(chip, offset.item() if isinstance(offset, np.generic) else offset)
        scores.append(result['score'])
        probabilities.append(result['prob'])
        latencies.append(result['latency_ms'])

    score_differences = np.abs(np.asarray(scores, dtype=np.float64) - golden_scores.astype(np.float64))
    probability_differences = np.abs(np.asarray(probabilities, dtype=np.float32) - golden_probs)
    max_score_diff = float(score_differences.max(initial=0.0))
    max_prob_diff = float(probability_differences.max(initial=0.0))
    return {
        'ok': bool(max_score_diff < SCORE_TOLERANCE),
        'max_abs_diff': max_score_diff,
        'max_prob_diff': max_prob_diff,
        'n': count,
        'ms_mean': float(np.mean(latencies)) if latencies else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-dir', default='model')
    args = parser.parse_args()
    try:
        result = run_selftest(args.model_dir)
    except Exception as exc:
        result = {'ok': False, 'error': str(exc)}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
