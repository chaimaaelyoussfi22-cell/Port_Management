# -*- coding: utf-8 -*-
"""Recommandations décisionnelles dérivées des diagnostics réels des postes."""

import html
import streamlit as st


def build_recommendations(ctx) -> list[tuple[str, str]]:
    kpis, prev, postes = ctx["kpis"], ctx["kpis_prev"], ctx["postes"]
    ideas = []
    if not postes.empty:
        sat = postes[postes["occupation"] >= 80]
        if not sat.empty:
            names = ", ".join(str(p) for p in sat["poste"].head(3))
            ideas.append(("Limiter la saturation",
                          f"Dérouter les prochaines escales des postes {names} (≥80 % d'occupation)."))
        slow = postes[(postes["ecart_sejour"].notna()) & (postes["ecart_sejour"] > 20)]
        if not slow.empty:
            ideas.append(("Réduire les séjours anormaux",
                          "Auditer productivité et process des postes à séjour >+20 % vs moyenne port."))
        free = postes[postes["occupation"] < 50]
        if not free.empty:
            names = ", ".join(str(p) for p in free["poste"].head(3))
            ideas.append(("Valoriser la capacité disponible",
                          f"Cibler les postes {names} pour lisser la charge du port."))
    var_prod = ctx["variations"].get("productivite")
    if var_prod is not None and var_prod <= -15:
        ideas.append(("Reconquérir la productivité",
                      "Comparer marchandises/opérateurs N vs N-1 pour localiser la perte de rendement."))
    var_att = ctx["variations"].get("attente")
    if var_att is not None and var_att >= 25:
        ideas.append(("Fluidifier l'accès à quai",
                      "Réviser le séquencement mouillage → accostage et prioriser les navires en rade."))
    var_ton = ctx["variations"].get("tonnage")
    if var_ton is not None and var_ton >= 15:
        ideas.append(("Anticiper le pic de trafic",
                      f"Trafic {var_ton:+.1f}% vs N-1 : prévoir main-d'œuvre et moyens terrestres."))
    return ideas


def render_smart_advisor(ctx):
    ideas = build_recommendations(ctx)
    st.markdown('<div class="section-heading"><span>✦</span> Smart Advisor</div>',
                unsafe_allow_html=True)
    if not ideas:
        st.markdown('<div class="empty-state">✦ Exploitation stable — aucune action corrective prioritaire.</div>',
                    unsafe_allow_html=True)
        return
    for title, body in ideas[:4]:
        st.markdown(f'<div class="advisor-row"><b>{html.escape(title)}</b><p>{html.escape(body)}</p></div>',
                    unsafe_allow_html=True)
