# -*- coding: utf-8 -*-
"""📊 Rapport structuré — moteur analytique automatique (12 sections).

PRINCIPE : filtres → données filtrées → calcul → graphiques → rapport.

Cohérence absolue avec le Dashboard : le contexte courant et le contexte N-1
sont tous deux produits par build_context() (analytics.py) — mêmes KPI, mêmes
variations, mêmes stats par poste. Les consignations et incidents proviennent
de leurs tables dédiées (jamais assimilés à des incidents).

Aucune donnée inventée : si l'historique est insuffisant, on affiche
« Historique insuffisant » / « Comparaison N-1 indisponible ».

Ce module est PURE (aucune dépendance Streamlit) : testable et réutilisé par
les exports PDF / Excel / CSV et par la prévisualisation de la page.
"""

from __future__ import annotations

import calendar
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import (
    MONTHS_FR, build_context, compare_kpis, compute_kpis, monthly_series,
    prepare_operations, previous_year_window)
from components.dashboard.analysis_views import COLOR_SEQ, _apply_theme
from components.dashboard import (
    attente_views, consignation_views, consignation_evo_views, escales_views,
    evolution_views, incidents_views, navires_views, occupation_views,
    sejour_views, trafic_views)

MONTHS_FULL = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet",
               "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


# ==================================================================
# FILTRES UTILISATEUR → SOUS-ENSEMBLE RÉEL
# ==================================================================
def apply_report_filters(ops: pd.DataFrame, rep: dict) -> pd.DataFrame:
    """Applique année, mois, poste, type navire, navire, opérateur, marchandise,
    type trafic sur les opérations brutes. Renvoie un DataFrame vidé if aucun."""
    f = ops.copy()
    if f.empty:
        return f
    d = pd.to_datetime(f["date"], errors="coerce")
    f = f[d.notna()].copy()
    f["date"] = d[f.index].dt.date
    if rep.get("year"):
        f = f[f["date"].apply(lambda dt: dt.year == int(rep["year"]))]
    months = rep.get("months") or []
    if months:
        f = f[f["date"].apply(lambda dt: dt.month in months)]

    def _col(col):
        return col if col in f.columns else None

    def _eq(col, value, sentinel):
        c = _col(col)
        if c is None or not value or value in sentinel:
            return
        f_filter = f[f[c].fillna("").astype(str) == str(value)]
        f.loc[:, "_keep"] = f.index.isin(f_filter.index)

    poste = _col("poste"); tn = _col("type_navire"); nav = _col("navire")
    op = _col("operateur"); mch = _col("type_marchandise")
    trafic = _col("type_operation")
    masks = []
    if poste is not None and rep.get("poste") and rep["poste"] != "Tous les postes":
        masks.append(f["poste"].fillna("").astype(str) == str(rep["poste"]))
    if tn is not None and rep.get("type_navire") and rep["type_navire"] != "Tous":
        masks.append(f["type_navire"].fillna("").astype(str) == str(rep["type_navire"]))
    if nav is not None and rep.get("navire") and rep["navire"] != "Tous":
        masks.append(f["navire"].fillna("").astype(str) == str(rep["navire"]))
    if op is not None and rep.get("operateur") and rep["operateur"] != "Tous":
        masks.append(f["operateur"].fillna("").astype(str) == str(rep["operateur"]))
    if mch is not None and rep.get("marchandise") and rep["marchandise"] != "Toutes":
        masks.append(f["type_marchandise"].fillna("").astype(str) == str(rep["marchandise"]))
    if trafic is not None and rep.get("type_trafic") and rep["type_trafic"] != "Tous types":
        masks.append(f["type_operation"].fillna("").astype(str)
                     .str.lower().str.startswith(str(rep["type_trafic"]).lower()[:4]))
    for m in masks:
        f = f[m]
    return f


def period_bounds_for(rep: dict) -> tuple[date, date]:
    year = int(rep.get("year") or date.today().year)
    months = sorted(rep.get("months") or [])
    m0, m1 = (months[0], months[-1]) if months else (1, 12)
    return date(year, m0, 1), date(year, m1, calendar.monthrange(year, m1)[1])


def filters_prev(rep: dict) -> dict:
    """Même filtre avec l'année N-1 (mêmes mois/dimensions)."""
    p = dict(rep)
    if p.get("year"):
        p["year"] = int(p["year"]) - 1
    return p


# ==================================================================
# CONTEXTE DU RAPPORT (courant + N-1 + sources auxiliaires)
# ==================================================================
def build_report_ctx(ops: pd.DataFrame, consig_raw: pd.DataFrame,
                     incidents_raw: pd.DataFrame, rep: dict) -> dict:
    cur_ops = apply_report_filters(ops, rep)
    prev_ops = apply_report_filters(ops, filters_prev(rep))
    start, end = period_bounds_for(rep)
    prev_rep = filters_prev(rep)
    p_start, p_end = period_bounds_for(prev_rep)

    cur = build_context(cur_ops, {"period": "Rapport", "start": start,
                                  "end": end, "poste": None, "operateur": None,
                                  "marchandise": None, "type_navire": None,
                                  "type_trafic": None})
    prev = build_context(prev_ops, {"period": "Rapport", "start": p_start,
                                    "end": p_end, "poste": None,
                                    "operateur": None, "marchandise": None,
                                    "type_navire": None, "type_trafic": None})

    variations = compare_kpis(cur["kpis"], prev["kpis"])
    cur["kpis_prev"] = prev["kpis"]
    cur["variations"] = variations
    cur["prepared_prev"] = prev["prepared"]
    cur["postes_prev"] = prev["postes"]
    cur["segments_prev"] = prev["segments"]
    cur["intervals_prev"] = prev["intervals"]
    cur["prev_period"] = {"start": p_start, "end": p_end}
    cur["has_prev"] = not prev_ops.empty

    # Données N + N-1 combinées pour les courbes (N pleine / N-1 pointillée)
    cur["prepared_all"] = (pd.concat([cur["prepared"], prev["prepared"]],
                                     ignore_index=True)
                           if not prev["prepared"].empty else cur["prepared"])

    # ---- Consignations (table dédiée) ----
    consig = consignation_views.prepare_consignations(consig_raw) \
        if consig_raw is not None and not consig_raw.empty else pd.DataFrame()
    cur["consig"] = _slice_aux(consig, start, end, rep)
    cur["consig_prev"] = _slice_aux(consig, p_start, p_end, prev_rep)

    # ---- Incidents (table dédiée) — consignations exclues (logique métier) ----
    inc = incidents_views.prepare_incidents(incidents_raw) \
        if incidents_raw is not None and not incidents_raw.empty else pd.DataFrame()
    inc = incidents_views.sans_consignations(inc) if not inc.empty else inc
    cur["incidents"] = _slice_aux_date(inc, start, end)
    cur["incidents_prev"] = _slice_aux_date(inc, p_start, p_end)

    cur["filters_applied"] = rep
    cur["period"] = {"start": start, "end": end,
                     "days": max((end - start).days + 1, 1)}
    return cur


def _slice_aux(frame: pd.DataFrame, start: date, end: date, rep: dict) -> pd.DataFrame:
    """Filtre temporel + poste sur une table auxiliaire (consignations)."""
    if frame is None or frame.empty:
        return frame if frame is not None else pd.DataFrame()
    f = frame.copy()
    dd = pd.to_datetime(f["date_debut"], errors="coerce")
    f = f[dd.notna()].copy()
    f["date_debut"] = dd[f.index].dt.date
    f = f[(f["date_debut"] >= start) & (f["date_debut"] <= end)]
    if rep.get("poste") and rep["poste"] != "Tous les postes" and "poste" in f:
        f = f[f["poste"].fillna("").astype(str) == str(rep["poste"])]
    return f


def _slice_aux_date(frame: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if frame is None or frame.empty or "date" not in frame:
        return frame if frame is not None else pd.DataFrame()
    f = frame.copy()
    dd = pd.to_datetime(f["date"], errors="coerce")
    f = f[dd.notna()].copy()
    f["date"] = dd[f.index].dt.date
    return f[(f["date"] >= start) & (f["date"] <= end)]


# ==================================================================
# AIDE KPI (courant / précédent / variation) — valeurs réelles
# ==================================================================
def _var(cur, prev):
    """Variation % ; None si indéfinie (division par zéro / absence)."""
    try:
        cur = float(cur); prev = float(prev)
    except (TypeError, ValueError):
        return None
    if prev is None or prev == 0 or pd.isna(prev):
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def _fr0(v) -> str:
    try:
        return f"{int(float(v)):,}".replace(",", "\u00a0")
    except (TypeError, ValueError):
        return "n/d"


def _fr1(v) -> str:
    try:
        return f"{float(v):,.1f}".replace(",", "\u00a0")
    except (TypeError, ValueError):
        return "n/d"


def _fmt_tonnes(v) -> str:
    try:
        return f"{float(v):,.0f}".replace(",", "\u00a0") + " t"
    except (TypeError, ValueError):
        return "n/d"


def _var_text(var, good_when_up=True, unit="%"):
    """Texte lisible d'une variation ; None si indisponible."""
    if var is None:
        return None
    delta = f"{var:+.{1}f}".replace(".", ",").replace("+", "+").replace("-", "−")
    return f"{delta} {unit}"


# ==================================================================
# SECTIONS — chacune renvoie {kpis, fig, table, insuffisant}
# ==================================================================
def _sec_escales(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("escales")
    kpis = [
        {"label": "Total escales", "value": _fr0(k["escales"]),
         "prev": _fr0(kp["escales"]), "var": var, "up_good": True},
    ]
    fig = escales_views.fig_evolution(ctx["prepared_all"], int(ctx["period"]["start"].year))
    table = pd.DataFrame([
        {"Période": r["periode"], "Escales": r["escales"]}
        for r in rv_monthly_escales(ctx)] or [])
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_trafic(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("tonnage")
    kpis = [
        {"label": "Volume total", "value": _fmt_tonnes(k["tonnage"]),
         "prev": _fmt_tonnes(kp["tonnage"]), "var": var, "up_good": True},
    ]
    year = int(ctx["period"]["start"].year)
    fig = evolution_views.fig_evo_by_type(ctx["prepared_all"], year)
    iec = ctx["prepared"].groupby("type_trafic")["tonnage"].sum() \
        if not ctx["prepared"].empty else pd.Series(dtype=float)
    rows = []
    for t in ["Import", "Export", "Cabotage"]:
        rows.append({"Type": t, "Tonnage": float(iec.get(t, 0.0))})
    table = pd.DataFrame(rows)
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_attente(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("attente")
    kpis = [
        {"label": "Attente moyenne", "value": _fr1(k["attente"]) + " h",
         "prev": _fr1(kp["attente"]) + " h", "var": var, "up_good": False},
    ]
    sel = {"year": int(ctx["period"]["start"].year), "months": ctx.get("filters_applied", {}).get("months") or [],
           "poste": ctx.get("filters_applied", {}).get("poste"),
           "type_navire": ctx.get("filters_applied", {}).get("type_navire"),
           "navire": ctx.get("filters_applied", {}).get("navire"),
           "operateur": ctx.get("filters_applied", {}).get("operateur"),
           "marchandise": ctx.get("filters_applied", {}).get("marchandise")}
    prep = attente_views.prepare(ctx["prepared_all"])
    fig = attente_views.fig_evolution(prep, sel)
    dist = attente_views.distribution_data(attente_views.filtered(prep, sel))
    table = dist if not dist.empty else pd.DataFrame()
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_consignation(ctx):
    c, cp = ctx.get("consig", pd.DataFrame()), ctx.get("consig_prev", pd.DataFrame())
    kcur = consignation_views.kpi_block(c) if not c.empty else {"count": 0, "duree_moy": 0.0}
    kprev = consignation_views.kpi_block(cp) if not cp.empty else {"count": 0, "duree_moy": 0.0}
    var = _var(kcur.get("count"), kprev.get("count"))
    year = int(ctx["period"]["start"].year)
    months = ctx.get("filters_applied", {}).get("months") or None
    kpis = [
        {"label": "Consignations", "value": _fr0(kcur.get("count")),
         "prev": _fr0(kprev.get("count")), "var": var, "up_good": None},
        {"label": "Durée moyenne", "value": _fr1(kcur.get("duree_moy")) + " h",
         "prev": _fr1(kprev.get("duree_moy")) + " h", "var": None, "up_good": None},
    ]
    fig, _t = consignation_views.fig_by_poste(c, year, months) if not c.empty else (None, "")
    table = None
    if not c.empty:
        tb, _ = consignation_views.events_table(c, year, months, None, None, limit=12)
        table = tb
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_navires(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("navires")
    kpis = [
        {"label": "Navires différents", "value": _fr0(k["navires"]),
         "prev": _fr0(kp["navires"]), "var": var, "up_good": True},
    ]
    fig = navires_views.fig_evolution(ctx["prepared_all"], int(ctx["period"]["start"].year))
    table = None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_sejour_quai(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("sejour_quai")
    kpis = [
        {"label": "Séjour moyen à quai", "value": _fr1(k["sejour_quai"]) + " h",
         "prev": _fr1(kp["sejour_quai"]) + " h", "var": var, "up_good": False},
    ]
    year = int(ctx["period"]["start"].year)
    months = ctx.get("filters_applied", {}).get("months") or []
    p = ctx.get("filters_applied", {}).get("poste")
    m = ctx.get("filters_applied", {}).get("marchandise")
    fig = None
    if p and p != "Tous les postes":
        fig, _ = sejour_views.fig_poste(ctx["prepared_all"], year, months, [p])
    elif m and m != "Toutes":
        fig, _ = sejour_views.fig_marchandise(ctx["prepared_all"], year, months, [m])
    else:
        fig, _ = sejour_views.fig_poste(ctx["prepared_all"], year, months, None)
    table = None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_productivite(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("productivite")
    kpis = [
        {"label": "Productivité globale", "value": _fr1(k["productivite"]) + " t/h",
         "prev": _fr1(kp["productivite"]) + " t/h", "var": var, "up_good": True},
    ]
    year = int(ctx["period"]["start"].year)
    ms = monthly_series(ctx["prepared_all"], "tonnage", "sum")
    fig = _line_series(ms, year, "Productivité mensuelle — tonnage (t)",
                       "Tonnes")
    table = None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_consignation_evo(ctx):
    c, cp = ctx.get("consig", pd.DataFrame()), ctx.get("consig_prev", pd.DataFrame())
    year = int(ctx["period"]["start"].year)
    months = ctx.get("filters_applied", {}).get("months") or None
    # Fusion N + N-1 pour une vraie courbe
    merged = pd.concat([c.assign(ylab=str(year)), cp.assign(ylab=str(year - 1))],
                       ignore_index=True) if not cp.empty else c
    fig = None
    if not merged.empty:
        fig, _t = consignation_evo_views.fig_evo_globale(merged, year, None, None)
    kcur = consignation_views.kpi_block(c) if not c.empty else {"count": 0}
    kprev = consignation_views.kpi_block(cp) if not cp.empty else {"count": 0}
    var = _var(kcur.get("count"), kprev.get("count"))
    kpis = [
        {"label": "Consignations", "value": _fr0(kcur.get("count")),
         "prev": _fr0(kprev.get("count")), "var": var, "up_good": None},
    ]
    table = None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_trafic_traite(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("tonnage")
    kpis = [
        {"label": "Volume total traité", "value": _fmt_tonnes(k["tonnage"]),
         "prev": _fmt_tonnes(kp["tonnage"]), "var": var, "up_good": True},
    ]
    year = int(ctx["period"]["start"].year)
    months = ctx.get("filters_applied", {}).get("months") or []
    m = ctx.get("filters_applied", {}).get("marchandise")
    fig = trafic_views.fig_evolution(
        ctx["prepared_all"], year, gran="Année complète", month=0,
        types=None, marches=[m] if m and m != "Toutes" else None)
    iec = ctx["prepared"].groupby("type_trafic")["tonnage"].sum() \
        if not ctx["prepared"].empty else pd.Series(dtype=float)
    table = pd.DataFrame([{"Type": t, "Tonnage": float(iec.get(t, 0.0))}
                          for t in ["Import", "Export", "Cabotage"]])
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_sejour_port(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("sejour_port")
    kpis = [
        {"label": "Séjour moyen au port", "value": _fr1(k["sejour_port"]) + " h",
         "prev": _fr1(kp["sejour_port"]) + " h", "var": var, "up_good": False},
    ]
    year = int(ctx["period"]["start"].year)
    ms = monthly_series(ctx["prepared_all"], "port_h", "mean")
    fig = _line_series(ms, year, "Séjour au port mensuel — moyenne (h)", "Heures")
    table = None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_occupation(ctx):
    k = ctx["kpis"]; kp = ctx["kpis_prev"]
    var = ctx["variations"].get("occupation")
    kpis = [
        {"label": "Taux d'occupation moyen", "value": _fr1(k["occupation"]) + " %",
         "prev": _fr1(kp["occupation"]) + " %", "var": var, "up_good": None},
    ]
    year = int(ctx["period"]["start"].year)
    months = ctx.get("filters_applied", {}).get("months") or []
    p = ctx.get("filters_applied", {}).get("poste")
    fig = None
    try:
        c = occupation_views.compute(ctx["prepared_all"], year, months,
                                     [] if not p or p == "Tous les postes" else [p])
        fig = c.get("fig_state")
    except Exception:
        fig = None
    # Table par poste
    postes = ctx["postes"]
    cols = [c for c in ["poste", "occupation", "escales", "tonnage", "productivite"]
            if c in postes.columns]
    table = postes[cols].reset_index(drop=True) if not postes.empty else None
    return {"kpis": kpis, "fig": fig, "table": table}


def _sec_incidents(ctx):
    i, ip = ctx.get("incidents", pd.DataFrame()), ctx.get("incidents_prev", pd.DataFrame())
    ncur = len(i); nprev = len(ip)
    var = _var(ncur, nprev)
    kpis = [
        {"label": "Incidents", "value": _fr0(ncur), "prev": _fr0(nprev),
         "var": var, "up_good": False},
    ]
    year = int(ctx["period"]["start"].year)
    fig = None
    if not i.empty:
        fig = _incidents_by_month(i, year)
    table = None
    if not i.empty:
        keep = [c for c in ["date", "nature", "lieu", "consistance"] if c in i.columns]
        table = i[keep].head(20).reset_index(drop=True)
    return {"kpis": kpis, "fig": fig, "table": table}


# ==================================================================
# FIGURE UTILITAIRES (construites depuis les données réelles)
# ==================================================================
def _line_series(ms: pd.DataFrame, year: int, title: str, unit: str):
    """Courbe N vs N-1 depuis une série monthly_series(year, month, value)."""
    if ms is None or ms.empty:
        return None
    fig = go.Figure()
    for yr in sorted(ms["year"].unique()):
        sub = ms[ms["year"] == yr].sort_values("month")
        if sub.empty or sub["value"].fillna(0).sum() == 0:
            continue
        fig.add_trace(go.Scatter(
            x=[MONTHS_FR[int(m) - 1] for m in sub["month"]], y=sub["value"],
            name=str(yr), mode="lines+markers",
            line=dict(color=COLOR_SEQ[0] if yr == year else COLOR_SEQ[2],
                      width=3 if yr == year else 2,
                      dash="solid" if yr == year else "dot")))
    if not fig.data:
        return None
    fig.update_layout(title=title, height=360, yaxis_title=unit, xaxis_title=None,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return _apply_theme(fig)


def _incidents_by_month(i: pd.DataFrame, year: int):
    if i.empty or "month" not in i:
        return None
    g = i.groupby("month").size().reindex(range(1, 13), fill_value=0)
    fig = go.Figure(go.Bar(x=[MONTHS_FR[m - 1] for m in g.index], y=g.values,
                           marker_color="#ff6077", marker_line_width=0))
    fig.update_layout(title=f"Incidents par mois — {year}", height=320, yaxis_title=None)
    return _apply_theme(fig)


# ==================================================================
# CATALOGUE DES SECTIONS (ordre = 12 domaines du Dashboard)
# ==================================================================
SECTIONS = [
    ("escales", "⚓", "1. Escales", _sec_escales),
    ("trafic", "📈", "2. Évolution du trafic", _sec_trafic),
    ("attente", "⏳", "3. Attente / Mouillage", _sec_attente),
    ("consignation", "🔒", "4. Consignation", _sec_consignation),
    ("navires", "🚢", "5. Navires", _sec_navires),
    ("sejour_quai", "⏱️", "6. Séjour à quai", _sec_sejour_quai),
    ("productivite", "⚙️", "7. Productivité", _sec_productivite),
    ("consignation_evo", "📉", "8. Évolution de la consignation", _sec_consignation_evo),
    ("trafic_traite", "📦", "9. Trafic traité", _sec_trafic_traite),
    ("sejour_port", "🛳️", "10. Séjour au port", _sec_sejour_port),
    ("occupation", "🏗️", "11. Taux d'occupation", _sec_occupation),
    ("incidents", "🚨", "12. Incidents", _sec_incidents),
]

SECTION_KEYS = [s[0] for s in SECTIONS]


def build_sections(ctx: dict) -> list[dict]:
    """Exécute les 12 constructeurs → liste de sections prêtes à rendre/exporter."""
    out = []
    for key, icon, title, fn in SECTIONS:
        try:
            res = fn(ctx)
        except Exception:
            res = {"kpis": [], "fig": None, "table": None}
        res["key"], res["icon"], res["title"] = key, icon, title
        out.append(res)
    return out


# ==================================================================
# FILTRES APPLIQUÉS — texte lisible pour le rapport
# ==================================================================
def filters_text(rep: dict) -> str:
    months = rep.get("months") or []
    m_txt = "Tous" if not months else " · ".join(MONTHS_FULL[m - 1] for m in sorted(months))
    parts = [
        ("Année", str(rep.get("year") or "—")),
        ("Mois", m_txt),
        ("Poste", rep.get("poste") or "Tous"),
        ("Type de navire", rep.get("type_navire") or "Tous"),
        ("Navire", rep.get("navire") or "Tous"),
        ("Opérateur", rep.get("operateur") or "Tous"),
        ("Marchandise", rep.get("marchandise") or "Toutes"),
        ("Type opération", rep.get("type_trafic") or "Tous types"),
    ]
    return " | ".join(f"{lab} : {val}" for lab, val in parts)


def rv_monthly_escales(ctx) -> list[dict]:
    if ctx["prepared"].empty:
        return []
    g = ctx["prepared"].assign(ym=ctx["prepared"]["year"].astype(str) + "-"
                               + ctx["prepared"]["month"].astype(str).str.zfill(2))
    gg = g.groupby("ym")["escale_key"].nunique().reset_index()
    return [{"periode": r["ym"], "escales": int(r["escale_key"])} for _, r in gg.iterrows()]


# ==================================================================
# EXPORTS — PDF / Excel / CSV (seulement les données réelles)
# ==================================================================
def report_excel_bytes(ctx: dict, sections: list[dict],
                       filter_text: str, generated: str) -> bytes:
    from xlsxwriter import Workbook
    from io import BytesIO
    buf = BytesIO()
    wb = Workbook(buf, {"in_memory": True})
    fmt_h = wb.add_format({"bold": True, "font_color": "#FFFFFF",
                           "bg_color": "#0B315A", "border": 1, "align": "center"})
    fmt_c = wb.add_format({"border": 1})
    fmt_b = wb.add_format({"bold": True, "font_color": "#0B315A"})
    fmt_t = wb.add_format({"num_format": "#,##0.00"})

    def _sheet(name, df, extra=None):
        import re
        safe = re.sub(r"[\[\]:*?/\\]", "-", name)[:31]
        ws = wb.add_worksheet(safe or "Feuille")
        if df is None or df.empty:
            ws.write(0, 0, "Aucune donnée.", fmt_c)
            return
        col = 0
        if extra:
            for k, v in extra:
                ws.write(0, col, str(k), fmt_b)
                ws.write(0, col + 1, str(v), fmt_c)
                col += 2
        for j, cname in enumerate(df.columns):
            ws.write(1, j, str(cname), fmt_h)
        for i, row in enumerate(df.itertuples(index=False), start=2):
            for j, val in enumerate(row):
                if isinstance(val, (float, np.floating)):
                    v = float(val)
                    if np.isnan(v) or np.isinf(v):
                        ws.write(i, j, "n/d", fmt_c)
                    else:
                        ws.write(i, j, v, fmt_t)
                else:
                    ws.write(i, j, str(val), fmt_c)

    _sheet("Synthèse", None, [
        ("Rapport", "Rapport structuré — Performance portuaire"),
        ("Filtres", filter_text),
        ("Période", f"{ctx['period']['start']} → {ctx['period']['end']}"),
        ("Généré", generated),
    ])

    krows = []
    for s in sections:
        for k in s["kpis"]:
            krows.append({"Section": s["title"], "Indicateur": k["label"],
                          "Valeur": k["value"], "N-1": k.get("prev", ""),
                          "Variation %": _var_text(k["var"])})
    _sheet("KPI", pd.DataFrame(krows))

    for s in sections:
        name = s["title"].split(". ", 1)[-1]
        _sheet(name, s["table"])

    wb.close()
    return buf.getvalue()


def report_csv_zip(ctx: dict, sections: list[dict]) -> bytes:
    from io import BytesIO
    import zipfile
    z = BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        for s in sections:
            if s["table"] is not None and not s["table"].empty:
                zf.writestr(f"{s['key']}.csv",
                            s["table"].to_csv(index=False).encode("utf-8-sig"))
        if not ctx["prepared"].empty:
            zf.writestr("donnees_filtrees.csv",
                        ctx["prepared"].to_csv(index=False).encode("utf-8-sig"))
    return z.getvalue()


def _png_bytes(fig) -> bytes | None:
    if fig is None:
        return None
    try:
        from components.dashboard.report_capture import fig_to_png_bytes
        return fig_to_png_bytes(fig, width=860, height=360)
    except Exception:
        return None


def report_pdf_bytes(ctx: dict, sections: list[dict],
                     filter_text: str, generated: str) -> bytes:
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)
    NAVY = colors.HexColor("#0B315A")
    BLUE = colors.HexColor("#1c8ccd")
    GREY = colors.HexColor("#5a6b7d")

    def _style(name, sz, col, leading=None, align="normal"):
        return ParagraphStyle(name=name, fontSize=sz,
                              textColor=col if col is not None else colors.black,
                              leading=leading or sz + 4,
                              alignment={"center": 1, "right": 2,
                                         "left": 0}.get(align, 0))

    s_brand = _style("brand", 13, NAVY, 16)
    s_date = _style("date", 8, GREY, 10, "right")
    s_h1 = _style("h1", 16, NAVY, 20)
    s_h2 = _style("h2", 12, NAVY, 15)
    s_body = _style("body", 9, None, 13)
    s_kpi = _style("kpi", 10, NAVY, 12)
    s_filtre = _style("filtre", 8, GREY, 10)

    story = []
    head = Table([
        [Paragraph("<b>ANP — PORT JORF LASFAR</b><br/>Rapport structuré · "
                   "Performance portuaire", s_brand),
         Paragraph(f"Généré le : {generated}", s_date)],
    ], colWidths=[130 * mm, 70 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLUE),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story.append(head)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Rapport structuré — Performance portuaire", s_h1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>Période :</b> {ctx['period']['start']} → "
                           f"{ctx['period']['end']}", s_body))
    story.append(Paragraph(f"<b>Filtres appliqués :</b> {filter_text}", s_filtre))
    story.append(Spacer(1, 4 * mm))

    for s in sections:
        story.append(Paragraph(f"{s['title']}", s_h2))
        # KPI inline
        if s["kpis"]:
            parts = []
            for k in s["kpis"]:
                var = _var_text(k.get("var"))
                parts.append(f"<b>{k['label']} :</b> {k['value']}"
                             + (f"  (N-1 : {k.get('prev', '')})"
                                + (f" · {var}" if var else "")
                                if k.get("prev") is not None else ""))
            story.append(Paragraph(" &nbsp; ".join(parts), s_kpi))
        if s["fig"] is not None:
            png = _png_bytes(s["fig"])
            if png:
                from io import BytesIO as _B
                img = Image(_B(png))
                w = 175 * mm
                h = 90 * mm
                img._w, img._h = w, h
                img.hAlign = "CENTER"
                story.append(Spacer(1, 3 * mm))
                story.append(img)
        if s["table"] is not None and not s["table"].empty:
            cols = list(s["table"].columns)
            data = [[str(c) for c in cols]]
            for row in s["table"].head(12).itertuples(index=False):
                data.append([str(v) for v in row])
            t = Table(data, colWidths=[(182 * mm) / max(len(cols), 1)] * len(cols),
                      repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bcd6ef")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#eef4fa")]),
            ]))
            story.append(Spacer(1, 3 * mm))
            story.append(t)
        story.append(Spacer(1, 5 * mm))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(A4[0] / 2, 8 * mm,
                                 "Rapport structuré automatique — Port Analytics Studio · ANP")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"p. {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm,
                            rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()

