"""En-tête du Smart Port Command Center."""

from datetime import datetime
import streamlit as st


def render_header():
    now = datetime.now()
    user = st.session_state.get("user_name") or st.session_state.get("username", "Utilisateur")
    anchor_icon = '''<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="5" r="2"/><path d="M12 7v13m-7-7h14M5 13a7 7 0 0 0 14 0M8 20h8"/></svg>'''
    st.markdown(f'''<section class="command-header">
        <div class="brand-mark">{anchor_icon}</div><div class="brand-copy"><h1>SMART PORT COMMAND CENTER</h1>
        <p>AGENCE NATIONALE DES PORTS <i>•</i> PORT DE JORF LASFAR</p></div>
        <div class="header-stat"><span>DATE</span><b>{now:%d/%m/%Y}</b></div>
        <div class="header-stat"><span>HEURE LOCALE</span><b>{now:%H:%M}</b></div>
        <div class="header-stat"><span>UTILISATEUR</span><b>{user}</b></div></section>''', unsafe_allow_html=True)
