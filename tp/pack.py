"""Offline access to prepared unseen chips and held-out sample chips."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT / "unseen_pack"
SAMPLES_DIR = ROOT / "samples"
PRESET_PLACES = {
    "Tunis": (10.20, 36.85, False), "Beja": (9.18, 36.73, False),
    "Kairouan": (10.10, 35.68, False), "Sfax": (10.74, 34.74, False),
    "Tozeur": (8.13, 33.92, False), "Gabes": (10.14, 33.88, False),
    "Sicily": (14.30, 37.55, True),
}


def _distance_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(value)))


def load_pack(root: str | Path | None = None) -> list[dict]:
    """Load validated pack entries and local samples without making network calls."""
    base = Path(root).resolve() if root is not None else ROOT
    pack_dir = base / "unseen_pack"
    samples_dir = base / "samples"
    entries: list[dict] = []
    index_path = pack_dir / "index.json"
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for row in index.get("entries", []):
                entry = _load_entry(base, pack_dir, row)
                if entry is not None:
                    entries.append(entry)
        except (OSError, ValueError, TypeError):
            entries = []

    known = {str(entry["pixels_path"].resolve()) for entry in entries}
    for meta_path in sorted(samples_dir.glob("chip_*.json")):
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        raw_place = str(metadata.get("place") or metadata.get("region") or "Unknown")
        place_aliases = {"nord_tunis": "Tunis", "nord_beja": "Beja"}
        row = {
            "file": f"samples/{meta_path.stem}.npy",
            "metadata": f"samples/{meta_path.name}",
            "place": place_aliases.get(raw_place.casefold(), raw_place),
            "center": [float(metadata.get("lon", 0.0)), float(metadata.get("lat", 0.0))],
            "date": str(metadata.get("date", "")),
            "cloudy": bool(metadata.get("hard", metadata.get("bad_frac", 0.0) > 0.05)),
            "group": "held-out test split",
        }
        entry = _load_entry(base, pack_dir, row)
        if entry is not None and str(entry["pixels_path"].resolve()) not in known:
            entries.append(entry)
            known.add(str(entry["pixels_path"].resolve()))
    return entries


def _load_entry(base: Path, pack_dir: Path, row: dict) -> dict | None:
    if not isinstance(row, dict) or not row.get("file") or not row.get("metadata"):
        return None
    file_path = Path(str(row["file"]))
    meta_path = Path(str(row["metadata"]))
    if file_path.is_absolute() or meta_path.is_absolute():
        return None
    pixels_path = (pack_dir / file_path).resolve() if not str(row["file"]).startswith("samples/") else (base / file_path).resolve()
    json_path = (pack_dir / meta_path).resolve() if not str(row["metadata"]).startswith("samples/") else (base / meta_path).resolve()
    try:
        pixels_path.relative_to(base)
        json_path.relative_to(base)
        pixels = np.load(pixels_path, allow_pickle=False)
        meta = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if pixels.shape != (4, 256, 256) or pixels.dtype != np.uint16 or not isinstance(meta, dict):
        return None
    output = dict(row)
    if output.get("group") == "held-out test split":
        aliases = {"nord_tunis": "Tunis", "nord_beja": "Beja"}
        raw_place = str(output.get("place", ""))
        output["place"] = aliases.get(raw_place.casefold(), raw_place)
    output.update({"pixels": pixels, "meta": meta, "pixels_path": pixels_path, "metadata_path": json_path})
    return output


def list_places(root: str | Path | None = None) -> list[dict]:
    """Summarize prepared places, including places represented by local samples."""
    entries = load_pack(root)
    places: dict[str, dict] = {
        name: {"place": name, "center": [lon, lat], "chips": 0, "foreign": foreign}
        for name, (lon, lat, foreign) in PRESET_PLACES.items()
    }
    for entry in entries:
        name = str(entry.get("place") or entry["meta"].get("place") or "Unknown")
        if name in places:
            places[name]["chips"] += 1
    return list(places.values())


def nearest_chip(lon: float, lat: float, max_km: float = 30, root: str | Path | None = None) -> dict | None:
    """Return the closest local chip entry within ``max_km``, otherwise None."""
    candidates = []
    for entry in load_pack(root):
        center = entry.get("center") or [entry["meta"].get("lon", 0.0), entry["meta"].get("lat", 0.0)]
        distance = _distance_km(float(lon), float(lat), float(center[0]), float(center[1]))
        if distance <= float(max_km):
            candidates.append((distance, entry))
    if not candidates:
        return None
    distance, entry = min(candidates, key=lambda item: item[0])
    return {**entry, "distance_km": distance}
