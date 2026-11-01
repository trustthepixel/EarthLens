"""Measure local ONNX, provenance, pipeline, memory, and model timings."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import psutil

from tp.engine import TrustPipeline
from tp.provenance import Ground


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "reports" / "measurements.json"


def _sample_chips() -> tuple[list[np.ndarray], list[dict]]:
    chips, metas = [], []
    for path in sorted(SAMPLES.glob("chip_*.npy")):
        chips.append(np.load(path, allow_pickle=False))
        metas.append(json.loads(path.with_suffix(".json").read_text(encoding="utf-8")))
    if not chips:
        raise RuntimeError("No sample chips are available for measurement.")
    return chips, metas


def _stats(values: list[float]) -> dict:
    return {
        "n_runs": len(values),
        "mean_ms": float(np.mean(values)),
        "p95_ms": float(np.percentile(values, 95)),
    }


def _process_rss(process: psutil.Process) -> int:
    info = process.memory_info()
    # peak_wset is the process lifetime peak on Windows; RSS is sampled elsewhere.
    return int(getattr(info, "peak_wset", info.rss))


def measure(model_dir: str | Path = "model", output: Path = OUTPUT) -> dict:
    chips, metas = _sample_chips()
    pipeline = TrustPipeline(str(model_dir))
    process = psutil.Process()
    peak_rss = _process_rss(process)
    offsets = [int(meta["offset"]) for meta in metas]

    # Warm the runtime, then measure 50 inference runs; with 20 local samples,
    # the inputs cycle through the available chips and the JSON records that fact.
    for _ in range(2):
        pipeline.analyzer.analyze(chips[0], offsets[0])
    latency_ms = []
    for index in range(50):
        chip_index = index % len(chips)
        result = pipeline.analyzer.analyze(chips[chip_index], offsets[chip_index])
        latency_ms.append(float(result["latency_ms"]))
        peak_rss = max(peak_rss, _process_rss(process))

    # Use a fresh verifier so the 50 unique signed packets have no prior state.
    verifier = Ground({pipeline.source.key_id: pipeline.source.public_key}, aoi_boxes=None)
    packets = [pipeline.acquire(chips[i % len(chips)], metas[i % len(metas)]) for i in range(50)]
    verify_ms = []
    for packet in packets:
        started = time.perf_counter()
        verifier.verify(packet)
        verify_ms.append((time.perf_counter() - started) * 1000.0)
        peak_rss = max(peak_rss, _process_rss(process))

    # Reset anti-replay state before the end-to-end measurement.
    pipeline.ground = Ground({pipeline.source.key_id: pipeline.source.public_key}, aoi_boxes=None)
    total_ms = []
    for index in range(50):
        chip_index = index % len(chips)
        started = time.perf_counter()
        packet = pipeline.acquire(chips[chip_index], metas[chip_index])
        pipeline.process(packet)
        total_ms.append((time.perf_counter() - started) * 1000.0)
        peak_rss = max(peak_rss, _process_rss(process))

    model_path = Path(model_dir) / "detector.onnx"
    model_bytes = model_path.stat().st_size
    value = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "environment": {"python": __import__("platform").python_version(), "platform": __import__("platform").platform()},
        "sample_inputs": {"available_unique_chips": len(chips), "inference_runs": 50, "cycled_when_needed": len(chips) < 50},
        "onnx_latency": _stats(latency_ms),
        "ground_verify": _stats(verify_ms),
        "total_pipeline": _stats(total_ms),
        "peak_resident_memory_bytes": peak_rss,
        "peak_memory_method": "Windows process peak working set when available; otherwise sampled RSS during measured loops.",
        "model_size": {"bytes": model_bytes, "decimal_mb": model_bytes / 1_000_000.0},
        "model_download_time_seconds": "not measured",
        "notes": "Inference uses 50 runs, cycling through the local sample set when fewer than 50 unique chips are available.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return value


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2, allow_nan=False))
