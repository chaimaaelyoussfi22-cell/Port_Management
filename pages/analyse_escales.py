# -*- coding: utf-8 -*-
"""PAGE /analyse_escales — Analyse des escales (dashboard type Power BI).

Layout Power BI compact : 2×2 cards, AUCUNE zone de filtres globale.
Chaque graphique possède SES PROPRES filtres dans son cadre ; les listes
Marchandise / Type de navire / Opérateur sont construites dynamiquement à
partir des données réellement présentes pour la période sélectionnée.
Méthodologie : COUNT DISTINCT n° d'escale · N vs N-1 sur la même période réelle.
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.escales_views import (
    available_years, available_months, available_categories,
    fig_evolution, fig_marchandise, fig_category,
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


def _prune(key: str, opts: list):
    """Lists dynamiques : retire les valeurs absentes des nouvelles options.
    Sélection vidée → on reprend toute la nouvelle liste (jamais de graphique vide)."""
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept or opts


def _prune_select(key: str, opts: list):
    v = st.session_state.get(key)
    if v is not None and v not in opts:
        st.session_state[key] = opts[0] if opts else None


def _year_sel(years: list, prefix: str):
    return st.selectbox("Année", years, key=f"{prefix}_y")


def _months_multi(frame, year, prefix):
    opts = available_months(frame, year)
    _prune(f"{prefix}_m", opts)
    return st.multiselect("Mois", opts, key=f"{prefix}_m",
                          format_func=lambda m: MOIS_NOMS[m - 1],
                          placeholder="Toute l'année",
                          label_visibility="collapsed")


def _chart(fig, note: str):
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.info(note)


# ==================================================================
# DONNÉES RÉELLES
# ==================================================================
operations = db_manager.get_operations()
if operations is None or operations.empty:
    st.warning("Aucune opération dans la base — importez des escales pour alimenter l'analyse.")
    st.stop()

_load_css()
prepared = prepare_operations(operations)
years = available_years(prepared)
if not years:
    st.warning("Aucune escale datable dans la base.")
    st.stop()

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>⚓ ANALYSE DES ESCALES</h1>'
            '<p>Dashboard Power BI · chaque graphique possède ses propres '
            'filtres · périodes réellement présentes dans les données</p></div>',
            unsafe_allow_html=True)

st.markdown('<div class="an-chips">' +
            _chip("Listes <b>Marchandise / Type de navire / Opérateur</b> "
                  "reconstruites selon la période choisie") +
            _chip("N vs N-1 : <b>même période réelle</b>") +
            "</div>", unsafe_allow_html=True)

# ==================================================================
# ROW 1 : ① Évolution N vs N-1 | ② Marchandise
# ==================================================================
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>① Évolution des escales — N vs N-1</h4></div>',
                    unsafe_allow_html=True)
        fy, fg = st.columns(2, gap="large")
        with fy:
            year_a = _year_sel(years, "es_a")
        with fg:
            real_m = available_months(prepared, year_a)
            gran_opts = ["Année complète"] + [MOIS_NOMS[m - 1] for m in real_m]
            _prune_select("es_a_gran", gran_opts)
            gran = st.selectbox("Durée / Granularité", gran_opts, key="es_a_gran")
        month_a = None if gran == "Année complète" else real_m[gran_opts.index(gran) - 1]
        fig1 = fig_evolution(prepared, year_a, month_a)
        _chart(fig1, "Aucune escale pour cette période.")
        st.caption("Année complète = par mois · mois choisi = jour par jour · "
                   "trait plein : N, pointillés : N-1.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Répartition par marchandise</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_b = _year_sel(years, "es_b")
        with fmc:
            months_b = _months_multi(prepared, year_b, "es_b")
        m_opts = available_categories(prepared, year_b, months_b, "marchandise_norm")
        if m_opts:
            _prune("es_b_march", m_opts)
            marches = st.multiselect("Marchandise(s) 🔍", m_opts, key="es_b_march",
                                     default=m_opts, placeholder="Toutes",
                                     label_visibility="collapsed")
            fig2 = fig_marchandise(prepared, year_b, months_b, marches) if marches else None
            _chart(fig2, "Sélectionnez au moins une marchandise.")
        else:
            st.info("Aucune marchandise renseignée sur cette période.")

# ==================================================================
# ROW 2 : ③ Type de navire | ④ Opérateur
# ==================================================================
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Escales par type de navire</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_c = _year_sel(years, "es_c")
        with fmc:
            months_c = _months_multi(prepared, year_c, "es_c")
        t_opts = available_categories(prepared, year_c, months_c, "type_navire_norm")
        if t_opts:
            _prune("es_c_types", t_opts)
            t_picked = st.multiselect("Type(s) de navire 🔍", t_opts, key="es_c_types",
                                      default=t_opts, placeholder="Tous",
                                      label_visibility="collapsed")
            fig3, _ = fig_category(prepared, year_c, months_c, "type_navire_norm",
                                   f"Escales par type — {year_c}", cats=t_picked)
            _chart(fig3, "Aucun type de navire pour cette sélection.")
        else:
            st.info("Aucun type de navire renseigné sur cette période.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>④ Escales par opérateur</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_d = _year_sel(years, "es_d")
        with fmc:
            months_d = _months_multi(prepared, year_d, "es_d")
        o_opts = available_categories(prepared, year_d, months_d, "operateur_norm")
        if o_opts:
            _prune("es_d_ops", o_opts)
            o_picked = st.multiselect("Opérateur(s) 🔍", o_opts, key="es_d_ops",
                                      default=o_opts, placeholder="Tous",
                                      label_visibility="collapsed")
            fig4, _ = fig_category(prepared, year_d, months_d, "operateur_norm",
                                   f"Escales par opérateur — {year_d}", cats=o_picked)
            _chart(fig4, "Aucun opérateur pour cette sélection.")
        else:
            st.info("Aucun opérateur renseigné sur cette période.")

st.markdown(
    '<div class="an-methodo">Méthodologie — Escales : COUNT DISTINCT n° d\'escale · '
    "N vs N-1 comparé sur exactement la même période réelle · "
    "« Autre » représente une seule catégorie · "
    "Valeurs non renseignées groupées sous « (non spécifié) ».</div>",
    unsafe_allow_html=True)