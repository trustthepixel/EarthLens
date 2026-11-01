"""Continuously send signed prepared chips to the ground station or proxy."""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone

import requests

from attacker.source_send import ROOT, make_source, packet
from tp.pack import load_pack
from tp.settings import api_endpoint, get_setting


def select_feed(entries, places=None):
    allowed = {value.strip() for value in places.split(',')} if places else None
    groups = {}
    for entry in entries:
        place = str(entry.get('place') or entry.get('meta', {}).get('place') or 'unknown')
        if allowed is None or place in allowed:
            groups.setdefault(place, []).append(entry)
    names = sorted(groups)
    return [(place, groups[place][index]) for index in range(max(map(len, groups.values()), default=0))
            for place in names if index < len(groups[place])]


def run(url=None, interval=4.0, places=None, direct=False,
        count=None, post=requests.post, sleep=time.sleep, entries=None, source_paths=None):
    url = api_endpoint('ingest') if direct else (url or get_setting('TP_PROXY_URL'))
    if not url:
        raise ValueError('Configure TP_API_URL for direct mode or TP_PROXY_URL for proxy mode.')
    rows = select_feed(load_pack() if entries is None else entries, places)
    if not rows:
        raise ValueError('No prepared chips match the selected places.')
    paths = source_paths or (ROOT / 'keys' / 'source_private.pem', ROOT / 'counter.txt')
    source, counter_path = make_source(*paths)
    index = sent = 0
    while count is None or sent < count:
        place, entry = rows[index % len(rows)]
        body = packet(source, counter_path, entry['pixels'], entry['meta'])
        timestamp = datetime.now(timezone.utc).isoformat(timespec='seconds')
        try:
            response = post(url, json=body, timeout=60)
            try:
                returned = response.json().get('status', 'unknown')
            except (ValueError, AttributeError):
                returned = 'invalid-response'
            print(f'{timestamp} | {place} | HTTP {response.status_code} | {returned}', flush=True)
        except requests.RequestException as exc:
            print(f'{timestamp} | {place} | HTTP error ({type(exc).__name__}) | unavailable', flush=True)
        sent += 1
        index += 1
        if count is None or sent < count:
            sleep(interval)
    return sent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=float, default=4.0)
    parser.add_argument('--places', help='Comma-separated preset place names to include')
    parser.add_argument('--url', default=None, help='Proxy ingest URL; defaults to TP_PROXY_URL')
    parser.add_argument('--direct', action='store_true', help='Send to the local API instead of the proxy')
    parser.add_argument('--count', type=int, help='Stop after this many packets')
    args = parser.parse_args(argv)
    if args.interval < 0 or (args.count is not None and args.count < 1):
        parser.error('interval must be non-negative and count must be positive')
    try:
        run(args.url, args.interval, args.places, args.direct, args.count)
    except KeyboardInterrupt:
        print('\nFeed stopped.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
