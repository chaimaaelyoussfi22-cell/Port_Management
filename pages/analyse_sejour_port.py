# -*- coding: utf-8 -*-
"""PAGE /analyse_sejour_port — Séjour au port : DURÉE GLOBALE.

Dashboard compact type Power BI · chaque graphique dans sa card avec filtres intégrés.
Métrique : port_h (Appareille_Port − Arrivee_Rade).
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.sejour_port_views import (
    available_years, port_by_category, compute)


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
        if k.startswith("sp_"):
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

st.markdown('<div class="an-title"><h1>SÉJOUR AU PORT</h1>'
            '<p>Port Analytics Studio · durée globale · tendances</p></div>',
            unsafe_allow_html=True)

# ==================================================================
# FILTRES GLOBAUX (année + réinitialiser)
# ==================================================================
with st.container(border=True):
    fh, fy, fr = st.columns([1.15, 1.05, 0.8], vertical_alignment="center")
    with fh:
        st.markdown('<div class="an-filter-head"><b>FILTRES GLOBAUX</b></div>',
                    unsafe_allow_html=True)
    with fy:
        year = st.selectbox("Année analysée", years, key="sp_year",
                            help="N-1 comparé automatiquement.",
                            label_visibility="collapsed")
    with fr:
        st.button("↺ Réinitialiser", use_container_width=True,
                  on_click=_reset_filters)

# ==================================================================
# KPI BAND
# ==================================================================
from components.dashboard.sejour_port_views import kpi_block as _kpi_block
ekpi = _kpi_block(prepared, year)
evo = ekpi["evolution"]
evo_txt = "—" if evo is None else f"{evo:+.1f} %".replace(".", ",")

kc1, kc2, kc3, kc4, kc5 = st.columns(5)
with kc1:
    _kpi("Durée moy. port", f"{ekpi['avg']} h", sub=f"{round(ekpi['avg']/24,1)} j")
with kc2:
    _kpi("Durée médiane", f"{ekpi['median']} h", sub=f"{round(ekpi['median']/24,1)} j")
with kc3:
    _kpi("Navires", f"{ekpi['ships']:,}", sub=f"{ekpi['count']} escales")
with kc4:
    _kpi("Séjour max", f"{ekpi['max']} h", sub=f"{round(ekpi['max']/24,1)} j")
with kc5:
    _kpi("Évolution vs N-1", evo_txt, sub=f"{year} vs {year-1}", var=evo)

chips = [_chip(f"Année : <b>{year}</b>"),
         _chip(f"Métrique : <b>Séjour au port (port_h)</b>")]
st.markdown('<div class="an-chips">' + "".join(chips) + "</div>",
            unsafe_allow_html=True)

# ==================================================================
# CARDS
# ==================================================================

# --- ROW 1 : ① Évolution N vs N-1 | ② Marchandise ---
row1_l, row1_r = st.columns(2, gap="large")

with row1_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>① Évolution N vs N-1</h4></div>',
                    unsafe_allow_html=True)
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            evo_gran = st.segmented_control(
                "Granularité", ["Par mois", "Par jour"], key="sp_evo_gran",
                label_visibility="collapsed", default="Par mois")
        with fc2:
            if evo_gran == "Par jour":
                _avail_months_port = sorted(prepared[prepared["year"] == year]["month"].dropna().unique().astype(int).tolist())
                evo_month = st.selectbox(
                    "Mois", _avail_months_port, key="sp_evo_month",
                    format_func=lambda m: MOIS_NOMS[m - 1],
                    label_visibility="collapsed")
            else:
                evo_month = 1
                st.selectbox("Mois", ["—"], disabled=True, key="sp_evo_month_ph",
                             label_visibility="collapsed")
        with fc3:
            if evo_gran == "Par mois":
                evo_months_list = st.multiselect(
                    "Mois (année complète)", list(MOIS_NOMS), key="sp_evo_months",
                    placeholder="Toute l'année", label_visibility="collapsed")
                evo_months = sorted(MOIS_NOMS.index(m) + 1 for m in evo_months_list)
            else:
                evo_months = []
                st.multiselect("Mois", [], key="sp_evo_months",
                               label_visibility="collapsed", disabled=True)
        from components.dashboard.sejour_port_views import (
            port_monthly, port_daily)
        from components.dashboard.analytics import MONTHS_FR
        from components.dashboard.escales_views import CUR_COLOR, PREV_COLOR, _apply_theme
        import plotly.graph_objects as go

        fig_evo = go.Figure()
        _evo_state = {"has_data": False}

        def _add_trace(yr, nm, col, dash):
            if evo_gran == "Par jour":
                s = port_daily(prepared, yr, evo_month)
                if s.empty:
                    return
                fig_evo.add_trace(go.Scatter(
                    x=s["mmdd"], y=s["sejour"], name=nm,
                    mode="lines+markers" if len(s) < 200 else "lines",
                    line=dict(color=col, width=3 if dash is None else 2,
                              dash=dash or "solid"),
                    customdata=s["label"].tolist(),
                    hovertemplate="%{customdata}<br>%{y:.1f} h<extra>" + nm + "</extra>"))
                _evo_state["has_data"] = True
            else:
                s = port_monthly(prepared, yr)
                if s.sum() == 0:
                    return
                fig_evo.add_trace(go.Scatter(
                    x=[MONTHS_FR[m - 1] for m in s.index], y=s.values, name=nm,
                    mode="lines+markers",
                    line=dict(color=col, width=3 if dash is None else 2,
                              dash=dash or "solid"),
                    hovertemplate="%{x}<br>%{y:.1f} h<extra>" + nm + "</extra>"))
                _evo_state["has_data"] = True

        _add_trace(year, f"N ({year})", CUR_COLOR, None)
        _add_trace(year - 1, f"N-1 ({year - 1})", PREV_COLOR, "dot")

        if _evo_state["has_data"]:
            suffix = (f" — {MOIS_NOMS[evo_month - 1]} {year}"
                      if evo_gran == "Par jour" else "")
            fig_evo.update_layout(
                height=380, yaxis_title="Durée moyenne de séjour (h)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                hovermode="x unified" if evo_gran == "Par mois" else "closest",
                yaxis_rangemode="nonnegative")
            fig_evo = _apply_theme(fig_evo)
            st.plotly_chart(fig_evo, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour cette période.")

with row1_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>② Séjour moyen par marchandise</h4></div>',
                    unsafe_allow_html=True)
        fm1, fm2 = st.columns(2)
        with fm1:
            march_months_list = st.multiselect(
                "Mois", list(MOIS_NOMS), key="sp_march_months",
                placeholder="Toute l'année", label_visibility="collapsed")
            march_months = sorted(MOIS_NOMS.index(m) + 1 for m in march_months_list)
        with fm2:
            _all_march = port_by_category(prepared, year, march_months,
                                          "marchandise_norm")
            march_opts = (_all_march["marchandise_norm"].tolist()
                          if not _all_march.empty else [])
            _keep_valid("sp_march_filter", march_opts)
            march_filter = st.multiselect(
                "Marchandise(s)", march_opts, key="sp_march_filter",
                placeholder="Toutes", label_visibility="collapsed")
        data_m = port_by_category(prepared, year, march_months, "marchandise_norm")
        if march_filter and not data_m.empty:
            data_m = data_m[data_m["marchandise_norm"].isin(march_filter)]
        title_m = "Séjour moyen par marchandise"
        if march_months_list:
            title_m += " · " + ", ".join(march_months_list)
        if not data_m.empty:
            total = max(int(data_m["escales"].sum()), 1)
            g = data_m.head(15).iloc[::-1]
            import numpy as np
            fig_m = go.Figure(go.Bar(
                x=g["sejour_moyen"], y=g["marchandise_norm"].astype(str),
                orientation="h",
                marker_color="#62ddff", marker_line_width=0,
                customdata=np.stack([
                    g["escales"].astype(int).values,
                    (g["escales"] / total * 100).round(1).values,
                    g.get("navires", __import__("pandas").Series([0]*len(g))).astype(int).values,
                ], axis=-1),
                hovertemplate="%{y}<br>Séjour : %{x:.1f} h"
                              + "<br>Escales : %{customdata[0]} (%{customdata[1]} %)"
                              + "<br>Navires : %{customdata[2]}"
                              + "<extra></extra>"))
            fig_m.update_layout(
                height=max(300, 34 * len(g) + 90),
                xaxis_title="Séjour moyen (h)")
            fig_m = _apply_theme(fig_m)
            st.plotly_chart(fig_m, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune marchandise renseignée.")

# --- ROW 2 : ③ Opérateur | ⑤ Distribution ---
row2_l, row2_r = st.columns(2, gap="large")

with row2_l:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>③ Séjour moyen par opérateur</h4></div>',
                    unsafe_allow_html=True)
        fo1, fo2 = st.columns(2)
        with fo1:
            op_months_list = st.multiselect(
                "Mois", list(MOIS_NOMS), key="sp_op_months",
                placeholder="Toute l'année", label_visibility="collapsed")
            op_months = sorted(MOIS_NOMS.index(m) + 1 for m in op_months_list)
        with fo2:
            _all_op = port_by_category(prepared, year, op_months, "operateur_norm")
            op_opts = (_all_op["operateur_norm"].tolist()
                       if not _all_op.empty else [])
            _keep_valid("sp_op_filter", op_opts)
            op_filter = st.multiselect(
                "Opérateur(s)", op_opts, key="sp_op_filter",
                placeholder="Tous", label_visibility="collapsed")
        data_o = port_by_category(prepared, year, op_months, "operateur_norm")
        if op_filter and not data_o.empty:
            data_o = data_o[data_o["operateur_norm"].isin(op_filter)]
        title_o = "Séjour moyen par opérateur"
        if op_months_list:
            title_o += " · " + ", ".join(op_months_list)
        if not data_o.empty:
            total = max(int(data_o["escales"].sum()), 1)
            g = data_o.head(15).iloc[::-1]
            import numpy as np
            fig_o = go.Figure(go.Bar(
                x=g["sejour_moyen"], y=g["operateur_norm"].astype(str),
                orientation="h",
                marker_color="#62ddff", marker_line_width=0,
                customdata=np.stack([
                    g["escales"].astype(int).values,
                    (g["escales"] / total * 100).round(1).values,
                    g.get("navires", __import__("pandas").Series([0]*len(g))).astype(int).values,
                ], axis=-1),
                hovertemplate="%{y}<br>Séjour : %{x:.1f} h"
                              + "<br>Escales : %{customdata[0]} (%{customdata[1]} %)"
                              + "<br>Navires : %{customdata[2]}"
                              + "<extra></extra>"))
            fig_o.update_layout(
                height=max(300, 34 * len(g) + 90),
                xaxis_title="Séjour moyen (h)")
            fig_o = _apply_theme(fig_o)
            st.plotly_chart(fig_o, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucun opérateur renseigné.")

with row2_r:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⑤ Distribution des durées de séjour</h4></div>',
                    unsafe_allow_html=True)
        fd1, fd2, _ = st.columns([1, 1, 2])
        with fd1:
            dist_months_list = st.multiselect(
                "Mois", list(MOIS_NOMS), key="sp_dist_months",
                placeholder="Toute l'année", label_visibility="collapsed")
            dist_months = sorted(MOIS_NOMS.index(m) + 1 for m in dist_months_list)
        with fd2:
            st.selectbox("Année", [year], disabled=True, key="sp_dist_year_ph",
                         label_visibility="collapsed")
        from components.dashboard.sejour_port_views import _fig_distribution
        fig_dist, title_dist = _fig_distribution(prepared, year, dist_months)
        if fig_dist is not None:
            st.plotly_chart(fig_dist, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Aucune donnée pour la distribution.")

# ==================================================================
# INSIGHTS
# ==================================================================
from components.dashboard.sejour_port_views import port_insights
insights = port_insights(prepared, year, dist_months)
if insights:
    with st.container(border=True):
        st.markdown('<div class="an-card-head"><h4>⑥ Analyse intelligente</h4></div>',
                    unsafe_allow_html=True)
        for ins in insights:
            st.markdown(
                f'<div style="padding:4px 0;font-size:.84rem;color:#0B3A5B;'
                f'border-bottom:1px solid #cfe6f8">{ins}</div>',
                unsafe_allow_html=True)

st.markdown(
    '<div class="an-methodo">Méthodologie — Séjour au port : durée totale '
    '(Appareille_Port − Arrivee_Rade) · '
    "Histogramme : intervalles en jours · "
    "Valeurs non renseignées groupées sous « (non spécifié) ».</div>",
    unsafe_allow_html=True)
