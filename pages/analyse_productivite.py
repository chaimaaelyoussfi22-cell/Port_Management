# -*- coding: utf-8 -*-
"""PAGE /analyse_productivite — Productivité du port.

Métrique port : productivité = Σ Tonnage ÷ Σ Durée de séjour au port (t/h).
Métrique poste : productivité du poste = Σ Tonnage affecté ÷ Σ Durée du poste
(règle de répartition : tonnage_attribué = tonnage_total / nombre de postes).
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.productivite_views import (
    POSTE_REFERENTIEL, _poste_label,
    available_years, kpi_block,
    _fig_port_monthly, _fig_evolution, _fig_poste, _fig_poste_evolution)

POSTE_OPTIONS = [_poste_label(k) for k in POSTE_REFERENTIEL]


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


def _reset_filters():
    for k in list(st.session_state):
        if k.startswith("pr_"):
            del st.session_state[k]


def _keep_valid(key: str, opts: list):
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept


def _kpi(label: str, value: str, accent: str = "", sub: str = "",
         var: float | None = None):
    cls = "neutral" if var is None else ("good" if var >= 0 else "bad")
    arrow = "" if var is None else ("▲" if var >= 0 else "▼")
    style = f' style="border-left:4px solid {accent}"' if accent else ""
    st.markdown(f'<div class="an-kpi"{style}><small>{label}</small>'
                f'<strong>{value}</strong>'
                f'<em class="var-chip {cls}">{arrow} {sub}</em></div>',
                unsafe_allow_html=True)


def _fmt_tons(v: float) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f} M T"
    if v >= 1_000:
        return f"{v/1_000:.0f} k T"
    return f"{v:.0f} T"


def _fmt_hours(v: float) -> str:
    if v >= 10_000:
        return f"{v/1_000:.1f} k h"
    return f"{v:,.0f} h"


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
    st.warning("Aucune escale datable dans la base.")
    st.stop()

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>PRODUCTIVITÉ</h1></div>',
            unsafe_allow_html=True)

# ==================================================================
# FILTRES GLOBAUX (année + marchandise + réinitialiser)
# ==================================================================
_MARCH_OPTIONS = ["Toutes les marchandises", *sorted(
    {str(v).strip() for v in prepared["marchandise_norm"].dropna()
     if str(v).strip()})]
with st.container(border=True):
    fh, fy, fm, fr = st.columns([1.15, 1.0, 1.5, 0.8], vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="pr_year",
                            help="N-1 comparé automatiquement.",
                            label_visibility="collapsed")
    with fm:
        _march = st.selectbox(
            "Marchandise", _MARCH_OPTIONS, key="pr_marchandise",
            help="Filtre global appliqué à toutes les cartes de la page.",
            label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

if _march == "Toutes les marchandises":
    prepared_f = prepared
else:
    prepared_f = prepared[
        prepared["marchandise_norm"].astype(str).str.strip() == _march]

# ==================================================================
# KPI BAND
# ==================================================================
ekpi = kpi_block(prepared_f, year)
evo = ekpi["evolution"]
evo_txt = "—" if evo is None else f"{evo:+.1f} %".replace(".", ",")

kc1, kc2, kc3, kc4 = st.columns(4)
with kc1:
    _kpi("Prod. du port", f"{ekpi['port_prod']:.1f} t/h",
         sub="Σ tonnage ÷ Σ durée séjour port")
with kc2:
    _kpi("Évolution vs N-1", evo_txt, sub=f"{year} vs {year-1}", var=evo)
with kc3:
    _kpi("Volume total", _fmt_tons(ekpi["volume"]),
         sub=f"{ekpi['count']} opérations · {ekpi['ships']} navires")
with kc4:
    _kpi("Durée séjour port", _fmt_hours(ekpi["duree_port"]),
         sub=f"{ekpi['escales']} escales")

# ==================================================================
# SECTION 1 — PRODUCTIVITÉ GLOBALE DU PORT
# ==================================================================
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>Productivité globale du port</h4></div>',
                unsafe_allow_html=True)
    s1_l, s1_r = st.columns(2, gap="large")

    with s1_l:
        st.markdown('<div class="an-card-head"><h4>Productivité mensuelle</h4></div>',
                    unsafe_allow_html=True)
        fig_port, _ = _fig_port_monthly(prepared_f, year)
        if fig_port is not None:
            st.plotly_chart(fig_port, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour la période.")

    with s1_r:
        st.markdown('<div class="an-card-head"><h4>Évolution de la productivité — N vs N-1</h4></div>',
                    unsafe_allow_html=True)
        fig_evo = _fig_evolution(prepared_f, year, "Par mois", 1)
        if fig_evo is not None:
            st.plotly_chart(fig_evo, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour cette période.")

# ==================================================================
# SECTION 2 — PRODUCTIVITÉ PAR POSTE (filtre lié aux 2 graphiques)
# ==================================================================
_keep_valid("pr_poste_filter", POSTE_OPTIONS)
poste_filter = st.multiselect(
    "Poste(s)", POSTE_OPTIONS, key="pr_poste_filter",
    placeholder="Tous les postes",
    help="Met à jour la productivité par poste et son évolution ci-dessous "
         "(vide = tous les postes).")

colL, colR = st.columns(2, gap="large")

with colL:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>Productivité par poste</h4></div>',
                    unsafe_allow_html=True)
        pm1, pm2 = st.columns([1.4, 1])
        with pm1:
            _pm_list = st.multiselect(
                "Mois", list(MOIS_NOMS), key="pr_poste_months",
                placeholder="Toute l'année", label_visibility="collapsed")
        poste_months = sorted(MOIS_NOMS.index(m) + 1 for m in _pm_list)
        fig_poste, _ = _fig_poste(prepared_f, year, poste_months, poste_filter)
        if fig_poste is not None:
            st.plotly_chart(fig_poste, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée de productivité par poste.")

with colR:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>Évolution de la productivité par poste</h4></div>',
                    unsafe_allow_html=True)
        fig_poste_evo, _ = _fig_poste_evolution(prepared_f, year, poste_filter)
        if fig_poste_evo is not None:
            st.plotly_chart(fig_poste_evo, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour la période.")