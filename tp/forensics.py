"""Classical (training-free) forensic check that complements the U-Net.

``copy_move`` finds regions that were duplicated inside the same chip (the weakest family of the
learned detector, together with photometric edits). It needs only NumPy and OpenCV and does not
change the model input contract. Two other training-free checks (local noise level and band
co-registration) were evaluated and dropped because they did not add detection power; see
``DEVELOPMENT_LOGS.md``.
"""
from __future__ import annotations

import cv2
import numpy as np

cv2.setNumThreads(0)

BLOCK = 32
GRID = 8


def _bands(x):
    arr = np.asarray(x, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[1:] != (256, 256):
        raise ValueError('expected an array of shape (C, 256, 256)')
    return arr


def _match_pairs(desc_a, pts_a, desc_b, pts_b, min_distance, ratio, same_image):
    """Pairs of keypoints whose descriptors match and that lie far enough apart."""
    knn = cv2.BFMatcher(cv2.NORM_L2).knnMatch(desc_a, desc_b, k=3)
    src, dst = [], []
    for m in knn:
        cand = [c for c in m if np.linalg.norm(pts_a[c.queryIdx] - pts_b[c.trainIdx]) >= min_distance]
        if same_image:
            cand = [c for c in cand if c.queryIdx != c.trainIdx]
        if cand and cand[0].distance < ratio * m[-1].distance:
            src.append(pts_a[cand[0].queryIdx])
            dst.append(pts_b[cand[0].trainIdx])
    return np.float32(src), np.float32(dst)


def copy_move(x, min_distance=24, ratio=0.75, min_inliers=8):
    """Score duplicated regions: number of consistent self-matches (0 when nothing is found).

    Rotated copies are found with SIFT self-matching and a similarity fit; mirrored copies are
    found by matching the image against its mirror and fitting a full affine transform.
    """
    arr = _bands(x)
    gray = arr.mean(axis=0)
    lo, hi = np.percentile(gray, [1, 99])
    img = np.clip((gray - lo) / (hi - lo + 1e-6) * 255, 0, 255).astype(np.uint8)
    sift = cv2.SIFT_create(nfeatures=1500, contrastThreshold=0.02)
    kps, desc = sift.detectAndCompute(img, None)
    zmap = np.zeros((GRID, GRID), np.float32)
    if desc is None or len(kps) < 10:
        return 0.0, zmap
    pts = np.float32([k.pt for k in kps])
    mirror_img = np.ascontiguousarray(img[:, ::-1])
    kps_m, desc_m = sift.detectAndCompute(mirror_img, None)
    best_count, best_pts = 0, None
    passes = [(desc, pts, True)]
    if desc_m is not None and len(kps_m) >= 10:
        pts_m = np.float32([(img.shape[1] - 1 - k.pt[0], k.pt[1]) for k in kps_m])
        passes.append((desc_m, pts_m, False))
    for desc_b, pts_b, same in passes:
        src, dst = _match_pairs(desc, pts, desc_b, pts_b, min_distance, ratio, same)
        if len(src) < min_inliers:
            continue
        if same:
            mat, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        else:
            mat, inl = cv2.estimateAffine2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if mat is None:
            continue
        keep = inl.ravel().astype(bool)
        if int(keep.sum()) > best_count:
            best_count, best_pts = int(keep.sum()), np.vstack([src[keep], dst[keep]])
    if best_count < min_inliers:
        return 0.0, zmap
    for px, py in best_pts:
        zmap[min(max(int(py), 0) // BLOCK, GRID - 1), min(max(int(px), 0) // BLOCK, GRID - 1)] += 1.0
    return float(best_count), zmap
