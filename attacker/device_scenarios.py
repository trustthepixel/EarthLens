"""Apply the existing attack modes to signed TPX2 binary packets."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import serialization

from attacker.scenarios import MODES, PLACES_PATH, should_target, tamper
from tp.device_protocol import (
    HEADER_LEN,
    PACKET_LEN,
    SIG_LEN,
    DeviceSource,
    parse_packet,
    pixel_bytes_le,
)


def tamper_device_packet(
    data: bytes,
    mode: str,
    rng: np.random.Generator,
    family: str = 'inpaint_ns',
    severity: str = 'strong',
    stolen_key_path: str | Path | None = None,
    loot: dict | None = None,
    target: str = 'all',
    probability: float = 1.0,
    place_centers: dict | None = None,
) -> bytes:
    """Return a tampered TPX2 packet while leaving the input bytes untouched."""
    if mode not in MODES:
        raise ValueError(f'Unknown attack mode: {mode}')
    packet = bytes(data)
    if len(packet) != PACKET_LEN:
        raise ValueError('Invalid TPX2 packet length.')
    if mode == 'passthrough':
        return packet

    parsed = parse_packet(packet)
    manifest = parsed['manifest']
    if not should_target(manifest, target, probability, rng, place_centers):
        return packet

    header = packet[:HEADER_LEN]
    signature = packet[HEADER_LEN:HEADER_LEN + SIG_LEN]
    pixels = parsed['pixels']

    if mode == 'replay':
        cache = loot if loot is not None else {}
        if 'device_replay_packet' not in cache:
            cache['device_replay_packet'] = packet
            return packet
        return bytes(cache['device_replay_packet'])

    if mode == 'manifest_meta':
        changed_header = bytearray(header)
        changed_header[109] ^= 1  # Alter a signed tile byte; the signature will no longer match.
        return bytes(changed_header) + signature + packet[HEADER_LEN + SIG_LEN:]

    pixel_mode = 'pixels' if mode in {'pixels', 'manifest_rehash', 'resign', 'stolen_key', 'strip'} else mode
    altered = tamper(
        parsed, pixel_mode, rng, family, severity, target='all', probability=1.0,
        place_centers=place_centers,
    )
    edited_pixels = np.asarray(altered['pixels'], dtype=np.uint16)
    edited_bytes = pixel_bytes_le(edited_pixels)

    if mode == 'pixels':
        return header + signature + edited_bytes
    if mode == 'manifest_rehash':
        changed_header = bytearray(header)
        changed_header[48:80] = hashlib.sha256(edited_bytes).digest()
        return bytes(changed_header) + signature + edited_bytes
    if mode == 'strip':
        return header + bytes(SIG_LEN) + edited_bytes

    if mode in {'resign', 'stolen_key'}:
        if mode == 'stolen_key':
            if not stolen_key_path:
                raise ValueError('stolen_key_path is required for stolen_key mode.')
            private_key = serialization.load_pem_private_key(
                Path(stolen_key_path).read_bytes(), password=None
            )
            source = DeviceSource(private_key)
            previous_stolen_counter = int((loot or {}).get('device_stolen_counter', 0))
            source.counter = max(int(manifest['counter']) - 1, previous_stolen_counter)
        else:
            source = DeviceSource()
            source.counter = int(manifest['counter']) - 1
        source.head = str(manifest['prev_hash'])
        meta = {
            'date': manifest['time_utc'],
            'lon': manifest['geo'][0],
            'lat': manifest['geo'][1],
            'tile': manifest['tile'],
            'offset': manifest['offset'],
            'r0': manifest['window'][0],
            'c0': manifest['window'][1],
        }
        forged = source.acquire(edited_pixels, meta)
        if mode == 'stolen_key' and loot is not None:
            loot['device_stolen_counter'] = source.counter
        return forged

    raise ValueError(f'Unsupported TPX2 attack mode: {mode}')
