# -*- coding: utf-8 -*-
"""Moteur du « Centre de rapports — Performance Portuaire » (page /rapports).

COHÉRENCE ABSOLUE AVEC LE DASHBOARD :
  - build_context() (components/dashboard/analytics.py) est réutilisée telle
    quelle : mêmes KPI, mêmes variations N vs N-1, mêmes statistiques par
    poste, mêmes alertes — aucune deuxième logique de calcul.
  - Les exports (Excel structuré, CSV, PDF) sont générés depuis ce SEUL
    contexte. Aucune donnée fictive, aucun KPI inventé.
Aucune dépendance Streamlit ici (moteur testable).
"""

import calendar
from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd

from components.dashboard.analytics import build_context
from components.dashboard.sejour_views import _poste_label

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)
    PDF_AVAILABLE = True
except Exception:  # pragma: no cover - reportlab optionnel
    PDF_AVAILABLE = False


POSTE_CLASSES = {
    "underused": "Sous-utilisé",
    "optimal": "Optimisé",
    "busy": "Très sollicité",
    "saturated": "Début saturation",
}


# ==================================================================
# FORMATAGE
# ==================================================================
def fmt_int(v) -> str:
    """Entier lisible avec séparateur de milliers non cassants."""
    try:
        return f"{int(float(v)):,}".replace(",", "\u00a0")
    except (TypeError, ValueError):
        return "0"


def fmt_tonnes(v) -> str:
    return f"{float(v or 0):,.0f}".replace(",", "\u00a0") + " t"


# ==================================================================
# PÉRIODE ET FILTRES
# ==================================================================
def period_bounds(year: int, months: list | None = None,
                  custom: tuple | None = None) -> tuple[date, date]:
    """Bornes de la période : personnalisée, sinon année + mois éventuels."""
    if custom:
        return date.fromisoformat(str(custom[0])), date.fromisoformat(str(custom[1]))
    ms = sorted(months) if months else []
    m0, m1 = (ms[0], ms[-1]) if ms else (1, 12)
    return date(year, m0, 1), date(year, m1, calendar.monthrange(year, m1)[1])


def period_label(start: date, end: date) -> str:
    return f"{start.strftime('%d/%m/%Y')} → {end.strftime('%d/%m/%Y')}"


def choices(ops: pd.DataFrame) -> dict:
    """Valeurs UNIQUEMENT présentes en base — filtres dynamiques."""
    out = {"years": [], "postes": [], "marchandises": [],
           "navires": [], "trafic": ["Import", "Export", "Cabotage"]}
    if ops is None or ops.empty:
        return out
    d = pd.to_datetime(ops["date"], errors="coerce")
    out["years"] = sorted(d.dt.year.dropna().astype(int).unique().tolist(), reverse=True)

    def uniq(col: str) -> list:
        if col not in ops:
            return []
        return sorted(ops[col].dropna().astype(str)
                      .loc[lambda s: s.str.strip() != ""].unique().tolist())

    out["postes"] = uniq("poste")
    out["marchandises"] = uniq("type_marchandise")
    out["navires"] = uniq("navire")
    return out


def filter_rapport(ops: pd.DataFrame, start: date, end: date,
                   postes: list[str] | None = None,
                   trafic: str | None = None,
                   marchandise: str | None = None,
                   navire: str | None = None) -> pd.DataFrame:
    """Filtre PÉRIODE + dimensions sur les opérations brutes.

    Sémantique identique à helpers.apply_filters (dashboard) : même colonne
    de date, mêmes colonnes poste / type_marchandise / navire / type_operation.
    """
    f = ops.copy()
    if f.empty:
        return f
    d = pd.to_datetime(f["date"], errors="coerce")
    f = f[d.notna()].copy()
    f["date"] = d[f.index].dt.date
    if start:
        f = f[f["date"] >= start]
    if end:
        f = f[f["date"] <= end]
    if postes:
        f = f[f["poste"].fillna("").astype(str).isin(postes)]
    if marchandise and marchandise != "Toutes":
        f = f[f["type_marchandise"].fillna("").astype(str) == marchandise]
    if navire and navire != "Tous":
        f = f[f["navire"].fillna("").astype(str) == navire]
    if trafic and trafic != "Tous types":
        f = f[f["type_operation"].fillna("").astype(str)
              .str.lower().str.startswith(trafic.lower()[:4])]
    return f


def report_context(ops_filtered: pd.DataFrame,
                   start: date, end: date) -> dict:
    """Contexte UNIQUE du rapport — exactement les définitions du dashboard."""
    filters = {"period": "Période rapport", "start": start, "end": end,
               "poste": None, "operateur": None, "marchandise": None,
               "type_navire": None, "type_trafic": None}
    return build_context(ops_filtered, filters)


# ==================================================================
# EXECUTIVE SUMMARY — calculée, jamais inventée
# ==================================================================
def executive_summary(ctx: dict) -> str:
    k = ctx["kpis"]
    top = ctx["postes"].sort_values("occupation", ascending=False)
    top = top.iloc[0] if not top.empty else None
    s = (f"Durant la période sélectionnée, le port a enregistré "
         f"{fmt_int(k['escales'])} escales représentant {fmt_tonnes(k['tonnage'])} "
         f"de trafic. Le taux d'occupation moyen des postes atteint "
         f"{k['occupation']:.1f} %. ")
    if top is not None:
        s += (f"Le poste le plus sollicité est {top['poste']} avec "
              f"{top['occupation']:.1f} % d'occupation. ")
    s += f"Le temps d'attente moyen est de {k['attente']:.1f} h."
    return s


def points_forts(ctx: dict) -> list[str]:
    out: list[str] = []
    v, k, p = ctx["variations"], ctx["kpis"], ctx["postes"]
    if v.get("tonnage") and v["tonnage"] > 0:
        out.append(f"Trafic en hausse : tonnage {v['tonnage']:+.1f} % vs période précédente.")
    if v.get("escales") and v["escales"] > 0:
        out.append(f"Activité des escales en progression ({v['escales']:+.1f} %).")
    if v.get("attente") is not None and v["attente"] < 0:
        out.append(f"Temps d'attente amélioré : {k['attente']:.1f} h "
                   f"({v['attente']:+.1f} % vs période précédente).")
    if v.get("sejour_quai") is not None and v["sejour_quai"] < 0:
        out.append(f"Séjour à quai réduit : {k['sejour_quai']:.1f} h "
                   f"({v['sejour_quai']:+.1f} %).")
    if v.get("productivite") and v["productivite"] > 0:
        out.append(f"Productivité moyenne en hausse ({v['productivite']:+.1f} %).")
    if not p.empty:
        zone = p[(p["occupation"] >= 50) & (p["occupation"] < 70)]
        if not zone.empty:
            best = zone.sort_values("productivite", ascending=False).iloc[0]
            out.append(f"Poste {best['poste']} le plus performant en zone optimale "
                       f"({best['occupation']:.0f} % d'occupation, "
                       f"{best['productivite']:.0f} t/h).")
    return out or ["Aucun point fort statistiquement significatif détecté."]


def points_vigilance(ctx: dict) -> list[str]:
    out: list[str] = []
    v, k, p = ctx["variations"], ctx["kpis"], ctx["postes"]
    if not p.empty:
        for _, r in p[p["occupation"] >= 80].head(3).iterrows():
            out.append(f"Poste {r['poste']} en début de saturation "
                       f"({r['occupation']:.1f} % d'occupation).")
    if v.get("attente") is not None and v["attente"] >= 25 and k["attente"] >= 6:
        out.append(f"Attente au mouillage en forte hausse ({k['attente']:.1f} h, "
                   f"{v['attente']:+.1f} %).")
    if v.get("tonnage") is not None and v["tonnage"] <= -10:
        out.append(f"Décroissance du trafic : tonnage {v['tonnage']:.1f} % "
                   f"vs période précédente.")
    if v.get("productivite") is not None and v["productivite"] <= -15:
        out.append(f"Productivité moyenne en baisse ({v['productivite']:+.1f} %).")
    if v.get("sejour_quai") is not None and v["sejour_quai"] >= 20:
        out.append(f"Séjour à quai en hausse ({k['sejour_quai']:.1f} h, "
                   f"{v['sejour_quai']:+.1f} %).")
    if not p.empty:
        for _, r in p[(p["ecart_sejour"].notna()) & (p["ecart_sejour"] > 20)].head(2).iterrows():
            out.append(f"Séjour anormal au poste {r['poste']} "
                       f"(+{r['ecart_sejour']:.0f} % vs moyenne port).")
    if ctx["occ_diagnostics"]:
        for d in ctx["occ_diagnostics"][:1]:
            out.append(f"Incohérence de données — poste {d['poste']} "
                       f"({d['taux_calcule_%']:.0f} %).")
    return out or ["Aucun point de vigilance particulier détecté."]


# ==================================================================
# COMPARAISON PÉRIODE PRÉCÉDENTE (définition du dashboard)
# ==================================================================
COMPARE_ORDER = [
    ("tonnage", "Tonnage total", "t"),
    ("escales", "Nombre d'escales", "escales"),
    ("navires", "Navires différents", "navires"),
    ("attente", "Temps d'attente moyen", "h"),
    ("sejour_quai", "Séjour moyen à quai", "h"),
    ("sejour_port", "Séjour moyen au port", "h"),
    ("productivite", "Productivité", "t/h"),
    ("occupation", "Taux d'occupation", "%"),
]


def comparison_table(ctx: dict) -> list[dict]:
    """8 KPI : période courante, période précédente, variation relative (%).

    Les variations sont EXACTEMENT compare_kpis() du dashboard (relatives à la
    valeur précédente) — aucune seconde formule.
    """
    k, kp, v = ctx["kpis"], ctx["kpis_prev"], ctx["variations"]
    rows = []
    for key, label, unit in COMPARE_ORDER:
        rows.append({"kpi": label, "unite": unit,
                     "courant": k.get(key), "precedent": kp.get(key),
                     "variation": v.get(key)})
    return rows


# ==================================================================
# TABLES DU RAPPORT (prévisualisation + exports)
# ==================================================================
def postes_report(ctx: dict) -> pd.DataFrame:
    """Par poste : occupation, statut, escales, tonnage, séjour, attente,
    productivité, diagnostic — ordre canonique puis occupation."""
    p = ctx["postes"].copy()
    if p.empty:
        return p
    at = ctx["prepared"].groupby("poste_norm")["attente_h"].mean().round(1)
    p["attente_moyenne"] = p["poste"].map(at).fillna(0.0)
    p["statut"] = p["classe"].map(POSTE_CLASSES).fillna(p["classe"])
    p["poste_disp"] = p["poste"].map(_poste_label)

    from components.dashboard.occupation_views import POSTE_ORDER_OCC_KEYS
    order = {k: i for i, k in enumerate(POSTE_ORDER_OCC_KEYS)}
    p["_ord"] = p["poste"].map(lambda x: order.get(x, 10000))
    p = p.sort_values(["_ord", "occupation"])
    p = p.drop(columns="_ord")
    return p.reset_index(drop=True)


def marchandises_report(ctx: dict) -> pd.DataFrame:
    c, pv = ctx["prepared"], ctx["prepared_prev"]
    cols = ["marchandise_norm", "tonnage", "part_%", "Import", "Export",
            "Cabotage", "escales", "precedent", "evolution"]
    if c.empty or "marchandise_norm" not in c.columns:
        return pd.DataFrame(columns=cols)
    g = (c.groupby("marchandise_norm")
         .agg(tonnage=("tonnage", "sum"),
              escales=("escale_key", "nunique")).reset_index())
    g = g[g["tonnage"] > 0]
    total = float(g["tonnage"].sum()) or 1.0
    g["part_%"] = g["tonnage"] / total * 100
    piv = c.pivot_table(index="marchandise_norm", columns="type_trafic",
                        values="tonnage", aggfunc="sum", fill_value=0.0)
    for t in ("Import", "Export", "Cabotage"):
        g[t] = piv[t] if t in piv else 0.0
    prev_tot = (pv.groupby("marchandise_norm")["tonnage"].sum()
                if not pv.empty and "marchandise_norm" in pv
                else pd.Series(dtype=float))
    g["precedent"] = g["marchandise_norm"].map(prev_tot).fillna(0.0)
    g["evolution"] = np.where(g["precedent"] > 0,
                              (g["tonnage"] - g["precedent"]) / g["precedent"] * 100,
                              np.nan)
    g = g.sort_values("tonnage", ascending=False)
    return g[cols].reset_index(drop=True)


def iec_report(ctx: dict) -> pd.DataFrame:
    c = ctx["prepared"]
    cols = ["type_trafic", "tonnage", "part_%", "escales", "navires"]
    if c.empty or "type_trafic" not in c.columns:
        return pd.DataFrame(columns=cols)
    g = (c.groupby("type_trafic").agg(
        tonnage=("tonnage", "sum"), escales=("escale_key", "nunique"),
        navires=("navire_name", "nunique")).reset_index())
    total = float(g["tonnage"].sum()) or 1.0
    g["part_%"] = g["tonnage"] / total * 100
    for t in ("Import", "Export", "Cabotage"):
        if t not in g["type_trafic"].tolist():
            g = pd.concat([g, pd.DataFrame([{"type_trafic": t, "tonnage": 0.0,
                                             "escales": 0, "navires": 0,
                                             "part_%": 0.0}])], ignore_index=True)
    return g[cols].reset_index(drop=True)


def monthly_report(ctx: dict) -> pd.DataFrame:
    """Niveau mensuel : escales, navires, tonnage, attente, occupation."""
    c, iv = ctx["prepared"], ctx["intervals"]
    cols = ["periode", "escales", "navires", "tonnage", "attente_h", "occupation_%"]
    if c.empty:
        return pd.DataFrame(columns=cols)
    c = c.assign(_ym=c["year"].astype(str) + "-" + c["month"].astype(str).str.zfill(2))
    g = (c.groupby("_ym").agg(escales=("escale_key", "nunique"),
                              navires=("navire_name", "nunique"),
                              tonnage=("tonnage", "sum"),
                              attente_h=("attente_h", "mean")).reset_index())
    occ = pd.DataFrame()
    if iv is not None and not iv.empty:
        from components.dashboard.occupation import monthly_occupancy
        mo = monthly_occupancy(iv)
        if not mo.empty:
            mo = mo.assign(_ym=mo["year"].astype(str) + "-" + mo["month"].astype(str).str.zfill(2))
            occ = mo.groupby("_ym")["taux_%"].mean().reset_index()
    if not occ.empty:
        g = g.merge(occ, on="_ym", how="left")
    else:
        g["taux_%"] = 0.0
    g = g.rename(columns={"_ym": "periode", "taux_%": "occupation_%"})
    g["attente_h"] = g["attente_h"].round(1)
    g["occupation_%"] = g["occupation_%"].round(1)
    return g[cols].reset_index(drop=True)


def details_report(ctx: dict) -> pd.DataFrame:
    cols = ["date", "navire", "poste", "type_operation", "type_trafic",
            "type_marchandise", "tonnage", "attente_h", "quai_h", "port_h",
            "escale_key"]
    df = ctx["prepared"]
    if df.empty:
        return df
    keep = [cl for cl in cols if cl in df.columns]
    return df[keep].reset_index(drop=True)


def escales_report(ctx: dict) -> pd.DataFrame:
    df = ctx["prepared"]
    if df.empty:
        return df
    cols = ["date", "escale_key", "navire_name", "poste_norm", "type_trafic",
            "type_marchandise", "tonnage", "attente_h", "quai_h", "port_h"]
    keep = [cl for cl in cols if cl in df.columns]
    return df[keep].sort_values("date").reset_index(drop=True)


# ==================================================================
# EXPORT EXCEL (structuré, plusieurs feuilles)
# ==================================================================
def excel_export(ctx: dict, filter_text: str, generated: str) -> bytes:
    from xlsxwriter import Workbook
    buf = BytesIO()
    wb = Workbook(buf, {"in_memory": True})
    fmt_h = wb.add_format({"bold": True, "font_color": "#FFFFFF",
                           "bg_color": "#0B315A", "border": 1, "align": "center"})
    fmt_c = wb.add_format({"border": 1})
    fmt_b = wb.add_format({"bold": True, "font_color": "#0B315A"})
    fmt_t = wb.add_format({"num_format": "#,##0.00"})

    def _sheet(name: str, df: pd.DataFrame):
        ws = wb.add_worksheet(name)
        if df is None or df.empty:
            ws.write(0, 0, "Aucune donnée.", fmt_c)
            return
        for j, col in enumerate(df.columns):
            ws.write(0, j, str(col), fmt_h)
        for i, row in enumerate(df.itertuples(index=False), start=1):
            for j, val in enumerate(row):
                if isinstance(val, (float, np.floating)):
                    v = float(val)
                    if np.isnan(v) or np.isinf(v):
                        ws.write(i, j, "n/d", fmt_c)
                    else:
                        ws.write(i, j, v, fmt_t)
                elif isinstance(val, (int, np.integer, np.bool_)):
                    ws.write(i, j, int(val), fmt_c)
                else:
                    ws.write(i, j, str(val), fmt_c)

    # --- Synthèse (texte) ---
    ws = wb.add_worksheet("Synthèse")
    lines = ["CENTRE DE RAPPORTS — PERFORMANCE PORTUAIRE",
             "Port Jorf Lasfar · ANP",
             f"Filtres : {filter_text}",
             f"Période : {ctx['period']['start']} → {ctx['period']['end']}",
             f"Généré le : {generated}", "",
             "SYNTHÈSE DE LA PÉRIODE", executive_summary(ctx), "",
             "POINTS FORTS"]
    for i, l in enumerate(lines):
        ws.write(i, 0, l, fmt_b if i in (0, 6, 9) else fmt_c)
    base = len(lines) + 1
    for i, l in enumerate(points_forts(ctx)):
        ws.write(base + i, 0, f"• {l}", fmt_c)
    ws.write(base + len(points_forts(ctx)) + 1, 0, "POINTS DE VIGILANCE", fmt_b)
    base2 = base + len(points_forts(ctx)) + 2
    for i, l in enumerate(points_vigilance(ctx)):
        ws.write(base2 + i, 0, f"• {l}", fmt_c)

    # --- KPI ---
    kpi_df = pd.DataFrame([
        {"KPI": r["kpi"], "Unité": r["unite"],
         "Période courante": r["courant"],
         "Période précédente": r["precedent"],
         "Variation %": r["variation"] if r["variation"] is None
         else round(r["variation"], 1)}
        for r in comparison_table(ctx)])
    _sheet("KPI", kpi_df)

    # --- Escales / Trafic / Occupation / Marchandises / IEC / Détails ---
    _sheet("Escales", escales_report(ctx))
    _sheet("Trafic", monthly_report(ctx))
    postes_df = postes_report(ctx) if not ctx["postes"].empty else pd.DataFrame()
    if not postes_df.empty:
        cols_p = [c for c in ["poste_disp", "occupation", "statut", "classe",
                              "escales", "tonnage", "sejour_moyen",
                              "attente_moyenne", "productivite",
                              "ecart_sejour", "diagnostic", "diag_classe"]
                  if c in postes_df.columns]
        _sheet("Occupation_Postes", postes_df[cols_p])
    else:
        _sheet("Occupation_Postes", pd.DataFrame())
    _sheet("Marchandises", marchandises_report(ctx))
    _sheet("Import_Export_Cabotage", iec_report(ctx))
    _sheet("Données détaillées", details_report(ctx))

    wb.close()
    return buf.getvalue()


# ==================================================================
# EXPORT CSV (brut filtré)
# ==================================================================
def csv_export(ctx: dict) -> bytes:
    return details_report(ctx).to_csv(index=False).encode("utf-8-sig")


# ==================================================================
# EXPORT PDF (reportlab — mise en page uniquement, aucun calcul dupliqué)
# ==================================================================
def _fr_num(x) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/d"
    try:
        return f"{float(x):,.1f}".replace(",", "\u00a0").replace(".", ",")
    except (TypeError, ValueError):
        return "n/d"


def _fr_pct(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/d"
    v = float(x)
    return f"{'+' if v >= 0 else ''}{v:.1f}".replace(".", ",") + " %"


def _pdf_table(data: list[list], widths: list, header_bg) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bcd6ef")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#eef4fa")]),
    ]
    t.setStyle(TableStyle(style))
    return t


def pdf_export(ctx: dict, filter_text: str, generated: str) -> bytes:
    """PDF professionnel : identité ANP, titre, période, filtres, KPI,
    synthèse, points forts/vigilance, tableaux. Chiffres issus du contexte."""
    if not PDF_AVAILABLE:
        raise RuntimeError("reportlab non disponible.")

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
    s_brand_sub = _style("brand_sub", 8, GREY, 10)
    s_date = _style("date", 8, GREY, 10, "right")
    s_h1 = _style("h1", 16, NAVY, 20)
    s_h2 = _style("h2", 12, NAVY, 15)
    s_h3 = _style("h3", 10, BLUE, 13)
    s_body = _style("body", 9, None, 13)
    s_bullet = _style("bullet", 9, None, 12)

    story = []
    brand = Table([
        [Paragraph("<b>ANP — PORT JORF LASFAR</b><br/>"
                   "Centre de rapports · Performance portuaire", s_brand),
         Paragraph(f"Généré le : {generated}", s_date)],
    ], colWidths=[120 * mm, 82 * mm])
    brand.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLUE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(brand)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Rapport de performance portuaire", s_h1))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"<b>Période :</b> {ctx['period']['start']} → {ctx['period']['end']}",
        s_body))
    story.append(Paragraph(f"<b>Filtres :</b> {filter_text}", s_body))
    story.append(Spacer(1, 4 * mm))

    # --- KPI ---
    story.append(Paragraph("KPI Performance", s_h2))
    krows = [["Indicateur", "Période courante", "Période précédente", "Variation"]]
    for r in comparison_table(ctx):
        krows.append([r["kpi"],
                      _fr_num(r["courant"]) + (" " + r["unite"] if r["unite"] else ""),
                      _fr_num(r["precedent"]) + (" " + r["unite"] if r["unite"] else ""),
                      _fr_pct(r["variation"])])
    story.append(_pdf_table(krows, [60 * mm, 42 * mm, 42 * mm, 28 * mm], NAVY))
    story.append(Spacer(1, 5 * mm))

    # --- Synthèse ---
    story.append(Paragraph("Synthèse de la période", s_h2))
    story.append(Paragraph(executive_summary(ctx), s_body))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Points forts", s_h2))
    for b in points_forts(ctx):
        story.append(Paragraph("• " + b, s_bullet))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Points de vigilance", s_h2))
    for b in points_vigilance(ctx):
        story.append(Paragraph("• " + b, s_bullet))
    story.append(Spacer(1, 5 * mm))

    # --- Occupation des postes ---
    postes_df = postes_report(ctx) if not ctx["postes"].empty else pd.DataFrame()
    if not postes_df.empty:
        story.append(Paragraph("État d'occupation des postes", s_h2))
        pcols = [c for c in ["poste_disp", "occupation", "statut", "escales",
                             "tonnage", "sejour_moyen", "attente_moyenne",
                             "productivite", "diagnostic"]
                 if c in postes_df.columns]
        data = [["Poste", "Occup.", "Statut", "Escales", "Tonnage (t)",
                 "Séjour (h)", "Attente (h)", "Prod. (t/h)", "Diagnostic"]]
        for r in postes_df[["occupation"]].itertuples():
            pass
        for r in postes_df.itertuples(index=False):
            data.append([
                r.poste_disp if hasattr(r, "poste_disp") else r.poste,
                _fr_num(r.occupation),
                r.statut,
                str(int(r.escales)),
                _fr_num(r.tonnage),
                _fr_num(r.sejour_moyen),
                _fr_num(getattr(r, "attente_moyenne", 0.0)),
                _fr_num(r.productivite),
                str(r.diagnostic),
            ])
        story.append(_pdf_table(data, widths=[18 * mm, 14 * mm, 22 * mm, 14 * mm,
                                              16 * mm, 15 * mm, 15 * mm, 15 * mm,
                                              33 * mm], header_bg=NAVY))
        story.append(Spacer(1, 5 * mm))

    # --- Marchandises ---
    mdf = marchandises_report(ctx)
    if not mdf.empty:
        story.append(Paragraph("Principales marchandises", s_h2))
        mdata = [["Marchandise", "Tonnage (t)", "Part %", "Import", "Export",
                  "Cabotage", "Évolution"]]
        for r in mdf.head(12).to_dict("records"):
            mdata.append([str(r["marchandise_norm"]), _fr_num(r["tonnage"]),
                          _fr_num(r["part_%"]),
                          _fr_num(r["Import"]), _fr_num(r["Export"]),
                          _fr_num(r["Cabotage"]), _fr_pct(r["evolution"])])
        story.append(_pdf_table(mdata, widths=[42 * mm, 25 * mm, 18 * mm, 25 * mm,
                                               25 * mm, 25 * mm, 22 * mm], header_bg=NAVY))
        story.append(Spacer(1, 5 * mm))

    # --- Trafic mensuel ---
    tdf = monthly_report(ctx)
    if not tdf.empty:
        story.append(Paragraph("Évolution temporelle", s_h2))
        tdata = [["Période", "Escales", "Navires", "Tonnage (t)",
                  "Attente (h)", "Occupation %"]]
        for r in tdf.to_dict("records"):
            tdata.append([str(r["periode"]), str(int(r["escales"])),
                          str(int(r["navires"])),
                          _fr_num(r["tonnage"]), _fr_num(r["attente_h"]),
                          _fr_num(r["occupation_%"])])
        story.append(_pdf_table(tdata, widths=[28 * mm, 28 * mm, 28 * mm, 38 * mm,
                                               30 * mm, 30 * mm], header_bg=NAVY))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(
            A4[0] / 2, 8 * mm,
            "Document généré automatiquement — Port Analytics Studio · ANP")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"p. {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm,
                            rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm)
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()