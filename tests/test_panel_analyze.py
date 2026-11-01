"""AppTest coverage for the live area analysis panel."""

import textwrap

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from ui import panel_analyze


def test_live_area_skips_scene_with_invalid_crs_and_uses_next_scene(monkeypatch):
    attempted = []
    chip = np.ones((4, 256, 256), dtype=np.uint16)
    meta = {'scene': 'usable'}

    def read_chip(item, lon, lat):
        attempted.append(item['id'])
        if item['id'] == 'bad-crs':
            raise panel_analyze.CRSError('invalid CRS in scene')
        return chip, meta

    monkeypatch.setattr(panel_analyze, 'fetch_acquisition', lambda item_id: {'id': item_id})
    monkeypatch.setattr(panel_analyze, 'read_chip_at', read_chip)

    actual_chip, actual_meta = panel_analyze._read_chip_from_acquisitions(
        ['bad-crs', 'usable'], 10.2, 36.8
    )

    assert actual_chip is chip
    assert actual_meta is meta
    assert attempted == ['bad-crs', 'usable']


def test_remote_analysis_posts_signed_packet_to_configured_backend(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from tp.chain import ChainedSource

    monkeypatch.setenv('TP_API_URL', 'https://ground.example/v1/health')
    packet = ChainedSource(sk=Ed25519PrivateKey.generate()).acquire(
        np.random.default_rng(4).integers(1000, 4000, size=(4, 256, 256), dtype=np.uint16),
        {'date': '2026-01-01', 'lon': 10.2, 'lat': 36.8, 'scene': 'TEST', 'tile': 'T32SNH', 'offset': 1000},
    )
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {'result': {'status': 'TRUSTED'}}

    monkeypatch.setattr(panel_analyze.requests, 'post', lambda url, **kwargs: calls.append((url, kwargs)) or Response())
    assert panel_analyze._send_to_backend(packet)['result']['status'] == 'TRUSTED'
    assert calls[0][0] == 'https://ground.example/v1/analyze'
    assert calls[0][1]['json']['manifest'] == packet['manifest']


def test_panel_selects_mocked_date_analyzes_and_shows_result(monkeypatch, tmp_path):
    acquisition_rows = [{
        'item_id': 'test-scene', 'date': '2026-10-26', 'cloud_cover': 3.0,
        'tile': '32SNA', 'baseline': '05.00'
    }]
    chip = np.random.default_rng(5).integers(2500, 9000, (4, 256, 256), dtype=np.uint16)
    meta = {
        'date': '2026-10-26', 'lon': 10.18, 'lat': 36.8, 'scene': 'test-scene',
        'tile': '32SNA', 'r0': 200, 'c0': 300, 'offset': 1000,
        'region': 'Tunis', 'place': 'Tunis', 'epsg': 32632,
        'x0': 500000.0, 'y0': 4100000.0, 'bad_frac': 0.01, 'haze_frac': 0.0,
    }
    monkeypatch.setattr(panel_analyze, '_cached_acquisitions', lambda *args, **kwargs: acquisition_rows)
    monkeypatch.setattr(panel_analyze, 'fetch_acquisition', lambda item_id: {'id': item_id})
    monkeypatch.setattr(panel_analyze, 'read_chip_at', lambda item, lon, lat: (chip.copy(), dict(meta)))

    script = tmp_path / 'panel_app.py'
    script.write_text(textwrap.dedent('''
        import streamlit as st
        import numpy as np
        from ui import state, panel_analyze
        state.initialize(st.session_state)
        st.session_state["area_point"] = {"lon": 10.18, "lat": 36.8}
        class FakePipeline:
            def acquire(self, pixels, metadata):
                return {"pixels": pixels, "manifest": {"scene": metadata["scene"]}}
            def process(self, packet, cloud_ctx=None, kind="none", progress_callback=None):
                if progress_callback:
                    progress_callback("Verifying packet...")
                    progress_callback("Running the model...")
                st.session_state["process_count"] = st.session_state.get("process_count", 0) + 1
                return {
                    "status": "SUSPICIOUS", "status_raw": "SUSPICIOUS", "conflict": False,
                    "reasons": ["Test analysis reason"],
                    "evidence": {"score": 2.0, "trust": 42.0, "latency_ms": 12.0, "t_low": 1.4, "t_high": 4.7},
                    "prob": np.zeros((256, 256), dtype=np.float32).tolist(),
                    "logits": None, "version_info": {"onnx_sha256": "hash", "config_sha256": "config", "variant": "test"}
                }
        panel_analyze.render({"pipeline": FakePipeline()})
    '''), encoding='utf-8')
    app = AppTest.from_file(str(script), default_timeout=60).run()
    assert not app.exception, app.exception
    assert [item for item in app.selectbox[0].options] == ['2026-10-26 | 3% cloud']
    app.button(key='area_analyse').click().run()

    assert not app.exception, app.exception
    assert app.session_state['process_count'] == 1
    rendered = '\n'.join(element.value for element in app.markdown)
    assert 'SUSPICIOUS' in rendered
    assert 'test-scene' in '\n'.join(element.value for element in app.markdown)
    assert app.session_state['area_last_elapsed_ms'] >= 0
    assert 'Provenance: simulated source signature' in '\n'.join(element.value for element in app.info)
    assert len(app.session_state['area_analysis_history']) == 1
    assert app.session_state['area_analysis_history'][0]['scene'] == 'test-scene'
    assert any('Recent analyses' in element.value for element in app.markdown)
    assert any('Cryptographic provenance' in element.value for element in app.markdown)
    app.run()
    assert len(app.session_state['area_analysis_history']) == 1


def test_offline_tunis_chip_analysis_and_both_tampering_paths(tmp_path):
    from tp.pack import load_pack

    entries = [entry for entry in load_pack() if entry.get('place') == 'Tunis']
    assert entries, 'A local Tunis pack chip or held-out sample reference is required.'
    script = tmp_path / 'offline_pack_app.py'
    script.write_text(textwrap.dedent('''
        import streamlit as st
        from tp.engine import TrustPipeline
        from tp.pack import load_pack
        from ui import state, panel_analyze
        state.initialize(st.session_state)
        st.session_state["area_data_source"] = "Prepared unseen data (offline)"
        st.session_state["area_prepared_place"] = "Tunis"
        st.session_state["area_point"] = {"lon": 10.20, "lat": 36.85}
        @st.cache_resource
        def pipeline():
            return TrustPipeline()
        places = [{"place": "Tunis", "center": [10.20, 36.85], "chips": 1}]
        panel_analyze.render({"pipeline": pipeline(), "pack_entries": load_pack(), "prepared_places": places})
    '''), encoding='utf-8')
    app = AppTest.from_file(str(script), default_timeout=120).run()
    assert not app.exception, app.exception
    assert any('Prepared place: Tunis' in item.value for item in app.caption)
    app.button(key='area_analyse').click().run()
    assert not app.exception, app.exception
    print(f"P17 prepared chip click-to-result: {app.session_state['area_last_elapsed_ms']:.1f} ms")
    assert any('TRUSTED' in item.value or 'SUSPICIOUS' in item.value or 'COMPROMISED' in item.value
               for item in app.markdown)

    app.selectbox(key='area_attack_family').select('inpaint_ns')
    app.selectbox(key='area_attack_severity').select('strong')
    app.button(key='area_apply_attack').click().run()
    assert not app.exception, app.exception
    source_status = app.session_state['area_result']['status']
    assert source_status != 'TRUSTED'

    app.radio(key='area_attack_where').set_value('In transit (breaks the signature)')
    app.button(key='area_apply_attack').click().run()
    assert not app.exception, app.exception
    assert app.session_state['area_result']['status'] == 'COMPROMISED'


@pytest.mark.network
def test_live_chip_click_to_result_timing(tmp_path, monkeypatch):
    import streamlit_folium
    monkeypatch.setattr(streamlit_folium, 'st_folium', lambda map_object, **kwargs: {})
    script = tmp_path / 'live_timing_app.py'
    script.write_text(textwrap.dedent('''
        import streamlit as st
        from tp.engine import TrustPipeline
        from ui import state, panel_analyze
        state.initialize(st.session_state)
        st.session_state['area_point'] = {'lon': 10.18, 'lat': 36.8}
        @st.cache_resource
        def pipeline():
            return TrustPipeline()
        panel_analyze.render({'pipeline': pipeline(), 'pack_entries': [], 'pack_available': False})
    '''), encoding='utf-8')
    app = AppTest.from_file(str(script), default_timeout=180).run()
    assert not app.exception, app.exception
    if not app.selectbox or app.selectbox[0].disabled or not app.button(key='area_analyse'):
        pytest.skip('Copernicus has no usable acquisition for the test area.')
    app.button(key='area_analyse').click().run()
    if app.exception:
        pytest.skip('Copernicus acquisition was unavailable during the live timing run.')
    if 'area_last_elapsed_ms' not in app.session_state:
        errors = ' '.join(element.value for element in app.error).casefold()
        if any(word in errors for word in ('unavailable', 'no usable', 'outside the image swath', 'outside the usable image')):
            pytest.skip('Copernicus did not provide a usable chip during the live timing run.')
        pytest.fail('Live acquisition completed without producing a click-to-result measurement.')
    assert app.session_state['area_last_source'] == 'live'
    assert app.session_state['area_last_elapsed_ms'] >= 0
    print(f"P17 live chip click-to-result: {app.session_state['area_last_elapsed_ms']:.1f} ms")
