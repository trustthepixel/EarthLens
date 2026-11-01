"""Pure packet tampering scenarios shared by the direct runner and mitmproxy."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import serialization

from tp.attacks import ALL_FAMILIES, make_attack
from tp.provenance import Source, merkle_root_hex, pixel_bytes, sha256_hex, tile_hashes

MODES = ('passthrough', 'pixels', 'manifest_meta', 'manifest_rehash', 'resign', 'stolen_key', 'replay', 'strip')
PLACES_PATH = Path(__file__).with_name('places.json')
try:
    PLACE_CENTERS = json.loads(PLACES_PATH.read_text(encoding='utf-8'))
except (OSError, ValueError):
    PLACE_CENTERS = {}


def _distance_km(lon1, lat1, lon2, lat2):
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(value)))


def should_target(manifest, target='all', probability=1.0, rng=None, place_centers=None):
    if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        raise ValueError('Probability must be between 0 and 1.')
    if probability == 0:
        return False
    if target != 'all':
        places = place_centers if place_centers is not None else PLACE_CENTERS
        row = places.get(target)
        geo = manifest.get('geo') if isinstance(manifest, dict) else None
        if not row or not isinstance(geo, list) or len(geo) != 2:
            return False
        if _distance_km(float(geo[0]), float(geo[1]), float(row['lon']), float(row['lat'])) > 30:
            return False
    return probability >= 1 or float((rng or np.random.default_rng()).random()) < probability


def _clone(pkt):
    return {'pixels': np.asarray(pkt['pixels']).copy(), 'manifest': copy.deepcopy(pkt['manifest']), 'signature': pkt.get('signature')}


def tamper(pkt, mode, rng, family='inpaint_ns', severity='strong', stolen_key_path=None, loot=None,
           target='all', probability=1.0, place_centers=None):
    if mode not in MODES:
        raise ValueError(f'Unknown attack mode: {mode}')
    out = _clone(pkt)
    if mode != 'passthrough' and not should_target(out['manifest'], target, probability, rng, place_centers):
        return out
    if mode == 'passthrough':
        return out
    if mode == 'replay':
        cache = loot if loot is not None else {}
        if 'replay_packet' not in cache:
            cache['replay_packet'] = _clone(pkt)
            return out
        return _clone(cache['replay_packet'])
    if mode == 'manifest_meta':
        out['manifest']['scene'] = 'ALTERED_' + str(out['manifest'].get('scene', 'scene'))
        return out
    if mode in ('pixels', 'manifest_rehash', 'resign', 'stolen_key', 'strip'):
        if family not in (*ALL_FAMILIES, 'compound', 'compound_mixed'):
            raise ValueError(f'Unknown attack family: {family}')
        donor = np.roll(out['pixels'], 37, axis=2)
        edited, mask, record = make_attack(out['pixels'], donor, family, severity, rng, int(out['manifest']['offset']))
        out['pixels'] = edited
        if mode == 'manifest_rehash':
            leaves = tile_hashes(edited)
            out['manifest'].update({'sha256': sha256_hex(pixel_bytes(edited)), 'tile_hashes': leaves,
                                    'merkle_root': merkle_root_hex(leaves)})
        elif mode in ('resign', 'stolen_key'):
            if mode == 'resign':
                signer = Source(sensor_id=out['manifest']['sensor'])
            else:
                if not stolen_key_path:
                    raise ValueError('stolen_key_path is required for stolen_key mode.')
                private = serialization.load_pem_private_key(open(stolen_key_path, 'rb').read(), password=None)
                signer = Source(sensor_id=out['manifest']['sensor'], sk=private)
            signer.counter = max(int(out['manifest']['counter']), int((loot or {}).get('stolen_counter', 0)))
            out = signer.acquire(edited, {'date': out['manifest']['time_utc'], 'lon': out['manifest']['geo'][0],
                                          'lat': out['manifest']['geo'][1], 'scene': out['manifest']['scene'],
                                          'tile': out['manifest']['tile'], 'offset': out['manifest']['offset']})
            if loot is not None and mode == 'stolen_key':
                loot['stolen_counter'] = signer.counter
        elif mode == 'strip':
            out['signature'] = None
        if loot is not None:
            loot['truth'] = {'mask': mask, 'detail': record}
        return out
    raise ValueError(mode)
