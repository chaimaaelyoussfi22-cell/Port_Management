# -*- coding: utf-8 -*-
"""PAGE /analyse_sejour — Analyse du séjour à quai (dashboard type Power BI).

Layout compact : chaque graphique dans sa propre card avec filtres intégrés.
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.sejour_views import (
    available_years, kpi_block, fig_evolution, fig_poste, fig_marchandise,
    fig_type_navire, fig_operateur, fig_distribution,
    fig_performance_poste, performance_by_poste, sejour_insights,
    ALL_POSTES, ALL_MARCHANDISES, poste_options, marchandise_options)


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
        if k.startswith("sq_"):
            del st.session_state[k]


def _keep_valid(key: str, opts: list):
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept


def _kpi(label: str, value: str, var: float | None = None, sub: str = ""):
    cls = "neutral" if var is None else ("good" if var >= 0 else "bad")
    arrow = "" if var is None else ("▼" if var < 0 else "▲" if var >= 0 else "")
    st.markdown(f'<div class="an-kpi"><small>{label}</small>'
                f'<strong>{value}</strong>'
                f'<em class="var-chip {cls}">{arrow} {sub}</em></div>',
                unsafe_allow_html=True)


# ==================================================================
# DONNÉES
# ==================================================================
operations = db_manager.get_operations()
if operations is None or operations.empty:
    st.warning("Aucune opération dans la base — importez des escales pour alimenter l'analyse.")
    st.stop()

_load_css()
prepared = prepare_operations(operations)
years = available_years(prepared)
if not years:
    st.warning("Aucune donnée de séjour à quai exploitable dans la base.")
    st.stop()

# ==================================================================
# EN-TÊTE + FILTRES GLOBAUX
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>SÉJOUR À QUAI</h1></div>',
            unsafe_allow_html=True)

with st.container(border=True):
    fh, fy, fg, fr = st.columns([1.15, 1.05, 1.35, 0.8], vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="sq_year",
                            help="N-1 comparé automatiquement.",
                            label_visibility="collapsed")
    with fg:
        gran = st.segmented_control("Granularité évolution",
                                    ["Par mois", "Par jour"], key="sq_gran",
                                    default="Par mois",
                                    label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

prev_year = year - 1
kpi = kpi_block(prepared, year)

# ==================================================================
# KPI BAND
# ==================================================================
k1, k2, k3, k4, k5 = st.columns(5)
with k1:
    _kpi("Séjour moyen", f"{kpi['avg']:.1f} h",
         kpi["evolution"] if kpi["evolution"] is None else -kpi["evolution"],
         "vs N-1" if kpi["evolution"] is not None else "")
with k2:
    _kpi("Médiane", f"{kpi['median']:.1f} h")
with k3:
    _kpi("Maximum", f"{kpi['max']:.1f} h")
with k4:
    _kpi("Navires", f"{kpi['ships']}", sub=f"{kpi['count']} escales")
with k5:
    _kpi("Référence", f"N-1 : {prev_year}")

# ==================================================================
# CARDS
# ==================================================================

# --- CARD ① : Évolution N vs N-1 ---
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>① Évolution du séjour moyen</h4>'
                f'<span class="an-card-sub">{year} vs {prev_year}</span></div>',
                unsafe_allow_html=True)
    fig1 = fig_evolution(prepared, year, gran or "Par mois")
    if fig1 is None:
        st.info("Données insuffisantes pour tracer l'évolution.")
    else:
        st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})

# --- ROW : ② Poste | ③ Marchandise ---
row1_l, row1_r = st.columns(2, gap="medium")
month_opts = [MOIS_NOMS[m - 1] for m in sorted(prepared[prepared["year"] == year]["month"].dropna().unique().astype(int).tolist())]

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Séjour par poste</h4></div>',
                    unsafe_allow_html=True)
        pick_m_poste = st.multiselect("Mois", month_opts, key="sq_m_poste",
                                      placeholder="Toute l'année",
                                      label_visibility="collapsed")
        months_poste = sorted(month_opts.index(m) + 1 for m in pick_m_poste)
        _poste_opts = poste_options(prepared, year, months_poste)
        _keep_valid("sq_p_poste", _poste_opts)
        pick_p_poste = st.multiselect("Poste(s)", _poste_opts,
                                      key="sq_p_poste",
                                      default=[ALL_POSTES],
                                      placeholder="Tous les postes",
                                      label_visibility="collapsed")
        fig2, t2 = fig_poste(prepared, year, months_poste, pick_p_poste)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucun poste pour cette sélection.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Séjour par marchandise</h4></div>',
                    unsafe_allow_html=True)
        pick_m_march = st.multiselect("Mois", month_opts, key="sq_m_march",
                                      placeholder="Toute l'année",
                                      label_visibility="collapsed")
        months_march = sorted(month_opts.index(m) + 1 for m in pick_m_march)
        _march_opts = marchandise_options(prepared, year, months_march)
        _keep_valid("sq_p_march", _march_opts)
        pick_m_f = st.multiselect("Marchandise(s)", _march_opts,
                                  key="sq_p_march",
                                  default=[ALL_MARCHANDISES],
                                  placeholder="Toutes les marchandises",
                                  label_visibility="collapsed")
        fig3, t3 = fig_marchandise(prepared, year, months_march, pick_m_f)
        if fig3:
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune marchandise pour cette sélection.")

# --- ROW : ④ Type navire | ⑤ Opérateur ---
row2_l, row2_r = st.columns(2, gap="medium")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>④ Séjour par type de navire</h4></div>',
                    unsafe_allow_html=True)
        pick_m_type = st.multiselect("Mois", month_opts, key="sq_m_type",
                                     placeholder="Toute l'année",
                                     label_visibility="collapsed")
        months_type = sorted(month_opts.index(m) + 1 for m in pick_m_type)
        fig4, t4 = fig_type_navire(prepared, year, months_type)
        if fig4:
            st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucun type de navire pour cette sélection.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⑤ Séjour par opérateur</h4></div>',
                    unsafe_allow_html=True)
        pick_m_op = st.multiselect("Mois", month_opts, key="sq_m_op",
                                   placeholder="Toute l'année",
                                   label_visibility="collapsed")
        months_op = sorted(month_opts.index(m) + 1 for m in pick_m_op)
        fig5, t5 = fig_operateur(prepared, year, months_op)
        if fig5:
            st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucun opérateur pour cette sélection.")

# --- ROW : ⑥ Distribution (jours) | ⑦ Insights ---
row3_l, row3_r = st.columns(2, gap="medium")

with row3_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⑥ Distribution des durées</h4></div>',
                    unsafe_allow_html=True)
        fig6 = fig_distribution(prepared, year)
        if fig6:
            st.plotly_chart(fig6, use_container_width=True, config={"displayModeBar": False})
            st.caption("Durées exprimées en jours (Appareillage_Quai − Accostage).")
        else:
            st.info("Aucune donnée de durée.")

with row3_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⑦ Insights intelligents</h4></div>',
                    unsafe_allow_html=True)
        insights = sejour_insights(prepared, year, months_poste)
        for ins in insights:
            st.markdown(f'<div style="padding:4px 0;font-size:.84rem;color:#0B3A5B;'
                        f'border-bottom:1px solid #cfe6f8">{ins}</div>',
                        unsafe_allow_html=True)

# --- ROW : ⑧ Performance par poste (pleine largeur) ---
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>⑧ Performance par poste</h4></div>',
                unsafe_allow_html=True)
    pick_m_perf = st.multiselect("Mois", month_opts, key="sq_m_perf",
                                 placeholder="Toute l'année",
                                 label_visibility="collapsed")
    months_perf = sorted(month_opts.index(m) + 1 for m in pick_m_perf)
    _perf_opts = poste_options(prepared, year, months_perf)
    _keep_valid("sq_p_perf", _perf_opts)
    pick_p_perf = st.multiselect("Poste(s)", _perf_opts,
                                 key="sq_p_perf",
                                 default=[ALL_POSTES],
                                 placeholder="Tous les postes",
                                 label_visibility="collapsed")
    perf = performance_by_poste(prepared, year, months_perf, pick_p_perf)
    if not perf.empty:
        st.dataframe(perf.rename(columns={
            "poste": "Poste", "navires": "Navires",
            "escales": "Escales", "sejour_moyen": "Séjour (h)",
            "tonnage": "Tonnage (t)"}),
            use_container_width=True, hide_index=True, height=300)
        csv = perf.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇ CSV", data=csv,
                           file_name="sejour_quai_postes.csv",
                           mime="text/csv", use_container_width=False)
    else:
        st.info("Aucune donnée.")
