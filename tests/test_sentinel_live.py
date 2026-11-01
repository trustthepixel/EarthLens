"""Tests for retained live-acquisition comparison helpers."""

import numpy as np
import pytest

from tp.sentinel_live import archive_check


def test_archive_check_reports_per_pixel_differences_and_mask(monkeypatch):
    import tp.sentinel_live as live

    rng = np.random.default_rng(7)
    reference = rng.integers(3000, 8000, size=(4, 256, 256), dtype=np.uint16)
    received = reference.copy()
    received[0, 10, 20] += 1
    received[3, 200, 220] += 2
    calls = []

    def fetch(scene, row, col):
        calls.append((scene, row, col))
        return reference, {"scene": scene}

    monkeypatch.setattr(live, "fetch_chip_by_scene", fetch)
    result = archive_check(received, {"scene": "scene-id", "r0": 16, "c0": 32})
    assert calls == [("scene-id", 16, 32)]
    assert result["different_pixels"] == 2
    assert result["share"] == 2 / (256 * 256)
    assert result["mask"][10, 20] and result["mask"][200, 220]


@pytest.mark.network
def test_live_tunis_point_downloads_valid_chip_and_returns_finite_score():
    from tp.contract import validate_chip
    from tp.engine import TrustPipeline
    from tp.sentinel_live import AreaNotUsable, NetworkUnavailable, fetch_acquisition, list_acquisitions, read_chip_at

    try:
        acquisitions = list_acquisitions(10.18, 36.8, days=60, max_cloud=60, n=15)
        chip = metadata = None
        for row in acquisitions:
            try:
                chip, metadata = read_chip_at(fetch_acquisition(row['item_id']), 10.18, 36.8)
                break
            except AreaNotUsable:
                continue
        if chip is None:
            pytest.skip('No usable recent Sentinel-2 acquisition was found at the Tunis point.')
    except NetworkUnavailable as exc:
        pytest.skip(f'Planetary Computer is unavailable: {exc}')

    checked = validate_chip(chip, metadata['offset'], metadata)
    assert checked['ok'], checked['errors']
    pipeline = TrustPipeline()
    packet = pipeline.acquire(chip, metadata)
    result = pipeline.process(packet, cloud_ctx={'cloudy': False})
    assert np.isfinite(result['evidence']['score'])
