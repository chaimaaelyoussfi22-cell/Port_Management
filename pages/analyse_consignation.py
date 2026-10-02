# -*- coding: utf-8 -*-
"""PAGE /analyse_consignation — Carte « CONSIGNATION » : diagnostic global
des événements de consignation.

Dashboard compact type Power BI : chaque graphique possède SES PROPRES filtres
intégrés à sa card (année, mois, cause…). Aucun filtre global. Toutes les
périodes / postes / causes proviennent exclusivement des données réelles.
"""

import streamlit as st

from database import db_manager
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.consignation_views import (
    prepare_consignations,
    available_years, available_months, available_causes, available_postes,
    kpi_block, fig_by_poste, fig_causes, fig_duration_distrib,
    port_stats, fig_port, events_table, NO_CAUSE,
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


def _kpi(label: str, value: str, sub: str, accent: str = ""):
    style = f' style="border-left:4px solid {accent}"' if accent else ""
    st.markdown(f'<div class="an-kpi"{style}><small>{label}</small>'
                f'<strong>{value}</strong>'
                f'<em class="var-chip neutral">{sub}</em></div>',
                unsafe_allow_html=True)


def _year_sel(years: list, prefix: str, label: str = "Année"):
    return st.selectbox(label, years, key=f"{prefix}_year")


def _months_sel(frame, year: int, prefix: str, label: str = "Mois",
                placeholder: str = "Tous les mois"):
    avail = available_months(frame, year)
    names = [MOIS_NOMS[m - 1] for m in avail]
    _keep_valid(f"{prefix}_months", names)
    sel = st.multiselect(label, names, key=f"{prefix}_months",
                         placeholder=placeholder,
                         label_visibility="collapsed")
    return sorted(MOIS_NOMS.index(n) + 1 for n in sel)


def _causes_sel(frame, year: int, months: list, prefix: str,
                label: str = "Cause 🔍", placeholder: str = "Toutes"):
    opts = available_causes(frame, year, months)
    _keep_valid(f"{prefix}_causes", opts)
    return st.multiselect(label, opts, key=f"{prefix}_causes",
                          placeholder=placeholder,
                          label_visibility="collapsed")


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

mini_span = frame["date_debut"].min(), frame["date_debut"].max()

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>⚓ CONSIGNATION</h1>'
            '<p>Analyse des événements de consignation · diagnostics par poste, '
            'cause et durée</p></div>', unsafe_allow_html=True)

# ==================================================================
# KPI BAND — diagnostic global (toutes les données réelles)
# ==================================================================
kpi = kpi_block(frame)
d_span = f"{mini_span[0]:%d/%m/%Y} → {mini_span[1]:%d/%m/%Y}"

kc1, kc2, kc3, kc4 = st.columns(4)
with kc1:
    _kpi("🚨 Événements", f"{kpi['count']:,}".replace(",", " "),
         sub=f"période : {d_span}")
with kc2:
    _kpi("⏱ Durée moyenne", f"{kpi['duree_moy']:.1f} j".replace(".", ","),
         sub=f"{kpi['duree_moy'] * 24:.1f} h".replace(".", ","))
with kc3:
    _kpi("⏱ Durée totale", f"{kpi['duree_tot']:,} j".replace(",", " ")
         .replace(".", ","), sub="cumul réel des durées")
with kc4:
    _kpi("📍 Postes concernés", f"{kpi['n_postes']}",
         accent="#62ddff", sub="postes distincts")

st.markdown('<div class="an-chips">' +
            _chip(f"Période couverte : <b>{d_span}</b>") +
            _chip("Source : <b>table consignations</b>") +
            _chip("Chaque carte possède <b>ses propres filtres</b>") +
            "</div>", unsafe_allow_html=True)

# ==================================================================
# ① CONSIGNATIONS PAR POSTE  |  ② CAUSES PRINCIPALES
# ==================================================================
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>📊 Consignations par poste</h4>'
                    '<span class="an-card-badge">ordre métier</span></div>',
                    unsafe_allow_html=True)
        fy, fm = st.columns(2)
        with fy:
            year1 = _year_sel(years, "cs1")
        with fm:
            months1 = _months_sel(frame, year1, "cs1")
        fig_p, _ = fig_by_poste(frame, year1, months1)
        _chart(fig_p, "Aucune consignation pour cette période.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>🚨 Causes principales</h4></div>',
                    unsafe_allow_html=True)
        fy, fm, fc = st.columns([1, 1, 1.4])
        with fy:
            year2 = _year_sel(years, "cs2")
        with fm:
            months2 = _months_sel(frame, year2, "cs2")
        with fc:
            causes2 = _causes_sel(frame, year2, months2, "cs2")
        fig, _ = fig_causes(frame, year2, months2, causes2)
        _chart(fig, "Aucune cause renseignée sur cette période.")

# ==================================================================
# ③ DURÉE DES CONSIGNATIONS  |  ④ CONSIGNATION PORT
# ==================================================================
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⏱ Durée des consignations</h4></div>',
                    unsafe_allow_html=True)
        fy, fm, fc = st.columns([1, 1, 1.4])
        with fy:
            year3 = _year_sel(years, "cs3")
        with fm:
            months3 = _months_sel(frame, year3, "cs3")
        with fc:
            causes3 = _causes_sel(frame, year3, months3, "cs3")
        fig, _ = fig_duration_distrib(frame, year3, months3, causes3)
        _chart(fig, "Aucune durée exploitable sur cette période.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>🌐 Consignation PORT — vue globale</h4>'
                    '<span class="an-card-badge">poste = PORT</span></div>',
                    unsafe_allow_html=True)
        fy, fm = st.columns(2)
        with fy:
            year4 = _year_sel(years, "cs4")
        with fm:
            months4 = _months_sel(frame, year4, "cs4")
        ps = port_stats(frame, year4, months4)
        moy_txt = f"{ps['duree_moy']:.1f}".replace(".", ",")
        tot_txt = f"{ps['duree_tot']:,.1f}".replace(",", " ").replace(".", ",")
        st.markdown(
            '<div class="an-mini-stats">'
            f'<div class="an-mini"><span>Événements PORT</span>'
            f'<b>{ps["count"]}</b></div>'
            f'<div class="an-mini"><span>Durée moyenne</span><b>{moy_txt} j</b></div>'
            f'<div class="an-mini"><span>Durée totale</span><b>{tot_txt} j</b></div>'
            '</div>', unsafe_allow_html=True)
        fig_port_v, _ = fig_port(frame, year4, months4)
        if fig_port_v is not None:
            _chart(fig_port_v, "")
        elif ps["total_all"] == 0:
            st.info("Aucune consignation PORT (poste = « PORT ») dans les données.")

# ==================================================================
# ⑤ TABLE DES ÉVÉNEMENTS
# ==================================================================
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>📋 Derniers événements</h4>'
                '<span class="an-card-badge">compact</span></div>',
                unsafe_allow_html=True)
    fy, fp, fc, fn = st.columns([1.2, 1.6, 1.8, 0.8])
    with fy:
        year_opts = [0] + years
        year5 = st.selectbox("Année", year_opts, key="cs5_year",
                             format_func=lambda y: "Toutes les années"
                             if y == 0 else str(y))
    with fp:
        poste_opts = available_postes(frame, year5 or None, None)
        _keep_valid("cs5_poste", poste_opts)
        poste5 = st.multiselect("Poste", poste_opts, key="cs5_poste",
                                placeholder="Tous", label_visibility="collapsed")
    with fc:
        if year5:
            cause_opts = available_causes(frame, year5, None)
        else:
            cause_opts = sorted({c if c else NO_CAUSE
                                 for c in frame["motif"].unique()})
        _keep_valid("cs5_cause", cause_opts)
        cause5 = st.multiselect("Cause", cause_opts, key="cs5_cause",
                                placeholder="Toutes", label_visibility="collapsed")
    with fn:
        rows_sel = st.selectbox("Lignes", [10, 20, 50], key="cs5_rows",
                                label_visibility="collapsed")

    table, total = events_table(frame, year5 or None, None, poste5, cause5,
                                limit=rows_sel)
    if table.empty:
        st.info("Aucun événement ne correspond aux filtres de la table.")
    else:
        shown = len(table)
        note = f" — {total}" if total > shown else ""
        st.caption(f"{shown} événement(s) affiché(s){note} (par ordre de date décroissant)")
        st.dataframe(table, use_container_width=True, hide_index=True)

st.markdown(
    '<div class="an-methodo">Méthodologie — Consignations : événements de '
    "fermeture de poste · « PORT » = consignation globale du port (jamais "
    "supprimée) · Durée = nombre_heures (sinon écart déconsignation − "
    "consignation) · « Mouvement » = observations de l'import · "
    "Toutes les périodes, causes et postes proviennent des données réelles.</div>",
    unsafe_allow_html=True)