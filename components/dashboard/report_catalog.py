# -*- coding: utf-8 -*-
"""Catalogue des visualisations disponibles pour la page Rapport.

CENTRALISÉ UNIQUEMENT DANS LE MODULE « RAPPORT » : le Dashboard reste 100 %
visualisation. Cette page offre un catalogue (Synthèse, Trafic, Postes,
Marchandises, Attente, Navires, Escales...) ; chaque entrée sait construire sa
figure Plotly + sa donnée associée depuis le CONTEXTE UNIQUE (build_context),
donc avec les filtres/période choisis dans le rapport.

Aucune donnée artificielle : tout provient des données réelles du port.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.analysis_views import (
    COLOR_SEQ, _apply_theme, _series_fig)
from components.dashboard import rapport_views as rv


# ==================================================================
# PETITS OUTILS DE FIGURE (thème maritime cohérent)
# ==================================================================
def _barh(data: pd.DataFrame, x: str, y: str, title: str,
          color: str = "#2dd4bf", height: int = None, bars=None):
    fig = go.Figure(go.Bar(
        x=data[x], y=data[y], orientation="h",
        marker_color=bars or color, marker_line_width=0, opacity=0.9))
    fig.update_layout(height=height or max(280, 28 * len(data)),
                      title=title, xaxis_title=None, yaxis_title=None,
                      margin=dict(t=50))
    return _apply_theme(fig)


def _monthly_lines(ctx, col: str, agg: str, title: str, unit: str):
    from components.dashboard.analytics import monthly_series
    cur = monthly_series(ctx["prepared"], col, agg)
    prev = (monthly_series(ctx["prepared_prev"], col, agg)
            if ctx["prepared_prev"] is not None
            and not ctx["prepared_prev"].empty else pd.DataFrame())
    fig = _series_fig(cur, prev, unit)
    if fig is None:
        return None
    fig.update_layout(title=title, height=360)
    return fig


# ==================================================================
# CONSTRUCTEURS D'ÉLÉMENTS (fig + data) depuis le contexte
# ==================================================================
def _kpi_compare(ctx):
    df = pd.DataFrame([
        {"Indicateur": r["kpi"], "Unité": r["unite"],
         "Période courante": r["courant"], "Période précédente": r["precedent"],
         "Variation %": (None if r["variation"] is None
                         else round(r["variation"], 1))}
        for r in rv.comparison_table(ctx)])
    return None, df


def _score_table(ctx):
    subs = ctx.get("score", {}).get("subscores", {})
    df = pd.DataFrame(
        [{"Indicateur": k, "Score /100": round(float(v), 1)}
         for k, v in subs.items()])
    return None, df


def _occupation_poste(ctx):
    p = ctx["postes"]
    data = p.sort_values("occupation") if not p.empty else p
    fig = _barh(data, "occupation", "poste", "Occupation par poste (%)",
                color=None, bars=[_occ_color(o) for o in data["occupation"]],
                height=max(300, 28 * len(data)))
    keep = [c for c in ["poste", "occupation", "escales", "tonnage",
                        "sejour_moyen", "productivite", "classe"]
            if c in p.columns]
    return fig, p[keep].reset_index(drop=True)


def _occ_color(o):
    return "#56a8ff" if o < 50 else "#32d2a4" if o < 70 \
        else "#f2b84b" if o < 80 else "#ff6077"


def _heatmap_occupation(ctx):
    from components.dashboard.occupation import monthly_occupancy
    iv = ctx.get("intervals")
    if iv is None or iv.empty:
        return None, None
    mo = monthly_occupancy(iv)
    if mo.empty:
        return None, None
    years = sorted(mo["year"].unique())
    latest = int(years[-1]) if years else None
    mgy = mo[mo["year"] == latest] if latest else mo
    heat = mgy.pivot_table(index="poste", columns="month",
                           values="taux_%", aggfunc="first")
    heat = heat.reindex(columns=[m for m in range(1, 13)
                                 if m in heat.columns]).dropna(how="all")
    heat.columns = [MONTHS_FR[int(c) - 1] for c in heat.columns]
    z = heat.values
    fig = go.Figure(go.Heatmap(
        z=z, x=heat.columns.tolist(), y=heat.index.tolist(),
        colorscale=[[0, "#0e2a47"], [0.35, "#2dd4bf"], [0.65, "#f2b84b"],
                    [1, "#ff6077"]],
        hovertemplate="<b>Poste %{y} — %{x}</b><br>Occupation : %{z:.1f} %"
                      "<extra></extra>"))
    fig.update_layout(height=max(300, 34 * len(heat)),
                      title=f"Heatmap Occupation Poste × Mois (%) — {latest}",
                      yaxis=dict(autorange="reversed"))
    return _apply_theme(fig), mo


def _trafic_mensuel(ctx):
    fig = _monthly_lines(ctx, "tonnage", "sum", "Évolution mensuelle du tonnage (t)",
                         "Tonnes")
    return fig, rv.monthly_report(ctx)


def _iec(ctx):
    df = rv.iec_report(ctx)
    colours = {"Import": "#62ddff", "Export": "#2dd4bf",
               "Cabotage": "#f2b84b"}
    fig = go.Figure(go.Bar(
        x=df["type_trafic"], y=df["tonnage"],
        marker_color=[colours.get(t, "#56a8ff") for t in df["type_trafic"]],
        marker_line_width=0, opacity=0.9,
        customdata=np.stack([df["part_%"].values, df["escales"].values],
                            axis=-1),
        hovertemplate="<b>%{x}</b><br>Tonnage : %{y:,.0f} t<br>"
                      "Part : %{customdata[0]:.1f} % · Escales : "
                      "%{customdata[1]}<extra></extra>"))
    fig.update_layout(title="Trafic Import / Export / Cabotage",
                      yaxis_title="Tonnes", xaxis_title=None, height=300)
    return _apply_theme(fig), df


def _marchandises(ctx):
    df = rv.marchandises_report(ctx)
    top = df.head(12)
    fig = go.Figure(go.Bar(
        x=top["tonnage"], y=top["marchandise_norm"], orientation="h",
        marker_color="#2dd4bf", marker_line_width=0, opacity=0.9,
        customdata=np.stack([top["part_%"].values], axis=-1),
        hovertemplate="<b>%{y}</b><br>Tonnage : %{x:,.0f} t<br>"
                      "Part : %{customdata[0]:.1f} %<extra></extra>"))
    fig.update_layout(title="Top marchandises (tonnage)", height=360,
                      xaxis_title="Tonnes", yaxis_title=None)
    return _apply_theme(fig), df


# --- Attente (réutilise attente_views, cohérent avec la page Attente) ---
def _attente_sel(prepared: pd.DataFrame, latest_year: int) -> dict:
    return {"year": latest_year, "months": [], "poste": None,
            "type_navire": None, "navire": None, "operateur": None,
            "marchandise": None}


def _attente_evolution(ctx):
    from components.dashboard import attente_views as av
    prep = av.prepare(ctx["prepared"])
    years = av.available_years(ctx["prepared"])
    if not years:
        return None, None
    latest = years[0]
    sel = _attente_sel(prep, latest)
    fig = av.fig_evolution(prep, sel)
    if fig is None:
        return None, None
    data = pd.concat([av.monthly_evol(prep, sel, latest),
                      av.monthly_evol(prep, sel, latest - 1)],
                     ignore_index=True)
    return fig, data


def _attente_distribution(ctx):
    from components.dashboard import attente_views as av
    prep = av.prepare(ctx["prepared"])
    years = av.available_years(ctx["prepared"])
    if not years:
        return None, None
    sel = _attente_sel(prep, years[0])
    fig = av.fig_distribution(prep, sel)
    data = av.distribution_data(av.filtered(prep, sel))
    return fig, data


def _attente_marchandise(ctx):
    from components.dashboard import attente_views as av
    prep = av.prepare(ctx["prepared"])
    years = av.available_years(ctx["prepared"])
    if not years:
        return None, None
    sel = _attente_sel(prep, years[0])
    fig = av.fig_marchandise(prep, sel, None)
    data = av.marchandise_stats(av.filtered_sans(prep, sel, skip="marchandise"))
    return fig, data


def _navires(ctx):
    df = pd.DataFrame()
    prep = ctx["prepared"]
    if not prep.empty:
        g = prep.groupby("navire_name")["escale_key"].nunique() \
            .sort_values(ascending=False).head(10)
        df = pd.DataFrame({"Navire": g.index, "Escales": g.values})
    fig = _barh(df, "Escales", "Navire", "Top 10 navires (escales)",
                color="#56a8ff") if not df.empty else None
    return fig, df


def _escales(ctx):
    return None, rv.escales_report(ctx)


# ==================================================================
# CATALOGUE
# ==================================================================
CATALOG = [
    # --- Synthèse & KPI ---
    {"id": "kpi_compare", "section": "Synthèse & KPI", "page": "Dashboard — KPI",
     "title": "Comparaison KPI N vs N-1", "kind": "table", "builder": _kpi_compare},
    {"id": "score", "section": "Synthèse & KPI", "page": "Dashboard — Score",
     "title": "Port Performance Score (sous-scores)", "kind": "table",
     "builder": _score_table},

    # --- Trafic ---
    {"id": "trafic_mensuel", "section": "Trafic", "page": "Dashboard — Trafic",
     "title": "Évolution mensuelle du tonnage", "kind": "figure",
     "builder": _trafic_mensuel},
    {"id": "iec", "section": "Trafic", "page": "Dashboard — Trafic",
     "title": "Import / Export / Cabotage", "kind": "figure", "builder": _iec},

    # --- Postes / Occupation ---
    {"id": "occupation_poste", "section": "Postes & Occupation",
     "page": "Dashboard — Postes", "title": "Occupation par poste (%)",
     "kind": "figure", "builder": _occupation_poste},
    {"id": "heatmap_occ", "section": "Postes & Occupation",
     "page": "Dashboard — Occupation", "title": "Heatmap Occupation Poste × Mois",
     "kind": "figure", "builder": _heatmap_occupation},

    # --- Marchandises ---
    {"id": "marchandises", "section": "Marchandises", "page": "Dashboard — Marchandises",
     "title": "Top marchandises (tonnage + part)", "kind": "figure",
     "builder": _marchandises},

    # --- Attente ---
    {"id": "attente_evolution", "section": "Attente au mouillage",
     "page": "Attente", "title": "Attente — Évolution N vs N-1", "kind": "figure",
     "builder": _attente_evolution},
    {"id": "attente_distribution", "section": "Attente au mouillage",
     "page": "Attente", "title": "Attente — Distribution des durées",
     "kind": "figure", "builder": _attente_distribution},
    {"id": "attente_marchandise", "section": "Attente au mouillage",
     "page": "Attente", "title": "Attente — Par marchandise", "kind": "figure",
     "builder": _attente_marchandise},

    # --- Navires ---
    {"id": "navires", "section": "Navires", "page": "Dashboard — Navires",
     "title": "Top 10 navires", "kind": "figure", "builder": _navires},

    # --- Escales ---
    {"id": "escales", "section": "Escales", "page": "Détail escales",
     "title": "Détail des escales", "kind": "table", "builder": _escales},
]


def catalog_sections() -> list[str]:
    seen: list[str] = []
    for e in CATALOG:
        if e["section"] not in seen:
            seen.append(e["section"])
    return seen


def catalog_by_section() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for e in CATALOG:
        out.setdefault(e["section"], []).append(e)
    return out
