"""Run the exported detector through ONNX Runtime without PyTorch."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort


class ModelContractError(ValueError):
    """Raised when the model files or input tensors violate the runtime contract."""


class OnnxAnalyzer:
    def __init__(self, model_dir: str | Path = 'model', threads: int | None = None):
        self.model_dir = Path(model_dir)
        config_path = self.model_dir / 'config.json'
        model_path = self.model_dir / 'detector.onnx'
        try:
            self.config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelContractError(f"Could not read config.json: {exc.__class__.__name__}.") from exc

        calibration = self.config.get('calibration')
        required = ('t_low', 't_high', 'platt_a', 'platt_b')
        if not isinstance(calibration, dict):
            raise ModelContractError("config.json must contain a 'calibration' object.")
        missing = [key for key in required if key not in calibration]
        if missing:
            raise ModelContractError('config.json calibration is incomplete; missing: ' + ', '.join(missing))
        values = {}
        for key in required:
            value = calibration[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ModelContractError(f'config.json calibration field {key!r} must be a finite number.')
            values[key] = float(value)
        self.t_low = values['t_low']
        self.t_high = values['t_high']
        self.platt_a = values['platt_a']
        self.platt_b = values['platt_b']

        if not model_path.is_file():
            raise ModelContractError('Model file detector.onnx is missing.')
        if threads is None:
            threads = min(4, os.cpu_count() or 1)
        if isinstance(threads, bool) or not isinstance(threads, int) or threads < 1:
            raise ValueError('threads must be a positive integer.')

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        try:
            self._session = ort.InferenceSession(
                str(model_path), sess_options=options, providers=['CPUExecutionProvider']
            )
        except Exception as exc:
            raise ModelContractError(f'Could not load detector.onnx with ONNX Runtime: {exc.__class__.__name__}.') from exc

        inputs = self._session.get_inputs()
        named_input = next((item for item in inputs if item.name == 'x'), None)
        if named_input is None:
            raise ModelContractError("detector.onnx must have an input named 'x'.")
        shape = named_input.shape
        if (
            len(shape) != 4
            or isinstance(shape[0], int)
            or shape[1:] != [4, 256, 256]
        ):
            raise ModelContractError(
                "detector.onnx input 'x' must have dynamic batch shape [N, 4, 256, 256]."
            )
        self._input_name = named_input.name

    @staticmethod
    def _validate_offset(offset: Any) -> int:
        if (
            isinstance(offset, bool)
            or not isinstance(offset, (int, float, np.integer, np.floating))
            or not math.isfinite(float(offset))
            or float(offset) not in (0.0, 1000.0)
        ):
            raise ValueError('offset must be 0 or 1000.')
        return int(offset)

    @staticmethod
    def _validate_pixels(pixels: Any) -> np.ndarray:
        array = np.asarray(pixels)
        if array.dtype != np.uint16:
            raise TypeError('pixels must have dtype uint16.')
        if array.shape != (4, 256, 256):
            raise ValueError('pixels must have shape (4, 256, 256).')
        return array

    @staticmethod
    def _sigmoid(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float32)
        result = np.empty_like(values)
        positive = values >= 0
        result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
        exp_values = np.exp(values[~positive])
        result[~positive] = exp_values / (1.0 + exp_values)
        return result

    def _run_batch(self, chips: np.ndarray, offsets: list[int]) -> list[dict[str, Any]]:
        if not len(chips):
            return []
        batch = np.stack([
            np.clip((chip.astype(np.float32) - float(offset)) / 10000.0, 0.0, 1.5)
            for chip, offset in zip(chips, offsets)
        ]).astype(np.float32, copy=False)
        started = time.perf_counter()
        outputs = self._session.run(None, {self._input_name: np.ascontiguousarray(batch)})
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not outputs:
            raise ModelContractError('detector.onnx returned no outputs.')
        logits_batch = np.asarray(outputs[0], dtype=np.float32)
        if logits_batch.shape == (len(chips), 1, 256, 256):
            logits_batch = logits_batch[:, 0]
        if logits_batch.shape != (len(chips), 256, 256):
            raise ModelContractError('detector.onnx output must have shape (N, 1, 256, 256).')

        results = []
        for logits in logits_batch:
            flat = logits.reshape(-1)
            score = float(np.partition(flat, flat.size - 200)[-200:].mean(dtype=np.float64))
            results.append({
                'score': score,
                'prob': self._sigmoid(logits),
                'logits': logits.copy(),
                'latency_ms': float(elapsed_ms / len(chips)),
            })
        return results

    def analyze(self, pixels: np.ndarray, offset: int) -> dict[str, Any]:
        chip = self._validate_pixels(pixels)
        checked_offset = self._validate_offset(offset)
        return self._run_batch(chip[None], [checked_offset])[0]

    def analyze_batch(
        self,
        chips: np.ndarray,
        offsets: list[int] | np.ndarray,
        batch_size: int = 4,
    ) -> list[dict[str, Any]]:
        arrays = np.asarray(chips)
        if arrays.dtype != np.uint16:
            raise TypeError('chips must have dtype uint16.')
        if arrays.ndim != 4 or arrays.shape[1:] != (4, 256, 256):
            raise ValueError('chips must have shape (N, 4, 256, 256).')
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError('batch_size must be a positive integer.')
        offset_array = np.asarray(offsets)
        if offset_array.ndim != 1 or len(offset_array) != len(arrays):
            raise ValueError('offsets must be a one-dimensional sequence with one value per chip.')
        checked_offsets = [self._validate_offset(value.item() if isinstance(value, np.generic) else value) for value in offset_array]

        results = []
        for start in range(0, len(arrays), batch_size):
            stop = min(start + batch_size, len(arrays))
            results.extend(self._run_batch(arrays[start:stop], checked_offsets[start:stop]))
        return results

    def trust_index(self, score: float) -> float:
        z = self.platt_a * float(score) + self.platt_b
        if z >= 0:
            probability = 1.0 / (1.0 + math.exp(-z))
        else:
            exp_z = math.exp(z)
            probability = exp_z / (1.0 + exp_z)
        return float(100.0 * (1.0 - probability))

    def decision_thresholds(self) -> tuple[float, float]:
        return self.t_low, self.t_high

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def version_info(self) -> dict[str, Any]:
        model_path = self.model_dir / 'detector.onnx'
        config_path = self.model_dir / 'config.json'
        return {
            'onnx_sha256': self._sha256(model_path),
            'config_sha256': self._sha256(config_path),
            't_low': self.t_low,
            't_high': self.t_high,
            'onnxruntime_version': ort.__version__,
            'model_size_mb': model_path.stat().st_size / 1_000_000.0,
            'variant': self.config.get('variant'),
        }

