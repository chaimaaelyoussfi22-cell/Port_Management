"""
ANP Port Jorf Lasfar - Application de gestion portuaire
Nouveau projet - Structure identique, base de données neuve
"""
import os
import base64
from pathlib import Path
from datetime import datetime

import streamlit as st

from database import DBManager
from auth import is_authenticated, login_form, show_user_info


# ===================== CONFIGURATION =====================
st.set_page_config(
    page_title="ANP Jorf Lasfar - Performance Portuaire",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ===================== CSS GLOBAL =====================
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    try:
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.markdown(
            """
            <style>
            * { font-family: 'Inter', sans-serif; }
            .stApp { background:#f8fafc; }
            [data-testid="stSidebarNav"] { display:none !important; }
            [data-testid="stSidebar"] {
                background: linear-gradient(180deg, #071428, #0a1d36) !important;
                border-right: 1px solid rgba(117,176,235,.18) !important;
            }
            .sp-brand { display:flex; align-items:center; gap:12px; padding:20px 18px 12px; }
            .sp-brand-mark {
                width:46px; height:46px; display:grid; place-items:center;
                border-radius:14px; background:rgba(86,168,255,.14);
                border:1px solid rgba(86,168,255,.5); font-size:22px;
            }
            .sp-brand-title { color:#fff; font-weight:800; font-size:1rem; letter-spacing:.14em; }
            .sp-brand-sub { color:#7fb6dd; font-size:.68rem; letter-spacing:.24em; margin-top:4px; text-transform:uppercase; }
            .sp-brand-eyebrow {
                display:flex; align-items:center; gap:10px; margin:0 18px 16px; padding-bottom:14px;
                border-bottom:1px solid rgba(117,176,235,.15);
                color:#5f86a8; font-size:.58rem; font-weight:800; letter-spacing:.2em;
            }
            .sp-brand-eyebrow::before, .sp-brand-eyebrow::after { content:""; flex:1; height:1px; }
            .sp-brand-eyebrow::before { background:linear-gradient(90deg,transparent,rgba(86,168,255,.4)); }
            .sp-brand-eyebrow::after  { background:linear-gradient(90deg,rgba(86,168,255,.4),transparent); }
            .sp-nav-heading { color:#5f86a8; font-size:.6rem; font-weight:800; letter-spacing:.24em; text-transform:uppercase; margin:2px 20px 8px; }
            .sp-footer { margin:18px 18px 0; padding:12px 6px 4px; display:flex; flex-direction:column; gap:3px; }
            .sp-foot-line { color:#7fb6dd; font-size:.64rem; font-weight:700; letter-spacing:.14em; }
            .sp-foot-sub { color:#5f86a8; font-size:.56rem; font-weight:600; letter-spacing:.2em; }
            </style>
            """,
            unsafe_allow_html=True,
        )


def force_sidebar_open():
    st.markdown(
        """
        <style>
        html, body, .stApp { overflow:auto !important; }
        .block-container {
            height:auto !important;
            min-height:auto !important;
            max-width:1920px !important;
            padding-top:1rem !important;
            padding-left:1rem !important;
            padding-right:1rem !important;
        }
        section[data-testid="stSidebar"], [data-testid="stSidebar"] {
            display:block !important;
            visibility:visible !important;
            width:21rem !important;
            min-width:21rem !important;
            transform:translateX(0px) !important;
        }
        @media (max-width:1100px) {
            section[data-testid="stSidebar"], [data-testid="stSidebar"] {
                width:17.5rem !important;
                min-width:17.5rem !important;
            }
        }
        @media (max-width:760px) {
            section[data-testid="stSidebar"], [data-testid="stSidebar"] {
                width:15rem !important;
                min-width:15rem !important;
            }
        }
        [data-testid="collapsedControl"] { display:none !important; visibility:hidden !important; }
        [data-testid="stSidebarNav"] { display:none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _image_as_data_url() -> str:
    image_path = Path(__file__).parent / "assets" / "port_bg.jpg"
    if not image_path.exists():
        return ""
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _gateway_css() -> str:
    bg = _image_as_data_url()
    background = (
        f"linear-gradient(rgba(1,13,35,.42), rgba(1,13,35,.62)), url('{bg}')"
        if bg
        else "linear-gradient(135deg,#03122d,#0b3b70)"
    )
    return f"""
    <style>
    #MainMenu, header, footer {{ visibility:hidden !important; }}
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {{ display:none !important; }}
    html, body, .stApp {{ margin:0 !important; padding:0 !important; overflow:hidden !important; }}
    .block-container {{ max-width:100% !important; padding:0 !important; }}
    .stApp {{
        background:{background} !important;
        background-size:cover !important;
        background-position:center !important;
        background-repeat:no-repeat !important;
    }}
    iframe {{ display:block !important; }}

    .stButton {{
        display:flex !important;
        justify-content:center !important;
        margin-top:-96px !important;
        position:relative !important;
        z-index:9999 !important;
    }}

    .stButton > button {{
        width:230px !important;
        height:50px !important;
        border-radius:999px !important;
        border:2px solid rgba(255,255,255,.35) !important;
        background:linear-gradient(135deg,#ffbd44,#f59e0b) !important;
        color:#061b46 !important;
        font-size:0.95rem !important;
        font-weight:900 !important;
        box-shadow:0 14px 35px rgba(0,0,0,.35) !important;
        transition:all .25s ease !important;
    }}

    .stButton > button:hover {{
        transform:translateY(-3px) !important;
        box-shadow:0 20px 46px rgba(0,0,0,.45) !important;
        filter:brightness(1.06) !important;
    }}
    </style>
    """


def _gateway_html() -> str:
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    current_date = now.strftime("%d/%m/%Y")

    bg = _image_as_data_url()
    background = (
        f"linear-gradient(rgba(1,13,35,.42), rgba(1,13,35,.62)), url('{bg}')"
        if bg
        else "linear-gradient(135deg,#03122d,#0b3b70)"
    )

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&display=swap');
* {{ box-sizing:border-box; }}
html, body {{
    margin:0;
    padding:0;
    width:100%;
    min-height:100%;
    overflow:hidden;
    font-family:'Inter', sans-serif;
}}
body {{
    background:{background};
    background-size:cover;
    background-position:center;
    background-repeat:no-repeat;
}}
.gateway-page {{
    min-height:720px;
    width:100%;
    position:relative;
    color:white;
    padding:28px 38px;
}}
.gateway-page::before {{
    content:"";
    position:fixed;
    inset:0;
    background:
        radial-gradient(circle at 50% 16%, rgba(255,186,59,.14), transparent 24%),
        radial-gradient(circle at 75% 54%, rgba(0,190,255,.16), transparent 26%),
        linear-gradient(180deg, rgba(1,13,35,.08), rgba(1,13,35,.34));
    pointer-events:none;
}}
.top-logo {{
    position:fixed;
    top:0;
    left:0;
    width:150px;
    height:185px;
    border-radius:0 0 28px 0;
    background:rgba(1,18,45,.76);
    border-right:1px solid rgba(255,255,255,.16);
    border-bottom:1px solid rgba(255,255,255,.16);
    display:flex;
    flex-direction:column;
    justify-content:center;
    align-items:center;
    z-index:2;
    backdrop-filter:blur(12px);
    box-shadow:0 18px 50px rgba(0,0,0,.28);
}}
.top-logo .anchor {{ font-size:2.45rem; color:#ffb83d; line-height:1; }}
.top-logo .anp {{ font-size:2.7rem; font-weight:950; line-height:.95; letter-spacing:-1px; }}
.top-logo .port {{ color:#ffbf45; font-size:.72rem; font-weight:900; letter-spacing:1.5px; margin-top:8px; }}
.clock-chip {{
    position:fixed;
    right:32px;
    top:38px;
    z-index:2;
    padding:16px 24px;
    border-radius:18px;
    background:rgba(3,22,54,.66);
    border:1px solid rgba(255,255,255,.16);
    backdrop-filter:blur(14px);
    box-shadow:0 18px 45px rgba(0,0,0,.25);
    display:flex;
    gap:13px;
    align-items:center;
}}
.clock-icon {{ font-size:1.5rem; opacity:.9; }}
.clock-time {{ font-size:1.6rem; font-weight:950; line-height:1; }}
.clock-date {{ font-size:.76rem; opacity:.75; margin-top:4px; }}
.hero {{
    position:relative;
    z-index:1;
    min-height:720px;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    text-align:center;
    padding-top:10px;
}}
.hero-anchor {{
    color:#ffb83d;
    font-size:3.15rem;
    line-height:1;
    filter:drop-shadow(0 10px 24px rgba(255,184,61,.3));
    margin-bottom:8px;
}}
.title-small {{
    font-size:clamp(2.1rem, 4.6vw, 4.25rem);
    font-weight:950;
    letter-spacing:3px;
    line-height:.95;
    color:white;
    text-shadow:0 8px 28px rgba(0,0,0,.35);
}}
.title-big {{
    font-size:clamp(2.15rem, 5vw, 4.75rem);
    font-weight:950;
    letter-spacing:2px;
    line-height:1;
    margin-top:8px;
    color:#ffc24b;
    text-shadow:0 10px 32px rgba(0,0,0,.42);
}}
.subtitle {{
    margin-top:18px;
    display:flex;
    align-items:center;
    gap:18px;
    color:#fff;
    font-size:1.25rem;
    font-weight:700;
    letter-spacing:4px;
}}
.subtitle::before, .subtitle::after {{
    content:"";
    width:54px;
    height:2px;
    background:linear-gradient(90deg, transparent, #ffbd44);
}}
.subtitle::after {{ background:linear-gradient(90deg, #ffbd44, transparent); }}
.hint {{
    margin-top:20px;
    color:rgba(255,255,255,.80);
    font-size:1.05rem;
    font-weight:400;
}}
.role-area {{
    margin-top:38px;
    width:min(820px, 90vw);
    display:grid;
    grid-template-columns:repeat(2, 1fr);
    gap:28px;
}}
.role-box {{ position:relative; }}
.role-card {{
    min-height:235px;
    padding:24px 28px 78px;
    border-radius:24px;
    text-align:center;
    background:linear-gradient(180deg, rgba(2,24,58,.70), rgba(2,18,45,.56));
    backdrop-filter:blur(12px);
    box-shadow:0 24px 70px rgba(0,0,0,.32), inset 0 1px 0 rgba(255,255,255,.08);
    transition:.25s ease;
}}
.role-card.admin {{ border:1.5px solid rgba(255,190,65,.78); }}
.role-card.agent {{ border:1.5px solid rgba(0,184,255,.78); }}
.role-card:hover {{ transform:translateY(-6px); }}
.role-card.admin:hover {{ box-shadow:0 26px 80px rgba(255,184,61,.22); }}
.role-card.agent:hover {{ box-shadow:0 26px 80px rgba(0,184,255,.22); }}
.role-icon {{
    width:76px;
    height:76px;
    margin:0 auto 18px;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:2.2rem;
    background:rgba(0,0,0,.16);
}}
.admin .role-icon {{ color:#ffbd44; border:2px solid rgba(255,189,68,.45); }}
.agent .role-icon {{ color:#21b9ff; border:2px solid rgba(33,185,255,.48); }}
.role-title {{ font-size:1.55rem; font-weight:950; color:#fff; margin-bottom:10px; }}
.role-line {{ width:46px; height:2px; margin:0 auto 18px; border-radius:99px; }}
.admin .role-line {{ background:#ffbd44; }}
.agent .role-line {{ background:#21b9ff; }}
.role-desc {{ color:rgba(255,255,255,.86); font-size:.94rem; line-height:1.55; }}
.action-btn {{
    position:absolute;
    left:50%;
    bottom:24px;
    transform:translateX(-50%);
    width:64px;
    height:64px;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    text-decoration:none;
    border:2px solid rgba(255,255,255,.35);
    backdrop-filter:blur(14px);
    box-shadow:0 18px 40px rgba(0,0,0,.40), inset 0 1px 0 rgba(255,255,255,.35);
    transition:all .25s ease;
    animation:pulseBtn 2.4s ease-in-out infinite;
}}
.action-btn::after {{
    content:"›";
    font-size:3rem;
    line-height:1;
    color:#061b46;
    font-weight:900;
    margin-top:-4px;
}}
.action-btn:hover {{
    transform:translateX(-50%) translateY(-5px) scale(1.08);
    box-shadow:0 24px 55px rgba(0,0,0,.48), 0 0 28px rgba(255,190,65,.55);
}}
.action-btn.admin-action {{
    background:radial-gradient(circle at 30% 25%, #fff4c7, #ffbd44 45%, #f59e0b 100%);
}}
.action-btn.agent-action {{
    background:radial-gradient(circle at 30% 25%, #e0f7ff, #35c4ff 45%, #0b74ff 100%);
}}
@keyframes pulseBtn {{
    0%, 100% {{ filter:brightness(1); }}
    50% {{ filter:brightness(1.18); }}
}}
@media(max-width:850px) {{
    html, body {{ overflow:auto; }}
    .top-logo, .clock-chip {{ display:none; }}
    .hero {{ justify-content:flex-start; padding:36px 12px 80px; }}
    .role-area {{ grid-template-columns:1fr; }}
    .gateway-page {{ min-height:900px; }}
}}
</style>
</head>
<body>
<div class="gateway-page">
    <div class="top-logo">
        <div class="anchor">⚓</div>
        <div class="anp">ANP</div>
        <div class="port">PORT JORF LASFAR</div>
    </div>

    <div class="clock-chip">
        <div class="clock-icon">◷</div>
        <div>
            <div class="clock-time">{current_time}</div>
            <div class="clock-date">{current_date}</div>
        </div>
    </div>

    <div class="hero">
        <div class="hero-anchor">⚓</div>
        <div class="title-small">SMART PORT</div>
        <div class="title-big">OPERATIONS CENTER</div>
        <div class="subtitle">ANP PORT JORF LASFAR</div>
        <div class="hint">Choisissez votre espace pour accéder aux fonctionnalités dédiées</div>
        <div class="role-area">
            <div class="role-box">
                <div class="role-card admin">
                    <div class="role-icon">👨‍✈️</div>
                    <div class="role-title">ESPACE ADMIN</div>
                    <div class="role-line"></div>
                </div>
            </div>
            <div class="role-box">
                <div class="role-card agent">
                    <div class="role-icon">🚢</div>
                    <div class="role-title">AGENT MARITIME</div>
                    <div class="role-line"></div>
                </div>
            </div>
        </div>
    </div>
</div>
</body>
</html>
"""


def _sync_portal_choice_from_query():
    try:
        portal = st.query_params.get("portal", None)
    except Exception:
        portal = None

    if isinstance(portal, list):
        portal = portal[0] if portal else None

    if portal in ("admin", "agent"):
        st.session_state.portal_choice = portal
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()


def show_gateway():
    st.markdown(_gateway_css(), unsafe_allow_html=True)
    st.iframe(_gateway_html(), height=700)

    left_space, admin_col, middle_space, agent_col, right_space = st.columns([1.35, 1.25, 0.30, 1.25, 0.95])

    with admin_col:
        if st.button("➡️ Accès Admin", key="btn_gateway_admin"):
            st.session_state.portal_choice = "admin"
            st.rerun()

    with agent_col:
        if st.button("➡️ Accès Agent Maritime", key="btn_gateway_agent"):
            st.session_state.portal_choice = "agent"
            st.rerun()


load_css()


# ===================== DATABASE =====================
db_manager = DBManager()

with st.spinner("🔌 Vérification de la connexion à MySQL..."):
    status = db_manager.check_connection()

if status["status"] == "error":
    st.error(
        f"""
        ❌ **Erreur de connexion à la base de données**

        {status["message"]}

        En local : vérifie MySQL (XAMPP), le port et le fichier `.env`.
        En Docker : `docker compose up --build`.
        Code d'erreur: {status.get("code", "N/A")}
        """
    )
    st.stop()

db_manager.initialize_database()


# ===================== PAGE ACCUEIL / GATEWAY =====================
if "portal_choice" not in st.session_state:
    st.session_state.portal_choice = None

_sync_portal_choice_from_query()

if not is_authenticated() and st.session_state.portal_choice is None:
    show_gateway()
    st.stop()


# ===================== AUTHENTIFICATION =====================
if not is_authenticated():
    login_form()
    st.stop()


force_sidebar_open()


# ===================== ROLE FROM MYSQL =====================
role = st.session_state.get("user_role", "user")
portal_choice = st.session_state.get("portal_choice")

if portal_choice == "admin" and role.lower() not in ["admin", "administrateur"]:
    st.error("⛔ Accès Admin refusé. Connectez-vous avec un compte administrateur.")
    if st.button("↩️ Retour à l'accueil"):
        st.session_state.portal_choice = None
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    st.stop()

if portal_choice == "agent" and role.lower() not in ["agent", "agent_maritime"]:
    st.error("⛔ Accès Agent Maritime refusé. Connectez-vous avec un compte agent.")
    if st.button("↩️ Retour à l'accueil"):
        st.session_state.portal_choice = None
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()
    st.stop()


# ===================== SIDEBAR =====================
with st.sidebar:
    st.markdown(
        """
        <div class="sp-brand">
            <div class="sp-brand-mark">⚓</div>
            <div class="sp-brand-copy">
                <div class="sp-brand-title">SMART PORT</div>
                <div class="sp-brand-sub">Jorf Lasfar</div>
            </div>
        </div>
        <div class="sp-brand-eyebrow">Port Performance Intelligence</div>
        <div class="sp-nav-heading">Navigation</div>
        """,
        unsafe_allow_html=True,
    )

    if role == "admin":
        pages_options = [
            "🏠 DASHBOARD",
            "✏️ SAISIE",
            "📊 RAPPORT",
        ]

    elif role == "agent":
        pages_options = [
            "✏️ SAISIE",
        ]

    else:
        st.error("⛔ Rôle non reconnu. Vérifie la colonne role dans MySQL.")
        st.stop()

    page = st.radio(
        "Menu Principal",
        pages_options,
        label_visibility="collapsed",
    )

    if st.button("↩️ Retour accueil", use_container_width=True):
        for key in ["authenticated", "username", "user_role", "user_name"]:
            st.session_state.pop(key, None)
        st.session_state.portal_choice = None
        try:
            st.query_params.clear()
        except Exception:
            pass
        st.rerun()

    show_user_info()

    st.markdown(
        """
        <div class="sp-footer">
            <div class="sp-foot-line">ANP — Port de Jorf Lasfar</div>
            <div class="sp-foot-sub">Data &amp; Performance Management</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===================== SECURITY ACCESS CONTROL =====================
if role == "agent" and page != "✏️ SAISIE":
    st.error("⛔ Accès refusé. L'agent maritime a accès uniquement à la saisie.")
    st.stop()


# ===================== ROUTING =====================
if page == "🏠 DASHBOARD":
    from pages.dashboard import show_dashboard
    show_dashboard()

elif page == "✏️ SAISIE":
    from pages.saisie import show_saisie
    show_saisie(db_manager)

elif page == "📊 RAPPORT":
    from pages.rapports import show_rapports
    show_rapports()