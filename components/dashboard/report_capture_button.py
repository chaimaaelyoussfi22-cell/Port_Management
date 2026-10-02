# -*- coding: utf-8 -*-
"""Bouton « ➕ Ajouter au rapport » réutilisable + indicateur de panier.

À placer sur n'importe quel élément du dashboard (graphique, tableau, carte)
pour l'ajouter au rapport en cours de construction (voir report_capture).
"""

from __future__ import annotations

import streamlit as st

from components.dashboard import report_capture as rc


def cart_badge() -> None:
    """Petit indicateur du nombre d'éléments déjà ajoutés au rapport."""
    n = rc.cart_count()
    if n:
        st.markdown(
            f"<div style='text-align:right;font-size:0.9rem;color:#56a8ff'>"
            f"📥 Rapport en cours : <b>{n}</b> élément{'s' if n > 1 else ''} "
            f"<a href='/' onclick='return false;' style='color:#a9cae8'>"
            f"(voir la page Rapport)</a></div>",
            unsafe_allow_html=True)


def capture_button(*, title: str, section: str, fig=None,
                   data=None, filter_text: str = "",
                   kind: str = "figure", tag: str = "",
                   compact: bool = True) -> bool:
    """Rend le bouton d'ajout au rapport. Retourne True si cliqué.

    - ``kind="figure"`` → stocke la figure Plotly + données (image + données).
    - ``kind="table"`` / ``"kpi"`` → stocke uniquement les données (pas d'image).
    """
    key = f"capture_{section}_{tag or title}_{kind}".replace(" ", "_")
    label = "➕ au rapport" if compact else "➕ Ajouter au rapport"
    if st.button(label, key=key, use_container_width=True):
        try:
            if kind == "figure" and fig is not None:
                rc.add_figure(title, section, fig, data, filter_text)
            else:
                rc.add_table(title, section, data, filter_text, kind=kind)
            st.toast(f"« {title} » ajouté au rapport", icon="📥")
        except Exception:
            st.error("Impossible d'ajouter cet élément au rapport.")
        return True
    return False
