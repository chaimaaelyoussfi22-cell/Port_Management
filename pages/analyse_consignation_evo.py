# -*- coding: utf-8 -*-
"""PAGE /analyse_consignation_evo — Carte « ÉVOLUTION DE LA CONSIGNATION » :
analyse temporelle des événements de consignation.

Dashboard compact type Power BI : carte « Évolution par poste » avec
comparaison N vs N-1 intégrée (trait plein = N, pointillés = N-1 dans une
couleur distincte). Tous les axes utilisent les périodes réellement présentes
dans les données.
"""

import streamlit as st

from database import db_manager
from components.dashboard.consignation_views import (
    prepare_consignations,
    available_years, duration_boundaries, format_boundaries_note,
    DUR_CAT_OPTIONS,
)
from components.dashboard.consignation_evo_views import (
    ALL_POSTES, poste_options,
    fig_evo_poste,
)


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


def _chip(txt: str) -> str:
    return f'<span class="an-chip">{txt}</span>'


def _keep_valid(key: str, opts: list):
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept


def _year_sel(years: list, prefix: str, label: str = "Année"):
    return st.selectbox(label, years, key=f"{prefix}_year")


def _dur_sel(prefix: str, label: str = "Durée"):
    return st.selectbox(label, DUR_CAT_OPTIONS, key=f"{prefix}_dur")


def _chart(fig, empty_note: str):
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.info(empty_note)


# ==================================================================
# DONNÉES RÉELLES
# ==================================================================
raw = db_manager.get_consignations(limit=20000)
frame = prepare_consignations(raw)
if frame.empty:
    st.warning("Aucune consignation dans la base — importez des consignations "
               "pour alimenter l'analyse.")
    st.stop()

_load_css()
years = available_years(frame)
if not years:
    st.warning("Aucune consignation datable.")
    st.stop()

boundaries = duration_boundaries(frame)

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>📈 ÉVOLUTION DE LA CONSIGNATION</h1>'
            '<p>Évolution par poste avec comparaison N vs N-1 — trait plein : '
            'année N · pointillés : année N-1</p></div>', unsafe_allow_html=True)

st.markdown('<div class="an-chips">' +
            _chip("Périodes : <b>uniquement celles présentes dans les données</b>") +
            _chip(format_boundaries_note(boundaries)) +
            "</div>", unsafe_allow_html=True)

# ==================================================================
# CARD UNIQUE : ÉVOLUTION PAR POSTE (avec N vs N-1 intégré)
# ==================================================================
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>⚓ Évolution par poste — N vs N-1</h4></div>',
                unsafe_allow_html=True)
    fy, fd = st.columns(2, gap="large")
    with fy:
        year_b = _year_sel(years, "ev_b",
                           label="Année (trait plein)")
    with fd:
        dur_b = _dur_sel("ev_b")
    poste_opts = poste_options(frame, year_b)
    _keep_valid("ev_b_postes", poste_opts)
    postes_b = st.multiselect("Poste(s)", poste_opts, key="ev_b_postes",
                              default=[ALL_POSTES],
                              placeholder="Tous les postes",
                              label_visibility="collapsed")
    fig, _, has_prev = fig_evo_poste(frame, year_b, dur_b, boundaries, postes_b)
    _chart(fig, "Aucune donnée pour cette sélection.")
    if fig is not None and not has_prev:
        st.caption(f"⚠ Comparaison N-1 indisponible : aucune donnée en {year_b - 1}.")

st.markdown(
    '<div class="an-methodo">Méthodologie — Évolution de la consignation : '
    "périodes réellement présentes dans le dataset · trait plein = année N, "
    "pointillés (couleur distincte) = année N-1, affichés uniquement sur les "
    "périodes réelles · Catégories de durée : Courte / Moyenne / Longue selon "
    "les percentiles 33e et 66e des durées réelles.</div>",
    unsafe_allow_html=True)