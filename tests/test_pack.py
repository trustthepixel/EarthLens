"""Offline pack loading, proximity lookup, and date-split safeguards."""

import json
from datetime import date

import numpy as np

from tp.pack import list_places, load_pack, nearest_chip


def _write_chip(folder, stem, lon, lat, group="post-training scene", place="Tunis", cloudy=False, acquired="2026-10-10"):
    folder.mkdir(parents=True, exist_ok=True)
    pixels = np.full((4, 256, 256), 4000, dtype=np.uint16)
    np.save(folder / f"{stem}.npy", pixels, allow_pickle=False)
    metadata = {
        "date": acquired, "lon": lon, "lat": lat, "scene": f"scene-{stem}", "tile": "32SNA",
        "r0": 0, "c0": 0, "offset": 1000, "region": place, "place": place,
        "epsg": 32632, "x0": 500000.0, "y0": 4100000.0, "bad_frac": 0.1 if cloudy else 0.0,
        "haze_frac": 0.0, "group": group,
    }
    (folder / f"{stem}.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_load_pack_and_nearest_chip_work_without_network(tmp_path):
    pack_dir = tmp_path / "unseen_pack"
    _write_chip(pack_dir, "chip_000", 10.20, 36.85)
    index = {
        "places": [{"place": "Tunis", "center": [10.20, 36.85], "foreign": False, "chip_count": 1}],
        "entries": [{"place": "Tunis", "center": [10.20, 36.85], "file": "chip_000.npy",
                     "metadata": "chip_000.json", "date": "2026-10-10", "cloudy": False,
                     "group": "post-training scene"}],
    }
    (pack_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

    entries = load_pack(tmp_path)
    nearest = nearest_chip(10.201, 36.851, root=tmp_path)
    assert len(entries) == 1
    assert entries[0]["pixels"].shape == (4, 256, 256)
    assert nearest["place"] == "Tunis" and nearest["distance_km"] < 1
    assert nearest_chip(0.0, 0.0, max_km=30, root=tmp_path) is None
    assert any(place["place"] == "Tunis" for place in list_places(tmp_path))


def test_pack_loader_includes_sample_files_as_references(tmp_path):
    _write_chip(tmp_path / "samples", "chip_001", 9.18, 36.73, group="held-out test split", place="Beja")
    entries = load_pack(tmp_path)
    assert len(entries) == 1
    assert entries[0]["group"] == "held-out test split"
    assert entries[0]["pixels_path"].parent.name == "samples"


def test_post_training_index_entries_have_no_pre_training_dates():
    index_path = __import__("pathlib").Path("unseen_pack/index.json")
    if not index_path.is_file():
        return
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for row in index.get("entries", []):
        if row.get("group") == "post-training scene":
            assert date.fromisoformat(row["date"]) >= date(2026, 10, 1)
