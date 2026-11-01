"""Status badges, legend, and neutral service health chips."""

from __future__ import annotations

from html import escape

from ui.theme import PALETTE


STATUS_COLORS = {
    "TRUSTED": PALETTE["trusted"],
    "SUSPICIOUS": PALETTE["suspicious"],
    "COMPROMISED": PALETTE["compromised"],
    "NOT ANALYZED": PALETTE["not_analysed"],
}


def status_badge(value: str, small: bool = False) -> str:
    label = str(value).upper()
    color = STATUS_COLORS.get(label, PALETTE["not_analysed"])
    size = "small" if small else "large"
    return (
        f'<span class="tp-threat-badge {size}" style="--badge-color:{color}">'
        f'{escape(label)}</span>'
    )


def status_legend() -> str:
    rows = []
    for label, color in STATUS_COLORS.items():
        rows.append(
            f'<div class="tp-legend-row"><span class="tp-legend-dot" style="background:{color}"></span>'
            f'{escape(label)}</div>'
        )
    return "".join(rows)


def connection_chips(model_text: str, internet_text: str, api_text: str) -> str:
    values = (model_text, internet_text, api_text)
    chips = "".join(f'<span class="tp-status-chip">{escape(value)}</span>' for value in values)
    return f'<div class="tp-status-row">{chips}</div>'
