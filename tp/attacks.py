import math

import cv2
import numpy as np

cv2.setNumThreads(0)

BANDS = ['B02', 'B03', 'B04', 'B08']

CHIP = 256

DEFAULT_OFFSET = 1000

SEVERITY = {'subtle': (24, 40), 'medium': (40, 72), 'strong': (72, 128)}

SEV_ALL = ('subtle', 'medium', 'strong')

def feather(mask, sigma=2.0):
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), float(sigma))

def to_u16(a):
    return np.clip(np.rint(a), 0, 65535).astype(np.uint16)

def shape_mask(size, rng):
    size = int(size)
    kind = str(rng.choice(['rect', 'ellipse', 'blob']))
    m = np.zeros((size, size), np.uint8)
    if kind == 'rect':
        m[:] = 1
    elif kind == 'ellipse':
        cv2.ellipse(m, (size // 2, size // 2), (max(size // 2 - 1, 2), max(size // 3, 2)),
                    float(rng.uniform(0, 180)), 0, 360, 1, -1)
    else:
        n = cv2.GaussianBlur(rng.normal(size=(size, size)).astype(np.float32), (0, 0), max(size / 6.0, 1.5))
        m = (n > np.quantile(n, 0.4)).astype(np.uint8)
        k, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        if k > 1:
            m = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    if m.sum() == 0:
        m[:] = 1
    return m

def place(tpl, H, W, rng):
    h, w = tpl.shape
    y = int(rng.integers(0, H - h + 1)); x = int(rng.integers(0, W - w + 1))
    m = np.zeros((H, W), np.uint8)
    m[y:y + h, x:x + w] = tpl
    return m, y, x

def random_mask(H, W, size, rng):
    return place(shape_mask(size, rng), H, W, rng)[0]

_LAP = np.array([[-1, 2, -1], [2, -4, 2], [-1, 2, -1]], np.float32) / 4.0

def noise_sigma(x):
    # écart-type du bruit par bande (estimateur robuste MAD sur le résidu passe-haut)
    s = []
    for c in range(x.shape[0]):
        r = cv2.filter2D(x[c].astype(np.float32), -1, _LAP)
        s.append(1.4826 * np.median(np.abs(r - np.median(r))) / 1.5 + 1e-3)
    return np.asarray(s, np.float32)

def detectability(x, out, mask, sig=None):
    # score z du changement : (amplitude moyenne du changement / bruit du capteur) x racine(nombre de pixels modifiés).
    # Un score faible = changement noyé dans le bruit : l'attaque est statistiquement imperceptible.
    sel = mask > 0
    n = int(sel.sum())
    if n == 0:
        return 0.0
    d = np.abs(out.astype(np.float32) - x.astype(np.float32))[:, sel].mean(1)
    sig = noise_sigma(x) if sig is None else sig
    return float(np.mean(d / sig) * math.sqrt(n))

def copy_move(x, donor, size, rng, off):
    C, H, W = x.shape
    tpl = shape_mask(size, rng)
    _, sy, sx = place(tpl, H, W, rng)
    h, w = tpl.shape
    patch = x[:, sy:sy + h, sx:sx + w].astype(np.float32)
    pm = tpl.copy()
    k = int(rng.integers(0, 4))
    patch = np.rot90(patch, k, axes=(1, 2)); pm = np.rot90(pm, k)
    if rng.random() < 0.5:
        patch = patch[:, :, ::-1]; pm = pm[:, ::-1]
    patch = np.ascontiguousarray(patch); pm = np.ascontiguousarray(pm)
    ph, pw = pm.shape
    ty = tx = 0
    for _ in range(50):
        ty, tx = int(rng.integers(0, H - ph + 1)), int(rng.integers(0, W - pw + 1))
        if abs(ty - sy) > h or abs(tx - sx) > w:
            break
    a = feather(pm, 2.0)[None]
    out = x.astype(np.float32)
    out[:, ty:ty + ph, tx:tx + pw] = a * patch + (1 - a) * out[:, ty:ty + ph, tx:tx + pw]
    mask = np.zeros((H, W), np.uint8)
    mask[ty:ty + ph, tx:tx + pw] = pm
    return to_u16(out), mask, {'rot90': k}

def splice(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    d = donor.astype(np.float32).copy()
    match = bool(rng.random() < 0.7)
    if match:
        for c in range(C):
            xs = x[c][m > 0].astype(np.float32)
            d[c] = (d[c] - d[c].mean()) / (d[c].std() + 1e-6) * (xs.std() + 1e-6) + xs.mean()
    a = feather(m, float(rng.uniform(1.0, 3.0)))[None]
    return to_u16(a * d + (1 - a) * x.astype(np.float32)), m, {'stats_matched': match}

def class_swap(x, donor, size, rng, off):
    # colle une VRAIE zone d'eau ou de végétation prise ailleurs (fausse inondation, faux champ irrigué)
    C, H, W = x.shape
    size = int(size)
    d = (donor.astype(np.float32) - off) / 10000.0
    b, g, r, n = d
    eps = 1e-4
    kind = str(rng.choice(['water', 'vegetation']))
    score = (g - n) / (g + n + eps) if kind == 'water' else (n - r) / (n + r + eps)
    k = size // 2 * 2 + 1
    box = cv2.blur(score.astype(np.float32), (k, k))
    ys, xs = np.where(box >= np.quantile(box, 0.98))
    j = int(rng.integers(len(ys)))
    y0 = int(np.clip(ys[j] - size // 2, 0, H - size)); x0 = int(np.clip(xs[j] - size // 2, 0, W - size))
    tpl = shape_mask(size, rng)
    patch = donor[:, y0:y0 + size, x0:x0 + size].astype(np.float32)
    m, ty, tx = place(tpl, H, W, rng)
    a = feather(tpl, 2.0)[None]
    out = x.astype(np.float32)
    out[:, ty:ty + size, tx:tx + size] = a * patch + (1 - a) * out[:, ty:ty + size, tx:tx + size]
    return to_u16(out), m, {'classe': kind}

def _affine_region(x, size, rng, make_M):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    ys, xs = np.where(m)
    M = make_M((float(xs.mean()), float(ys.mean())))
    warped = np.stack([cv2.warpAffine(x[c].astype(np.float32), M, (W, H), flags=cv2.INTER_CUBIC,
                                      borderMode=cv2.BORDER_REFLECT) for c in range(C)])
    mm = np.maximum(m, cv2.warpAffine(m, M, (W, H), flags=cv2.INTER_NEAREST))
    a = feather(mm, 2.0)[None]
    return to_u16(a * warped + (1 - a) * x.astype(np.float32)), mm

def _rotate(x, size, rng, lo, hi):
    angle = float(rng.uniform(lo, hi)) * (1 if rng.random() < 0.5 else -1)
    out, mm = _affine_region(x, size, rng, lambda c: cv2.getRotationMatrix2D(c, angle, 1.0))
    return out, mm, {'angle': round(angle, 1)}

def rotate_region(x, donor, size, rng, off):
    return _rotate(x, size, rng, 5, 40)

def rotate_big(x, donor, size, rng, off):                  # paramètres inédits (test)
    return _rotate(x, size, rng, 45, 90)

def scale_region(x, donor, size, rng, off):
    f = float(rng.uniform(0.75, 1.3))
    if abs(f - 1) < 0.08:
        f = 1.15
    out, mm = _affine_region(x, size, rng, lambda c: cv2.getRotationMatrix2D(c, 0.0, f))
    return out, mm, {'facteur': round(f, 2)}

def spectral_edit(x, donor, size, rng, off):
    C, H, W = x.shape
    mode = str(rng.choice(['greenify', 'dry', 'flood']))
    if mode == 'greenify':
        g = [1, 1, rng.uniform(.7, .9), rng.uniform(1.2, 1.5)]
    elif mode == 'dry':
        g = [1, 1, rng.uniform(1.1, 1.3), rng.uniform(.6, .85)]
    else:
        g = [rng.uniform(.95, 1.2), rng.uniform(.95, 1.15), rng.uniform(.85, 1.0), rng.uniform(.3, .6)]
    m = random_mask(H, W, size, rng)
    a = feather(m, float(rng.uniform(2, 4)))[None]
    xf = x.astype(np.float32)
    edited = (xf - off) * np.asarray(g, np.float32)[:, None, None] + off
    return to_u16(a * edited + (1 - a) * xf), m, {'mode': mode}

def photometric_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    gain, gamma = float(rng.uniform(0.7, 1.3)), float(rng.uniform(0.7, 1.4))
    refl = np.clip(x.astype(np.float32) - off, 0, None)
    ref = max(float(np.percentile(refl, 99.5)), 1.0)
    y = ref * np.power(np.clip(refl * gain / ref, 0, None), gamma) + off
    a = feather(m, 3.0)[None]
    return to_u16(a * y + (1 - a) * x.astype(np.float32)), m, {'gain': round(gain, 2), 'gamma': round(gamma, 2)}

def noise_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    xf = x.astype(np.float32)
    if rng.random() < 0.5:
        y = xf + rng.normal(0, float(rng.uniform(20, 120)), xf.shape).astype(np.float32); mode = 'gauss'
    else:
        y = (xf - off) * (1 + rng.normal(0, float(rng.uniform(.03, .12)), xf.shape).astype(np.float32)) + off; mode = 'speckle'
    a = feather(m, 3.0)[None]
    return to_u16(a * y + (1 - a) * xf), m, {'mode': mode}

def blur_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    xf = x.astype(np.float32)
    if rng.random() < 0.6:
        k = int(rng.choice([3, 5, 7])); y = np.stack([cv2.GaussianBlur(c, (k, k), 0) for c in xf]); mode = 'flou'
    else:
        amt = float(rng.uniform(0.8, 2.0))
        y = xf + amt * (xf - np.stack([cv2.GaussianBlur(c, (0, 0), 1.5) for c in xf])); mode = 'nettete'
    a = feather(m, 2.0)[None]
    return to_u16(a * y + (1 - a) * xf), m, {'mode': mode}

def jpeg_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    q = int(rng.integers(30, 86))
    dec = np.empty(x.shape, np.float32)
    for c in range(C):
        lo, hi = np.percentile(x[c], [0.5, 99.5]); sc = float(hi - lo) + 1e-6
        u8 = np.clip((x[c].astype(np.float32) - lo) / sc * 255, 0, 255).astype(np.uint8)
        ok, buf = cv2.imencode('.jpg', u8, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        dec[c] = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255 * sc + lo
    a = feather(m, 1.5)[None]
    return to_u16(a * dec + (1 - a) * x.astype(np.float32)), m, {'qualite': q}

def object_insert(x, donor, size, rng, off):
    # petits objets brillants ou sombres (toits, véhicules, bateaux) à l'échelle de quelques pixels
    C, H, W = x.shape
    size = int(size)
    wy, wx = int(rng.integers(0, H - size + 1)), int(rng.integers(0, W - size + 1))
    out = x.astype(np.float32)
    mask = np.zeros((H, W), np.uint8)
    sign = 1.0 if rng.random() < 0.6 else -1.0
    n = int(rng.integers(2, 6))
    for _ in range(n):
        r = int(rng.integers(2, 6))
        cy = wy + int(rng.integers(r, size - r)); cx = wx + int(rng.integers(r, size - r))
        disc = np.zeros((H, W), np.float32)
        cv2.circle(disc, (cx, cy), r, 1.0, -1)
        out += feather(disc, 1.0)[None] * sign * float(rng.uniform(0.10, 0.35)) * 10000.0
        mask |= (cv2.dilate(disc.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0).astype(np.uint8)
    return to_u16(out), mask, {'n_objets': n}

def _inpaint(x, size, rng, flag):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    out = x.astype(np.float32).copy()
    radius = int(rng.integers(3, 8))
    for c in range(C):
        lo, hi = np.percentile(x[c], [0.5, 99.5]); sc = float(hi - lo) + 1e-6
        u8 = np.clip((x[c].astype(np.float32) - lo) / sc * 255, 0, 255).astype(np.uint8)
        r = cv2.inpaint(u8, m, radius, flag).astype(np.float32) / 255 * sc + lo
        out[c] = np.where(m > 0, r, out[c])
    return to_u16(out), m, {'rayon': radius}

def inpaint_telea(x, donor, size, rng, off):
    return _inpaint(x, size, rng, cv2.INPAINT_TELEA)

def inpaint_ns(x, donor, size, rng, off):
    return _inpaint(x, size, rng, cv2.INPAINT_NS)

def cloud_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    noise = cv2.GaussianBlur(rng.random((H, W)).astype(np.float32), (0, 0), 10)
    noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-6)
    a = (feather(m, 6.0) * (0.6 + 0.4 * noise))[None]
    white = off + float(rng.uniform(2500, 4500)) * (0.8 + 0.2 * noise)[None]
    return to_u16(a * white + (1 - a) * x.astype(np.float32)), m, {}

def resample_region(x, donor, size, rng, off):
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    f = float(rng.uniform(0.5, 0.9)) if rng.random() < 0.7 else float(rng.uniform(1.1, 1.6))
    xf = x.astype(np.float32).transpose(1, 2, 0)
    small = cv2.resize(xf, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    back = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC).transpose(2, 0, 1)
    a = feather(m, 2.0)[None]
    return to_u16(a * back + (1 - a) * x.astype(np.float32)), m, {'facteur': round(f, 2)}

def band_shift(x, donor, size, rng, off):
    # décalage d'une bande de 1 à 2 pixels (indice de parallaxe entre bandes)
    C, H, W = x.shape
    m = random_mask(H, W, size, rng)
    band = int(rng.integers(0, C))
    dy = dx = 0
    while dy == 0 and dx == 0:
        dy, dx = int(rng.integers(-2, 3)), int(rng.integers(-2, 3))
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    sh = cv2.warpAffine(x[band].astype(np.float32), M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    a = feather(m, 2.0)
    out = x.astype(np.float32).copy()
    out[band] = a * sh + (1 - a) * out[band]
    return to_u16(out), m, {'bande': BANDS[band], 'dy': dy, 'dx': dx}

FAMILIES = {
    'copy_move': copy_move, 'splice': splice, 'class_swap': class_swap, 'rotate': rotate_region,
    'scale': scale_region, 'spectral': spectral_edit, 'photometric': photometric_region,
    'noise': noise_region, 'blur': blur_region, 'jpeg': jpeg_region, 'object_insert': object_insert,
    'inpaint': inpaint_telea, 'inpaint_ns': inpaint_ns, 'cloud': cloud_region,
    'resample': resample_region, 'band_shift': band_shift, 'rotate_big': rotate_big,
}

TRAIN_FAMILIES = ['copy_move', 'splice', 'class_swap', 'rotate', 'scale', 'spectral', 'photometric',
                  'noise', 'blur', 'jpeg', 'object_insert']

HELDOUT_FAMILIES = ['inpaint', 'inpaint_ns', 'cloud', 'resample', 'band_shift', 'rotate_big']

ALL_FAMILIES = TRAIN_FAMILIES + HELDOUT_FAMILIES

COMPOUND_POOL = ['copy_move', 'splice', 'class_swap', 'rotate', 'scale', 'spectral', 'photometric', 'noise', 'blur', 'jpeg']

COMPOUND_MIXED_POOL = COMPOUND_POOL + ['inpaint', 'resample', 'cloud']

EVAL_FAMILIES = ALL_FAMILIES + ['compound', 'compound_mixed']

def compound(x, donor, off, rng, severity, pool):
    k = int(rng.integers(2, 4))
    chain = [str(n) for n in rng.choice(pool, size=k, replace=False)]
    cur = x
    mask = np.zeros(x.shape[1:], np.uint8)
    recs = []
    for n in chain:
        cur, m, r = _single_attack(cur, donor, n, severity, rng, off)
        mask |= m
        recs.append({'attack_type': n, 'parameters': r['parameters']})
    return cur, mask, {'attack_type': 'compound', 'severity': severity, 'chain': recs}

def _single_attack(x, donor, name, severity, rng, off):
    lo, hi = SEVERITY[severity]
    size = int(rng.integers(lo, hi + 1))
    out, mask, params = FAMILIES[name](x, donor, size, rng, off)
    return out, mask, {'attack_type': name, 'severity': severity, 'size': size, 'parameters': params}

def make_attack(x, donor, name, severity, rng, off):
    if name in ('compound', 'compound_mixed'):
        pool = COMPOUND_POOL if name == 'compound' else COMPOUND_MIXED_POOL
        out, mask, rec = compound(x, donor, off, rng, severity, pool)
        rec['attack_type'] = name
    else:
        out, mask, rec = _single_attack(x, donor, name, severity, rng, off)
    rec['detectability'] = round(detectability(x, out, mask), 2)
    return out, mask, rec

def benign(x, rng, gain=0.03, noise=10.0, vary=False):
    # variation légitime (gain global + bruit de capteur) : appliquée aux DEUX classes
    g = rng.uniform(1.0 - gain, 1.0 + gain)
    s = noise * (rng.uniform(0.25, 1.0) if vary else 1.0)
    n = rng.normal(0, s, x.shape)
    return to_u16(x.astype(np.float32) * g + n)
