"""TPX2: a compact binary packet format that a microcontroller can produce.

The legacy packet signs a canonical JSON manifest, which is hard to reproduce byte for byte on a
small board. TPX2 signs a fixed-size binary header instead, so firmware only has to fill a struct,
hash the pixels and sign 121 bytes.

Packet layout (all integers little-endian)::

    header (121 bytes) | signature (64 bytes, Ed25519 over the header) | pixels (4*256*256 uint16)

Header layout::

    offset size field
         0    4 magic            b'TPX2'
         4    8 key_id           first 8 bytes of SHA-256 of the raw Ed25519 public key
        12    4 counter          u32, starts at 1 and increases by 1 per packet
        16   32 prev_hash        link hash of the previous packet (zeros for the first packet)
        48   32 pixel_sha256     SHA-256 of the pixel bytes (little-endian uint16, C order)
        80    2 channels         u16 (4)
        82    2 height           u16 (256)
        84    2 width            u16 (256)
        86    2 offset           u16, reflectance offset (0 or 1000)
        88    4 lon_e6           i32, longitude in micro-degrees
        92    4 lat_e6           i32, latitude in micro-degrees
        96    4 date             u32, acquisition date as YYYYMMDD
       100    8 nonce            random bytes
       108    1 sensor           u8 (1 = SENTINEL-2-L2A)
       109    8 tile             ASCII, zero padded
       117    2 window_r0        u16
       119    2 window_c0        u16

The link hash of a packet is SHA-256(header || signature). The next packet stores it as
``prev_hash``, which chains packets together exactly like the legacy JSON chain.
"""
import datetime as _dt
import hashlib
import os
import struct

import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tp.chain import GENESIS, ChainedGround

MAGIC = b'TPX2'
HEADER_FMT = '<4s8sI32s32sHHHHiiI8sB8sHH'
HEADER_LEN = struct.calcsize(HEADER_FMT)
SIG_LEN = 64
SHAPE = (4, 256, 256)
PIXEL_LEN = SHAPE[0] * SHAPE[1] * SHAPE[2] * 2
PACKET_LEN = HEADER_LEN + SIG_LEN + PIXEL_LEN
SENSORS = {1: 'SENTINEL-2-L2A'}
FORMAT_NAME = 'TPX2'

assert HEADER_LEN == 121


def pixel_bytes_le(arr):
    """Pixel bytes as the device hashes them: little-endian uint16, C order."""
    return np.ascontiguousarray(arr, dtype='<u2').tobytes()


def key_id_bytes(public_key):
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).digest()[:8]


def link_hash_v2(header, signature):
    return hashlib.sha256(header + signature).hexdigest()


def pack_header(key_id, counter, prev_hash_hex, pixel_sha_hex, offset, lon, lat, date, nonce, tile,
                window=(0, 0), sensor=1, shape=SHAPE):
    """Build the 121-byte header. ``date`` is an ISO string or an int YYYYMMDD."""
    if isinstance(date, str):
        date = int(date[:10].replace('-', ''))
    return struct.pack(HEADER_FMT, MAGIC, key_id, counter, bytes.fromhex(prev_hash_hex), bytes.fromhex(pixel_sha_hex),
                       shape[0], shape[1], shape[2], int(offset), int(round(lon * 1e6)), int(round(lat * 1e6)),
                       int(date), nonce, sensor, str(tile).encode('ascii')[:8].ljust(8, b'\0'),
                       int(window[0]), int(window[1]))


def unpack_header(header):
    """Decode a header into plain Python fields. Raises ValueError on a malformed header."""
    if len(header) != HEADER_LEN:
        raise ValueError('wrong header length')
    (magic, key_id, counter, prev_hash, pixel_sha, channels, height, width, offset, lon_e6, lat_e6, date, nonce,
     sensor, tile, r0, c0) = struct.unpack(HEADER_FMT, header)
    if magic != MAGIC:
        raise ValueError('bad magic')
    text = f'{date:08d}'
    try:
        _dt.date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError as exc:
        raise ValueError('invalid date') from exc
    return {
        'key_id': key_id.hex(), 'counter': counter, 'prev_hash': prev_hash.hex(), 'sha256': pixel_sha.hex(),
        'shape': [channels, height, width], 'offset': offset, 'geo': [lon_e6 / 1e6, lat_e6 / 1e6],
        'time_utc': f'{text[:4]}-{text[4:6]}-{text[6:]}', 'nonce': nonce.hex(), 'sensor_code': sensor,
        'sensor': SENSORS.get(sensor, f'UNKNOWN-{sensor}'), 'tile': tile.rstrip(b'\0').decode('ascii', 'replace'),
        'window': [r0, c0],
    }


def manifest_from_header(header):
    """Legacy-shaped manifest dictionary derived from a header, for the engine, API and dashboard."""
    fields = unpack_header(header)
    fields.update({'format': FORMAT_NAME, 'dtype': 'uint16', 'header_hex': header.hex(),
                   'scene': f"{fields['tile']}_{fields['time_utc']}"})
    return fields


def parse_packet(data):
    """Split raw packet bytes into the ``pkg`` dictionary used by the trust pipeline."""
    if len(data) != PACKET_LEN:
        raise ValueError(f'wrong packet length {len(data)}')
    header = data[:HEADER_LEN]
    signature_bytes = data[HEADER_LEN:HEADER_LEN + SIG_LEN]
    # The fixed-size TPX2 signature field is all zeroes when a wire-level strip attack
    # removes the signature. Treat that reserved representation as missing.
    signature = signature_bytes.hex() if any(signature_bytes) else None
    pixels = np.frombuffer(data, dtype='<u2', offset=HEADER_LEN + SIG_LEN).astype(np.uint16).reshape(SHAPE)
    return {'pixels': pixels, 'manifest': manifest_from_header(header), 'signature': signature}


def build_packet(sk, counter, prev_hash_hex, arr, meta, nonce=None):
    """Reference implementation of what the firmware does. Returns (packet_bytes, link_hash_hex)."""
    arr = np.ascontiguousarray(arr, dtype=np.uint16)
    if arr.shape != SHAPE:
        raise ValueError('pixels must have shape (4, 256, 256)')
    key_id = key_id_bytes(sk.public_key())
    header = pack_header(
        key_id, counter, prev_hash_hex, hashlib.sha256(pixel_bytes_le(arr)).hexdigest(), meta.get('offset', 1000),
        float(meta.get('lon', 0.0)), float(meta.get('lat', 0.0)), meta.get('date', '1970-01-01'),
        nonce if nonce is not None else os.urandom(8), meta.get('tile', ''),
        (int(meta.get('r0', 0)), int(meta.get('c0', 0))))
    signature = sk.sign(header)
    return header + signature + pixel_bytes_le(arr), link_hash_v2(header, signature)


class DeviceSource:
    """Python stand-in for the satellite firmware (used on a Raspberry Pi or in tests)."""

    def __init__(self, sk=None):
        self._sk = sk if sk is not None else Ed25519PrivateKey.generate()
        self.public_key = self._sk.public_key()
        self.key_id = key_id_bytes(self.public_key).hex()
        self.counter = 0
        self.head = GENESIS

    def acquire(self, arr, meta, nonce=None):
        self.counter += 1
        data, link = build_packet(self._sk, self.counter, self.head, arr, meta, nonce)
        self.head = link
        return data


class DeviceGround(ChainedGround):
    """Ground station that verifies legacy JSON packets and TPX2 device packets."""

    def verify(self, pkg):
        manifest = pkg.get('manifest') if isinstance(pkg, dict) else None
        if isinstance(manifest, dict) and manifest.get('format') == FORMAT_NAME:
            return self._verify_device(pkg)
        return super().verify(pkg)

    def _verify_device(self, pkg):
        res = {'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED', 'replay': False, 'plausible': True,
               'changed_tiles': [], 'reasons': [], 'chain': 'N/A'}
        arr, sig_hex = pkg.get('pixels'), pkg.get('signature')
        try:
            header = bytes.fromhex(pkg['manifest']['header_hex'])
            fields = unpack_header(header)  # always re-derived: the dictionary fields are not trusted
        except (KeyError, ValueError, TypeError):
            res['reasons'].append('malformed device header')
            return res
        key_id = fields['key_id']
        pub = self.trusted.get(key_id)
        if not sig_hex:
            res['reasons'].append('signature missing: origin cannot be verified')
            return res
        if pub is None:
            res['provenance'] = 'INVALID'
            res['reasons'].append(f'unknown key ({key_id}): signer not recognised')
            return res
        try:
            signature = bytes.fromhex(sig_hex)
            pub.verify(signature, header)
            res['provenance'] = 'VALID'
        except (InvalidSignature, ValueError):
            res['provenance'] = 'INVALID'
            res['reasons'].append('invalid signature: header modified or signed by someone else')
            return res
        shape_ok = (arr is not None and list(arr.shape) == fields['shape'] and str(arr.dtype) == 'uint16')
        same = shape_ok and hashlib.sha256(pixel_bytes_le(arr)).hexdigest() == fields['sha256']
        res['integrity'] = 'PASS' if same else 'FAIL'
        if not same:
            res['reasons'].append('SHA-256 mismatch: pixels were modified after signing')
        previous_counter = self.last_counter.get(key_id, 0)
        if fields['nonce'] in self.seen_nonces or fields['counter'] <= previous_counter:
            res['replay'] = True
            res['reasons'].append('replay: nonce already seen or counter not increasing')
        else:
            self.seen_nonces.add(fields['nonce'])
            self.last_counter[key_id] = fields['counter']
            self._check_chain(res, key_id, fields['prev_hash'], fields['counter'], previous_counter,
                              link_hash_v2(header, signature))
        if fields['sensor'] not in self.allowed_sensors:
            res['plausible'] = False
            res['reasons'].append('sensor not allowed')
        date = _dt.datetime.strptime(fields['time_utc'], '%Y-%m-%d').replace(tzinfo=_dt.timezone.utc)
        if date > _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=self.tolerance_days):
            res['plausible'] = False
            res['reasons'].append('acquisition date is in the future')
        if self.aoi_boxes:
            lon, lat = fields['geo']
            if not any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3] for b in self.aoi_boxes):
                res['plausible'] = False
                res['reasons'].append('position outside the expected zones')
        return res
