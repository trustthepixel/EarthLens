"""Tests for georeferenced chip exports."""

import numpy as np
import rasterio

from tp.data_io import export_geotiff


def test_geotiff_export_reopens_with_pixels_and_georeferencing(tmp_path):
    rng = np.random.default_rng(7)
    chip = rng.integers(3000, 8000, size=(4, 256, 256), dtype=np.uint16)
    path = tmp_path / "chip.tif"
    export_geotiff(chip, {"x0": 500000.0, "y0": 4200000.0, "epsg": 32632}, path)
    with rasterio.open(path) as dataset:
        assert dataset.count == 4
        assert np.array_equal(dataset.read(), chip)
        assert dataset.crs.to_epsg() == 32632
        assert tuple(dataset.descriptions) == ("B02", "B03", "B04", "B08")
