"""Evaluate authentic sample chips and fixed-seed synthetic forgeries."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from tp.attacks import ALL_FAMILIES, make_attack
from tp.engine import TrustPipeline
from tp.provenance import Ground


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
OUTPUT = ROOT / "reports" / "eval_samples.csv"
NOTE = "small sample, indicative only"
SEED = 20261027


def _samples() -> list[tuple[np.ndarray, dict]]:
    values = []
    for path in sorted(SAMPLES.glob("chip_*.npy")):
        values.append((np.load(path, allow_pickle=False), json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))))
    if not values:
        raise RuntimeError("No sample chips are available for evaluation.")
    return values


def _row(label: str, results: list[dict]) -> dict:
    counts = {status: sum(result["status"] == status for result in results) for status in ("TRUSTED", "SUSPICIOUS", "COMPROMISED")}
    total = len(results)
    return {
        "evaluation": label,
        "n_samples": total,
        "trusted": counts["TRUSTED"],
        "suspicious": counts["SUSPICIOUS"],
        "compromised": counts["COMPROMISED"],
        "trusted_rate": counts["TRUSTED"] / total if total else "",
        "suspicious_rate": counts["SUSPICIOUS"] / total if total else "",
        "compromised_rate": counts["COMPROMISED"] / total if total else "",
        "note": NOTE,
    }


def evaluate(model_dir: str | Path = "model", output: Path = OUTPUT) -> list[dict]:
    samples = _samples()
    pipeline = TrustPipeline(str(model_dir))
    rows = []
    authentic_results = []
    cloudy_results = []
    for chip, meta in samples:
        result = pipeline.process(pipeline.acquire(chip, meta), cloud_ctx={"cloudy": bool(meta.get("hard", False))})
        authentic_results.append(result)
        if bool(meta.get("hard", False)):
            cloudy_results.append(result)
    rows.append(_row("authentic_all", authentic_results))
    rows.append(_row("authentic_cloudy", cloudy_results))

    pipeline.ground = Ground({pipeline.source.key_id: pipeline.source.public_key}, aoi_boxes=None)
    for family_index, family in enumerate(ALL_FAMILIES):
        family_results = []
        for sample_index, (chip, meta) in enumerate(samples):
            donor = np.roll(chip, 37, axis=2)
            rng = np.random.default_rng(np.random.SeedSequence([SEED, family_index, sample_index]))
            attacked, mask, _record = make_attack(chip, donor, family, "strong", rng, int(meta["offset"]))
            if not np.any(mask):
                raise RuntimeError(f"Attack family {family} produced an empty evaluation mask.")
            packet = pipeline.acquire(attacked, meta)
            family_results.append(pipeline.process(packet, kind=f"eval:{family}"))
        rows.append(_row(f"forgery:{family}", family_results))

    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["evaluation", "n_samples", "trusted", "suspicious", "compromised", "trusted_rate", "suspicious_rate", "compromised_rate", "note"]
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    for row in evaluate():
        print(json.dumps(row, sort_keys=True))
