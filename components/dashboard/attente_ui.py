# -*- coding: utf-8 -*-
"""Section « ⏳ Attente au mouillage » : filtres Année/Mois + 3 graphiques.

Utilisée par :
- pages/analyse.py (section métrique=attente) ;
- la page dédiée pages/analyse_attente.py.

Contenu :
- Filtres Année + Mois (seuls).
- 3 graphiques :
  ① Évolution de l'attente moyenne selon le mois de début d'attente (N vs N-1)
  ② Distribution des durées d'attente
  ③ Attente moyenne par marchandise
La logique (attente_views) reste pure pandas/plotly, testable sans Streamlit.
"""

import pandas as pd
import streamlit as st

from components.dashboard import attente_views as av
from components.dashboard.filters import MONTHS_FR


def render_attente_card(frame: pd.DataFrame):
    """Filtres Année/Mois + 3 graphiques de la section Attente."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        st.info("Aucune donnée d'attente (horaires mouillage absents sur la période).")
        return
    if "att_year" not in frame.columns:
        frame = av.prepare(frame)
    if frame.empty:
        st.info("Aucune donnée d'attente (horaires mouillage absents).")
        return

    years = [int(y) for y in sorted(frame["att_year"].dropna().unique().tolist(),
                                    reverse=True)]
    if not years:
        st.info("Aucune donnée d'attente (horaires mouillage absents).")
        return

    S = st.session_state

    # ---- Filtres Année + Mois (seuls) ----
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            year = int(st.selectbox("📅 Année", years, key="at_year"))
        with c2:
            pick_m = st.multiselect("🗓 Mois (début d'attente)", MONTHS_FR,
                                    key="at_months", placeholder="Tous les mois",
                                    help="Laissez vide pour tous les mois.")
        months = [MONTHS_FR.index(m) + 1 for m in pick_m]

    # Dictionnaire sel : Année/Mois appliqués, autres dimensions sans restriction
    sel = {"year": year, "months": months, "poste": None, "type_navire": None,
           "navire": None, "operateur": None, "marchandise": None}

    # ① Évolution N vs N-1
    fig = av.fig_evolution(frame, sel)
    if fig:
        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})
    else:
        st.info("Évolution indisponible (données N ou N-1 insuffisantes).")

    # ② Distribution + ③ Attente par marchandise
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        fig = av.fig_distribution(frame, sel)
        if fig:
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Distribution indisponible sur cette sélection.")
    with c2:
        march_options = av.marchandise_options(frame, sel)
        picked = st.multiselect(
            "▦ Marchandise", march_options, key="at_marchandise",
            placeholder="Toutes les marchandises",
            help="Filtre dédié au graphique « Attente par marchandise ». Laissez "
                 "vide pour afficher toutes les marchandises.")
        fig = av.fig_marchandise(frame, sel, picked or None)
        if fig:
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})
        else:
            st.info("Attente par marchandise indisponible sur cette sélection.")
