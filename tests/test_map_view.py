"""Tests for basemap availability order and map construction."""

from ui import map_view


class Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


def test_basemap_probe_prefers_eox_and_uses_tunisia_tile_timeout():
    calls = []
    response = Response(200)

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    assert map_view.probe_basemap(get) == map_view.EOX
    assert calls == [(map_view.BASEMAPS[map_view.EOX]["probe_url"], {"timeout": 3, "stream": True})]
    assert calls[0][0].endswith("/6/24/33.jpg")
    assert response.closed


def test_basemap_probe_falls_back_in_order():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Response(503 if len(calls) == 1 else 200)

    assert map_view.probe_basemap(get) == map_view.ESRI
    assert calls == [map_view.BASEMAPS[name]["probe_url"] for name in (map_view.EOX, map_view.ESRI)]


def test_basemap_probe_uses_openstreetmap_after_eox_and_esri_fail():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return Response(503 if len(calls) < 3 else 200)

    assert map_view.probe_basemap(get) == map_view.OSM
    assert calls == [map_view.BASEMAPS[name]["probe_url"] for name in (map_view.EOX, map_view.ESRI, map_view.OSM)]


def test_basemap_probe_uses_dark_no_tile_mode_when_every_request_fails():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        raise OSError("offline")

    assert map_view.probe_basemap(get) == map_view.NO_TILES
    assert len(calls) == 3


def test_map_contains_one_base_layer_and_embedded_controls():
    map_object = map_view.build_map({"lat": 34.0, "lng": 9.5}, 6, map_view.NO_TILES)
    html = map_object.get_root().render()
    assert map_object.location == [34.0, 9.5]
    assert "Coordinates" in html
    assert "EARTHLENS" in html
    assert "TRUSTED" in html and "SUSPICIOUS" in html and "COMPROMISED" in html
    assert "NOT ANALYZED" in html
    assert "L.divIcon" in html
    assert "L.AwesomeMarkers.icon" not in html


def test_map_draws_preview_and_selected_overlay():
    map_object = map_view.build_map(
        center={"lat": 36.8, "lng": 10.18},
        point={"lat": 36.8, "lon": 10.18},
        overlays={"True colour": {
            "image": "data:image/png;base64,aGVsbG8=",
            "bounds": [[36.7, 10.1], [36.9, 10.3]],
            "show": True,
        }},
    )
    html = map_object.get_root().render()
    assert "Selected area" in html
    assert "256" in html and "2.56" in html
    assert "image_overlay_" in html
    assert "data:image/png;base64,aGVsbG8=" in html


def test_map_renders_prepared_places_as_blue_square_markers_with_chip_counts():
    map_object = map_view.build_map(
        basemap=map_view.NO_TILES,
        prepared_places=[{"place": "Tunis", "center": [10.20, 36.85], "chips": 3}],
    )
    html = map_object.get_root().render()
    assert "Tunis · 3 prepared chips" in html
    assert "background:#4C8DFF" in html
    assert "tp-pack-marker" in html
