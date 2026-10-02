# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse du séjour au port » (dashboard Power BI).

Métrique centrale : durée de séjour au port (port_h) = Appareille_Port − Arrivee_Rade.
Aucune dépendance Streamlit ici — données + figures Plotly pures, testables.

Visualisations :
  ① Évolution du séjour moyen N vs N-1
  ② Séjour moyen par marchandise
  ③ Séjour moyen par opérateur
  ④ Tonnage vs durée de séjour (scatter)
  ⑤ Distribution des durées (histogramme)
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, UNSPECIFIED, _apply_theme)

METRIC = "port_h"
DELTA_BINS = [
    (0, 1, "0–1 j"),
    (1, 2, "1–2 j"),
    (2, 3, "2–3 j"),
    (3, 5, "3–5 j"),
    (5, 7, "5–7 j"),
    (7, float("inf"), ">7 j"),
]


# ==================================================================
# PRÉPARATION
# ==================================================================
def _base(frame: pd.DataFrame) -> pd.DataFrame:
    """Lignes exploitables : port_h > 0 + année/mois présents."""
    required = {METRIC, "month", "year"}
    if frame is None or frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    f = frame.copy()
    f[METRIC] = pd.to_numeric(f[METRIC], errors="coerce")
    f = f[(f[METRIC].notna()) & (f[METRIC] > 0)
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


# ==================================================================
# KPI
# ==================================================================
def kpi_block(frame: pd.DataFrame, year: int) -> dict:
    """KPI du séjour au port : moyenne, médiane, max, navires uniques, évolution."""
    f = _base(frame)
    if f.empty:
        return {"avg": 0.0, "median": 0.0, "max": 0.0, "ships": 0,
                "prev_avg": 0.0, "evolution": None, "count": 0}
    cur = f[f["year"] == year]
    prev = f[f["year"] == year - 1]
    if cur.empty:
        return {"avg": 0.0, "median": 0.0, "max": 0.0, "ships": 0,
                "prev_avg": 0.0, "evolution": None, "count": 0}
    avg = round(float(cur[METRIC].mean()), 1)
    median = round(float(cur[METRIC].median()), 1)
    max_val = round(float(cur[METRIC].max()), 1)
    ships = int(cur["navire_name"].nunique()) if "navire_name" in cur.columns else 0
    count = len(cur)
    prev_avg = round(float(prev[METRIC].mean()), 1) if not prev.empty else 0.0
    evolution = (round(100 * (avg - prev_avg) / prev_avg, 1)
                 if prev_avg > 0 else None)
    return {"avg": avg, "median": median, "max": max_val, "ships": ships,
            "prev_avg": prev_avg, "evolution": evolution, "count": count}


# ==================================================================
# AGRÉGATS TEMPORELS
# ==================================================================
def port_monthly(frame: pd.DataFrame, year: int) -> pd.Series:
    """Séjour moyen au port par mois — uniquement les mois avec données."""
    f = _base(frame)
    if f.empty:
        return pd.Series(dtype=float)
    f = f[f["year"] == year]
    if f.empty:
        return pd.Series(dtype=float)
    means = f.groupby("month")[METRIC].mean()
    return means.round(2)


def port_daily(frame: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    f = _base(frame)
    if f.empty:
        return pd.DataFrame(columns=["mmdd", "label", "sejour"])
    f = f[(f["year"] == year) & (f["month"] == month)]
    if f.empty or "date" not in f.columns:
        return pd.DataFrame(columns=["mmdd", "label", "sejour"])
    d = pd.to_datetime(f["date"], errors="coerce")
    f = f[d.notna()]
    f["day"] = d[d.notna()].dt.normalize()
    g = f.groupby("day")[METRIC].mean().sort_index()
    idx = g.index
    return pd.DataFrame({
        "mmdd": idx.strftime("%m-%d"),
        "label": idx.strftime("%d/%m"),
        "sejour": g.round(2).values,
    })


# ==================================================================
# AGRÉGATS PAR CATÉGORIE
# ==================================================================
def port_by_category(frame: pd.DataFrame, year: int, months: list[int],
                     col: str) -> pd.DataFrame:
    f = _base(frame)
    if f.empty:
        return pd.DataFrame(columns=[col, "sejour_moyen", "escales", "navires"])
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=[col, "sejour_moyen", "escales", "navires"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=[col, "sejour_moyen", "escales", "navires"])
    f = f.assign(cat=_cat(f, col))
    g = f.groupby("cat").agg(
        sejour_moyen=(METRIC, "mean"),
        escales=("escale_key", "nunique"),
        navires=("navire_name", "nunique"),
    ).sort_values("sejour_moyen", ascending=False).reset_index()
    g["sejour_moyen"] = g["sejour_moyen"].round(2)
    return g.rename(columns={"cat": col})


# ==================================================================
# SCATTER & DISTRIBUTION
# ==================================================================
def port_scatter_data(frame: pd.DataFrame, year: int,
                      months: list[int]) -> pd.DataFrame:
    f = _base(frame)
    if f.empty:
        return pd.DataFrame()
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame()
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame()
    cols = [METRIC, "tonnage", "navire_name"]
    for c in ["marchandise_norm", "type_navire_norm", "operateur_norm"]:
        if c in f.columns:
            cols.append(c)
    out = f[[c for c in cols if c in f.columns]].copy()
    out[METRIC] = pd.to_numeric(out[METRIC], errors="coerce")
    out["tonnage"] = pd.to_numeric(out.get("tonnage", pd.Series(dtype=float)),
                                   errors="coerce")
    out = out.dropna(subset=[METRIC, "tonnage"])
    out["date_label"] = ""
    if "date" in f.columns:
        dt = pd.to_datetime(f["date"], errors="coerce")
        out["date_label"] = dt.dt.strftime("%d/%m/%Y").fillna("")
    return out


def port_distribution_data(frame: pd.DataFrame, year: int,
                           months: list[int]) -> pd.DataFrame:
    f = _base(frame)
    if f.empty:
        return pd.DataFrame(columns=["interval", "count"])
    f = f[f["year"] == year]
    if f.empty:
        return pd.DataFrame(columns=["interval", "count"])
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return pd.DataFrame(columns=["interval", "count"])
    hours = f[METRIC].dropna()
    hours = hours[hours > 0]
    if hours.empty:
        return pd.DataFrame(columns=["interval", "count"])
    days_val = hours / 24.0
    bins_edges = [b[0] for b in DELTA_BINS] + [DELTA_BINS[-1][1]]
    cats = pd.cut(days_val, bins=bins_edges, right=False,
                  labels=[b[2] for b in DELTA_BINS])
    counts = cats.value_counts().reindex([b[2] for b in DELTA_BINS], fill_value=0)
    return pd.DataFrame({"interval": counts.index.tolist(),
                         "count": counts.values.tolist()})


# ==================================================================
# FIGURES
# ==================================================================
def _months_suffix(months: list[int]) -> str:
    from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
    return (" · " + ", ".join(MOIS_NOMS[m - 1] for m in sorted(months))
            if months else " · toute l'année")


def _fig_evolution(frame: pd.DataFrame, year: int,
                   granularity: str, month: int) -> go.Figure | None:
    """① Évolution N vs N-1 — courbes séjour moyen (mois ou jour)."""
    fig = go.Figure()

    def _trace(year_target: int, name: str, color: str, dash: str | None):
        if granularity == "Par jour":
            s = port_daily(frame, year_target, month)
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
            s = port_monthly(frame, year_target)
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
        height=400, yaxis_title="Durée moyenne de séjour (h)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if granularity == "Par mois" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


def _horizontal_bars(data: pd.DataFrame, col: str, value_col: str,
                     title: str, unit: str = "h",
                     height_min: int = 300) -> go.Figure | None:
    if data is None or data.empty:
        return None
    total = max(int(data["escales"].sum()), 1)
    g = data.head(15).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=g[value_col], y=g[col].astype(str), orientation="h",
        marker_color=CUR_COLOR, marker_line_width=0,
        customdata=np.stack([
            g["escales"].astype(int).values,
            (g["escales"] / total * 100).round(1).values,
            g.get("navires", pd.Series([0] * len(g))).astype(int).values,
        ], axis=-1),
        hovertemplate="%{y}<br>Séjour moyen : %{x:.1f} " + unit
                      + "<br>Escales : %{customdata[0]} (%{customdata[1]} %)"
                      + "<br>Navires : %{customdata[2]}"
                      + "<extra></extra>"))
    fig.update_layout(height=max(height_min, 34 * len(g) + 90),
                      xaxis_title=f"Séjour moyen ({unit})")
    return _apply_theme(fig)


def _fig_by_category(frame: pd.DataFrame, year: int, months: list[int],
                     col: str) -> tuple[go.Figure | None, str]:
    data = port_by_category(frame, year, months, col)
    label = col.replace("_norm", "").replace("_", " ").title()
    title = f"Séjour moyen par {label}" + _months_suffix(months)
    fig = _horizontal_bars(data, col, "sejour_moyen", title)
    return fig, title


def _fig_scatter(frame: pd.DataFrame, year: int,
                 months: list[int]) -> tuple[go.Figure | None, str]:
    data = port_scatter_data(frame, year, months)
    title = "Tonnage vs durée de séjour" + _months_suffix(months)
    if data.empty:
        return None, title
    hover_cols = []
    for c in ["navire_name", "tonnage", METRIC, "marchandise_norm",
              "type_navire_norm", "operateur_norm", "date_label"]:
        if c in data.columns:
            hover_cols.append(c)
    fig = px.scatter(
        data, x="tonnage", y=METRIC,
        color="type_navire_norm" if "type_navire_norm" in data.columns else None,
        hover_data={c: True for c in hover_cols if c in data.columns},
        color_discrete_sequence=COLOR_SEQ)
    fig.update_traces(marker=dict(size=8, opacity=0.85),
                      hovertemplate=(
                          "<b>%{customdata[0]}</b><br>"
                          "Tonnage : %{x:,.0f} t<br>"
                          "Durée : %{y:.1f} h<br>"
                          "%{customdata[1]}<br>"
                          "%{customdata[2]}<extra></extra>"))
    fig.update_layout(
        height=380,
        xaxis_title="Tonnage (t)", yaxis_title="Durée au port (h)",
        yaxis_rangemode="nonnegative",
        legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return _apply_theme(fig), title


def _fig_distribution(frame: pd.DataFrame, year: int,
                      months: list[int]) -> tuple[go.Figure | None, str]:
    data = port_distribution_data(frame, year, months)
    title = "Distribution des durées de séjour" + _months_suffix(months)
    if data.empty:
        return None, title
    fig = go.Figure(go.Bar(
        x=data["interval"], y=data["count"],
        marker_color=[COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(data))],
        text=data["count"], textposition="outside"))
    fig.update_layout(
        height=350, xaxis_title="Durée (jours)",
        yaxis_title="Nombre d'escales",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig), title


def port_insights(frame: pd.DataFrame, year: int,
                  months: list[int]) -> list[str]:
    f = _base(frame)
    if f.empty:
        return ["Aucune donnée de séjour au port exploitable."]
    f = f[f["year"] == year]
    if f.empty:
        return [f"Aucune donnée pour {year}."]
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return ["Aucune donnée pour la période sélectionnée."]
    avg = round(float(f[METRIC].mean()), 1)
    med = round(float(f[METRIC].median()), 1)
    mx = round(float(f[METRIC].max()), 1)
    ships = f["navire_name"].nunique() if "navire_name" in f.columns else 0
    lines = [f"**Durée moyenne au port :** {avg} h ({round(avg/24,1)} jours)"]
    sym = "distribution symétrique" if abs(avg - med) < avg * 0.15 else "asymétrie notable"
    lines.append(f"**Durée médiane :** {med} h ({round(med/24,1)} jours) — {sym}")
    norm = "élevé" if mx > avg * 3 else "dans la norme"
    lines.append(f"**Durée maximale :** {mx} h ({round(mx/24,1)} jours) — {norm}")
    lines.append(f"**Navires uniques :** {ships}")
    if "marchandise_norm" in f.columns:
        top_m = f["marchandise_norm"].mode()
        if not top_m.empty and top_m.iloc[0]:
            lines.append(f"**Marchandise dominante :** {top_m.iloc[0]}")
    return lines


# ==================================================================
# API PUBLIQUE (appelée par la page Streamlit)
# ==================================================================
def compute(frame: pd.DataFrame, year: int, granularity: str,
            evo_month: int, evo_months: list[int], march_months: list[int],
            march_filter: list[str], operateur_months: list[int],
            operateur_filter: list[str], scatter_months: list[int],
            scatter_type_filter: list[str], dist_months: list[int]):
    """Calcule toutes les figures et KPI pour la page séjour au port.

    Retourne un dict avec toutes les données/figures prêt à afficher.
    """
    kpi = kpi_block(frame, year)

    # Évolution
    fig_evo = _fig_evolution(frame, year, granularity, evo_month)
    suffix_evo = (f" — {MONTHS_FR[evo_month - 1]} {year}"
                  if granularity == "Par jour" and evo_month else "")
    title_evo = f"Évolution du séjour — {year} vs {year - 1}" + suffix_evo

    # Marchandise
    fig_march, title_march = _fig_by_category(frame, year, march_months,
                                               "marchandise_norm")
    if march_filter:
        data_march = port_by_category(frame, year, march_months,
                                      "marchandise_norm")
        if not data_march.empty:
            data_march = data_march[
                data_march["marchandise_norm"].isin(march_filter)]
            fig_march = _horizontal_bars(data_march, "marchandise_norm",
                                         "sejour_moyen", title_march)
            title_march += f" — filtré ({len(march_filter)} marchandise(s))"

    # Opérateur
    fig_op, title_op = _fig_by_category(frame, year, operateur_months,
                                         "operateur_norm")
    if operateur_filter:
        data_op = port_by_category(frame, year, operateur_months,
                                   "operateur_norm")
        if not data_op.empty:
            data_op = data_op[
                data_op["operateur_norm"].isin(operateur_filter)]
            fig_op = _horizontal_bars(data_op, "operateur_norm",
                                      "sejour_moyen", title_op)
            title_op += f" — filtré ({len(operateur_filter)} opérateur(s))"

    # Scatter
    fig_scat, title_scat = _fig_scatter(frame, year, scatter_months)
    if scatter_type_filter and fig_scat is not None:
        data_scat = port_scatter_data(frame, year, scatter_months)
        if not data_scat.empty and "type_navire_norm" in data_scat.columns:
            data_scat = data_scat[
                data_scat["type_navire_norm"].isin(scatter_type_filter)]
            fig_scat, title_scat = _fig_scatter(frame, year, scatter_months)
            title_scat += f" — filtré ({len(scatter_type_filter)} type(s))"

    # Distribution
    fig_dist, title_dist = _fig_distribution(frame, year, dist_months)

    # Insights
    insights = port_insights(frame, year, dist_months)

    return {
        "kpi": kpi,
        "title_evo": title_evo, "fig_evo": fig_evo,
        "title_march": title_march, "fig_march": fig_march,
        "title_op": title_op, "fig_op": fig_op,
        "title_scat": title_scat, "fig_scat": fig_scat,
        "title_dist": title_dist, "fig_dist": fig_dist,
        "insights": insights,
    }
