# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse de l'Évolution » (dashboard Power BI).

Focus : TENDANCES / VARIATION / COMPARAISON N vs N-1.
Ce module étend trafic_views (moteur partagé) avec des fonctions
spécifiques à l'analyse temporelle des flux portuaires.

Aucune dépendance Streamlit — données + figures Plotly pures, testables.
"""

import calendar

import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, _apply_theme)
from components.dashboard.trafic_views import (
    OP_ORDER, OP_COLORS, EXTRA_COLOR, _bt, _cat, scope,
    monthly_volume, daily_volume, _fmt_tons, period_prev, period_label)


# ==================================================================
# KPI — PAGE ÉVOLUTION
# ==================================================================
def evolution_kpi_block(frame: pd.DataFrame, year: int,
                        months: list[int] = (), days: list[int] = (),
                        types: list[str] | None = None) -> dict:
    """KPI spécifiques à la page Évolution : evo, meilleur/pire mois, max var."""
    effective_types = types or OP_ORDER
    cur = scope(frame, year, months, days)
    prev = scope(frame, year - 1, months, days)
    if effective_types:
        cur = cur[_cat(cur, "type_trafic").isin(effective_types)] if not cur.empty else cur
        prev = prev[_cat(prev, "type_trafic").isin(effective_types)] if not prev.empty else prev
    cur_total = float(cur["tonnage"].sum()) if not cur.empty else 0.0
    prev_total = float(prev["tonnage"].sum()) if not prev.empty else 0.0
    evo = (round(100 * (cur_total - prev_total) / prev_total, 1)
           if prev_total else None)
    cur_m = cur.groupby("month")["tonnage"].sum() if not cur.empty else pd.Series(dtype=float)
    prev_m = prev.groupby("month")["tonnage"].sum() if not prev.empty else pd.Series(dtype=float)
    best_month = best_var = worst_month = worst_var = max_var_m = max_var = None
    if not cur_m.empty:
        best_month = int(cur_m.idxmax())
        worst_month = int(cur_m.idxmin())
    monthly_vars: dict[int, float] = {}
    for m in range(1, 13):
        c = float(cur_m.get(m, 0))
        p = float(prev_m.get(m, 0))
        if p > 0:
            monthly_vars[m] = round(100 * (c - p) / p, 1)
    if monthly_vars:
        max_var_m = max(monthly_vars, key=lambda m: abs(monthly_vars[m]))
        max_var = monthly_vars[max_var_m]
    return {
        "cur_total": cur_total, "prev_total": prev_total,
        "evolution": evo,
        "best_month": best_month, "best_volume": float(cur_m.get(best_month, 0)) if best_month else 0.0,
        "worst_month": worst_month, "worst_volume": float(cur_m.get(worst_month, 0)) if worst_month else 0.0,
        "max_var_month": max_var_m, "max_var_pct": max_var,
    }


# ==================================================================
# FIGURES — ÉVOLUTION PAR TYPE D'OPÉRATION
# ==================================================================
def fig_evo_by_type(frame: pd.DataFrame, year: int, gran: str = "Année complète",
                    month: int = 1, types: list[str] | None = None) -> go.Figure | None:
    """Courbes N vs N-1 ventilées par type d'opération (Cabotage/Import/Export)."""
    effective_types = types or OP_ORDER
    fig = go.Figure()
    for t in effective_types:
        color = OP_COLORS.get(t, EXTRA_COLOR)
        # Année N
        if gran == "Par jour":
            s, _ = daily_volume(frame, year, month, [t], [])
            xs = [f"{d:02d}/{month:02d}" for d in s.index]
        else:
            s = monthly_volume(frame, year, [t], [])
            xs = [MONTHS_FR[m - 1] for m in s.index]
        if sum(s) > 0:
            fig.add_trace(go.Scatter(
                x=xs, y=s.values.tolist(), name=f"{t} · {year}",
                mode="lines+markers", line=dict(color=color, width=2.6),
                customdata=[_fmt_tons(v) for v in s.values.tolist()],
                hovertemplate="%{x}<br>%{customdata}<extra>" + t + f" · {year}</extra>"))
        # Année N-1
        if gran == "Par jour":
            sp, _ = daily_volume(frame, year - 1, month, [t], [])
            xsp = [f"{d:02d}/{month:02d}" for d in sp.index]
        else:
            sp = monthly_volume(frame, year - 1, [t], [])
            xsp = [MONTHS_FR[m - 1] for m in sp.index]
        if sum(sp) > 0:
            fig.add_trace(go.Scatter(
                x=xsp, y=sp.values.tolist(), name=f"{t} · {year - 1}",
                mode="lines+markers",
                line=dict(color=color, width=1.8, dash="dot"),
                customdata=[_fmt_tons(v) for v in sp.values.tolist()],
                hovertemplate="%{x}<br>%{customdata}<extra>" + t + f" · {year - 1}</extra>"))
    if not fig.data:
        return None
    fig.update_layout(
        height=420, yaxis_title="Volume (tonnes)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if gran != "Par jour" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


# ==================================================================
# FIGURES — ÉVOLUTION PAR CATÉGORIE (opérateur / marchandise)
# ==================================================================
def fig_evo_by_category(frame: pd.DataFrame, year: int, cats: list[str],
                        cat_col: str, gran: str = "Année complète",
                        month: int = 1,
                        types: list[str] | None = None) -> go.Figure | None:
    """Courbes N vs N-1 pour une catégorie donnée (opérateur ou marchandise).

    Une ligne par catégorie sélectionnée, N solide / N-1 pointillé.
    """
    if not cats:
        return None
    effective_types = types or OP_ORDER
    fig = go.Figure()

    def _xy_for(yr: int, cat: str):
        f = _bt(frame)
        f = f[f["year"] == yr]
        f = f[_cat(f, "type_trafic").isin(effective_types)]
        f = f[_cat(f, cat_col) == cat]
        if gran == "Par jour":
            if f.empty or "date" not in f.columns:
                return [], []
            day = pd.to_datetime(f["date"], errors="coerce").dt.day
            g = f.assign(day=day).dropna(subset=["day"]).groupby("day")["tonnage"].sum()
            vals = [round(float(g.get(d, 0.0)), 1) for d in g.index]
            return [f"{int(d):02d}/{month:02d}" for d in g.index], vals
        else:
            months_agg = f.groupby("month")["tonnage"].sum()
            if months_agg.empty:
                return [], []
            vals = [round(float(v), 1) for v in months_agg.values]
            return [MONTHS_FR[int(m) - 1] for m in months_agg.index], vals

    for i, cat in enumerate(cats):
        c = COLOR_SEQ[i % len(COLOR_SEQ)]
        xs, ys = _xy_for(year, cat)
        if sum(ys) > 0:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=f"{cat} · {year}",
                mode="lines+markers", line=dict(color=c, width=2.6),
                customdata=[_fmt_tons(v) for v in ys],
                hovertemplate="%{x}<br>%{customdata}<extra>" + cat + f" · {year}</extra>"))
        xp, yp = _xy_for(year - 1, cat)
        if sum(yp) > 0:
            fig.add_trace(go.Scatter(
                x=xp, y=yp, name=f"{cat} · {year - 1}",
                mode="lines+markers",
                line=dict(color=c, width=1.8, dash="dot"),
                customdata=[_fmt_tons(v) for v in yp],
                hovertemplate="%{x}<br>%{customdata}<extra>" + cat + f" · {year - 1}</extra>"))
    if not fig.data:
        return None
    fig.update_layout(
        height=420, yaxis_title="Volume (tonnes)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if gran != "Par jour" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


# ==================================================================
# HELPERS DYNAMIQUES
# ==================================================================
def available_cats(frame: pd.DataFrame, year: int, col: str,
                   months: list[int] = (), days: list[int] = (),
                   types: list[str] | None = None) -> list[str]:
    """Catégories (opérateurs / marchandises) disponibles sur la période."""
    effective_types = types or OP_ORDER
    f = scope(frame, year, months, days)
    if f.empty:
        return []
    f = f[_cat(f, "type_trafic").isin(effective_types)]
    vals = sorted(set(_cat(f, col)) - {"(non spécifié)"})
    return vals
