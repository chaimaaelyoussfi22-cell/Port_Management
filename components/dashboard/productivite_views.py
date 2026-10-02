# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Productivité » (dashboard Power BI).

Métrique port : productivité = Σ Tonnage ÷ Σ Durée de séjour au port (t/h),
calculée mois par mois (ou jour par jour) sur les données réelles de la
période concernée — aucune valeur inventée pour un mois sans données.

Métrique poste : productivité du poste = Σ Tonnage affecté ÷ Σ Durée du poste,
avec la règle de répartition officielle : tonnage_attribué = tonnage / N postes.
Le référentiel officiel (23 postes) est affiché dans son ordre métier exact —
aucun tri, aucun ajout ; les postes sans activité apparaissent à 0 t/h.

Aucune dépendance Streamlit ici — données + figures Plotly pures, testables.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import (
    MONTHS_FR, load_poste_segments)
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, _apply_theme)
from components.dashboard.sejour_views import (
    ALL_POSTES, POSTE_REFERENTIEL, _poste_key, _poste_label)


# ==================================================================
# PRÉPARATION
# ==================================================================
def _base(frame: pd.DataFrame, duree_col: str = "port_h") -> pd.DataFrame:
    """Lignes exploitables : durée (port ou quai) > 0, tonnage ≥ 0, mois/année présents."""
    required = {duree_col, "tonnage", "month", "year"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    f = frame.copy()
    f[duree_col] = pd.to_numeric(f[duree_col], errors="coerce")
    f["tonnage"] = pd.to_numeric(f["tonnage"], errors="coerce")
    f = f[(f[duree_col].notna()) & (f[duree_col] > 0)
           & (f["tonnage"].notna()) & (f["tonnage"] >= 0)
           & f["month"].notna() & f["year"].notna()]
    if f.empty:
        return pd.DataFrame()
    f["month"] = f["month"].astype(int)
    f["year"] = f["year"].astype(int)
    return f


def _base_port(frame: pd.DataFrame) -> pd.DataFrame:
    """Métrique port : durée de séjour au port (port_h)."""
    return _base(frame, "port_h")


def _base_quai(frame: pd.DataFrame) -> pd.DataFrame:
    """Découpage par poste : durée à quai (quai_h) pour les segments."""
    return _base(frame, "quai_h")


def available_years(frame: pd.DataFrame) -> list[int]:
    f = _base_quai(frame)
    return sorted(f["year"].unique().tolist(), reverse=True) if not f.empty else []


def available_months(frame: pd.DataFrame, year: int) -> list[int]:
    """Mois de l'année disposant réellement de données port exploitables."""
    f = _base_port(frame)
    f = f[f["year"] == year]
    return sorted(int(m) for m in f["month"].unique().tolist()) if not f.empty else []


# ==================================================================
# KPI
# ==================================================================
def kpi_block(frame: pd.DataFrame, year: int) -> dict:
    """KPI : productivité globale du port, volume, durée séjour port, évolution."""
    empty = {"port_prod": 0.0, "volume": 0.0, "duree_port": 0.0,
             "evolution": None, "escales": 0, "ships": 0, "count": 0}
    f = _base_port(frame)
    if f.empty:
        return empty
    cur = f[f["year"] == year]
    prev = f[f["year"] == year - 1]
    if cur.empty:
        return empty
    vol = float(cur["tonnage"].sum())
    duree = float(cur["port_h"].sum())
    port_prod = round(vol / duree, 1) if duree > 0 else 0.0
    ships = int(cur["navire_name"].nunique()) if "navire_name" in cur.columns else 0
    escales = int(cur["escale_key"].nunique()) if "escale_key" in cur.columns else len(cur)
    count = len(cur)

    prev_vol = float(prev["tonnage"].sum()) if not prev.empty else 0.0
    prev_duree = float(prev["port_h"].sum()) if not prev.empty else 0.0
    prev_prod = round(prev_vol / prev_duree, 1) if prev_duree > 0 else 0.0
    evolution = (round(100 * (port_prod - prev_prod) / prev_prod, 1)
                 if prev_prod > 0 else None)

    return {"port_prod": port_prod, "volume": vol, "duree_port": round(duree, 1),
            "evolution": evolution, "escales": escales, "ships": ships, "count": count}


# ==================================================================
# PRODUCTIVITÉ PORT — SÉRIES TEMPORELLES
# ==================================================================
def port_prod_monthly(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    """Productivité mensuelle du port : Σ tonnage ÷ Σ durée séjour port, par mois."""
    cols = ["month", "prod", "tonnage", "duree"]
    f = _base_port(frame)
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=cols)
    g = f.groupby("month").agg(
        tonnage=("tonnage", "sum"), duree=("port_h", "sum")).reset_index()
    g["prod"] = g.apply(
        lambda r: round(r["tonnage"] / r["duree"], 1) if r["duree"] > 0 else 0.0, axis=1)
    return g.sort_values("month").reset_index(drop=True)


def port_prod_daily(frame: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """Productivité journalière du port pour un mois donné (année N ou N-1)."""
    cols = ["day", "label", "prod", "tonnage", "duree"]
    f = _base_port(frame)
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f[(f["year"] == year) & (f["month"] == month)]
    if f.empty or "date" not in f.columns:
        return pd.DataFrame(columns=cols)
    d = pd.to_datetime(f["date"], errors="coerce")
    f = f[d.notna()].copy()
    f["day"] = d[d.notna()].dt.normalize()
    g = f.groupby("day").agg(
        tonnage=("tonnage", "sum"), duree=("port_h", "sum")).reset_index()
    g["prod"] = g.apply(
        lambda r: round(r["tonnage"] / r["duree"], 1) if r["duree"] > 0 else 0.0, axis=1)
    g = g.sort_values("day").reset_index(drop=True)
    g["label"] = g["day"].dt.strftime("%d/%m")
    g["day_label"] = g["day"].dt.strftime("%m-%d")
    return g[["day_label", "label", "prod", "tonnage", "duree"]].rename(
        columns={"day_label": "day"})


# ==================================================================
# PRODUCTIVITÉ PAR POSTE (règle de répartition officielle)
# ==================================================================
def _poste_segments(frame: pd.DataFrame, year: int,
                    months: list[int] | None = None) -> pd.DataFrame:
    """Segments d'occupation réels des postes pour l'année N (mois optionnels)."""
    f = _base_quai(frame)
    if f.empty:
        return pd.DataFrame()
    f = f[f["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame()
    return load_poste_segments(f)


def poste_prod_data(frame: pd.DataFrame, year: int,
                    months: list[int] | None = None) -> pd.DataFrame:
    """Productivité par poste — référentiel complet, ordre métier exact.

    Tonnage affecté selon la règle officielle (tonnage / nombre de postes),
    durée = occupation réelle du poste (segments, chevauchements dédupliqués).
    Mois optionnels : agrégation restreinte à la période voulue (vide = année).
    Les postes sans activité apparaissent à 0 t/h.
    """
    cols = ["poste", "prod", "tonnage_attr", "duree", "escales"]
    seg = _poste_segments(frame, year, months)
    if seg.empty or "poste_norm" not in seg.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for key in POSTE_REFERENTIEL:
        label = _poste_label(key)
        g = seg[seg["poste_norm"] == key]
        tonnage = float(g["tonnage_attr"].sum()) if not g.empty else 0.0
        dur = float(g["seg_dur_h"].clip(lower=0).sum()) if not g.empty else 0.0
        prod = round(tonnage / dur, 1) if dur > 0 else 0.0
        escales = int(g["escale_key"].nunique()) if (
            not g.empty and "escale_key" in g.columns) else 0
        rows.append({"poste": label, "prod": prod,
                     "tonnage_attr": round(tonnage, 0),
                     "duree": round(dur, 1), "escales": escales})
    return pd.DataFrame(rows, columns=cols)


def poste_prod_monthly(frame: pd.DataFrame, year: int,
                       postes: list[str]) -> pd.DataFrame:
    """Évolution mensuelle (année N) de la productivité des postes sélectionnés.

    Seuls les mois réellement présents sont émis (aucune valeur inventée).
    postes = libellés d'affichage ; si vide, agrégat « Tous les postes » émis
    (même métrique : Σ tonnage affecté ÷ Σ durée du poste).
    """
    cols = ["poste", "month", "prod"]
    seg = _poste_segments(frame, year)
    if seg.empty or "poste_norm" not in seg.columns:
        return pd.DataFrame(columns=cols)
    keys = [_poste_key(p) for p in postes] if postes else None
    if keys:
        seg = seg[seg["poste_norm"].isin(keys)]
    if seg.empty:
        return pd.DataFrame(columns=cols)
    if keys:
        g = seg.groupby(["poste_norm", "month"]).agg(
            tonnage=("tonnage_attr", "sum"), duree=("seg_dur_h", "sum")).reset_index()
        g["poste"] = g["poste_norm"].map(_poste_label)
    else:
        g = seg.groupby("month").agg(
            tonnage=("tonnage_attr", "sum"), duree=("seg_dur_h", "sum")).reset_index()
        g["poste"] = ALL_POSTES
    g["prod"] = g.apply(
        lambda r: round(r["tonnage"] / r["duree"], 1) if r["duree"] > 0 else 0.0, axis=1)
    return g[["poste", "month", "prod"]].sort_values("month").reset_index(drop=True)


# ==================================================================
# FIGURES — PRODUCTIVITÉ GLOBALE DU PORT
# ==================================================================
def _fig_port_monthly(frame: pd.DataFrame, year: int) -> tuple[go.Figure | None, str]:
    """Productivité mensuelle du port — barres (mois réellement présents)."""
    title = "Productivité mensuelle"
    data = port_prod_monthly(frame, year)
    data = data[data["prod"] > 0]
    if data.empty:
        return None, title
    labels = [MONTHS_FR[int(m) - 1] for m in data["month"]]
    fig = go.Figure(go.Bar(
        x=labels, y=data["prod"],
        marker_color=[CUR_COLOR] * len(data),
        text=[f"{p:.0f}" for p in data["prod"]],
        textposition="outside",
        customdata=np.stack([data["tonnage"].values, data["duree"].values], axis=-1),
        hovertemplate="<b>%{x}</b><br>"
                      "Productivité : %{y:.1f} t/h<br>"
                      "Volume : %{customdata[0]:,.0f} T<br>"
                      "Durée séjour port : %{customdata[1]:,.0f} h"
                      + "<extra></extra>"))
    fig.update_layout(height=380, yaxis_title="Productivité (t/h)",
                      yaxis_rangemode="nonnegative")
    return _apply_theme(fig), title


def _fig_port_daily(frame: pd.DataFrame, year: int,
                    month: int) -> tuple[go.Figure | None, str]:
    """Productivité journalière du port (mois donné) — barres."""
    title = "Productivité journalière"
    data = port_prod_daily(frame, year, month)
    data = data[data["prod"] > 0]
    if data.empty:
        return None, title
    fig = go.Figure(go.Bar(
        x=data["day"], y=data["prod"],
        marker_color=[CUR_COLOR] * len(data),
        text=[f"{p:.0f}" for p in data["prod"]],
        textposition="outside",
        customdata=np.stack([
            data["label"].values,
            data["tonnage"].values,
            data["duree"].values,
        ], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>"
                      "Productivité : %{y:.1f} t/h<br>"
                      "Volume : %{customdata[1]:,.0f} T<br>"
                      "Durée séjour port : %{customdata[2]:,.0f} h"
                      + "<extra></extra>"))
    fig.update_layout(height=380, yaxis_title="Productivité (t/h)",
                      yaxis_rangemode="nonnegative")
    return _apply_theme(fig), title


def _fig_evolution(frame: pd.DataFrame, year: int, granularity: str,
                   month: int) -> go.Figure | None:
    """Évolution de la productivité du port N vs N-1 (mensuelle ou journalière)."""
    fig = go.Figure()

    def _trace(yr: int, name: str, color: str, dash: str | None):
        if granularity == "Par jour":
            s = port_prod_daily(frame, yr, month)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=s["day"], y=s["prod"], name=name,
                mode="lines+markers" if len(s) < 200 else "lines",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                customdata=s["label"].tolist(),
                hovertemplate="%{customdata}<br>%{y:.1f} t/h<extra>" + name + "</extra>"))
        else:
            s = port_prod_monthly(frame, yr)
            if s.empty:
                return
            fig.add_trace(go.Scatter(
                x=[MONTHS_FR[int(m) - 1] for m in s["month"]], y=s["prod"],
                name=name, mode="lines+markers",
                line=dict(color=color, width=3 if dash is None else 2,
                          dash=dash or "solid"),
                hovertemplate="%{x}<br>%{y:.1f} t/h<extra>" + name + "</extra>"))

    _trace(year, f"N ({year})", CUR_COLOR, None)
    _trace(year - 1, f"N-1 ({year - 1})", PREV_COLOR, "dot")
    if not fig.data:
        return None
    fig.update_layout(
        height=380, yaxis_title="Productivité (t/h)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if granularity == "Par mois" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


# ==================================================================
# FIGURES — PRODUCTIVITÉ PAR POSTE
# ==================================================================
def _months_suffix(months: list[int] | None) -> str:
    if not months:
        return " · toute l'année"
    return " · " + ", ".join(MONTHS_FR[int(m) - 1] for m in sorted(months))


def _fig_poste(frame: pd.DataFrame, year: int, months: list[int],
               postes: list[str]) -> tuple[go.Figure | None, str]:
    """Productivité par poste — barres verticales (référentiel complet)."""
    title = "Productivité par poste" + _months_suffix(months)
    data = poste_prod_data(frame, year, months)
    if postes:
        data = data[data["poste"].isin(postes)]
    if data.empty:
        return None, title
    fig = go.Figure(go.Bar(
        x=data["poste"].astype(str), y=data["prod"],
        marker_color=CUR_COLOR,
        marker_line_width=0,
        text=[f"{p:.0f}" if p > 0 else None for p in data["prod"]],
        textposition="outside",
        customdata=np.stack([
            data["escales"].astype(int).values,
            data["tonnage_attr"].values,
            data["duree"].values,
        ], axis=-1),
        hovertemplate="<b>%{x}</b><br>"
                      "Productivité : %{y:.1f} t/h<br>"
                      "Escales : %{customdata[0]}<br>"
                      "Volume attribué : %{customdata[1]:,.0f} T<br>"
                      "Durée du poste : %{customdata[2]:,.0f} h"
                      + "<extra></extra>"))
    fig.update_layout(
        height=400, yaxis_title="Productivité (t/h)",
        yaxis_rangemode="nonnegative")
    fig.update_xaxes(tickangle=-45, automargin=True)
    return _apply_theme(fig), title


def _fig_poste_evolution(frame: pd.DataFrame, year: int,
                         postes: list[str]) -> tuple[go.Figure | None, str]:
    """Évolution mensuelle de la productivité par poste — une série par poste."""
    title = "Évolution de la productivité par poste"
    data = poste_prod_monthly(frame, year, postes)
    if data.empty:
        return None, title
    fig = go.Figure()
    if postes:
        for i, p in enumerate(postes):
            s = data[data["poste"] == p].sort_values("month")
            if s.empty:
                continue
            fig.add_trace(go.Scatter(
                x=[MONTHS_FR[int(m) - 1] for m in s["month"]],
                y=s["prod"], name=p, mode="lines+markers",
                line=dict(color=COLOR_SEQ[i % len(COLOR_SEQ)], width=2),
                hovertemplate="%{x}<br>%{y:.1f} t/h<extra>" + p + "</extra>"))
    else:
        s = data.sort_values("month")
        fig.add_trace(go.Scatter(
            x=[MONTHS_FR[int(m) - 1] for m in s["month"]],
            y=s["prod"], name=ALL_POSTES, mode="lines+markers",
            line=dict(color=CUR_COLOR, width=3),
            hovertemplate="%{x}<br>%{y:.1f} t/h<extra>" + ALL_POSTES + "</extra>"))
    if not fig.data:
        return None, title
    fig.update_layout(
        height=400, xaxis_title="Mois", yaxis_title="Productivité (t/h)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig), title