# -*- coding: utf-8 -*-
"""Moteur de la carte « ⏳ Attente au mouillage » (dashboard Power BI).

Métrique centrale : attente_h = Sortie_Mouillage − Mouillage (heures).

RÈGLE D'ATTRIBUTION TEMPORELLE
    Chaque escale est affectée au mois / année de DÉBUT de son attente
    (date_mouillage). Toute la durée d'attente est comptée dans ce mois —
    JAMAIS répartie entre plusieurs mois.
    Repli (données incomplètes) : si date_mouillage absente, on retient la
    date de l'opération (colonne `date`), sinon l'année/mois préparés.

Indicateurs  : moyenne, médiane, P90, P95, maximum (heures).
Graphiques   : ① Évolution de l'attente moyenne par mois de début (N vs N-1)
               ② Distribution des durées d'attente par tranches fixes.
Aucune dépendance Streamlit ici — données + figures Plotly pures, testables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, _apply_theme)

# Tranches fixes de durée (heures) — bornes incluses à gauche.
BIN_EDGES = [0, 24, 48, 72, 120, 168, 240, np.inf]
BIN_LABELS = ["0 – 24 h", "24 – 48 h", "48 – 72 h", "72 – 120 h",
              "120 – 168 h", "168 – 240 h", "> 240 h"]

# Labels des widgets (défauts)
POSTE_ALL = "Tous les postes"
TYPE_ALL = "Tous les types"
NAVIRE_ALL = "Tous les navires"
OP_ALL = "Tous les opérateurs"
MARCH_ALL = "Toutes les marchandises"


# ==================================================================
# PRÉPARATION / ATTRIBUTION
# ==================================================================
def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Attribue chaque escale au mois/année de DÉBUT de son attente."""
    if frame is None or frame.empty or "attente_h" not in frame.columns:
        return pd.DataFrame()
    f = frame.copy()
    f["attente_h"] = pd.to_numeric(f["attente_h"], errors="coerce")
    f = f[f["attente_h"].notna() & (f["attente_h"] > 0)]
    if f.empty:
        return pd.DataFrame(columns=["att_year", "att_month"])

    start = (pd.to_datetime(f["date_mouillage"], errors="coerce")
             if "date_mouillage" in f.columns
             else pd.Series(pd.NaT, index=f.index))
    op = (pd.to_datetime(f["date"], errors="coerce")
          if "date" in f.columns
          else pd.Series(pd.NaT, index=f.index))
    best = start.fillna(op)
    year = best.dt.year
    month = best.dt.month
    if "year" in f.columns:
        year = year.fillna(pd.to_numeric(f["year"], errors="coerce"))
    if "month" in f.columns:
        month = month.fillna(pd.to_numeric(f["month"], errors="coerce"))

    f["att_year"] = year
    f["att_month"] = month
    f = f[f["att_year"].notna() & f["att_month"].notna()]
    f["att_year"] = f["att_year"].astype(int)
    f["att_month"] = f["att_month"].astype(int)
    f = f[f["att_month"].between(1, 12)]
    return f


def available_years(frame: pd.DataFrame) -> list[int]:
    f = prepare(frame)
    return sorted(f["att_year"].unique().tolist(),
                  reverse=True) if not f.empty else []


def available_months(frame: pd.DataFrame, year: int) -> list[int]:
    f = prepare(frame)
    if f.empty:
        return []
    return sorted(f.loc[f["att_year"] == year, "att_month"].unique().tolist())


def distinct(frame: pd.DataFrame, col: str) -> list[str]:
    """Valeurs distinctes réelles (non vides) d'une colonne."""
    if frame is None or frame.empty or col not in frame.columns:
        return []
    s = frame[col].fillna("").astype(str).str.strip()
    s = s[s != ""]
    return sorted(s.unique().tolist())


# ==================================================================
# FILTRES (cascade)
# ==================================================================
def _value(val) -> str | None:
    if val is None:
        return None
    s = str(val)
    if s.startswith(("Tous", "Toutes")):
        return None
    return s


def apply_dimensions(frame: pd.DataFrame, sel: dict) -> pd.DataFrame:
    """Applique uniquement les dimensions (poste/type/navire/opérateur/march.)."""
    for col, key in (("poste_norm", "poste"), ("type_navire_norm", "type_navire"),
                     ("navire_name", "navire"), ("operateur_norm", "operateur"),
                     ("marchandise_norm", "marchandise")):
        v = _value(sel.get(key))
        if v and col in frame.columns:
            frame = frame[frame[col].fillna("").astype(str) == v]
    return frame


def filtered(frame: pd.DataFrame, sel: dict) -> pd.DataFrame:
    """Rows de la période (année + mois de DÉBUT) + dimensions filtrées."""
    f = apply_dimensions(prepare(frame), sel)
    if f.empty:
        return f
    year = sel.get("year")
    if year is not None:
        f = f[f["att_year"] == int(year)]
    months = sel.get("months") or []
    if months:
        f = f[f["att_month"].isin([int(m) for m in months])]
    return f


def monthly_evol(frame: pd.DataFrame, sel: dict, year_target: int) -> pd.DataFrame:
    """Série mensuelle (moyenne/médiane/effectifs) pour une année cible.

    Dimensions filtrées identiques à la sélection ; attribution par le mois
    de DÉBUT de l'attente (att_year == year_target).
    """
    f = apply_dimensions(prepare(frame), sel)
    if f.empty:
        return pd.DataFrame(columns=["att_month", "moyenne", "mediane",
                                     "n", "navires"])
    f = f[f["att_year"] == int(year_target)]
    if f.empty:
        return pd.DataFrame(columns=["att_month", "moyenne", "mediane",
                                     "n", "navires"])
    months = sel.get("months") or []
    if months:
        f = f[f["att_month"].isin([int(m) for m in months])]
    if f.empty:
        return pd.DataFrame(columns=["att_month", "moyenne", "mediane",
                                     "n", "navires"])
    g = f.groupby("att_month")["attente_h"].agg(
        moyenne="mean", mediane="median", n="count").reset_index()
    nv = f.groupby("att_month")["navire_name"].nunique() \
        if "navire_name" in f.columns else pd.Series(dtype=int)
    g = g.merge(nv.rename("navires"), on="att_month", how="left")
    g["navires"] = g["navires"].fillna(0).astype(int)
    return g


# ==================================================================
# KPI
# ==================================================================
def _safe(v) -> float | None:
    if v is None or pd.isna(v):
        return None
    return float(v)


def kpi_stats(f: pd.DataFrame) -> dict:
    """Statistiques d'attente : moyenne, médiane, P90, P95, maximum."""
    if f is None or f.empty or "attente_h" not in f.columns:
        return {"moyenne": None, "mediane": None, "p90": None, "p95": None,
                "maximum": None, "count": 0, "escales": 0, "navires": 0}
    v = f["attente_h"]
    return {
        "moyenne": _safe(v.mean()),
        "mediane": _safe(v.median()),
        "p90": _safe(v.quantile(0.90)),
        "p95": _safe(v.quantile(0.95)),
        "maximum": _safe(v.max()),
        "count": int(len(v)),
        "escales": int(f["escale_key"].nunique()) if "escale_key" in f.columns else int(len(v)),
        "navires": int(f["navire_name"].nunique()) if "navire_name" in f.columns else 0,
    }


# ==================================================================
# DISTRIBUTION PAR TRANCHES
# ==================================================================
def distribution_data(f: pd.DataFrame) -> pd.DataFrame:
    """Effectifs par tranche de durée (colonne/période déjà filtrées)."""
    cols = ["tranche", "escales", "part_pct"]
    if f is None or f.empty or "attente_h" not in f.columns:
        return pd.DataFrame(columns=cols)
    cats = pd.cut(f["attente_h"], bins=BIN_EDGES, right=False, labels=BIN_LABELS)
    counts = cats.value_counts().reindex(BIN_LABELS).fillna(0)
    total = float(counts.sum()) or 1.0
    return pd.DataFrame({
        "tranche": BIN_LABELS,
        "escales": counts.astype(int).values,
        "part_pct": (counts.values / total * 100).round(1),
    })


def _bin_index(value: float, edges: list[float]) -> int:
    for i in range(1, len(edges)):
        if value < edges[i]:
            return i - 1
    return len(edges) - 2


# ==================================================================
# FIGURES
# ==================================================================
def _apply_dimensions_sans(frame: pd.DataFrame, sel: dict,
                           skip: str | None = None) -> pd.DataFrame:
    """Applique les dimensions sauf `skip` (pour une analyse indépendante)."""
    for col, key in (("poste_norm", "poste"), ("type_navire_norm", "type_navire"),
                     ("navire_name", "navire"), ("operateur_norm", "operateur"),
                     ("marchandise_norm", "marchandise")):
        if key == skip:
            continue
        v = _value(sel.get(key))
        if v and col in frame.columns:
            frame = frame[frame[col].fillna("").astype(str) == v]
    return frame


def filtered_sans(frame: pd.DataFrame, sel: dict,
                  skip: str | None = None) -> pd.DataFrame:
    """Période (année + mois de début) + dimensions filtrées, sans `skip`."""
    f = _apply_dimensions_sans(prepare(frame), sel, skip)
    if f.empty:
        return f
    year = sel.get("year")
    if year is not None:
        f = f[f["att_year"] == int(year)]
    months = sel.get("months") or []
    if months:
        f = f[f["att_month"].isin([int(m) for m in months])]
    return f


def marchandise_stats(f: pd.DataFrame) -> pd.DataFrame:
    """Attente moyenne + nombre d'escales par marchandise (période filtrée)."""
    cols = ["marchandise", "attente_moyenne", "escales"]
    if f is None or f.empty or "marchandise_norm" not in f.columns:
        return pd.DataFrame(columns=cols)
    work = f[f["marchandise_norm"].fillna("").astype(str).str.strip() != ""]
    if work.empty:
        return pd.DataFrame(columns=cols)
    g = work.groupby("marchandise_norm")["attente_h"].agg(
        attente_moyenne="mean", escales="count").reset_index()
    g = g.rename(columns={"marchandise_norm": "marchandise"})
    g["attente_moyenne"] = g["attente_moyenne"].round(1)
    g["escales"] = g["escales"].astype(int)
    return g.sort_values("attente_moyenne", ascending=True)


def marchandise_options(frame: pd.DataFrame, sel: dict) -> list[str]:
    """Marchandises distinctes (non vides) de la période filtrée, triées."""
    f = filtered_sans(frame, sel, skip="marchandise")
    data = marchandise_stats(f)
    return data["marchandise"].astype(str).tolist() if not data.empty else []


def fig_marchandise(frame: pd.DataFrame, sel: dict,
                    marchandises: list[str] | None = None) -> go.Figure | None:
    """③ Attente par marchandise : durée moyenne (b) + effectifs (escales).

    ``marchandises`` : liste des marchandises à afficher. Vide / None → toutes
    les marchandises ; sinon uniquement celles sélectionnées.
    """
    f = filtered_sans(frame, sel, skip="marchandise")
    data = marchandise_stats(f)
    if data.empty or data["escales"].sum() == 0:
        return None
    if marchandises:
        data = data[data["marchandise"].astype(str).isin(
            [str(m) for m in marchandises])]
        if data.empty or data["escales"].sum() == 0:
            return None

    # Conversion heures → jours (données réelles uniquement)
    data = data.copy()
    data["attente_jours"] = data["attente_moyenne"] / 24.0
    avg_jours = float(f["attente_h"].mean()) / 24.0

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=data["attente_jours"], y=data["marchandise"],
        orientation="h",
        marker_color=["#62ddff"],
        marker_line_width=0, opacity=0.9,
        customdata=np.stack([data["escales"].values], axis=-1),
        hovertemplate="<b>%{y}</b><br>"
                      "Attente moyenne : %{x:.1f} j<br>"
                      "Escales : %{customdata[0]}<extra></extra>"))
    fig.add_vline(x=avg_jours, line_dash="dash",
                  line_color="#2dd4bf", line_width=2)
    fig.add_annotation(xref="paper", x=1.0, yref="paper", y=1.12, xanchor="right",
                       text=f"■ Attente moyenne globale : {avg_jours:.1f} j",
                       showarrow=False, font=dict(color="#2dd4bf", size=12))
    fig.update_layout(
        height=380, title="Attente par marchandise",
        xaxis_title="Attente moyenne (jours)", yaxis_title=None,
        margin=dict(t=60))
    return _apply_theme(fig)


def fig_evolution(frame: pd.DataFrame, sel: dict) -> go.Figure | None:
    """① Évolution de l'attente moyenne par mois de DÉBUT — N vs N-1."""
    year = int(sel["year"])
    cur = monthly_evol(frame, sel, year)
    prev = monthly_evol(frame, sel, year - 1)
    fig = go.Figure()

    def _trace(data: pd.DataFrame, label: str, trace_year: int,
               color: str, dash: str | None):
        if data is None or data.empty or data["n"].sum() == 0:
            return
        months = [MONTHS_FR[int(m) - 1] for m in data["att_month"]]
        custom = np.stack([
            np.full(len(data), trace_year),
            data["n"].astype(int).values,
            data["mediane"].round(1).values,
            data["navires"].astype(int).values,
        ], axis=-1)
        fig.add_trace(go.Scatter(
            x=months, y=data["moyenne"].round(2), name=label,
            mode="lines+markers",
            line=dict(color=color, width=3 if dash is None else 2,
                      dash=dash or "solid"),
            customdata=custom,
            hovertemplate="<b>%{x} %{customdata[0]}</b><br>"
                          "Attente moyenne : %{y:.1f} h<br>"
                          "Médiane : %{customdata[2]:.1f} h<br>"
                          "Escales : %{customdata[1]} · "
                          "Navires : %{customdata[3]}<extra></extra>"))

    _trace(cur, f"Année N ({year})", year, CUR_COLOR, None)
    _trace(prev, f"Année N-1 ({year - 1})", year - 1, PREV_COLOR, "dot")
    if not fig.data:
        return None
    fig.update_layout(
        height=380,
        title="Évolution de l'attente moyenne selon le mois de début d'attente",
        yaxis_title="Attente moyenne (h)",
        yaxis_rangemode="nonnegative",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=50))
    return _apply_theme(fig)


def fig_distribution(frame: pd.DataFrame, sel: dict) -> go.Figure | None:
    """② Distribution des durées d'attente par tranches fixes."""
    f = filtered(frame, sel)
    if f.empty:
        return None
    data = distribution_data(f)
    if data["escales"].sum() == 0:
        return None
    fig = go.Figure(go.Bar(
        x=data["tranche"], y=data["escales"],
        marker_color=[COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(data))],
        marker_line_width=0, opacity=0.9,
        customdata=np.stack([data["part_pct"].values], axis=-1),
        hovertemplate="<b>Tranche : %{x}</b><br>"
                      "Nombre d'escales : %{y}<br>"
                      "Part du total : %{customdata[0]:.1f} %<extra></extra>"))

    v = f["attente_h"]
    med, p90 = float(v.median()), float(v.quantile(0.90))
    fig.add_vline(x=_bin_index(med, BIN_EDGES), line_dash="dash",
                  line_color="#2dd4bf", line_width=2)
    fig.add_vline(x=_bin_index(p90, BIN_EDGES), line_dash="dash",
                  line_color="#f2b84b", line_width=2)
    fig.add_annotation(xref="paper", x=0.0, yref="paper", y=1.12, xanchor="left",
                       text=f"■ Médiane : {med:.1f} h", showarrow=False,
                       font=dict(color="#2dd4bf", size=12))
    fig.add_annotation(xref="paper", x=1.0, yref="paper", y=1.12, xanchor="right",
                       text=f"■ P90 : {p90:.1f} h", showarrow=False,
                       font=dict(color="#f2b84b", size=12))
    fig.update_layout(
        height=380, title="Distribution des durées d'attente",
        xaxis_title=None, yaxis_title="Nombre d'escales",
        margin=dict(t=60))
    return _apply_theme(fig)