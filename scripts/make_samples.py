"""Create a small offline sample set from the reference test chips."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "data_raw"
OUTPUT_DIR = ROOT / "samples"
EXPECTED_SHAPE = (4, 256, 256)
JSON_KEYS = (
    "date", "lon", "lat", "scene", "tile", "r0", "c0", "offset",
    "hard", "epsg", "x0", "y0", "region",
)
SAMPLE_RE = re.compile(r"^chip_\d{3}\.(?:npy|json)$")


def _native(value: object) -> object:
    """Convert pandas/NumPy scalars to JSON-compatible Python scalars."""
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


def _is_true(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return bool(value)
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


def _region_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.casefold())


def _select_indices(meta: pd.DataFrame, count: int) -> list[int]:
    step = max(1, count // 15)
    selected = set(range(0, count, step))

    cloudy = [i for i, value in enumerate(meta["hard"].tolist()) if _is_true(value)]
    selected.update(cloudy[:3])

    regions = meta["region"].tolist()
    for target, needles in (("tunis", ("tunis",)), ("beja", ("beja",))):
        matches = [
            i for i, region in enumerate(regions)
            if any(needle in _region_key(region) for needle in needles)
        ]
        selected.update(matches[:3])

    return sorted(selected)


def main() -> None:
    x_path = INPUT_DIR / "test_x.npy"
    off_path = INPUT_DIR / "test_off.npy"
    meta_path = INPUT_DIR / "test_meta.csv"
    x = np.load(x_path, allow_pickle=False)
    offsets = np.load(off_path, allow_pickle=False)
    meta = pd.read_csv(meta_path)

    if x.ndim != 4 or x.shape[1:] != EXPECTED_SHAPE:
        raise ValueError(f"test_x.npy must have shape (N,4,256,256); got {x.shape}")
    if x.dtype != np.uint16:
        raise ValueError(f"test_x.npy must have dtype uint16; got {x.dtype}")
    if offsets.ndim != 1:
        raise ValueError(f"test_off.npy must be one-dimensional; got {offsets.shape}")
    missing_columns = [key for key in JSON_KEYS if key not in meta.columns]
    if missing_columns:
        raise ValueError(f"test_meta.csv is missing columns: {', '.join(missing_columns)}")
    if not (len(x) == len(offsets) == len(meta)):
        raise ValueError(
            "Input lengths differ: "
            f"test_x.npy={len(x)}, test_off.npy={len(offsets)}, test_meta.csv={len(meta)}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    unexpected = sorted(
        path.name for path in OUTPUT_DIR.iterdir()
        if path.is_file() and not SAMPLE_RE.fullmatch(path.name)
    )
    if unexpected:
        print("Removing non-sample files from samples/: " + ", ".join(unexpected))
        for name in unexpected:
            (OUTPUT_DIR / name).unlink()
    else:
        print("Non-sample files to remove from samples/: none")

    indices = _select_indices(meta, len(x))
    for index in indices:
        row = meta.iloc[index]
        chip = x[index]
        if chip.shape != EXPECTED_SHAPE or chip.dtype != np.uint16:
            raise ValueError(f"Chip {index} violates the required shape or dtype")
        stem = f"chip_{index:03d}"
        np.save(OUTPUT_DIR / f"{stem}.npy", chip, allow_pickle=False)
        record = {key: _native(row[key]) for key in JSON_KEYS}
        record["offset"] = int(offsets[index])
        record["hard"] = _is_true(row["hard"])
        for key in ("lon", "lat", "x0", "y0"):
            record[key] = float(row[key])
        for key in ("r0", "c0", "epsg"):
            record[key] = int(row[key])
        record["region"] = str(row["region"])
        (OUTPUT_DIR / f"{stem}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    npy_files = sorted(OUTPUT_DIR.glob("chip_*.npy"))
    json_files = sorted(OUTPUT_DIR.glob("chip_*.json"))
    if len(npy_files) != len(json_files) or len(npy_files) != len(indices):
        raise RuntimeError("Generated .npy and .json sample counts do not match")
    for npy_path in npy_files:
        chip = np.load(npy_path, allow_pickle=False)
        if chip.shape != EXPECTED_SHAPE or chip.dtype != np.uint16:
            raise RuntimeError(f"Invalid generated chip: {npy_path.name}")
        json_path = npy_path.with_suffix(".json")
        record = json.loads(json_path.read_text(encoding="utf-8"))
        if not all(key in record for key in JSON_KEYS):
            raise RuntimeError(f"Metadata keys missing in {json_path.name}")
    cloudy_count = sum(_is_true(meta.iloc[i]["hard"]) for i in indices)
    print(f"Verified {len(indices)} chips; cloudy chips: {cloudy_count}")


if __name__ == "__main__":
    main()
