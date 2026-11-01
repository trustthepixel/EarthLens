"""Fetch and score a small set of recent clean chips."""

from __future__ import annotations

import sys
import random

import numpy as np

from tp.onnx_analyzer import OnnxAnalyzer
from tp.sentinel_live import NetworkUnavailable, REGIONS, latest_items, sample_scene


def main() -> int:
    analyzer = OnnxAnalyzer('model')
    threshold, _ = analyzer.decision_thresholds()
    found = 0
    print('region | scene | date | offset | score | compared with t_low')
    for region in ('Tunis', 'Kairouan', 'Sfax', 'Gabes'):
        if found >= 10:
            break
        try:
            bbox = REGIONS[region]
            items = latest_items(bbox, days=45, max_cloud=30, n=10)
        except NetworkUnavailable as exc:
            print(f'Live data unavailable: {exc}')
            print('Run: .\\.venv\\Scripts\\python.exe -m scripts.live_smoke')
            return 0
        for item in items:
            if found >= 10:
                break
            try:
                chips, metas, _ = sample_scene(region, 'live', bbox, item, 'clean', 1,
                                               tries_factor=40, rnd=random.Random())
            except NetworkUnavailable as exc:
                print(f'Live data unavailable: {exc}')
                print('Run: .\\.venv\\Scripts\\python.exe -m scripts.live_smoke')
                return 0
            if not chips:
                continue
            meta = metas[0]
            score = analyzer.analyze(chips[0], meta['offset'])['score']
            print(f"{region} | {item.id} | {meta['date']} | {meta['offset']} | {score:.6f} | {'below' if score < threshold else 'at/above'}")
            found += 1
    if not found:
        print('No recent clean chips were available.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
