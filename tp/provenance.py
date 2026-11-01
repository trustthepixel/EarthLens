import copy
import datetime as _dt
import hashlib
import json
import uuid

import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tp.attacks import ALL_FAMILIES, DEFAULT_OFFSET, SEV_ALL, make_attack

TILE = 32

def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('utf-8')

def pixel_bytes(arr):
    return np.ascontiguousarray(arr, dtype=np.uint16).tobytes()

def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()

def tile_hashes(arr, tile=TILE):
    C, H, W = arr.shape
    a = np.ascontiguousarray(arr, dtype=np.uint16)
    return [sha256_hex(a[:, y:y + tile, x:x + tile].tobytes()) for y in range(0, H, tile) for x in range(0, W, tile)]

def merkle_root_hex(leaves):
    level = [bytes.fromhex(h) for h in leaves]
    if not level:
        return sha256_hex(b'')
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest() for i in range(0, len(level), 2)]
    return level[0].hex()

def public_key_id(pub):
    raw = pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(raw).hexdigest()[:16]

def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

class Source:
    # « satellite » : seul détenteur de la clé privée ; produit un paquet signé
    def __init__(self, sensor_id='SENTINEL-2-L2A', sk=None):
        self._sk = sk if sk is not None else Ed25519PrivateKey.generate()
        self.public_key = self._sk.public_key()
        self.key_id = public_key_id(self.public_key)
        self.sensor_id = sensor_id
        self.counter = 0

    def acquire(self, arr, meta):
        arr = np.ascontiguousarray(arr, dtype=np.uint16).copy()
        self.counter += 1
        leaves = tile_hashes(arr)
        manifest = {
            'obs_id': str(uuid.uuid4()), 'sensor': self.sensor_id, 'key_id': self.key_id,
            'time_utc': str(meta.get('date', '')), 'issued_utc': _now_iso(),
            'geo': [float(meta.get('lon', 0.0)), float(meta.get('lat', 0.0))],
            'scene': str(meta.get('scene', '')), 'tile': str(meta.get('tile', '')),
            'window': [int(meta.get('r0', 0)), int(meta.get('c0', 0))],
            'shape': list(arr.shape), 'dtype': 'uint16', 'offset': int(meta.get('offset', DEFAULT_OFFSET)),
            'counter': self.counter, 'nonce': uuid.uuid4().hex,
            'sha256': sha256_hex(pixel_bytes(arr)), 'merkle_root': merkle_root_hex(leaves), 'tile_hashes': leaves,
        }
        sig = self._sk.sign(canonical(manifest)).hex()
        return {'pixels': arr, 'manifest': manifest, 'signature': sig}

class Ground:
    # station sol : ne détient que des clés publiques épinglées ; garde la mémoire anti-rejeu
    def __init__(self, trusted_keys, allowed_sensors=('SENTINEL-2-L2A',), aoi_boxes=None, tolerance_days=1):
        self.trusted = dict(trusted_keys)                  # key_id -> clé publique
        self.allowed_sensors = set(allowed_sensors)
        self.aoi_boxes = aoi_boxes                          # liste de (lon_min, lat_min, lon_max, lat_max) ou None
        self.tolerance_days = tolerance_days
        self.seen_nonces, self.last_counter = set(), {}

    def verify(self, pkg):
        res = {'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED', 'replay': False, 'plausible': True,
               'changed_tiles': [], 'reasons': []}
        man, arr, sig = pkg.get('manifest'), pkg.get('pixels'), pkg.get('signature')
        if man is None or arr is None:
            res['reasons'].append('paquet incomplet (manifeste ou pixels absents)')
            return res
        # 1) signature
        kid = man.get('key_id')
        pub = self.trusted.get(kid)
        if not sig:
            res['reasons'].append('signature absente : origine non vérifiable')
        elif pub is None:
            res['provenance'] = 'INVALID'
            res['reasons'].append(f'clé inconnue ({kid}) : signataire non reconnu')
        else:
            try:
                pub.verify(bytes.fromhex(sig), canonical(man))
                res['provenance'] = 'VALID'
            except (InvalidSignature, ValueError):
                res['provenance'] = 'INVALID'
                res['reasons'].append('signature invalide : manifeste modifié ou signé par un tiers')
        # 2) intégrité des pixels (le manifeste n'est digne de confiance que si la signature est valide)
        if res['provenance'] == 'VALID':
            ok_shape = list(arr.shape) == list(man['shape']) and str(arr.dtype) == man['dtype']
            same = ok_shape and sha256_hex(pixel_bytes(arr)) == man['sha256']
            res['integrity'] = 'PASS' if same else 'FAIL'
            if not same:
                res['reasons'].append('empreinte SHA-256 différente : pixels modifiés après la signature')
                if ok_shape:
                    now = tile_hashes(arr)
                    res['changed_tiles'] = [i for i, (a, b) in enumerate(zip(now, man['tile_hashes'])) if a != b]
            # 3) rejeu
            if man['nonce'] in self.seen_nonces or man['counter'] <= self.last_counter.get(kid, 0):
                res['replay'] = True
                res['reasons'].append('rejeu : nonce déjà vu ou compteur non croissant')
            else:
                self.seen_nonces.add(man['nonce'])
                self.last_counter[kid] = man['counter']
            # 4) plausibilité des métadonnées
            if man.get('sensor') not in self.allowed_sensors:
                res['plausible'] = False; res['reasons'].append('capteur non autorisé')
            try:
                t = _dt.datetime.strptime(str(man['time_utc'])[:10], '%Y-%m-%d').replace(tzinfo=_dt.timezone.utc)
                if t > _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=self.tolerance_days):
                    res['plausible'] = False; res['reasons'].append('date d\'acquisition dans le futur')
            except ValueError:
                res['plausible'] = False; res['reasons'].append('date d\'acquisition illisible')
            if self.aoi_boxes:
                lon, lat = man['geo']
                if not any(b[0] <= lon <= b[2] and b[1] <= lat <= b[3] for b in self.aoi_boxes):
                    res['plausible'] = False; res['reasons'].append('position hors des zones attendues')
        return res

CHANNEL_ATTACKS = ['pixels', 'manifest_meta', 'manifest_rehash', 'resign', 'replay', 'strip']

def channel_attack(pkg, kind, rng, donor=None, old_pkg=None):
    # renvoie (paquet attaqué, vérité terrain {'mask': ..., 'detail': ...}) ; la vérité n'est jamais transmise à la station sol
    pk = {'pixels': pkg['pixels'].copy(), 'manifest': copy.deepcopy(pkg['manifest']), 'signature': pkg['signature']}
    off = float(pk['manifest']['offset'])
    truth = {'mask': None, 'detail': kind}
    def tamper_pixels():
        name = str(rng.choice(ALL_FAMILIES))
        d = donor if donor is not None else np.roll(pk['pixels'], 37, axis=2)
        for _ in range(6):
            out, m, rec = make_attack(pk['pixels'], d, name, str(rng.choice(SEV_ALL)), rng, off)
            if m.sum() > 0:
                break
        truth['mask'] = m; truth['detail'] = f'{kind}:{name}'
        return out
    if kind == 'pixels':
        pk['pixels'] = tamper_pixels()
    elif kind == 'manifest_meta':
        field = str(rng.choice(['geo', 'time_utc', 'scene', 'sensor']))
        if field == 'geo': pk['manifest']['geo'] = [pk['manifest']['geo'][0] + 0.5, pk['manifest']['geo'][1] - 0.4]
        elif field == 'time_utc': pk['manifest']['time_utc'] = '2019-01-01'
        elif field == 'scene': pk['manifest']['scene'] = 'FAUX_' + pk['manifest']['scene']
        else: pk['manifest']['sensor'] = 'CAMERA-INCONNUE'
        truth['detail'] = f'{kind}:{field}'
    elif kind == 'manifest_rehash':        # l'attaquant recalcule tous les hash mais ne peut pas re-signer
        pk['pixels'] = tamper_pixels()
        leaves = tile_hashes(pk['pixels'])
        pk['manifest'].update({'sha256': sha256_hex(pixel_bytes(pk['pixels'])), 'tile_hashes': leaves,
                               'merkle_root': merkle_root_hex(leaves)})
    elif kind == 'resign':                 # l'attaquant signe avec sa propre clé
        pk['pixels'] = tamper_pixels()
        evil = Source(sensor_id=pk['manifest']['sensor'])
        evil.counter = int(pk['manifest']['counter'])
        fake = evil.acquire(pk['pixels'], {'date': pk['manifest']['time_utc'], 'lon': pk['manifest']['geo'][0],
                                           'lat': pk['manifest']['geo'][1], 'scene': pk['manifest']['scene'],
                                           'tile': pk['manifest']['tile'], 'offset': pk['manifest']['offset']})
        pk = fake
    elif kind == 'replay':
        pk = {'pixels': old_pkg['pixels'].copy(), 'manifest': copy.deepcopy(old_pkg['manifest']), 'signature': old_pkg['signature']}
    elif kind == 'strip':
        pk['pixels'] = tamper_pixels(); pk['signature'] = None
    else:
        raise ValueError(kind)
    return pk, truth

def decide(ver, score, t_low, t_high):
    # moteur de confiance : combine les preuves déterministes (signature) et la preuve statistique (IA)
    why = list(ver['reasons'])
    if ver['integrity'] == 'FAIL' or ver['provenance'] == 'INVALID' or ver['replay']:
        return 'COMPROMISED', why
    if score is not None and score >= t_high:
        return 'COMPROMISED', why + [f'anomalie de contenu forte (score {score:.2f} ≥ {t_high:.2f})']
    if not ver['plausible']:
        return 'SUSPICIOUS', why
    if ver['provenance'] == 'UNKNOWN':
        return 'SUSPICIOUS', why + ['origine non vérifiée']
    if score is not None and score >= t_low:
        return 'SUSPICIOUS', why + [f'anomalie de contenu (score {score:.2f} ≥ {t_low:.2f})']
    return 'TRUSTED', why

class AuditLog:
    # journal chaîné par hash : toute modification d'une ligne passée casse la chaîne
    def __init__(self):
        self.entries, self.prev = [], '0' * 64
    def add(self, record):
        body = {'t': _now_iso(), 'prev': self.prev, 'record': record}
        h = sha256_hex(canonical(body))
        self.entries.append({**body, 'hash': h}); self.prev = h
        return h
    def verify(self):
        prev = '0' * 64
        for e in self.entries:
            body = {'t': e['t'], 'prev': e['prev'], 'record': e['record']}
            if e['prev'] != prev or sha256_hex(canonical(body)) != e['hash']:
                return False
            prev = e['hash']
        return True
