# -*- coding: utf-8 -*-
"""Filtres opérationnels : Année, Mois, Période, Poste, Marchandise,
Type de navire, Opérateur, Type de trafic. Toutes les vues du dashboard
sont recalculées à chaque changement."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

MONTHS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
             "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]


def _choices(frame: pd.DataFrame, column: str) -> list:
    if column not in frame or frame.empty:
        return []
    return sorted(frame[column].dropna().astype(str).loc[lambda s: s.str.strip() != ""].unique().tolist())


def render_filters(operations: pd.DataFrame) -> dict:
    """Affiche les filtres et retourne la spécification complète (dates incluses)."""
    st.markdown('<div class="filter-heading">⌕ <span>Filtres opérationnels</span></div>', unsafe_allow_html=True)
    choices = {
        "poste": _choices(operations, "poste"),
        "operateur": _choices(operations, "operateur"),
        "marchandise": _choices(operations, "type_marchandise"),
        "type_navire": _choices(operations, "type_navire"),
    }
    years = sorted(pd.to_datetime(operations["date"], errors="coerce").dt.year.dropna().astype(int).unique().tolist()) \
        if not operations.empty and "date" in operations else []

    if "dashboard_dates" not in st.session_state:
        st.session_state.dashboard_dates = (date.today() - timedelta(days=30), date.today())

    period = st.selectbox(
        "🗓 Période",
        ["Toutes les données", "Aujourd’hui", "Cette semaine", "Ce mois",
         "Cette année", "Année spécifique", "Mois spécifique", "Personnalisée"],
        key="dashboard_period")

    start = end = None
    custom_dates = None
    if period == "Année spécifique" and years:
        year = st.selectbox("📅 Année", years, index=len(years) - 1, key="dashboard_year")
        start, end = date(year, 1, 1), date(year, 12, 31)
    elif period == "Mois spécifique" and years:
        c1, c2 = st.columns(2)
        year = c1.selectbox("📅 Année", years, index=len(years) - 1, key="dashboard_year")
        month = c2.selectbox("🗓 Mois", list(range(1, 13)),
                             format_func=lambda m: MONTHS_FR[m - 1], key="dashboard_month")
        last_day = calendar_monthrange(year, month)
        start, end = date(year, month, 1), date(year, month, last_day)
    elif period == "Personnalisée":
        custom_dates = st.date_input("Intervalle", value=st.session_state.dashboard_dates, key="dashboard_dates")
        if isinstance(custom_dates, tuple) and len(custom_dates) == 2:
            start, end = custom_dates

    cols = st.columns([1.05, .95, 1.15, 1.1, 1.1, .95, .55])
    with cols[0]:
        poste = st.selectbox("⚓ Poste", ["Tous les postes", *choices["poste"]])
    with cols[1]:
        operateur = st.selectbox("◉ Opérateur", ["Tous les opérateurs", *choices["operateur"]])
    with cols[2]:
        marchandise = st.selectbox("▦ Marchandise", ["Toutes les marchandises", *choices["marchandise"]])
    with cols[3]:
        type_navire = st.selectbox("🚢 Type navire", ["Tous les navires", *choices["type_navire"]])
    with cols[4]:
        type_trafic = st.selectbox("↔ Type de trafic", ["Tous types", "Import", "Export", "Cabotage"])
    with cols[5]:
        if st.button("Actualiser", help="Réinitialiser les filtres", use_container_width=True):
            for key in list(st.session_state):
                if key.startswith("dashboard_"):
                    del st.session_state[key]
            st.rerun()

    days = max((end - start).days + 1, 1) if (start and end) else None
    return {"period": period, "dates": custom_dates, "start": start, "end": end, "days": days,
            "poste": poste, "operateur": operateur, "marchandise": marchandise,
            "type_navire": type_navire, "type_trafic": type_trafic}


def calendar_monthrange(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]
