# -*- coding: utf-8 -*-
"""Module TOP / Alertes : les 3 à 5 événements opérationnels les plus importants."""

import html
import streamlit as st

from components.dashboard.analytics import generate_alerts


def render_smart_alerts(ctx):
    alerts = generate_alerts(ctx["kpis"], ctx["kpis_prev"], ctx["postes"])
    st.markdown('<div class="section-heading"><span>!</span> Smart Alerts & Priorités</div>',
                unsafe_allow_html=True)
    if not alerts:
        st.markdown('<div class="empty-state">✓ Aucune alerte active pour cette sélection.</div>',
                    unsafe_allow_html=True)
        return
    for a in alerts:
        css = {"critique": "danger", "positive": "success"}.get(a["severity"], "notice")
        action = f'<p>➜ {html.escape(a["action"])}</p>' if a.get("action") else ""
        st.markdown(
            f'''<div class="alert-row {css}"><b>{a["icon"]} {html.escape(a["title"])}</b>
            <span>{html.escape(a["detail"])}</span>{action}</div>''',
            unsafe_allow_html=True)
