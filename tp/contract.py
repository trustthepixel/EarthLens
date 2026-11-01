"""Input checks for Sentinel-2 chips and Planetary Computer items."""

from __future__ import annotations

from typing import Any

import numpy as np


def _check(name: str, passed: bool, detail: str) -> tuple[str, str, str]:
    return name, 'PASS' if passed else 'FAIL', detail


def validate_chip(pixels: Any, offset: Any, meta: dict[str, Any] | None = None, strict: bool = True) -> dict[str, Any]:
    """Validate a raw four-band uint16 chip against the model input contract."""
    del strict  # All listed contract violations are blocking in both modes.
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[tuple[str, str, str]] = []
    array = np.asarray(pixels)

    shape_ok = array.shape == (4, 256, 256)
    checks.append(_check('shape', shape_ok, f'Expected (4, 256, 256); received {array.shape}.'))
    if not shape_ok:
        errors.append('pixels must have shape (4, 256, 256).')
    dtype_ok = array.dtype == np.uint16
    checks.append(_check('dtype', dtype_ok, f'Expected uint16; received {array.dtype}.'))
    if not dtype_ok:
        errors.append('pixels must have dtype uint16.')
    offset_ok = not isinstance(offset, (bool, np.bool_)) and offset in (0, 1000)
    checks.append(_check('offset', bool(offset_ok), 'Offset must be 0 or 1000.'))
    if not offset_ok:
        errors.append('offset must be 0 or 1000.')

    if shape_ok and dtype_ok:
        zero_fraction = float(np.count_nonzero(array == 0) / array.size)
        zeros_ok = zero_fraction < 0.01
        checks.append(_check('zero_fraction', zeros_ok, f'Zero fraction is {zero_fraction:.6f}; it must be below 0.01.'))
        if not zeros_ok:
            errors.append('zero fraction must be below 1%.')
        constant_bands = [index for index, band in enumerate(array) if int(band.min()) == int(band.max())]
        bands_ok = not constant_bands
        checks.append(_check('constant_bands', bands_ok, 'No band is constant.' if bands_ok else f'Constant bands: {constant_bands}.'))
        if not bands_ok:
            errors.append('constant bands are invalid; each band must contain more than one value.')
        if offset_ok:
            reflectance_mean = float((array.astype(np.float32) - float(offset)) .mean() / 10000.0)
            reflectance_ok = 0.0 <= reflectance_mean <= 1.5
            checks.append(_check('mean_reflectance', reflectance_ok, f'Mean reflectance is {reflectance_mean:.6f}; expected [0, 1.5].'))
            if not reflectance_ok:
                errors.append('mean reflectance must be within [0, 1.5].')

    if meta is not None:
        epsg = meta.get('epsg')
        epsg_ok = isinstance(epsg, (int, np.integer)) and not isinstance(epsg, (bool, np.bool_)) and (32601 <= int(epsg) <= 32660 or 32701 <= int(epsg) <= 32760)
        checks.append(_check('epsg', epsg_ok, 'EPSG must be a UTM zone code.'))
        if not epsg_ok:
            errors.append('meta.epsg must be a UTM EPSG code (32601-32660 or 32701-32760).')
        product = str(meta.get('product', meta.get('product_type', meta.get('processing_level', '')))).upper()
        if product and 'L1C' in product:
            warnings.append('product is L1C; Sentinel-2 L2A is expected.')
        elif not product:
            warnings.append('product level is unknown.')
        if meta.get('baseline') in (None, '') and meta.get('s2:processing_baseline') in (None, ''):
            warnings.append('processing baseline is missing.')
        location = meta.get('region')
        lon, lat = meta.get('lon'), meta.get('lat')
        if location:
            in_domain = str(location).casefold() in {'tunis', 'beja', 'kairouan', 'sfax', 'tozeur', 'gabes', 'sicily'}
        elif lon is not None and lat is not None:
            in_domain = (8.0 <= float(lon) <= 11.4 and 33.3 <= float(lat) <= 37.3) or (12.0 <= float(lon) <= 16.5 and 35.0 <= float(lat) <= 39.0)
        else:
            in_domain = False
        if not in_domain:
            warnings.append('outside training domain')

    return {'ok': not errors, 'errors': errors, 'warnings': warnings, 'checks': checks}


def validate_stac_item(item: Any) -> dict[str, Any]:
    """Validate the collection and required assets of a STAC item."""
    if isinstance(item, dict):
        collection = item.get('collection_id') or item.get('collection')
        assets = item.get('assets', {}) or {}
    else:
        collection = getattr(item, 'collection_id', None) or getattr(item, 'collection', None)
        assets = getattr(item, 'assets', {}) or {}
    if hasattr(collection, 'id'):
        collection = collection.id
    errors = []
    if collection != 'sentinel-2-l2a':
        errors.append("STAC item collection must be 'sentinel-2-l2a'.")
    missing = [key for key in ('B02', 'B03', 'B04', 'B08', 'SCL') if key not in assets]
    if missing:
        errors.append('STAC item is missing assets: ' + ', '.join(missing) + '.')
    return {'ok': not errors, 'errors': errors}
