# -*- coding: utf-8 -*-
"""PAGE /analyse_incidents — Carte « INCIDENTS » : diagnostic des événements
portuaires (nature, lieu, catégorie, registre).

Dashboard compact type Power BI : chaque graphique possède SES PROPRES filtres
intégrés à sa card (catégorie, nature, zone, lieu). Aucune valeur fictive :
on affiche « — » si une dimension manque. Toutes les périodes, natures et
lieux proviennent exclusivement des données réelles de la table incidents.
"""

import streamlit as st

from database import db_manager
from components.dashboard.incidents_views import render_incidents_card


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


_load_css()

# ==================================================================
# EN-TÊTE
# ==================================================================
bl, _ = st.columns([1.2, 5])
with bl:
    if st.button("← Retour au Dashboard", use_container_width=True):
        st.switch_page("app.py")

# Carte complète (KPI, donut, évolution, lieux, catégories, heatmap, registre) :
# aucun filtre global — mêmes filtres internes que sur la carte du dashboard.
render_incidents_card(
    db_manager.get_incidents(limit=200000),
)