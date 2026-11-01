"""Interactive controller for the Kali mitmproxy scenario addon."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlencode

import requests
from tp.settings import get_setting

MODES = ('passthrough', 'pixels', 'manifest_meta', 'manifest_rehash', 'resign', 'replay', 'strip', 'stolen_key')
FAMILIES = ('inpaint_ns', 'copy_move', 'spectral', 'photometric', 'band_shift', 'texture', 'compound', 'compound_mixed')
SEVERITIES = ('subtle', 'medium', 'strong')


def build_mode_url(base_url, mode, family='inpaint_ns', severity='strong', target='all', probability=1.0):
    query = urlencode({'m': mode, 'family': family, 'sev': severity, 'target': target, 'p': f'{float(probability):g}'})
    return f'{base_url.rstrip("/")}/__mode?{query}'


def configure(base_url, mode, family='inpaint_ns', severity='strong', target='all', probability=1.0,
              get=requests.get):
    response = get(build_mode_url(base_url, mode, family, severity, target, probability), timeout=10)
    response.raise_for_status()
    return response.text


def _choose(prompt, choices, default=0):
    print(prompt)
    for index, value in enumerate(choices, 1):
        print(f'{index}. {value}')
    raw = input(f'Select [{default + 1}]: ').strip()
    return choices[int(raw) - 1] if raw.isdigit() and 1 <= int(raw) <= len(choices) else choices[default]


def main():
    base = get_setting('TP_PROXY_URL')
    if not base:
        print('Set TP_PROXY_URL to the configured proxy base URL.')
        return 1
    while True:
        displayed_modes = ('Back to normal (passthrough)',) + tuple(item for item in MODES if item != 'passthrough')
        selected_mode = _choose('Attack mode', displayed_modes)
        mode = 'passthrough' if selected_mode == 'Back to normal (passthrough)' else selected_mode
        family = _choose('Attack family', FAMILIES)
        severity = _choose('Severity', SEVERITIES, 2)
        places_path = os.path.join(os.path.dirname(__file__), 'places.json')
        try:
            places = ['all', *json.loads(Path(places_path).read_text(encoding='utf-8')).keys()]
        except (OSError, ValueError):
            places = ['all']
        target = _choose('Target place', places)
        raw = input('Tampering probability 0..1 [1]: ').strip()
        try:
            probability = float(raw) if raw else 1.0
            if not 0 <= probability <= 1:
                raise ValueError
        except ValueError:
            print('Invalid probability; using 1.')
            probability = 1.0
        try:
            active = configure(base, mode, family, severity, target, probability)
            print(f'Active configuration: {active}')
        except requests.RequestException as exc:
            print(f'Proxy control failed: {type(exc).__name__}')
        if input('Press Enter to choose another configuration, or q to quit: ').strip().lower() == 'q':
            return 0


if __name__ == '__main__':
    raise SystemExit(main())
