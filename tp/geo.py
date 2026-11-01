"""Geographic reprojection and lightweight PNG overlay helpers."""

from __future__ import annotations

import base64
from io import BytesIO

import cv2
import numpy as np
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import calculate_default_transform, reproject

from tp.sentinel_live import SIZE, chip_footprint_4326


def warp_to_4326(array, meta):
    """Reproject an HxW or HxWxC chip array and return it with Leaflet bounds."""
    source = np.asarray(array)
    if source.ndim not in (2, 3):
        raise ValueError('array must have shape (height, width) or (height, width, channels).')
    if source.shape[:2] != (SIZE, SIZE):
        raise ValueError('array height and width must both be 256 pixels.')
    epsg = int(meta['epsg'])
    source_transform = Affine(10.0, 0.0, float(meta['x0']), 0.0, -10.0, float(meta['y0']))
    west, south = float(meta['x0']), float(meta['y0']) - SIZE * 10.0
    east, north = float(meta['x0']) + SIZE * 10.0, float(meta['y0'])
    footprint = chip_footprint_4326(meta)
    fallback_bounds = [
        [min(point[1] for point in footprint), min(point[0] for point in footprint)],
        [max(point[1] for point in footprint), max(point[0] for point in footprint)],
    ]
    try:
        dst_transform, dst_width, dst_height = calculate_default_transform(
            f'EPSG:{epsg}', 'EPSG:4326', SIZE, SIZE, west, south, east, north
        )
        if dst_width <= 0 or dst_height <= 0:
            raise ValueError('Reprojection produced an empty destination grid.')
        resampling = Resampling.nearest if np.issubdtype(source.dtype, np.integer) or source.dtype == np.bool_ else Resampling.bilinear
        if source.ndim == 2:
            destination = np.zeros((dst_height, dst_width), dtype=source.dtype)
            reproject(
                source=source,
                destination=destination,
                src_transform=source_transform,
                src_crs=f'EPSG:{epsg}',
                dst_transform=dst_transform,
                dst_crs='EPSG:4326',
                resampling=resampling,
            )
        else:
            destination = np.zeros((dst_height, dst_width, source.shape[2]), dtype=source.dtype)
            for index in range(source.shape[2]):
                reproject(
                    source=source[:, :, index],
                    destination=destination[:, :, index],
                    src_transform=source_transform,
                    src_crs=f'EPSG:{epsg}',
                    dst_transform=dst_transform,
                    dst_crs='EPSG:4326',
                    resampling=resampling,
                )
        dst_south = float(dst_transform.f + dst_height * dst_transform.e)
        dst_west = float(dst_transform.c)
        dst_north = float(dst_transform.f)
        dst_east = float(dst_transform.c + dst_width * dst_transform.a)
        return destination, [[dst_south, dst_west], [dst_north, dst_east]]
    except Exception:
        return source.copy(), fallback_bounds


def _to_png_data_uri(array, mode=None):
    image = Image.fromarray(np.asarray(array), mode=mode)
    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


def rgb_data_uri(rgb):
    """Encode an RGB uint8 image as a PNG data URI."""
    array = np.asarray(rgb)
    if array.ndim != 3 or array.shape[2] != 3:
        raise ValueError('RGB image must have shape (height, width, 3).')
    return _to_png_data_uri(np.clip(array, 0, 255).astype(np.uint8), mode='RGB')


def ndvi_data_uri(ndvi):
    """Encode NDVI using a red-yellow-green color ramp."""
    values = np.asarray(ndvi, dtype=np.float32)
    normalized = np.clip((values + 1.0) / 2.0, 0.0, 1.0)
    stops = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    colors = np.array([[215, 48, 39], [255, 255, 191], [26, 152, 80]], dtype=np.float32)
    output = np.stack(
        [np.interp(normalized, stops, colors[:, channel]) for channel in range(3)], axis=-1
    ).astype(np.uint8)
    return _to_png_data_uri(output, mode='RGB')


def heatmap_data_uri(probability, alpha_max=210):
    """Encode a probability map as inferno RGBA with probability-scaled alpha."""
    values = np.asarray(probability, dtype=np.float32)
    if values.ndim != 2:
        raise ValueError('Probability map must be two-dimensional.')
    gray = np.clip(values, 0.0, 1.0)
    bgr = cv2.applyColorMap(np.rint(gray * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    rgba = np.dstack((rgb, np.rint(gray * int(alpha_max)).astype(np.uint8)))
    return _to_png_data_uri(rgba, mode='RGBA')


def mask_contour_data_uri(mask, color=(255, 255, 255), thickness=2):
    """Encode a binary mask outline as a transparent PNG for map overlays."""
    binary = (np.asarray(mask) > 0).astype(np.uint8)
    if binary.ndim != 2:
        raise ValueError('Mask must be two-dimensional.')
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rgba = np.zeros((*binary.shape, 4), dtype=np.uint8)
    cv2.drawContours(rgba, contours, -1, (*map(int, color), 255), int(thickness))
    return _to_png_data_uri(rgba, mode='RGBA')
