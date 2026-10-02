# -*- coding: utf-8 -*-
"""Moteur partagé des pages dédiées « Volume Trafic » et « Évolution ».

Deux pages complémentaires partagent ce moteur :
  - Volume Trafic  → COMPOSITION / RÉPARTITION du trafic (donut, barres groupées)
  - Évolution      → TENDANCES / VARIATION N vs N-1 (courbes, insights temporels)

Métrique centrale : VOLUME = SUM(tonnage), ventilé par type d'opération
Cabotage / Import / Export (couleurs métier imposées : bleu / rouge / orange).

Règles :
  - aucune liste codée en dur : marchandises, opérateurs, années, mois,
    jours et types proviennent des données réellement disponibles ;
  - combinaison absente ⇒ volume 0 (jamais de valeur inventée) ;
  - totaux = somme stricte des lignes filtrées (totaux cohérents).
"""

import calendar

import pandas as pd
import plotly.graph_objects as go

from components.dashboard.analytics import MONTHS_FR
from components.dashboard.filters import MONTHS_FR as MOIS_NOMS
from components.dashboard.escales_views import (
    COLOR_SEQ, CUR_COLOR, PREV_COLOR, UNSPECIFIED, _apply_theme)

# Types d'opération canoniques — couleurs métier imposées (bleu/rouge/orange)
OP_ORDER = ["Cabotage", "Import", "Export"]
OP_COLORS = {"Cabotage": "#56a8ff", "Import": "#ff6077", "Export": "#ff9d66"}
EXTRA_COLOR = "#8aa3bd"   # type hors taxonomy canonique (robustesse)


# ==================================================================
# PRÉPARATION
# ==================================================================
def _bt(frame: pd.DataFrame) -> pd.DataFrame:
    """Lignes exploitables : tonnage numérique + année/mois présents."""
    if frame is None:
        return pd.DataFrame()
    if frame.empty:
        return frame.head(0)
    f = frame.copy()
    f["tonnage"] = pd.to_numeric(f.get("tonnage"), errors="coerce").fillna(0.0)
    f = f[f["month"].notna() & f["year"].notna()]
    f["month"] = f["month"].astype(int)
    f["year"] = f["year"].astype(int)
    return f


def _cat(frame: pd.DataFrame, col: str) -> pd.Series:
    s = frame[col].fillna("").astype(str).str.strip()
    return s.mask(s == "", UNSPECIFIED)


def available_years(frame: pd.DataFrame) -> list[int]:
    f = _bt(frame)
    return sorted(f["year"].unique().tolist(), reverse=True) if not f.empty else []


def scope(frame: pd.DataFrame, year: int, months: list[int] = (),
          days: list[int] = ()) -> pd.DataFrame:
    """Lignes de l'année restreintes aux mois puis jours choisis ([] = tout)."""
    f = _bt(frame)
    f = f[f["year"] == year]
    if months:
        f = f[f["month"].isin(months)]
    if days and len(months) == 1 and "date" in f.columns and not f.empty:
        d = pd.to_datetime(f["date"], errors="coerce").dt.day
        f = f[d.isin(days)]
    return f.reset_index(drop=True)


def present_types(frame: pd.DataFrame, year: int, months: list[int] = ()) -> list[str]:
    """Types d'opération réellement présents sur la période (ordre métier)."""
    f = scope(frame, year, months)
    vals = set(_cat(f, "type_trafic")) if not f.empty else set()
    ordered = [t for t in OP_ORDER if t in vals]
    return ordered + sorted(vals - set(OP_ORDER))


def period_label(year: int, months: list[int] = (), days: list[int] = ()) -> str:
    """« 2025 » · « Mars 2025 » · « 2025 · Mars, Avril » (+ jours filtrés)."""
    if len(months) == 1:
        base = f"{MOIS_NOMS[months[0] - 1]} {year}"
    elif months:
        base = f"{year} · " + ", ".join(MOIS_NOMS[m - 1] for m in sorted(months))
    else:
        base = str(year)
    return base + (" · jours sélectionnés" if days else "")


def period_prev(label: str) -> str:
    """Décrémente l'année d'un libellé période (« Mars 2025 » → « Mars 2024 »)."""
    parts = label.split()
    for i, p in enumerate(parts):
        if p.isdigit() and len(p) == 4:
            parts[i] = str(int(p) - 1)
            break
    return " ".join(parts)


def _fmt_tons(v: float) -> str:
    return f"{v:,.0f}".replace(",", "\u00a0") + " t"


# ==================================================================
# KPI
# ==================================================================
def kpi_block(frame: pd.DataFrame, year: int, months: list[int] = (),
              days: list[int] = (), types: list[str] | None = None) -> dict:
    """Volumes par type + total + évolution vs MÊME période N-1."""
    def _vol(yr: int) -> tuple[float, dict]:
        f = scope(frame, yr, months, days)
        if f.empty:
            return 0.0, {}
        if types is not None:
            f = f[_cat(f, "type_trafic").isin(types)]
        total = round(float(f["tonnage"].sum()), 1) if not f.empty else 0.0
        per = {t: round(float(f.loc[_cat(f, "type_trafic") == t, "tonnage"].sum()), 1)
               for t in OP_ORDER} if not f.empty else {}
        return total, per

    total, per = _vol(year)
    prev_total, _ = _vol(year - 1)
    evolution = (round(100 * (total - prev_total) / prev_total, 1)
                 if prev_total else None)
    out = {"total": total, "prev_total": prev_total, "evolution": evolution}
    out.update({t: per.get(t, 0.0) for t in OP_ORDER})
    return out


# ==================================================================
# AGRÉGATS
# ==================================================================
def monthly_volume(frame: pd.DataFrame, year: int, types: list[str],
                   marches: list[str]) -> pd.Series:
    """Tonnage mensuel pour la sélection courante — uniquement les mois avec données."""
    f = _bt(frame)
    if f.empty or "year" not in f.columns:
        return pd.Series(dtype=float)
    f = f[f["year"] == year]
    if f.empty:
        return pd.Series(dtype=float)
    f = f[_cat(f, "type_trafic").isin(types)]
    if marches:
        f = f[_cat(f, "marchandise_norm").isin(marches)]
    if f.empty:
        return pd.Series(dtype=float)
    g = f.groupby("month")["tonnage"].sum()
    return g.round(1)


def daily_volume(frame: pd.DataFrame, year: int, month: int, types: list[str],
                 marches: list[str]) -> tuple[pd.Series, int]:
    """Tonnage par jour du mois (zéros explicites) + nb de jours couverts."""
    ndays = max(calendar.monthrange(year, month)[1],
                calendar.monthrange(year - 1, month)[1])
    f = scope(frame, year, [month])
    if f.empty or "year" not in f.columns:
        return pd.Series({d: 0.0 for d in range(1, ndays + 1)}, dtype=float), ndays
    zeros = pd.Series({d: 0.0 for d in range(1, ndays + 1)}, dtype=float)
    if f.empty or "date" not in f.columns:
        return zeros, ndays
    f = f[_cat(f, "type_trafic").isin(types)]
    if marches:
        f = f[_cat(f, "marchandise_norm").isin(marches)]
    if f.empty:
        return zeros, ndays
    day = pd.to_datetime(f["date"], errors="coerce").dt.day
    g = f.assign(day=day).dropna(subset=["day"]).groupby("day")["tonnage"].sum()
    return pd.Series({d: round(float(g.get(d, 0.0)), 1)
                      for d in range(1, ndays + 1)}), ndays


def volume_by_category_type(frame: pd.DataFrame, year: int, months: list[int],
                            types: list[str], col: str,
                            days: list[int] = ()) -> pd.DataFrame:
    """Pivot catégories × types d'opération (0 explicite), tri total desc."""
    cols = [col, *types]
    f = scope(frame, year, months, days)
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f[_cat(f, "type_trafic").isin(types)]
    if f.empty:
        return pd.DataFrame(columns=cols)
    f = f.assign(cat=_cat(f, col))
    piv = f.pivot_table(index="cat", columns="type_trafic",
                        values="tonnage", aggfunc="sum", fill_value=0.0)
    piv = piv.reindex(columns=types, fill_value=0.0).round(1)
    return (piv.assign(_tot=piv.sum(axis=1)).sort_values("_tot", ascending=False)
            .drop(columns="_tot").rename_axis(col).reset_index())


def top_cats(frame: pd.DataFrame, year: int, months: list[int],
             types: list[str], col: str, n: int) -> list[str]:
    """n premières catégories par volume sur la période (défauts intelligents)."""
    piv = volume_by_category_type(frame, year, months, types, col)
    return piv[col].head(n).tolist() if not piv.empty else []


# ==================================================================
# FIGURES
# ==================================================================
def _xy(frame: pd.DataFrame, yr: int, gran: str, month: int,
        types: list[str], mch: str | None) -> tuple[list[str], list[float]]:
    """Paire (axe X, volumes) pour une année selon la granularité choisie."""
    if gran == "Par jour":
        s, ndays = daily_volume(frame, yr, month, types, [mch] if mch else [])
        return ([f"{d:02d}/{month:02d}" for d in s.index], s.values.tolist())
    s = monthly_volume(frame, yr, types, [mch] if mch else [])
    return [MONTHS_FR[m - 1] for m in s.index], s.values.tolist()


def fig_evolution(frame: pd.DataFrame, year: int, gran: str = "Année complète",
                  month: int = 1, types: list[str] | None = None,
                  marches: list[str] | None = None) -> go.Figure | None:
    """① Courbes N vs N-1 — axe mensuel (année complète) ou journalier (mois précis).

    Une seule marchandise → courbe N pleine + N-1 en pointillés (couleurs N/N-1).
    Plusieurs marchandises → une couleur par marchandise, N pleine / N-1 pointillée.
    """
    types = types if types is not None else OP_ORDER
    marches = marches or []
    sel = marches[:1] if len(marches) <= 1 else marches
    fig = go.Figure()

    def _add(yr: int, mch: str | None, color: str, dash: str, width: float):
        xs, ys = _xy(frame, yr, gran, month, types, mch)
        if not sum(ys):
            return  # série vide → pas de courbe fantôme à zéro
        suffix = f" · {yr}"
        name = (f"{mch}{suffix}" if mch else
                f"{'Toutes marchandises' if not marches else marches[0]}{suffix}")
        fig.add_trace(go.Scatter(
            x=xs, y=ys, name=name, mode="lines+markers",
            line=dict(color=color, width=width, dash=dash),
            customdata=[_fmt_tons(v) for v in ys],
            hovertemplate="%{x}<br>%{customdata}<extra>" + name + "</extra>"))

    if len(sel) <= 1:
        _add(year, sel[0] if sel else None, CUR_COLOR, "solid", 3)
        _add(year - 1, sel[0] if sel else None, PREV_COLOR, "dot", 2)
    else:
        for i, mch in enumerate(sel):
            c = COLOR_SEQ[i % len(COLOR_SEQ)]
            _add(year, mch, c, "solid", 2.6)
            _add(year - 1, mch, c, "dot", 1.8)
    if not fig.data:
        return None
    fig.update_layout(
        height=420, yaxis_title="Volume (tonnes)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified" if gran != "Par jour" else "closest",
        yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


def fig_grouped_type(piv: pd.DataFrame, col: str, periode: str,
                     compare_piv: pd.DataFrame | None = None) -> go.Figure | None:
    """②③ Barres groupées catégories × opérations — couleurs métier fixes.

    compare_piv fourni ⇒ chaque opération est doublée :
    N plein / N-1 hachuré (même couleur), légende « … (N-1) ».
    """
    if piv is None or piv.empty:
        return None
    cats = piv[col].tolist()
    types = list(piv.columns[1:])
    grand = max(float(piv[types].to_numpy().sum()), 1.0)

    def _prev_vals(t: str) -> list[float]:
        if compare_piv is None or compare_piv.empty or t not in compare_piv.columns:
            return [0.0] * len(cats)
        s = compare_piv.set_index(col)[t]
        return [round(float(s.get(c, 0.0)), 1) for c in cats]

    fig = go.Figure()
    for t in types:
        color = OP_COLORS.get(t, EXTRA_COLOR)
        vals = [float(v) for v in piv[t]]
        fig.add_bar(x=cats, y=vals, name=t, marker_color=color,
                    marker_line_width=0,
                    customdata=[[_fmt_tons(v), round(100 * v / grand, 1), periode]
                                for v in vals],
                    hovertemplate="%{x}<br>%{customdata[2]} (%{customdata[1]} %)"
                                  "<br>%{customdata[0]}<extra>" + t + "</extra>")
        if compare_piv is not None:
            pvals = _prev_vals(t)
            fig.add_bar(x=cats, y=pvals, name=f"{t} · N-1",
                        marker=dict(color=color, opacity=0.55,
                                    pattern=dict(shape="/", solidity=0.12)),
                        marker_line_width=0,
                        customdata=[[_fmt_tons(v), "", period_prev(periode)]
                                    for v in pvals],
                        hovertemplate="%{x}<br>%{customdata[2]}"
                                      "<br>%{customdata[0]}<extra>"
                                      + t + " · N-1</extra>")
    fig.update_layout(barmode="group", height=430,
                      yaxis_title="Volume (tonnes)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02),
                      yaxis_rangemode="nonnegative")
    return _apply_theme(fig)


# ==================================================================
# DONUT — RÉPARTITION GLOBALE PAR TYPE D'OPÉRATION
# ==================================================================
def fig_donut(frame: pd.DataFrame, year: int, months: list[int] = (),
              days: list[int] = (), types: list[str] | None = None,
              periode: str = "") -> go.Figure | None:
    """Donut chart montrant la répartition Import / Export / Cabotage."""
    if frame is None or frame.empty:
        return None
    f = scope(frame, year, months, days)
    if f.empty or "type_trafic" not in f.columns:
        return None
    if types:
        f = f[_cat(f, "type_trafic").isin(types)]
    if f.empty:
        return None
    g = f.groupby(_cat(f, "type_trafic"))["tonnage"].sum().reset_index()
    g.columns = ["type", "tonnage"]
    g = g[g["tonnage"] > 0].sort_values("tonnage", ascending=False)
    if g.empty:
        return None
    total = float(g["tonnage"].sum())
    colors = [OP_COLORS.get(t, EXTRA_COLOR) for t in g["type"]]
    fig = go.Figure(go.Pie(
        labels=g["type"].tolist(),
        values=g["tonnage"].tolist(),
        hole=0.42,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="label+percent",
        texttemplate="%{label}<br>%{percent}<br>%{value:,.0f} t",
        hovertemplate="%{label}<br>%{value:,.0f} t<br>%{percent}<extra></extra>",
        textposition="outside"))
    fig.update_layout(
        height=400, showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.08),
        annotations=[dict(text=f"<b>{_fmt_tons(total)}</b><br>total",
                          x=0.5, y=0.5, font_size=14, showarrow=False)])
    return _apply_theme(fig)


# ==================================================================
# INSIGHTS — PAGE VOLUME TRAFIC (COMPOSITION)
# ==================================================================
def composition_insights(frame: pd.DataFrame, year: int, months: list[int] = (),
                         days: list[int] = (), types: list[str] | None = None) -> list[str]:
    """Insights automatiques pour la page Volume Trafic (composition)."""
    if frame is None or frame.empty:
        return ["Aucune donnée disponible pour cette période."]
    f = scope(frame, year, months, days)
    if f.empty:
        return ["Aucune donnée disponible pour cette période."]
    effective_types = types or OP_ORDER
    f_typed = f[_cat(f, "type_trafic").isin(effective_types)]
    insights: list[str] = []
    total = float(f_typed["tonnage"].sum()) if not f_typed.empty else 0.0
    if total <= 0:
        return ["Le volume total est nul pour cette sélection."]
    march_g = f_typed.groupby(_cat(f_typed, "marchandise_norm"))["tonnage"].sum()
    if not march_g.empty:
        top_m = march_g.idxmax()
        top_pct = 100 * march_g.max() / march_g.sum()
        insights.append(f"Le **{top_m}** représente **{top_pct:.1f}%** du trafic sélectionné.")
    op_g = f_typed.groupby(_cat(f_typed, "operateur_norm"))["tonnage"].sum()
    if not op_g.empty:
        top_op = op_g.idxmax()
        op_pct = 100 * op_g.max() / op_g.sum()
        insights.append(f"**{top_op}** est l'opérateur ayant le volume le plus élevé "
                        f"(**{op_pct:.1f}%** du total).")
    type_g = f_typed.groupby(_cat(f_typed, "type_trafic"))["tonnage"].sum()
    if not type_g.empty:
        top_type = type_g.idxmax()
        top_type_pct = 100 * type_g.max() / type_g.sum()
        insights.append(f"L'**{top_type}** constitue **{top_type_pct:.1f}%** du volume total.")
        if len(type_g) >= 2:
            sorted_t = type_g.sort_values(ascending=False)
            second_pct = 100 * sorted_t.iloc[1] / type_g.sum()
            insights.append(f"L'**{sorted_t.index[1]}** suit avec **{second_pct:.1f}%**.")
    return insights


# ==================================================================
# INSIGHTS — PAGE ÉVOLUTION (TENDANCES)
# ==================================================================
def evolution_insights(frame: pd.DataFrame, year: int,
                       months: list[int] = (), days: list[int] = (),
                       types: list[str] | None = None) -> list[str]:
    """Insights automatiques pour la page Évolution (tendances N vs N-1)."""
    if frame is None or frame.empty:
        return ["Aucune donnée disponible pour cette période."]
    effective_types = types or OP_ORDER
    cur = scope(frame, year, months, days)
    prev = scope(frame, year - 1, months, days)
    if effective_types:
        cur = cur[_cat(cur, "type_trafic").isin(effective_types)] if not cur.empty else cur
        prev = prev[_cat(prev, "type_trafic").isin(effective_types)] if not prev.empty else prev
    insights: list[str] = []
    cur_total = float(cur["tonnage"].sum()) if not cur.empty else 0.0
    prev_total = float(prev["tonnage"].sum()) if not prev.empty else 0.0
    if prev_total > 0:
        evo = 100 * (cur_total - prev_total) / prev_total
        if evo > 0:
            insights.append(f"📈 **Croissance de {evo:+.1f}%** vs N-1 sur la période.")
        elif evo < 0:
            insights.append(f"📉 **Baisse de {evo:+.1f}%** vs N-1 sur la période.")
        else:
            insights.append(f"➡️ Le volume est **stable** par rapport à N-1.")
    elif cur_total > 0:
        insights.append(f"📈 Volume de **{_fmt_tons(cur_total)}** (pas de données N-1).")
    cur_m = cur.groupby("month")["tonnage"].sum() if not cur.empty else pd.Series(dtype=float)
    prev_m = prev.groupby("month")["tonnage"].sum() if not prev.empty else pd.Series(dtype=float)
    if not cur_m.empty:
        best_m = int(cur_m.idxmax())
        worst_m = int(cur_m.idxmin())
        insights.append(f"🔝 **Meilleur mois** : {MOIS_NOMS[best_m - 1]} "
                        f"({_fmt_tons(cur_m.max())}).")
        if best_m != worst_m:
            insights.append(f"🔻 **Mois le plus faible** : {MOIS_NOMS[worst_m - 1]} "
                            f"({_fmt_tons(cur_m.min())}).")
    for m in range(1, 13):
        c = float(cur_m.get(m, 0))
        p = float(prev_m.get(m, 0))
        if p > 0:
            var = 100 * (c - p) / p
            if abs(var) >= 25:
                direction = "augmenté" if var > 0 else "diminué"
                insights.append(
                    f"⚠️ Variation importante en **{MOIS_NOMS[m - 1]}** : "
                    f"le trafic a {direction} de **{abs(var):.1f}%** "
                    f"vs {MOIS_NOMS[m - 1]} {year - 1}.")
    return insights if insights else ["Pas de tendance significative détectée sur cette période."]
