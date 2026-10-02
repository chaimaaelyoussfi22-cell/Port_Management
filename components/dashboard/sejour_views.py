# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse du séjour à quai » (dashboard Power BI).

Métrique centrale : durée de séjour à quai (quai_h) = Appareillage_Quai − Accostage.
Aucune dépendance Streamlit ici — données + figures Plotly pures, testables.

Visualisations :
  ① Évolution du séjour moyen N vs N-1
  ② Séjour moyen par poste N vs N-1 (référentiel complet) + évolution %
  ③ Temps à quai par marchandise (donut, filtrable)
  ④ Séjour moyen par type de navire (dégradé)
  ⑤ Séjour moyen par opérateur
  ⑥ Distribution des durées de séjour par classe de durée (barres colorées)
  ⑦ Performance par poste (tableau, référentiel complet)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, UNSPECIFIED, _apply_theme)

from validators import POSTES_VALIDES

ALL_POSTES = "Tous les postes"
ALL_MARCHANDISES = "Toutes les marchandises"

# Référentiel officiel des postes (ordre métier, valeurs normalisées).
POSTE_REFERENTIEL = list(POSTES_VALIDES)

# Libellés d'affichage officiels (casse mixte, identiques à la saisie).
POSTE_DISPLAY = {"1BIS": "1Bis", "1TER": "1Ter", "2BIS": "2Bis",
                 "2TER": "2Ter", "4BIS": "4Bis", "3BIS": "3Bis"}
POSTE_DISPLAY_REV = {v: k for k, v in POSTE_DISPLAY.items()}


def _poste_label(p: str) -> str:
    """Libellé d'affichage officiel d'un poste (ex. « 1BIS » → « 1Bis »)."""
    return POSTE_DISPLAY.get(p, p)


def _poste_key(p: str) -> str:
    """Clé normalisée d'un poste à partir de son libellé d'affichage."""
    return POSTE_DISPLAY_REV.get(p, p)

# Dégradé de couleurs pour les classes de durée (vert → ambre → rouge).
DUR_CLASS_COLORS = ["#32d2a4", "#56a8ff", "#62ddff", "#f2b84b",
                    "#ffab3d", "#ff6077", "#ff8fb3"]


# ==================================================================
# PRÉPARATION
# ==================================================================
def _base(frame: pd.DataFrame) -> pd.DataFrame:
    """Lignes exploitables : quai_h > 0 + année/mois présents."""
    required = {"quai_h", "month", "year"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    f = frame.copy()
    f["quai_h"] = pd.to_numeric(f["quai_h"], errors="coerce")
    f = f[(f["quai_h"].notna()) & (f["quai_h"] > 0)
           & f["month"].notna() & f["year"].notna()]
    if f.empty:
        return pd.DataFrame()
    f["month"] = f["month"].astype(int)
    f["year"] = f["year"].astype(int)
    return f


def available_years(frame: pd.DataFrame) -> list[int]:
    f = _base(frame)
    return sorted(f["year"].unique().tolist(), reverse=True) if not f.empty else []


def _cat(frame: pd.DataFrame, col: str) -> pd.Series:
    s = frame[col].fillna("").astype(str).str.strip()
    return s.mask(s == "", UNSPECIFIED)


def _period(frame: pd.DataFrame, year: int,
            months: list[int]) -> pd.DataFrame:
    """Sous-ensemble réel de la période : année + mois choisis."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return pd.DataFrame()
    f = f[f["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    return f


# ==================================================================
# KPI
# ==================================================================
def kpi_block(frame: pd.DataFrame, year: int) -> dict:
    """KPI du séjour à quai : moyenne, médiane, max, navires uniques, évolution."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return {"avg": 0.0, "median": 0.0, "max": 0.0, "ships": 0,
                "prev_avg": 0.0, "evolution": None, "count": 0}
    cur = f[f["year"] == year]
    prev = f[f["year"] == year - 1]
    if cur.empty:
        return {"avg": 0.0, "median": 0.0, "max": 0.0, "ships": 0,
                "prev_avg": 0.0, "evolution": None, "count": 0}
    avg = round(float(cur["quai_h"].mean()), 1)
    median = round(float(cur["quai_h"].median()), 1)
    max_val = round(float(cur["quai_h"].max()), 1)
    ships = int(cur["navire_name"].nunique()) if "navire_name" in cur.columns else 0
    count = len(cur)
    prev_avg = round(float(prev["quai_h"].mean()), 1) if not prev.empty else 0.0
    evolution = (round(100 * (avg - prev_avg) / prev_avg, 1)
                 if prev_avg > 0 else None)
    return {"avg": avg, "median": median, "max": max_val, "ships": ships,
            "prev_avg": prev_avg, "evolution": evolution, "count": count}


# ==================================================================
# AGRÉGATS MENSUELS / JOURNALIERS
# ==================================================================
def sejour_monthly(frame: pd.DataFrame, year: int) -> pd.Series:
    """Séjour moyen par mois pour une année — uniquement les mois avec données."""
    f = _base(frame)
    if f.empty:
        return pd.Series(dtype=float)
    f = f[f["year"] == year]
    if f.empty:
        return pd.Series(dtype=float)
    means = f.groupby("month")["quai_h"].mean()
    return means.round(2)


def sejour_daily(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    """Séjour moyen par jour pour une année."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return pd.DataFrame(columns=["mmdd", "label", "sejour"])
    f = f[f["year"] == year]
    if f.empty or "date" not in f.columns:
        return pd.DataFrame(columns=["mmdd", "label", "sejour"])
    d = pd.to_datetime(f["date"], errors="coerce")
    f = f[d.notna()]
    f["day"] = d[d.notna()].dt.normalize()
    g = f.groupby("day")["quai_h"].mean().sort_index()
    idx = g.index
    return pd.DataFrame({
        "mmdd": idx.strftime("%m-%d"),
        "label": idx.strftime("%d/%m"),
        "sejour": g.round(2).values,
    })


# ==================================================================
# AGRÉGATS PAR CATÉGORIE
# ==================================================================
def _avg_by_cat(frame: pd.DataFrame, year: int, months: list[int],
                col: str) -> pd.DataFrame:
    """Séjour moyen par catégorie (poste / marchandise / type navire / opérateur)."""
    f = _period(frame, year, months)
    if f.empty:
        return pd.DataFrame(columns=[col, "sejour_moyen", "escales", "navires"])
    f = f.assign(cat=_cat(f, col))
    g = f.groupby("cat").agg(
        sejour_moyen=("quai_h", "mean"),
        escales=("escale_key", "nunique"),
        navires=("navire_name", "nunique"),
    ).sort_values("sejour_moyen", ascending=False).reset_index()
    g["sejour_moyen"] = g["sejour_moyen"].round(2)
    return g.rename(columns={"cat": col})


def sejour_by_poste(frame: pd.DataFrame, year: int,
                    months: list[int]) -> pd.DataFrame:
    return _avg_by_cat(frame, year, months, "poste_norm")


def sejour_by_marchandise(frame: pd.DataFrame, year: int,
                          months: list[int]) -> pd.DataFrame:
    return _avg_by_cat(frame, year, months, "marchandise_norm")


def sejour_by_type_navire(frame: pd.DataFrame, year: int,
                          months: list[int]) -> pd.DataFrame:
    return _avg_by_cat(frame, year, months, "type_navire_norm")


def sejour_by_operateur(frame: pd.DataFrame, year: int,
                        months: list[int]) -> pd.DataFrame:
    return _avg_by_cat(frame, year, months, "operateur_norm")


def _avg_map(frame: pd.DataFrame, col: str) -> dict[str, float]:
    """Séjour moyen par catégorie réelle de la colonne (dict nom → valeur)."""
    if frame.empty or col not in frame.columns:
        return {}
    by = _cat(frame, col)
    s = frame.assign(_cat=by).groupby("_cat")["quai_h"].mean()
    return {k: float(v) for k, v in s.items()}


def poste_options(frame: pd.DataFrame, year: int,
                  months: list[int]) -> list[str]:
    """Référentiel complet des postes (libellés d'affichage officiels) + postes
    réellement présents hors liste, précédés de « Tous les postes »."""
    keys = list(POSTE_REFERENTIEL)
    f = _period(frame, year, months)
    if not f.empty:
        real = sorted({p for p in f.get("poste_norm", pd.Series(dtype=object))
                       .fillna("").astype(str) if p and p != UNSPECIFIED})
        for p in real:
            if p not in keys:
                keys.append(p)
    return [ALL_POSTES] + [_poste_label(k) for k in keys]


def marchandise_options(frame: pd.DataFrame, year: int,
                        months: list[int]) -> list[str]:
    """Marchandises réellement présentes sur la période (sélection complète)."""
    f = _period(frame, year, months)
    if f.empty:
        return [ALL_MARCHANDISES]
    cats = sorted({c for c in _cat(f, "marchandise_norm").unique() if c})
    return [ALL_MARCHANDISES] + cats


def performance_by_poste(frame: pd.DataFrame, year: int,
                         months: list[int],
                         postes: list[str] | None = None) -> pd.DataFrame:
    """Tableau : poste, nb navires, nb escales, séjour moyen, tonnage total.

    Référentiel exact : en mode « Tous les postes », uniquement les postes de
    POSTE_REFERENTIEL dans l'ordre métier, y compris sans activité (valeurs
    0). Filtre postes : si une sélection est faite, seuls ces postes sont
    listés, valeurs 0 pour ceux sans activité."""
    cols = ["poste", "navires", "escales", "sejour_moyen", "tonnage"]
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return pd.DataFrame(columns=cols)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=cols)
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f.assign(poste_label=_cat(f, "poste_norm"))
    if postes and ALL_POSTES not in postes:
        sel = [_poste_key(p) for p in postes if p and p != ALL_POSTES]
        f = f[f["poste_label"].isin(sel)]
    if f.empty:
        return pd.DataFrame(columns=cols)
    g = f.groupby("poste_label").agg(
        navires=("navire_name", "nunique"),
        escales=("escale_key", "nunique"),
        sejour_moyen=("quai_h", "mean"),
        tonnage=("tonnage", "sum"))
    if postes and ALL_POSTES not in postes:
        order = [_poste_key(p) for p in postes if p and p != ALL_POSTES]
    else:
        order = list(POSTE_REFERENTIEL)
    g = g.reindex(order, fill_value=0)
    g.index = [_poste_label(p) for p in g.index]
    g["sejour_moyen"] = g["sejour_moyen"].round(2)
    g["tonnage"] = g["tonnage"].round(0).astype(int)
    return g.rename_axis("poste").reset_index()


def distribution_data(frame: pd.DataFrame, year: int,
                      nbins: int = 30) -> pd.DataFrame:
    """Données pour histogramme des durées de séjour."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return pd.DataFrame(columns=["quai_h"])
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=["quai_h"])
    return f[["quai_h"]]


# ==================================================================
# FIGURES
# ==================================================================
def _months_suffix(months: list[int]) -> str:
    from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
    return (" · " + ", ".join(MOIS_NOMS[m - 1] for m in sorted(months))
            if months else " · toute l'année")


def fig_evolution(frame: pd.DataFrame, year: int,
                  granularity: str = "Par mois") -> go.Figure | None:
    """① Évolution N vs N-1 — courbes séjour moyen (mois ou jour)."""
    fig = go.Figure()

    def _trace(year_target: int, name: str, color: str, dash: str | None):
        if granularity == "Par jour":
            s = sejour_daily(frame, year_target)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=s["mmdd"], y=s["sejour"], name=name,
                mode="lines+markers" if len(s) < 200 else "lines",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                customdata=s["label"].tolist(),
                hovertemplate="%{customdata}<br>%{y:.1f} h<extra>" + name + "</extra>"))
        else:
            s = sejour_monthly(frame, year_target)
            if s.sum() == 0:
                return
            fig.add_trace(go.Scatter(
                x=[MONTHS_FR[m - 1] for m in s.index], y=s.values, name=name,
                mode="lines+markers",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                hovertemplate="%{x}<br>%{y:.1f} h<extra>" + name + "</extra>"))

    _trace(year, f"Année N ({year})", CUR_COLOR, None)
    _trace(year - 1, f"Année N-1 ({year - 1})", PREV_COLOR, "dot")
    if not fig.data:
        return None
    fig.update_layout(
        height=310, yaxis_title="Durée moyenne de séjour (h)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if granularity == "Par mois" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


def fig_poste(frame: pd.DataFrame, year: int,
              months: list[int],
              postes: list[str] | None = None) -> tuple[go.Figure | None, str]:
    """② Postes : séjour moyen N vs N-1 (EN JOURS) par poste — en mode « Tous les
    postes », exactement le référentiel officiel dans l'ordre métier, avec
    évolution % calculée quand les deux années sont disponibles (sinon « — »).
    Filtre postes : si une sélection est faite, seuls ces postes sont tracés,
    toujours dans l'ordre métier."""
    title = "Séjour moyen par poste — N vs N-1" + _months_suffix(months)
    cur = _period(frame, year, months)
    prev = _period(frame, year - 1, months)
    if cur.empty:
        return None, title
    if postes and ALL_POSTES not in postes:
        order = [_poste_key(p) for p in postes if p and p != ALL_POSTES]
    else:
        order = list(POSTE_REFERENTIEL)
    if not order:
        return None, title
    labels = [_poste_label(p) for p in order]
    m_cur = _avg_map(cur, "poste_norm")
    m_prev = _avg_map(prev, "poste_norm")
    xs_n = [round(m_cur.get(p) / 24.0, 2) if m_cur.get(p) is not None else None
            for p in order]
    xs_p = [round(m_prev.get(p) / 24.0, 2) if m_prev.get(p) is not None else None
            for p in order]
    evo = []
    for a, b in zip(xs_n, xs_p):
        if a is not None and b is not None and b > 0:
            evo.append(100 * (a - b) / b)
        else:
            evo.append(None)
    maxv = max((v for v in xs_n + xs_p if v is not None), default=0.0)
    pad = max(0.05, 0.06 * maxv)
    tx, ty, ts, tc = [], [], [], []
    for i, (p, a, b, e) in enumerate(zip(order, xs_n, xs_p, evo)):
        if a is None and b is None:
            continue
        tx.append((a if a is not None else b) + pad)
        ty.append(labels[i])
        if e is None:
            ts.append("—")
            tc.append("#8f9bb3")
        elif e <= 0:
            ts.append(f"{e:+.1f} %")
            tc.append("#2dd4bf")
        else:
            ts.append(f"{e:+.1f} %")
            tc.append("#ff6077")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=xs_n, y=labels, orientation="h", name=f"Année N ({year})",
        marker_color=CUR_COLOR, marker_line_width=0,
        hovertemplate="<b>Poste %{y}</b><br>Séjour N : %{x:.2f} j<extra></extra>"))
    fig.add_trace(go.Bar(
        x=xs_p, y=labels, orientation="h", name=f"Année N-1 ({year - 1})",
        marker_color=PREV_COLOR, marker_line_width=0, opacity=0.85,
        hovertemplate="<b>Poste %{y}</b><br>Séjour N-1 : %{x:.2f} j<extra></extra>"))
    if ty:
        fig.add_trace(go.Scatter(
            x=tx, y=ty, mode="text", text=ts, textfont=dict(size=10, color=tc),
            showlegend=False, hoverinfo="skip"))
    fig.update_layout(
        height=max(330, 28 * len(order) + 110),
        barmode="group",
        xaxis_title="Durée moyenne de séjour (jours)",
        xaxis_rangemode="nonnegative",
        yaxis=dict(categoryorder="array", categoryarray=labels,
                   autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=8, r=95, t=8, b=8))
    return _apply_theme(fig), title


def fig_marchandise(frame: pd.DataFrame, year: int,
                    months: list[int],
                    marchandises: list[str] | None = None) -> tuple[go.Figure | None, str]:
    """③ Temps cumulé à quai par marchandise (donut, top 7 + Autres).
    Filtre marchandises : si une sélection est faite (sans « Toutes »),
    seules ces marchandises sont représentées."""
    title = "Temps à quai par marchandise" + _months_suffix(months)
    f = _period(frame, year, months)
    if f.empty:
        return None, title
    f = f.assign(cat=_cat(f, "marchandise_norm"))
    if marchandises and ALL_MARCHANDISES not in marchandises:
        sel = [m for m in marchandises if m and m != ALL_MARCHANDISES]
        f = f[f["cat"].isin(sel)]
    if f.empty:
        return None, title
    tot = f.groupby("cat")["quai_h"].sum().sort_values(ascending=False)
    if tot.empty:
        return None, title
    duree_totale = float(tot.sum())
    if duree_totale <= 0:
        return None, title
    top = tot.head(7)
    if len(tot) > 7:
        top = pd.concat([top, pd.Series({"Autres": tot.iloc[7:].sum()})])
    labels = top.index.astype(str).tolist()
    values = np.round(top.values, 1)
    colors = [COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(labels))]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.62, sort=False,
        marker=dict(colors=colors, line=dict(color="#08182a", width=2)),
        textinfo="percent", textposition="inside",
        insidetextorientation="horizontal",
        customdata=[f"{v:,.0f}" for v in values],
        hovertemplate="%{label}<br>%{customdata} h (%{percent})<extra></extra>"))
    fig.add_annotation(
        text=f"<b>{duree_totale:,.0f}</b><br>h à quai",
        x=0.5, y=0.5, showarrow=False, font=dict(size=15, color="#0B3A5B"))
    fig.update_layout(height=310, showlegend=True,
                      legend=dict(orientation="v", x=1.02, font=dict(size=11)))
    return _apply_theme(fig), title


def fig_type_navire(frame: pd.DataFrame, year: int,
                    months: list[int]) -> tuple[go.Figure | None, str]:
    """④ Type de navire : barres horizontales à dégradé (bleu → turquoise → ambre)."""
    data = sejour_by_type_navire(frame, year, months)
    title = "Séjour moyen par type de navire" + _months_suffix(months)
    if data is None or data.empty:
        return None, title
    g = data.head(12).iloc[::-1]
    vals = pd.to_numeric(g["sejour_moyen"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    vmin, vmax = float(vals.min()), float(vals.max())
    scale = [[0, "#3aa0ff"], [0.5, "#32d2a4"], [1, "#f2b84b"]]
    norm = 0.5 if vmax == vmin else (vals - vmin) / (vmax - vmin)
    colors = list(sample_colorscale(scale, norm.tolist()))
    fig = go.Figure(go.Bar(
        x=g["sejour_moyen"], y=g["type_navire_norm"].astype(str), orientation="h",
        marker_color=colors, marker_line_width=0,
        customdata=np.stack([
            g["escales"].astype(int).values,
            g.get("navires", pd.Series([0] * len(g))).astype(int).values,
        ], axis=-1),
        hovertemplate="<b>%{y}</b><br>Séjour moyen : %{x:.1f} h"
                      "<br>Escales : %{customdata[0]} · Navires : %{customdata[1]}"
                      "<extra></extra>"))
    fig.update_layout(height=max(300, 34 * len(g) + 90),
                      xaxis_title="Séjour moyen (h)")
    return _apply_theme(fig), title


def fig_operateur(frame: pd.DataFrame, year: int,
                  months: list[int]) -> tuple[go.Figure | None, str]:
    """⑤ Opérateur : colonnes verticales avec étiquettes (barres si trop de catégories)."""
    data = sejour_by_operateur(frame, year, months)
    title = "Séjour moyen par opérateur" + _months_suffix(months)
    if data is None or data.empty:
        return None, title
    g = data.head(10)
    if len(g) <= 8:
        fig = go.Figure(go.Bar(
            x=g["operateur_norm"].astype(str),
            y=pd.to_numeric(g["sejour_moyen"], errors="coerce"),
            orientation="v",
            text=g["sejour_moyen"].map(lambda v: f"{v:.1f}"),
            textposition="outside",
            marker_color=CUR_COLOR, marker_line_width=0,
            customdata=g["escales"].astype(int).values,
            hovertemplate="<b>%{x}</b><br>Séjour moyen : %{y:.1f} h"
                          "<br>Escales : %{customdata}<extra></extra>"))
        fig.update_layout(height=310, yaxis_title="Séjour moyen (h)",
                          yaxis_rangemode="nonnegative")
    else:
        g2 = g.iloc[::-1]
        fig = go.Figure(go.Bar(
            x=g2["sejour_moyen"], y=g2["operateur_norm"].astype(str),
            orientation="h",
            marker_color=CUR_COLOR, marker_line_width=0,
            customdata=g2["escales"].astype(int).values,
            hovertemplate="<b>%{y}</b><br>Séjour moyen : %{x:.1f} h"
                          "<br>Escales : %{customdata}<extra></extra>"))
        fig.update_layout(height=max(320, 34 * len(g2) + 90),
                          xaxis_title="Séjour moyen (h)")
    return _apply_theme(fig), title


def _classes_duree_jours(jours: pd.Series) -> tuple[list[str], list[int]]:
    """Classes de durée (en jours) adaptées au max réel : <0,5 j · 0,5–1 j ·
    1–2 j · 2–4 j · … · > X j."""
    dur = jours[jours >= 0].dropna()
    if dur.empty:
        return [], []
    maxd = float(dur.max())
    edges = [0.0, 0.5, 1.0, 2.0]
    while edges[-1] < maxd and len(edges) < 7:
        edges.append(edges[-1] * 2.0)
    fmt = lambda v: f"{v:g}".replace(".", ",")  # noqa: E731
    labels = [f"< {fmt(edges[1])} j"]
    for lo, hi in zip(edges[1:-1], edges[2:]):
        labels.append(f"{fmt(lo)} – {fmt(hi)} j")
    labels.append(f"> {fmt(edges[-1])} j")
    counts = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        if hi is None:
            counts.append(int((dur >= lo).sum()))
        else:
            counts.append(int(((dur >= lo) & (dur < hi)).sum()))
    return labels, counts


def fig_distribution(frame: pd.DataFrame, year: int,
                     nbins: int = 24) -> go.Figure | None:
    """⑥ Distribution des durées de séjour EN JOURS (quai_h / 24) par classe
    de durée — barres colorées de la plus courte à la plus longue."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return None
    f = f[f["year"] == year]
    if f.empty:
        return None
    f = f.assign(duree_jours=f["quai_h"] / 24.0)
    days = f["duree_jours"]
    labels, counts = _classes_duree_jours(days)
    if not labels:
        return None
    colors = [DUR_CLASS_COLORS[i % len(DUR_CLASS_COLORS)]
              for i in range(len(labels))]
    fig = go.Figure(go.Bar(
        x=labels, y=counts, marker_color=colors, marker_line_width=0,
        text=counts, textposition="auto",
        hovertemplate="<b>%{x}</b><br>Escales : %{y}<extra></extra>"))
    avg = float(days.mean())
    med = float(days.median())
    fig.add_annotation(
        text=f"Moyenne {avg:.1f} j · Médiane {med:.1f} j",
        x=0.98, y=1.02, xref="paper", yref="paper", showarrow=False,
        align="right", font=dict(size=11, color="#8f9bb3"))
    fig.update_layout(height=310,
                      xaxis_title="Durée à quai (jours)",
                      yaxis_title="Nombre d'escales")
    return _apply_theme(fig)


def fig_performance_poste(frame: pd.DataFrame, year: int,
                          months: list[int]) -> go.Figure | None:
    """⑦ Performance par poste : durée moyenne avec taille = nombre d'escales."""
    data = performance_by_poste(frame, year, months)
    if data.empty:
        return None
    g = data.head(12).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=g["sejour_moyen"], y=g["poste"].astype(str), orientation="h",
        marker_color=CUR_COLOR, marker_line_width=0,
        customdata=np.stack([
            g["navires"].astype(int).values,
            g["escales"].astype(int).values,
            g["tonnage"].values,
        ], axis=-1),
        hovertemplate="<b>Poste %{y}</b><br>Séjour moyen : %{x:.1f} h"
                      + "<br>Navires : %{customdata[0]}"
                      + "<br>Escales : %{customdata[1]}"
                      + "<br>Tonnage : %{customdata[2]:,.0f} t"
                      + "<extra></extra>"))
    fig.update_layout(height=max(320, 34 * len(g) + 90),
                      xaxis_title="Séjour moyen (h)")
    return _apply_theme(fig)


# ==================================================================
# INSIGHTS
# ==================================================================
def sejour_insights(frame: pd.DataFrame, year: int,
                    months: list[int]) -> list[str]:
    """Insights automatiques sur le séjour à quai."""
    f = _base(frame)
    if f.empty or "year" not in f.columns:
        return ["Aucune donnée de séjour à quai disponible pour cette année."]
    cur = f[f["year"] == year]
    prev = f[f["year"] == year - 1]
    if cur.empty:
        return ["Aucune donnée de séjour à quai disponible pour cette année."]

    avg = float(cur["quai_h"].mean())
    median = float(cur["quai_h"].median())
    max_val = float(cur["quai_h"].max())
    p90 = float(cur["quai_h"].quantile(0.90))
    n = len(cur)
    ships = int(cur["navire_name"].nunique()) if "navire_name" in cur.columns else 0

    insights = []
    insights.append(f"<b>Durée moyenne de séjour</b> : <b>{avg:.1f} h</b> "
                    f"(médiane {median:.1f} h) sur <b>{n}</b> escales "
                    f"et <b>{ships}</b> navires distincts.")

    if not prev.empty:
        prev_avg = float(prev["quai_h"].mean())
        if prev_avg > 0:
            var_pct = round(100 * (avg - prev_avg) / prev_avg, 1)
            direction = "augmenté" if var_pct > 0 else "diminué"
            insights.append(f"Évolution vs N-1 : <b>{direction} de {abs(var_pct):.1f} %</b> "
                            f"(N-1 : {prev_avg:.1f} h).")

    if max_val > avg * 2.5:
        insights.append(f"<b>Attention</b> : la durée maximale ({max_val:.1f} h) "
                        f"dépasse 2,5× la moyenne — escale potentiellement atypique.")

    if p90 > avg * 1.8:
        insights.append(f"Le P90 ({p90:.1f} h) est {100 * (p90 / avg - 1):.0f}% "
                        f"au-dessus de la moyenne — distribution asymétrique.")

    # Poste le plus long
    by_poste = sejour_by_poste(frame, year, months)
    if not by_poste.empty:
        top = by_poste.iloc[0]
        insights.append(f"Poste avec le séjour le plus long : <b>{top['poste_norm']}</b> "
                        f"({top['sejour_moyen']:.1f} h · {int(top['escales'])} escales).")

    # Poste le plus court
    if len(by_poste) > 1:
        bottom = by_poste.iloc[-1]
        insights.append(f"Poste avec le séjour le plus court : <b>{bottom['poste_norm']}</b> "
                        f"({bottom['sejour_moyen']:.1f} h · {int(bottom['escales'])} escales).")

    return insights
