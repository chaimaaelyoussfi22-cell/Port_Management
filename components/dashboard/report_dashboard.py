# -*- coding: utf-8 -*-
"""Catalogue du « 🎯 Rapport du dashboard » — la page RAPPORT reconstruite.

Le Dashboard demeure la source UNIQUE de vérité : chaque visualisation de ce
catalogue réutilise EXACTEMENT les builders/figures réels du Dashboard
(escales_views, navires_views, trafic_views, evolution_views, sejour_views,
sejour_port_views, attente_views, productivite_views, occupation_views,
consignation_views, consignation_evo_views, incidents_views) — aucune donnée
fictive, aucune logique recalculée ailleurs.

Les 12 cartes (DIMENSIONS) servent de catalogue de navigation. Pour chaque
carte on définit une liste de visualisations ; chacune est un spec :
    {"vid": <id logique>, "title": <titre affiché>,
     "builder": callable(res) -> (fig|None, data_df|None)}

Le builder reçoit un objet `Res` (contexte partagé, voir `build_res`) et
retourne la figure Plotly réelle + sa donnée (pour export Excel/CSV).

Aucune dépendance Streamlit dans la logique métier ; les fonctions de rendu
(Streamlit) sont regroupées en fin de module.
"""

from __future__ import annotations

from typing import Callable, Optional

# ==================================================================
# CONTEXTE PARTAGÉ
# ==================================================================
class Res:
    """Contexte réel d'un rapport : toutes les tables/figures proviennent des
    données filtrées par build_context (Dashboard) + tables auxiliaires."""

    __slots__ = ("ctx", "prepared", "year", "months", "consig", "incidents",
                 "filter_text")

    def __init__(self, ctx, prepared, year, months, consig, incidents,
                 filter_text: str = ""):
        self.ctx = ctx                  # build_context() -> dict (analytics)
        self.prepared = prepared        # ctx["prepared"] (opérations filtrées)
        self.year = year                # année de référence
        self.months = months            # mois sélectionnés ([] = toute l'année)
        self.consig = consig            # table consignations préparée
        self.incidents = incidents      # table incidents préparée (sans consignations)
        self.filter_text = filter_text


# Libellé des mois pour les suffixes (reprend filters.MONTHS_FR)
from components.dashboard.filters import MONTHS_FR as _MOIS  # noqa: E402


def _months_suffix(months: list[int]) -> str:
    return (" · " + ", ".join(_MOIS[m - 1] for m in sorted(months))
            if months else "")


def _type_trafic(sel: str) -> Optional[list[str]]:
    """Traduit la sélection « Type d'opération » en liste de types (None=Tous)."""
    if sel in (None, "", "Tous types", "Tous"):
        return None
    if sel == "Cabotage":
        return ["Cabotage"]
    return [sel]


# ==================================================================
# DONNÉES AUXILIAIRES (tables réelles, aucune donnée inventée)
# ==================================================================
def prepare_consig(limit: int = 20000):
    from database import db_manager
    from components.dashboard.consignation_views import prepare_consignations
    raw = db_manager.get_consignations(limit=limit)
    return prepare_consignations(raw)


def prepare_incidents(limit: int = 200000):
    from database import db_manager
    from components.dashboard.incidents_views import (
        prepare_incidents as _pi, sans_consignations)
    raw = db_manager.get_incidents(limit=limit)
    df = _pi(raw)
    return sans_consignations(df)


# ==================================================================
# BUILDERS DE VISUALISATIONS — réutilisent les vrais figurines Dashboard
# ==================================================================
def _b_esc_evolution(res):
    year, months = res.year, res.months
    from components.dashboard import escales_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    title = ("Évolution des escales N vs N-1"
             + (f" — {_MOIS[m-1][:4]} {year}" if len(months) == 1 else "")
             + _months_suffix(months))
    fig = v.fig_evolution(res.prepared, year,
                          month=months[0] if len(months) == 1 else None)
    return fig, _monthly_df("escales", res)


def _b_esc_marchandise(res):
    year, months = res.year, res.months
    from components.dashboard import escales_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v.fig_marchandise(res.prepared, year, months or None)
    return fig, _monthly_df("escales", res)


def _b_esc_category(res, col, cat_label, col_data):
    year, months = res.year, res.months
    from components.dashboard import escales_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, title = v.fig_category(res.prepared, year, months, col, cat_label)
    return fig, _cat_df(res, col, col_data)


def _b_nav_evolution(res):
    year, months = res.year, res.months
    from components.dashboard import navires_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    title = ("Évolution des navires N vs N-1"
             + (f" — {_MOIS[m-1][:4]} {year}" if len(months) == 1 else ""))
    fig = v.fig_evolution(res.prepared, year,
                          month=months[0] if len(months) == 1 else None)
    return fig, _monthly_df("navires", res)


def _b_nav_category(res, col, title_txt):
    year, months = res.year, res.months
    from components.dashboard import navires_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    cat = col.replace("_norm", "")
    if cat == "type_navire":
        fig, _ = v.fig_type_navire(res.prepared, year, months)
    else:
        fig, _ = v.fig_operateur(res.prepared, year, months)
    data = _cat_df(res, col, "navires")
    return (fig, data.rename(columns={"navire": "navires"}) if data is not None
            else data)


def _b_nav_marchandise(res):
    year, months = res.year, res.months
    from components.dashboard import navires_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, title = v.fig_marchandise(res.prepared, year, months, [])
    return fig, _cat_df(res, "marchandise_norm", "navires")


def _b_trafic_donut(res):
    year, months = res.year, res.months
    from components.dashboard import trafic_views as v
    period = v.period_label(year, months)
    fig = v.fig_donut(res.prepared, year, months=months, periode=period)
    return fig, _iec_df(res)


def _b_trafic_monthly(res):
    year, months = res.year, res.months
    from components.dashboard import trafic_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v.fig_evolution(res.prepared, year,
                          month=months[0] if len(months) == 1 else None)
    return fig, _monthly_df("tonnage", res)


def _b_trafic_grouped(res):
    year, months = res.year, res.months
    from components.dashboard import trafic_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    types = v.present_types(res.prepared, year, months)
    data = v.volume_by_category_type(res.prepared, year, months, types,
                                     "marchandise_norm")
    prev = v.volume_by_category_type(res.prepared, year - 1, months, types,
                                     "marchandise_norm") \
        if year - 1 in set(res.prepared["year"]) else None
    fig = v.fig_grouped_type(data, "marchandise_norm",
                             v.period_label(year, months), prev)
    return fig, data


def _b_trafic_categ_composition(res):
    year, months = res.year, res.months
    from components.dashboard import trafic_views as v
    return _b_trafic_grouped(res)


def _b_evo_global(res):
    year, months = res.year, res.months
    from components.dashboard import trafic_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v.fig_evolution(res.prepared, year,
                          month=months[0] if len(months) == 1 else None)
    data = _monthly_df("tonnage", res)
    return fig, data


def _b_evo_by_type(res):
    year, months = res.year, res.months
    from components.dashboard import evolution_views as v
    from components.dashboard.trafic_views import OP_ORDER
    if year not in set(res.prepared["year"]):
        return None, None
    types = OP_ORDER
    gran = ("Par mois" if len(months) != 1 else "Par jour")
    fig = v.fig_evo_by_type(res.prepared, year, gran,
                            month=months[0] if len(months) == 1 else 1,
                            types=types)
    return fig, _monthly_df("tonnage", res)


def _b_evo_operateur(res):
    year, months = res.year, res.months
    from components.dashboard import evolution_views as v
    if year not in set(res.prepared["year"]):
        return None, None
    cats = v.available_cats(res.prepared, year, "operateur_norm", months=months)
    fig = v.fig_evo_by_category(res.prepared, year, cats[:8], "operateur_norm",
                                types=None)
    return fig, _cat_df(res, "operateur_norm", "tonnage")


def _b_evo_marchandise(res):
    year, months = res.year, res.months
    from components.dashboard import evolution_views as v
    if year not in set(res.prepared["year"]):
        return None, None
    cats = v.available_cats(res.prepared, year, "marchandise_norm", months=months)
    fig = v.fig_evo_by_category(res.prepared, year, cats[:8], "marchandise_norm",
                                types=None)
    return fig, _cat_df(res, "marchandise_norm", "tonnage")


def _b_sq_evolution(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v.fig_evolution(res.prepared, year, "Par mois")
    return fig, _monthly_df("sejour_quai", res)


def _b_sq_poste(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, title = v.fig_poste(res.prepared, year, months, [v.ALL_POSTES])
    data = v.performance_by_poste(res.prepared, year, months)
    return fig, data


def _b_sq_marchandise(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v.fig_marchandise(res.prepared, year, months,
                               [v.ALL_MARCHANDISES])
    return fig, _avg_cat_df(res, "marchandise_norm")


def _b_sq_type(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v.fig_type_navire(res.prepared, year, months)
    return fig, _avg_cat_df(res, "type_navire_norm")


def _b_sq_operateur(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v.fig_operateur(res.prepared, year, months)
    return fig, _avg_cat_df(res, "operateur_norm")


def _b_sq_distribution(res):
    year, _ = res.year, res.months
    from components.dashboard import sejour_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v.fig_distribution(res.prepared, year)
    data = v.distribution_data(res.prepared, year)
    return fig, data


def _b_sp_evolution(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_port_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig = v._fig_evolution if hasattr(v, "_fig_evolution") else None
    from components.dashboard.analytics import MONTHS_FR
    if fig is None:
        return None, None
    fig = v._fig_evolution(res.prepared, year, "Par mois",
                           months[0] if len(months) == 1 else 1)
    return fig, _monthly_df("sejour_port", res)


def _b_sp_marchandise(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_port_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_by_category(res.prepared, year, months, "marchandise_norm")
    return fig, _avg_cat_df(res, "marchandise_norm")


def _b_sp_operateur(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_port_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_by_category(res.prepared, year, months, "operateur_norm")
    return fig, _avg_cat_df(res, "operateur_norm")


def _b_sp_scatter(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_port_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_scatter(res.prepared, year, months)
    return fig, v.port_scatter_data(res.prepared, year, months)


def _b_sp_distribution(res):
    year, months = res.year, res.months
    from components.dashboard import sejour_port_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_distribution(res.prepared, year, months)
    return fig, v.port_distribution_data(res.prepared, year, months)


def _b_att_evolution(res):
    from components.dashboard import attente_views as v
    sel = {"year": res.year, "months": res.months}
    fig = v.fig_evolution(res.prepared, sel)
    return fig, _monthly_df("attente", res)


def _b_att_distribution(res):
    from components.dashboard import attente_views as v
    sel = {"year": res.year, "months": res.months}
    fig = v.fig_distribution(res.prepared, sel)
    data = v.distribution_data(v.filtered(res.prepared, sel))
    return fig, data


def _b_att_marchandise(res):
    from components.dashboard import attente_views as v
    sel = {"year": res.year, "months": res.months}
    fig = v.fig_marchandise(res.prepared, sel, None)
    return fig, _avg_cat_df(res, "marchandise_norm")


def _b_prod_global(res):
    year, _ = res.year, res.months
    from components.dashboard import productivite_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_port_monthly(res.prepared, year)
    return fig, _monthly_df("productivite", res)


def _b_prod_poste(res):
    year, months = res.year, res.months
    from components.dashboard import productivite_views as v
    if year not in v.available_years(res.prepared):
        return None, None
    fig, _ = v._fig_poste(res.prepared, year, months, [])
    return fig, v.poste_prod_data(res.prepared, year, months or None)


def _b_occ_etat(res):
    from components.dashboard.occupation_views import compute as occ_compute
    r = occ_compute(res.prepared, res.year, res.months, [])
    fig = r["fig_state"]
    data = None
    if fig is not None:
        from components.dashboard.occupation_views import _state_data
        data = _state_data(r["monthly"], res.year, res.months, [])
    return fig, data


def _b_occ_evolution(res):
    from components.dashboard.occupation_views import compute as occ_compute
    r = occ_compute(res.prepared, res.year, res.months, [])
    return r["fig_evo"], _monthly_occupancy_df(res)


def _b_consign_poste(res):
    year, months = res.year, res.months
    from components.dashboard import consignation_views as v
    if not _consig_years(res):
        return None, None
    fig, _title = v.fig_by_poste(res.consig, year, months or None)
    return fig, None


def _b_consign_causes(res):
    year, months = res.year, res.months
    from components.dashboard import consignation_views as v
    if not _consig_years(res):
        return None, None
    fig, _title = v.fig_causes(res.consig, year, months or None, None)
    return fig, None


def _b_consign_duration(res):
    year, months = res.year, res.months
    from components.dashboard import consignation_views as v
    if not _consig_years(res):
        return None, None
    fig, _title = v.fig_duration_distrib(res.consig, year, months or None,
                                         None)
    return fig, None


def _b_consign_port(res):
    year, months = res.year, res.months
    from components.dashboard import consignation_views as v
    if not _consig_years(res):
        return None, None
    fig, _title = v.fig_port(res.consig, year, months or None)
    return fig, None


def _b_consign_events(res):
    year, months = res.year, res.months
    from components.dashboard import consignation_views as v
    if not _consig_years(res):
        return None, None
    table, _total = v.events_table(res.consig, year, months or None, None,
                                   None)
    return None, table


def _b_ce_globale(res):
    year = res.year
    from components.dashboard import consignation_evo_views as v
    if not _consig_years(res):
        return None, None
    dur_cat = None
    fig, title = v.fig_evo_globale(res.consig, year, dur_cat, None)
    return fig, _consig_monthly_df(res)


def _b_ce_poste(res):
    year = res.year
    from components.dashboard import consignation_evo_views as v
    if not _consig_years(res):
        return None, None
    opts = v.poste_options(res.consig, year)
    fig, title, _ = v.fig_evo_poste(res.consig, year, None, None,
                                    [v.ALL_POSTES])
    return fig, None


def _b_ce_nvsn1(res):
    year = res.year
    from components.dashboard import consignation_evo_views as v
    if not _consig_years(res):
        return None, None
    fig, title, _ = v.fig_evo_nvsn1(res.consig, year, None, None, None)
    return fig, None


def _b_ce_duree(res):
    year = res.year
    from components.dashboard import consignation_evo_views as v
    if not _consig_years(res):
        return None, None
    fig, title = v.fig_evo_duree(res.consig, year, None, None)
    return fig, None


def _b_inc_nature(res):
    fig, data = _inc_nature_fig(res.incidents)
    return fig, data


def _b_inc_evolution(res):
    fig, data = _inc_evolution_fig(res.incidents)
    return fig, data


def _b_inc_lieux(res):
    fig, data = _inc_lieux_fig(res.incidents)
    return fig, data


# ==================================================================
# FIGURES FRAÎCHEMENT CONSTRUITES POUR LES INCIDENTS (table réelle)
# ==================================================================
def _inc_nature_fig(df):
    if df is None or df.empty:
        return None, None
    g = df["nature"].value_counts().sort_values(ascending=False)
    display = g.head(10)
    rest = int(g.iloc[10:].sum()) if len(g) > 10 else 0
    labels = display.index.tolist() + (["Autres"] if rest else [])
    values = display.values.tolist() + ([rest] if rest else [])
    import plotly.graph_objects as go
    from components.dashboard.incidents_views import COLORS, _theme
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.62,
        marker={"colors": COLORS[:len(labels)]},
        textinfo="percent", sort=False))
    fig.update_layout(height=330, showlegend=True,
                      legend=dict(orientation="h", yanchor="bottom", y=-0.05))
    fig = _theme(fig)
    data = g.reset_index()
    data.columns = ["nature", "count"]
    return fig, data


def _inc_evolution_fig(df):
    if df is None or df.empty:
        return None, None
    from components.dashboard.filters import MONTHS_FR
    g = (df.groupby(["year", "month"]).size().reset_index(name="nb")
         .sort_values(["year", "month"]))
    g["label"] = [f"{MONTHS_FR[m - 1][:4]} {y}"
                  for y, m in zip(g["year"], g["month"])]
    import plotly.graph_objects as go
    from components.dashboard.incidents_views import _theme
    fig = go.Figure(go.Scatter(
        x=g["label"], y=g["nb"], mode="lines+markers",
        line={"color": "#62ddff", "width": 2.8}, marker={"size": 7},
        fill="tozeroy", fillcolor="rgba(98,221,255,.16)"))
    fig.update_layout(height=330, xaxis_title=None, yaxis_title="Incidents",
                      showlegend=False)
    fig = _theme(fig)
    return fig, g[["label", "nb"]].rename(columns={"label": "Période",
                                                   "nb": "Incidents"})


def _inc_lieux_fig(df):
    if df is None or df.empty:
        return None, None
    g = df["lieu"].value_counts().sort_values(ascending=False).head(12)
    import plotly.graph_objects as go
    from components.dashboard.incidents_views import _theme
    fig = go.Figure(go.Bar(
        y=g.index.tolist(), x=g.values.tolist(), orientation="h",
        text=g.values.tolist(), textposition="outside", cliponaxis=False,
        marker={"color": "#56a8ff"}))
    fig.update_layout(height=max(320, 36 * len(g)),
                      margin={"l": 8, "r": 40, "t": 8, "b": 8},
                      xaxis_title="Incidents", yaxis_title=None, showlegend=False)
    fig.update_yaxes(automargin=True)
    fig = _theme(fig)
    data = g.reset_index()
    data.columns = ["lieu", "count"]
    return fig, data


# ==================================================================
# DONNÉES POUR EXPORT (associées aux figures)
# ==================================================================
def _monthly_df(metric, res):
    """Série mensuelle réelle de la période pour le KPI demandé."""
    from components.dashboard.analytics import MONTHS_FR
    p = res.prepared
    if p is None or p.empty or "month" not in p:
        return None
    if "year" in p.columns:
        p = p[p["year"] == res.year] if res.year in set(p["year"]) else p
    if res.months:
        p = p[p["month"].isin(res.months)]
    if p.empty:
        return None
    g = p.assign(_month=p["month"].astype(int))
    if metric == "escales":
        s = g.groupby("_month")["escale_key"].nunique()
        label = "Escales"
    elif metric == "navires":
        s = g.groupby("_month")["navire_name"].nunique()
        label = "Navires"
    elif metric == "sejour_quai":
        s = g.groupby("_month")["quai_h"].mean()
        label = "Séjour quai (h)"
    elif metric == "sejour_port":
        s = g.groupby("_month")["port_h"].mean()
        label = "Séjour port (h)"
    elif metric == "attente":
        s = g.groupby("_month")["attente_h"].mean()
        label = "Attente (h)"
    elif metric == "productivite":
        g2 = g.groupby("_month").agg(v=("tonnage", "sum"),
                                     d=("port_h", "sum"))
        s = (g2["v"] / g2["d"].replace(0, float("nan"))).fillna(0.0)
        label = "Productivité (t/h)"
    else:  # tonnage
        s = g.groupby("_month")["tonnage"].sum()
        label = "Tonnage (t)"
    out = pd.DataFrame({"Mois": [MONTHS_FR[int(m) - 1] for m in s.index],
                        label: s.round(2).values})
    return out


def _consig_monthly_df(res):
    from components.dashboard.analytics import MONTHS_FR
    if res.consig is None or res.consig.empty:
        return None
    f = res.consig[res.consig["year"] == res.year] if res.year in set(res.consig["year"]) else res.consig
    if res.months:
        f = f[f["month"].isin(res.months)]
    if f.empty:
        return None
    s = f.groupby("month").size()
    import pandas as pd
    return pd.DataFrame({"Mois": [MONTHS_FR[int(m) - 1] for m in s.index],
                         "Consignations": s.values})


def _cat_df(res, col, value_col):
    p = res.prepared
    if p is None or p.empty or col not in p.columns:
        return None
    f = p.copy()
    if "year" in f.columns and res.year in set(f["year"]):
        f = f[f["year"] == res.year]
    if res.months:
        f = f[f["month"].isin(res.months)]
    if f.empty:
        return None
    import pandas as pd
    key = col.replace("_norm", "")
    g = f.assign(_c=f[col].fillna("non spécifié")).groupby("_c")
    if value_col == "tonnage":
        out = g["tonnage"].sum()
    elif value_col == "navires":
        out = g["navire_name"].nunique()
    else:
        out = g.size()
    df = out.reset_index().rename(columns={"_c": key, 0: str(value_col)})
    df.columns = [key, str(value_col)]
    return df


def _avg_cat_df(res, col):
    p = res.prepared
    if p is None or p.empty or col not in p.columns:
        return None
    f = p.copy()
    if "year" in f.columns and res.year in set(f["year"]):
        f = f[f["year"] == res.year]
    if res.months:
        f = f[f["month"].isin(res.months)]
    if f.empty:
        return None
    import pandas as pd
    key = col.replace("_norm", "")
    g = f.assign(_c=f[col].fillna("non spécifié"))
    df = g.groupby("_c").agg(moyenne=("quai_h", "mean")).reset_index()
    df.columns = [key, "moyenne"]
    return df


def _iec_df(res):
    import pandas as pd
    p = res.prepared
    if p is None or p.empty:
        return None
    f = p.copy()
    if "year" in f.columns and res.year in set(f["year"]):
        f = f[f["year"] == res.year]
    if res.months:
        f = f[f["month"].isin(res.months)]
    if f.empty:
        return None
    g = f.groupby("type_trafic")["tonnage"].sum().reset_index()
    g.columns = ["Type d'opération", "Tonnage (t)"]
    return g


def _monthly_occupancy_df(res):
    from components.dashboard.occupation import monthly_occupancy
    from components.dashboard.analytics import MONTHS_FR
    iv = res.ctx.get("intervals")
    if iv is None or iv.empty:
        return None
    mo = monthly_occupancy(iv)
    if mo.empty:
        return None
    if res.year in set(mo["year"]):
        mo = mo[mo["year"] == res.year]
    if res.months:
        mo = mo[mo["month"].isin(res.months)]
    if mo.empty:
        return None
    g = mo.groupby("month")["taux_%"].mean().reset_index()
    import pandas as pd
    return pd.DataFrame({"Mois": [MONTHS_FR[int(m) - 1] for m in g["month"]],
                         "Occupation (%)": g["taux_%"].round(1).values})


def _consig_years(res):
    return res.consig is not None and not res.consig.empty and \
        "year" in res.consig.columns


# ==================================================================
# CATALOGUE : les 12 cartes du Dashboard (mêmes clés que kpi_cards)
# ==================================================================
import pandas as pd  # noqa: E402  (utilisé par les builders de données)

CARD_VISUALS: dict[str, list[dict]] = {
    "escales": [
        {"vid": "esc_evolution", "title": "Évolution des escales N vs N-1",
         "builder": _b_esc_evolution},
        {"vid": "esc_marchandise",
         "title": "Escales par marchandise (mensuel)",
         "builder": _b_esc_marchandise},
        {"vid": "esc_type",
         "title": "Escales par type de navire",
         "builder": lambda r: _b_esc_category(r, "type_navire_norm",
                                              "Escales par type de navire",
                                              "escales")},
        {"vid": "esc_operateur",
         "title": "Escales par opérateur",
         "builder": lambda r: _b_esc_category(r, "operateur_norm",
                                              "Escales par opérateur",
                                              "escales")},
    ],
    "navires": [
        {"vid": "nav_evolution", "title": "Évolution des navires N vs N-1",
         "builder": _b_nav_evolution},
        {"vid": "nav_type", "title": "Navires par type de navire",
         "builder": lambda r: _b_nav_category(r, "type_navire_norm", "")},
        {"vid": "nav_operateur", "title": "Navires par opérateur",
         "builder": lambda r: _b_nav_category(r, "operateur_norm", "")},
        {"vid": "nav_marchandise", "title": "Navires par marchandise",
         "builder": _b_nav_marchandise},
    ],
    "tonnage": [
        {"vid": "tr_donut",
         "title": "Répartition du trafic Import / Export / Cabotage",
         "builder": _b_trafic_donut},
        {"vid": "tr_monthly", "title": "Évolution du tonnage N vs N-1",
         "builder": _b_trafic_monthly},
        {"vid": "tr_grouped",
         "title": "Tonnage par marchandise et type d'opération",
         "builder": _b_trafic_grouped},
    ],
    "evolution_trafic": [
        {"vid": "ev_global", "title": "Évolution globale du trafic N vs N-1",
         "builder": _b_evo_global},
        {"vid": "ev_type", "title": "Évolution par type d'opération",
         "builder": _b_evo_by_type},
        {"vid": "ev_operateur", "title": "Évolution par opérateur",
         "builder": _b_evo_operateur},
        {"vid": "ev_marchandise", "title": "Évolution par marchandise",
         "builder": _b_evo_marchandise},
    ],
    "sejour_quai": [
        {"vid": "sq_evolution", "title": "Évolution du séjour à quai N vs N-1",
         "builder": _b_sq_evolution},
        {"vid": "sq_poste", "title": "Séjour à quai par poste N vs N-1",
         "builder": _b_sq_poste},
        {"vid": "sq_marchandise", "title": "Temps à quai par marchandise",
         "builder": _b_sq_marchandise},
        {"vid": "sq_type", "title": "Séjour à quai par type de navire",
         "builder": _b_sq_type},
        {"vid": "sq_operateur", "title": "Séjour à quai par opérateur",
         "builder": _b_sq_operateur},
        {"vid": "sq_distribution",
         "title": "Distribution des durées de séjour à quai",
         "builder": _b_sq_distribution},
    ],
    "sejour_port": [
        {"vid": "sp_evolution", "title": "Évolution du séjour au port N vs N-1",
         "builder": _b_sp_evolution},
        {"vid": "sp_marchandise", "title": "Séjour au port par marchandise",
         "builder": _b_sp_marchandise},
        {"vid": "sp_operateur", "title": "Séjour au port par opérateur",
         "builder": _b_sp_operateur},
        {"vid": "sp_scatter", "title": "Tonnage vs durée de séjour au port",
         "builder": _b_sp_scatter},
        {"vid": "sp_distribution",
         "title": "Distribution des durées de séjour au port",
         "builder": _b_sp_distribution},
    ],
    "attente": [
        {"vid": "att_evolution", "title": "Évolution de l'attente N vs N-1",
         "builder": _b_att_evolution},
        {"vid": "att_distribution", "title": "Distribution des durées d'attente",
         "builder": _b_att_distribution},
        {"vid": "att_marchandise", "title": "Attente par marchandise",
         "builder": _b_att_marchandise},
    ],
    "productivite": [
        {"vid": "prod_global", "title": "Productivité mensuelle du port",
         "builder": _b_prod_global},
        {"vid": "prod_poste", "title": "Productivité par poste",
         "builder": _b_prod_poste},
    ],
    "occupation": [
        {"vid": "occ_etat", "title": "État d'occupation des postes",
         "builder": _b_occ_etat},
        {"vid": "occ_evolution",
         "title": "Évolution du taux d'occupation N vs N-1",
         "builder": _b_occ_evolution},
    ],
    "consignation": [
        {"vid": "co_poste", "title": "Consignations par poste",
         "builder": _b_consign_poste},
        {"vid": "co_causes", "title": "Consignations par cause",
         "builder": _b_consign_causes},
        {"vid": "co_duration", "title": "Distribution des durées de consignation",
         "builder": _b_consign_duration},
        {"vid": "co_port", "title": "Statistiques consignation / port",
         "builder": _b_consign_port},
        {"vid": "co_register", "title": "Registre des consignations",
         "builder": _b_consign_events},
    ],
    "consignation_evo": [
        {"vid": "ce_globale", "title": "Évolution globale de la consignation",
         "builder": _b_ce_globale},
        {"vid": "ce_poste", "title": "Évolution de la consignation par poste",
         "builder": _b_ce_poste},
        {"vid": "ce_nvsn1", "title": "Consignations N vs N-1",
         "builder": _b_ce_nvsn1},
        {"vid": "ce_duree", "title": "Évolution selon la durée",
         "builder": _b_ce_duree},
    ],
    "incidents": [
        {"vid": "inc_nature", "title": "Incidents par nature",
         "builder": _b_inc_nature},
        {"vid": "inc_evolution", "title": "Évolution des incidents",
         "builder": _b_inc_evolution},
        {"vid": "inc_lieux", "title": "Incidents par lieu / poste",
         "builder": _b_inc_lieux},
    ],
}


def visuals_for_card(card_key: str) -> list[dict]:
    """Visualisations (id/titre/builder) d'une carte, sans duplicats d'id."""
    seen: set[str] = set()
    out: list[dict] = []
    for spec in CARD_VISUALS.get(card_key, []):
        if spec["vid"] in seen:
            continue
        seen.add(spec["vid"])
        out.append(spec)
    return out


def all_cards() -> list:
    from components.dashboard.kpi_cards import DIMENSIONS
    return DIMENSIONS
