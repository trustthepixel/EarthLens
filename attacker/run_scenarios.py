"""Exercise the ground-station API through a proxy or directly."""

from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
import requests
from attacker.scenarios import tamper
from attacker.source_send import ROOT, make_source, packet
from tp.settings import api_endpoint, get_setting

N = 20
ORDER = ('passthrough', 'pixels', 'manifest_meta', 'manifest_rehash', 'resign', 'replay', 'strip', 'stolen_key')
EXPECT = {'passthrough': {'TRUSTED', 'SUSPICIOUS'}, 'pixels': {'COMPROMISED'},
          'manifest_meta': {'COMPROMISED'}, 'manifest_rehash': {'COMPROMISED'},
          'resign': {'COMPROMISED'}, 'replay': {'COMPROMISED'},
          'strip': {'SUSPICIOUS', 'COMPROMISED'}, 'stolen_key': {'SUSPICIOUS', 'COMPROMISED'}}


def _wire(pkg):
    buff = io.BytesIO()
    np.save(buff, pkg['pixels'], allow_pickle=False)
    return {'pixels': base64.b64encode(buff.getvalue()).decode('ascii'), 'manifest': pkg['manifest'], 'signature': pkg.get('signature')}


def run(direct=False, api_url=None, proxy_url=None, n=N):
    api_url = api_url or api_endpoint('ingest')
    proxy_url = proxy_url or get_setting('TP_PROXY_URL')
    if direct and not api_url:
        raise ValueError('Configure TP_API_URL for direct mode or pass --api-url.')
    if not direct and not proxy_url:
        raise ValueError('Configure TP_PROXY_URL for proxy mode or pass --proxy-url.')
    sample = ROOT / 'samples' / 'chip_000.npy'
    pixels = np.load(sample, allow_pickle=False)
    meta = json.loads(sample.with_suffix('.json').read_text(encoding='utf-8'))
    source, counter_path = make_source()
    rng = np.random.default_rng(int(os.getenv('SEED', '0')))
    loot = {}
    rows = []
    for mode in ORDER:
        if not direct:
            requests.get(proxy_url + '/__mode', params={'m': mode}, timeout=10).raise_for_status()
        for idx in range(n):
            body = packet(source, counter_path, pixels, meta)
            if direct:
                pkg = {'pixels': pixels.copy(), 'manifest': body['manifest'], 'signature': body['signature']}
                attacked = tamper(pkg, mode, rng, os.getenv('FAMILY', 'inpaint_ns'), os.getenv('SEV', 'strong'), os.getenv('STOLEN_KEY'), loot)
                body = _wire(attacked)
                response = requests.post(api_url, json=body, headers={'X-Attack-Mode': mode}, timeout=60)
            else:
                response = requests.post(proxy_url + '/ingest', json=body, timeout=60)
            data = response.json()
            status = data.get('status', 'ERROR')
            expected = EXPECT[mode]
            ok = status in expected
            if mode == 'replay':
                ok = status in ({'TRUSTED', 'SUSPICIOUS'} if idx == 0 else {'COMPROMISED'})
            rows.append({'mode': mode, 'packet': idx + 1, 'status': status, 'score': data.get('score'),
                         'ok': ok, 'expected': '|'.join(sorted(expected))})
    output = ROOT / 'attack_campaign.csv'
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row['mode']].append(row)
    for mode in ORDER:
        selected = grouped[mode]
        counts = {status: sum(row['status'] == status for row in selected) for status in sorted({row['status'] for row in selected})}
        print(f"{mode}: {sum(row['ok'] for row in selected)}/{len(selected)} expected; statuses={counts}")
    print(f'Campaign table written to {output.name}')
    return all(row['ok'] for row in rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direct', action='store_true', help='tamper and call the API without mitmproxy')
    parser.add_argument('--api-url', default=None, help='Backend ingest URL; defaults to TP_API_URL configuration')
    parser.add_argument('--proxy-url', default=None, help='Proxy base URL; defaults to TP_PROXY_URL')
    parser.add_argument('--n', type=int, default=N)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.direct, args.api_url, args.proxy_url, args.n) else 1)
