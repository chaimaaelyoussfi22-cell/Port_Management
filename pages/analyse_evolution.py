# -*- coding: utf-8 -*-
"""PAGE /analyse_evolution — Évolution du trafic : TENDANCES N vs N-1.

Layout compact : chaque graphique dans sa propre card avec filtres intégrés.
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import _choices, MONTHS_FR
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.trafic_views import (
    OP_ORDER, _cat, _fmt_tons, available_years, daily_volume, fig_evolution,
    kpi_block, monthly_volume, period_label, present_types, scope,
    top_cats, evolution_insights)
from components.dashboard.evolution_views import (
    evolution_kpi_block, fig_evo_by_type, fig_evo_by_category,
    available_cats)


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
        if k.startswith("ev_"):
            del st.session_state[k]


def _keep_valid(key: str, opts: list):
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept or opts


def _vol_top(frame, year: int, months: list, days: list, types: list | None,
             col: str, n: int) -> list:
    """Top n catégories par volume sur la période (pour la présélection)."""
    f = scope(frame, year, months, days)
    if f.empty:
        return []
    eff = types or OP_ORDER
    f = f[_cat(f, "type_trafic").isin(eff)]
    if f.empty:
        return []
    return (f.groupby(_cat(f, col))["tonnage"].sum()
            .sort_values(ascending=False).head(n).index.astype(str).tolist())


def _kpi(label: str, value: str, accent: str = "", sub: str = "",
         var: float | None = None):
    cls = "neutral" if var is None else ("good" if var >= 0 else "bad")
    arrow = "" if var is None else ("▲" if var >= 0 else "▼")
    style = f' style="border-left:4px solid {accent}"' if accent else ""
    st.markdown(f'<div class="an-kpi"{style}><small>{label}</small>'
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
    st.warning("Aucune escale datable dans la base.")
    st.stop()

# ==================================================================
# EN-TÊTE + FILTRES GLOBAUX
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

st.markdown('<div class="an-title"><h1>ÉVOLUTION DU TRAFIC</h1>'
            '<p>Port Analytics Studio · tendances · comparaison N vs N-1</p></div>',
            unsafe_allow_html=True)

with st.container(border=True):
    fh, fy, fm, fg, fty, fr = st.columns([1.1, 0.8, 0.95, 1.25, 1.15, 0.75],
                                         vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="ev_year",
                            help="N-1 comparé automatiquement.",
                            label_visibility="collapsed")
    with fm:
        pick_months = st.multiselect("Mois", list(MONTHS_FR), key="ev_months",
                                     placeholder="Toute l'année",
                                     label_visibility="collapsed")
    with fg:
        gran = st.segmented_control("Granularité",
                                    ["Année complète", "Mois sélectionné"],
                                    key="ev_gran", default="Année complète",
                                    label_visibility="collapsed")
    with fty:
        pick_types = st.multiselect("Type(s) d'opération", OP_ORDER, key="ev_types",
                                    placeholder="Tous les types",
                                    label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

    months = sorted(MONTHS_FR.index(m) + 1 for m in pick_months)
    gran = gran or "Année complète"
    gran_month = months[0] if len(months) == 1 else None
    if gran == "Mois sélectionné" and not gran_month:
        gran_month = st.selectbox(
            "Mois précis", list(range(1, 13)),
            key="ev_gmonth", format_func=lambda m: MOIS_NOMS[m - 1])

    days: list[int] = []
    if len(months) == 1:
        ndays_scope = max(daily_volume(prepared, y, months[0], OP_ORDER, [])[1]
                          for y in (year, year - 1))
        _keep_valid("ev_days", list(range(1, ndays_scope + 1)))
        pick_days = st.multiselect(
            f"Jour(s) de {MOIS_NOMS[months[0] - 1]}", range(1, ndays_scope + 1),
            key="ev_days", format_func=lambda d: f"{d:02d}",
            placeholder="Tous les jours")
        days = sorted(pick_days)

types_present = present_types(prepared, year, months)
_keep_valid("ev_types", OP_ORDER)
types = pick_types if pick_types else types_present
periode = period_label(year, months, days)

# ==================================================================
# KPI BAND
# ==================================================================
ekpi = evolution_kpi_block(prepared, year, months, days, types)
evo = ekpi["evolution"]
evo_txt = "—" if evo is None else f"{evo:+.1f} %".replace(".", ",")
best_txt = MOIS_NOMS[ekpi["best_month"] - 1] if ekpi["best_month"] else "—"
worst_txt = MOIS_NOMS[ekpi["worst_month"] - 1] if ekpi["worst_month"] else "—"

kc1, kc2, kc3, kc4 = st.columns(4)
with kc1:
    _kpi("Évolution vs N-1", evo_txt, sub=f"{year} vs {year-1}", var=evo)
with kc2:
    _kpi("Meilleur mois", best_txt,
         sub=f"{_fmt_tons(ekpi['best_volume'])}" if ekpi["best_volume"] else "")
with kc3:
    _kpi("Pire mois", worst_txt,
         sub=f"{_fmt_tons(ekpi['worst_volume'])}" if ekpi["worst_volume"] else "")
with kc4:
    mx = ekpi['max_var_pct']
    mx_m = MOIS_NOMS[ekpi['max_var_month'] - 1] if ekpi['max_var_month'] else "—"
    _kpi("Max variation", f"{mx_m} : {f'{mx:+.1f} %'.replace('.',',') if mx else '—'}",
         sub="vs même mois N-1")

chips = [_chip(f"Période : <b>{periode}</b>"),
         _chip(f"{year} vs {year - 1}"),
         _chip(f"Granularité : <b>{gran}</b>")]
st.markdown('<div class="an-chips">' + "".join(chips) + "</div>",
            unsafe_allow_html=True)

# ==================================================================
# CARDS
# ==================================================================

# --- ROW : ① Évolution globale | ② Par type ---
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>① Évolution globale</h4></div>',
                    unsafe_allow_html=True)
        fig1 = fig_evolution(prepared, year, gran, gran_month or 1, types, None)
        if fig1:
            st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour cette période.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Par type d\'opération</h4></div>',
                    unsafe_allow_html=True)
        fig2 = fig_evo_by_type(prepared, year, gran, gran_month or 1, types)
        if fig2:
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour cette ventilation.")

# --- ROW : ③ Opérateur | ④ Marchandise ---
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Par opérateur</h4></div>',
                    unsafe_allow_html=True)
        o_opts = available_cats(prepared, year, "operateur_norm", months, days, types)
        if o_opts:
            _keep_valid("ev_ops", o_opts)
            pick_ops = st.multiselect("Opérateur(s)", o_opts, key="ev_ops",
                                      default=o_opts,
                                      label_visibility="collapsed")
            fig3 = fig_evo_by_category(prepared, year, pick_ops, "operateur_norm",
                                        gran, gran_month or 1, types)
            if fig3:
                st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Aucune donnée.")
        else:
            st.info("Aucun opérateur renseigné.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>④ Par marchandise</h4></div>',
                    unsafe_allow_html=True)
        m_opts = available_cats(prepared, year, "marchandise_norm", months, days, types)
        if m_opts:
            _keep_valid("ev_march", m_opts)
            m_top = [m for m in _vol_top(prepared, year, months, days, types,
                                         "marchandise_norm", 6) if m in m_opts]
            pick_march = st.multiselect("Marchandise(s)", m_opts, key="ev_march",
                                        default=m_top or m_opts,
                                        label_visibility="collapsed")
            fig4 = fig_evo_by_category(prepared, year, pick_march, "marchandise_norm",
                                        gran, gran_month or 1, types)
            if fig4:
                st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Aucune donnée.")
        else:
            st.info("Aucune marchandise renseignée.")

# --- CARD ⑤ Insights (pleine largeur) ---
with st.container(border=True):
    st.markdown('<div class="an-card-head"><h4>⑤ Analyse intelligente de l\'évolution</h4></div>',
                unsafe_allow_html=True)
    insights = evolution_insights(prepared, year, months, days, types)
    for ins in insights:
        st.markdown(f'<div style="padding:4px 0;font-size:.84rem;color:#0B3A5B;'
                    f'border-bottom:1px solid #cfe6f8">{ins}</div>',
                    unsafe_allow_html=True)

st.markdown(
    '<div class="an-methodo">Méthodologie — Évolution : comparaison N vs N-1 '
    "alignée sur le calendrier · Ligne pleine = année analysée · "
    "pointillés = année précédente · Alertes : variation ≥ 25 % · "
    "Valeurs non renseignées groupées sous « (non spécifié) ».</div>",
    unsafe_allow_html=True)
