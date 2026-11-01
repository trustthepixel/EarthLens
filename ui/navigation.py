"""EARTHLENS sidebar destinations, rendered by Streamlit."""

from __future__ import annotations

from pathlib import Path


NAV_GROUPS = {
    "Operations": (
        "Mission Control",
        "Analyze area",
        "Copernicus Acquisition",
        "Live demo",
        "Geospatial Map",
    ),
    "Integrity analysis": (
        "Image processing",
        "Attack Lab",
        "Forensics & verification",
        "Verification",
        "Audit Logs",
        "Model Evaluation",
    ),
    "System": ("System details", "Copernicus configuration"),
}
NAVIGATION = tuple((group, pages) for group, pages in NAV_GROUPS.items())
NAV_PAGES = frozenset(page for pages in NAV_GROUPS.values() for page in pages)
NAV_ICONS = {
    "Mission Control": ":material/dashboard:",
    "Copernicus Acquisition": ":material/database:",
    "Geospatial Map": ":material/public:",
    "Image processing": ":material/image_search:",
    "Attack Lab": ":material/biotech:",
    "Forensics & verification": ":material/fact_check:",
    "Verification": ":material/shield:",
    "Audit Logs": ":material/inventory_2:",
    "Model Evaluation": ":material/query_stats:",
    "System details": ":material/settings:",
    "Copernicus configuration": ":material/satellite_alt:",
    "Analyze area": ":material/travel_explore:",
    "Live demo": ":material/sensors:",
}


def _select_page(page: str) -> None:
    import streamlit as st

    st.session_state["workspace_page"] = page
    if page in {"Copernicus Acquisition", "Image processing", "Attack Lab", "Forensics & verification", "Verification", "Copernicus configuration"}:
        st.session_state["dashboard_mode"] = "Analyze area"
    elif page in {"Mission Control", "Live demo"}:
        st.session_state["dashboard_mode"] = "Live monitor" if page == "Live demo" else "Analyze area"


def render(*, model_text: str, internet_text: str, api_text: str) -> str:
    """Render the original grouped navigation and service status in the sidebar."""
    import streamlit as st

    selected = st.session_state.get("workspace_page", "Mission Control")
    if selected not in NAV_PAGES:
        selected = "Mission Control"
        st.session_state["workspace_page"] = selected

    with st.sidebar:
        logo = Path(__file__).resolve().parents[1] / "assets" / "logo.svg"
        brand, name = st.columns([0.44, 1.56], vertical_alignment="center")
        with brand:
            st.image(str(logo), width=40)
        with name:
            st.markdown('<div class="tp-title">EARTHLENS</div>', unsafe_allow_html=True)

        with st.container(key="tp-navigation"):
            for group, pages in NAV_GROUPS.items():
                st.markdown(f'<div class="tp-nav-heading">{group}</div>', unsafe_allow_html=True)
                for page in pages:
                    key = "navigation_" + page.casefold().replace(" ", "_").replace("&", "and")
                    st.button(
                        page,
                        key=key,
                        icon=NAV_ICONS[page],
                        type="primary" if selected == page else "secondary",
                        use_container_width=True,
                        on_click=_select_page,
                        args=(page,),
                    )

        st.markdown('<div class="tp-separator"></div>', unsafe_allow_html=True)
        from ui.status import connection_chips

        st.markdown(
            connection_chips(model_text, internet_text, api_text),
            unsafe_allow_html=True,
        )
    return selected
