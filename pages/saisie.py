"""
Page Saisie des données - ANP Port Jorf Lasfar
Version avancée avec :
- Nouvelle interface Marchandise conservée
- Type M intégré dans la liste déroulante avec option "Ajouter"
- Correspondance automatique Type M → Marchandise
- Plusieurs marchandises dynamiques
- Type de navire avec liste + Autre + Enregistrement
- Changement de poste avec bouton large
- Incident avec lieu (liste + Autre + Enregistrement)
- Incident avec consistance en texte libre
- Importation Excel intégrée
"""
import streamlit as st
from datetime import datetime, time
import re

from database import DBManager, OperationRow
from utils import calculer_temps_attente, calculer_temps_sejour
from validators import ValidationError, validate_complete_operation
from import_ui import render_escale_import, render_consignation_import


def show_saisie(db_manager: DBManager):
    """
    Affiche la page de saisie des données portuaires
    Version avancée avec toutes les nouvelles fonctionnalités
    """
    # ===================== CSS =====================
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
        * { box-sizing:border-box; font-family:'Inter', sans-serif; }
        
        :root {
            --s-navy: #06264A;
            --s-navy-2: #073B74;
            --s-blue: #0B5CFF;
            --s-blue-2: #1D75FF;
            --s-sky: #39A9FF;
            --s-gold: #D7B64A;
            --s-bg: #F3F8FF;
            --s-card: #FFFFFF;
            --s-border: #D7E5F5;
            --s-border-2: #BBD2EE;
            --s-text: #08244A;
            --s-muted: #617391;
            --s-green: #10B981;
            --s-red: #EF4444;
        }
        
        .stApp {
            background: linear-gradient(90deg, #05366C 0 92px, transparent 92px),
                        radial-gradient(circle at 18% 8%, rgba(57,169,255,.18), transparent 24%),
                        radial-gradient(circle at 86% 92%, rgba(11,92,255,.11), transparent 25%),
                        linear-gradient(135deg, #F6FAFF 0%, #FFFFFF 48%, #EEF6FF 100%) !important;
        }
        
        .stApp:before {
            content: "⚓\\A⌂\\A🚢\\A▣\\A🛡\\A📋\\A⚙";
            white-space: pre;
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: 92px;
            padding-top: 34px;
            text-align: center;
            color: white;
            font-size: 1.55rem;
            line-height: 4.15rem;
            z-index: 0;
            background: radial-gradient(circle at 50% 96%, rgba(57,169,255,.35), transparent 15%),
                        linear-gradient(180deg, #052B56, #075AA4 58%, #05366C);
            box-shadow: 10px 0 34px rgba(5,43,86,.20);
            pointer-events: none;
        }
        
        .stApp:after {
            content: "";
            position: fixed;
            right: -18px;
            top: 120px;
            width: 260px;
            height: 78vh;
            z-index: 0;
            pointer-events: none;
            opacity: .42;
            background-repeat: no-repeat;
            background-size: 100% 100%;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 260 820' fill='none'%3E%3Cg opacity='0.65' stroke='%2399CCFF' stroke-width='2'%3E%3Cpath d='M260 70 C190 95 175 155 260 190'/%3E%3Cpath d='M260 105 C178 135 158 205 260 250'/%3E%3Cpath d='M260 140 C168 180 135 260 260 315'/%3E%3Cpath d='M260 178 C155 228 112 320 260 385'/%3E%3Cpath d='M260 220 C142 280 90 390 260 468'/%3E%3Cpath d='M260 266 C130 340 70 465 260 552'/%3E%3Cpath d='M260 315 C120 405 52 545 260 640'/%3E%3Cpath d='M260 370 C110 475 35 625 260 738'/%3E%3C/g%3E%3C/svg%3E");
        }
        
        .block-container {
            padding-top: .70rem !important;
            padding-bottom: 1.15rem !important;
            padding-left: 118px !important;
            padding-right: 1.4rem !important;
            max-width: 1780px !important;
            position: relative;
            z-index: 2;
        }
        
        [data-testid="stToolbar"] { display: none !important; }
        #MainMenu, footer, header { visibility: hidden !important; }
        
        /* ===== HERO ===== */
        .saisie-hero {
            background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(245,250,255,.94));
            border: 1px solid var(--s-border);
            border-radius: 18px;
            padding: .95rem 1.2rem;
            box-shadow: 0 14px 34px rgba(8,36,74,.075);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin: .15rem 0 .90rem 0;
            position: relative;
            overflow: hidden;
        }
        
        .saisie-hero:before {
            content: "";
            position: absolute;
            left: 0;
            right: 0;
            top: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--s-blue), var(--s-sky), var(--s-gold));
        }
        
        .saisie-hero-left {
            display: flex;
            align-items: center;
            gap: .9rem;
            position: relative;
            z-index: 2;
        }
        
        .saisie-hero-icon {
            width: 52px;
            height: 52px;
            min-width: 52px;
            border-radius: 16px;
            background: linear-gradient(145deg, #063B78, #0B5CFF);
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.55rem;
            box-shadow: 0 15px 30px rgba(11,92,255,.24);
        }
        
        .saisie-hero-title {
            color: var(--s-text);
            font-size: 1.55rem;
            font-weight: 950;
            letter-spacing: -.045em;
            line-height: 1.05;
        }
        
        .saisie-hero-sub {
            color: #38557A;
            font-size: .82rem;
            font-weight: 720;
            margin-top: .22rem;
        }
        
        .date-chip {
            min-width: 185px;
            border: 1px solid var(--s-border);
            background: #fff;
            border-radius: 18px;
            padding: .75rem 1rem;
            box-shadow: 0 10px 24px rgba(8,36,74,.07);
            color: var(--s-text);
            font-weight: 950;
            font-size: .88rem;
            text-align: center;
            position: relative;
            z-index: 2;
        }
        
        .date-chip span {
            color: #2D5DB7;
            font-weight: 800;
        }
        
        /* ===== CARDS ===== */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--s-border) !important;
            border-radius: 18px !important;
            background: rgba(255,255,255,.94) !important;
            box-shadow: 0 12px 32px rgba(8,36,74,.07) !important;
            overflow: hidden !important;
            position: relative !important;
            backdrop-filter: blur(8px);
        }
        
        /* ===== SECTION HEAD ===== */
        .section-head {
            display: flex;
            align-items: center;
            gap: .58rem;
            padding-bottom: .66rem;
            margin-bottom: .70rem;
            border-bottom: 1px solid #E3EDF8;
            position: relative;
        }
        
        .section-head:after {
            content: "";
            position: absolute;
            left: 0;
            bottom: -1px;
            width: 76px;
            height: 2px;
            background: linear-gradient(90deg, var(--s-blue), var(--s-sky), transparent);
        }
        
        .section-icon {
            color: var(--s-blue);
            font-size: 1.10rem;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            background: #EEF6FF;
            border: 1px solid #B9D8FF;
        }
        
        .section-num {
            color: var(--s-gold);
            font-weight: 950;
            font-size: .82rem;
        }
        
        .section-title {
            color: var(--s-text);
            font-weight: 950;
            text-transform: uppercase;
            letter-spacing: .25px;
            font-size: .82rem;
        }
        
        /* ===== INPUTS ===== */
        .stTextInput>div>div>input,
        .stNumberInput>div>div>input,
        .stTextArea>div>textarea,
        .stDateInput>div>div>input,
        .stTimeInput>div>div>input {
            border-radius: 11px !important;
            border: 1px solid #D7E4F3 !important;
            background: #FFFFFF !important;
            color: #0F172A !important;
            min-height: 40px !important;
            font-size: .86rem !important;
            padding: .52rem .82rem !important;
            box-shadow: 0 4px 12px rgba(8,36,74,.035) !important;
        }
        
        .stSelectbox div[data-baseweb="select"] {
            border-radius: 11px !important;
            border: 1px solid #D7E4F3 !important;
            background: #FFFFFF !important;
            min-height: 40px !important;
            box-shadow: 0 4px 12px rgba(8,36,74,.035) !important;
        }
        
        .stTextInput label,
        .stSelectbox label,
        .stNumberInput label,
        .stTextArea label,
        .stDateInput label,
        .stTimeInput label,
        .stCheckbox label {
            color: var(--s-text) !important;
            font-weight: 800 !important;
            font-size: .74rem !important;
            margin-bottom: .14rem !important;
            letter-spacing: .08px !important;
        }
        
        /* ===== RESUME ===== */
        .resume-row {
            display: flex;
            justify-content: space-between;
            gap: .75rem;
            padding: .38rem 0;
            border-bottom: 1px dashed #DDE8F4;
            font-size: .76rem;
        }
        
        .resume-label {
            color: #28415F;
            font-weight: 850;
        }
        
        .resume-value {
            color: var(--s-text);
            font-weight: 950;
            text-align: right;
            max-width: 58%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        /* ===== BUTTONS ===== */
        .stButton>button {
            border-radius: 14px !important;
            min-height: 46px !important;
            font-weight: 950 !important;
            letter-spacing: .10px !important;
            transition: all .18s ease !important;
        }
        
        .stButton>button[kind="primary"],
        .stButton>button[data-testid="baseButton-primary"] {
            background: linear-gradient(135deg, #06264A, #073B74, #0B5CFF) !important;
            color: #FFFFFF !important;
            border: 1px solid rgba(255,255,255,.12) !important;
            box-shadow: 0 13px 28px rgba(6,38,74,.24) !important;
        }
        
        .stButton>button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 16px 34px rgba(8,36,74,.18) !important;
        }
        
        /* ===== BOUTON CHANGEMENT DE POSTE LARGE ===== */
        .st-key-add_poste_change button {
            width: 100% !important;
            min-height: 56px !important;
            font-size: 1.05rem !important;
            font-weight: 950 !important;
            letter-spacing: 1.5px !important;
            padding: 0.8rem 1.5rem !important;
            border-radius: 14px !important;
            border: 2px dashed #0066CC !important;
            background: linear-gradient(135deg, rgba(0,102,204,0.06), rgba(0,153,204,0.04)) !important;
            color: #0066CC !important;
            box-shadow: 0 4px 16px rgba(0,102,204,0.08) !important;
            transition: all 0.3s ease !important;
            text-transform: uppercase !important;
        }
        
        .st-key-add_poste_change button:hover {
            background: linear-gradient(135deg, #0066CC, #0099CC) !important;
            color: #FFFFFF !important;
            border: 2px solid #0066CC !important;
            box-shadow: 0 8px 32px rgba(0,102,204,0.25) !important;
            transform: translateY(-2px) !important;
        }
        
        .st-key-add_poste_change button:active {
            transform: translateY(0px) !important;
        }
        
        /* ===== MESSAGES ===== */
        .success-message {
            background: linear-gradient(135deg, #ECFDF5, #FFFFFF);
            border: 1px solid #A7F3D0;
            border-left: 4px solid #10B981;
            padding: 1rem 1.2rem;
            border-radius: 14px;
            margin: 1rem 0;
            color: #065F46;
            font-weight: 700;
            box-shadow: 0 10px 24px rgba(16,185,129,.08);
        }
        
        .error-message {
            background: linear-gradient(135deg, #FEF2F2, #FFFFFF);
            border: 1px solid #FECACA;
            border-left: 4px solid #EF4444;
            padding: 1rem 1.2rem;
            border-radius: 14px;
            margin: 1rem 0;
            color: #991B1B;
            font-weight: 700;
        }
        
        .footer-clean {
            text-align: center;
            color: var(--s-muted);
            font-size: .72rem;
            font-weight: 750;
            padding: .85rem 0 .3rem;
        }
        
        /* ===== CHANGEMENT DE POSTE - NOUVEAU DESIGN ===== */
        .poste-change-card {
            background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(248,252,255,.94));
            border: 2px solid #D4E1ED;
            border-radius: 18px;
            padding: 1rem 1.2rem 0.8rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 6px 28px rgba(0,31,63,.06);
            position: relative;
            overflow: hidden;
        }
        
        .poste-change-card::before {
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #0066CC, #0099CC, #009999);
        }
        
        .poste-change-header {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin-bottom: 0.8rem;
            color: #001F3F;
            font-weight: 900;
            font-size: 0.9rem;
            letter-spacing: 0.3px;
        }
        
        .poste-change-header .badge {
            background: linear-gradient(135deg, #0066CC, #0099CC);
            color: white;
            padding: 0.15rem 0.8rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 900;
        }
        
        .poste-change-row {
            display: grid;
            grid-template-columns: 1.2fr 1fr 1fr;
            gap: 0.8rem;
            align-items: center;
            margin-bottom: 0.5rem;
        }
        
        .poste-change-row .poste-label {
            font-weight: 800;
            color: #08244A;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .poste-change-row .poste-value {
            font-weight: 700;
            color: #0B5CFF;
        }
        
        @media (max-width: 768px) {
            .poste-change-row {
                grid-template-columns: 1fr;
                gap: 0.5rem;
            }
        }
        
        /* ===== INCIDENTS ===== */
        .incident-row {
            display: grid;
            grid-template-columns: 2fr 1.5fr 1.5fr 2fr 0.8fr;
            gap: 0.8rem;
            align-items: center;
            padding: 0.7rem 0.8rem;
            border-radius: 12px;
            border-bottom: 1px solid #E3EDF8;
            transition: all 0.2s ease;
        }
        
        .incident-row:hover { background: #F0F7FF; }
        
        .incident-row.header {
            background: linear-gradient(135deg, #06264A, #0B5CFF);
            color: white;
            font-weight: 900;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-radius: 14px 14px 0 0;
            border-bottom: none;
            padding: 0.8rem 0.8rem;
        }
        
        .incident-row.header:hover { background: linear-gradient(135deg, #06264A, #0B5CFF); }
        .incident-nature { font-weight: 800; color: #08244A; }
        .incident-lieu { font-weight: 700; color: #38557A; }
        .incident-consistance { font-weight: 700; color: #38557A; }
        .incident-date { font-weight: 700; color: #38557A; }
        
        .btn-remove-incident {
            color: #EF4444;
            font-weight: 900;
            cursor: pointer;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            border: 1px solid #EF4444;
            background: rgba(239,68,68,0.05);
            transition: all 0.2s ease;
            text-align: center;
            font-size: 0.75rem;
        }
        
        .btn-remove-incident:hover { background: rgba(239,68,68,0.15); }
        
        .empty-state {
            text-align: center;
            padding: 2rem 1rem;
            color: #6B8BA3;
        }
        
        .empty-state .empty-icon { font-size: 3rem; opacity: 0.5; }
        .empty-state .empty-text { font-size: 1rem; font-weight: 700; margin-top: 0.5rem; }
        
        /* ===== IMPORT TAB STYLES ===== */
        .import-tab-header {
            background: linear-gradient(135deg, #f0f4ff, #e8edf5);
            padding: 1.5rem;
            border-radius: 16px;
            margin-bottom: 1.5rem;
        }
        .import-tab-header h2 {
            color: #0a1a2f;
            margin: 0;
            font-weight: 800;
        }
        .import-tab-header p {
            color: #4b5563;
            margin: 0.5rem 0 0 0;
            font-size: 0.95rem;
        }
        
        @media (max-width: 1200px) {
            .stApp {
                background: linear-gradient(135deg, #F6FAFF, #FFFFFF, #EEF6FF) !important;
            }
            .stApp:before, .stApp:after { display: none !important; }
            .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
        }
        
        @media (max-width: 768px) {
            .incident-row { grid-template-columns: 1fr; gap: 0.3rem; padding: 0.8rem; }
            .incident-row.header { display: none; }
        }
    </style>
    """, unsafe_allow_html=True)

    # ===================== HEADER =====================
    st.markdown(f"""
    <div class="saisie-hero">
        <div class="saisie-hero-left">
            <div class="saisie-hero-icon">⚓</div>
            <div>
                <div class="saisie-hero-title">Saisie des opérations portuaires</div>
                <div class="saisie-hero-sub">Système de gestion des escales maritimes</div>
            </div>
        </div>
        <div class="date-chip">📅 {datetime.now().strftime('%d %b %Y')}<br><span>{datetime.now().strftime('%H:%M')}</span></div>
    </div>
    """, unsafe_allow_html=True)

    # ===================== FONCTIONS UTILITAIRES =====================
    def validate_time_format(time_str: str):
        if not time_str:
            return 0, 0, False
        match = re.match(r'^(\d{1,2}):(\d{2})(?::\d{2})?$', time_str.strip())
        if not match:
            return 0, 0, False
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return 0, 0, False
        return hour, minute, True

    def clean_value(v):
        if v is None or (isinstance(v, str) and v.startswith("Sélectionner")):
            return "-"
        return str(v) if str(v).strip() else "-"

    # ===================== SESSION STATE INIT =====================
    if "poste_changes" not in st.session_state:
        st.session_state.poste_changes = []
    
    if "custom_types_m" not in st.session_state:
        st.session_state.custom_types_m = []
    
    if "custom_lieux" not in st.session_state:
        st.session_state.custom_lieux = []

    if "incidents_list" not in st.session_state:
        st.session_state.incidents_list = []

    # ===================== LISTES =====================
    # Nouvelle liste des postes
    POSTES = [
        "1N", "1S", "1Bis", "1Ter",
        "2N", "2Bis", "2Ter",
        "4", "4Bis", "5", "6", "7",
        "3", "3Bis",
        "9",
        "14S",
        "8", "14N", "16N", "16S", "11_12", "13",
        "10"
    ]

    # Liste des opérateurs par poste
    OPERATEURS_PAR_POSTE = {
        "OCP": ["1N", "1S", "1Bis", "1Ter", "2N", "2Bis", "2Ter", "4", "4Bis", "5", "6", "7"],
        "JLEC": ["3", "3Bis"],
        "HYDROCARB JORF": ["9"],
        "MASS CEREALES": ["14S"],
        "MARSA MAROC": ["8", "14N", "16N", "16S", "11_12", "13"],
        "SONASID": ["10"],
    }

    # ==================== CORRESPONDANCE TYPE M ↔ MARCHANDISES ====================
    TYPE_M_MAPPING = {
        "O2": ["Engrais vrac"],
        "MM15": ["Ferrailles en vrac", "Ferraille"],
        "SO15": ["Ferrailles en vrac"],
        "MM10": ["Gasoil", "Gasoline", "Jet A1", "Fuel Oil", "Gasoil + Gasoline"],
        "H10": ["Gasoil", "Gasoline", "Jet A1", "Fuel Oil", "Huile de base"],
        "MM22": ["Billettes"],
        "MS11": ["Blé tendre", "Blé dur", "Maïs"],
        "MM12": ["Pulpe de betterave", "Pulpes de betteraves"],
        "MM13": ["Barytine", "Anthracite en vrac"],
        "MM18": ["L.A.B", "Oxide aluminium"],
        "MM17": ["Sucre brut", "Sacs sucre"],
        "MM17S": ["Soufre en vrac"],
        "SO15S": ["Fer briqueté à chaud (HBI)"],
        "MM30": ["Bovins", "Sable"],
        "MM25": ["Matériels divers"],
        "MM9": ["Butane", "Propane", "Butane + Propane"],
        "MM8": ["Coke de pétroles"],
        "MM2D": ["Amonitrate"],
        "MM2": ["Sulfate d'ammonium"],
        "MS12": ["Tourteaux de soja"],
        "O3": ["Soufre en vrac", "Soufre solide"],
        "O5": ["Acide phosphorique", "Acide purifié"],
        "O6": ["Acide sulfurique"],
        "O7": ["Ammoniac"],
        "J8": ["Charbon"],
        "H9": ["Butane"],
        "A": ["Valeur vide / Divers"]
    }

    # Liste des Type M (avec ajout personnalisé)
    TYPE_M_BASE = list(TYPE_M_MAPPING.keys())
    TYPE_M_LIST = sorted(list(set(TYPE_M_BASE + st.session_state.custom_types_m)))

    # ============================================================
    # TYPE DE NAVIRE avec liste + Autre + Ajout permanent
    # ============================================================
    if "custom_types_navire" not in st.session_state:
        st.session_state.custom_types_navire = []

    TYPE_NAVIRE_BASE = [
        "Sélectionner le type de navire",
        "Vraquier",
        "Minéralier",
        "Phosphatier",
        "Céréalier",
        "Soufrier",
        "Chimiquier",
        "Hydrocarbure (Pétrolier/Tanker)",
        "Conventionnel"
    ]

    TYPE_NAVIRE_LIST = TYPE_NAVIRE_BASE + st.session_state.custom_types_navire

    # ============================================================
    # LIEUX POUR INCIDENTS (avec ajout personnalisé)
    # ============================================================
    LIEUX_BASE = [
        "1N", "1S", "1Bis", "1Ter",
        "2N", "2Bis", "2Ter",
        "4", "4Bis", "5", "6", "7",
        "3", "3Bis",
        "9",
        "14S",
        "8", "14N", "16N", "16S", "11_12", "13",
        "10",
        "Rade",
        "Digue principale et contre digue",
        "Quai de Servitude",
        "Entrée Nord du Port",
        "Capitainerie",
        "Port de pêche",
        "Autre"
    ]

    LIEUX_INCIDENTS = LIEUX_BASE + st.session_state.custom_lieux

    # ============================================================
    # MODE DE CONDITIONNEMENT - NOUVELLE LISTE
    # ============================================================
    MODE_CONDITIONNEMENT_LIST = ["V", "L", "C", "ANP"]

    # Liste des consignataires
    CONSIGNATAIRES = [
        "Sélectionner le consignataire",
        "ACACIA MARITIME", "AGEMAFRIC", "AGENCE MED", "ANP",
        "ATLANTIC TRADING AND SHIPPING", "BABORD MAROC S.A (BABMARSA)",
        "BCMCC", "CCCM", "COMATAM", "GLOBAL CARGO LEADER",
        "GLOBAL SEA SERVICES", "GLOBE MARINE",
        "HARBOUR & MARITIME SERVICES AGENCY", "IDEA MAROC",
        "LASRY MAROC", "MARBAR", "MARMEDSA MAROC", "M S S",
        "NAXCO SHIPPING", "NOATUM MARITIME MOROCCO",
        "NOBLE SHIPPING", "PEREZ Y CIA MAROC", "SEATRADE",
        "SOCONAV", "SOMASAF", "TRADE NAV", "TRANSPORTS MAROCAINS",
        "UNIVERSAL SHIPPING", "WAFA SHIPPING", "WORLDWIDE SERVICES AGENCY"
    ]

    # ===================== 4 ONGLETS (dont Import Excel) =====================
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚢 Gestion des Escales",
        "⚓ Gestion des Consignations",
        "🚨 Gestion des incidents",
        "📥 Importation Excel"
    ])

    # ==================== TAB1: Gestion des Escales ====================
    with tab1:
        main_col, side_col = st.columns([2.35, 1], gap="medium")

        # ==================== MAIN COLUMN ====================
        with main_col:
            # --- Section 01: Informations navire ---
            with st.container(border=True):
                st.markdown('<div class="section-head"><span class="section-icon">🚢</span><span class="section-num">01</span><span class="section-title">Informations navire</span></div>', unsafe_allow_html=True)
                col1, col2 = st.columns(2, gap="large")

                with col1:
                    navire = st.text_input("Nom du navire", placeholder="Ex: MSC Houston")
                    pavillon = st.text_input("Pavillon", placeholder="Ex: Panama")
                    
                    # Type de navire avec liste + Autre + Ajout permanent
                    type_navire = st.selectbox(
                        "Type de navire",
                        TYPE_NAVIRE_LIST,
                        key="type_navire_select"
                    )
                    
                    if type_navire == "Autre":
                        type_navire_autre = st.text_input(
                            "✏️ Précisez le type de navire",
                            placeholder="Ex: Navire de recherche, Bateau-pilote, etc.",
                            key="type_navire_autre"
                        )
                        
                        col_btn_ajouter, col_btn_annuler = st.columns(2)
                        with col_btn_ajouter:
                            if st.button("➕ Ajouter ce type à la liste", key="add_type_navire_btn"):
                                if type_navire_autre and type_navire_autre.strip():
                                    nouveau_type = type_navire_autre.strip()
                                    if nouveau_type not in TYPE_NAVIRE_LIST:
                                        st.session_state.custom_types_navire.append(nouveau_type)
                                        st.success(f"✅ Le type '{nouveau_type}' a été ajouté à la liste !")
                                        st.rerun()
                                    else:
                                        st.warning(f"⚠️ Le type '{nouveau_type}' existe déjà dans la liste.")
                                else:
                                    st.warning("⚠️ Veuillez saisir un type de navire avant d'ajouter.")
                        
                        with col_btn_annuler:
                            if st.button("❌ Annuler", key="cancel_type_navire"):
                                st.rerun()
                        
                        if type_navire_autre:
                            type_navire_final = type_navire_autre
                        else:
                            type_navire_final = "Autre"
                    else:
                        type_navire_final = type_navire

                    operateur = st.selectbox(
                        "Opérateur",
                        ["Sélectionner l'opérateur"] + list(OPERATEURS_PAR_POSTE.keys()),
                        key="operateur_select"
                    )

                postes_options = OPERATEURS_PAR_POSTE.get(operateur, [])

                with col2:
                    numero_navire = st.text_input("Escale", placeholder="Ex: IMO 1234567")
                    
                    if postes_options:
                        poste = st.selectbox(
                            "Poste",
                            postes_options,
                            key="poste_select"
                        )
                    else:
                        poste = st.selectbox(
                            "Poste",
                            ["Sélectionner d'abord l'opérateur"],
                            key="poste_select"
                        )
                    
                    consignataire = st.selectbox("Consignataire", CONSIGNATAIRES)

            # --- Section 02: Horaires ---
            with st.container(border=True):
                st.markdown('<div class="section-head"><span class="section-icon">🕘</span><span class="section-num">02</span><span class="section-title">Horaires</span></div>', unsafe_allow_html=True)

                # Rade
                col_rade1, col_rade2 = st.columns(2, gap="large")
                with col_rade1:
                    date_rade = st.date_input("📅 Date Rade", datetime.now())
                with col_rade2:
                    heure_rade_str = st.text_input("⏰ Heure Rade", value="06:00", placeholder="HH:MM", key="heure_rade")
                    h, m, ok = validate_time_format(heure_rade_str)
                    heure_rade = time(h, m) if ok else time(6, 0)

                # Mouillage
                col_mou1, col_mou2 = st.columns(2, gap="large")
                with col_mou1:
                    date_mouillage = st.date_input("📅 Date Mouillage", datetime.now())
                with col_mou2:
                    heure_mouillage_str = st.text_input("⏰ Heure Mouillage", value="08:00", placeholder="HH:MM", key="heure_mouillage")
                    h, m, ok = validate_time_format(heure_mouillage_str)
                    heure_mouillage = time(h, m) if ok else time(8, 0)

                # Sortie Mouillage
                col_sor1, col_sor2 = st.columns(2, gap="large")
                with col_sor1:
                    date_sortie_mouillage = st.date_input("📅 Date Sortie Mouillage", datetime.now())
                with col_sor2:
                    heure_sortie_mouillage_str = st.text_input("⏰ Heure Sortie Mouillage", value="09:00", placeholder="HH:MM", key="heure_sortie_mouillage")
                    h, m, ok = validate_time_format(heure_sortie_mouillage_str)
                    heure_sortie_mouillage = time(h, m) if ok else time(9, 0)

                # Accostage
                col_acc1, col_acc2 = st.columns(2, gap="large")
                with col_acc1:
                    date_accostage = st.date_input("📅 Date Accostage", datetime.now())
                with col_acc2:
                    heure_accostage_str = st.text_input("⏰ Heure Accostage", value="10:00", placeholder="HH:MM", key="heure_accostage")
                    h, m, ok = validate_time_format(heure_accostage_str)
                    heure_accostage = time(h, m) if ok else time(10, 0)

                # Appareillage Quai
                col_appq1, col_appq2 = st.columns(2, gap="large")
                with col_appq1:
                    date_app_quai = st.date_input("📅 Date Appareillage Quai", datetime.now())
                with col_appq2:
                    heure_app_quai_str = st.text_input("⏰ Heure Appareillage Quai", value="17:00", placeholder="HH:MM", key="heure_app_quai")
                    h, m, ok = validate_time_format(heure_app_quai_str)
                    heure_app_quai = time(h, m) if ok else time(17, 0)

                # ============================================================
                # CHANGEMENT DE POSTE - VERSION AVEC MOUILLAGE ET SORTIE MOUILLAGE
                # ============================================================
                st.markdown('<div style="margin-top: 1.2rem;"></div>', unsafe_allow_html=True)
                
                st.markdown("""
                <div style="display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.8rem; background: rgba(0,102,204,0.05); border-radius: 10px; border-left: 4px solid #0066CC; margin-bottom: 0.8rem; font-size: 0.78rem; color: #4A6478;">
                    <span style="font-size: 1.1rem;">ℹ️</span>
                    <span>Cliquez sur le bouton ci-dessous pour ajouter un changement de poste. Les champs Mouillage et Sortie Mouillage sont optionnels.</span>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(
                    "🔄  CHANGEMENT DE POSTE",
                    key="add_poste_change",
                    use_container_width=True,
                    help="Cliquez pour ajouter un changement de poste"
                ):
                    new_change = {
                        "id": len(st.session_state.poste_changes) + 1,
                        "poste": POSTES[0] if POSTES else "",
                        # Nouveaux champs optionnels
                        "date_mouillage": datetime.now(),
                        "heure_mouillage": "12:00",
                        "date_sortie_mouillage": datetime.now(),
                        "heure_sortie_mouillage": "12:30",
                        # Champs existants
                        "date_accostage": datetime.now(),
                        "heure_accostage": "13:00",
                        "date_app_quai": datetime.now(),
                        "heure_app_quai": "17:00"
                    }
                    st.session_state.poste_changes.append(new_change)
                    st.rerun()

                for idx, change in enumerate(st.session_state.poste_changes):
                    change_id = change["id"]
                    st.markdown(f"""
                    <div class="poste-change-card">
                        <div class="poste-change-header">
                            <span>🔄 Changement de poste #{change_id}</span>
                            <span class="badge">Bloc {idx + 1}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Poste
                    col_poste, _ = st.columns([1, 1])
                    with col_poste:
                        poste_change_value = st.selectbox(
                            f"POSTE #{change_id}",
                            POSTES,
                            index=POSTES.index(change["poste"]) if change["poste"] in POSTES else 0,
                            key=f"poste_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["poste"] = poste_change_value
                    
                    # ============================================================
                    # NOUVEAUX CHAMPS : Mouillage et Sortie Mouillage (OPTIONNELS)
                    # ============================================================
                    st.markdown('<div style="font-size:0.7rem;color:#6B7280;margin:0.2rem 0 0.4rem 0;">🌊 Mouillage (optionnel)</div>', unsafe_allow_html=True)
                    
                    col_mouillage1, col_mouillage2 = st.columns(2, gap="large")
                    with col_mouillage1:
                        date_mouillage_change = st.date_input(
                            f"📅 Date Mouillage #{change_id}",
                            value=change.get("date_mouillage", datetime.now()),
                            key=f"date_mouillage_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["date_mouillage"] = date_mouillage_change
                    with col_mouillage2:
                        heure_mouillage_change_str = st.text_input(
                            f"⏰ Heure Mouillage #{change_id}",
                            value=change.get("heure_mouillage", "12:00"),
                            placeholder="HH:MM",
                            key=f"heure_mouillage_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["heure_mouillage"] = heure_mouillage_change_str
                    
                    col_sortie1, col_sortie2 = st.columns(2, gap="large")
                    with col_sortie1:
                        date_sortie_mouillage_change = st.date_input(
                            f"📅 Date Sortie Mouillage #{change_id}",
                            value=change.get("date_sortie_mouillage", datetime.now()),
                            key=f"date_sortie_mouillage_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["date_sortie_mouillage"] = date_sortie_mouillage_change
                    with col_sortie2:
                        heure_sortie_mouillage_change_str = st.text_input(
                            f"⏰ Heure Sortie Mouillage #{change_id}",
                            value=change.get("heure_sortie_mouillage", "12:30"),
                            placeholder="HH:MM",
                            key=f"heure_sortie_mouillage_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["heure_sortie_mouillage"] = heure_sortie_mouillage_change_str
                    
                    st.markdown('<hr style="margin:0.5rem 0;opacity:0.2;">', unsafe_allow_html=True)
                    
                    # ============================================================
                    # CHAMPS EXISTANTS : Accostage et Appareillage Quai
                    # ============================================================
                    st.markdown('<div style="font-size:0.7rem;color:#0B5CFF;margin:0.2rem 0 0.4rem 0;">⚓ Accostage et Appareillage Quai</div>', unsafe_allow_html=True)
                    
                    col_p1, col_p2 = st.columns(2, gap="large")
                    with col_p1:
                        date_acc_change = st.date_input(
                            f"📅 Date Accostage #{change_id}",
                            value=change.get("date_accostage", datetime.now()),
                            key=f"date_acc_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["date_accostage"] = date_acc_change
                        
                        date_appq_change = st.date_input(
                            f"📅 Date Appareillage Quai #{change_id}",
                            value=change.get("date_app_quai", datetime.now()),
                            key=f"date_appq_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["date_app_quai"] = date_appq_change
                    
                    with col_p2:
                        heure_acc_change_str = st.text_input(
                            f"⏰ Heure Accostage #{change_id}",
                            value=change.get("heure_accostage", "13:00"),
                            placeholder="HH:MM",
                            key=f"heure_acc_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["heure_accostage"] = heure_acc_change_str
                        
                        heure_appq_change_str = st.text_input(
                            f"⏰ Heure Appareillage Quai #{change_id}",
                            value=change.get("heure_app_quai", "17:00"),
                            placeholder="HH:MM",
                            key=f"heure_appq_change_{change_id}"
                        )
                        st.session_state.poste_changes[idx]["heure_app_quai"] = heure_appq_change_str
                    
                    # Bouton Supprimer
                    if st.button(f"🗑️ Supprimer le changement #{change_id}", key=f"remove_change_{change_id}"):
                        st.session_state.poste_changes = [c for c in st.session_state.poste_changes if c["id"] != change_id]
                        st.rerun()
                    
                    st.markdown("<hr style='margin: 0.8rem 0; opacity: 0.3;'>", unsafe_allow_html=True)

                # Appareillage Port
                col_appp1, col_appp2 = st.columns(2, gap="large")
                with col_appp1:
                    date_app_port = st.date_input("📅 Date Appareillage Port", datetime.now())
                with col_appp2:
                    heure_app_port_str = st.text_input("⏰ Heure Appareillage Port", value="18:00", placeholder="HH:MM", key="heure_app_port")
                    h, m, ok = validate_time_format(heure_app_port_str)
                    heure_app_port = time(h, m) if ok else time(18, 0)

            # --- Section 03: Marchandise ---
            with st.container(border=True):
                st.markdown('<div class="section-head"><span class="section-icon">📦</span><span class="section-num">03</span><span class="section-title">Marchandise</span></div>', unsafe_allow_html=True)

                nombre_marchandises = st.number_input(
                    "Nombre de marchandises",
                    min_value=1,
                    max_value=20,
                    value=1,
                    step=1,
                    key="nombre_marchandises",
                )

                marchandises = []

                for i in range(int(nombre_marchandises)):
                    st.markdown(
                        f'<div style="font-weight:900;color:#0B5CFF;margin:.65rem 0 .25rem;">📦 Marchandise #{i + 1}</div>',
                        unsafe_allow_html=True,
                    )

                    col_mar1, col_mar2 = st.columns(2, gap="large")

                    with col_mar1:
                        # Type d'opération
                        type_operation_i = st.selectbox(
                            f"Type d'opération #{i + 1}",
                            ["Sélectionner le type d'opération", "Export", "Import", "Cabotage"],
                            key=f"type_operation_marchandise_{i}",
                        )
                        
                        # Type M avec option "➕ Ajouter un nouveau type"
                        type_m_options = ["Sélectionner un Type M"] + TYPE_M_LIST + ["➕ Ajouter un nouveau type"]
                        type_m_selected = st.selectbox(
                            f"Type M #{i + 1}",
                            type_m_options,
                            key=f"type_m_{i}"
                        )
                        
                        # Si l'utilisateur choisit "➕ Ajouter un nouveau type"
                        if type_m_selected == "➕ Ajouter un nouveau type":
                            st.markdown('<div style="background: #F0F6FF; padding: 0.8rem; border-radius: 12px; border: 1px solid #B9D8FF; margin: 0.3rem 0;">', unsafe_allow_html=True)
                            st.markdown('<span style="font-weight:800;color:#06264A;">✏️ Nouveau Type M</span>', unsafe_allow_html=True)
                            
                            col_new1, col_new2 = st.columns(2)
                            with col_new1:
                                new_type_m = st.text_input(
                                    "Nom du nouveau Type M",
                                    placeholder="Ex: ABC45",
                                    key=f"new_type_m_input_{i}"
                                )
                            with col_new2:
                                new_type_m_marchandise = st.text_input(
                                    "Marchandises (séparées par des virgules)",
                                    placeholder="Ex: Produit A, Produit B",
                                    key=f"new_type_m_marchandise_{i}"
                                )
                            
                            col_btn_ok, col_btn_cancel = st.columns(2)
                            with col_btn_ok:
                                if st.button("✅ Ajouter", key=f"confirm_add_type_m_{i}"):
                                    if new_type_m and new_type_m.strip():
                                        type_upper = new_type_m.strip().upper()
                                        if type_upper not in TYPE_M_LIST:
                                            st.session_state.custom_types_m.append(type_upper)
                                            if new_type_m_marchandise.strip():
                                                marchandises_associees = [m.strip() for m in new_type_m_marchandise.split(",") if m.strip()]
                                                TYPE_M_MAPPING[type_upper] = marchandises_associees
                                            else:
                                                TYPE_M_MAPPING[type_upper] = ["Marchandise à définir"]
                                            st.success(f"✅ Le Type M '{type_upper}' a été ajouté !")
                                            st.rerun()
                                        else:
                                            st.warning(f"⚠️ Le Type M '{type_upper}' existe déjà.")
                                    else:
                                        st.warning("⚠️ Veuillez entrer un nom de Type M.")
                            with col_btn_cancel:
                                if st.button("❌ Annuler", key=f"cancel_add_type_m_{i}"):
                                    st.rerun()
                            st.markdown('</div>', unsafe_allow_html=True)
                            
                            type_m_selected = "Sélectionner un Type M"
                        
                        # Détermination des marchandises correspondantes
                        if type_m_selected != "Sélectionner un Type M" and type_m_selected in TYPE_M_MAPPING:
                            marchandises_correspondantes = TYPE_M_MAPPING[type_m_selected]
                            marchandises_options = ["Sélectionner"] + marchandises_correspondantes
                        else:
                            marchandises_options = ["Sélectionner un Type M d'abord"]
                        
                        # Marchandise (liste déroulante dépendante du Type M)
                        if len(marchandises_options) > 1:
                            type_marchandise_i = st.selectbox(
                                f"Marchandise #{i + 1}",
                                marchandises_options,
                                key=f"marchandise_select_{i}"
                            )
                            if type_marchandise_i == "Sélectionner":
                                type_marchandise_i = ""
                        else:
                            type_marchandise_i = st.selectbox(
                                f"Marchandise #{i + 1}",
                                marchandises_options,
                                key=f"marchandise_select_{i}"
                            )
                            if type_marchandise_i == "Sélectionner un Type M d'abord":
                                type_marchandise_i = ""

                        mode_conditionnement_i = st.selectbox(
                            f"Mode de conditionnement #{i + 1}",
                            ["Sélectionner le mode de conditionnement"] + MODE_CONDITIONNEMENT_LIST,
                            key=f"mode_conditionnement_{i}",
                        )

                    with col_mar2:
                        quantite_i = st.text_input(
                            f"Quantité #{i + 1}",
                            placeholder="Ex: 1500",
                            key=f"quantite_marchandise_{i}",
                        )
                        unite_i = st.selectbox(
                            f"Unité #{i + 1}",
                            ["Sélectionner l'unité", "Conteneur", "M3", "Tonnes"],
                            key=f"unite_marchandise_{i}",
                        )

                    marchandises.append({
                        "type_operation": type_operation_i,
                        "type_m": type_m_selected if type_m_selected not in ["Sélectionner un Type M", "➕ Ajouter un nouveau type"] else "",
                        "type_marchandise": type_marchandise_i,
                        "mode_conditionnement": mode_conditionnement_i,
                        "quantite": quantite_i,
                        "unite": unite_i,
                    })

                premiere_marchandise = marchandises[0] if marchandises else {}
                type_operation = premiere_marchandise.get("type_operation", "Sélectionner le type d'opération")
                type_m = premiere_marchandise.get("type_m", "")
                type_marchandise = premiere_marchandise.get("type_marchandise", "")
                mode_conditionnement = premiere_marchandise.get("mode_conditionnement", "Sélectionner le mode de conditionnement")
                quantite = premiere_marchandise.get("quantite", "")
                unite = premiere_marchandise.get("unite", "Sélectionner l'unité")

        # ==================== SIDE COLUMN ====================
        with side_col:
            # Section 04: Observations
            with st.container(border=True):
                st.markdown('<div class="section-head"><span class="section-icon">📝</span><span class="section-num">04</span><span class="section-title">Observations</span></div>', unsafe_allow_html=True)
                observations = st.text_area("Notes complémentaires", placeholder="Observations sur l'opération...", height=200)

            # Section 05: Résumé
            with st.container(border=True):
                st.markdown('<div class="section-head"><span class="section-icon">📋</span><span class="section-num">05</span><span class="section-title">Résumé de l\'opération</span></div>', unsafe_allow_html=True)

                # Compter les changements de poste avec mouillage
                nb_changes_avec_mouillage = 0
                for change in st.session_state.poste_changes:
                    if change.get("date_mouillage") and change.get("heure_mouillage"):
                        nb_changes_avec_mouillage += 1

                resume_items = [
                    ("Navire", clean_value(navire)),
                    ("Escale", clean_value(numero_navire)),
                    ("Type Navire", clean_value(type_navire_final)),
                    ("Poste", clean_value(poste)),
                    ("Opérateur", clean_value(operateur)),
                    ("Consignataire", clean_value(consignataire)),
                    ("Rade", f"{date_rade} {heure_rade_str}"),
                    ("Mouillage", f"{date_mouillage} {heure_mouillage_str}"),
                    ("Sortie Mouillage", f"{date_sortie_mouillage} {heure_sortie_mouillage_str}"),
                    ("Accostage", f"{date_accostage} {heure_accostage_str}"),
                    ("App. Quai", f"{date_app_quai} {heure_app_quai_str}"),
                    ("App. Port", f"{date_app_port} {heure_app_port_str}"),
                    ("Nb changements poste", str(len(st.session_state.poste_changes))),
                    ("Dont avec mouillage", str(nb_changes_avec_mouillage)),
                    ("Nb marchandises", str(len(marchandises))),
                    ("Type M", clean_value(type_m)),
                    ("Type opération", clean_value(type_operation)),
                    ("Marchandises", clean_value(type_marchandise)),
                    ("Quantité", f"{clean_value(quantite)} {'' if unite.startswith('Sélectionner') else unite}"),
                ]
                for label, value in resume_items:
                    st.markdown(f'<div class="resume-row"><span class="resume-label">{label}</span><span class="resume-value">{value}</span></div>', unsafe_allow_html=True)

            # Boutons
            submit = st.button("💾 Enregistrer l'opération", use_container_width=True, type="primary")
            if st.button("↻ Réinitialiser", use_container_width=True):
                st.session_state.poste_changes = []
                st.session_state.custom_types_m = []
                st.session_state.custom_lieux = []
                st.session_state.incidents_list = []
                st.rerun()

        # ==================== SUBMIT ====================
        if submit:
            if (not navire or
                operateur.startswith("Sélectionner") or
                poste.startswith("Sélectionner") or
                consignataire.startswith("Sélectionner") or
                type_operation.startswith("Sélectionner") or
                type_marchandise.startswith("Sélectionner") or
                mode_conditionnement.startswith("Sélectionner") or
                unite.startswith("Sélectionner")):
                st.markdown("""
                <div class="error-message">
                    ❌ Veuillez compléter tous les champs obligatoires (Navire, Opérateur, Poste, Consignataire, Marchandise).
                </div>
                """, unsafe_allow_html=True)
                return

            try:
                quantite_float = 0.0
                marchandises_valides = []

                for idx, m in enumerate(marchandises, start=1):
                    if (m["type_operation"].startswith("Sélectionner") or
                        m["mode_conditionnement"].startswith("Sélectionner") or
                        m["unite"].startswith("Sélectionner") or
                        not str(m["quantite"]).strip()):
                        st.error(f"❌ Veuillez compléter tous les champs de la marchandise #{idx}.")
                        return

                    qte = float(str(m["quantite"]).replace(",", "."))
                    if qte <= 0:
                        st.error(f"❌ La quantité de la marchandise #{idx} doit être supérieure à 0.")
                        return

                    m_clean = dict(m)
                    m_clean["quantite_float"] = qte
                    marchandises_valides.append(m_clean)
                    quantite_float += qte

                type_operation = marchandises_valides[0]["type_operation"]
                type_m = marchandises_valides[0].get("type_m", "")
                type_marchandise = marchandises_valides[0]["type_marchandise"]
                mode_conditionnement = marchandises_valides[0]["mode_conditionnement"]
                unite = marchandises_valides[0]["unite"]

            except ValueError:
                st.error("❌ Quantité non valide. Entrez un nombre pour chaque marchandise.")
                return

            try:
                temps_attente = calculer_temps_attente(heure_rade, heure_mouillage, date_rade, date_mouillage)
                temps_sejour = calculer_temps_sejour(heure_accostage, heure_app_quai, date_accostage, date_app_quai)

                duree_heures = temps_sejour if temps_sejour and temps_sejour > 0 else 1
                productivite_h = quantite_float / duree_heures if quantite_float > 0 else 0

                observations_finales = (
                    f"Type M : {type_m}\n"
                    f"Type des marchandises : {type_marchandise}\n"
                    f"Mode de conditionnement : {mode_conditionnement}\n"
                    f"Changements de poste : {len(st.session_state.poste_changes)}\n"
                    f"{observations}"
                )

                operation_data = {
                    "navire": navire,
                    "numero_navire": numero_navire,
                    "pavillon": pavillon,
                    "type_navire": type_navire_final,
                    "poste": poste,
                    "agent": consignataire,
                    "type_operation": type_operation,
                    "type_marchandise": type_marchandise,
                    "mode_conditionnement": mode_conditionnement,
                    "operateur": operateur,
                    "unite": unite,
                    "quantite": quantite_float,
                    "observations": observations_finales,
                    "consignataire": consignataire,
                    "nombre_escales": 1,
                    "poste_changes": st.session_state.poste_changes,
                    "type_m": type_m,
                }

                horaires = {
                    "date_rade": date_rade,
                    "heure_rade": heure_rade,
                    "date_mouillage": date_mouillage,
                    "heure_mouillage": heure_mouillage,
                    "date_sortie_mouillage": date_sortie_mouillage,
                    "heure_sortie_mouillage": heure_sortie_mouillage,
                    "date_accostage": date_accostage,
                    "heure_accostage": heure_accostage,
                    "date_app_quai": date_app_quai,
                    "heure_app_quai": heure_app_quai,
                    "date_app_port": date_app_port,
                    "heure_app_port": heure_app_port,
                }

                try:
                    validate_complete_operation(operation_data, horaires)
                except ValidationError as ve:
                    st.error(str(ve))
                    st.stop()

                row = OperationRow(
                    date=str(date_rade),
                    navire=navire,
                    id_navire=numero_navire,
                    pavillon=pavillon,
                    type_navire=type_navire_final,
                    poste=poste,
                    type_operation=type_operation,
                    unite=unite,
                    quantite=quantite_float,
                    operateur=operateur,
                    type_marchandise=type_marchandise,
                    mode_conditionnement=mode_conditionnement,
                    heure_rade=str(heure_rade),
                    heure_mouillage=str(heure_mouillage),
                    heure_sortie_mouillage=str(heure_sortie_mouillage),
                    heure_accostage=str(heure_accostage),
                    heure_app_quai=str(heure_app_quai),
                    heure_app_port=str(heure_app_port),
                    date_rade=str(date_rade),
                    date_mouillage=str(date_mouillage),
                    date_sortie_mouillage=str(date_sortie_mouillage),
                    date_accostage=str(date_accostage),
                    date_app_quai=str(date_app_quai),
                    date_app_port=str(date_app_port),
                    observations=observations_finales,
                    consignataire=consignataire,
                    incidents=[],
                    poste_changes=st.session_state.poste_changes,
                    type_m_list=[type_m] if type_m else [],
                    marchandise_list=[type_marchandise] if type_marchandise else [],
                )

                db_manager.initialize_database()
                result = db_manager.insert_operation(row, temps_attente, temps_sejour)

                if result:
                    st.markdown(f"""
                    <div class="success-message">
                        ✅ <strong>Opération enregistrée avec succès !</strong><br>
                        🚢 Navire : <strong>{navire}</strong><br>
                        🏢 Opérateur : <strong>{operateur}</strong><br>
                        📍 Poste : <strong>{poste}</strong><br>
                        📋 Consignataire : <strong>{consignataire}</strong><br>
                        📦 Type M : <strong>{type_m if type_m else 'Non spécifié'}</strong><br>
                        📦 Marchandises : <strong>{type_marchandise}</strong><br>
                        📊 Quantité : <strong>{quantite_float} {unite}</strong><br>
                        ⏱️ Attente : <strong>{temps_attente} h</strong><br>
                        ⚓ Séjour à quai : <strong>{temps_sejour} h</strong><br>
                        🔄 Changements de poste : <strong>{len(st.session_state.poste_changes)}</strong>
                    </div>
                    """, unsafe_allow_html=True)
                    st.balloons()
                    st.session_state.poste_changes = []
                else:
                    st.error("❌ Erreur lors de l'enregistrement dans la base de données.")

            except Exception as e:
                st.error(f"❌ Erreur : {str(e)}")

    # ==================== TAB2: Gestion des Consignations ====================
    with tab2:
        st.subheader("⚓ Gestion des Consignations")

        col_debut1, col_debut2 = st.columns(2, gap="large")
        with col_debut1:
            date_debut_consignation = st.date_input("📅 Date début consignation", datetime.now())
        with col_debut2:
            heure_debut_consignation = st.text_input(
                "⏰ Heure début consignation",
                value="08:00",
                placeholder="HH:MM",
                key="heure_debut_consignation"
            )

        col_fin1, col_fin2 = st.columns(2, gap="large")
        with col_fin1:
            date_fin_consignation = st.date_input("📅 Date fin consignation", datetime.now())
        with col_fin2:
            heure_fin_consignation = st.text_input(
                "⏰ Heure fin consignation",
                value="17:00",
                placeholder="HH:MM",
                key="heure_fin_consignation"
            )

        poste_consignation = st.selectbox(
            "⚓ Poste concerné",
            POSTES
        )

        motif = st.selectbox(
            "📋 Motif de consignation",
            ["Brume", "Mauvais temps", "Vent fort", "Houle importante", "Maintenance du poste",
             "Travaux", "Panne équipement", "Sécurité", "Inspection", "Autre"]
        )

        if motif == "Autre":
            motif = st.text_input("Préciser le motif")

        observations_consignation = st.text_area("📝 Observations")

        try:
            date_debut_complete = datetime.combine(
                date_debut_consignation,
                datetime.strptime(heure_debut_consignation, "%H:%M").time()
            )
            date_fin_complete = datetime.combine(
                date_fin_consignation,
                datetime.strptime(heure_fin_consignation, "%H:%M").time()
            )

            diff_heures = (date_fin_complete - date_debut_complete).total_seconds() / 3600
            nombre_heures = max(1, int(diff_heures))

            if diff_heures < 24:
                st.info(f"⏱️ Durée d'indisponibilité : **{nombre_heures} heures**")
            else:
                jours = int(diff_heures // 24)
                heures_restantes = int(diff_heures % 24)
                st.info(f"⏱️ Durée d'indisponibilité : **{jours} jours et {heures_restantes} heures** ({nombre_heures} heures)")

        except:
            st.warning("⚠️ Veuillez entrer des heures valides (HH:MM)")
            nombre_heures = 1

        if st.button("💾 Enregistrer la consignation", use_container_width=True, key="save_consignation"):
            if date_fin_consignation < date_debut_consignation:
                st.error("❌ La date de fin doit être supérieure ou égale à la date de début.")
            elif date_debut_consignation == date_fin_consignation and heure_fin_consignation <= heure_debut_consignation:
                st.error("❌ L'heure de fin doit être postérieure à l'heure de début.")
            else:
                db_manager.initialize_database()
                result = db_manager.insert_consignation_poste(
                    date_debut_consignation,
                    date_fin_consignation,
                    heure_debut_consignation,
                    heure_fin_consignation,
                    poste_consignation,
                    motif,
                    nombre_heures,
                    f"Heures : {heure_debut_consignation} - {heure_fin_consignation}\n{observations_consignation}"
                )

                if result:
                    st.success(
                        f"✅ Consignation enregistrée avec succès !\n"
                        f"📅 Du {date_debut_consignation} {heure_debut_consignation} "
                        f"au {date_fin_consignation} {heure_fin_consignation}\n"
                        f"⏱️ Durée : {nombre_heures} heures"
                    )
                    st.balloons()
                else:
                    st.error("❌ Erreur lors de l'enregistrement")

    # ==================== TAB3: Gestion des incidents ====================
    with tab3:
        st.markdown('<div class="section-head"><span class="section-icon">🚨</span><span class="section-num">01</span><span class="section-title">Ajouter un incident</span></div>', unsafe_allow_html=True)
        
        col_add1, col_add2, col_add3, col_add4 = st.columns([2, 1.5, 1.5, 1])
        
        with col_add1:
            nature = st.text_input("Nature de l'incident", placeholder="Ex: Panne technique, Retard, etc.")
        with col_add2:
            date_incident = st.date_input("Date", value=datetime.now())
        with col_add3:
            lieu = st.selectbox(
                "Lieu",
                LIEUX_INCIDENTS,
                key="lieu_incident"
            )
            
            if lieu == "Autre":
                lieu_autre = st.text_input(
                    "✏️ Précisez le lieu",
                    placeholder="Ex: Nouveau lieu",
                    key="lieu_incident_autre"
                )
                
                col_btn_save, col_btn_cancel = st.columns(2)
                with col_btn_save:
                    if st.button("➕ Enregistrer ce lieu", key="save_lieu_btn"):
                        if lieu_autre and lieu_autre.strip():
                            nouveau_lieu = lieu_autre.strip()
                            if nouveau_lieu not in LIEUX_INCIDENTS:
                                st.session_state.custom_lieux.append(nouveau_lieu)
                                st.success(f"✅ Le lieu '{nouveau_lieu}' a été ajouté à la liste !")
                                st.rerun()
                            else:
                                st.warning(f"⚠️ Le lieu '{nouveau_lieu}' existe déjà dans la liste.")
                        else:
                            st.warning("⚠️ Veuillez saisir un lieu avant d'enregistrer.")
                
                with col_btn_cancel:
                    if st.button("❌ Annuler", key="cancel_lieu"):
                        st.rerun()
                
                lieu_final = lieu_autre if lieu_autre else "Autre"
            else:
                lieu_final = lieu
                
        with col_add4:
            consistance = st.text_input(
                "Consistance",
                placeholder="Ex: Critique, Mineur, etc.",
                key="consistance_incident"
            )
        
        if st.button("➕ Ajouter l'incident", use_container_width=True, type="primary"):
            if nature and nature.strip():
                new_incident = {
                    "id": len(st.session_state.incidents_list) + 1,
                    "nature": nature.strip(),
                    "date": date_incident.strftime("%d/%m/%Y"),
                    "lieu": lieu_final,
                    "consistance": consistance if consistance else "Non spécifiée",
                    "date_obj": date_incident
                }
                st.session_state.incidents_list.append(new_incident)
                st.rerun()
            else:
                st.warning("⚠️ Veuillez renseigner la nature de l'incident.")

        # ===== TABLEAU DES INCIDENTS =====
        st.markdown('<div class="section-head"><span class="section-icon">📋</span><span class="section-num">02</span><span class="section-title">Liste des incidents</span></div>', unsafe_allow_html=True)
        
        if st.session_state.incidents_list:
            st.markdown("""
            <div class="incident-row header">
                <div>Nature</div>
                <div>Date</div>
                <div>Lieu</div>
                <div>Consistance</div>
                <div style="text-align:center;">Action</div>
            </div>
            """, unsafe_allow_html=True)
            
            for incident in st.session_state.incidents_list:
                st.markdown(f"""
                <div class="incident-row">
                    <div class="incident-nature">{incident['nature']}</div>
                    <div class="incident-date">{incident['date']}</div>
                    <div class="incident-lieu">{incident['lieu']}</div>
                    <div class="incident-consistance">{incident['consistance']}</div>
                    <div style="text-align:center;">
                        <span class="btn-remove-incident">✕ Supprimer</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"🗑️ Supprimer #{incident['id']}", key=f"del_incident_{incident['id']}"):
                    st.session_state.incidents_list = [
                        inc for inc in st.session_state.incidents_list 
                        if inc["id"] != incident["id"]
                    ]
                    st.rerun()
            
            total = len(st.session_state.incidents_list)
            
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                st.metric("📊 Total incidents", total)
            with col_stat2:
                consistances = {}
                for inc in st.session_state.incidents_list:
                    c = inc.get("consistance", "Non spécifiée")
                    consistances[c] = consistances.get(c, 0) + 1
                if consistances:
                    st.metric("📈 Répartition", ", ".join([f"{k}: {v}" for k, v in consistances.items()]))
                
            if st.button("🗑️ Supprimer tous les incidents", use_container_width=True):
                st.session_state.incidents_list = []
                st.rerun()
                
        else:
            st.markdown("""
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-text">Aucun incident enregistré</div>
                <div class="empty-sub" style="color: #6B8BA3; font-size: 0.85rem;">Utilisez le formulaire ci-dessus pour ajouter un incident.</div>
            </div>
            """, unsafe_allow_html=True)

    # ==================== TAB4: Importation Excel ====================
    with tab4:
        st.markdown("""
        <div class="import-tab-header">
            <h2>📥 Importation Excel</h2>
            <p>
                Importez vos données depuis un fichier Excel. 
                Chaque module dispose de son propre importateur.
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        import_subtab1, import_subtab2 = st.tabs([
            "📊 Importer des escales",
            "⚓ Importer des consignations"
        ])
        
        with import_subtab1:
            render_escale_import()
            
        with import_subtab2:
            render_consignation_import()

    # ===================== FOOTER =====================
    st.markdown('<div class="footer-clean">ANP - Agence Nationale des Ports | Port Jorf Lasfar | Version 2.0 © 2026</div>', unsafe_allow_html=True)