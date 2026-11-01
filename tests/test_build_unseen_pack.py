"""Resumable pack-builder behavior with a mocked STAC catalog."""

import json

import numpy as np

from scripts import build_unseen_pack as builder


def test_builder_filters_dates_references_samples_and_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builder, "PLACES", {"Tunis": (10.20, 36.85, False)})
    samples = tmp_path / "samples"
    samples.mkdir()
    np.save(samples / "chip_001.npy", np.zeros((4, 256, 256), dtype=np.uint16), allow_pickle=False)
    (samples / "chip_001.json").write_text(json.dumps({
        "date": "2026-09-20", "lon": 10.2, "lat": 36.85, "region": "nord_tunis",
        "scene": "held-out", "tile": "32SNA", "r0": 0, "c0": 0, "offset": 1000,
    }), encoding="utf-8")
    monkeypatch.setattr(builder, "list_acquisitions", lambda *args, **kwargs: [
        {"item_id": "old", "date": "2026-09-30"},
        {"item_id": "clean-a", "date": "2026-10-10"},
        {"item_id": "cloud", "date": "2026-10-11"},
        {"item_id": "clean-b", "date": "2026-10-12"},
    ])
    monkeypatch.setattr(builder, "fetch_acquisition", lambda item_id: {"id": item_id})

    def read_chip(item, lon, lat):
        bad = 0.1 if item["id"] == "cloud" else 0.0
        chip = np.full((4, 256, 256), 5000, dtype=np.uint16)
        meta = {"date": {"clean-a": "2026-10-10", "cloud": "2026-10-11", "clean-b": "2026-10-12"}[item["id"]],
                "lon": lon, "lat": lat, "scene": item["id"], "tile": "32SNA", "r0": 0,
                "c0": 0, "offset": 1000, "region": "Tunis", "place": "Tunis", "epsg": 32632,
                "x0": 500000.0, "y0": 4100000.0, "bad_frac": bad, "haze_frac": 0.0}
        return chip, meta

    monkeypatch.setattr(builder, "read_chip_at", read_chip)
    entries = builder.build("unseen_pack", max_total_mb=15)
    post = [row for row in entries if row.get("group") == "post-training scene"]
    assert {row["date"] for row in post} == {"2026-10-10", "2026-10-11", "2026-10-12"}
    assert sum(row["cloudy"] for row in post) == 1
    assert any(row["group"] == "held-out test split" and row["file"] == "samples/chip_001.npy" for row in entries)
    assert not (tmp_path / "unseen_pack" / "samples" / "chip_001.npy").exists()

    second = builder.build("unseen_pack", max_total_mb=15)
    assert len([row for row in second if row.get("group") == "post-training scene"]) == 3
    index = json.loads((tmp_path / "unseen_pack" / "index.json").read_text(encoding="utf-8"))
    assert all(row["date"] >= "2026-10-01" for row in index["entries"] if row.get("group") == "post-training scene")
