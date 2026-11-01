"""Evaluate the kernel bank per attack family on the chips in ``samples/``.

Usage: python -m scripts.eval_kernels [--reps 3] [--severity medium] [--out reports/kernel_eval.md]

Authentic class: every sample chip with benign gain and noise variation. Attack class: the same
chips with one attack family applied (``tp.attacks``). The report lists the AUC of the state-adaptive
score, of a baseline that always runs every kernel, and of each kernel alone.
"""
import argparse
import glob
import json
import time

import numpy as np

from tp import attacks
from tp.kernels import KERNELS, STATE_KERNELS, _filters, _kernel_map, analyze_kernels, reflectance


def auc(negative, positive):
    neg, pos = np.asarray(negative, float), np.asarray(positive, float)
    wins = (pos[:, None] > neg[None]).sum() + 0.5 * (pos[:, None] == neg[None]).sum()
    return float(wins / (len(pos) * len(neg)))


def all_kernel_scores(x, offset=1000):
    banks = [_filters(band) for band in reflectance(x, offset)]
    return {name: float(np.abs(np.mean([_kernel_map(name, bank) for bank in banks], axis=0)).max())
            for name in KERNELS}


def evaluate(reps=3, severity='medium', seed=0, families=None):
    paths = sorted(glob.glob('samples/*.npy'))
    chips = [np.load(p) for p in paths]
    offsets = [json.load(open(p.replace('.npy', '.json')))['offset'] for p in paths]
    rng = np.random.default_rng(seed)

    def record(x, off):
        per = all_kernel_scores(x, off)
        report = analyze_kernels(x, off)
        return {'adaptive': report['score'], 'all': max(per.values()), 'state': report['state'], **per}

    authentic = [record(attacks.benign(c, rng, vary=True), o) for c, o in zip(chips, offsets) for _ in range(reps)]
    result = {}
    for family in families or attacks.ALL_FAMILIES:
        rows = []
        for i, (c, o) in enumerate(zip(chips, offsets)):
            donor = chips[(i + 1) % len(chips)]
            for _ in range(reps):
                x = attacks.benign(c, rng, vary=True)
                out, _, _ = attacks.make_attack(x, donor, family, severity, rng, o)
                rows.append(record(out, o))
        result[family] = {key: auc([a[key] for a in authentic], [r[key] for r in rows])
                          for key in ('adaptive', 'all') + KERNELS}
    states = {}
    for a in authentic:
        states[a['state']] = states.get(a['state'], 0) + 1
    return authentic, result, states


def to_markdown(result, states, reps, severity, seconds):
    cols = ('adaptive', 'all') + KERNELS
    lines = [f'# Kernel bank evaluation ({severity}, {reps} repetitions per chip)', '',
             f'Chips: samples/ (authentic class = benign gain and noise variation). States seen: {states}.',
             f'Run time: {seconds:.0f} s.', '',
             '| family | ' + ' | '.join(cols) + ' |', '|---|' + '---|' * len(cols)]
    for family, row in result.items():
        lines.append(f'| {family} | ' + ' | '.join(f'{row[c]:.2f}' for c in cols) + ' |')
    mean = {c: np.mean([row[c] for row in result.values()]) for c in cols}
    lines.append('| **mean** | ' + ' | '.join(f'{mean[c]:.2f}' for c in cols) + ' |')
    lines += ['', 'AUC 0.50 means no separation. State to kernel mapping: ' + json.dumps(STATE_KERNELS), '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reps', type=int, default=3)
    parser.add_argument('--severity', default='medium', choices=['subtle', 'medium', 'strong'])
    parser.add_argument('--out', default='reports/kernel_eval.md')
    args = parser.parse_args()
    start = time.time()
    _, result, states = evaluate(args.reps, args.severity)
    text = to_markdown(result, states, args.reps, args.severity, time.time() - start)
    with open(args.out, 'w', encoding='utf-8') as handle:
        handle.write(text)
    print(text)
