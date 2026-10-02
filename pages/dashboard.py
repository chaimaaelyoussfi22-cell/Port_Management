# -*- coding: utf-8 -*-
"""Page principale — Smart Port Command Center / Port Performance Intelligence.

Pipeline : données réelles → filtres → contexte analytique unique (KPI N/N-1,
segments par poste, score composite, diagnostics, alertes) → rendu.
Tout est recalculé à chaque changement de filtre ; aucune valeur statique.
"""

import streamlit as st

from database import db_manager
from components.dashboard.header import render_header
from components.dashboard.filters import render_filters
from components.dashboard.helpers import apply_filters
from components.dashboard.kpi_cards import render_kpi_cards
from components.dashboard.performance_score import render_performance_score
from components.dashboard.digital_twin import render_digital_twin
from components.dashboard.poste_panel import render_poste_panel
from components.dashboard.smart_alerts import render_smart_alerts
from components.dashboard.smart_advisor import render_smart_advisor


def load_dashboard_css():
    with open("assets/dashboard.css", encoding="utf-8") as css:
        st.markdown(f"<style>{css.read()}</style>", unsafe_allow_html=True)

    # ===================== THÈME BLEU CIEL — poissons animés =====================
    st.markdown("""
    <style>
    /* --- Fond bleu ciel de l'océan --- */
    .stApp {
        background:
            radial-gradient(circle at 15% 18%, rgba(255,255,255,.55), transparent 32%),
            radial-gradient(circle at 84% 55%, rgba(186,230,253,.75), transparent 38%),
            linear-gradient(180deg, #7ec8f5 0%, #a9dcf7 36%, #d4f2ff 72%, #f5fbff 100%) !important;
        color: #0b315a !important;
    }
    .block-container { position: relative; z-index: 1; }

    /* --- Poissons qui nagent dans le décor --- */
    .stApp::after {
        content: "🐟";
        position: fixed; left: 0; top: 34%; z-index: 0;
        font-size: 54px; line-height: 1; opacity: .64; pointer-events: none;
        animation: anpSwimA 26s linear infinite;
    }
    @keyframes anpSwimA {
        0%   { transform: translate(-200px, 0) scaleX(-1); }
        25%  { transform: translate(calc(25vw), -18px) scaleX(-1); }
        50%  { transform: translate(calc(50vw), 8px) scaleX(-1); }
        75%  { transform: translate(calc(75vw), -12px) scaleX(-1); }
        100% { transform: translate(calc(110vw), 0) scaleX(-1); }
    }
    .stApp .block-container::before {
        content: "🐠";
        position: fixed; left: 0; top: 57%; z-index: 0;
        font-size: 34px; line-height: 1; opacity: .6; pointer-events: none;
        animation: anpSwimB 18s linear infinite;
    }
    @keyframes anpSwimB {
        0%   { transform: translate(110vw, 0); }
        30%  { transform: translate(calc(70vw), -14px); }
        60%  { transform: translate(calc(40vw), 8px); }
        100% { transform: translate(-220px, 0); }
    }
    .stApp [data-testid="stMain"]::before {
        content: "🦈";
        position: fixed; left: 0; top: 76%; z-index: 0;
        font-size: 88px; line-height: 1; opacity: .46; pointer-events: none;
        animation: anpSwimC 40s linear infinite;
    }
    @keyframes anpSwimC {
        0%   { transform: translate(-260px, 0) scaleX(-1); }
        25%  { transform: translate(calc(25vw), 12px) scaleX(-1); }
        50%  { transform: translate(calc(50vw), -10px) scaleX(-1); }
        75%  { transform: translate(calc(75vw), 6px) scaleX(-1); }
        100% { transform: translate(calc(110vw), 0) scaleX(-1); }
    }
    .stApp [data-testid="stMain"]::after {
        content: "🐟";
        position: fixed; left: 0; top: 16%; z-index: 0;
        font-size: 28px; line-height: 1; opacity: .62; pointer-events: none;
        animation: anpSwimD 14s linear infinite;
    }
    @keyframes anpSwimD {
        0%   { transform: translate(110vw, 0); }
        35%  { transform: translate(calc(65vw), -12px); }
        70%  { transform: translate(calc(30vw), 6px); }
        100% { transform: translate(-200px, 0); }
    }

    /* --- Coquillage posé au fond --- */
    .stApp .block-container::after {
        content: "🐚";
        position: fixed; left: 20px; bottom: 16px; z-index: 0;
        font-size: 40px; line-height: 1; opacity: .42; pointer-events: none;
        transform: rotate(-16deg);
        filter: drop-shadow(0 5px 7px rgba(0,60,110,.22));
    }
    </style>
    """, unsafe_allow_html=True)


def show_dashboard():
    load_dashboard_css()
    render_header()

    operations = db_manager.get_operations()
    if operations is None or operations.empty:
        st.warning("Aucune opération dans la base. Importez des escales ou saisissez une opération "
                   "pour alimenter le Port Performance Intelligence.")
        return

    filters = render_filters(operations)
    filtered = apply_filters(operations, filters)

    if filtered.empty:
        st.info("Aucune donnée ne correspond aux filtres sélectionnés.")
        return

    from components.dashboard.analytics import build_context
    ctx = build_context(filtered, filters)

    render_kpi_cards(ctx)

    left, right = st.columns([2, 3], gap="medium")
    with left:
        render_performance_score(ctx)
    with right:
        render_digital_twin(ctx)
        render_poste_panel(ctx)

    alerts_col, advisor_col = st.columns(2)
    with alerts_col:
        render_smart_alerts(ctx)
    with advisor_col:
        render_smart_advisor(ctx)
