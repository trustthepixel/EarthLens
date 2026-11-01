"""Live Copernicus area selection and analysis controls."""

from __future__ import annotations

import json
import time
import base64
import io
from datetime import datetime, timezone

import numpy as np
import requests
import streamlit as st
from rasterio.errors import CRSError

from tp.contract import validate_chip
from tp.engine import build_report
from tp.attacks import ALL_FAMILIES, make_attack
from tp.geo import heatmap_data_uri, mask_contour_data_uri, ndvi_data_uri, rgb_data_uri, warp_to_4326
from tp.sentinel_live import (
    AreaNotUsable,
    NetworkUnavailable,
    REGIONS,
    cloud_context,
    fetch_acquisition,
    list_acquisitions,
    read_chip_at,
)
from tp.pack import load_pack
from ui.status import status_badge
from ui.language import render_legacy_reasons
from tp.settings import api_endpoint


@st.cache_data(ttl=600, show_spinner=False)
def _cached_acquisitions(lon: float, lat: float, days: int = 60, max_cloud: int = 60, n: int = 15):
    return list_acquisitions(lon, lat, days=days, max_cloud=max_cloud, n=n)


def _read_chip_from_acquisitions(item_ids, lon: float, lat: float):
    """Read from the first usable scene, skipping unusable chip or CRS metadata."""
    last_area_error = None
    last_crs_error = None
    for item_id in item_ids:
        try:
            item = fetch_acquisition(item_id)
            return read_chip_at(item, lon, lat)
        except AreaNotUsable as exc:
            last_area_error = exc
        except CRSError as exc:
            last_crs_error = exc
    if last_area_error is not None:
        raise last_area_error
    if last_crs_error is not None:
        raise AreaNotUsable(
            'The available Sentinel-2 scenes have unusable CRS metadata. Select another date or a nearby point.'
        ) from last_crs_error
    raise AreaNotUsable('No usable Sentinel-2 scene is available at this point.')


def _in_training_domain(lon: float, lat: float) -> bool:
    margin = 0.5
    return any(
        west - margin <= lon <= east + margin and south - margin <= lat <= north + margin
        for west, south, east, north in REGIONS.values()
    )


def _network_message(error: NetworkUnavailable) -> str:
    if error.status_code == 429:
        return "The data service is rate limiting requests (HTTP 429). Wait briefly and try again."
    if error.status_code == 403:
        return "The data access token expired or was rejected (HTTP 403). Retry to request a fresh link."
    return "The Copernicus data service is unavailable. Check the network and try again."


def _stretched_rgb(chip: np.ndarray, offset: int) -> np.ndarray:
    reflectance = np.clip((chip[[2, 1, 0]].astype(np.float32) - float(offset)) / 10000.0, 0.0, 1.5)
    channels = []
    for band in reflectance:
        low, high = np.percentile(band, [2, 98])
        scaled = np.zeros_like(band) if high <= low else (band - low) / (high - low)
        channels.append(np.rint(np.clip(scaled, 0.0, 1.0) * 255).astype(np.uint8))
    return np.stack(channels, axis=-1)


@st.cache_data(ttl=900, max_entries=8, show_spinner=False)
def _make_overlays(chip, result, meta, truth=None):
    rgb = _stretched_rgb(chip, int(meta['offset']))
    reflectance = np.clip((chip.astype(np.float32) - float(meta['offset'])) / 10000.0, 0.0, 1.5)
    eps = 1e-6
    ndvi = (reflectance[3] - reflectance[2]) / (reflectance[3] + reflectance[2] + eps)
    probability = np.asarray(result['prob'], dtype=np.float32)
    warped_rgb, bounds = warp_to_4326(rgb, meta)
    warped_ndvi, ndvi_bounds = warp_to_4326(ndvi, meta)
    warped_heatmap, heat_bounds = warp_to_4326(probability, meta)
    overlays = {
        'True colour': {'image': rgb_data_uri(warped_rgb), 'bounds': bounds, 'show': True},
        'NDVI': {'image': ndvi_data_uri(warped_ndvi), 'bounds': ndvi_bounds, 'show': False},
        'Forgery heatmap': {'image': heatmap_data_uri(warped_heatmap), 'bounds': heat_bounds, 'show': result.get('status') != 'TRUSTED'},
    }
    if truth is not None:
        truth_mask = (np.asarray(truth) > 0).astype(np.uint8)
        warped_truth, truth_bounds = warp_to_4326(truth_mask, meta)
        overlays['Ground truth contour'] = {
            'image': mask_contour_data_uri(warped_truth), 'bounds': truth_bounds, 'show': True,
        }
    return overlays


def _send_to_backend(pkg, cloud_ctx=None):
    """Send a signed chip packet to the configured backend for verification and inference."""
    url = api_endpoint('analyze')
    if not url:
        raise AreaNotUsable('TP_API_URL is not configured for backend analysis.')
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(pkg['pixels']), allow_pickle=False)
    payload = {
        'pixels': base64.b64encode(buffer.getvalue()).decode('ascii'),
        'manifest': pkg['manifest'],
        'signature': pkg['signature'],
        'cloud_ctx': cloud_ctx or {},
    }
    response = requests.post(url, json=payload, timeout=90.0)
    response.raise_for_status()
    return response.json()


def _render_process(chip, meta, ctx, *, kind='none', truth=None, where=None, details=None):
    session = st.session_state
    started = time.perf_counter()
    validation = validate_chip(chip, meta['offset'], meta, strict=True)
    if not validation['ok']:
        raise AreaNotUsable('The selected chip failed input validation: ' + ' '.join(validation['errors']))
    cloud = cloud_context(meta)
    if 'bad_frac' not in meta and 'hard' in meta:
        cloud['cloudy'] = bool(meta['hard'])
    package_chip = chip if where != 'In transit (breaks the signature)' else session.get('area_original_chip', chip)
    source = ctx.get('source') or getattr(ctx.get('pipeline'), 'source', None)
    if source is not None:
        if ctx.get('api_configured'):
            source.counter = max(int(source.counter) + 1, time.time_ns())
            source.head = None
        pkg = source.acquire(package_chip, meta)
    elif ctx.get('pipeline') is not None:
        pkg = ctx['pipeline'].acquire(package_chip, meta)
    else:
        raise AreaNotUsable('The packet source is unavailable.')
    obs_id = (pkg.get('manifest') or {}).get('obs_id')
    if obs_id and session.get('area_processed_obs_id') == obs_id and session.get('area_result') is not None:
        return
    session['area_processing_obs_id'] = obs_id
    if where == 'In transit (breaks the signature)':
        pkg['pixels'] = np.asarray(chip).copy()
    progress = st.status('Sending signed packet to the backend...' if ctx.get('api_configured') else 'Verifying packet...', expanded=True)
    with progress:
        def show_stage(label):
            progress.update(label=label, state='running')
        if ctx.get('api_configured'):
            body = _send_to_backend(pkg, cloud)
            result = body['result']
            pkg = {
                'pixels': np.asarray(chip).copy(),
                'manifest': body['manifest'],
                'signature': body['signature'],
            }
        else:
            if ctx.get('pipeline') is None:
                raise AreaNotUsable('Neither the configured backend nor the local model is available.')
            result = ctx['pipeline'].process(pkg, cloud_ctx=cloud, kind=kind, progress_callback=show_stage)
        elapsed_ms = (time.perf_counter() - started) * 1000
        progress.update(label='Analysis complete', state='complete')
    session['area_packet'] = pkg
    session['area_cloud'] = cloud
    session['area_chip'] = np.asarray(chip).copy()
    session['area_meta'] = dict(meta)
    session['area_validation'] = validation
    session['area_result'] = result
    session['area_processed_obs_id'] = session.pop('area_processing_obs_id', obs_id)
    session['area_last_elapsed_ms'] = elapsed_ms
    session['area_last_source'] = 'prepared' if session.get('area_data_source') == 'Prepared unseen data (offline)' else 'live'
    history = list(session.get('area_analysis_history', []))
    history.append({
        'time_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'scene': str(meta.get('scene') or 'Unknown scene'),
        'date': str(meta.get('date') or 'Unknown date'),
        'source': session['area_last_source'],
        'status': str(result.get('status') or 'UNKNOWN'),
        'score': (result.get('evidence') or {}).get('score'),
        'elapsed_ms': elapsed_ms,
    })
    session['area_analysis_history'] = history[-10:]
    session['area_truth'] = None if truth is None else np.asarray(truth).copy()
    session['area_attack_details'] = details
    session['area_overlays'] = _make_overlays(chip, result, meta, truth)
    session['area_show_rgb'] = True
    session['area_show_ndvi'] = False
    session['area_show_heatmap'] = result.get('status') != 'TRUSTED'
    session['area_original_chip'] = np.asarray(chip).copy() if kind == 'none' else session.get('area_original_chip', np.asarray(chip).copy())
    session['area_original_meta'] = dict(meta) if kind == 'none' else session.get('area_original_meta', dict(meta))
    if kind == 'none':
        session['area_original_result'] = result
        session['area_original_overlays'] = dict(session['area_overlays'])
    session['map_center'] = {'lat': float(meta['lat']), 'lng': float(meta['lon'])}
    session['map_zoom'] = 14


def _distance_km(lon_a, lat_a, lon_b, lat_b):
    from math import asin, cos, radians, sin, sqrt
    p1, p2 = radians(lat_a), radians(lat_b)
    value = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin(radians(lon_b - lon_a) / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(value)))


def _nearest_prepared_place(point, places):
    if not point:
        return None
    choices = [( _distance_km(point['lon'], point['lat'], row['center'][0], row['center'][1]), row)
                for row in places]
    if not choices:
        return None
    distance, row = min(choices, key=lambda value: value[0])
    return row if distance <= 30.0 else None


def _draw_attack_controls(ctx, entries):
    session = st.session_state
    original = session.get('area_original_chip')
    original_meta = session.get('area_original_meta')
    if original is None or original_meta is None or not ctx.get('analysis_available', ctx.get('pipeline') is not None):
        return
    with st.expander('Simulate tampering (local test)', expanded=False):
        family = st.selectbox('Forgery family', [*ALL_FAMILIES, 'compound', 'compound_mixed'], key='area_attack_family')
        severity = st.selectbox('Severity', ['subtle', 'medium', 'strong'], index=2, key='area_attack_severity')
        seed = st.number_input('Seed', min_value=0, max_value=2**31 - 1, value=1, step=1, key='area_attack_seed')
        where = st.radio('Where', ['At the source (valid signature, the AI must catch it)',
                                   'In transit (breaks the signature)'], key='area_attack_where')
        if st.button('Apply and analyse', type='primary', key='area_apply_attack'):
            donor_entry = next((entry for entry in entries
                                if entry.get('pixels_path') != session.get('area_original_path')),
                               None)
            donor = donor_entry['pixels'] if donor_entry is not None else np.roll(original, 37, axis=2)
            attacked, truth, details = make_attack(
                np.asarray(original), np.asarray(donor), family, severity,
                np.random.default_rng(int(seed)), int(original_meta['offset']),
            )
            try:
                _render_process(attacked, original_meta, ctx, kind='local_tampering', truth=truth,
                                where=where, details=details)
                session['area_attack_where_value'] = where
            except Exception as exc:
                st.error(f'Tampering analysis failed ({type(exc).__name__}).')
        if st.button('Reset to original chip', key='area_reset_attack'):
            session['area_chip'] = np.asarray(original).copy()
            session['area_meta'] = dict(original_meta)
            session['area_result'] = session.get('area_original_result')
            session['area_overlays'] = dict(session.get('area_original_overlays', {}))
            session['area_truth'] = None
            session['area_attack_details'] = None
            session['area_show_heatmap'] = session['area_result'].get('status') != 'TRUSTED' if session.get('area_result') else False
            st.rerun()


def _draw_result(result, meta, backend=False):
    st.markdown('<div class="tp-section-label">Analysis result</div>', unsafe_allow_html=True)
    st.markdown(status_badge(result.get('status', 'UNKNOWN')), unsafe_allow_html=True)
    evidence = result.get('evidence') or {}
    score, low, high = evidence.get('score'), evidence.get('t_low'), evidence.get('t_high')
    if score is not None and low is not None and high is not None:
        extent = max(float(high) * 1.35, float(score) * 1.15, 1e-6)
        score_pct = min(100.0, max(0.0, 100.0 * float(score) / extent))
        low_pct, high_pct = 100.0 * float(low) / extent, 100.0 * float(high) / extent
        st.markdown(
            '<div class="tp-score-track"><div class="tp-score-fill" style="width:'
            f'{score_pct:.2f}%"></div><i style="left:{low_pct:.2f}%"></i><b style="left:{high_pct:.2f}%"></b></div>'
            f'<div class="tp-score-label">Score {float(score):.4f} | t_low {float(low):.4f} | t_high {float(high):.4f}</div>',
            unsafe_allow_html=True,
        )
    st.markdown(f"<span title='Trust index combines provenance, integrity, replay, and plausibility evidence.'>Trust index</span>: {evidence.get('trust', 'N/A')}", unsafe_allow_html=True)
    st.markdown(f"Scene: {meta['scene']} | Date: {meta['date']} | <span title='Sentinel processing baseline offset, either 0 or 1000 DN.'>Offset</span>: {meta['offset']}", unsafe_allow_html=True)
    bad_fraction = meta.get('bad_frac')
    haze_fraction = meta.get('haze_frac')
    bad_text = f'{float(bad_fraction) * 100:.1f}%' if bad_fraction is not None else 'unavailable'
    haze_text = f'{float(haze_fraction) * 100:.1f}%' if haze_fraction is not None else 'unavailable'
    st.caption(f"SCL cloud: {bad_text} | Haze: {haze_text} | Latency: {evidence.get('latency_ms', 'N/A')} ms")
    if result.get('conflict'):
        st.warning('CONFLICT: the source signature is valid, but image content is suspicious.')
    _render_evidence_channels(result)
    render_legacy_reasons(st, result.get('reasons', []))
    st.info('Provenance: simulated source signature')
    st.caption('Processed by the configured ground-station API.' if backend else 'Processed locally with the configured model repository.')
    report = build_report(result, meta)
    st.download_button(
        'Download report (JSON)',
        data=json.dumps(report, ensure_ascii=True, indent=2),
        file_name='trust_the_pixel_report.json',
        mime='application/json',
    )


def _render_evidence_channels(result):
    """Present current cryptographic and model evidence without invented dashboard metrics."""
    evidence = result.get('evidence') or {}
    score = evidence.get('score')
    low, high = evidence.get('t_low'), evidence.get('t_high')
    if score is None or low is None or high is None:
        model_readout = 'Unavailable'
    else:
        score, low, high = float(score), float(low), float(high)
        if score < low:
            model_readout = f'{score:.3f} (below t_low {low:.3f})'
        elif score < high:
            model_readout = f'{score:.3f} (between thresholds)'
        else:
            model_readout = f'{score:.3f} (at or above t_high {high:.3f})'

    provenance = evidence.get('provenance', 'UNKNOWN')
    integrity = evidence.get('integrity', 'UNVERIFIED')
    replay = 'Detected' if evidence.get('replay') else 'Not detected'
    copy_move_matches = evidence.get('copy_move')
    copy_move_text = 'Unavailable' if copy_move_matches is None else str(copy_move_matches)

    st.markdown('<div class="tp-section-label">Verification evidence</div>', unsafe_allow_html=True)
    crypto, vision = st.columns(2)
    with crypto:
        with st.container(border=True):
            st.markdown('<div class="tp-evidence-heading">Cryptographic provenance</div>', unsafe_allow_html=True)
            st.caption(f'Source: {provenance}')
            st.caption(f'Pixel integrity: {integrity}')
            st.caption(f'Replay: {replay}')
            st.caption(f'Hash chain: {evidence.get("chain", "N/A")}')
    with vision:
        with st.container(border=True):
            st.markdown('<div class="tp-evidence-heading">Image analysis</div>', unsafe_allow_html=True)
            st.caption(f'Model score: {model_readout}')
            st.caption(f'Trust index: {evidence.get("trust", "Unavailable")}')
            st.caption(f'Copy-move matches: {copy_move_text}')
            st.caption(f'Model latency: {evidence.get("latency_ms", "Unavailable")} ms')


def _render_recent_analyses(history):
    if not history:
        return
    st.markdown('<div class="tp-section-label">Recent analyses</div>', unsafe_allow_html=True)
    for index, row in enumerate(reversed(history[-5:])):
        left, right = st.columns([1.6, 1.0], vertical_alignment='center')
        left.markdown(status_badge(row.get('status', 'UNKNOWN'), small=True), unsafe_allow_html=True)
        left.caption(f"{row.get('scene', 'Unknown scene')} | {row.get('date', 'Unknown date')} | {row.get('source', 'unknown')} chip")
        score = row.get('score')
        score_text = f'{float(score):.3f}' if isinstance(score, (int, float)) else 'Unavailable'
        right.caption(f"Score: {score_text}")
        right.caption(f"{row.get('elapsed_ms', 0):.0f} ms | {row.get('time_utc', '')}")
        if index < min(4, len(history) - 1):
            st.markdown('<div class="tp-separator"></div>', unsafe_allow_html=True)


def render_image_processing() -> None:
    """Expose the processed image layers and model evidence in the workspace."""
    session = st.session_state
    result, meta = session.get('area_result'), session.get('area_meta')
    if not result or not meta:
        st.info('Analyze an area first. The true-colour image, NDVI, and model heatmap will appear here.')
        if st.button('Open Analyze area', key='image_processing_open_area'):
            session['workspace_page'] = 'Analyze area'
            st.rerun()
        return

    _render_evidence_channels(result)
    st.markdown('<div class="tp-section-label">Image layers on the map</div>', unsafe_allow_html=True)
    for key, label in (
        ('area_show_rgb', 'True colour'),
        ('area_show_ndvi', 'NDVI'),
        ('area_show_heatmap', 'Forgery heatmap'),
    ):
        if key not in session:
            session[key] = key == 'area_show_rgb' or (key == 'area_show_heatmap' and result.get('status') != 'TRUSTED')
        st.checkbox(label, key=key)
    st.slider('Overlay opacity', 0.1, 1.0, key='area_opacity')
    overlays = session.get('area_overlays') or {}
    for key, label in (
        ('area_show_rgb', 'True colour'),
        ('area_show_ndvi', 'NDVI'),
        ('area_show_heatmap', 'Forgery heatmap'),
    ):
        if label in overlays:
            overlays[label]['show'] = bool(session[key])
    st.caption(f"Scene {meta.get('scene', 'Unknown')} · {meta.get('date', 'Unknown date')} · fixed 256 × 256 chip")


def render_attack_lab(ctx: dict) -> None:
    """Present the existing local attack simulator as a first-class workspace."""
    session = st.session_state
    if session.get('area_original_chip') is None:
        st.info('Analyze an area first. The attack lab uses that real 256 × 256 chip as its baseline.')
        if st.button('Open Analyze area', key='attack_lab_open_area'):
            session['workspace_page'] = 'Analyze area'
            st.rerun()
        return
    _draw_attack_controls(ctx, ctx.get('pack_entries') or [])


def render_forensics(api_configured: bool = False) -> None:
    """Show the latest packet verification and its source manifest."""
    session = st.session_state
    result, meta = session.get('area_result'), session.get('area_meta')
    packet = session.get('area_packet') or {}
    if not result or not meta:
        st.info('No processed observation is available. Analyze an area to create a signed packet and forensic result.')
        if st.button('Open Analyze area', key='forensics_open_area'):
            session['workspace_page'] = 'Analyze area'
            st.rerun()
        return

    _draw_result(result, meta, backend=api_configured)
    manifest = packet.get('manifest')
    if isinstance(manifest, dict):
        with st.expander('Signed source manifest'):
            st.json(manifest)
    validation = session.get('area_validation') or {}
    st.markdown('<div class="tp-section-label">Input contract</div>', unsafe_allow_html=True)
    if validation.get('ok'):
        st.success('Chip validated: uint16, 4 bands, 256 × 256, Sentinel-2 band order.')
    else:
        st.error('Chip contract validation failed.')
        for error in validation.get('errors', []):
            st.caption(str(error))


def render(ctx: dict) -> None:
    session = st.session_state
    if not ctx.get('api_configured'):
        st.info('Backend API is not configured for this dashboard process. Area analysis uses the local model. Set TP_API_URL and TP_SOURCE_PRIVATE_KEY in the PowerShell window used to start Streamlit, then restart it to use the backend.')
    st.markdown('<div class="tp-section-label">1 · Area</div>', unsafe_allow_html=True)
    point = session.get('area_point')
    st.caption('Click the map to select an analysis point.' if not point else f"Coordinates: {point['lat']:.5f}, {point['lon']:.5f}")
    if point is None:
        st.markdown('<div class="tp-empty-state">Click on the map to select an area.</div>', unsafe_allow_html=True)
    st.caption('Area size is fixed: it is the input size the model was trained on.')
    if point and not _in_training_domain(point['lon'], point['lat']):
        st.warning('Outside training domain')

    st.markdown('<div class="tp-section-label">2 · Data source</div>', unsafe_allow_html=True)
    data_options = ['Live Copernicus (latest)'] + (['Prepared unseen data (offline)'] if ctx.get('pack_available', True) else [])
    if not ctx.get('pack_available', True):
        st.info('Prepared unseen data is unavailable because unseen_pack/index.json was not found.')
    if session.get('area_data_source') not in data_options:
        session['area_data_source'] = data_options[0]
    data_source = st.radio(
        'Data source',
        data_options,
        index=0,
        key='area_data_source',
        label_visibility='collapsed',
    )
    entries = ctx.get('pack_entries')
    if entries is None:
        entries = load_pack()
    places = ctx.get('prepared_places') or []

    acquisitions = []
    acquisition_error = None
    if point and data_source == 'Live Copernicus (latest)':
        try:
            with st.spinner('Searching Copernicus acquisitions...'):
                acquisitions = _cached_acquisitions(point['lon'], point['lat'])
        except NetworkUnavailable as exc:
            acquisition_error = _network_message(exc)
        except Exception:
            acquisition_error = 'The Copernicus data service is unavailable. Check the network and try again.'

    st.markdown('<div class="tp-section-label">3 · Date</div>', unsafe_allow_html=True)
    if acquisition_error:
        st.error(acquisition_error)
    if not point:
        st.selectbox('Acquisition date', ['Select an area first'], disabled=True, label_visibility='collapsed')
    elif data_source == 'Prepared unseen data (offline)':
        selected_place = session.get('area_prepared_place')
        if selected_place is None:
            place_row = _nearest_prepared_place(point, places)
            selected_place = place_row['place'] if place_row else None
        prepared = [entry for entry in entries if entry.get('place') == selected_place]
        if not prepared:
            st.info('No prepared data near this point; use Live Copernicus.')
            st.selectbox('Acquisition date', ['No prepared chip available'], disabled=True, label_visibility='collapsed')
        else:
            labels = [f"{row.get('date', row['meta'].get('date', 'Unknown date'))} · cloudy {'yes' if row.get('cloudy') else 'no'} · {row.get('group', 'local pack')}"
                      for row in prepared]
            selected_index = st.selectbox('Acquisition date', range(len(prepared)), format_func=lambda index: labels[index],
                                          key='area_pack_chip_index', label_visibility='collapsed')
            selected_row = prepared[selected_index]
            if selected_row.get('group') == 'post-training scene':
                st.info('Acquired after the training period (not in train/val/test). The same geography may have been seen in other scenes.')
            else:
                st.info('This chip references the held-out test split; it is included as a local comparison sample.')
            st.caption(f"Prepared place: {selected_row.get('place')} | Group: {selected_row.get('group')}")
            can_analyze = ctx.get('analysis_available', ctx.get('pipeline') is not None)
            if st.button('Analyze this area', type='primary', disabled=not can_analyze, key='area_analyse',
                         help=None if can_analyze else 'Check model availability and backend source-key configuration above.'):
                try:
                    chip = selected_row['pixels']
                    meta = dict(selected_row['meta'])
                    meta.setdefault('place', selected_row.get('place', 'Unknown'))
                    meta.setdefault('region', meta['place'])
                    session['area_original_path'] = selected_row.get('pixels_path')
                    _render_process(chip, meta, ctx)
                except Exception as exc:
                    st.error(f'Analysis failed ({type(exc).__name__}). Check the selected offline chip.')
    elif not acquisitions:
        if not acquisition_error:
            st.error('No usable Sentinel-2 scene was found for this point and date range.')
        st.selectbox('Acquisition date', ['No usable scene available'], disabled=True, label_visibility='collapsed')
    else:
        ids = [item['item_id'] for item in acquisitions]
        labels = {
            item['item_id']: f"{item['date']} | {item['cloud_cover']:.0f}% cloud"
            for item in acquisitions
        }
        selected_id = st.selectbox(
            'Acquisition date', ids, format_func=lambda item_id: labels[item_id],
            key='area_selected_item', label_visibility='collapsed',
        )
        selected = next(item for item in acquisitions if item['item_id'] == selected_id)
        st.caption(f"MGRS tile: {selected['tile'] or 'Unknown'} | Baseline: {selected['baseline'] or 'Unknown'}")
        can_analyze = ctx.get('analysis_available', ctx.get('pipeline') is not None) and data_source == 'Live Copernicus (latest)'
        if data_source == 'Live Copernicus (latest)' and st.button('Analyze this area', type='primary', disabled=not can_analyze, key='area_analyse',
                                                                  help=None if can_analyze else 'Check model availability and backend source-key configuration above.'):
            click_started = time.perf_counter()
            progress = st.status('Reading Sentinel-2 bands...', expanded=True)
            try:
                with progress:
                    tried_ids = [selected_id] + [item_id for item_id in ids if item_id != selected_id]
                    chosen_chip, chosen_meta = _read_chip_from_acquisitions(
                        tried_ids, point['lon'], point['lat']
                    )
                    session['area_original_path'] = None
                    _render_process(chosen_chip, chosen_meta, ctx)
                    session['area_last_elapsed_ms'] = (time.perf_counter() - click_started) * 1000
                    session['area_last_source'] = 'live'
                    progress.update(label='Analysis complete', state='complete')
            except AreaNotUsable as exc:
                progress.update(label='Area unavailable', state='error')
                st.error(str(exc))
            except NetworkUnavailable as exc:
                progress.update(label='Network unavailable', state='error')
                st.error(_network_message(exc))
            except CRSError:
                progress.update(label='Coordinate reference error', state='error')
                st.error('The selected scene could not be transformed to map coordinates. Restart Streamlit to apply its bundled PROJ database, then try another date or nearby point.')
            except Exception as exc:
                progress.update(label='Analysis failed', state='error')
                st.error(f'Analysis failed ({type(exc).__name__}). Check the selected area and try again.')

    result, meta = session.get('area_result'), session.get('area_meta')
    if result and meta:
        st.markdown('<div class="tp-section-label">Current observation</div>', unsafe_allow_html=True)
        _draw_result(result, meta, backend=bool(ctx.get('api_configured')))
        if session.get('area_last_elapsed_ms') is not None:
            st.caption(f"Click to result ({session.get('area_last_source', 'area')} chip): {session['area_last_elapsed_ms']:.1f} ms")
        truth = session.get('area_truth')
        details = session.get('area_attack_details')
        if truth is not None:
            probabilities = result.get('prob')
            predicted = np.asarray(np.zeros((256, 256)) if probabilities is None else probabilities,
                                   dtype=np.float32) > 0.5
            actual = np.asarray(truth) > 0
            intersection = int(np.logical_and(predicted, actual).sum())
            union = int(np.logical_or(predicted, actual).sum())
            denominator = int(predicted.sum() + actual.sum())
            st.metric('IoU', f'{intersection / union:.3f}' if union else '1.000')
            st.metric('Dice', f'{2 * intersection / denominator:.3f}' if denominator else '1.000')
            st.caption(f"Attack detectability: {details.get('detectability', 'N/A') if details else 'N/A'}")
            family = st.session_state.get('area_attack_family')
            severity = st.session_state.get('area_attack_severity')
            if family in {'photometric', 'band_shift', 'copy_move'} or (family == 'spectral' and severity == 'subtle'):
                st.warning('Family poorly detected by the model')
            st.caption('White map contour shows the ground-truth tampering mask; it is not passed to the model.')
        # Attack processing can update these keys; instantiate its controls first
        # so Streamlit never sees a post-instantiation session-state mutation.
        _draw_attack_controls(ctx, entries)
        st.markdown('<div class="tp-section-label">Map layers</div>', unsafe_allow_html=True)
        for key, label in (
            ('area_show_rgb', 'True colour'),
            ('area_show_ndvi', 'NDVI'),
            ('area_show_heatmap', 'Forgery heatmap'),
        ):
            st.checkbox(label, key=key)
        st.slider('Overlay opacity', 0.1, 1.0, key='area_opacity')
        overlay_names = {'area_show_rgb': 'True colour', 'area_show_ndvi': 'NDVI', 'area_show_heatmap': 'Forgery heatmap'}
        for key, name in overlay_names.items():
            if name in session['area_overlays']:
                session['area_overlays'][name]['show'] = bool(session[key])
    _render_recent_analyses(session.get('area_analysis_history', []))
