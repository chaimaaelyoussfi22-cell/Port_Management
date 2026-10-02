# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse des navires » (dashboard Power BI).

Métrique centrale : NAVIRES UNIQUES (COUNT DISTINCT navire_name).
Escales = COUNT DISTINCT escale_key · Moyenne = escales ÷ navires uniques.
Aucune dépendance Streamlit — données + figures Plotly pures, testables.
"""

import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, UNSPECIFIED, _apply_theme)


# ==================================================================
# PRÉPARATION
# ==================================================================
def _bn(frame: pd.DataFrame) -> pd.DataFrame:
    """Lignes exploitables : navire identifié + année/mois présents."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    f = frame.copy()
    f["navire_name"] = f["navire_name"].fillna("").astype(str).str.strip()
    f["escale_key"] = f["escale_key"].fillna("").astype(str)
    f = f[(f["navire_name"] != "") & f["month"].notna() & f["year"].notna()]
    f["month"] = f["month"].astype(int)
    f["year"] = f["year"].astype(int)
    return f


def available_years(frame: pd.DataFrame) -> list[int]:
    f = _bn(frame)
    return sorted(f["year"].unique().tolist(), reverse=True) if not f.empty else []


def available_months(frame: pd.DataFrame, year: int) -> list[int]:
    """Mois réellement présents pour une année donnée."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty:
        return []
    return sorted(f["month"].dropna().astype(int).unique().tolist())


def available_categories(frame: pd.DataFrame, year: int, months: list[int],
                         col: str) -> list[str]:
    """Catégories réellement présentes pour la période (année + mois choisis)."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty:
        return []
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return []
    return sorted(_cat(f, col).unique().tolist())


def _cat(frame: pd.DataFrame, col: str) -> pd.Series:
    s = frame[col].fillna("").astype(str).str.strip()
    return s.mask(s == "", UNSPECIFIED)


# ==================================================================
# KPI
# ==================================================================
def kpi_block(frame: pd.DataFrame, year: int) -> dict:
    """Navires uniques · escales totales · moyenne escales/navire · évolution N-1."""
    f = _bn(frame)
    cur = f[f["year"] == year]
    prev = f[f["year"] == year - 1]
    ships = int(cur["navire_name"].nunique())
    escales = int(cur["escale_key"].nunique()) if not cur.empty else 0
    prev_ships = int(prev["navire_name"].nunique())
    evolution = (round(100 * (ships - prev_ships) / prev_ships, 1)
                 if prev_ships else None)
    return {
        "ships": ships,
        "escales": escales,
        "avg": round(escales / ships, 1) if ships else 0.0,
        "prev_ships": prev_ships,
        "evolution": evolution,
    }


# ==================================================================
# AGRÉGATS
# ==================================================================
def navires_monthly(frame: pd.DataFrame, year: int) -> pd.Series:
    """Navires uniques par mois — uniquement les mois réellement présents."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.Series(dtype=int)
    return f.groupby("month")["navire_name"].nunique().astype(int)


def navires_daily(frame: pd.DataFrame, year: int,
                  month: int | None = None) -> pd.DataFrame:
    """Navires uniques par jour → mmdd / label / navires.
    Année complète (month=None) ou mois précis (jour par jour, aligné MM-DD)."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty or "date" not in f.columns:
        return pd.DataFrame(columns=["mmdd", "label", "navires"])
    d = pd.to_datetime(f["date"], errors="coerce")
    ok = d.notna()
    f = f[ok]
    dd = d[ok]
    if month is not None:
        keep = dd.dt.month == month
        f = f[keep]
        dd = dd[keep]
    if f.empty:
        return pd.DataFrame(columns=["mmdd", "label", "navires"])
    day = dd.dt.normalize()
    g = f.assign(day=day).groupby("day")["navire_name"].nunique().sort_index()
    idx = g.index
    return pd.DataFrame({
        "mmdd": idx.strftime("%m-%d"),
        "label": idx.strftime("%d/%m"),
        "navires": g.astype(int).values,
    })


def navires_by_category(frame: pd.DataFrame, year: int, months: list[int],
                        col: str, cats: list[str] | None = None) -> pd.DataFrame:
    """Navires uniques par catégorie (type de navire / opérateur), tri décroissant."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=[col, "navires"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=[col, "navires"])
    f = f.assign(cat=_cat(f, col))
    if cats:
        f = f[f["cat"].isin(cats)]
    if f.empty:
        return pd.DataFrame(columns=[col, "navires"])
    g = f.groupby("cat")["navire_name"].nunique().sort_values(ascending=False)
    return g.rename_axis(col).reset_index(name="navires")


def navires_by_marchandise_monthly(frame: pd.DataFrame, year: int,
                                   months: list[int],
                                   marches: list[str]) -> pd.DataFrame:
    """Navires uniques par (mois × marchandise), restreint aux sélections."""
    f = _bn(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "navires"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "navires"])
    f = f.assign(marchandise=_cat(f, "marchandise_norm"))
    if marches:
        f = f[f["marchandise"].isin(marches)]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "navires"])
    g = (f.groupby(["month", "marchandise"])["navire_name"]
         .nunique().reset_index(name="navires"))
    return g


def top_label(frame: pd.DataFrame, year: int, col: str) -> str:
    g = navires_by_category(frame, year, [], col)
    return str(g.iloc[0][col]) if not g.empty else "—"


def _months_suffix(months: list[int]) -> str:
    return " · " + ", ".join(MOIS_NOMS[m - 1] for m in sorted(months)) if months \
        else " · toute l'année"


# ==================================================================
# FIGURES
# ==================================================================
def fig_evolution(frame: pd.DataFrame, year: int,
                  month: int | None = None) -> go.Figure | None:
    """① Évolution des navires N vs N-1 — mois par mois (année complète) ou
    jour par jour (mois sélectionné, aligné MM-DD sur la même période réelle)."""
    fig = go.Figure()

    def _trace(year_target: int, name: str, color: str, dash: str | None):
        sub = _bn(frame)
        sub = sub[sub["year"] == year_target] if not sub.empty else sub
        if sub.empty:
            return  # année absente → pas de courbe fantôme à zéro
        if month is not None:
            s = navires_daily(frame, year_target, month)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=s["mmdd"], y=s["navires"], name=name,
                mode="lines+markers" if len(s) < 40 else "lines",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                customdata=s["label"].tolist(),
                hovertemplate="%{customdata}<br>%{y} navires<extra>" + name + "</extra>"))
        else:
            s = navires_monthly(frame, year_target)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=[MONTHS_FR[m - 1] for m in s.index], y=s.values, name=name,
                mode="lines+markers",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                hovertemplate="%{x}<br>%{y} navires<extra>" + name + "</extra>"))

    _trace(year, f"Année N ({year})", CUR_COLOR, None)
    _trace(year - 1, f"Année N-1 ({year - 1})", PREV_COLOR, "dot")
    if not fig.data:
        return None
    fig.update_layout(
        height=360, yaxis_title="Nombre de navires",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if month is None else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


def _ranked_bars(g: pd.DataFrame, col: str, value_col: str, unit: str,
                 height_min: int = 300) -> go.Figure | None:
    """Barres horizontales classées (top au-dessus) + tooltip % du total."""
    if g is None or g.empty:
        return None
    total = max(int(g[value_col].sum()), 1)
    g = g.head(15).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=g[value_col], y=g[col].astype(str), orientation="h",
        marker_color=CUR_COLOR, marker_line_width=0,
        customdata=[[int(v), round(100 * v / total, 1)] for v in g[value_col]],
        hovertemplate="%{y}<br>%{customdata[0]} " + unit
                      + " (%{customdata[1]} %)<extra></extra>"))
    fig.update_layout(height=max(height_min, 34 * len(g) + 90),
                      xaxis_title=f"Nombre de {unit}")
    return _apply_theme(fig)


def fig_type_navire(frame: pd.DataFrame, year: int, months: list[int],
                    types: list[str] | None = None) -> tuple[go.Figure | None, str]:
    """② Navires uniques par type de navire — classement automatique."""
    g = navires_by_category(frame, year, months, "type_navire_norm", types)
    title = "Navires par type de navire" + _months_suffix(months)
    if types is not None:
        title += f" · {len(types)} type(s) sélectionné(s)"
    return _ranked_bars(g, "type_navire_norm", "navires", "navires"), title


def fig_operateur(frame: pd.DataFrame, year: int, months: list[int],
                  operateurs: list[str] | None = None) -> tuple[go.Figure | None, str]:
    """③ Navires uniques par opérateur — classement automatique."""
    g = navires_by_category(frame, year, months, "operateur_norm", operateurs)
    title = "Navires par opérateur" + _months_suffix(months)
    if operateurs is not None:
        title += f" · {len(operateurs)} opérateur(s)"
    return _ranked_bars(g, "operateur_norm", "navires", "navires"), title


def fig_marchandise(frame: pd.DataFrame, year: int, months: list[int],
                    marches: list[str]) -> tuple[go.Figure | None, str]:
    """④ Navires uniques par marchandise — analyse mensuelle empilée."""
    g = navires_by_marchandise_monthly(frame, year, months, marches)
    title = "Navires par type de marchandise"
    title += _months_suffix(months) if months else ""
    if g.empty:
        return None, title
    order = (g.groupby("marchandise")["navires"].sum()
             .sort_values(ascending=False).index.tolist())
    total = max(int(g["navires"].sum()), 1)
    shown_months = sorted(g["month"].unique())
    labels = [MOIS_NOMS[m - 1] for m in shown_months]
    fig = go.Figure()
    for i, m in enumerate(order):
        sub = g[g["marchandise"] == m].set_index("month")["navires"]
        y = [int(sub.get(mm, 0)) for mm in shown_months]
        fig.add_bar(x=labels, y=y, name=m,
                    marker_color=COLOR_SEQ[i % len(COLOR_SEQ)],
                    customdata=[[v, round(100 * v / total, 1)] for v in y],
                    hovertemplate="%{x} · " + str(m)
                                  + "<br>%{customdata[0]} navires (%{customdata[1]} %)"
                                    "<extra></extra>")
    fig.update_layout(height=400, barmode="stack",
                      yaxis_title="Nombre de navires",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return _apply_theme(fig), title
