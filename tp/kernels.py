"""State-adaptive kernel bank: low-pass and high-pass, linear and non-linear filters.

The chip is first classified into an image state (cloudy, flat, textured, urban). Each state selects
the kernels that are informative for it. Every kernel produces a residual image; the residual is
summarised block by block with robust statistics, and a block that departs from the rest of the chip
gets a high z-score. The result is an explainable anomaly map plus a score.

Kernel families
---------------
* ``laplacian_noise``  - linear high-pass (3x3 Laplacian): local sensor-noise level.
* ``dog_ratio``        - linear band-pass over low-pass: ratio of fine detail (DoG 1-2 px) to
                         coarse structure (Gaussian low-pass), sensitive to blur and resampling.
* ``median_residual``  - non-linear (median 5x5): impulsive noise, smooth patches from inpainting.
* ``morph_residual``   - non-linear (morphological gradient): small bright or dark objects.

The score is evidence, not a verdict. It does not change the model input contract and uses only
NumPy and OpenCV.
"""
from __future__ import annotations

import cv2
import numpy as np

cv2.setNumThreads(0)

GRID = 8
BLOCK = 32
STATES = ('cloudy', 'flat', 'textured', 'urban')
KERNELS = ('laplacian_noise', 'dog_ratio', 'median_residual', 'morph_residual')

# Kernels used for each image state (a priori design, not fitted to the evaluation data).
STATE_KERNELS = {
    'flat': ('laplacian_noise', 'median_residual', 'dog_ratio'),
    'textured': ('dog_ratio', 'laplacian_noise', 'morph_residual'),
    'cloudy': ('median_residual', 'dog_ratio'),
    'urban': ('morph_residual', 'median_residual'),
}

LOCAL_REFERENCE = True  # compare blocks with their neighbours (False: with the whole chip)
CLOUD_FRACTION = 0.25
FLAT_GRADIENT = 0.02
URBAN_GRADIENT = 0.08

_LAPLACIAN = np.array([[-1, 2, -1], [2, -4, 2], [-1, 2, -1]], np.float32) / 4.0


def reflectance(x, offset=1000):
    """Reflectance as defined by the model input contract: (DN - offset) / 10000 clipped to [0, 1.5]."""
    arr = np.asarray(x)
    if arr.ndim != 3 or arr.shape[0] != 4 or arr.shape[1:] != (256, 256):
        raise ValueError('expected an array of shape (4, 256, 256)')
    return np.clip((arr.astype(np.float32) - float(offset)) / 10000.0, 0.0, 1.5)


def _gradient(img):
    smooth = cv2.GaussianBlur(img, (0, 0), 1.0)
    return cv2.magnitude(cv2.Sobel(smooth, cv2.CV_32F, 1, 0), cv2.Sobel(smooth, cv2.CV_32F, 0, 1))


def classify_state(x, offset=1000):
    """Return ``(state, measurements)`` for a chip."""
    r = reflectance(x, offset)
    visible = r[:3].mean(axis=0)
    bright_and_grey = (r[:3].min(axis=0) > 0.2) & (np.abs(r[3] - visible) < 0.1)
    cloud_fraction = float(bright_and_grey.mean())
    gradient = _gradient(r.mean(axis=0))
    measurements = {
        'cloud_fraction': round(cloud_fraction, 4),
        'median_gradient': round(float(np.median(gradient)), 5),
        'p95_gradient': round(float(np.percentile(gradient, 95)), 5),
    }
    if cloud_fraction > CLOUD_FRACTION:
        state = 'cloudy'
    elif measurements['median_gradient'] < FLAT_GRADIENT:
        state = 'flat'
    elif measurements['median_gradient'] > URBAN_GRADIENT:
        state = 'urban'
    else:
        state = 'textured'
    return state, measurements


def _filters(band):
    """Linear and non-linear filter outputs of one band (reflectance units)."""
    low = cv2.GaussianBlur(band, (0, 0), 2.0)
    fine = cv2.GaussianBlur(band, (0, 0), 1.0) - low
    k3 = np.ones((3, 3), np.uint8)
    return {
        'lowpass': low,
        'highpass': cv2.filter2D(band, -1, _LAPLACIAN),
        'dog': fine,
        'median': band - cv2.medianBlur(band, 5),
        'morph': cv2.dilate(band, k3) - cv2.erode(band, k3),
    }


def _block_view(img):
    return img.reshape(GRID, BLOCK, GRID, BLOCK).transpose(0, 2, 1, 3).reshape(GRID * GRID, -1)


def _robust_sigma(blocks):
    med = np.median(blocks, axis=1, keepdims=True)
    return 1.4826 * np.median(np.abs(blocks - med), axis=1)


def _robust_z(values):
    med = float(np.median(values))
    mad = 1.4826 * float(np.median(np.abs(values - med))) + 1e-3
    return (values - med) / mad


def _local_z(values):
    """Deviation of each block from the median of its neighbours, in robust standard deviations.

    Land cover changes smoothly from block to block, so comparing a block with its neighbours is
    fairer than comparing it with the whole chip.
    """
    grid = values.reshape(GRID, GRID)
    padded = np.pad(grid, 1, mode='edge')
    neighbours = np.stack([padded[i:i + GRID, j:j + GRID] for i in range(3) for j in range(3) if (i, j) != (1, 1)])
    diff = (grid - np.median(neighbours, axis=0)).ravel()
    mad = 1.4826 * float(np.median(np.abs(diff - np.median(diff)))) + 1e-3
    return (diff - np.median(diff)) / mad


def _kernel_map(name, bank):
    """Block-wise robust z-map (GRID x GRID) of one kernel for one band."""
    eps = 1e-5
    if name == 'laplacian_noise':
        feat = np.log(_robust_sigma(_block_view(bank['highpass'])) + eps)
    elif name == 'median_residual':
        feat = np.log(_robust_sigma(_block_view(bank['median'])) + eps)
    elif name == 'dog_ratio':
        fine = (_block_view(bank['dog']) ** 2).mean(axis=1)
        coarse = (_block_view(bank['lowpass'] - cv2.GaussianBlur(bank['lowpass'], (0, 0), 6.0)) ** 2).mean(axis=1)
        feat = np.log(fine + eps) - np.log(coarse + eps)
    elif name == 'morph_residual':
        feat = np.log(np.percentile(_block_view(bank['morph']), 95, axis=1) + eps)
    else:
        raise ValueError(f'unknown kernel: {name}')
    return (_local_z(feat) if LOCAL_REFERENCE else _robust_z(feat)).reshape(GRID, GRID)


def analyze_kernels(x, offset=1000):
    """Classify the chip, run the kernels chosen for its state and return scores and maps.

    Returns a dictionary with ``state``, ``measurements``, ``kernels`` (names used), ``scores``
    (per kernel, max absolute block z), ``score`` (their maximum), ``block_maps`` (per kernel
    8x8), ``anomaly_map`` (256x256 float32 in [0, 1]) and ``layers`` (filter outputs of the mean
    band for visual inspection).
    """
    r = reflectance(x, offset)
    state, measurements = classify_state(x, offset)
    banks = [_filters(band) for band in r]
    names = STATE_KERNELS[state]
    block_maps, scores = {}, {}
    for name in names:
        zmap = np.mean([_kernel_map(name, bank) for bank in banks], axis=0)
        block_maps[name] = zmap.astype(np.float32)
        scores[name] = float(np.abs(zmap).max())
    combined = np.max([np.abs(m) for m in block_maps.values()], axis=0)
    anomaly = cv2.resize(combined.astype(np.float32), (256, 256), interpolation=cv2.INTER_LINEAR)
    anomaly = np.clip(anomaly / 10.0, 0.0, 1.0).astype(np.float32)
    mean_bank = _filters(r.mean(axis=0))
    return {
        'state': state, 'measurements': measurements, 'kernels': list(names), 'scores': scores,
        'score': float(max(scores.values())), 'block_maps': block_maps, 'anomaly_map': anomaly,
        'layers': {key: value.astype(np.float32) for key, value in mean_bank.items()},
    }
