# -*- coding: utf-8 -*-
"""PAGE /analyse_occupation — Taux d'occupation des postes : UTILISATION.

Dashboard compact type Power BI · chaque graphique dans sa card avec filtres intégrés.
Métrique : taux d'occupation = temps occupé / (jours × 24h) × 100.
"""

import streamlit as st

import pandas as pd

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.occupation_views import (
    kpi_block, _state_data, state_table_html, _fig_evolution,
    _fig_status_split)
from components.dashboard.occupation import (
    quay_intervals, monthly_occupancy, poste_order)


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


def _chip(txt: str) -> str:
    return f'<span class="an-chip">{txt}</span>'


def _reset_filters():
    for k in list(st.session_state):
        if k.startswith("oc_"):
            del st.session_state[k]


def _kpi(label: str, value: str, accent: str = "", sub: str = ""):
    style = f' style="border-left:4px solid {accent}"' if accent else ""
    st.markdown(f'<div class="an-kpi"{style}><small>{label}</small>'
                f'<strong>{value}</strong>'
                f'<em class="var-chip neutral">{sub}</em></div>',
                unsafe_allow_html=True)


def _available_years(monthly: pd.DataFrame) -> list[int]:
    if monthly.empty:
        return []
    return sorted(monthly["year"].unique().tolist(), reverse=True)


# ==================================================================
# DONNÉES
# ==================================================================
operations = db_manager.get_operations()
if operations is None or operations.empty:
    st.warning("Aucune opération dans la base — importez des escales pour alimenter l'analyse.")
    st.stop()

_load_css()
prepared = prepare_operations(operations)

# Build intervals + monthly once (shared across all cards)
intervals = quay_intervals(prepared)
if intervals.empty:
    st.warning("Aucun intervalle d'occupation calculable.")
    st.stop()

_all_monthly = monthly_occupancy(intervals)
if _all_monthly.empty:
    st.warning("Aucune donnée d'occupation mensuelle disponible.")
    st.stop()

years = _available_years(_all_monthly)
if not years:
    st.warning("Aucune année exploitable.")
    st.stop()

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>TAUX D\'OCCUPATION PAR POSTE</h1>'
            '<p>Port Analytics Studio · utilisation · charge des postes</p></div>',
            unsafe_allow_html=True)

# ==================================================================
# FILTRES GLOBAUX
# ==================================================================
with st.container(border=True):
    fh, fy, fm, fr = st.columns([1.25, 0.95, 1.1, 0.85],
                                vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="oc_year",
                            label_visibility="collapsed")
    with fm:
        months_list = st.multiselect(
            "Mois", list(MOIS_NOMS), key="oc_months",
            placeholder="Toute l'année", label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

months = sorted(MOIS_NOMS.index(m) + 1 for m in months_list)

# ==================================================================
# KPI BAND
# ==================================================================
kpi = kpi_block(_all_monthly, year)

kc1, kc2, kc3, kc4 = st.columns(4)
with kc1:
    _kpi("Occupation moy.", f"{kpi['avg_occ']:.1f} %",
         sub="moyenne tous postes")
with kc2:
    _kpi("Postes actifs", f"{kpi['n_postes']}", sub="postes d'accostage")
with kc3:
    _kpi("🔴 Saturation", f"{kpi['n_critical']}",
         accent="#ff6077", sub="taux > 80 %")
with kc4:
    _kpi("🟠 Très sollicités", f"{kpi['n_busy']}",
         accent="#f2b84b", sub="taux 70–80 %")

chips = [_chip(f"Année : <b>{year}</b>"),
         _chip("Formule : <b>occupé ÷ (jours × 24h) × 100</b>")]
if months_list:
    chips.append(_chip(f"Mois : <b>{', '.join(months_list)}</b>"))
st.markdown('<div class="an-chips">' + "".join(chips) + "</div>",
            unsafe_allow_html=True)

# ==================================================================
# CARD ① : ÉTAT D'OCCUPATION DES POSTES
# ==================================================================
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>⚓ État d\'occupation des postes</h4></div>',
                unsafe_allow_html=True)
    state_df = _state_data(_all_monthly, year, months, None)
    if state_df is not None and not state_df.empty:
        st.markdown(state_table_html(state_df), unsafe_allow_html=True)
    else:
        st.info("Aucune donnée d'occupation pour cette période.")

# ==================================================================
# ROW : ② ÉVOLUTION | ③ RÉPARTITION
# ==================================================================
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>📈 Évolution du taux d\'occupation par poste — N vs N-1</h4></div>',
                    unsafe_allow_html=True)
        all_postes = poste_order(_all_monthly["poste"])
        evo_poste = st.multiselect(
            "Poste(s)", all_postes, key="oc_evo_poste",
            placeholder="Tous", label_visibility="collapsed")
        fig_evo, _ = _fig_evolution(_all_monthly, year, months, evo_poste)
        if fig_evo is not None:
            st.plotly_chart(fig_evo, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée d'évolution.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>🚦 Répartition des postes</h4></div>',
                    unsafe_allow_html=True)
        fig_status = _fig_status_split(_all_monthly, year)
        if fig_status is not None:
            st.plotly_chart(fig_status, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée de répartition.")

st.markdown(
    '<div class="an-methodo">Méthodologie — Taux d\'occupation = '
    "Temps occupé (union dédupliquée) ÷ (Jours calendrier × 24 h) × 100 · "
    "Postes d\'ancrage exclus (RADE, MOUILLAGE) · "
    "Ordre des postes : 1N, 1S, 1Bis, 1Ter, 2N, 2Bis, 2Ter, 3, 3Bis, 4, "
    "4Bis, 5, 6, 7, 8, 9, 10, 11_12, 13, 14N, 14S, 16N, 16S · "
    "Statut : 🔵 < 50 % · 🟢 50–< 70 % · 🟠 70–< 80 % · 🔴 ≥ 80 %.</div>",
    unsafe_allow_html=True)
