# -*- coding: utf-8 -*-
"""Panneau de détail d'un poste sélectionné dans le Digital Twin.

S'ouvre après la sélection d'un poste (clic sur la carte ou liste déroulante,
qui pilotent la même session). Contenu :

  - en-tête : poste, statut, badge période analysée (filtres globaux du dashboard) ;
  - fiche KPI du poste (occupation, séjour, attente, productivité, escales, tonnage)
    avec variation N-1 issue des mêmes formules que le dashboard ;
  - tableau détaillé des escales de la période.

Aucune valeur fictive : uniquement les données filtrées par le dashboard et les
formules KPI existantes (components.dashboard.analytics).
"""

from __future__ import annotations

import calendar
import html

import pandas as pd
import streamlit as st
from streamlit.components.v1 import html as st_html

from components.dashboard.analytics import (
    CLASS_COLORS,
    CLASS_LABELS,
    DIAG_STYLE,
    MONTHS_FR,
    poste_stats,
)
from components.dashboard.occupation import format_hhmmss


# ==================================================================
# AIDES FORMATAGE
# ==================================================================
def _period_label(ctx: dict) -> str:
    p = ctx.get("period", {})
    s, e = p.get("start"), p.get("end")
    if not s or not e:
        return "Toutes les données disponibles"
    last = calendar.monthrange(s.year, s.month)[1]
    whole_month = (s.day == 1) and (e.day == last)
    if whole_month:
        return f"{MONTHS_FR[s.month - 1]} {s.year}"
    return f"{s.strftime('%d/%m/%Y')} → {e.strftime('%d/%m/%Y')}"


def _dt_fmt(row, dcol: str, tcol: str) -> str:
    d = pd.to_datetime(row.get(dcol), errors="coerce")
    if pd.isna(d):
        return "—"
    return f"{d.strftime('%d/%m/%Y')} {format_hhmmss(row.get(tcol))[:5]}"


def _f1(v, unit: str = "") -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.1f}".replace(",", " ") + unit


def _f0(v, unit: str = "") -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:,.0f}".replace(",", " ") + unit


def _mean_attente(at: pd.DataFrame) -> float:
    vals = at["attente_h"].dropna() if "attente_h" in at else pd.Series(dtype=float)
    return float(vals.mean()) if len(vals) else 0.0


def _fiche_tile(label: str, value: str, cls: str, style: str | None) -> str:
    inline = f' style="{style}"' if style else ""
    b_class = f' class="{cls}"' if cls else ""
    return f'<div class="pd-kpi"><span>{label}</span><b{b_class}{inline}>{value}</b></div>'


def _prev_stats(ctx: dict) -> pd.DataFrame:
    prev = ctx.get("prepared_prev", pd.DataFrame())
    if prev is None or prev.empty:
        return pd.DataFrame()
    try:
        return poste_stats(
            prev,
            ctx.get("segments_prev", pd.DataFrame()),
            ctx.get("period", {}).get("days", 365) or 365,
            intervals=ctx.get("intervals_prev") or None,
        )
    except Exception:
        return pd.DataFrame()


# ==================================================================
# TABLEAU DES ESCALES
# ==================================================================
def _sort_escales(at_poste: pd.DataFrame) -> pd.DataFrame:
    if at_poste.empty:
        return at_poste
    dcol = "date_rade" if "date_rade" in at_poste else "date"
    return at_poste.sort_values(dcol, kind="mergesort")


def _escales_table(at_poste: pd.DataFrame, ctx: dict):
    kpis = ctx.get("kpis", {})
    port_sej = float(kpis.get("sejour_quai") or 0)
    if at_poste.empty:
        st.caption("Aucune escale sur cette période pour ce poste.")
        return
    df = pd.DataFrame({
        "N° Escale": at_poste["escale_key"],
        "Navire": at_poste.get("navire_name", at_poste.get("navire", "")),
        "Arrivée": [_dt_fmt(r, "date_rade", "heure_rade") for _, r in at_poste.iterrows()],
        "Accostage": [_dt_fmt(r, "date_accostage", "heure_accostage") for _, r in at_poste.iterrows()],
        "App. quai": [_dt_fmt(r, "date_app_quai", "heure_app_quai") for _, r in at_poste.iterrows()],
        "Trafic": at_poste.get("type_trafic", ""),
        "Marchandise": at_poste.get("marchandise_norm", ""),
        "Tonnage (t)": [f"{v:,.0f}".replace(",", " ") for v in at_poste["tonnage"].fillna(0)],
        "Séjour quai (h)": [_f1(v) for v in at_poste["quai_h"]],
        "Attente (h)": [_f1(v) for v in at_poste["attente_h"]],
        "Productivité (t/h)": [
            _f1(float(t) / float(q)) if q and q > 0 else "—"
            for t, q in zip(at_poste["tonnage"], at_poste["quai_h"])],
    })
    if port_sej:
        df["Statut"] = ["⚠️ Séjour élevé" if (q and q > 2 * port_sej) else "✓ OK"
                        for q in at_poste["quai_h"]]
    else:
        df["Statut"] = "✓ OK"
    st.dataframe(df.drop_duplicates(subset=["N° Escale", "Navire"]),
                 use_container_width=True, height=400, hide_index=True)


# ==================================================================
# RENDU PRINCIPAL
# ==================================================================
def render_poste_panel(ctx: dict):
    poste = st.session_state.get("selected_poste")
    if not poste:
        return
    if ctx.get("postes") is None or ctx["postes"].empty:
        return
    postes = ctx["postes"]
    row = postes[postes["poste"].astype(str) == str(poste)]
    if row.empty:
        return
    r = row.iloc[0]
    prepared = ctx["prepared"] if ctx.get("prepared") is not None and not ctx["prepared"].empty else pd.DataFrame()
    at_poste = prepared[prepared["poste_norm"].astype(str) == str(poste)] if not prepared.empty else prepared
    attente_cur = _mean_attente(at_poste)

    prev_stats = _prev_stats(ctx)
    prev_row = prev_stats[prev_stats["poste"].astype(str) == str(poste)] if not prev_stats.empty else pd.DataFrame()

    def _p(col, default=0.0):
        return float(prev_row.iloc[0].get(col) or default) if not prev_row.empty else None

    occ_pts = None
    if _p("occupation") is not None:
        occ_pts = round(float(r["occupation"]) - _p("occupation"), 1)

    icon = DIAG_STYLE.get(r["diag_classe"], ("📊",))[0]
    period_txt = _period_label(ctx)

    # ----- Ancrage cible du défilement automatique au clic sur la carte -----
    st.markdown('<div id="poste-detail-panel"></div>', unsafe_allow_html=True)

    # ----- En-tête + fermeture -----
    head_l, head_r = st.columns([7, 1])
    with head_l:
        st.markdown(f'''<div class="pd-head">
            <div class="pd-title">
                <span class="eyebrow">ANALYSE OPÉRATIONNELLE · DIGITAL TWIN</span>
                <h3>Détail du poste {poste}</h3>
                <p class="pd-caption">📅 Période analysée : {period_txt}</p>
            </div>
            <div class="pd-badges">
                <span class="status-badge" data-status="{r['classe']}">{icon} {CLASS_LABELS.get(r['classe'], r['classe'])}</span>
                <span class="pd-stat-mini">⚓ {int(r['escales'])} escales</span>
                <span class="pd-stat-mini">📦 {_f0(float(r['tonnage']))} t</span>
            </div>
        </div>''', unsafe_allow_html=True)
    with head_r:
        if st.button("✖ Fermer", key="close_poste_panel", use_container_width=True,
                     help="Fermer l'analyse du poste et revenir à la vue générale"):
            st.session_state.pop("selected_poste", None)
            st.rerun()

    # ----- Fiche KPI du poste -----
    st.markdown(f'<div class="pd-sec"><h4>Fiche du poste</h4><small>{period_txt} · valeurs réelles de la période</small></div>',
                unsafe_allow_html=True)
    stat_label = CLASS_LABELS.get(r["classe"], r["classe"])
    stat_color = CLASS_COLORS.get(r["classe"], "#56a8ff")
    var_pts_text = f"{occ_pts:+.1f} pts" if occ_pts is not None else "—"
    var_pts_cls = "good" if occ_pts is not None and abs(occ_pts) <= 5 \
        else "bad" if occ_pts is not None else "neutral"
    stat_style = (f"color:{stat_color};border-color:{stat_color}66;"
                  f"background:{stat_color}1f")
    tiles = [
        ("Berth / Station", html.escape(str(r["poste"])), "", None),
        ("Escales", _f0(int(r["escales"])), "", None),
        ("Tonnage (t)", _f0(float(r["tonnage"])), "", None),
        ("Occupation", _f1(r["occupation"], " %"), "", None),
        ("Séjour moy. (h)", _f1(r["sejour_moyen"]), "", None),
        ("Attente moy. (h)", _f1(attente_cur), "", None),
        ("Variation N-1 (pts)", var_pts_text, var_pts_cls, None),
        ("Statut", stat_label, "", stat_style),
    ]
    st.markdown('<div class="pd-fiche">' + "".join(
        _fiche_tile(*tile) for tile in tiles) + '</div>', unsafe_allow_html=True)

    # ----- Détail des escales -----
    st.markdown(f'<div class="pd-sec"><h4>Détail des escales — poste {poste}</h4>'
                f'<small>{period_txt}</small></div>', unsafe_allow_html=True)
    _escales_table(_sort_escales(at_poste), ctx)

    # ----- Défilement automatique vers le panneau si l'utilisateur a cliqué -----
    st_html("""<script>
(function(){
  var top = window.parent;
  var target = top.__anpScrollToPanel;
  if (!target) return;
  top.__anpScrollToPanel = null;
  var el = top.document.getElementById('poste-detail-panel');
  if (el){ el.scrollIntoView({behavior:'smooth', block:'start'}); }
})();
</script>""", height=1)