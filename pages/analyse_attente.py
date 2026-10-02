# -*- coding: utf-8 -*-
"""PAGE /analyse_attente — Attente au mouillage (dashboard type Power BI).

Métrique : attente_h (Sortie_Mouillage − Mouillage).
Attribution temporelle : mois/année de DÉBUT de l'attente (date_mouillage).
Composants réutilisés : attente_views (logique) + attente_ui (carte).
"""

import streamlit as st

from database import db_manager
from components.dashboard.analytics import prepare_operations
from components.dashboard import attente_views as av
from components.dashboard.attente_ui import render_attente_card


def _load_css():
    for f in ("assets/dashboard.css", "assets/analyse.css"):
        try:
            with open(f, encoding="utf-8") as fh:
                st.markdown(f"<style>{fh.read()}</style>", unsafe_allow_html=True)
        except FileNotFoundError:
            pass


def _header():
    st.markdown(
        '<div class="an-header"><div class="an-title">'
        '<h1>⏳ ATTENTE AU MOUILLAGE</h1>'
        '<p>Analyse de l\'attente avant accostage — KPI, évolution N vs N-1, '
        'distribution par tranches de durée</p>'
        '</div><div class="an-header-meta">'
        '<div class="meta"><span>données</span><b>réelles</b></div>'
        '<div class="meta"><span>indicateur</span><b>attente_h</b></div>'
        '</div></div>',
        unsafe_allow_html=True)


def main():
    _load_css()
    _header()
    ops = db_manager.get_operations()
    if ops is None or ops.empty:
        st.warning("Aucune opération dans la base. Importez des escales ou "
                   "saisissez une opération pour alimenter le port.")
        return
    prepared = prepare_operations(ops)
    if prepared.empty:
        st.info("Aucune donnée exploitable.")
        return
    render_attente_card(av.prepare(prepared))


if __name__ == "__main__" or st.runtime.exists():
    main()