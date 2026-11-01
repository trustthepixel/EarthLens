"""Generate fixed TPX2 test vectors that firmware must reproduce byte for byte.

Run from the project root::

    python -m scripts.make_tpx2_vectors

The vectors use a fixed demonstration seed. Never reuse that seed on a real device.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tp.chain import GENESIS
from tp.device_protocol import HEADER_LEN, build_packet, key_id_bytes, pixel_bytes_le

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tests' / 'vectors' / 'tpx2_vectors.json'
SEED = bytes(range(32))
META = {'date': '2026-05-01', 'lon': 10.18, 'lat': 36.8, 'tile': 'T32SNH', 'offset': 1000, 'r0': 0, 'c0': 0}
PIXEL_FORMULA = 'pixel[c][y][x] = 1000 + ((c*131 + y*7 + x*13 + shift) % 3000), shift = packet_index'


def vector_pixels(shift):
    c, y, x = np.meshgrid(np.arange(4), np.arange(256), np.arange(256), indexing='ij')
    return (1000 + ((c * 131 + y * 7 + x * 13 + shift) % 3000)).astype(np.uint16)


def build():
    sk = Ed25519PrivateKey.from_private_bytes(SEED)
    pub_raw = sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    packets, prev = [], GENESIS
    for index in range(2):
        pixels = vector_pixels(index)
        nonce = bytes(range(index * 16 + 1, index * 16 + 9))
        data, link = build_packet(sk, index + 1, prev, pixels, META, nonce=nonce)
        header, signature = data[:HEADER_LEN], data[HEADER_LEN:HEADER_LEN + 64]
        packets.append({'counter': index + 1, 'prev_hash': prev, 'nonce_hex': nonce.hex(),
                        'pixel_sha256': hashlib.sha256(pixel_bytes_le(pixels)).hexdigest(),
                        'header_hex': header.hex(), 'signature_hex': signature.hex(), 'link_hash': link})
        prev = link
    return {'seed_hex': SEED.hex(), 'public_key_hex': pub_raw.hex(), 'key_id_hex': key_id_bytes(sk.public_key()).hex(),
            'meta': META, 'pixel_formula': PIXEL_FORMULA, 'header_length': HEADER_LEN, 'packets': packets}


def main():
    OUT.write_text(json.dumps(build(), indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {OUT.relative_to(ROOT).as_posix()}')


if __name__ == '__main__':
    main()
