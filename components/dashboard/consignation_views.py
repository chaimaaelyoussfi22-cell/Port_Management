# -*- coding: utf-8 -*-
"""Moteur des cartes « CONSIGNATION » / « ÉVOLUTION DE LA CONSIGNATION ».

Données : table consignations (date_debut, date_fin, heure_debut, heure_fin,
poste, motif, nombre_heures, observations).
Aucune dépendance Streamlit — données + figures Plotly pures, testables.

Fidélité aux données réelles :
  · toutes les périodes / postes / causes proviennent du dataset ;
  · aucun mois, poste ou cause inventé ;
  · le graphique « Consignations par poste » reporte seul l'ordre métier
    de référence (POSTE_ORDER) avec des valeurs 0 pour les postes absents ;
  · « PORT » (consignation globale du port) n'est jamais supprimé.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.analysis_views import COLOR_SEQ, _apply_theme

CUR_COLOR = "#62ddff"      # année N
PREV_COLOR = "#f2b84b"     # année N-1
POSTE_PORT = "PORT"
NO_CAUSE = "(cause non renseignée)"

# ―― Ordre métier de référence pour l'axe Y du graphique « par poste » ――
POSTE_ORDER = [
    "1N", "1S", "1Bis", "1Ter", "2N", "2Bis", "2Ter", "4", "4Bis", "5",
    "6", "7", "3", "3Bis", "9", "14S", "8", "14N", "16N", "16S",
    "11_12", "13", "10",
]

# ―― Catégories de durée (Courte / Moyenne / Longue) ――
DUR_CAT_SHORT = "Courte durée"
DUR_CAT_MEDIUM = "Moyenne durée"
DUR_CAT_LONG = "Longue durée"
DUR_CAT_OPTIONS = ["Toutes", DUR_CAT_SHORT, DUR_CAT_MEDIUM, DUR_CAT_LONG]
DUR_CAT_COLORS = {DUR_CAT_SHORT: "#2dd4bf", DUR_CAT_MEDIUM: "#f2b84b",
                  DUR_CAT_LONG: "#ff6077"}


def _fmt_j(v: float) -> str:
    return f"{v:g}".replace(".", ",")


# ==================================================================
# PRÉPARATION
# ==================================================================
def prepare_consignations(raw: pd.DataFrame) -> pd.DataFrame:
    """Nettoie et prépare les consignations pour l'analyse (aucune donnée fictive)."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    f = raw.copy()
    f["date_debut"] = pd.to_datetime(f["date_debut"], errors="coerce")
    f["date_fin"] = pd.to_datetime(f["date_fin"], errors="coerce")
    f = f[f["date_debut"].notna()]
    if f.empty:
        return pd.DataFrame()
    f["year"] = f["date_debut"].dt.year.astype(int)
    f["month"] = f["date_debut"].dt.month.astype(int)

    for col in ("poste", "motif", "observations"):
        if col in f.columns:
            f[col] = f[col].fillna("").astype(str).str.strip()
        else:
            f[col] = ""

    # Durée réelle : nombre_heures si renseigné (> 0), sinon écart date_fin − date_debut.
    f["nombre_heures"] = pd.to_numeric(f["nombre_heures"], errors="coerce")
    hours_known = f["nombre_heures"].fillna(0) > 0
    hrs = f["nombre_heures"].where(hours_known)
    diff_h = (f["date_fin"] - f["date_debut"]).dt.total_seconds() / 3600.0
    f["duree_h"] = hrs.fillna(diff_h.fillna(0)).clip(lower=0)
    f["duree_jours"] = (f["duree_h"] / 24).round(2)

    f["is_port"] = f["poste"].str.upper() == POSTE_PORT
    return f


def available_years(frame: pd.DataFrame) -> list[int]:
    if frame.empty:
        return []
    return sorted(frame["year"].unique().tolist(), reverse=True)


def available_months(frame: pd.DataFrame, year: int) -> list[int]:
    if frame.empty:
        return []
    sub = frame[frame["year"] == year]
    return sorted(sub["month"].unique().tolist())


def available_causes(frame: pd.DataFrame, year: int,
                     months: list[int] | None) -> list[str]:
    """Causes réellement présentes (motif vide → « cause non renseignée »)."""
    f = frame[frame["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    return sorted({c if c else NO_CAUSE for c in f["motif"].unique()})


def available_postes(frame: pd.DataFrame, year: int | None,
                     months: list[int] | None) -> list[str]:
    """Postes réellement présents (valeur « PORT » comprise)."""
    f = frame
    if year is not None:
        f = f[f["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    return sorted({p for p in f["poste"].unique() if p})


# ==================================================================
# DURÉE — CATÉGORIES COURTE / MOYENNE / LONGUE (seuils réels)
# ==================================================================
def duration_boundaries(frame: pd.DataFrame) -> dict | None:
    """Seuils Courte/Moyenne/Longue = 33e & 66e percentiles des durées réelles
    positives. Si les durées sont dégénérées, repli sur la médiane. Repli final :
    None (aucune durée positive réelle → tout est « Courte durée »)."""
    if frame is None or frame.empty:
        return None
    dur = pd.to_numeric(frame["duree_jours"], errors="coerce")
    dur = dur[dur > 0].dropna()
    if dur.empty:
        return None
    b1 = float(dur.quantile(1 / 3))
    b2 = float(dur.quantile(2 / 3))
    if b1 == b2:
        return {"b1": float(dur.median()), "b2": None}
    return {"b1": b1, "b2": b2}


def cat_duration(frame: pd.DataFrame, boundaries: dict | None,
                 inplace: bool = False) -> pd.DataFrame:
    """Affecte duree_cat (Courte/Moyenne/Longue) sur la base des seuils réels."""
    out = frame if inplace else frame.copy()
    d = out["duree_jours"]
    if boundaries is None or boundaries.get("b1") is None:
        out["duree_cat"] = DUR_CAT_SHORT
    elif boundaries.get("b2") is None:
        out["duree_cat"] = np.where(d > boundaries["b1"],
                                    DUR_CAT_LONG, DUR_CAT_SHORT)
    else:
        out["duree_cat"] = np.select(
            [d <= boundaries["b1"], d <= boundaries["b2"]],
            [DUR_CAT_SHORT, DUR_CAT_MEDIUM], default=DUR_CAT_LONG)
    return out


def format_boundaries_note(boundaries: dict | None) -> str:
    if boundaries is None or boundaries.get("b1") is None:
        return "Catégories de durée : aucune durée positive réelle"
    b1 = _fmt_j(boundaries["b1"])
    b2 = boundaries.get("b2")
    if b2 is None:
        return f"Courte ≤ {b1} j · Longue > {b1} j (médiane réelle)"
    return (f"Courte ≤ {b1} j · Moyenne {b1}–{_fmt_j(b2)} j · "
            f"Longue > {_fmt_j(b2)} j (33e & 66e percentiles réels)")


# ==================================================================
# KPI BAND — diagnostic global (toutes les données réelles)
# ==================================================================
def kpi_block(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"count": 0, "duree_moy": 0.0, "duree_tot": 0.0,
                "n_postes": 0, "debut": None, "fin": None}
    d = frame["duree_jours"]
    postes = {p for p in frame["poste"] if p}
    return {
        "count": int(len(frame)),
        "duree_moy": round(float(d.mean()), 1) if len(d) else 0.0,
        "duree_tot": round(float(d.sum()), 1),
        "n_postes": len(postes),
        "debut": frame["date_debut"].min(),
        "fin": frame["date_debut"].max(),
    }


# ==================================================================
# ① CONSIGNATIONS PAR POSTE — barres horizontales, ordre métier stable
# ==================================================================
def fig_by_poste(frame: pd.DataFrame, year: int,
                 months: list[int] | None) -> tuple[go.Figure | None, str]:
    """Barres horizontales : axe Y dans l'ordre métier POSTE_ORDER, valeurs 0
    pour les postes sans consignation sur la période. Les postes réels hors
    liste de référence (ex. PORT) sont ajoutés en fin d'axe."""
    title = "Consignations par poste"
    f = frame[frame["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return None, title
    counts = f["poste"].value_counts()
    real = sorted(p for p in counts.index if p)
    # Ordre métier complet (postes sans consignation → 0), puis postes réels
    # hors liste de référence (ex. PORT) ajoutés en fin d'axe.
    cats = list(POSTE_ORDER)
    for p in real:
        if p not in cats:
            cats.append(p)
    vals = [int(counts.get(p, 0)) for p in cats]
    if not vals or sum(vals) == 0:
        return None, title
    text = [str(v) if v else "" for v in vals]
    fig = go.Figure(go.Bar(
        x=vals, y=cats, orientation="h",
        marker_color=[COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(cats))],
        text=text, textposition="outside", cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x} consignation(s)<extra></extra>"))
    fig.update_layout(height=max(300, 26 * len(cats) + 90),
                      xaxis_title="Nombre de consignations",
                      yaxis=dict(categoryorder="array", categoryarray=cats),
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title


# ==================================================================
# ② CAUSES PRINCIPALES — donut
# ==================================================================
def fig_causes(frame: pd.DataFrame, year: int, months: list[int] | None,
               cause_filter: list[str] | None) -> tuple[go.Figure | None, str]:
    """Donut des causes réellement présentes (top individuel + regroupement
    « Autres » si trop de causes). Filtre cause : affiche uniquement les causes
    sélectionnées quand le filtre est non vide."""
    title = "Causes principales"
    f = frame[frame["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        return None, title
    g = f["motif"].replace("", NO_CAUSE).value_counts()
    if cause_filter:
        g = g[g.index.isin(cause_filter)]
    if g.empty:
        return None, title
    g = g.sort_values(ascending=False)
    labels = g.index.tolist()
    values = g.values.tolist()
    colors = [COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(labels))]
    total = int(sum(values))
    if len(labels) > 7:
        labels = labels[:6] + ["Autres"]
        values = values[:6] + [sum(values[6:])]
        colors = colors[:6] + ["#7fb7d8"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.42,
        marker=dict(colors=colors),
        textinfo="label", textposition="outside",
        hovertemplate="<b>%{label}</b><br>%{value} événement(s) (%{percent})"
                      "<extra></extra>"))
    fig.add_annotation(
        text=f"<b>{total}</b><br><span style='font-size:10px'>événements</span>",
        x=0.5, y=0.5, showarrow=False, font=dict(color="#eaf6ff", size=15))
    fig.update_layout(height=330, showlegend=False,
                      margin=dict(l=30, r=30, t=8, b=8))
    return _apply_theme(fig), title


# ==================================================================
# ③ DISTRIBUTION DES DURÉES — classes adaptées aux données réelles
# ==================================================================
def _classes_duree(jours: pd.Series) -> tuple[list[str], list[int]]:
    """Classes de durée adaptées au max réel : <0,5 j · 0,5–1 j · 1–2 j ·
    2–4 j · … · > X j."""
    dur = jours[jours >= 0].dropna()
    if dur.empty:
        return [], []
    maxd = float(dur.max())
    edges = [0.0, 0.5, 1.0, 2.0]
    while edges[-1] < maxd and len(edges) < 7:
        edges.append(edges[-1] * 2.0)
    labels = [f"< {_fmt_j(edges[1])} j"]
    for lo, hi in zip(edges[1:-1], edges[2:]):
        labels.append(f"{_fmt_j(lo)} – {_fmt_j(hi)} j")
    labels.append(f"> {_fmt_j(edges[-1])} j")
    counts = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        if hi is None:
            counts.append(int((dur >= lo).sum()))
        else:
            counts.append(int(((dur >= lo) & (dur < hi)).sum()))
    return labels, counts


def fig_duration_distrib(frame: pd.DataFrame, year: int,
                         months: list[int] | None,
                         cause_filter: list[str] | None,
                         height: int = 330) -> tuple[go.Figure | None, str]:
    """Barres de distribution des durées réelles par classe."""
    title = "Distribution des durées"
    f = frame[frame["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if cause_filter:
        f = f[f["motif"].replace("", NO_CAUSE).isin(cause_filter)]
    if f.empty:
        return None, title
    labels, counts = _classes_duree(f["duree_jours"])
    if not labels:
        return None, title
    fig = go.Figure(go.Bar(
        x=labels, y=counts,
        marker_color=[COLOR_SEQ[i % len(COLOR_SEQ)] for i in range(len(labels))],
        text=[str(c) if c else "" for c in counts], textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y} consignation(s)<extra></extra>"))
    fig.update_layout(height=height, xaxis_title="Durée de la consignation",
                      yaxis_title="Nombre de consignations",
                      yaxis_rangemode="nonnegative",
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title


# ==================================================================
# ④ CONSIGNATION PORT — vue globale (poste = PORT)
# ==================================================================
def port_stats(frame: pd.DataFrame, year: int,
               months: list[int] | None) -> dict:
    port = frame[frame["is_port"]]
    f = port[port["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    return {
        "count": int(len(f)),
        "duree_moy": round(float(f["duree_jours"].mean()), 1) if len(f) else 0.0,
        "duree_tot": round(float(f["duree_jours"].sum()), 1),
        "total_all": int(len(port)),
    }


def fig_port(frame: pd.DataFrame, year: int,
             months: list[int] | None) -> tuple[go.Figure | None, str]:
    """Mini-barres des événements PORT par période réellement disponible.
    Repli sur toutes les périodes réelles si la période filtrée est vide,
    afin de ne jamais masquer les consignations PORT."""
    title = "Évolution des consignations PORT"
    port = frame[frame["is_port"]]
    if port.empty:
        return None, title
    f = port[port["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if f.empty:
        f = port
        g = f.groupby(["year", "month"]).size()
        labels = [f"{MONTHS_FR[int(m) - 1]} {int(y)}" for (y, m) in g.index]
    else:
        g = f.groupby("month").size()
        labels = [MONTHS_FR[int(m) - 1] for m in g.index]
    g = g[g > 0]
    if g.empty:
        return None, title
    fig = go.Figure(go.Bar(
        x=labels, y=g.values, marker_color="#ff6077",
        text=g.values, textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y} événement(s) PORT<extra></extra>"))
    fig.update_layout(height=260, yaxis_title="Événements PORT",
                      yaxis_rangemode="nonnegative",
                      margin=dict(l=8, r=14, t=8, b=8))
    return _apply_theme(fig), title


# ==================================================================
# ⑤ TABLEAU DES ÉVÉNEMENTS
# ==================================================================
def _fmt_dt(dt, heure) -> str:
    if dt is None or pd.isna(dt):
        return "—"
    try:
        if isinstance(heure, str) and ":" in heure:
            hh, mm = heure.split(":")[:2]
            dt = dt.replace(hour=int(hh) % 24, minute=int(mm) % 60)
    except (ValueError, TypeError):
        pass
    return dt.strftime("%d/%m/%Y %H:%M")


def events_table(frame: pd.DataFrame, year: int | None,
                 months: list[int] | None,
                 poste_filter: list[str] | None,
                 cause_filter: list[str] | None,
                 limit: int = 12) -> tuple[pd.DataFrame, int]:
    """Table compacte : Poste, Consignation, Déconsignation, Cause, Durée,
    Mouvement (observations). Seules les données réelles, triées par date."""
    f = frame
    if year is not None:
        f = f[f["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if poste_filter:
        f = f[f["poste"].isin(poste_filter)]
    if cause_filter:
        f = f[f["motif"].replace("", NO_CAUSE).isin(cause_filter)]
    total = int(len(f))
    if total == 0:
        return pd.DataFrame(), 0
    f2 = f.sort_values("date_debut", ascending=False).head(int(limit))

    heure_d = f2["heure_debut"] if "heure_debut" in f2.columns else None
    heure_f = f2["heure_fin"] if "heure_fin" in f2.columns else None
    obs = f2["observations"] if "observations" in f2.columns else None

    rows = pd.DataFrame({
        "Poste": [p if p else "—" for p in f2["poste"]],
        "Consignation": [_fmt_dt(d, hd) for d, hd in
                         zip(f2["date_debut"], heure_d if heure_d is not None else [None] * len(f2))],
        "Déconsignation": [_fmt_dt(d, hf) for d, hf in
                           zip(f2["date_fin"], heure_f if heure_f is not None else [None] * len(f2))],
        "Cause": [c if c else NO_CAUSE for c in f2["motif"]],
        "Durée": ["{} j".format(f"{v:.1f}".replace(".", ",")) for v in f2["duree_jours"]],
        "Mouvement": [m if m else "—" for m in
                      (obs if obs is not None else [None] * len(f2))],
    })
    return rows, total