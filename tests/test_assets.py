"""Validate the offline samples and locally available inference artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import pytest


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_KEYS = {"date", "lon", "lat", "scene", "tile", "r0", "c0", "offset"}


def test_sample_chips_have_matching_metadata() -> None:
    sample_dir = ROOT / "samples"
    arrays = {path.stem for path in sample_dir.glob("chip_*.npy")}
    metadata = {path.stem for path in sample_dir.glob("chip_*.json")}
    assert arrays
    assert arrays == metadata

    for stem in sorted(arrays):
        chip = np.load(sample_dir / f"{stem}.npy", allow_pickle=False)
        record = json.loads((sample_dir / f"{stem}.json").read_text(encoding="utf-8"))
        assert chip.shape == (4, 256, 256)
        assert chip.dtype == np.uint16
        assert SAMPLE_KEYS <= record.keys()


def test_model_configuration_golden_data_and_onnx_are_readable() -> None:
    paths = [
        ROOT / "model" / "detector.onnx",
        ROOT / "model" / "config.json",
        ROOT / "model" / "golden.npz",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in paths if not path.is_file()]
    if missing:
        pytest.skip("Local model artifacts unavailable: " + ", ".join(missing))

    config = json.loads(paths[1].read_text(encoding="utf-8"))
    assert config["bands"] == ["B02", "B03", "B04", "B08"]
    assert config["chip"] == 256
    with np.load(paths[2], allow_pickle=False) as golden:
        assert golden.files

    session = ort.InferenceSession(str(paths[0]), providers=["CPUExecutionProvider"])
    input_shape = session.get_inputs()[0].shape
    assert input_shape[1:] == [4, 256, 256]
