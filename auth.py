"""
Système d'authentification pour l'application ANP
"""
import base64
import hashlib
from pathlib import Path

import streamlit as st
from database import DBManager


def get_db():
    return DBManager()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password_db(username: str, password: str) -> bool:
    db = get_db()
    conn = db._connect()

    if conn is None:
        return False

    try:
        cursor = conn.cursor()
        hashed_password = hash_password(password)

        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE username = %s
            AND (password = %s OR password_hash = %s)
            """,
            (username, hashed_password, hashed_password),
        )

        result = cursor.fetchone()
        return result is not None

    except Exception as e:
        print(f"Erreur authentification: {e}")
        return False

    finally:
        if conn:
            conn.close()


def get_user_info(username: str) -> dict:
    db = get_db()
    conn = db._connect()

    if conn is None:
        return {"name": username, "role": "user"}

    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT username, role FROM users WHERE username = %s",
            (username,),
        )

        result = cursor.fetchone()

        if result:
            return {
                "username": result[0],
                "role": result[1],
                "name": result[0].capitalize(),
            }

        return {"name": username, "role": "user"}

    except Exception as e:
        print(f"Erreur: {e}")
        return {"name": username, "role": "user"}

    finally:
        if conn:
            conn.close()


def _background_image_css() -> str:
    image_path = Path(__file__).parent / "assets" / "port_bg.jpg"

    if not image_path.exists():
        return "linear-gradient(135deg, #dbeafe 0%, #eff6ff 50%, #ffffff 100%)"

    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    return (
        "linear-gradient(rgba(255,255,255,.10), rgba(255,255,255,.18)), "
        f"url('data:image/jpeg;base64,{encoded}')"
    )


def login_form():
    bg_css = _background_image_css()

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

#MainMenu,
header,
footer {{
    visibility: hidden !important;
}}

[data-testid="stToolbar"] {{
    display: none !important;
}}

[data-testid="collapsedControl"] {{
    display: block !important;
}}

* {{
    box-sizing: border-box;
}}

html,
body,
.stApp {{
    width: 100% !important;
    min-height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
}}

.stApp {{
    font-family: 'Inter', sans-serif !important;
    background: {bg_css} !important;
    background-size: cover !important;
    background-position: center !important;
    background-repeat: no-repeat !important;
    background-attachment: fixed !important;
}}

.stApp::before {{
    content: "";
    position: fixed;
    inset: 0;
    background: rgba(5, 18, 45, .10);
    pointer-events: none;
    z-index: 0;
}}

.block-container {{
    max-width: 100% !important;
    width: 100% !important;
    height: 100vh !important;
    padding: 0 !important;
    margin: 0 !important;
}}

section.main > div {{
    padding: 0 !important;
}}

div[data-testid="stVerticalBlock"] {{
    gap: 0 !important;
}}

[data-testid="column"] {{
    padding: 0 !important;
}}

/* ===================== LEFT FIXED SIDE PANEL ===================== */
.side-panel {{
    width: 330px;
    height: 100vh;
    background:
        radial-gradient(circle at 15% 0%, rgba(212,167,61,.20), transparent 26%),
        linear-gradient(180deg, #02153b 0%, #041d52 60%, #061332 100%);
    border-right: 5px solid #d4a73d;
    border-radius: 0 92px 92px 0;
    padding: 42px 36px 28px;
    color: white;
    box-shadow: 18px 0 50px rgba(0,0,0,.32);
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 100;
    overflow: hidden;
}}

.side-panel::after {{
    content: "⚓";
    position: absolute;
    bottom: 26px;
    right: 34px;
    font-size: 7.6rem;
    opacity: .065;
}}

.side-logo {{
    margin-bottom: 44px;
}}

.side-anchor {{
    font-size: 3.3rem;
    color: #d4a73d;
    line-height: 1;
}}

.side-anp {{
    margin-top: 8px;
    font-size: 3.7rem;
    font-weight: 950;
    color: white;
    line-height: .88;
    letter-spacing: -.04em;
}}

.side-sub {{
    margin-top: 10px;
    color: #d4a73d;
    font-weight: 950;
    letter-spacing: .10em;
    font-size: .88rem;
}}

.side-section-title {{
    margin-top: 1rem;
    color: rgba(255,255,255,.92);
    font-size: .84rem;
    font-weight: 950;
    letter-spacing: .08em;
    text-transform: uppercase;
}}

.side-section-line {{
    width: 76px;
    height: 2px;
    margin-top: 13px;
    margin-bottom: 24px;
    background: #d4a73d;
}}

.feature-item {{
    display: flex;
    align-items: flex-start;
    gap: 14px;
    margin-bottom: 22px;
}}

.feature-icon {{
    width: 40px;
    min-width: 40px;
    height: 40px;
    border-radius: 14px;
    background: rgba(212,167,61,.14);
    border: 1px solid rgba(212,167,61,.30);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.28rem;
    color: #d4a73d;
}}

.feature-title {{
    color: white;
    font-size: .94rem;
    font-weight: 900;
}}

.feature-sub {{
    color: rgba(255,255,255,.72);
    font-size: .80rem;
    margin-top: 4px;
    line-height: 1.32;
}}

/* ===================== CENTER TITLE ===================== */
.main-brand-wrap {{
    margin-left: 330px !important;
    width: calc(100vw - 330px) !important;
    display: flex !important;
    justify-content: center !important;
    align-items: flex-start !important;
    padding-top: 0px !important;
    position: relative !important;
    z-index: 30 !important;
    transform: translateX(-25px) !important;
}}

.main-brand {{
    width: 100%;
    text-align: center !important;
    margin-top: 0px !important;
    margin-bottom: 0px !important;
}}

.brand-anchor {{
    font-size: 2.55rem !important;
    line-height: .95;
    color: #d4a73d;
    filter: drop-shadow(0 8px 18px rgba(0,0,0,.18));
}}

.brand-anp {{
    font-size: 3.25rem !important;
    font-weight: 950;
    color: #061b46;
    line-height: .82;
    letter-spacing: -.055em;
}}

.brand-sub {{
    color: #c89c2e;
    font-weight: 950;
    letter-spacing: .12em;
    font-size: .78rem !important;
    margin-top: .2rem !important;
}}

.brand-line {{
    width: 230px !important;
    height: 2px;
    margin: .45rem auto .35rem !important;
    background: linear-gradient(90deg, transparent, #d4a73d, transparent);
}}

.brand-title {{
    color: #061b46;
    font-weight: 950;
    font-size: 1.42rem !important;
    line-height: 1.05 !important;
    letter-spacing: -.035em;
}}

/* ===================== LOGIN CARD ===================== */
[data-testid="stForm"] {{
    position: relative !important;
    z-index: 20 !important;
    width: 100% !important;
    max-width: 350px !important;
    margin-left: calc(330px + ((100vw - 330px - 350px) / 2)) !important;
    margin-right: 0 !important;
    margin-top: 25px !important;
    margin-bottom: 0 !important;
    padding: 1.25rem 1.75rem 1.15rem !important;
    border-radius: 24px !important;
    border: 1px solid rgba(255,255,255,.72) !important;
    background: rgba(255,255,255,.94) !important;
    backdrop-filter: blur(22px) !important;
    box-shadow: 0 28px 76px rgba(15,23,42,.23) !important;
}}

[data-testid="stForm"] > div {{
    gap: .32rem !important;
}}

.card-head {{
    text-align: center;
    padding-bottom: .22rem;
}}

.card-anchor {{
    width: 54px !important;
    height: 54px !important;
    margin: 0 auto .48rem !important;
    border-radius: 50%;
    background: linear-gradient(135deg, #f8fbff, #e8eefc);
    border: 1px solid #dbe5f5;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.65rem !important;
    color: #1d4ed8;
    box-shadow:
        inset 0 1px 0 rgba(255,255,255,.9),
        0 12px 28px rgba(15,23,42,.08);
}}

.card-title {{
    font-size: 1.72rem !important;
    font-weight: 950;
    color: #061b46;
    letter-spacing: -.045em;
    line-height: 1;
}}

[data-testid="stForm"] label {{
    color: #334155 !important;
    font-size: .72rem !important;
    font-weight: 850 !important;
}}

.stTextInput {{
    margin-bottom: .12rem !important;
}}

.stTextInput input {{
    height: 40px !important;
    border-radius: 10px !important;
    border: 1px solid #dbe2ea !important;
    background: #ffffff !important;
    color: #0A1A2F !important;
    font-size: .86rem !important;
    font-weight: 750 !important;
    padding-left: 1rem !important;
    box-shadow: 0 6px 16px rgba(15,23,42,.045) !important;
}}

.stTextInput input:focus {{
    border-color: #0d2f75 !important;
    box-shadow: 0 0 0 4px rgba(13,47,117,.12) !important;
}}

.stTextInput input::placeholder {{
    color: #8b95a5 !important;
    font-weight: 700 !important;
}}

.stButton button {{
    height: 40px !important;
    border-radius: 10px !important;
    border: none !important;
    background: #0d2f75 !important;
    color: white !important;
    font-size: .86rem !important;
    font-weight: 900 !important;
    box-shadow: 0 14px 26px rgba(13,47,117,.22) !important;
    transition: all .18s ease !important;
}}

.stButton button:hover {{
    transform: translateY(-2px);
    background: #08245d !important;
    box-shadow: 0 18px 34px rgba(13,47,117,.30) !important;
}}

.stAlert {{
    max-width: 350px !important;
    margin: .55rem auto 0 !important;
    border-radius: 14px !important;
}}

@media(max-height: 760px) {{
    .side-panel {{ padding-top: 30px; }}
    .side-logo {{ margin-bottom: 28px; }}
    .feature-item {{ margin-bottom: 15px; }}
    .main-brand-wrap {{ padding-top: 0px !important; }}
    .brand-anchor {{ font-size: 2.2rem !important; }}
    .brand-anp {{ font-size: 3.05rem !important; }}
    .brand-title {{ font-size: 1.32rem !important; }}
    [data-testid="stForm"] {{
        padding: 1.05rem 1.55rem 1rem !important;
        margin-top: 18px !important;
    }}
}}

@media(max-width: 980px) {{
    html,
    body,
    .stApp {{
        overflow: auto !important;
    }}

    .side-panel {{
        position: relative;
        width: 100%;
        height: auto;
        min-height: auto;
        border-radius: 0 0 42px 42px;
        border-right: 0;
        border-bottom: 5px solid #d4a73d;
        padding: 28px 24px;
    }}

    .main-brand-wrap {{
        margin-left: 0 !important;
        width: 100% !important;
        transform: none !important;
        padding: 18px 16px 0 !important;
    }}

    [data-testid="stForm"] {{
        width: calc(100% - 32px) !important;
        max-width: 350px !important;
        margin-left: auto !important;
        margin-right: auto !important;
    }}
}}

@media(max-width: 600px) {{
    [data-testid="stForm"] {{
        padding: 1.25rem 1.1rem 1.2rem !important;
        border-radius: 22px !important;
    }}

    .brand-anchor {{ font-size: 2.2rem !important; }}
    .brand-anp {{ font-size: 2.85rem !important; }}
    .brand-title {{ font-size: 1.15rem !important; }}
    .card-title {{ font-size: 1.72rem !important; }}
}}
</style>
        """,
        unsafe_allow_html=True,
    )

    st.html(
        """
<aside class="side-panel">
    <div class="side-logo">
        <div class="side-anchor">⚓</div>
        <div class="side-anp">ANP</div>
        <div class="side-sub">PORT JORF LASFAR</div>
    </div>

    <div class="side-section-title">Notre engagement</div>
    <div class="side-section-line"></div>

    <div class="feature-item">
        <div class="feature-icon">🛡️</div>
        <div>
            <div class="feature-title">Sécurité</div>
            <div class="feature-sub">Vos données sont protégées et sécurisées</div>
        </div>
    </div>

    <div class="feature-item">
        <div class="feature-icon">📊</div>
        <div>
            <div class="feature-title">Performance</div>
            <div class="feature-sub">KPIs temps réel pour de meilleures décisions</div>
        </div>
    </div>

    <div class="feature-item">
        <div class="feature-icon">👥</div>
        <div>
            <div class="feature-title">Collaboration</div>
            <div class="feature-sub">Une plateforme unifiée pour tous les acteurs</div>
        </div>
    </div>

    <div class="feature-item">
        <div class="feature-icon">🕒</div>
        <div>
            <div class="feature-title">Disponibilité</div>
            <div class="feature-sub">Accès 24/7 aux données opérationnelles</div>
        </div>
    </div>
</aside>

<div class="main-brand-wrap">
    <div class="main-brand">
        <div class="brand-anchor">⚓</div>
        <div class="brand-anp">ANP</div>
        <div class="brand-sub">PORT JORF LASFAR</div>
        <div class="brand-line"></div>
        <div class="brand-title">SMART PORT OPERATIONS CENTER</div>
    </div>
</div>
        """
    )

    with st.form("login_form"):
        st.html(
            """
<div class="card-head">
    <div class="card-anchor">⚓</div>
    <div class="card-title">Bienvenue</div>
</div>
            """
        )

        username = st.text_input(
            "Nom d'utilisateur",
            placeholder="Entrez votre nom d'utilisateur",
        )

        password = st.text_input(
            "Mot de passe",
            type="password",
            placeholder="Entrez votre mot de passe",
        )

        submitted = st.form_submit_button(
            "🔒 Se connecter",
            use_container_width=True,
        )

        if submitted:
            if check_password_db(username, password):
                st.session_state.authenticated = True
                st.session_state.username = username

                user_info = get_user_info(username)

                st.session_state.user_role = user_info.get("role", "user")
                st.session_state.user_name = user_info.get("name", username)

                st.rerun()

            else:
                st.error("❌ Nom d'utilisateur ou mot de passe incorrect")


def logout():
    for key in ["authenticated", "username", "user_role", "user_name"]:
        if key in st.session_state:
            del st.session_state[key]

    st.rerun()


def is_authenticated() -> bool:
    return st.session_state.get("authenticated", False)


def has_permission(required_role: str = None) -> bool:
    if not is_authenticated():
        return False

    if required_role is None:
        return True

    role = st.session_state.get("user_role", "user")
    roles_order = ["admin", "user", "consignataire"]

    try:
        return roles_order.index(role) <= roles_order.index(required_role)

    except ValueError:
        return False


def show_user_info():
    if not is_authenticated():
        return

    st.sidebar.markdown("---")

    if st.sidebar.button("🚪 Déconnexion", use_container_width=True):
        logout()