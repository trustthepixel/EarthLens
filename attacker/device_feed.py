"""Send signed TPX2 packets from prepared sample chips: a Python stand-in for the satellite firmware.

Run it on a Raspberry Pi or a laptop. The device seed and the chain state stay on the sender::

    python -m attacker.device_feed --url http://<ground-station>:8000/ingest_v2 --seed-file keys/device_pi.seed.hex

``--drop-every N`` skips sending every Nth packet after signing it, which shows a chain gap at the
ground station without touching the network path.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tp.device_protocol import DeviceSource
from tp.settings import api_endpoint

ROOT = Path(__file__).resolve().parents[1]


def load_samples(directory=ROOT / 'samples'):
    rows = []
    for path in sorted(Path(directory).glob('chip_*.npy')):
        meta_path = path.with_suffix('.json')
        if meta_path.exists():
            rows.append((path.stem, np.load(path, allow_pickle=False), json.loads(meta_path.read_text(encoding='utf-8'))))
    return rows


def make_source(seed_file, state_file):
    seed = bytes.fromhex(Path(seed_file).read_text(encoding='utf-8').strip())
    source = DeviceSource(Ed25519PrivateKey.from_private_bytes(seed))
    try:
        state = json.loads(Path(state_file).read_text(encoding='utf-8'))
        source.counter, source.head = int(state['counter']), str(state['head'])
    except (OSError, ValueError, KeyError):
        pass
    return source


def save_state(source, state_file):
    Path(state_file).write_text(json.dumps({'counter': source.counter, 'head': source.head}), encoding='utf-8')


def run(url, seed_file, state_file=ROOT / 'device_state.json', interval=4.0, count=None, drop_every=0,
        samples=None, post=requests.post, sleep=time.sleep):
    rows = samples if samples is not None else load_samples()
    if not rows:
        raise ValueError('No sample chips found.')
    source = make_source(seed_file, state_file)
    sent = index = 0
    while count is None or sent < count:
        name, pixels, meta = rows[index % len(rows)]
        data = source.acquire(pixels, meta)
        save_state(source, state_file)
        stamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        if drop_every and source.counter % drop_every == 0:
            print(f'{stamp} | {name} | counter {source.counter} | dropped on purpose', flush=True)
        else:
            try:
                response = post(url, data=data, headers={'content-type': 'application/octet-stream'}, timeout=60)
                try:
                    returned = response.json().get('status', 'unknown')
                except (ValueError, AttributeError):
                    returned = 'invalid-response'
                print(f'{stamp} | {name} | counter {source.counter} | HTTP {response.status_code} | {returned}', flush=True)
            except requests.RequestException as exc:
                print(f'{stamp} | {name} | counter {source.counter} | HTTP error ({type(exc).__name__})', flush=True)
        sent += 1
        index += 1
        if count is None or sent < count:
            sleep(interval)
    return sent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=None, help='Backend device endpoint; defaults to TP_API_URL configuration')
    parser.add_argument('--seed-file', type=Path, required=True)
    parser.add_argument('--state-file', type=Path, default=ROOT / 'device_state.json')
    parser.add_argument('--interval', type=float, default=4.0)
    parser.add_argument('--count', type=int)
    parser.add_argument('--drop-every', type=int, default=0)
    args = parser.parse_args(argv)
    if args.interval < 0 or args.drop_every < 0 or (args.count is not None and args.count < 1):
        parser.error('interval and drop-every must be non-negative and count must be positive')
    url = args.url or api_endpoint('ingest_v2')
    if not url:
        parser.error('Set TP_API_URL or provide --url.')
    try:
        run(url, args.seed_file, args.state_file, args.interval, args.count, args.drop_every)
    except KeyboardInterrupt:
        print('\nFeed stopped.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
