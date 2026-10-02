# -*- coding: utf-8 -*-
"""Moteur — Carte « ÉVOLUTION DE LA CONSIGNATION » (dashboard Power BI).

Analyse temporelle des consignations : évolution globale, par poste,
comparaison N vs N-1 sur les périodes réellement comparables, et répartition
par catégorie de durée (Courte / Moyenne / Longue, seuils réels).

Fidélité aux données réelles : axes = périodes réellement présentes dans le
dataset. Aucun mois inventé, aucune période artificiellement complétée.
"""

import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.analysis_views import COLOR_SEQ, _apply_theme
from components.dashboard.consignation_views import (
    DUR_CAT_LONG, DUR_CAT_MEDIUM, DUR_CAT_OPTIONS, DUR_CAT_SHORT,
    DUR_CAT_COLORS, cat_duration)

CUR_COLOR = "#62ddff"      # année N
PREV_COLOR = "#f2b84b"     # année N-1
ALL_POSTES = "Tous les postes"


def poste_options(frame: pd.DataFrame, year: int) -> list[str]:
    """Postes réellement présents pour l'année (valeur « PORT » comprise)."""
    f = frame[frame["year"] == year]
    real = sorted({p for p in f["poste"] if p})
    return [ALL_POSTES] + real


def _select(frame: pd.DataFrame, year: int, dur_cat: str | None,
            boundaries: dict | None) -> pd.DataFrame:
    """Filtre année + catégorie de durée. Retourne une copie catégorisée."""
    f = frame[frame["year"] == year].copy()
    cat_duration(f, boundaries, inplace=True)
    if dur_cat and dur_cat != DUR_CAT_OPTIONS[0]:
        f = f[f["duree_cat"] == dur_cat]
    return f


def _months_xy(f: pd.DataFrame) -> tuple[list[str], pd.Series]:
    s = f.groupby("month").size()
    s = s[s > 0]
    return [MONTHS_FR[int(m) - 1] for m in s.index], s


# ==================================================================
# ① ÉVOLUTION GLOBALE
# ==================================================================
def fig_evo_globale(frame: pd.DataFrame, year: int,
                    dur_cat: str | None, boundaries: dict | None,
                    height: int = 320) -> tuple[go.Figure | None, str]:
    """Courbe du nombre de consignations sur les périodes réellement présentes."""
    title = "Évolution globale"
    f = _select(frame, year, dur_cat, boundaries)
    if f.empty:
        return None, title
    labels, s = _months_xy(f)
    fig = go.Figure(go.Scatter(
        x=labels, y=s.values, mode="lines+markers",
        line=dict(color=CUR_COLOR, width=3),
        marker=dict(size=7, color=CUR_COLOR),
        fill="tozeroy", fillcolor="rgba(98,221,255,.10)",
        hovertemplate="%{x}<br><b>%{y}</b> consignation(s)<extra></extra>"))
    fig.update_layout(height=height, yaxis_title="Nombre de consignations",
                      yaxis_rangemode="nonnegative",
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title


# ==================================================================
# ② ÉVOLUTION PAR POSTE
# ==================================================================
def fig_evo_poste(frame: pd.DataFrame, year: int, dur_cat: str | None,
                  boundaries: dict | None, postes: list[str] | None,
                  height: int = 360) -> tuple[go.Figure | None, str, bool]:
    """Courbes par poste pour l'année N (couleur propre) avec comparaison N-1
    intégrée dans une couleur distincte (pointillés + marqueurs carrés).

    · « Tous les postes » → courbe agrégée N + courbe agrégée N-1.
    · Postes sélectionnés → une courbe N par poste + sa courbe N-1.
    L'année N-1 n'apparaît que si des données réelles existent.
    Retourne (fig, titre, a_compare) ; a_compare=False si N-1 indisponible."""
    title = "Évolution par poste — N vs N-1"
    prev = year - 1
    f = _select(frame, year, dur_cat, boundaries)
    fp = _select(frame, prev, dur_cat, boundaries)
    has_prev = not fp.empty
    if f.empty or postes is None or not postes:
        return None, title, has_prev
    fig = go.Figure()
    if ALL_POSTES in postes:
        labels, s = _months_xy(f)
        fig.add_trace(go.Scatter(
            x=labels, y=s.values, name=f"Tous les postes ({year})",
            mode="lines+markers", line=dict(color=CUR_COLOR, width=3),
            marker=dict(size=6)))
        if has_prev:
            lp, sp = _months_xy(fp)
            fig.add_trace(go.Scatter(
                x=lp, y=sp.values, name=f"Tous les postes ({prev})",
                mode="lines+markers",
                line=dict(color=PREV_COLOR, width=2.2, dash="dot"),
                marker=dict(size=6, symbol="square"), opacity=0.7))
    else:
        picks = sorted(set(postes))
        for i, p in enumerate(picks):
            pf = f[f["poste"] == p]
            if pf.empty:
                continue
            labels, s = _months_xy(pf)
            fig.add_trace(go.Scatter(
                x=labels, y=s.values, name=f"{p} ({year})", mode="lines+markers",
                line=dict(color=COLOR_SEQ[i % len(COLOR_SEQ)], width=2.4),
                marker=dict(size=6)))
            pp = fp[fp["poste"] == p]
            if has_prev and not pp.empty:
                lp, sp = _months_xy(pp)
                fig.add_trace(go.Scatter(
                    x=lp, y=sp.values, name=f"{p} ({prev})", mode="lines+markers",
                    line=dict(color=PREV_COLOR, width=2.2, dash="dot"),
                    marker=dict(size=6, symbol="square"), opacity=0.7))
    if not fig.data:
        return None, title, has_prev
    fig.update_layout(height=height, yaxis_title="Nombre de consignations",
                      legend=dict(orientation="h", yanchor="bottom", y=1.06,
                                  font=dict(size=9)),
                      hovermode="x unified",
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title, has_prev


# ==================================================================
# ③ N vs N-1 (périodes réellement comparables)
# ==================================================================
def fig_evo_nvsn1(frame: pd.DataFrame, year: int, dur_cat: str | None,
                  boundaries: dict | None, poste: str | None,
                  height: int = 330) -> tuple[go.Figure | None, str, bool]:
    """Comparaison N (trait plein) vs N-1 (pointillés) sur les mois présents
    dans les DEUX années. Renvoie (fig, titre, comparable)."""
    prev = year - 1
    title = f"N vs N-1 — {year} vs {prev}"
    if prev not in set(frame["year"]):
        return None, title, False
    f = _select(frame, year, dur_cat, boundaries)
    fp = _select(frame, prev, dur_cat, boundaries)
    if poste and poste != ALL_POSTES:
        f = f[f["poste"] == poste]
        fp = fp[fp["poste"] == poste]
    sc = f.groupby("month").size()
    sp = fp.groupby("month").size()
    common = sorted(set(sc.index) & set(sp.index))
    if not common:
        return None, title, False
    labels = [MONTHS_FR[m - 1] for m in common]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=[sc[m] for m in common], name=f"{year} (N)",
        mode="lines+markers", line=dict(color=CUR_COLOR, width=3),
        marker=dict(size=7)))
    fig.add_trace(go.Scatter(
        x=labels, y=[sp[m] for m in common], name=f"{prev} (N-1)",
        mode="lines+markers", line=dict(color=PREV_COLOR, width=2.5, dash="dot"),
        marker=dict(size=7, symbol="square")))
    fig.update_layout(height=height, yaxis_title="Nombre de consignations",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04,
                                  font=dict(size=10)),
                      hovermode="x unified",
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title, True


# ==================================================================
# ④ ÉVOLUTION SELON LA DURÉE (barres empilées Courte / Moyenne / Longue)
# ==================================================================
def fig_evo_duree(frame: pd.DataFrame, year: int,
                  postes: list[str] | None, boundaries: dict | None,
                  height: int = 300) -> tuple[go.Figure | None, str]:
    """Répartition mensuelle des consignations par catégorie de durée."""
    title = "Évolution selon la durée"
    f = frame[frame["year"] == year].copy()
    cat_duration(f, boundaries, inplace=True)
    if postes and ALL_POSTES not in postes:
        f = f[f["poste"].isin(postes)]
    if f.empty:
        return None, title
    piv = f.groupby(["month", "duree_cat"]).size().unstack(fill_value=0)
    for cat in (DUR_CAT_SHORT, DUR_CAT_MEDIUM, DUR_CAT_LONG):
        if cat not in piv.columns:
            piv[cat] = 0
    piv = piv[[DUR_CAT_SHORT, DUR_CAT_MEDIUM, DUR_CAT_LONG]]
    labels = [MONTHS_FR[int(m) - 1] for m in piv.index]
    fig = go.Figure()
    for cat in piv.columns:
        fig.add_trace(go.Bar(
            x=labels, y=piv[cat].values, name=cat,
            marker_color=DUR_CAT_COLORS[cat],
            hovertemplate="%{x}<br><b>%{y}</b> consignation(s) — "
                          f"{cat}<extra></extra>"))
    fig.update_layout(barmode="stack", height=height,
                      yaxis_title="Nombre de consignations",
                      legend=dict(orientation="h", yanchor="bottom", y=1.04,
                                  font=dict(size=9)),
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title