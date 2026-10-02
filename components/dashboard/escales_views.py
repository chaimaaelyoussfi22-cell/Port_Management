# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse des escales » (dashboard Power BI).

Comptage officiel : COUNT DISTINCT escale_key (même définition que les KPI).
Aucune dépendance Streamlit ici — logique de données + figures Plotly purses,
réutilisables et testables hors runtime.
"""

import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.analysis_views import COLOR_SEQ, _apply_theme

CUR_COLOR = "#62ddff"     # année N
PREV_COLOR = "#f2b84b"    # année N-1
UNSPECIFIED = "(non spécifié)"


# ==================================================================
# PRÉPARATION
# ==================================================================
def _base(frame: pd.DataFrame) -> pd.DataFrame:
    """Lignes exploitables : année/mois présents + clé d'escale non vide."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    f = frame.copy()
    f["escale_key"] = f["escale_key"].fillna("").astype(str)
    f = f[(f["escale_key"] != "") & f["month"].notna() & f["year"].notna()]
    f["month"] = f["month"].astype(int)
    f["year"] = f["year"].astype(int)
    return f


def available_years(frame: pd.DataFrame) -> list[int]:
    f = _base(frame)
    return sorted(f["year"].unique().tolist(), reverse=True) if not f.empty else []


def available_months(frame: pd.DataFrame, year: int) -> list[int]:
    """Mois réellement présents pour une année donnée."""
    f = _base(frame)
    f = f[f["year"] == year]
    if f.empty:
        return []
    return sorted(f["month"].dropna().astype(int).unique().tolist())


def available_categories(frame: pd.DataFrame, year: int, months: list[int],
                         col: str) -> list[str]:
    """Catégories réellement présentes pour la période (année + mois choisis)."""
    f = _base(frame)
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
# AGRÉGATS
# ==================================================================
def escales_monthly(frame: pd.DataFrame, year: int) -> pd.Series:
    """Escales distinctes par mois pour une année — uniquement les mois avec données."""
    f = _base(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.Series(dtype=int)
    counts = f.groupby("month")["escale_key"].nunique()
    return counts.astype(int)


def escales_daily(frame: pd.DataFrame, year: int,
                  month: int | None = None) -> pd.DataFrame:
    """Escales distinctes par jour → colonnes mmdd / label / escales.
    Année complète (month=None) ou mois précis (jour par jour, aligné MM-DD)."""
    f = _base(frame)
    f = f[f["year"] == year]
    if f.empty or "date" not in f.columns:
        return pd.DataFrame(columns=["mmdd", "label", "escales"])
    d = pd.to_datetime(f["date"], errors="coerce")
    ok = d.notna()
    f = f[ok]
    dd = d[ok]
    if month is not None:
        keep = dd.dt.month == month
        f = f[keep]
        dd = dd[keep]
    if f.empty:
        return pd.DataFrame(columns=["mmdd", "label", "escales"])
    f["day"] = dd.dt.normalize()
    g = f.groupby("day")["escale_key"].nunique().sort_index()
    idx = g.index
    return pd.DataFrame({
        "mmdd": idx.strftime("%m-%d"),
        "label": idx.strftime("%d/%m"),
        "escales": g.astype(int).values,
    })


def escales_by_marchandise_monthly(frame: pd.DataFrame, year: int,
                                   months: list[int] | None = None,
                                   marches: list[str] | None = None) -> pd.DataFrame:
    """Escales par (mois × marchandise) restreinte aux mois/marchandises choisis."""
    f = _base(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "escales"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "escales"])
    f = f.assign(marchandise=_cat(f, "marchandise_norm"))
    if marches:
        f = f[f["marchandise"].isin(marches)]
    if f.empty:
        return pd.DataFrame(columns=["month", "marchandise", "escales"])
    g = (f.groupby(["month", "marchandise"])["escale_key"]
         .nunique().reset_index(name="escales"))
    return g


def escales_by_category(frame: pd.DataFrame, year: int, months: list[int],
                        col: str, cats: list[str] | None = None) -> pd.DataFrame:
    """Escales par catégorie (type de navire / opérateur) sur la période choisie."""
    f = _base(frame)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=[col, "escales"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=[col, "escales"])
    f = f.assign(cat=_cat(f, col))
    if cats:
        f = f[f["cat"].isin(cats)]
    if f.empty:
        return pd.DataFrame(columns=[col, "escales"])
    g = f.groupby("cat")["escale_key"].nunique().sort_values(ascending=False)
    return g.rename_axis(col).reset_index(name="escales")


def top_label(frame: pd.DataFrame, col: str, year: int) -> str:
    g = escales_by_category(frame, year, [], col)
    return str(g.iloc[0][col]) if not g.empty else "—"


# ==================================================================
# FIGURES
# ==================================================================
def fig_evolution(frame: pd.DataFrame, year: int,
                  month: int | None = None) -> go.Figure | None:
    """① Évolution N vs N-1 — mois par mois (année complète) ou jour par jour
    (mois sélectionné, aligné MM-DD sur la même période réelle)."""
    prev_year = year - 1
    fig = go.Figure()

    def _trace(year_target: int, name: str, color: str, dash: str | None):
        sub = _base(frame)
        sub = sub[sub["year"] == year_target] if not sub.empty else sub
        if sub.empty:
            return  # année absente des données → aucune courbe (pas de ligne à zéro)
        if month is not None:
            s = escales_daily(frame, year_target, month)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=s["mmdd"], y=s["escales"], name=name,
                mode="lines+markers" if len(s) < 40 else "lines",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                customdata=s["label"].tolist(),
                hovertemplate="%{customdata}<br>%{y} escales<extra>"
                              + name + "</extra>"))
        else:
            s = escales_monthly(frame, year_target)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=[MONTHS_FR[m - 1] for m in s.index], y=s.values, name=name,
                mode="lines+markers",
                line={"color": color, "width": 3 if dash is None else 2,
                      "dash": dash or "solid"},
                hovertemplate="%{x}<br>%{y} escales<extra>"
                              + name + "</extra>"))

    _trace(year, f"Année N ({year})", CUR_COLOR, None)
    _trace(prev_year, f"Année N-1 ({prev_year})", PREV_COLOR, "dot")
    if not fig.data:
        return None
    fig.update_layout(
        height=360, yaxis_title="Nombre d'escales",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if month is None else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


def fig_marchandise(frame: pd.DataFrame, year: int,
                    months: list[int] | None = None,
                    marches: list[str] | None = None) -> go.Figure | None:
    """② Répartition mensuelle des escales par marchandise (barres empilées)."""
    g = escales_by_marchandise_monthly(frame, year, months, marches)
    if g.empty:
        return None
    order = (g.groupby("marchandise")["escales"].sum()
             .sort_values(ascending=False).index.tolist())
    total = max(int(g["escales"].sum()), 1)
    all_months = sorted(g["month"].unique())
    if not all_months:
        return None
    fig = go.Figure()
    for i, m in enumerate(order):
        sub = g[g["marchandise"] == m].set_index("month")["escales"]
        y = [int(sub.get(mth, 0)) for mth in all_months]
        fig.add_bar(x=[MONTHS_FR[mth - 1] for mth in all_months], y=y, name=m,
                    marker_color=COLOR_SEQ[i % len(COLOR_SEQ)],
                    customdata=[[v, round(100 * v / total, 1)] for v in y],
                    hovertemplate="%{x} · " + str(m)
                                  + "<br>%{customdata[0]} escales (%{customdata[1]} %)"
                                    "<extra></extra>")
    fig.update_layout(height=360, barmode="stack",
                      yaxis_title="Nombre d'escales",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return _apply_theme(fig)


def fig_category(frame: pd.DataFrame, year: int, months: list[int],
                 col: str, cat_label: str,
                 cats: list[str] | None = None) -> tuple[go.Figure | None, str]:
    """③④ Barres horizontales escales par type de navire / opérateur."""
    g = escales_by_category(frame, year, months, col, cats)
    title = cat_label
    if g.empty:
        return None, title
    if months:
        title += " · " + ", ".join(MOIS_NOMS[m - 1] for m in sorted(months))
    else:
        title += " · toute l'année"
    if cats is not None:
        title += f" · {len(cats)} catégorie(s)"
    total = max(int(g["escales"].sum()), 1)
    g = g.head(12).iloc[::-1]  # top au-dessus
    fig = go.Figure(go.Bar(
        x=g["escales"], y=g[col].astype(str), orientation="h",
        marker_color=CUR_COLOR, marker_line_width=0,
        customdata=[[int(v), round(100 * v / total, 1)] for v in g["escales"]],
        hovertemplate="%{y}<br>%{customdata[0]} escales (%{customdata[1]} %)<extra></extra>"))
    fig.update_layout(height=max(280, 34 * len(g) + 90), xaxis_title="Nombre d'escales")
    return _apply_theme(fig), title
