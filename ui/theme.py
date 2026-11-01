"""Dark EO Browser-inspired dashboard theme."""

from __future__ import annotations


PALETTE = {
    "background": "#080D14",
    "surface": "#111C29",
    "border": "#253548",
    "text": "#EAF1F7",
    "secondary": "#8293A6",
    "accent": "#A6F36A",
    "trusted": "#A6F36A",
    "suspicious": "#F4B942",
    "compromised": "#FA4A4A",
    "not_analysed": "#60788E",
}


CSS = """
:root {
  --tp-bg: #080D14;
  --tp-surface: #111C29;
  --tp-border: #253548;
  --tp-text: #EAF1F7;
  --tp-secondary: #8293A6;
  --tp-accent: #A6F36A;
  --tp-trusted: #A6F36A;
  --tp-suspicious: #F4B942;
  --tp-compromised: #FA4A4A;
}
html, body, .stApp { background: var(--tp-bg); color: var(--tp-text); }
.stApp { font-family: Inter, "Segoe UI", ui-sans-serif, system-ui, sans-serif; }
.stApp { background-image: radial-gradient(ellipse at 86% 0%, #14223466 0%, transparent 38%); }
#MainMenu, header, footer, [data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stSidebar"] {
  min-width: 286px !important; max-width: 286px !important;
  background: linear-gradient(180deg, #0D1723 0%, #0A111A 100%);
  border-right: 1px solid var(--tp-border); box-shadow: 10px 0 30px #02070D66; overflow-y: auto;
}
[data-testid="stSidebarContent"] { padding: 1.15rem .85rem 1.1rem; max-height: 100vh; overflow-y: auto; }
[data-testid="stMainBlockContainer"] {
  max-width: none !important; padding: 1.6rem 1.65rem 2rem !important; margin: 0 !important;
  min-height: 100vh; height: auto; overflow: visible;
}
.st-key-tp-topbar { display:block; margin:-1.6rem -1.65rem 1.2rem; padding:.7rem 1.65rem .65rem; border-bottom:1px solid #253548; background:#080D14; }
.tp-topbar-crumb { color:#7890A6; font-size:.59rem; font-weight:750; letter-spacing:.2em; }
.tp-topbar-crumb span { color:#A6F36A; padding:0 .28rem; }
.tp-topbar-title { color:#EAF1F7; font-size:1.05rem; margin-top:.15rem; }
.tp-topbar-right { display:flex; align-items:center; justify-content:flex-end; gap:1rem; color:#8EA4B7; font-size:.68rem; letter-spacing:.09em; }
.tp-ground-status { white-space:nowrap; }
.tp-ground-status i { display:inline-block; width:7px; height:7px; margin-right:.5rem; border-radius:50%; background:#F4B942; }
.tp-ground-status i.online { background:#A6F36A; box-shadow:0 0 10px #A6F36A; }
.tp-ground-status i.offline { background:#FA4A4A; }
.tp-topbar-alert { border-left:1px solid #253548; padding-left:.8rem; white-space:nowrap; }
.tp-topbar-alert b { color:#F4B942; margin-left:.2rem; }
.tp-topbar-avatar { display:grid; place-items:center; width:2rem; height:2rem; border:1px solid #31465B; border-radius:50%; color:#A6F36A; font-weight:750; letter-spacing:0; }
.main .block-container { padding: 1.6rem 1.65rem 2rem !important; }
section.main, [data-testid="stMain"] { padding: 0 !important; margin: 0 !important; }
[data-testid="stCustomComponentV1"] { height: 86vh !important; min-height: 620px; }
[data-testid="stCustomComponentV1"] iframe { height: 86vh !important; min-height: 620px; }
.tp-title { color: #EAF1F7; font-size: .92rem; font-weight: 750; letter-spacing: .14em; }
.tp-nav-heading { color:#61788E; font-size:.59rem; font-weight:750; letter-spacing:.2em; text-transform:uppercase; margin:1.1rem .6rem .38rem; }
.tp-page-heading { color:#EAF1F7; font-size:.78rem; font-weight:650; letter-spacing:.04em; margin:.1rem 0 .65rem; }
.tp-workspace-header { padding:.3rem 1.05rem 1.35rem; margin:0 0 1.35rem; border-bottom:1px solid #2A3C4F; }
.tp-workspace-eyebrow { color:#8BA0B4; font-size:.68rem; line-height:1.4; font-weight:750; letter-spacing:.19em; text-transform:uppercase; margin-bottom:.8rem; }
.tp-workspace-eyebrow span { color:#A6F36A; padding:0 .38rem; }
.tp-workspace-title { color:#F1F6FA; font-size:clamp(1.8rem, 2.15vw, 2.25rem); line-height:1.16; font-weight:680; letter-spacing:-.035em; margin:0 0 .62rem; }
.tp-workspace-description { color:#9AABBB; font-size:.98rem; line-height:1.6; max-width:76ch; }
.tp-section-label { color: #8293A6; font-size: .66rem; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; margin: 1rem 0 .48rem; }
.tp-separator { height: 1px; background: linear-gradient(90deg, #3B5267, #25354800); margin: .9rem 0; }
.tp-basemap-name { color: var(--tp-secondary); font-size: .78rem; margin: .25rem 0 .6rem; }
.tp-status-row { display: flex; flex-wrap: wrap; gap: .4rem; }
.tp-status-chip { color: #C5D2DC; background: #111C29; border: 1px solid #253548; border-radius: 999px; padding: .32rem .58rem; font-size: .66rem; white-space: nowrap; box-shadow: inset 0 1px #FFFFFF08; }
.tp-threat-badge { display:inline-flex; align-items:center; border:1px solid var(--badge-color); border-radius:999px; color:var(--badge-color); background:color-mix(in srgb, var(--badge-color) 12%, transparent); font-weight:700; letter-spacing:.04em; }
.tp-threat-badge.large { padding:.65rem .9rem; font-size:.92rem; }
.tp-threat-badge.small { padding:.32rem .52rem; font-size:.72rem; }
.tp-signature-note { color: var(--tp-secondary); border-top: 1px solid var(--tp-border); margin-top: .8rem; padding-top: .6rem; font-size: .72rem; line-height: 1.45; }
.tp-card, .tp-empty-state { background: linear-gradient(145deg, #111C29, #0D1520); border: 1px solid #253548; border-radius: 8px; padding: .85rem; margin: .55rem 0; box-shadow: 0 8px 22px #02070D33; }
.tp-empty-state { color: var(--tp-secondary); line-height: 1.45; }
.tp-score-track { height:8px; position:relative; background:#263652; border-radius:6px; margin:.65rem 0 .4rem; }
.tp-score-fill { height:100%; background:#78A9FF; border-radius:6px; }
.tp-score-track i, .tp-score-track b { position:absolute; top:-3px; height:14px; width:2px; background:#8293A6; }
.tp-score-track b { background:#EAF1F7; }
.tp-score-label { color:#8293A6; font-size:.75rem; }
.tp-monitor-count { display:flex; align-items:center; gap:8px; min-height:42px; padding:8px 6px; border:1px solid var(--count-color); border-radius:8px; color:#EAF1F7; }
.tp-monitor-count b { color:var(--count-color); font-size:1.15rem; }
.tp-monitor-count span { font-size:.75rem; }
:focus-visible { outline:3px solid #9BC0FF !important; outline-offset:2px !important; }
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button { min-height:2.45rem; font-weight:650; border-radius:9px; transition:transform .15s ease, border-color .15s ease, box-shadow .15s ease; }
[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] button:hover { border-color:#A6F36A; box-shadow:0 5px 18px #A6F36A20; transform:translateY(-1px); }
[data-testid="stSidebar"] [data-testid="stButton"] button { min-height:2.25rem; justify-content:flex-start; padding:.38rem .68rem; font-size:.76rem; text-align:left; }
.st-key-tp-navigation [data-testid="stButton"] button[kind="secondary"] { color:#A9BAC9; background:transparent; border-color:transparent; box-shadow:none; font-weight:550; }
.st-key-tp-navigation [data-testid="stButton"] button[kind="secondary"]:hover { color:#F1F6FA; background:#162332; border-color:#263748; box-shadow:none; transform:translateX(2px); }
.st-key-tp-navigation [data-testid="stButton"] button[kind="primary"] { color:#0B141B; background:linear-gradient(100deg,#A6F36A,#B8F782); border:1px solid #B8F782; box-shadow:0 5px 18px #A6F36A24; font-weight:750; }
.st-key-tp-navigation [data-testid="stButton"] button[kind="primary"]:hover { color:#0B141B; box-shadow:0 7px 22px #A6F36A32; transform:translateY(-1px); }
.st-key-tp-workspace-controls, .st-key-tp-map-workspace { border:1px solid #263748; border-radius:14px; background:linear-gradient(145deg,#111C29E8,#0C141EE8); box-shadow:0 12px 32px #02070D38; padding:1rem 1.05rem; }
.st-key-tp-workspace-controls [data-testid="stVerticalBlock"] { gap:.75rem; }
.st-key-tp-map-workspace { padding:.85rem 1rem .3rem; margin-bottom:.55rem; }
.st-key-tp-workspace-controls { padding:1.2rem 1.2rem 1.35rem; }
[data-testid="stSelectbox"] label, [data-testid="stRadio"] label, [data-testid="stSlider"] label { color:#C2CED8; font-weight:600; }
[data-testid="stRadio"] div[role="radiogroup"] { gap:.45rem; }
[data-testid="stRadio"] div[role="radiogroup"] label { background:#121E2A; border:1px solid #263748; border-radius:9px; padding:.35rem .65rem; }
[data-testid="stRadio"] label { border-radius:9px; }
[data-testid="stExpander"] { border-color:#253548; border-radius:8px; background:#0D152066; }
[data-testid="stMetric"] { background:#111C29; border:1px solid #253548; border-radius:8px; padding:.7rem .8rem; }
[data-testid="stCaptionContainer"] { color:var(--tp-secondary); }
abbr[title] { text-decoration:underline dotted; text-underline-offset:2px; cursor:help; }
@media (max-width: 1400px) {
  [data-testid="stSidebar"] { min-width:270px !important; max-width:270px !important; }
  [data-testid="stMainBlockContainer"] { min-width:0; }
}
@media (max-width: 1280px) {
  [data-testid="stSidebar"] { min-width:255px !important; max-width:255px !important; }
  [data-testid="stCustomComponentV1"], [data-testid="stCustomComponentV1"] iframe { min-height:560px; }
  [data-testid="stSidebarContent"] { padding:.8rem .75rem 1rem; }
}
@media (max-width: 1100px) {
  .st-key-tp-topbar { margin:-1.25rem -1.2rem 1rem; padding:.65rem 1.2rem; }
  [data-testid="stMainBlockContainer"], .main .block-container { padding:1.25rem 1.2rem 1.6rem !important; }
  [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; gap:1rem !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="column"] { flex:1 1 100% !important; min-width:100% !important; width:100% !important; }
  .tp-workspace-header { padding-left:.8rem; padding-right:.8rem; margin-bottom:1rem; }
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding: .8rem .65rem 1.2rem !important; }
  .tp-workspace-title { font-size:1.4rem; }
  .st-key-tp-workspace-controls, .st-key-tp-map-workspace { padding:.75rem; }
  [data-testid="stCustomComponentV1"], [data-testid="stCustomComponentV1"] iframe { height: 72vh !important; min-height: 520px; }
}
@media (max-width: 760px) {
  [data-testid="stSidebar"] { min-width:min(88vw, 340px) !important; max-width:min(88vw, 340px) !important; }
  [data-testid="stCustomComponentV1"], [data-testid="stCustomComponentV1"] iframe { min-height:520px; }
}
"""


def inject_theme(streamlit) -> None:
    streamlit.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
