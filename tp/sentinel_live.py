"""Read recent Sentinel-2 L2A chips from Microsoft Planetary Computer."""

from __future__ import annotations

import datetime as dt
import os
import random
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from rasterio.env import set_proj_data_search_path
from rasterio.enums import Resampling
from rasterio.warp import transform as rio_transform, transform_bounds
from rasterio.windows import Window, bounds as window_bounds, from_bounds
from pystac_client.stac_api_io import StacApiIO

# Other GIS installations on Windows can leave a different PROJ database on
# GDAL's search path. Prefer the database shipped with this Rasterio runtime.
_proj_data = Path(rasterio.__file__).resolve().parent / 'proj_data'
if (_proj_data / 'proj.db').is_file():
    os.environ['PROJ_DATA'] = str(_proj_data)
    set_proj_data_search_path(str(_proj_data))

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
BANDS = ['B02', 'B03', 'B04', 'B08']
SIZE = 256
BAD_SCL = [0, 1, 3, 8, 9, 10, 11]
CLEAN_BAD_MAX = 0.02
HARD_BAD_MIN, HARD_BAD_MAX = 0.05, 0.60
HAZE_B02, HAZE_CLEAN_MAX, HAZE_HARD_MIN = 0.25, 0.02, 0.05

REGIONS = {
    'Tunis': [9.9, 36.6, 10.5, 37.1],
    'Beja': [9.0, 36.6, 9.6, 37.1],
    'Kairouan': [9.8, 35.4, 10.4, 35.9],
    'Sfax': [10.4, 34.5, 11.0, 35.0],
    'Tozeur': [8.0, 33.7, 8.5, 34.1],
    'Gabes': [9.9, 33.7, 10.4, 34.1],
    'Sicily': [14.0, 37.3, 14.6, 37.8],
}
REGION_NOTES = {'Sicily': 'foreign area, used for validation'}


class NetworkUnavailable(RuntimeError):
    """Raised when Planetary Computer data cannot be read after retries."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AreaNotUsable(ValueError):
    """Raised when a requested map point cannot provide a complete chip."""


def _is_status(exc: Exception, status: int) -> bool:
    response = getattr(exc, 'response', None)
    return (
        getattr(response, 'status_code', None) == status
        or getattr(exc, 'status_code', None) == status
        or f'{status} ' in str(exc)
        or f'HTTP {status}' in str(exc).upper()
    )


def with_retry(operation: Callable[[], Any], item: Any = None, attempts: int = 3) -> Any:
    """Retry an STAC or GDAL network operation, refreshing signed URLs on 403."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last = exc
            if _is_status(exc, 403) and item is not None:
                try:
                    _original_sign(item)
                except Exception:
                    pass
            if attempt + 1 >= attempts:
                break
            delay = 2 ** attempt
            if _is_status(exc, 429):
                retry_after = getattr(getattr(exc, 'response', None), 'headers', {}).get('Retry-After')
                try:
                    delay = max(delay, float(retry_after))
                except (TypeError, ValueError):
                    pass
            time.sleep(delay)
    status_code = next((code for code in (403, 429) if last is not None and _is_status(last, code)), None)
    suffix = f' HTTP {status_code}.' if status_code is not None else '.'
    raise NetworkUnavailable(
        f'Network read failed after {attempts} attempts ({type(last).__name__}).{suffix}',
        status_code=status_code,
    ) from last


_original_sign = pc.sign
_current_item = None


def _retry_sign(item):
    global _current_item
    _current_item = item
    return with_retry(lambda: _original_sign(item), item)


class _RetryDataset:
    """Delegate dataset access and retry remote raster reads."""

    def __init__(self, dataset, item=None):
        object.__setattr__(self, '_dataset', dataset)
        object.__setattr__(self, '_item', item)

    def __setattr__(self, name, value):
        if name in {'_dataset', '_item'}:
            object.__setattr__(self, name, value)
        else:
            setattr(self._dataset, name, value)

    def __getattr__(self, name):
        return getattr(self._dataset, name)

    def __enter__(self):
        self._dataset.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._dataset.__exit__(exc_type, exc_value, traceback)

    def read(self, *args, **kwargs):
        return with_retry(lambda: self._dataset.read(*args, **kwargs), self._item)


_original_rasterio_open = rasterio.open


def _retry_rasterio_open(*args, **kwargs):
    dataset = with_retry(lambda: _original_rasterio_open(*args, **kwargs), _current_item)
    return _RetryDataset(dataset, _current_item)


# Keep the notebook's `pc.sign` and `rasterio.open(...).read(...)` calls verbatim.
pc.sign = _retry_sign
rasterio.open = _retry_rasterio_open


def season_of(date_str):
    m = int(str(date_str)[5:7])
    return 'DJF' if m in (12, 1, 2) else 'MAM' if m in (3, 4, 5) else 'JJA' if m in (6, 7, 8) else 'SON'

def baseline_offset(props):
    # depuis la baseline 04.00 (25 janvier 2022), les valeurs numériques sont décalées de +1000
    try:
        return 1000 if float(props.get('s2:processing_baseline', '0')) >= 4.0 else 0
    except (TypeError, ValueError):
        return 0

def aoi_window(src, bbox):
    l, b, r, t = transform_bounds('EPSG:4326', src.crs, *bbox)
    w = from_bounds(l, b, r, t, src.transform)
    r0, c0 = max(int(w.row_off), 0), max(int(w.col_off), 0)
    r1 = min(int(w.row_off + w.height), src.height)
    c1 = min(int(w.col_off + w.width), src.width)
    return r0, r1, c0, c1

def classify_chip(bad, haze):
    if bad <= CLEAN_BAD_MAX and haze <= HAZE_CLEAN_MAX:
        return 'clean'
    if HARD_BAD_MIN <= bad <= HARD_BAD_MAX or HAZE_HARD_MIN <= haze <= HARD_BAD_MAX:
        return 'hard'
    return 'ambiguous'

def chip_georef(src, r0, c0, size=SIZE):
    tr = src.window_transform(Window(c0, r0, size, size))
    x0, y0 = float(tr.c), float(tr.f)
    xc, yc = x0 + size * 5.0, y0 - size * 5.0                     # centre (pixels de 10 m)
    lon, lat = rio_transform(src.crs, 'EPSG:4326', [xc], [yc])
    return dict(epsg=int(src.crs.to_epsg() or 0), x0=x0, y0=y0, lon=float(lon[0]), lat=float(lat[0]))

def sample_scene(region, role, bbox, item, want, n, tries_factor=12, rnd=None):
    # lit au plus n chips de la classe `want` ('clean' ou 'hard') dans la scène, sans chevauchement
    rnd = rnd or random
    item = pc.sign(item)                                       # jeton d'accès temporaire
    srcs = {b: rasterio.open(item.assets[b].href) for b in BANDS}
    scl = rasterio.open(item.assets['SCL'].href)               # 20 m
    off = baseline_offset(item.properties)
    chips, meta, placed, counts = [], [], [], {'clean': 0, 'hard': 0, 'ambiguous': 0, 'vide': 0}
    try:
        r0a, r1a, c0a, c1a = aoi_window(srcs['B02'], bbox)
        if r1a - r0a <= SIZE or c1a - c0a <= SIZE:
            return [], [], counts
        tries = 0
        while len(chips) < n and tries < n * tries_factor:
            tries += 1
            r0 = rnd.randrange(r0a, r1a - SIZE); r0 -= r0 % 2
            c0 = rnd.randrange(c0a, c1a - SIZE); c0 -= c0 % 2
            if any(abs(r0 - r) < SIZE and abs(c0 - c) < SIZE for r, c in placed):
                continue
            s = scl.read(1, window=Window(c0 // 2, r0 // 2, SIZE // 2, SIZE // 2),
                         out_shape=(SIZE, SIZE), resampling=Resampling.nearest)
            bad = float(np.isin(s, BAD_SCL).mean())
            if bad > HARD_BAD_MAX or (want == 'clean' and bad > HARD_BAD_MIN):
                counts['ambiguous'] += 1; continue
            x = np.stack([srcs[b].read(1, window=Window(c0, r0, SIZE, SIZE)) for b in BANDS])
            if (x == 0).mean() > 0.01:
                counts['vide'] += 1; continue
            haze = float((((x[0].astype(np.float32) - off) / 10000.0) > HAZE_B02).mean())
            kind = classify_chip(bad, haze)
            counts[kind] += 1
            if kind != want:
                continue
            chips.append(x.astype(np.uint16)); placed.append((r0, c0))
            meta.append(dict(region=region, role=role, scene=item.id, tile=item.properties['s2:mgrs_tile'],
                             date=item.properties['datetime'][:10], season=season_of(item.properties['datetime'][:10]),
                             cloud_scene=float(item.properties.get('eo:cloud_cover', np.nan)),
                             baseline=item.properties.get('s2:processing_baseline'), offset=off, r0=r0, c0=c0,
                             bad_frac=round(bad, 4), haze_frac=round(haze, 4), hard=(kind == 'hard'),
                             **chip_georef(srcs['B02'], r0, c0)))
    finally:
        for s_ in srcs.values():
            s_.close()
        scl.close()
    return chips, meta, counts


def latest_items(bbox, days=45, max_cloud=30, n=10):
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days)
    def search():
        cat = pystac_client.Client.open(
            STAC, modifier=pc.sign_inplace, stac_io=StacApiIO(timeout=10, max_retries=0)
        )
        results = cat.search(collections=['sentinel-2-l2a'], bbox=bbox,
                             datetime=f'{start:%Y-%m-%d}/{end:%Y-%m-%d}',
                             query={'eo:cloud_cover': {'lt': max_cloud}},
                             sortby=[{'field': 'properties.datetime', 'direction': 'desc'}], max_items=n)
        return list(results.items())
    return with_retry(search)


def latest_chip(region, want='clean', days=45, max_cloud=30):
    """Return the latest usable chip, metadata, and item, or three None values."""
    bbox = REGIONS[region]
    with rasterio.Env(GDAL_HTTP_TIMEOUT=30, GDAL_HTTP_MAX_RETRY=0, GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
        for item in latest_items(bbox, days, max_cloud):
            chips, metas, _ = sample_scene(region, 'live', bbox, item, want, 1, tries_factor=40, rnd=random.Random())
            if chips:
                return chips[0], metas[0], item
    return None, None, None


def cloud_context(meta: dict[str, Any]) -> dict[str, Any]:
    bad = float(meta.get('bad_frac', 0.0))
    haze = float(meta.get('haze_frac', 0.0))
    return {'bad_frac': bad, 'haze_frac': haze, 'cloudy': bool(bad > 0.05 or haze > 0.05)}


def _open_scene(item):
    signed = pc.sign(item)
    sources = {band: with_retry(lambda band=band: rasterio.open(signed.assets[band].href), signed) for band in BANDS}
    scl = with_retry(lambda: rasterio.open(signed.assets['SCL'].href), signed)
    return signed, sources, scl


def fetch_chip_by_scene(scene_id, r0, c0):
    """Read the same chip window from a previously identified STAC scene."""
    def find_scene():
        catalog = pystac_client.Client.open(
            STAC, modifier=pc.sign_inplace, stac_io=StacApiIO(timeout=10, max_retries=0)
        )
        return list(catalog.search(collections=['sentinel-2-l2a'], ids=[scene_id], max_items=1).items())
    matches = with_retry(find_scene)
    if not matches:
        raise NetworkUnavailable(f'Scene {scene_id} was not found in the STAC search results.')
    item, sources, scl = _open_scene(matches[0])
    try:
        pixels = np.stack([with_retry(lambda band=band: sources[band].read(1, window=Window(c0, r0, SIZE, SIZE)), item) for band in BANDS]).astype(np.uint16)
        meta = dict(scene=item.id, date=item.properties['datetime'][:10], offset=baseline_offset(item.properties), r0=int(r0), c0=int(c0), **chip_georef(sources['B02'], r0, c0))
        return pixels, meta
    finally:
        for src in sources.values(): src.close()
        scl.close()


def archive_check(pixels, meta):
    """Compare a chip DN-by-DN with the same scene window in the live archive."""
    required = ('scene', 'r0', 'c0')
    missing = [key for key in required if meta.get(key) in (None, '')]
    if missing:
        raise ValueError('Archive comparison requires metadata fields: ' + ', '.join(missing) + '.')
    archive_pixels, archive_meta = fetch_chip_by_scene(meta['scene'], int(meta['r0']), int(meta['c0']))
    observed = np.asarray(pixels)
    reference = np.asarray(archive_pixels)
    if observed.shape != reference.shape:
        raise ValueError(f'Archive chip shape mismatch: received {observed.shape}, archive {reference.shape}.')
    if observed.dtype != reference.dtype:
        raise ValueError(f'Archive chip dtype mismatch: received {observed.dtype}, archive {reference.dtype}.')
    mask = np.any(observed != reference, axis=0)
    share = float(mask.mean())
    return {
        'share': share,
        'mask': mask,
        'different_pixels': int(mask.sum()),
        'total_pixels': int(mask.size),
        'archive_meta': archive_meta,
    }


def read_grid(item, bbox, n=3, anchor=None):
    """Read adjacent chip windows and per-cell doubtful SCL fractions."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError('n must be a positive integer.')
    item, sources, scl = _open_scene(item)
    try:
        if anchor is None:
            r0a, _, c0a, _ = aoi_window(sources['B02'], bbox)
            r0, c0 = r0a - r0a % 2, c0a - c0a % 2
        else:
            r0, c0 = map(int, anchor)
        chips, metas, cloud = [], [], []
        for i in range(n):
            for j in range(n):
                row, col = r0 + i * SIZE, c0 + j * SIZE
                pixels = np.stack([with_retry(lambda band=band: sources[band].read(1, window=Window(col, row, SIZE, SIZE)), item) for band in BANDS]).astype(np.uint16)
                scl_values = with_retry(lambda: scl.read(1, window=Window(col // 2, row // 2, SIZE // 2, SIZE // 2), out_shape=(SIZE, SIZE), resampling=Resampling.nearest), item)
                bad = float(np.isin(scl_values, BAD_SCL).mean())
                off = baseline_offset(item.properties)
                haze = float((((pixels[0].astype(np.float32) - off) / 10000.0) > HAZE_B02).mean())
                meta = dict(scene=item.id, date=item.properties['datetime'][:10], offset=off, r0=row, c0=col, bad_frac=bad, haze_frac=haze, **chip_georef(sources['B02'], row, col))
                chips.append(pixels); metas.append(meta); cloud.append(cloud_context(meta))
        return np.stack(chips), metas, cloud
    finally:
        for src in sources.values(): src.close()
        scl.close()


def list_acquisitions(lon, lat, days=60, max_cloud=60, n=15):
    """List recent Sentinel-2 acquisitions intersecting a map point."""
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=int(days))

    def search():
        catalog = pystac_client.Client.open(
            STAC, modifier=pc.sign_inplace, stac_io=StacApiIO(timeout=10, max_retries=0)
        )
        results = catalog.search(
            collections=['sentinel-2-l2a'],
            intersects={'type': 'Point', 'coordinates': [float(lon), float(lat)]},
            datetime=f'{start:%Y-%m-%d}/{end:%Y-%m-%d}',
            query={'eo:cloud_cover': {'lt': float(max_cloud)}},
            sortby=[{'field': 'properties.datetime', 'direction': 'desc'}],
            max_items=int(n),
        )
        items = list(results.items())
        items.sort(key=lambda item: str(item.properties.get('datetime', '')), reverse=True)
        return [
            {
                'item_id': item.id,
                'date': str(item.properties.get('datetime', ''))[:10],
                'cloud_cover': float(item.properties.get('eo:cloud_cover') or 0.0),
                'tile': str(item.properties.get('s2:mgrs_tile', '')),
                'baseline': item.properties.get('s2:processing_baseline'),
            }
            for item in items
        ]

    return with_retry(search)


def fetch_acquisition(item_id):
    """Fetch one complete STAC item selected from a cached acquisition list."""
    def fetch():
        catalog = pystac_client.Client.open(
            STAC, modifier=pc.sign_inplace, stac_io=StacApiIO(timeout=10, max_retries=0)
        )
        return list(catalog.search(collections=['sentinel-2-l2a'], ids=[str(item_id)], max_items=1).items())

    matches = with_retry(fetch)
    if not matches:
        raise NetworkUnavailable('The selected Sentinel-2 acquisition is no longer available.')
    return matches[0]


def _region_at_point(lon, lat):
    for name, (west, south, east, north) in REGIONS.items():
        if west - 0.5 <= lon <= east + 0.5 and south - 0.5 <= lat <= north + 0.5:
            return name
    return 'Outside training domain'


def read_chip_at(item, lon, lat):
    """Read a centered, clamped 256-pixel chip and its Sentinel metadata."""
    lon, lat = float(lon), float(lat)
    with rasterio.Env(GDAL_HTTP_TIMEOUT=30, GDAL_HTTP_MAX_RETRY=0, GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR'):
        signed, sources, scl = _open_scene(item)
        try:
            blue = sources['B02']
            x_values, y_values = rio_transform('EPSG:4326', blue.crs, [lon], [lat])
            row, col = blue.index(x_values[0], y_values[0])
            if blue.height < SIZE or blue.width < SIZE:
                raise AreaNotUsable('The scene is smaller than the required 256 by 256 pixel area.')
            r0 = max(0, min(int(row) - SIZE // 2, int(blue.height) - SIZE))
            c0 = max(0, min(int(col) - SIZE // 2, int(blue.width) - SIZE))
            r0 -= r0 % 2
            c0 -= c0 % 2
            if r0 + SIZE > blue.height or c0 + SIZE > blue.width:
                raise AreaNotUsable('The requested area falls outside the image swath.')

            window = Window(c0, r0, SIZE, SIZE)
            if any(str(source.dtypes[0]) != 'uint16' for source in sources.values()):
                raise AreaNotUsable('Sentinel image bands must contain uint16 digital numbers.')
            bands = [
                with_retry(lambda source=sources[band]: source.read(1, window=window), signed)
                for band in BANDS
            ]
            chip = np.stack(bands)
            if chip.shape != (4, SIZE, SIZE):
                raise AreaNotUsable('The image swath does not contain a complete 256 by 256 pixel area.')
            chip = chip.astype(np.uint16, copy=False)
            if float(np.count_nonzero(chip == 0) / chip.size) > 0.01:
                raise AreaNotUsable('The selected area is outside the usable image swath.')

            left, bottom, right, top = window_bounds(window, blue.transform)
            scl_window = from_bounds(left, bottom, right, top, scl.transform)
            scl_values = with_retry(
                lambda: scl.read(
                    1,
                    window=scl_window,
                    out_shape=(SIZE, SIZE),
                    resampling=Resampling.nearest,
                ),
                signed,
            )
            bad_frac = float(np.isin(scl_values, BAD_SCL).mean())
            offset = baseline_offset(signed.properties)
            haze_frac = float((((chip[0].astype(np.float32) - offset) / 10000.0) > HAZE_B02).mean())
            region = _region_at_point(lon, lat)
            meta = {
                'date': str(signed.properties['datetime'])[:10],
                'lon': lon,
                'lat': lat,
                'scene': str(signed.id),
                'tile': str(signed.properties.get('s2:mgrs_tile', '')),
                'r0': int(r0),
                'c0': int(c0),
                'offset': int(offset),
                'region': region,
                'place': region,
                'epsg': int(blue.crs.to_epsg() or 0),
                'x0': float(blue.window_transform(window).c),
                'y0': float(blue.window_transform(window).f),
                'bad_frac': bad_frac,
                'haze_frac': haze_frac,
            }
            return chip, meta
        finally:
            for source in sources.values():
                source.close()
            scl.close()


def chip_footprint_4326(meta):
    """Return chip corner coordinates as (longitude, latitude) pairs."""
    x0, y0 = float(meta['x0']), float(meta['y0'])
    size_m = SIZE * 10.0
    xs = [x0, x0 + size_m, x0 + size_m, x0]
    ys = [y0, y0, y0 - size_m, y0 - size_m]
    longitudes, latitudes = rio_transform(f"EPSG:{int(meta['epsg'])}", 'EPSG:4326', xs, ys)
    return [(float(x), float(y)) for x, y in zip(longitudes, latitudes)]


def preview_footprint(lon, lat):
    """Return an approximate 2.56 km square as (longitude, latitude) corners."""
    lon, lat = float(lon), float(lat)
    half_side = 1280.0
    dlat = half_side / 111320.0
    cosine = max(abs(float(np.cos(np.deg2rad(lat)))), 1e-6)
    dlon = half_side / (111320.0 * cosine)
    west, east = lon - dlon, lon + dlon
    south, north = lat - dlat, lat + dlat
    return [(west, south), (east, south), (east, north), (west, north)]
