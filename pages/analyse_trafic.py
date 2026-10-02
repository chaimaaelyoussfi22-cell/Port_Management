# -*- coding: utf-8 -*-
"""PAGE /analyse_trafic — Volume Trafic : COMPOSITION / RÉPARTITION.

Layout compact : chaque graphique dans sa propre card avec filtres intégrés.
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import _choices, MONTHS_FR
from components.dashboard.trafic_views import (
    OP_COLORS, OP_ORDER, _fmt_tons, available_years, daily_volume,
    fig_donut, fig_grouped_type, kpi_block, period_label,
    present_types, scope, top_cats, volume_by_category_type,
    composition_insights)


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
        if k.startswith("vt_"):
            del st.session_state[k]


def _keep_valid(key: str, opts: list):
    v = st.session_state.get(key)
    if isinstance(v, list):
        kept = [x for x in v if x in opts]
        if kept != v:
            st.session_state[key] = kept


def _kpi(label: str, value: str, accent: str = "", sub: str = ""):
    style = f' style="border-left:4px solid {accent}"' if accent else ""
    st.markdown(f'<div class="an-kpi"{style}><small>{label}</small>'
                f'<strong>{value}</strong>'
                f'<em class="var-chip neutral">{sub}</em></div>',
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

st.markdown('<div class="an-title"><h1>VOLUME TRAFIC</h1>'
            '<p>Port Analytics Studio · composition · répartition</p></div>',
            unsafe_allow_html=True)

with st.container(border=True):
    fh, fy, fty, fm, fr = st.columns([1.15, 0.85, 1.2, 1.0, 0.8],
                                     vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="vt_year",
                            label_visibility="collapsed")
    with fty:
        pick_types = st.multiselect("Type(s) d'opération", OP_ORDER, key="vt_types",
                                    placeholder="Tous les types",
                                    label_visibility="collapsed")
    with fm:
        pick_months_list = st.multiselect("Mois", list(MONTHS_FR), key="vt_months",
                                          placeholder="Toute l'année",
                                          label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

    months = sorted(MONTHS_FR.index(m) + 1 for m in pick_months_list)

    days: list[int] = []
    if len(months) == 1:
        ndays_scope = max(daily_volume(prepared, y, months[0], OP_ORDER, [])[1]
                          for y in (year, year - 1))
        _keep_valid("vt_days", list(range(1, ndays_scope + 1)))
        pick_days = st.multiselect(
            f"Jour(s) de {MONTHS_FR[months[0] - 1]}", range(1, ndays_scope + 1),
            key="vt_days", format_func=lambda d: f"{d:02d}",
            placeholder="Tous les jours")
        days = sorted(pick_days)

types_present = present_types(prepared, year, months)
_keep_valid("vt_types", OP_ORDER)
types = pick_types if pick_types else types_present
periode = period_label(year, months, days)

# ==================================================================
# KPI BAND
# ==================================================================
kpi = kpi_block(prepared, year, months, days, types)
total = kpi["total"]
pct_imp = round(100 * kpi["Import"] / total, 1) if total else 0
pct_exp = round(100 * kpi["Export"] / total, 1) if total else 0
pct_cab = round(100 * kpi["Cabotage"] / total, 1) if total else 0

kc1, kc2, kc3, kc4, kc5 = st.columns(5)
with kc1:
    _kpi("Volume total", _fmt_tons(total), sub="tonnes")
with kc2:
    _kpi("🔴 Import", _fmt_tons(kpi["Import"]), OP_COLORS["Import"], f"{pct_imp} %")
with kc3:
    _kpi("🟠 Export", _fmt_tons(kpi["Export"]), OP_COLORS["Export"], f"{pct_exp} %")
with kc4:
    _kpi("🔵 Cabotage", _fmt_tons(kpi["Cabotage"]), OP_COLORS["Cabotage"], f"{pct_cab} %")
with kc5:
    top_type = max([("Import", kpi["Import"]), ("Export", kpi["Export"]),
                     ("Cabotage", kpi["Cabotage"])], key=lambda x: x[1])
    _kpi("Opération dominante", top_type[0],
         OP_COLORS.get(top_type[0], ""), f"{round(100*top_type[1]/total,1) if total else 0} %")

chips = [_chip(f"Période : <b>{periode}</b>"),
         _chip(f"Opérations : <b>{' / '.join(types) if types else '—'}</b>")]
st.markdown('<div class="an-chips">' + "".join(chips) + "</div>",
            unsafe_allow_html=True)

# ==================================================================
# CARDS
# ==================================================================
gframe = scope(prepared, year, months, days)

# --- ROW : ① Marchandise | ② Opérateur ---
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>① Volume par marchandise</h4></div>',
                    unsafe_allow_html=True)
        gframe_ma = gframe.assign(
            marchandise_norm=gframe["marchandise_norm"].fillna("").astype(str).str.strip())
        m_opts = [m for m in _choices(gframe_ma, "marchandise_norm") if m]
        if m_opts:
            _keep_valid("vt_march", m_opts)
            pick_march = st.multiselect("Marchandise(s)", m_opts, key="vt_march",
                                        label_visibility="collapsed")
            piv_m = volume_by_category_type(prepared, year, months, types,
                                            "marchandise_norm", days)
            if pick_march:
                piv_m = piv_m[piv_m["marchandise_norm"].isin(pick_march)]
            fig1 = fig_grouped_type(piv_m, "marchandise_norm", periode)
            if fig1:
                st.plotly_chart(fig1, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Aucun volume pour cette sélection.")
        else:
            st.info("Aucune marchandise renseignée.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Volume par opérateur</h4></div>',
                    unsafe_allow_html=True)
        gframe_op = gframe.assign(
            operateur_norm=gframe["operateur_norm"].fillna("").astype(str).str.strip())
        o_opts = [o for o in _choices(gframe_op, "operateur_norm") if o]
        if o_opts:
            _keep_valid("vt_ops", o_opts)
            pick_ops = st.multiselect("Opérateur(s)", o_opts, key="vt_ops",
                                      label_visibility="collapsed")
            piv_o = volume_by_category_type(prepared, year, months, types,
                                            "operateur_norm", days)
            if pick_ops:
                piv_o = piv_o[piv_o["operateur_norm"].isin(pick_ops)]
            fig2 = fig_grouped_type(piv_o, "operateur_norm", periode)
            if fig2:
                st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Aucun volume pour cette sélection.")
        else:
            st.info("Aucun opérateur renseigné.")

# --- ROW : ③ Donut | ④ Insights ---
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Répartition globale</h4></div>',
                    unsafe_allow_html=True)
        fig3 = fig_donut(prepared, year, months, days, types, periode)
        if fig3:
            st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour le donut.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>④ Analyse intelligente</h4></div>',
                    unsafe_allow_html=True)
        insights = composition_insights(prepared, year, months, days, types)
        for ins in insights:
            st.markdown(f'<div style="padding:4px 0;font-size:.84rem;color:#0B3A5B;'
                        f'border-bottom:1px solid #cfe6f8">{ins}</div>',
                        unsafe_allow_html=True)

st.markdown(
    '<div class="an-methodo">Méthodologie — Volume : SOMME des tonnages · '
    "Donut : répartition par type d'opération · "
    "Valeurs non renseignées groupées sous « (non spécifié) ».</div>",
    unsafe_allow_html=True)
