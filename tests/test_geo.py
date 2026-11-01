"""Tests for chip footprint geometry, reprojection, and preview helpers."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from tp.geo import heatmap_data_uri, ndvi_data_uri, rgb_data_uri, warp_to_4326
from tp.sentinel_live import chip_footprint_4326, preview_footprint


def test_runtime_uses_rasterio_bundled_proj_database():
    bundled_proj = Path(rasterio.__file__).resolve().parent / 'proj_data'
    assert (bundled_proj / 'proj.db').is_file()
    assert Path(os.environ['PROJ_DATA']).resolve() == bundled_proj.resolve()


def test_preview_footprint_is_fixed_size_near_the_selected_point():
    lon, lat = 10.18, 36.8
    corners = preview_footprint(lon, lat)
    assert len(corners) == 4
    assert abs((corners[1][0] - corners[0][0]) - 2560 / (111320 * np.cos(np.deg2rad(lat)))) < 1e-10
    assert abs((corners[2][1] - corners[1][1]) - 2560 / 111320) < 1e-10


def test_sample_chip_footprint_center_matches_metadata_location():
    sample_files = sorted(Path('samples').glob('chip_*.json'))
    assert sample_files
    metadata = json.loads(sample_files[0].read_text(encoding='utf-8'))
    corners = chip_footprint_4326(metadata)
    center_lon = (corners[0][0] + corners[1][0]) / 2
    center_lat = (corners[0][1] + corners[2][1]) / 2
    distance = np.hypot((center_lon - metadata['lon']) * 111320 * np.cos(np.deg2rad(center_lat)),
                        (center_lat - metadata['lat']) * 111320)
    assert distance < 5


def test_warp_to_4326_reprojects_synthetic_array_and_returns_bounds():
    meta = {'epsg': 32632, 'x0': 500000.0, 'y0': 4100000.0}
    array = np.arange(256 * 256, dtype=np.float32).reshape(256, 256)
    warped, bounds = warp_to_4326(array, meta)
    assert warped.ndim == 2
    assert warped.size > 0
    assert len(bounds) == 2 and len(bounds[0]) == 2
    assert bounds[0][0] < bounds[1][0] and bounds[0][1] < bounds[1][1]


def test_overlay_helpers_emit_png_data_uris():
    assert rgb_data_uri(np.zeros((16, 16, 3), dtype=np.uint8)).startswith('data:image/png;base64,')
    assert ndvi_data_uri(np.zeros((16, 16), dtype=np.float32)).startswith('data:image/png;base64,')
    assert heatmap_data_uri(np.ones((16, 16), dtype=np.float32)).startswith('data:image/png;base64,')


class _MemoryRaster:
    def __init__(self, value, width=512, height=512, crs=None, transform=None):
        self.value = value
        self.width = width
        self.height = height
        self.dtypes = ('uint16',)
        self.crs = crs or CRS.from_epsg(32632)
        self.transform = transform or Affine(10, 0, 500000, 0, -10, 4100000)
        self.windows = []
        self.closed = False

    def index(self, x, y):
        return (0, 0)

    def read(self, band, window=None, out_shape=None, resampling=None):
        self.windows.append(window)
        shape = tuple(out_shape) if out_shape is not None else (int(window.height), int(window.width))
        return np.full(shape, self.value, dtype=np.uint16)

    def window_transform(self, window):
        return self.transform @ Affine.translation(window.col_off, window.row_off)

    def close(self):
        self.closed = True


def test_read_chip_at_clamps_centered_window_inside_raster(monkeypatch):
    import tp.sentinel_live as live

    sources = {band: _MemoryRaster(4500 + index * 100) for index, band in enumerate(live.BANDS)}
    scl = _MemoryRaster(4, transform=Affine(20, 0, 500000, 0, -20, 4100000))
    item = type('Item', (), {'id': 'scene-1', 'properties': {
        'datetime': '2026-10-26T10:00:00Z', 's2:mgrs_tile': '32SNA', 's2:processing_baseline': '05.00'
    }})()
    monkeypatch.setattr(live, '_open_scene', lambda _item: (item, sources, scl))
    chip, meta = live.read_chip_at(item, 10.18, 36.8)

    assert chip.shape == (4, 256, 256) and chip.dtype == np.uint16
    assert meta['r0'] == 0 and meta['c0'] == 0
    assert meta['offset'] == 1000
    assert set(meta) == {
        'date', 'lon', 'lat', 'scene', 'tile', 'r0', 'c0', 'offset', 'region', 'place',
        'epsg', 'x0', 'y0', 'bad_frac', 'haze_frac'
    }
    assert all(src.windows[0].row_off == 0 and src.windows[0].col_off == 0 for src in sources.values())
    assert all(src.closed for src in sources.values()) and scl.closed


def test_read_chip_at_rejects_windows_with_more_than_one_percent_zeros(monkeypatch):
    import tp.sentinel_live as live

    sources = {band: _MemoryRaster(0 if band == 'B02' else 4500 + index * 100)
               for index, band in enumerate(live.BANDS)}
    scl = _MemoryRaster(4, transform=Affine(20, 0, 500000, 0, -20, 4100000))
    item = type('Item', (), {'id': 'scene-1', 'properties': {
        'datetime': '2026-10-26T10:00:00Z', 's2:mgrs_tile': '32SNA', 's2:processing_baseline': '05.00'
    }})()
    monkeypatch.setattr(live, '_open_scene', lambda _item: (item, sources, scl))
    with pytest.raises(live.AreaNotUsable, match='outside the usable image swath'):
        live.read_chip_at(item, 10.18, 36.8)


def test_list_acquisitions_uses_point_filter_and_sorts_latest_first(monkeypatch):
    import tp.sentinel_live as live

    class Item:
        def __init__(self, item_id, date):
            self.id = item_id
            self.properties = {
                'datetime': date,
                'eo:cloud_cover': 3,
                's2:mgrs_tile': '32SNA',
                's2:processing_baseline': '05.00',
            }

    class Search:
        def items(self):
            return [Item('older', '2026-10-20T00:00:00Z'), Item('latest', '2026-10-26T00:00:00Z')]

    class Catalog:
        def search(self, **kwargs):
            assert kwargs['collections'] == ['sentinel-2-l2a']
            assert kwargs['intersects'] == {'type': 'Point', 'coordinates': [10.18, 36.8]}
            assert kwargs['max_items'] == 15
            return Search()

    monkeypatch.setattr(live.pystac_client.Client, 'open', lambda *args, **kwargs: Catalog())
    rows = live.list_acquisitions(10.18, 36.8)
    assert [row['item_id'] for row in rows] == ['latest', 'older']
    assert set(rows[0]) == {'item_id', 'date', 'cloud_cover', 'tile', 'baseline'}
