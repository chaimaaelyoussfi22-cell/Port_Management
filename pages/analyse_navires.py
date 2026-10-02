# -*- coding: utf-8 -*-
"""PAGE /analyse_navires — Analyse des navires (dashboard type Power BI).

Layout Power BI compact : 2×2 cards, AUCUNE zone de filtres globale.
Chaque graphique possède SES PROPRES filtres dans son cadre ; les listes
Type de navire / Opérateur / Marchandise sont construites dynamiquement à
partir des données réellement présentes pour la période sélectionnée.
Méthodologie : COUNT DISTINCT nom du navire · N vs N-1 sur la même période réelle.
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.navires_views import (
    available_years, available_months, available_categories,
    fig_evolution, fig_type_navire, fig_operateur, fig_marchandise,
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

st.markdown('<div class="an-title"><h1>🚢 ANALYSE DES NAVIRES</h1>'
            '<p>Dashboard Power BI · chaque graphique possède ses propres '
            'filtres · périodes réellement présentes dans les données</p></div>',
            unsafe_allow_html=True)

st.markdown('<div class="an-chips">' +
            _chip("Listes <b>Type de navire / Opérateur / Marchandise</b> "
                  "reconstruites selon la période choisie") +
            _chip("N vs N-1 : <b>même période réelle</b>") +
            "</div>", unsafe_allow_html=True)

# ==================================================================
# ROW 1 : ① Évolution N vs N-1 | ② Type de navire
# ==================================================================
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>① Évolution des navires — N vs N-1</h4></div>',
                    unsafe_allow_html=True)
        fy, fg = st.columns(2, gap="large")
        with fy:
            year_a = _year_sel(years, "nv_a")
        with fg:
            real_m = available_months(prepared, year_a)
            gran_opts = ["Année complète"] + [MOIS_NOMS[m - 1] for m in real_m]
            _prune_select("nv_a_gran", gran_opts)
            gran = st.selectbox("Durée / Granularité", gran_opts, key="nv_a_gran")
        month_a = None if gran == "Année complète" else real_m[gran_opts.index(gran) - 1]
        fig1 = fig_evolution(prepared, year_a, month_a)
        _chart(fig1, "Aucun navire pour cette période.")
        st.caption("Année complète = par mois · mois choisi = jour par jour · "
                   "trait plein : N, pointillés : N-1.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Navires par type de navire</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_b = _year_sel(years, "nv_b")
        with fmc:
            months_b = _months_multi(prepared, year_b, "nv_b")
        t_opts = available_categories(prepared, year_b, months_b, "type_navire_norm")
        if t_opts:
            _prune("nv_b_types", t_opts)
            t_picked = st.multiselect("Type(s) de navire 🔍", t_opts, key="nv_b_types",
                                      default=t_opts, placeholder="Tous",
                                      label_visibility="collapsed")
            fig2, _ = fig_type_navire(prepared, year_b, months_b, t_picked)
            _chart(fig2, "Aucun type de navire pour cette sélection.")
        else:
            st.info("Aucun type de navire renseigné sur cette période.")

# ==================================================================
# ROW 2 : ③ Opérateur | ④ Marchandise
# ==================================================================
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Navires par opérateur</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_c = _year_sel(years, "nv_c")
        with fmc:
            months_c = _months_multi(prepared, year_c, "nv_c")
        o_opts = available_categories(prepared, year_c, months_c, "operateur_norm")
        if o_opts:
            _prune("nv_c_ops", o_opts)
            o_picked = st.multiselect("Opérateur(s) 🔍", o_opts, key="nv_c_ops",
                                      default=o_opts, placeholder="Tous",
                                      label_visibility="collapsed")
            fig3, _ = fig_operateur(prepared, year_c, months_c, o_picked)
            _chart(fig3, "Aucun opérateur pour cette sélection.")
        else:
            st.info("Aucun opérateur renseigné sur cette période.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>④ Navires par marchandise</h4></div>',
                    unsafe_allow_html=True)
        fy, fmc = st.columns(2, gap="large")
        with fy:
            year_d = _year_sel(years, "nv_d")
        with fmc:
            months_d = _months_multi(prepared, year_d, "nv_d")
        m_opts = available_categories(prepared, year_d, months_d, "marchandise_norm")
        if m_opts:
            _prune("nv_d_march", m_opts)
            marches = st.multiselect("Marchandise(s) 🔍", m_opts, key="nv_d_march",
                                     default=m_opts, placeholder="Toutes",
                                     label_visibility="collapsed")
            fig4, _ = fig_marchandise(prepared, year_d, months_d, marches) if marches \
                else (None, "")
            _chart(fig4, "Sélectionnez au moins une marchandise.")
        else:
            st.info("Aucune marchandise renseignée sur cette période.")

st.markdown(
    '<div class="an-methodo">Méthodologie — Navires uniques : COUNT DISTINCT nom du '
    "navire · N vs N-1 comparé sur exactement la même période réelle · "
    "« Autre » représente une seule catégorie · "
    "Valeurs non renseignées groupées sous « (non spécifié) ».</div>",
    unsafe_allow_html=True)