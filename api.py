"""Local ground-station API for signed Sentinel-2 chip packets."""

from __future__ import annotations

import base64
import io
import json
import math
import os
import threading
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from tp.device_protocol import PACKET_LEN, parse_packet
from tp.engine import TrustPipeline
from tp.provenance import public_key_id
from tp.model_fetch import ensure_model

MAX_BODY = 6 * 1024 * 1024
EVENTS_PATH = Path(os.environ.get('TP_EVENTS_PATH', 'events.jsonl'))
EVENTS_DATA_DIR = Path(os.environ.get('TP_EVENTS_DATA_DIR', 'events_data'))
EVENTS_ARCHIVE_DIR = Path(os.environ.get('TP_EVENTS_ARCHIVE_DIR', 'events_archive'))
_event_lock = threading.Lock()
_event_id = 0
_pipeline: TrustPipeline | None = None
_startup_error: str | None = None
app = FastAPI(title='earthLens Ground Station', version='0.1.0')


def load_trusted_keys(directory: str | Path = 'trusted_keys') -> dict[str, Ed25519PublicKey]:
    keys: dict[str, Ed25519PublicKey] = {}
    root = Path(directory)
    if not root.exists():
        return keys
    for path in sorted(root.glob('*.pem')):
        key = serialization.load_pem_public_key(path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError(f'{path.name} is not an Ed25519 public key.')
        keys[public_key_id(key)] = key
    return keys


def configure_pipeline(model_dir: str | Path = 'model', keys_dir: str | Path = 'trusted_keys') -> None:
    global _pipeline, _startup_error
    try:
        ensure_model(model_dir)
        _pipeline = TrustPipeline.ground_station(load_trusted_keys(keys_dir), str(model_dir))
        _startup_error = None
    except Exception as exc:
        _pipeline = None
        _startup_error = f'{type(exc).__name__}: {exc}'


configure_pipeline()


def _malformed() -> JSONResponse:
    return JSONResponse({'status': 'COMPROMISED', 'reasons': ['Malformed packet'], 'score': None, 'trust': None,
                         'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED', 'replay': False, 'changed_tiles': []})


def _valid_manifest(manifest: Any) -> bool:
    if not isinstance(manifest, dict):
        return False
    strings = ('obs_id', 'sensor', 'key_id', 'time_utc', 'issued_utc', 'scene', 'tile', 'dtype', 'nonce', 'sha256', 'merkle_root')
    if any(not isinstance(manifest.get(k), str) or not manifest[k] for k in strings):
        return False
    if manifest['dtype'] != 'uint16' or len(manifest['sha256']) != 64 or len(manifest['merkle_root']) != 64:
        return False
    if any(c not in '0123456789abcdef' for c in manifest['sha256'].lower() + manifest['merkle_root'].lower()):
        return False
    if not isinstance(manifest.get('shape'), list) or manifest['shape'] != [4, 256, 256]:
        return False
    if not isinstance(manifest.get('tile_hashes'), list) or len(manifest['tile_hashes']) != 64:
        return False
    if any(not isinstance(v, str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v.lower()) for v in manifest['tile_hashes']):
        return False
    geo = manifest.get('geo')
    if not isinstance(geo, list) or len(geo) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in geo):
        return False
    if not -180 <= geo[0] <= 180 or not -90 <= geo[1] <= 90:
        return False
    window = manifest.get('window')
    if not isinstance(window, list) or len(window) != 2 or any(type(v) is not int for v in window):
        return False
    if type(manifest.get('offset')) is not int or manifest['offset'] not in (0, 1000):
        return False
    if type(manifest.get('counter')) is not int or manifest['counter'] < 1:
        return False
    return True


def _append_event(event: dict[str, Any]) -> dict[str, Any]:
    global _event_id
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _event_lock:
        seq = _event_id
        if EVENTS_PATH.exists():
            with EVENTS_PATH.open('r', encoding='utf-8') as handle:
                seq = max([seq, *(_event_number(line) for line in handle if line.strip())])
        _event_id = seq + 1
        record = {'event_id': _event_id, 'seq': _event_id - 1, **event}
        with EVENTS_PATH.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
    return record


def _event_number(line: str) -> int:
    try:
        return int(json.loads(line).get('event_id', 0))
    except (ValueError, TypeError, AttributeError):
        return 0


def _place_for_geo(lon: float | None, lat: float | None) -> str:
    if lon is None or lat is None:
        return 'unknown'
    from tp.pack import list_places, _distance_km
    nearest = min(((_distance_km(lon, lat, *row['center']), row['place']) for row in list_places()), default=None)
    return nearest[1] if nearest and nearest[0] <= 30 else 'unknown'


def _write_images(event_id: int, pixels: np.ndarray, probability: Any) -> None:
    from PIL import Image
    rgb = np.stack([pixels[2], pixels[1], pixels[0]], axis=-1).astype(np.float32)
    low, high = np.percentile(rgb, [2, 98])
    rgb = np.zeros_like(rgb, dtype=np.uint8) if high <= low else np.clip((rgb - low) * (255.0 / (high - low)), 0, 255).astype(np.uint8)
    EVENTS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode='RGB').save(EVENTS_DATA_DIR / f'{event_id}_rgb.png', optimize=True)
    prob = np.asarray(probability if probability is not None else np.zeros((256, 256)), dtype=np.float32)
    prob = np.nan_to_num(prob.reshape(256, 256), nan=0.0, posinf=1.0, neginf=0.0).clip(0, 1)
    red = (prob * 255).astype(np.uint8)
    rgba = np.stack([red, np.zeros_like(red), 255 - red, (prob * 220).astype(np.uint8)], axis=-1)
    Image.fromarray(rgba, mode='RGBA').save(EVENTS_DATA_DIR / f'{event_id}_heat.png', optimize=True)


def _malformed_event(manifest: Any = None, assumed_mode: str = 'unknown') -> dict[str, Any]:
    if _pipeline is not None:
        _pipeline.audit_log.add({'scene': None, 'status': 'COMPROMISED', 'score': None, 'kind': 'malformed', 'obs_id': None})
    geo = manifest.get('geo') if isinstance(manifest, dict) else None
    lon, lat = (geo[0], geo[1]) if isinstance(geo, list) and len(geo) == 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in geo) else (None, None)
    return _append_event({'time_utc': datetime.now(timezone.utc).isoformat(), 'status': 'COMPROMISED', 'status_raw': 'COMPROMISED',
        'reasons': ['Malformed packet'], 'score': None, 'trust': None, 'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED',
        'replay': False, 'changed_tiles': [], 'lon': lon, 'lat': lat, 'place': _place_for_geo(lon, lat),
        'scene': manifest.get('scene') if isinstance(manifest, dict) else None,
        'date': manifest.get('time_utc') if isinstance(manifest, dict) else None,
        'window': manifest.get('window') if isinstance(manifest, dict) else None,
        'plausible': None, 't_low': None, 't_high': None, 'assumed_mode': assumed_mode})


def _record(pkg: dict[str, Any], mode: str) -> dict[str, Any]:
    """Run the trust pipeline on one parsed packet, store the event and its images, and build the response."""
    if _pipeline is None:
        raise RuntimeError('pipeline unavailable')
    manifest, pixels = pkg['manifest'], pkg['pixels']
    result = _pipeline.process(pkg, kind=mode)
    evidence = result['evidence']
    response = {'status': result['status'], 'reasons': result['reasons'], 'score': evidence['score'],
                'trust': evidence['trust'], 'provenance': evidence['provenance'], 'integrity': evidence['integrity'],
                'replay': evidence['replay'], 'changed_tiles': evidence['changed_tiles'],
                'chain': evidence.get('chain', 'N/A'), 'copy_move': evidence.get('copy_move')}
    geo = manifest['geo']
    event = _append_event({'time_utc': datetime.now(timezone.utc).isoformat(), 'status': result['status'],
        'status_raw': result.get('status_raw', result['status']), 'reasons': result['reasons'],
        'score': evidence['score'], 'trust': evidence['trust'], 'provenance': evidence['provenance'],
        'integrity': evidence['integrity'], 'replay': evidence['replay'], 'changed_tiles': evidence['changed_tiles'],
        'chain': evidence.get('chain', 'N/A'), 'copy_move': evidence.get('copy_move'),
        'lon': geo[0], 'lat': geo[1], 'place': _place_for_geo(geo[0], geo[1]),
        'scene': manifest['scene'], 'date': manifest['time_utc'],
        'window': manifest['window'], 'plausible': evidence['plausible'],
        't_low': evidence['t_low'], 't_high': evidence['t_high'], 'assumed_mode': mode})
    _write_images(event['event_id'], pixels, result.get('prob'))
    return response


@app.post('/ingest')
async def ingest(request: Request):
    raw = bytearray()
    mode = request.headers.get('x-attack-mode', 'unknown')[:40]
    manifest = None
    try:
        if request.headers.get('content-length') and int(request.headers['content-length']) > MAX_BODY:
            _malformed_event(assumed_mode=mode)
            return _malformed()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                _malformed_event(assumed_mode=mode)
                return _malformed()
        body = json.loads(raw)
        manifest = body.get('manifest') if isinstance(body, dict) else None
        if not isinstance(body, dict) or set(('pixels', 'manifest', 'signature')) - body.keys():
            raise ValueError('missing fields')
        if not isinstance(body['pixels'], str) or (body['signature'] is not None and not isinstance(body['signature'], str)):
            raise ValueError('invalid field types')
        if not _valid_manifest(body['manifest']):
            raise ValueError('invalid manifest')
        npy = base64.b64decode(body['pixels'], validate=True)
        if len(npy) > MAX_BODY:
            raise ValueError('oversized array')
        pixels = np.load(io.BytesIO(npy), allow_pickle=False)
        if not isinstance(pixels, np.ndarray) or pixels.shape != (4, 256, 256) or pixels.dtype != np.uint16:
            raise ValueError('invalid array contract')
        pkg = {'pixels': pixels, 'manifest': body['manifest'], 'signature': body['signature']}
        return _record(pkg, mode)
    except Exception:
        try:
            _malformed_event(manifest, mode)
        except Exception:
            pass
        return _malformed()


@app.post('/ingest_v2')
async def ingest_v2(request: Request):
    """Receive a binary TPX2 device packet (header, signature, raw pixels)."""
    raw = bytearray()
    mode = request.headers.get('x-attack-mode', 'unknown')[:40]
    manifest = None
    try:
        if request.headers.get('content-length') and int(request.headers['content-length']) > PACKET_LEN:
            raise ValueError('oversized packet')
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > PACKET_LEN:
                raise ValueError('oversized packet')
        pkg = parse_packet(bytes(raw))
        manifest = pkg['manifest']
        return _record(pkg, mode)
    except Exception:
        try:
            _malformed_event(manifest, mode)
        except Exception:
            pass
        return _malformed()


@app.post('/analyze')
async def analyze(request: Request):
    """Verify and analyze one signed chip without adding it to the live event feed."""
    raw = bytearray()
    try:
        if request.headers.get('content-length') and int(request.headers['content-length']) > MAX_BODY:
            raise HTTPException(status_code=413, detail='Request exceeds the configured size limit.')
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise HTTPException(status_code=413, detail='Request exceeds the configured size limit.')
        body = json.loads(raw)
        if not isinstance(body, dict) or set(('pixels', 'manifest', 'signature')) - body.keys():
            raise ValueError('missing fields')
        if not isinstance(body['pixels'], str) or not isinstance(body['signature'], str):
            raise ValueError('invalid field types')
        if not _valid_manifest(body['manifest']):
            raise ValueError('invalid manifest')
        npy = base64.b64decode(body['pixels'], validate=True)
        pixels = np.load(io.BytesIO(npy), allow_pickle=False)
        if pixels.shape != (4, 256, 256) or pixels.dtype != np.uint16:
            raise ValueError('invalid array contract')
        if _pipeline is None:
            raise HTTPException(status_code=503, detail='Backend model pipeline is unavailable.')
        result = _pipeline.process(
            {'pixels': pixels, 'manifest': body['manifest'], 'signature': body['signature']},
            cloud_ctx=body.get('cloud_ctx') if isinstance(body.get('cloud_ctx'), dict) else None,
            kind='dashboard_analysis',
        )
        return {'result': result, 'manifest': body['manifest'], 'signature': body['signature']}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Invalid analysis packet ({type(exc).__name__}).') from exc


@app.get('/health')
def health():
    return {'ok': _pipeline is not None, 'trusted_keys': len(_pipeline.ground.trusted) if _pipeline else 0,
            'trusted_key_ids': sorted(_pipeline.ground.trusted) if _pipeline else [],
            'error': _startup_error, 'anti_replay': 'In-memory anti-replay state resets when the server restarts.'}


@app.get('/events')
def events(since: int = 0, limit: int = 100):
    if since < 0:
        return JSONResponse({'error': 'since must be non-negative'}, status_code=400)
    if limit < 1 or limit > 1000:
        return JSONResponse({'error': 'limit must be between 1 and 1000'}, status_code=400)
    rows = []
    try:
        with EVENTS_PATH.open('r', encoding='utf-8') as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get('seq', row.get('event_id', 0)) >= since:
                    rows.append(row)
    except FileNotFoundError:
        pass
    except OSError:
        pass
    return {'events': rows[:limit]}


@app.post('/reset-events')
def reset_events(request: Request):
    host = request.client.host if request.client else ''
    if host not in {'127.0.0.1', '::1', 'localhost', 'testclient'}:
        return JSONResponse({'error': 'This endpoint is available only from localhost.'}, status_code=403)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    archive = EVENTS_ARCHIVE_DIR / stamp
    with _event_lock:
        if EVENTS_PATH.exists() or EVENTS_DATA_DIR.exists():
            archive.mkdir(parents=True, exist_ok=False)
            if EVENTS_PATH.exists():
                shutil.move(str(EVENTS_PATH), str(archive / EVENTS_PATH.name))
            if EVENTS_DATA_DIR.exists():
                shutil.move(str(EVENTS_DATA_DIR), str(archive / EVENTS_DATA_DIR.name))
    return {'ok': True, 'archive': stamp}
