"""Build a resumable offline pack of post-training Sentinel-2 chips."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from tp.sentinel_live import fetch_acquisition, list_acquisitions, read_chip_at

PLACES = {
    "Tunis": (10.20, 36.85, False),
    "Beja": (9.18, 36.73, False),
    "Kairouan": (10.10, 35.68, False),
    "Sfax": (10.74, 34.74, False),
    "Tozeur": (8.13, 33.92, False),
    "Gabes": (10.14, 33.88, False),
    "Sicily": (14.30, 37.55, True),
}
POST_TRAINING_START = date(2026, 10, 1)


def _read_index(path: Path) -> dict:
    if not path.is_file():
        return {"places": [], "entries": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        raise ValueError("unseen_pack/index.json has an invalid format.")
    value.setdefault("places", [])
    return value


def _pack_bytes(directory: Path) -> int:
    return sum(path.stat().st_size for path in directory.glob("chip_*") if path.is_file())


def _save_index(directory: Path, index: dict) -> None:
    index["places"] = [{"place": name, "center": [lon, lat], "foreign": foreign,
                        "chip_count": sum(row.get("place") == name for row in index["entries"])}
                       for name, (lon, lat, foreign) in PLACES.items()]
    temporary = directory / "index.json.tmp"
    temporary.write_text(json.dumps(index, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(directory / "index.json")


def _add_held_out_references(entries: list[dict], samples: Path = Path("samples")) -> None:
    referenced = {str(row.get("file", "")) for row in entries}
    for metadata_path in sorted(samples.glob("chip_*.json")):
        file_name = f"samples/{metadata_path.stem}.npy"
        if file_name in referenced:
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not metadata_path.with_suffix(".npy").is_file():
                continue
            raw_place = str(metadata.get("place") or metadata.get("region") or "Unknown")
            place_aliases = {"nord_tunis": "Tunis", "nord_beja": "Beja"}
            place = place_aliases.get(raw_place.casefold(), raw_place)
            entries.append({"place": place,
                            "center": [float(metadata["lon"]), float(metadata["lat"])],
                            "file": file_name, "metadata": f"samples/{metadata_path.name}",
                            "date": str(metadata.get("date", "")),
                            "cloudy": bool(metadata.get("hard", metadata.get("bad_frac", 0) > 0.05)),
                            "group": "held-out test split"})
        except (OSError, ValueError, KeyError, TypeError):
            continue


def build(output: str | Path = "unseen_pack", max_total_mb: float = 15.0) -> list[dict]:
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    index_path = directory / "index.json"
    index = _read_index(index_path)
    entries = index["entries"]
    _add_held_out_references(entries)
    _save_index(directory, index)
    by_place = {name: [row for row in entries if row.get("place") == name and row.get("group") == "post-training scene"] for name in PLACES}
    existing_ids = {str(row.get("item_id", "")) for row in entries if row.get("item_id")}
    next_id = max([int(Path(str(row.get("file", "chip_-1.npy"))).stem.split("_")[-1]) for row in entries
                   if str(row.get("file", "")).startswith("chip_") and Path(str(row["file"])).stem.split("_")[-1].isdigit()] + [-1]) + 1
    today = datetime.now(timezone.utc).date()
    days = max(1, (today - POST_TRAINING_START).days + 1)

    for place, (lon, lat, foreign) in PLACES.items():
        rows = by_place[place]
        clean_dates = {str(row.get("date")) for row in rows if not row.get("cloudy")}
        cloudy_exists = any(row.get("cloudy") for row in rows)
        print(f"Searching post-training scenes for {place}...", flush=True)
        try:
            acquisitions = list_acquisitions(lon, lat, days=days, max_cloud=100, n=60)
        except Exception as exc:
            print(f"{place}: acquisition search unavailable ({type(exc).__name__}); existing entries retained.")
            continue
        for acquisition_number, acquisition in enumerate(acquisitions):
            acquired = str(acquisition.get("date", ""))[:10]
            try:
                if date.fromisoformat(acquired) < POST_TRAINING_START:
                    continue
            except ValueError:
                continue
            item_id = str(acquisition.get("item_id", ""))
            if item_id in existing_ids:
                continue
            degree_offset = min(0.008, 0.003 + acquisition_number * 0.0007)
            positions = [(lon + degree_offset, lat), (lon, lat + degree_offset),
                         (lon - degree_offset, lat), (lon, lat - degree_offset), (lon, lat)]
            try:
                item = fetch_acquisition(item_id)
            except Exception:
                continue
            for chip_lon, chip_lat in positions:
                try:
                    chip, meta = read_chip_at(item, chip_lon, chip_lat)
                except Exception:
                    continue
                cloudy_fraction = float(meta.get("bad_frac", 0.0))
                cloudy = 0.05 <= cloudy_fraction <= 0.60
                clean = cloudy_fraction < 0.05 and float(meta.get("haze_frac", 0.0)) < 0.05
                if not ((clean and len(clean_dates) < 2 and acquired not in clean_dates) or (cloudy and not cloudy_exists)):
                    continue
                chip_path = directory / f"chip_{next_id:03d}.npy"
                meta_path = directory / f"chip_{next_id:03d}.json"
                if _pack_bytes(directory) + chip.nbytes > max_total_mb * 1024 * 1024:
                    print(f"{place}: size limit reached; remaining acquisitions skipped.")
                    break
                chip = np.asarray(chip)
                if chip.shape != (4, 256, 256) or chip.dtype != np.uint16:
                    continue
                metadata = {**meta, "place": place, "group": "post-training scene"}
                temporary_chip = chip_path.with_suffix(".npy.tmp")
                with temporary_chip.open("wb") as stream:
                    np.save(stream, chip, allow_pickle=False)
                temporary_chip.replace(chip_path)
                temporary_meta = meta_path.with_suffix(".json.tmp")
                temporary_meta.write_text(json.dumps(metadata, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
                temporary_meta.replace(meta_path)
                row = {"place": place, "center": [chip_lon, chip_lat], "foreign": foreign,
                       "file": chip_path.name, "metadata": meta_path.name, "date": acquired,
                       "cloudy": cloudy, "group": "post-training scene", "item_id": item_id}
                entries.append(row)
                _save_index(directory, index)
                rows.append(row)
                existing_ids.add(item_id)
                next_id += 1
                clean_dates.add(acquired) if clean else None
                cloudy_exists = cloudy_exists or cloudy
                break

    # Held-out chips are references only; the sample files are never copied or changed.
    referenced = {str(row.get("file", "")) for row in entries}
    for metadata_path in sorted(Path("samples").glob("chip_*.json")):
        file_name = f"samples/{metadata_path.stem}.npy"
        if file_name in referenced:
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            chip_path = metadata_path.with_suffix(".npy")
            if not chip_path.is_file():
                continue
            entries.append({"place": str(metadata.get("place") or metadata.get("region") or "Unknown"),
                            "center": [float(metadata["lon"]), float(metadata["lat"])],
                            "file": file_name, "metadata": f"samples/{metadata_path.name}",
                            "date": str(metadata.get("date", "")),
                            "cloudy": bool(metadata.get("hard", metadata.get("bad_frac", 0) > 0.05)),
                            "group": "held-out test split"})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    index["entries"] = entries
    _save_index(directory, index)
    rows = []
    for place in PLACES:
        own = [entry for entry in entries if entry.get("place") == place]
        rows.append((place, len(own), sum(bool(entry.get("cloudy")) for entry in own),
                     ", ".join(sorted({str(entry.get("date")) for entry in own if entry.get("group") == "post-training scene"}))))
    print("Place     Chips  Cloudy  Post-training dates")
    for place, count, clouds, dates in rows:
        print(f"{place:<9} {count:>5} {clouds:>7}  {dates}")
    print(f"Pack size: {_pack_bytes(directory) / (1024 * 1024):.2f} MiB (limit {max_total_mb:g} MiB)")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-total-mb", type=float, default=15.0)
    parser.add_argument("--output", default="unseen_pack")
    args = parser.parse_args()
    build(args.output, args.max_total_mb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
