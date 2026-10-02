# -*- coding: utf-8 -*-
"""Cartes KPI premium du dashboard global.

11 dimensions · valeur période filtrée · variation N-1 (sens métier) ·
sparkline mensuelle. Chaque carte possède son bouton « Analyser » :
- chaque dimension ouvre sa page dédiée (dashboards Power BI) ;
- « Consignation » et « Évolution de la consignation » affichent leurs
  propres valeurs réelles (table consignations) via _consignation_card().
Navigation par session_state + st.switch_page : aucun rechargement global.
"""

import streamlit as st

DIMENSIONS = [
    {"key": "escales", "title": "Escales", "icon": "⚓"},
    {"key": "navires", "title": "Navires", "icon": "🚢"},
    {"key": "tonnage", "title": "Trafic traité", "icon": "📦"},
    {"key": "evolution_trafic", "title": "Évolution du trafic", "icon": "📈"},
    {"key": "sejour_quai", "title": "Séjour à quai", "icon": "⏱"},
    {"key": "sejour_port", "title": "Séjour au port", "icon": "🛳"},
    {"key": "attente", "title": "Attente / Mouillage", "icon": "⏳"},
    {"key": "productivite", "title": "Productivité", "icon": "⚙️"},
    {"key": "occupation", "title": "Taux d'occupation", "icon": "🏗"},
    {"key": "consignation", "title": "Consignation", "icon": "🔒"},
    {"key": "consignation_evo", "title": "Évolution de la consignation", "icon": "📉"},
    {"key": "incidents", "title": "Incidents", "icon": "🚨"},
]

# sens métier : une hausse est-elle positive ? (None = stabilité attendue)
_HIGHER_POSITIVE = {
    "escales": True, "navires": True, "tonnage": True, "evolution_trafic": None,
    "sejour_quai": False, "sejour_port": False, "attente": False,
    "productivite": True, "occupation": None, "consignation": False,
    "consignation_evo": False,
    "incidents": False,
}

# clé KPI + mode de formatage (identique aux mini-KPI du score)
_VALUE_MODE = {
    "escales": ("escales", "int"), "navires": ("navires", "int"),
    "tonnage": ("tonnage", "tonnage"), "attente": ("attente", "d1"),
    "sejour_quai": ("sejour_quai", "d1"), "sejour_port": ("sejour_port", "d1"),
    "productivite": ("productivite", "d1"), "occupation": ("occupation", "d1"),
    "consignation": ("consignation", "int"),
    "consignation_evo": ("consignation", "int"),
}


def _spark(series_month: list[float], color: str = "#62ddff") -> str:
    import math
    vals = [v for v in series_month if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if len(vals) < 2:
        return '<div class="chart-empty">Historique<br>insuffisant</div>'
    low, high = min(vals), max(vals)
    spread = (high - low) or 1
    pts = " ".join(f"{i * 100 / (len(vals) - 1):.1f},{62 - ((v - low) / spread * 52):.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg class="micro-chart" viewBox="0 0 100 70" preserveAspectRatio="none">'
            f'<path class="chart-grid" d="M0 16H100M0 39H100M0 62H100"/>'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.1" '
            f'vector-effect="non-scaling-stroke"/></svg>')


def _sparkline_for(ctx: dict, key: str) -> str:
    prepared = ctx.get("prepared")
    if prepared is None or prepared.empty or key not in {
            "escales", "navires", "tonnage", "productivite"}:
        return _spark([])
    g = prepared.groupby("month")
    if key == "escales":
        s = g["escale_key"].nunique()
    elif key == "navires":
        s = g["navire_name"].nunique()
    elif key == "tonnage":
        s = g["tonnage"].sum()
    else:
        q = g["tonnage"].sum(); h = g["quai_h"].sum()
        s = (q / h.replace(0, float("nan"))).fillna(0)
    return _spark([float(v) for v in s.sort_index().tolist()])


@st.cache_data(ttl=600, show_spinner=False)
def _consignations_frame():
    """Données consignations (table réelle) pour les cartes dédiées."""
    from database import db_manager
    from components.dashboard.consignation_views import prepare_consignations
    raw = db_manager.get_consignations(limit=20000)
    return prepare_consignations(raw)


@st.cache_data(ttl=600, show_spinner=False)
def _incidents_frame():
    """Données incidents (table réelle) pour la carte dédiée."""
    from database import db_manager
    from components.dashboard.incidents_views import prepare_incidents
    raw = db_manager.get_incidents(limit=200000)
    return prepare_incidents(raw)


def _incidents_card() -> tuple[str, float | None, str]:
    """Valeur réelle + variation + sparkline mensuelle pour la carte Incidents.

    Compte uniquement les incidents hors Consignation / Déconsignation
    (mêmes règles que la page « Analyse des incidents »).
    """
    from components.dashboard.incidents_views import sans_consignations
    frame = sans_consignations(_incidents_frame())
    empty = "—", None, _spark([])
    if frame is None or frame.empty:
        return empty
    total = int(len(frame))
    years = sorted(frame["year"].unique().tolist())
    if not years:
        return f"{total:,}".replace(",", " "), None, _spark([])
    latest = years[-1]
    monthly = (frame[frame["year"] == latest].groupby("month").size()
               .sort_index().tolist())
    spark = _spark([float(v) for v in monthly])
    return f"{total:,}".replace(",", " "), None, spark


def _consignation_card(key: str) -> tuple[str, float | None, str]:
    """Valeur réelle + variation + sparkline pour les cartes consignation."""
    frame = _consignations_frame()
    empty = "—", None, _spark([])
    if frame is None or frame.empty:
        return empty
    years = sorted(frame["year"].unique().tolist())
    if not years:
        return empty
    latest = years[-1]
    cur = int((frame["year"] == latest).sum())
    prev = int((frame["year"] == latest - 1).sum())
    var = round(100 * (cur - prev) / prev, 1) if prev > 0 else None
    monthly = (frame[frame["year"] == latest].groupby("month").size()
               .sort_index().tolist())
    spark = _spark([float(v) for v in monthly])
    if key == "consignation":
        total = int(len(frame))
        return f"{total:,}".replace(",", " "), var, spark
    return f"{cur:,}".replace(",", " "), var, spark


def render_kpi_cards(ctx: dict):
    """Grille des 11 dimensions, chacune avec son bouton « Analyser »."""
    from components.dashboard.performance_score import _fmt, _variation_chip

    cols = st.columns(3, gap="small")
    for idx, dim in enumerate(DIMENSIONS):
        key = dim["key"]
        variations = ctx["variations"]
        if key in ("consignation", "consignation_evo"):
            value_txt, var, spark = _consignation_card(key)
        elif key == "incidents":
            value_txt, var, spark = _incidents_card()
        elif key == "evolution_trafic":
            var = variations.get("tonnage")
            value_txt = f"{var:+.1f} %".replace(".", ",") if var is not None else "—"
            spark = _sparkline_for(ctx, key)
        else:
            src, mode = _VALUE_MODE[key]
            value_txt = _fmt(ctx["kpis"].get(src), mode)
            var = variations.get(key)
            spark = _sparkline_for(ctx, key)
        chip = _variation_chip(var, _HIGHER_POSITIVE[key])
        with cols[idx % 3]:
            st.markdown(f'''<div class="ops-card"><span>{dim["title"]}</span>
                <div class="tile-icon">{dim["icon"]}</div>
                <div class="ops-card-body"><div>
                    <small>PÉRIODE FILTRÉE</small>
                    <strong>{value_txt}</strong>
                    {chip}
                </div><div class="chart-wrap">{spark}</div></div>
            </div>''', unsafe_allow_html=True)
            if st.button("Analyser", key=f"btn_an_{key}", use_container_width=True):
                if key == "escales":
                    # Page dédiée « Analyse des escales » (dashboard Power BI)
                    st.switch_page("pages/analyse_escales.py")
                elif key == "navires":
                    # Page dédiée « Analyse des navires » (dashboard Power BI)
                    st.switch_page("pages/analyse_navires.py")
                elif key == "tonnage":
                    # Page dédiée « Volume Trafic » (composition / répartition)
                    st.switch_page("pages/analyse_trafic.py")
                elif key == "evolution_trafic":
                    # Page dédiée « Évolution du trafic » (tendances N vs N-1)
                    st.switch_page("pages/analyse_evolution.py")
                elif key == "sejour_quai":
                    # Page dédiée « Analyse du séjour à quai » (dashboard Power BI)
                    st.switch_page("pages/analyse_sejour.py")
                elif key == "sejour_port":
                    # Page dédiée « Analyse du séjour au port » (dashboard Power BI)
                    st.switch_page("pages/analyse_sejour_port.py")
                elif key == "productivite":
                    # Page dédiée « Analyse de la productivité » (dashboard Power BI)
                    st.switch_page("pages/analyse_productivite.py")
                elif key == "occupation":
                    # Page dédiée « Analyse du taux d'occupation » (dashboard Power BI)
                    st.switch_page("pages/analyse_occupation.py")
                elif key == "consignation":
                    # Page dédiée « Analyse des consignations » (dashboard Power BI)
                    st.switch_page("pages/analyse_consignation.py")
                elif key == "consignation_evo":
                    # Page dédiée « Évolution de la consignation » (dashboard Power BI)
                    st.switch_page("pages/analyse_consignation_evo.py")
                elif key == "incidents":
                    # Page dédiée « Analyse des incidents » (dashboard Power BI)
                    st.switch_page("pages/analyse_incidents.py")
                else:
                    st.session_state["analyse_metric"] = key
                    st.switch_page("pages/analyse.py")
