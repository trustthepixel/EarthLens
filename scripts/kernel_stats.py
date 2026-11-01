"""Reference statistics of the kernel bank, for the MATLAB prototype and a parity check.

Usage:
    python -m scripts.kernel_stats --chip samples/chip_000 --out exports
        writes exports/<name>_B1.csv .. _B4.csv (digital numbers) and exports/<name>_python.csv
    python -m scripts.kernel_stats --compare exports/<name>_python.csv exports/<name>_matlab.csv
        compares the two statistics files and exits with status 1 when they disagree

The statistics are computed on the interior of the chip (8 pixel border removed) so that the
different border conventions of OpenCV and MATLAB do not matter.
"""
import argparse
import csv
import json
import os
import sys

import numpy as np

from tp.kernels import _filters, reflectance

MARGIN = 8
FIELDS = ('band', 'laplacian_sigma', 'dog_rms', 'median_sigma', 'morph_p95')


def interior_statistics(x, offset=1000):
    """One row per band with robust statistics of the filter residuals (reflectance units)."""
    rows = []
    for index, band in enumerate(reflectance(x, offset), start=1):
        bank = _filters(band)
        sl = (slice(MARGIN, -MARGIN), slice(MARGIN, -MARGIN))

        def sigma(img):
            vals = img[sl].ravel()
            return float(1.4826 * np.median(np.abs(vals - np.median(vals))))

        rows.append({
            'band': index,
            'laplacian_sigma': sigma(bank['highpass']),
            'dog_rms': float(np.sqrt(np.mean(bank['dog'][sl] ** 2))),
            'median_sigma': sigma(bank['median']),
            'morph_p95': float(np.percentile(bank['morph'][sl], 95)),
        })
    return rows


def write_stats(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_stats(path):
    with open(path, newline='', encoding='utf-8') as handle:
        return [{key: float(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def compare(path_a, path_b, rel_tol=0.02):
    """Return a list of disagreements between two statistics files (empty means they match)."""
    a, b = read_stats(path_a), read_stats(path_b)
    if len(a) != len(b):
        return [f'different number of rows: {len(a)} and {len(b)}']
    problems = []
    for row_a, row_b in zip(a, b):
        for key in FIELDS[1:]:
            ref = max(abs(row_a[key]), 1e-9)
            if abs(row_a[key] - row_b[key]) / ref > rel_tol:
                problems.append(f"band {int(row_a['band'])} {key}: {row_a[key]:.6g} vs {row_b[key]:.6g}")
    return problems


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--chip')
    parser.add_argument('--out', default='exports')
    parser.add_argument('--compare', nargs=2, metavar=('PYTHON_CSV', 'MATLAB_CSV'))
    args = parser.parse_args()
    if args.compare:
        issues = compare(*args.compare)
        print('PARITY OK' if not issues else 'PARITY FAILED\n' + '\n'.join(issues))
        sys.exit(1 if issues else 0)
    if not args.chip:
        parser.error('--chip or --compare is required')
    chip = np.load(args.chip + '.npy')
    with open(args.chip + '.json', encoding='utf-8') as handle:
        offset = json.load(handle)['offset']
    name = os.path.basename(args.chip)
    os.makedirs(args.out, exist_ok=True)
    for index in range(4):
        np.savetxt(os.path.join(args.out, f'{name}_B{index + 1}.csv'), chip[index], fmt='%d', delimiter=',')
    write_stats(os.path.join(args.out, f'{name}_python.csv'), interior_statistics(chip, offset))
    print(f'wrote band CSVs and {name}_python.csv in {args.out} (offset {offset})')
