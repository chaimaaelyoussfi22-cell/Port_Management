# -*- coding: utf-8 -*-
"""Moteur de la page dédiée « Analyse du taux d'occupation » (dashboard Power BI).

Métrique : taux d'occupation = temps occupé / (jours × 24h) × 100.
Règle : union dédupliquée des intervalles par poste (pas de double comptage).
Aucune dépendance Streamlit ici — données + figures Plotly pures, testables.

Visualisations :
  ① État d'occupation de chaque poste (barres occupé/disponible)
  ② Évolution mensuelle par poste N vs N-1
  ③ Répartition des postes par statut
  ④ Insights automatiques
"""

import calendar

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, UNSPECIFIED, _apply_theme)
from components.dashboard.occupation import (
    quay_intervals, monthly_occupancy, merge_union, poste_order)
from components.dashboard.sejour_views import _poste_label

STATUS_COLORS = {
    "underused": "#56a8ff",
    "optimal": "#32d2a4",
    "busy": "#f2b84b",
    "saturated": "#ff6077",
}
STATUS_LABELS = {
    "underused": "Sous-utilisé",
    "optimal": "Optimisé",
    "busy": "Très sollicité",
    "saturated": "Début saturation",
}
STATUS_ICONS = {
    "underused": "🔵",
    "optimal": "🟢",
    "busy": "🟠",
    "saturated": "🔴",
}

# Référentiel « État d'occupation » : ordre d'affichage EXACT demandé.
# Ordre métier (différent de POSTES_VALIDES/POSTE_REFERENTIEL) :
# 1N, 1S, 1Bis, 1Ter, 2N, 2Bis, 2Ter, 3, 3Bis, 4, 4Bis, 5, 6, 7,
# 8, 9, 10, 11_12, 13, 14N, 14S, 16N, 16S.
POSTE_ORDER_OCC = ["1N", "1S", "1Bis", "1Ter", "2N", "2Bis", "2Ter",
                   "3", "3Bis", "4", "4Bis", "5", "6", "7",
                   "8", "9", "10", "11_12", "13", "14N", "14S", "16N", "16S"]
POSTE_ORDER_OCC_KEYS = [p.upper() for p in POSTE_ORDER_OCC]


# ==================================================================
# CLASSIFICATION
# ==================================================================
def classify(taux: float) -> str:
    """Statut métier : 🔵 < 50 % · 🟢 50 à < 70 % · 🟠 70 à < 80 % · 🔴 ≥ 80 %."""
    if taux < 50:
        return "underused"
    if taux < 70:
        return "optimal"
    if taux < 80:
        return "busy"
    return "saturated"


# ==================================================================
# KPI
# ==================================================================
def kpi_block(monthly: pd.DataFrame, year: int) -> dict:
    """KPI globaux : occupation moyenne, nb postes, nb postes critiques."""
    if monthly.empty:
        return {"avg_occ": 0.0, "n_postes": 0, "n_critical": 0, "n_busy": 0}
    cur = monthly[monthly["year"] == year]
    if cur.empty:
        return {"avg_occ": 0.0, "n_postes": 0, "n_critical": 0, "n_busy": 0}
    avg_occ = round(float(cur["taux_%"].mean()), 1)
    postes = cur["poste"].nunique()
    latest = cur.groupby("poste").last().reset_index()
    n_critical = int((latest["taux_%"] > 80).sum())
    n_busy = int(((latest["taux_%"] >= 70) & (latest["taux_%"] <= 80)).sum())
    return {"avg_occ": avg_occ, "n_postes": postes,
            "n_critical": n_critical, "n_busy": n_busy}


# ==================================================================
# ÉTAT D'OCCUPATION (référentiel complet : tableau + barres)
# ==================================================================
def _state_data(monthly: pd.DataFrame, year: int,
                months: list[int],
                poste_filter: list[str]) -> pd.DataFrame | None:
    """Données « état d'occupation » : UNE LIGNE PAR POSTE DU RÉFÉRENTIEL.

    Colonnes : poste (clé norm.), poste_disp (libellé exact), taux (%, réel),
    statut, duree_h, heures_dispo. Les postes du référentiel SANS données sur
    le périmètre restent présents (taux 0 %, statut « underused », heures
    disponibles du périmètre) — aucun poste n'est retiré par le filtrage.
    Ordre fixe (POSTE_ORDER_OCC), jamais recalculé selon les valeurs.
    Retourne None si aucun volume de données n'est exploitable.
    """
    if monthly.empty:
        return None
    cur = monthly[monthly["year"] == year]
    if months:
        cur = cur[cur["month"].isin(months)]
    if cur.empty:
        return None

    agg = cur.groupby("poste").agg(
        duree_h=("duree_h", "sum"),
        heures_dispo=("heures_dispo", "sum")).reset_index()
    agg["taux"] = agg.apply(
        lambda r: round(r["duree_h"] / r["heures_dispo"] * 100, 1)
        if r["heures_dispo"] > 0 else 0.0, axis=1)
    agg["statut"] = agg["taux"].apply(classify)

    # Postes cibles : sous-ensemble filtré sinon les 23 du référentiel,
    # TOUJOURS dans l'ordre exact de POSTE_ORDER_OCC (jamais trié par taux).
    if poste_filter:
        keys = [p.strip().upper() for p in poste_filter]
    else:
        keys = list(POSTE_ORDER_OCC_KEYS)
    keys = [k for k in POSTE_ORDER_OCC_KEYS if k in keys]
    if not keys:
        return None

    # Heures calendaires du périmètre (année × mois retenus) — pour les postes
    # du référentiel absents des données (statut « sous-utilisé », 0 %).
    scope_hours = sum(
        calendar.monthrange(int(y), int(m))[1] * 24
        for y, m in set(zip(cur["year"], cur["month"])))

    g = agg.set_index("poste").reindex(keys).reset_index()
    g["duree_h"] = g["duree_h"].fillna(0.0)
    g["heures_dispo"] = g["heures_dispo"].fillna(float(scope_hours))
    g["taux"] = g["taux"].fillna(0.0)
    g["statut"] = g["statut"].fillna("underused")
    g["poste_disp"] = g["poste"].map(_poste_label)
    return g[["poste", "poste_disp", "taux", "statut",
              "duree_h", "heures_dispo"]]


def _fig_state(monthly: pd.DataFrame, year: int,
               months: list[int],
               poste_filter: list[str]) -> tuple[go.Figure | None, str]:
    """Barres horizontales occupé/disponible par poste (référentiel complet).

    Axe des Y : les postes du référentiel dans l'EXACT ordre demandé
    (POSTE_ORDER_OCC), « tous » sélectionné inclus — un poste du référentiel
    sans activité dans le périmètre reste affiché à 0 % (heures disponibles
    du périmètre conservées pour le hover).
    """
    title = "État d'occupation des postes"
    g = _state_data(monthly, year, months, poste_filter)
    if g is None or g.empty:
        return None, title

    colors_occ = [STATUS_COLORS.get(s, "#56a8ff") for s in g["statut"]]
    dispo_pct = (100 - g["taux"]).clip(lower=0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=g["poste_disp"].astype(str), x=g["taux"],
        orientation="h", name="Occupé",
        marker_color=colors_occ, marker_line_width=0,
        text=[f"{t:.0f} %" if t > 0 else "" for t in g["taux"]],
        textposition="outside", cliponaxis=False,
        customdata=np.stack([
            g["duree_h"].values,
            g["heures_dispo"].values - g["duree_h"].values,
            [STATUS_ICONS.get(s, "") for s in g["statut"]],
            [STATUS_LABELS.get(s, "") for s in g["statut"]],
        ], axis=-1),
        hovertemplate="<b>%{y}</b><br>"
                      "Occupé : %{customdata[0]:,.0f} h<br>"
                      "Disponible : %{customdata[1]:,.0f} h<br>"
                      "Taux : %{x:.1f} %<br>"
                      "%{customdata[2]} %{customdata[3]}"
                      + "<extra></extra>"))
    fig.add_trace(go.Bar(
        y=g["poste_disp"].astype(str), x=dispo_pct,
        orientation="h", name="Disponible",
        marker_color="rgba(255,255,255,0.08)", marker_line_width=0,
        hoverinfo="skip"))
    fig.update_layout(
        barmode="stack",
        height=max(420, 40 * len(g) + 150),
        xaxis_title="Taux d'occupation (%)",
        xaxis_range=[0, max(100.0, float(g["taux"].max()) + 8.0)],
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        showlegend=True)
    return _apply_theme(fig), title


def state_table_html(df: pd.DataFrame) -> str:
    """HTML compact « Poste | Taux d'occupation | Statut » (Smart Port).

    Génère le tableau avec TOUTES les lignes de df (référentiel complet,
    ordre conservé) ; valeurs réelles du DataFrame, jamais inventées ;
    jauge mini + % à droite, badge coloré selon `statut` (CSS .occ-wrap).
    """
    rows = []
    for r in df.itertuples():
        t = float(r.taux)
        pct = f"{round(t)} %"
        icon = STATUS_ICONS.get(r.statut, "")
        label = STATUS_LABELS.get(r.statut, r.statut)
        width = min(t, 100.0)
        rows.append(
            f'<tr data-status="{r.statut}">'
            f'<td class="occ-poste" title="{r.poste}">{r.poste_disp}</td>'
            f'<td class="occ-taux">'
            f'<span class="occ-gauge"><i style="width:{width:.1f}%"></i></span>'
            f'<b>{pct}</b></td>'
            f'<td class="occ-stat"><span class="occ-badge">{icon} {label}</span></td>'
            f'</tr>')
    head = ('<thead><tr><th>Poste</th>'
            '<th class="occ-th-taux">Taux d\'occupation</th>'
            '<th>Statut</th></tr></thead>')
    return ('<div class="occ-wrap"><table>' + head + '<tbody>'
            + "".join(rows) + '</tbody></table></div>')


# ==================================================================
# ÉVOLUTION MENSUELLE PAR POSTE (N vs N-1)
# ==================================================================
def _fig_evolution(monthly: pd.DataFrame, year: int,
                   months: list[int],
                   poste_filter: list[str]) -> tuple[go.Figure | None, str]:
    """Courbes d'évolution du taux d'occupation par poste, N vs N-1.

    Un poste = UNE couleur (N en trait plein, N-1 en pointillés) ;
    postes affichés dans l'ordre naturel du quai ; la légende permet
    d'activer/désactiver chaque poste (N et N-1 ensemble).
    """
    title = f"Évolution du taux d'occupation — {year} vs {year - 1}"
    if monthly.empty:
        return None, title

    fig = go.Figure()
    has_data = False

    postes_to_show = poste_order(monthly["poste"])
    if poste_filter:
        postes_to_show = [p for p in postes_to_show if p in poste_filter]
    if not postes_to_show:
        return None, title

    for idx, poste in enumerate(postes_to_show):
        pm = monthly[monthly["poste"] == poste].sort_values("month")
        if pm.empty:
            continue

        cur = pm[pm["year"] == year]
        prev = pm[pm["year"] == year - 1]

        if months:
            cur = cur[cur["month"].isin(months)]
            prev = prev[prev["month"].isin(months)]

        color = COLOR_SEQ[idx % len(COLOR_SEQ)]
        if not cur.empty:
            labels = [MONTHS_FR[int(m) - 1] for m in cur["month"]]
            fig.add_trace(go.Scatter(
                x=labels, y=cur["taux_%"],
                name=f"{poste}",
                mode="lines+markers",
                line=dict(color=color, width=2.6),
                marker=dict(size=5, color=color),
                legendgroup=poste,
                hovertemplate=f"<b>{poste} {year}</b><br>"
                              "%{x}<br>Taux : %{y:.1f} %<extra></extra>"))
            has_data = True

        if not prev.empty:
            labels_prev = [MONTHS_FR[int(m) - 1] for m in prev["month"]]
            fig.add_trace(go.Scatter(
                x=labels_prev, y=prev["taux_%"],
                name=f"{poste} ({year - 1})",
                mode="lines+markers",
                line=dict(color=color, width=1.8, dash="dot"),
                marker=dict(size=4, color=color),
                legendgroup=poste, showlegend=False, opacity=0.55,
                hovertemplate=f"<b>{poste} {year - 1}</b><br>"
                              "%{x}<br>Taux : %{y:.1f} %<extra></extra>"))
            has_data = True

    if not has_data:
        return None, title

    fig.update_layout(
        height=380,
        title=title,
        yaxis_title="Taux d'occupation (%)",
        yaxis_range=[0, max(100, float(monthly["taux_%"].max()) * 1.1)],
        legend=dict(orientation="v", yanchor="top", y=1.0,
                    xanchor="left", x=1.02, font=dict(size=10)),
        hovermode="closest",
        margin=dict(r=130, t=60))
    return _apply_theme(fig), title


# ==================================================================
# RÉPARTITION DES POSTES PAR STATUT
# ==================================================================
def _fig_status_split(monthly: pd.DataFrame, year: int) -> go.Figure | None:
    """Compte les postes par catégorie de statut."""
    if monthly.empty:
        return None
    cur = monthly[monthly["year"] == year]
    if cur.empty:
        return None
    latest = cur.groupby("poste").last().reset_index()
    latest["statut"] = latest["taux_%"].apply(classify)
    counts = latest["statut"].value_counts()
    if counts.empty:
        return None
    order = ["underused", "optimal", "busy", "saturated"]
    labels = [STATUS_ICONS.get(s, "") + " " + STATUS_LABELS.get(s, s) for s in order]
    values = [int(counts.get(s, 0)) for s in order]
    colors = [STATUS_COLORS[s] for s in order]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=colors, text=values, textposition="outside"))
    fig.update_layout(
        height=200, xaxis_title="Nombre de postes",
        xaxis=dict(tickmode="linear", dtick=1),
        margin=dict(l=10, r=10, t=10, b=10))
    return _apply_theme(fig)


# ==================================================================
# INSIGHTS
# ==================================================================
def _insights(monthly: pd.DataFrame, year: int,
              months: list[int]) -> list[str]:
    if monthly.empty:
        return ["Aucune donnée d'occupation exploitable."]
    cur = monthly[monthly["year"] == year]
    if months:
        cur = cur[cur["month"].isin(months)]
    if cur.empty:
        return [f"Aucune donnée d'occupation pour {year}."]

    latest = cur.groupby("poste").last().reset_index()
    latest["statut"] = latest["taux_%"].apply(classify)
    latest = latest.sort_values("taux_%", ascending=False)

    lines = []
    for _, row in latest.iterrows():
        p = row["poste"]
        taux = row["taux_%"]
        s = row["statut"]
        icon = STATUS_ICONS.get(s, "")
        label = STATUS_LABELS.get(s, "")
        lines.append(f"{icon} **{p}** : {taux:.0f} % → {label.lower()}")

    prev_year = monthly[monthly["year"] == year - 1]
    if months:
        prev_year = prev_year[prev_year["month"].isin(months)]
    if not prev_year.empty:
        prev_latest = prev_year.groupby("poste").last().reset_index()
        merged = latest.merge(prev_latest[["poste", "taux_%"]],
                              on="poste", suffixes=("", "_prev"))
        merged["delta"] = merged["taux_%"] - merged["taux_%_prev"]
        big = merged[merged["delta"].abs() >= 5].sort_values("delta", ascending=False)
        for _, row in big.head(3).iterrows():
            signe = "+" if row["delta"] >= 0 else ""
            trend = "📈" if row["delta"] > 0 else "📉"
            lines.append(f"{trend} **{row['poste']}** : {signe}{row['delta']:.0f} pts vs N-1")

    n_sat = int((latest["statut"] == "saturated").sum())
    if n_sat > 0:
        lines.append(f"⚠️ **{n_sat} poste(s)** dépassent le seuil de 80 %")

    return lines


# ==================================================================
# API PUBLIQUE
# ==================================================================
def compute(prepared: pd.DataFrame, year: int, months: list[int],
            poste_filter: list[str]) -> dict:
    """Calcule toutes les figures et KPI pour la page occupation."""
    from components.dashboard.occupation import quay_intervals as _qi

    ops = prepared.copy()
    intervals = _qi(ops)

    if intervals.empty:
        return {"kpi": {"avg_occ": 0.0, "n_postes": 0, "n_critical": 0, "n_busy": 0},
                "monthly": pd.DataFrame(),
                "fig_state": None, "fig_evo": None, "fig_status": None,
                "insights": ["Aucune donnée d'occupation disponible."]}

    mo = monthly_occupancy(intervals)
    kpi = kpi_block(mo, year)

    fig_state, title_state = _fig_state(mo, year, months, poste_filter)
    fig_evo, title_evo = _fig_evolution(mo, year, months, poste_filter)
    fig_status = _fig_status_split(mo, year)
    insights = _insights(mo, year, months)

    return {
        "kpi": kpi, "monthly": mo,
        "fig_state": fig_state, "title_state": title_state,
        "fig_evo": fig_evo, "title_evo": title_evo,
        "fig_status": fig_status,
        "insights": insights,
    }
