"""Thin reverse-proxy adapter around attacker.scenarios.tamper."""

from __future__ import annotations

import base64
import io
import json
import os
from urllib.parse import parse_qs, urlsplit

import numpy as np
from mitmproxy import http

from tp.attacks import ALL_FAMILIES, SEV_ALL
from attacker.scenarios import MODES, PLACES_PATH, tamper


class ScenarioAddon:
    def __init__(self):
        self.mode = 'passthrough'
        self.family = os.getenv('FAMILY', 'inpaint_ns')
        self.severity = os.getenv('SEV', 'strong')
        self.target = 'all'
        self.probability = 1.0
        self.rng = np.random.default_rng(int(os.getenv('SEED', '0')))
        self.stolen_key = os.getenv('STOLEN_KEY')
        self.loot = {}
        self.place_centers = __import__('json').loads(PLACES_PATH.read_text(encoding='utf-8'))

    def request(self, flow: http.HTTPFlow):
        parsed = urlsplit(flow.request.pretty_url)
        if parsed.path == '/__mode':
            query = parse_qs(parsed.query)
            requested = query.get('m', [''])[0]
            if requested not in MODES:
                flow.response = http.Response.make(400, b'Unknown mode')
            else:
                try:
                    family = query.get('family', [self.family])[0]
                    severity = query.get('sev', [self.severity])[0]
                    target = query.get('target', ['all'])[0]
                    probability = float(query.get('p', ['1'])[0])
                    if target != 'all' and target not in self.place_centers:
                        raise ValueError('unknown target')
                    if family not in (*ALL_FAMILIES, 'compound', 'compound_mixed') or severity not in SEV_ALL:
                        raise ValueError('invalid family or severity')
                    if not 0 <= probability <= 1:
                        raise ValueError('invalid probability')
                    self.mode, self.family, self.severity = requested, family, severity
                    self.target, self.probability = target, probability
                    self.loot.clear()
                    detail = f'mode={self.mode}; family={self.family}; severity={self.severity}; target={self.target}; probability={self.probability:g}'
                    flow.response = http.Response.make(200, detail.encode())
                except (ValueError, OSError, KeyError):
                    flow.response = http.Response.make(400, b'Invalid attack configuration')
            return
        if parsed.path != '/ingest' or flow.request.method != 'POST':
            return
        try:
            payload = json.loads(flow.request.get_text())
            pixels = np.load(io.BytesIO(base64.b64decode(payload['pixels'], validate=True)), allow_pickle=False)
            pkt = {'pixels': pixels, 'manifest': payload['manifest'], 'signature': payload.get('signature')}
            altered = tamper(pkt, self.mode, self.rng, self.family, self.severity, self.stolen_key, self.loot,
                             target=self.target, probability=self.probability, place_centers=self.place_centers)
            buff = io.BytesIO()
            np.save(buff, altered['pixels'], allow_pickle=False)
            payload.update({'pixels': base64.b64encode(buff.getvalue()).decode('ascii'),
                            'manifest': altered['manifest'], 'signature': altered.get('signature')})
            flow.request.text = json.dumps(payload, separators=(',', ':'))
            flow.request.headers['X-Attack-Mode'] = self.mode
        except Exception as exc:
            flow.response = http.Response.make(400, f'Invalid packet for configured scenario: {type(exc).__name__}'.encode())


addons = [ScenarioAddon()]
