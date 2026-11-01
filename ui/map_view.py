"""Folium map construction and ordered basemap availability checks."""

from __future__ import annotations

import copy
from functools import lru_cache
from html import escape
from typing import Callable

import folium
import requests
from folium.plugins import Fullscreen, MousePosition

from tp.sentinel_live import chip_footprint_4326, preview_footprint
from ui.status import status_legend
from ui.status import STATUS_COLORS


AUTO = "Auto"
NO_TILES = "No tiles (offline)"
EOX = "EOX Sentinel-2 cloudless"
ESRI = "Esri World Imagery"
OSM = "OpenStreetMap"

EOX_TILE = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg"
ESRI_TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
OSM_TILE = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
EOX_ATTRIBUTION = (
    'EOxCloudless <a href="https://cloudless.eox.at">cloudless.eox.at</a> by '
    '<a href="https://eox.at">EOX IT Services GmbH</a> '
    '(Contains modified Copernicus Sentinel data 2023)'
)

BASEMAPS = {
    EOX: {
        "tiles": EOX_TILE,
        "attribution": EOX_ATTRIBUTION,
        "probe_url": "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/GoogleMapsCompatible/6/24/33.jpg",
        "max_zoom": 14,
    },
    ESRI: {
        "tiles": ESRI_TILE,
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "probe_url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/6/24/33",
        "max_zoom": 19,
    },
    OSM: {
        "tiles": OSM_TILE,
        "attribution": "© OpenStreetMap contributors",
        "probe_url": "https://tile.openstreetmap.org/6/33/24.png",
        "max_zoom": 19,
    },
}


@lru_cache(maxsize=64)
def _cached_footprint(lon: float, lat: float):
    return tuple(preview_footprint(lon, lat))


@lru_cache(maxsize=16)
def _monitor_place_footprints(specs: tuple) -> folium.FeatureGroup:
    """Cache neutral place footprints shared by monitor map reruns."""
    group = folium.FeatureGroup(name='Preset place footprints', show=True)
    for place, lon, lat in specs:
        corners = _cached_footprint(lon, lat)
        folium.Polygon(
            [[point[1], point[0]] for point in corners], color='#8791A3', weight=2,
            fill=True, fill_color='#8791A3', fill_opacity=0.18,
            tooltip=folium.Tooltip(escape(place)),
            popup=folium.Popup(escape(place), max_width=180),
        ).add_to(group)
    return group


def probe_basemap(request_get: Callable | None = None) -> str:
    """Return the first tile service responding HTTP 200, or the no-tile mode."""
    get = request_get or requests.get
    for name, config in BASEMAPS.items():
        response = None
        try:
            response = get(config["probe_url"], timeout=3, stream=True)
            if response.status_code == 200:
                return name
        except requests.RequestException:
            pass
        except Exception:
            pass
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
    return NO_TILES


def build_map(
    center: dict | None = None,
    zoom: int = 6,
    basemap: str = NO_TILES,
    *,
    point: dict | None = None,
    result: dict | None = None,
    meta: dict | None = None,
    overlays: dict | None = None,
    opacity: float = 0.65,
    prepared_places: list[dict] | None = None,
    monitor_places: list[dict] | None = None,
    monitor_selected_place: str | None = None,
    recorded_session: bool = False,
    workspace_summary: dict | None = None,
) -> folium.Map:
    center = center or {"lat": 34.0, "lng": 9.5}
    location = [float(center.get("lat", 34.0)), float(center.get("lng", 9.5))]
    map_object = folium.Map(
        location=location,
        zoom_start=int(zoom),
        tiles=None,
        control_scale=True,
        width="100%",
        height="100%",
        zoom_control=True,
        prefer_canvas=True,
    )
    if basemap in BASEMAPS:
        config = BASEMAPS[basemap]
        folium.TileLayer(
            tiles=config["tiles"],
            name=basemap,
            attr=config["attribution"],
            max_zoom=config["max_zoom"],
            control=False,
            subdomains="abc" if basemap == OSM else "",
        ).add_to(map_object)

    MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="Coordinates",
        num_digits=5,
    ).add_to(map_object)
    Fullscreen(position="topright", title="Enter fullscreen", title_cancel="Exit fullscreen").add_to(map_object)

    if monitor_places is not None:
        monitor_specs = tuple(sorted(
            (str(row.get('place', 'unknown')), float(row.get('center', [0.0, 0.0])[0]),
             float(row.get('center', [0.0, 0.0])[1]))
            for row in monitor_places
        ))
        copy.deepcopy(_monitor_place_footprints(monitor_specs)).add_to(map_object)
        for prepared in monitor_places:
            place = str(prepared.get('place', 'unknown'))
            center = prepared.get('center', [0.0, 0.0])
            lon, lat = float(center[0]), float(center[1])
            status = str(prepared.get('status') or '').upper()
            color = STATUS_COLORS.get(status, '#8791A3')
            corners = _cached_footprint(lon, lat)
            locations = [[point[1], point[0]] for point in corners]
            if status in {'TRUSTED', 'SUSPICIOUS', 'COMPROMISED'}:
                folium.Polygon(locations, color=color, weight=3 if place == monitor_selected_place else 2,
                               fill=True, fill_color=color, fill_opacity=0.32,
                               interactive=False).add_to(map_object)
            if status == 'COMPROMISED':
                symbol = ('<span style="display:flex;align-items:center;justify-content:center;width:22px;height:22px;'
                          'border-radius:50%;background:#E5484D;color:white;font:bold 15px system-ui,sans-serif;'
                          'box-shadow:0 0 0 3px rgba(229,72,77,.22);animation:tp-pulse 1.4s infinite">!</span>')
            elif status == 'SUSPICIOUS':
                symbol = ('<span style="display:flex;align-items:center;justify-content:center;width:20px;height:20px;'
                          'border-radius:50%;background:#F59E0B;color:#111A2E;font:bold 14px system-ui,sans-serif">!</span>')
            elif status == 'TRUSTED':
                symbol = '<span style="width:10px;height:10px;border-radius:50%;background:#35B36A;border:2px solid white"></span>'
            else:
                symbol = '<span style="width:10px;height:10px;border-radius:50%;background:#8791A3;border:2px solid white"></span>'
            marker_html = ('<div style="display:flex;flex-direction:column;align-items:center;gap:3px">' + symbol +
                f'<span style="color:#E6EDF7;background:#111A2E;padding:1px 4px;border-radius:3px;font:11px system-ui,sans-serif">{escape(place)}</span></div>')
            folium.Marker([lat + 0.025, lon],
                icon=folium.DivIcon(html=marker_html, icon_size=(90, 38), icon_anchor=(45, 19), class_name='tp-monitor-place'),
                tooltip=escape(place), popup=folium.Popup(escape(place), max_width=180)).add_to(map_object)
    else:
      for prepared in prepared_places or []:
        place = str(prepared.get("place", ""))
        center = prepared.get("center", [0.0, 0.0])
        lon, lat = float(center[0]), float(center[1])
        count = int(prepared.get("chips", prepared.get("chip_count", 0)))
        square = ('<div style="width:13px;height:13px;background:#4C8DFF;border:2px solid #E6EDF7;'
                  'box-shadow:0 0 0 4px rgba(76,141,255,.18)"></div>')
        folium.Marker(
            [lat, lon],
            icon=folium.DivIcon(html=square, icon_size=(17, 17), icon_anchor=(8, 8), class_name="tp-pack-marker"),
            tooltip=f"{escape(place)} · {count} prepared chips",
            popup=folium.Popup(escape(place), max_width=180),
        ).add_to(map_object)

    if monitor_places is None:
        marker_location = location
        marker_tooltip = "Not analyzed"
        if point:
            marker_location = [float(point["lat"]), float(point["lon"])]
            marker_tooltip = f"Selected area: {point['lat']:.5f}, {point['lon']:.5f}"
        marker_html = (
            '<div style="width:13px;height:13px;border-radius:50%;background:#8FA1BF;'
            'border:2px solid #E6EDF7;box-shadow:0 0 0 5px rgba(143,161,191,.2)"></div>'
        )
        folium.Marker(
            location=marker_location,
            icon=folium.DivIcon(html=marker_html, icon_size=(17, 17), icon_anchor=(8, 8), class_name="tp-marker"),
            tooltip=marker_tooltip,
        ).add_to(map_object)

    if monitor_places is None and result and meta:
        corners = chip_footprint_4326(meta)
        color = STATUS_COLORS.get(str(result.get("status", "NOT ANALYZED")).upper(), STATUS_COLORS["NOT ANALYZED"])
        folium.Polygon(
            locations=[[lat, lon] for lon, lat in corners],
            color=color,
            weight=2,
            fill=False,
            tooltip=f"{result.get('status', 'Analyzed')} chip footprint",
        ).add_to(map_object)
    elif monitor_places is None and point:
        corners = preview_footprint(point["lon"], point["lat"])
        folium.Polygon(
            locations=[[lat, lon] for lon, lat in corners],
            color="#E6EDF7",
            weight=2,
            dash_array="6 5",
            fill=False,
            tooltip="256×256 px · 2.56 × 2.56 km",
        ).add_to(map_object)

    for name, overlay in (overlays or {}).items():
        if not isinstance(overlay, dict) or not overlay.get("show") or not overlay.get("image"):
            continue
        folium.raster_layers.ImageOverlay(
            image=overlay["image"],
            bounds=overlay["bounds"],
            name=name,
            opacity=float(opacity),
            interactive=False,
            cross_origin=False,
            zindex=2,
        ).add_to(map_object)

    map_object.get_root().html.add_child(folium.Element(
        '<style>.leaflet-container{background:#0B1220!important}.tp-map-title{position:absolute;z-index:1000;'
        'top:14px;left:58px;padding:7px 11px;border:1px solid #1E2A44;border-radius:8px;'
        'background:rgba(17,26,46,.94);color:#E6EDF7;font:600 12px system-ui,sans-serif;letter-spacing:.06em}'
        '.tp-map-legend{position:absolute;z-index:1000;right:12px;bottom:30px;padding:9px 11px;'
        'border:1px solid #1E2A44;border-radius:8px;background:rgba(17,26,46,.94);'
        'color:#E6EDF7;font:11px system-ui,sans-serif}.tp-legend-row{display:flex;align-items:center;gap:7px;margin:3px 0}'
        '.tp-legend-dot{width:8px;height:8px;border-radius:50%;display:inline-block}'
        '.tp-workspace-card{position:absolute;z-index:1000;top:14px;right:58px;width:min(360px,calc(100% - 90px));'
        'padding:14px;border:1px solid #1E2A44;border-radius:10px;background:rgba(17,26,46,.96);color:#E6EDF7;'
        'box-shadow:0 8px 28px rgba(0,0,0,.28);font:12px system-ui,sans-serif}'
        '.tp-workspace-top{display:flex;align-items:center;justify-content:space-between;color:#B6C4D9;font-size:10px;'
        'text-transform:uppercase;letter-spacing:.12em}.tp-workspace-title{margin-top:9px;font-size:15px;font-weight:700}'
        '.tp-workspace-subtitle{margin-top:4px;color:#B6C4D9;font-size:11px;overflow-wrap:anywhere}'
        '.tp-workspace-status{display:inline-block;margin-top:10px;padding:4px 7px;border:1px solid var(--workspace-status);'
        'border-radius:999px;color:var(--workspace-status);font-size:10px;font-weight:700;letter-spacing:.06em}'
        '.tp-workspace-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 14px;margin-top:11px}'
        '.tp-workspace-metric{min-width:0;display:flex;flex-direction:column;gap:3px}'
        '.tp-workspace-metric span{color:#B6C4D9;font-size:9px;text-transform:uppercase;letter-spacing:.08em}'
        '.tp-workspace-metric b{color:#E6EDF7;font-size:11px;font-weight:600;overflow-wrap:anywhere}'
        '.tp-workspace-recorded{border:1px solid #B6C4D9;border-radius:999px;padding:3px 6px;color:#B6C4D9;'
        'font-size:9px;font-weight:700;letter-spacing:.04em}'
        '@media(max-width:700px){.tp-workspace-card{top:104px;left:12px;right:12px;width:auto}}'
        '@keyframes tp-pulse{0%,100%{box-shadow:0 0 0 3px rgba(229,72,77,.25);transform:scale(1)}'
        '50%{box-shadow:0 0 0 9px rgba(229,72,77,.02);transform:scale(1.08)}}</style>'
        f'<div class="tp-map-title">EARTHLENS · TUNISIA · {escape(basemap)}</div>'
        f'<div class="tp-map-legend">{"<b>RECORDED SESSION</b><br>" if recorded_session else ""}{status_legend()}</div>'
    ))
    map_object.get_root().html.add_child(folium.Element(
        '<div style="position:absolute;z-index:1000;top:62px;left:58px;padding:6px 10px;'
        'border:1px solid #1E2A44;border-radius:7px;background:rgba(17,26,46,.92);'
        'color:#E6EDF7;font:11px system-ui,sans-serif">256×256 px · 2.56 × 2.56 km</div>'
    ))
    if workspace_summary:
        map_object.get_root().html.add_child(folium.Element(_workspace_summary_html(workspace_summary)))
    return map_object


def _workspace_summary_html(summary: dict) -> str:
    """Render an escaped, map-native summary card from supplied runtime values."""
    mode = escape(str(summary.get("mode", "Workspace")))
    title = escape(str(summary.get("title", "")))
    subtitle = escape(str(summary.get("subtitle", "")))
    status = str(summary.get("status", "NOT ANALYZED")).upper()
    status_color = STATUS_COLORS.get(status, STATUS_COLORS["NOT ANALYZED"])
    metrics = summary.get("metrics", [])
    cells = "".join(
        '<div class="tp-workspace-metric"><span>' + escape(str(item.get("label", "")))
        + '</span><b>' + escape(str(item.get("value", "Unavailable"))) + '</b></div>'
        for item in metrics if isinstance(item, dict)
    )
    recorded = '<span class="tp-workspace-recorded">RECORDED SESSION</span>' if summary.get("recorded") else ""
    return (
        '<div class="tp-workspace-card" role="region" aria-label="Workspace summary">'
        f'<div class="tp-workspace-top"><span>{mode}</span>{recorded}</div>'
        f'<div class="tp-workspace-title">{title}</div>'
        f'<div class="tp-workspace-subtitle">{subtitle}</div>'
        f'<div class="tp-workspace-status" style="--workspace-status:{status_color}">{escape(status)}</div>'
        f'<div class="tp-workspace-grid">{cells}</div></div>'
    )
