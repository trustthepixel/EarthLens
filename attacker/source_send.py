"""Create and send a signed packet from a local source installation."""

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
import requests
from cryptography.hazmat.primitives import serialization

from tp.chain import ChainedSource
from tp.settings import api_endpoint

ROOT = Path(__file__).resolve().parents[1]


def make_source(private_path=ROOT / 'keys' / 'source_private.pem', counter_path=ROOT / 'counter.txt'):
    private = serialization.load_pem_private_key(Path(private_path).read_bytes(), password=None)
    source = ChainedSource(sk=private)
    try:
        source.counter = int(Path(counter_path).read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        source.counter = 0
    chain_path = Path(counter_path).with_suffix(Path(counter_path).suffix + '.chain')
    try:
        source.head = chain_path.read_text(encoding='utf-8').strip()
    except OSError:
        pass
    return source, Path(counter_path)


def packet(source, counter_path, pixels, meta):
    pkg = source.acquire(pixels, meta)
    counter_path.write_text(str(source.counter), encoding='utf-8')
    Path(counter_path).with_suffix(Path(counter_path).suffix + '.chain').write_text(source.head, encoding='utf-8')
    buffer = io.BytesIO()
    np.save(buffer, pkg['pixels'], allow_pickle=False)
    return {'pixels': base64.b64encode(buffer.getvalue()).decode('ascii'), 'manifest': pkg['manifest'], 'signature': pkg['signature']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=None, help='Backend ingest URL; defaults to TP_API_URL configuration')
    parser.add_argument('--chip', type=Path, default=ROOT / 'samples' / 'chip_000.npy')
    parser.add_argument('--meta', type=Path, default=None)
    args = parser.parse_args(argv)
    meta_path = args.meta or args.chip.with_suffix('.json')
    source, counter_file = make_source()
    body = packet(source, counter_file, np.load(args.chip, allow_pickle=False), json.loads(meta_path.read_text(encoding='utf-8')))
    url = args.url or api_endpoint('ingest')
    if not url:
        parser.error('Set TP_API_URL or provide --url.')
    response = requests.post(url, json=body, timeout=60)
    print(json.dumps(response.json(), indent=2))
    return 0 if response.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
