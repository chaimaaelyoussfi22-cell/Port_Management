# -*- coding: utf-8 -*-
"""PAGE /analyse — Attente au mouillage (page réduite).

La page est désormais dédiée UNIQUEMENT à la section « Attente au mouillage » :
- Filtres Année + Mois (seuls).
- 3 graphiques :
  ① Évolution de l'attente moyenne selon le mois de début d'attente (N vs N-1)
  ② Distribution des durées d'attente
  ③ Attente moyenne par marchandise

Toutes les autres sections (filtres interconnectés globaux, KPIs, évolution
multi-métrique, postes, heatmap, navires, types, marchandises, scatter,
alertes, insights, tableau) ont été supprimées.
"""

import pandas as pd
import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


def render_back_button():
    bl, _ = st.columns([1.2, 5])
    with bl:
        if st.button("← Retour au Dashboard", use_container_width=True):
            st.switch_page("app.py")


def render_header():
    st.markdown(
        '<div class="an-title"><h1>⏳ ATTENTE AU MOUILLAGE</h1>'
        '<p>Attente = Sortie_Mouillage − Mouillage · Attribution par mois de '
        'DÉBUT d\'attente · N vs N-1</p></div>',
        unsafe_allow_html=True)


# ==================================================================
# PAGE
# ==================================================================
operations = db_manager.get_operations()
if operations is None or operations.empty:
    st.warning("Aucune opération dans la base — importez des escales pour alimenter l'analyse.")
    st.stop()

_load_css()
render_back_button()
render_header()

prepared = prepare_operations(operations)
if prepared.empty:
    st.info("Aucune donnée exploitable.")
    st.stop()

# Toutes les années sont passées à la carte Attente : elle gère elle-même le
# filtre Année/Mois et la comparaison N vs N-1 (frame N-1 incluse dans les données).
from components.dashboard.attente_ui import render_attente_card
render_attente_card(prepared)

st.markdown('<div class="an-methodo">Méthodologie — Attente : Sortie_Mouillage − '
            'Mouillage · Attribution : mois de DÉBUT de l\'attente (date_mouillage) · '
            'Comparaison : année N vs N-1.</div>', unsafe_allow_html=True)
