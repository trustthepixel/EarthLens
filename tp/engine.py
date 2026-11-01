"""Orchestrate provenance verification, contract checks, and ONNX analysis."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Any

import numpy as np

from tp.contract import validate_chip
from tp.onnx_analyzer import OnnxAnalyzer
from tp.chain import ChainedSource, decide_chained
from tp.device_protocol import DeviceGround
from tp.forensics import copy_move
from tp.provenance import AuditLog
from tp.sentinel_live import REGIONS

APP_VERSION = '0.1.0'


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')


def _serializable(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _manifest_meta(manifest: Any) -> dict[str, Any] | None:
    if not isinstance(manifest, dict):
        return None
    geo = manifest.get('geo')
    try:
        lon, lat = float(geo[0]), float(geo[1])
    except (TypeError, ValueError, IndexError, KeyError):
        lon, lat = None, None
    meta: dict[str, Any] = {
        'scene': manifest.get('scene'),
        'tile': manifest.get('tile'),
        'offset': manifest.get('offset'),
        'lon': lon,
        'lat': lat,
    }
    if lon is not None and lat is not None and -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
        zone = min(60, max(1, int((lon + 180.0) // 6.0) + 1))
        meta['epsg'] = (32600 if lat >= 0 else 32700) + zone
    return meta


class TrustPipeline:
    """Process signed demonstration packets through provenance and model checks."""

    def __init__(self, model_dir: str = 'model', aoi_margin_deg: float = 1.0, source=None):
        if isinstance(aoi_margin_deg, bool) or not isinstance(aoi_margin_deg, (int, float)) or not math.isfinite(float(aoi_margin_deg)) or aoi_margin_deg < 0:
            raise ValueError('aoi_margin_deg must be a finite non-negative number.')
        self.analyzer = OnnxAnalyzer(model_dir)
        self.source = source if source is not None else ChainedSource()
        margin = float(aoi_margin_deg)
        boxes = [
            (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)
            for bbox in REGIONS.values()
        ]
        self.ground = DeviceGround({self.source.key_id: self.source.public_key}, aoi_boxes=boxes)
        self.audit_log = AuditLog()

    @classmethod
    def ground_station(cls, trusted_keys: dict[str, Any], model_dir: str = 'model', aoi_margin_deg: float = 1.0):
        """Create a verifier-only pipeline; this instance never holds a source key."""
        if isinstance(aoi_margin_deg, bool) or not isinstance(aoi_margin_deg, (int, float)) or not math.isfinite(float(aoi_margin_deg)) or aoi_margin_deg < 0:
            raise ValueError('aoi_margin_deg must be a finite non-negative number.')
        self = cls.__new__(cls)
        self.analyzer = OnnxAnalyzer(model_dir)
        self.source = None
        margin = float(aoi_margin_deg)
        boxes = [(b[0] - margin, b[1] - margin, b[2] + margin, b[3] + margin) for b in REGIONS.values()]
        self.ground = DeviceGround(trusted_keys, aoi_boxes=boxes)
        self.audit_log = AuditLog()
        return self

    def acquire(self, chip: Any, meta: dict[str, Any]) -> dict[str, Any]:
        """Create a signed packet using the pipeline's demonstration source key."""
        return self.source.acquire(chip, meta)

    def process(
        self,
        pkg: Any,
        cloud_ctx: dict[str, Any] | None = None,
        kind: str = 'none',
        progress_callback=None,
    ) -> dict[str, Any]:
        """Verify a packet exactly once, then validate and analyze its image."""
        t_low, t_high = self.analyzer.decision_thresholds()
        if callable(progress_callback):
            progress_callback('Verifying packet...')
        try:
            ver = self.ground.verify(pkg)
        except Exception as exc:
            ver = {
                'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED', 'replay': False,
                'plausible': False, 'changed_tiles': [],
                'reasons': [f'Packet verification failed: {type(exc).__name__}.'],
            }

        if not isinstance(ver, dict):
            ver = {
                'provenance': 'UNKNOWN', 'integrity': 'UNVERIFIED', 'replay': False,
                'plausible': False, 'changed_tiles': [], 'reasons': ['Packet verification returned an invalid result.'],
            }
        ver = {
            'provenance': ver.get('provenance', 'UNKNOWN'),
            'integrity': ver.get('integrity', 'UNVERIFIED'),
            'replay': bool(ver.get('replay', False)),
            'plausible': bool(ver.get('plausible', False)),
            'changed_tiles': ver.get('changed_tiles', []),
            'reasons': list(ver.get('reasons', [])),
            'chain': ver.get('chain', 'N/A'),
        }
        manifest = pkg.get('manifest') if isinstance(pkg, dict) else None
        pixels = pkg.get('pixels') if isinstance(pkg, dict) else None
        offset = 1000
        if ver['provenance'] == 'VALID' and isinstance(manifest, dict):
            offset = manifest.get('offset', 1000)

        contract = validate_chip(pixels, offset, _manifest_meta(manifest), strict=False)
        contract_reasons = [f"Input contract: {message}" for message in contract['errors']]
        contract_reasons.extend(f"Input warning: {message}" for message in contract['warnings'])

        if callable(progress_callback):
            progress_callback('Running the model...')
        try:
            analysis = self.analyzer.analyze(pixels, offset)
            score = float(analysis['score'])
            trust = float(self.analyzer.trust_index(score))
            latency_ms = float(analysis['latency_ms'])
            prob = _serializable(analysis['prob'])
            logits = _serializable(analysis['logits'])
            raw_status, decided_reasons = decide_chained(ver, score, t_low, t_high)
            status_raw = raw_status
            status = raw_status
            reasons = list(decided_reasons)
            reasons.extend(contract_reasons)
            cloudy = bool((cloud_ctx or {}).get('cloudy', False))
            if (
                cloudy and raw_status == 'COMPROMISED'
                and ver['provenance'] == 'VALID' and ver['integrity'] == 'PASS'
                and not ver['replay'] and ver['plausible']
                and score >= t_high
            ):
                status = 'SUSPICIOUS'
                reasons.append('Cloudy context: AI score alone, not escalated')
            conflict = bool(
                ver['provenance'] == 'VALID' and ver['integrity'] == 'PASS'
                and score >= t_low
            )
            try:
                duplicate_matches = int(copy_move(pixels)[0])
            except Exception:
                duplicate_matches = None
            if duplicate_matches:
                reasons.append(f'Duplicated region found inside the image ({duplicate_matches} matching keypoints)')
                if status == 'TRUSTED':
                    status = 'SUSPICIOUS'
                if status_raw == 'TRUSTED':
                    status_raw = 'SUSPICIOUS'
        except Exception:
            duplicate_matches = None
            score = trust = latency_ms = None
            prob = logits = None
            raw_status, decided_reasons = decide_chained(ver, None, t_low, t_high)
            status_raw = 'COMPROMISED'
            status = 'COMPROMISED'
            reasons = list(decided_reasons)
            reasons.extend(contract_reasons)
            reasons.append('Input could not be analysed')
            conflict = False

        changed_tiles = _serializable(ver['changed_tiles'])
        evidence = {
            'provenance': ver['provenance'],
            'integrity': ver['integrity'],
            'replay': ver['replay'],
            'chain': ver['chain'],
            'copy_move': duplicate_matches,
            'plausible': ver['plausible'],
            'changed_tiles': changed_tiles,
            'score': score,
            'trust': trust,
            'latency_ms': latency_ms,
            't_low': float(t_low),
            't_high': float(t_high),
        }
        result = {
            'status': status,
            'status_raw': status_raw,
            'reasons': reasons,
            'conflict': conflict,
            'evidence': evidence,
            'prob': prob,
            'logits': logits,
            'version_info': self.analyzer.version_info(),
        }
        self.audit_log.add({
            'scene': manifest.get('scene') if isinstance(manifest, dict) else None,
            'status': status,
            'score': round(score, 6) if score is not None else None,
            'kind': str(kind),
            'obs_id': manifest.get('obs_id') if isinstance(manifest, dict) else None,
        })
        return _serializable(result)


def build_report(result: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """Build a privacy-conscious JSON report with a self-excluding SHA-256."""
    evidence = result.get('evidence', {})
    version = result.get('version_info', {})
    report = {
        'scene': str(meta.get('scene', '')),
        'date': str(meta.get('date', '')),
        'tile': str(meta.get('tile', '')),
        'offset': _serializable(meta.get('offset')),
        'status': result.get('status'),
        'raw_status': result.get('status_raw'),
        'reasons': _serializable(result.get('reasons', [])),
        'evidence': _serializable(evidence),
        'scores': {'score': _serializable(evidence.get('score')), 'trust': _serializable(evidence.get('trust'))},
        'thresholds': {'t_low': _serializable(evidence.get('t_low')), 't_high': _serializable(evidence.get('t_high'))},
        'model_version': {key: _serializable(version.get(key)) for key in ('onnx_sha256', 'config_sha256', 'variant')},
        'app_version': APP_VERSION,
        'timestamp_utc': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z'),
    }
    report['report_sha256'] = hashlib.sha256(_canonical_json(report)).hexdigest()
    return report
