import os
import base64
import streamlit as st

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo_fir.png")


@st.cache_data
def get_logo_base64() -> str:
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

# ==============================================================================
# FIR GPS ANALYTICS PLATFORM — CONFIGURAZIONE & TEMA UFFICIALE ITALRUGBY
# ==============================================================================

RUGBY_ROLES = [
    "Pilone",
    "Tallonatore",
    "Seconda Linea",
    "Terza Linea",
    "Mediano di Mischia",
    "Apertura",
    "Centro",
    "Ala",
    "Estremo",
]

DEPARTMENTS = ["Avanti", "TreQuarti"]

ROLE_TO_DEPT = {
    # Avanti
    "Pilone": "Avanti",
    "Pilone Sinistro": "Avanti",
    "Pilone Destro": "Avanti",
    "Tallonatore": "Avanti",
    "Seconda Linea": "Avanti",
    "Terza Linea": "Avanti",
    "Flanker": "Avanti",
    "Flanker Sinistro": "Avanti",
    "Flanker Destro": "Avanti",
    "Numero Otto": "Avanti",
    "Numero 8": "Avanti",
    "N.8": "Avanti",
    "Avanti": "Avanti",
    # TreQuarti
    "Mediano di Mischia": "TreQuarti",
    "Mediano di Apertura": "TreQuarti",
    "Apertura": "TreQuarti",
    "Centro": "TreQuarti",
    "Primo Centro": "TreQuarti",
    "Secondo Centro": "TreQuarti",
    "Centro/Ala": "TreQuarti",
    "Ala": "TreQuarti",
    "Ala Sinistra": "TreQuarti",
    "Ala Destra": "TreQuarti",
    "Estremo": "TreQuarti",
    "TreQuarti": "TreQuarti",
    "Trequarti": "TreQuarti",
}

JERSEY_POSITIONS_1_23 = {
    1: ("1. Pilone Sinistro", "Pilone", True, 30, 20),
    2: ("2. Tallonatore", "Tallonatore", True, 50, 20),
    3: ("3. Pilone Destro", "Pilone", True, 70, 20),
    4: ("4. Seconda Linea", "Seconda Linea", True, 40, 32),
    5: ("5. Seconda Linea", "Seconda Linea", True, 60, 32),
    6: ("6. Flanker Sinistro", "Terza Linea", True, 25, 44),
    7: ("7. Flanker Destro", "Terza Linea", True, 75, 44),
    8: ("8. Numero Otto", "Terza Linea", True, 50, 46),
    9: ("9. Mediano di Mischia", "Mediano di Mischia", True, 35, 58),
    10: ("10. Mediano di Apertura", "Apertura", True, 55, 62),
    11: ("11. Ala Sinistra", "Ala", True, 15, 75),
    12: ("12. Primo Centro", "Centro", True, 45, 74),
    13: ("13. Secondo Centro", "Centro", True, 65, 76),
    14: ("14. Ala Destra", "Ala", True, 85, 75),
    15: ("15. Estremo", "Estremo", True, 50, 88),
    16: ("16. Tallonatore Finisher", "Tallonatore", False, 10, 95),
    17: ("17. Pilone Finisher", "Pilone", False, 22, 95),
    18: ("18. Pilone Finisher", "Pilone", False, 34, 95),
    19: ("19. Seconda Linea Finisher", "Seconda Linea", False, 46, 95),
    20: ("20. Terza Linea Finisher", "Terza Linea", False, 58, 95),
    21: ("21. Mediano Finisher", "Mediano di Mischia", False, 70, 95),
    22: ("22. Apertura Finisher", "Apertura", False, 82, 95),
    23: ("23. Utility Back Finisher", "Centro", False, 94, 95),
}

# Tutte le 48 colonne D-AY del Foglio FULL FIR
FIR_COLUMNS_META = [
    # (db_col, excel_col, label, category, col_type)
    ("player_name", "D", "D: Giocatore (Name)", "Anagrafica & Seduta", "text"),
    ("sigla", "E", "E: Sigla", "Anagrafica & Seduta", "text"),
    ("session_name", "F", "F: Seduta (z)", "Anagrafica & Seduta", "text"),
    ("date", "G", "G: Data", "Anagrafica & Seduta", "date"),
    ("day_name", "H", "H: Giorno", "Anagrafica & Seduta", "text"),
    ("role", "I", "I: Ruolo", "Anagrafica & Seduta", "text"),
    ("period", "J", "J: Periodo", "Anagrafica & Seduta", "text"),
    ("profile_max_vel", "K", "K: Profile Max Vel (km/h)", "Volume & Velocità", "float"),
    ("v_max_pct", "L", "L: V max (% Max)", "Volume & Velocità", "float"),
    ("duration", "M", "M: Durata (min)", "Volume & Velocità", "float"),
    ("distance_m", "N", "N: Distanza (m)", "Volume & Velocità", "float"),
    ("m_per_min", "O", "O: m/min", "Volume & Velocità", "float"),
    ("mp_0_12", "P", "P: MP 0-12 W (m)", "Potenza Metabolica (MP)", "float"),
    ("mp_12_20", "Q", "Q: MP 12-20 W (m)", "Potenza Metabolica (MP)", "float"),
    ("mp_20_25", "R", "R: MP 20-25.5 W (m)", "Potenza Metabolica (MP)", "float"),
    ("mp_25_35", "S", "S: MP 25.5-35 W (m)", "Potenza Metabolica (MP)", "float"),
    ("mp_35_50", "T", "T: MP 35-50 W (m)", "Potenza Metabolica (MP)", "float"),
    ("mp_50_100", "U", "U: MP 50-100 W (m)", "Potenza Metabolica (MP)", "float"),
    ("ai_12_20", "V", "V: A.I. 12-20 W", "Anaerobic Index (A.I.)", "float"),
    ("ai_20_25", "W", "W: A.I. 20-25.5 W", "Anaerobic Index (A.I.)", "float"),
    ("ai_25_40", "X", "X: A.I. 25.5-40 W", "Anaerobic Index (A.I.)", "float"),
    ("ai_40_50", "Y", "Y: A.I. 40-50 W", "Anaerobic Index (A.I.)", "float"),
    ("ai_50_100", "Z", "Z: A.I. 50-100 W", "Anaerobic Index (A.I.)", "float"),
    ("v_max", "AA", "AA: V max (km/h)", "Volume & Velocità", "float"),
    ("speed_0_6", "AB", "AB: Vel 0-6 km/h (m)", "Zone di Velocità", "float"),
    ("speed_6_15", "AC", "AC: Vel 6-15 km/h (m)", "Zone di Velocità", "float"),
    ("speed_15_18", "AD", "AD: Vel 15-18 km/h (m)", "Zone di Velocità", "float"),
    ("speed_18_20", "AE", "AE: Vel 18-20 km/h (m)", "Zone di Velocità", "float"),
    ("speed_20_25", "AF", "AF: Vel 20-25 km/h (m)", "Zone di Velocità", "float"),
    ("speed_25_72", "AG", "AG: Vel 25-72 km/h (m)", "Zone di Velocità", "float"),
    ("actions_gt_6", "AH", "AH: Azioni >6 km/h", "Azioni & Accelerazioni", "float"),
    ("actions_gt_15", "AI", "AI: Azioni >15 km/h", "Azioni & Accelerazioni", "float"),
    ("actions_gt_18", "AJ", "AJ: Azioni >18 km/h", "Azioni & Accelerazioni", "float"),
    ("actions_gt_20", "AK", "AK: Azioni >20 km/h", "Azioni & Accelerazioni", "float"),
    ("actions_gt_25", "AL", "AL: Azioni >25 km/h", "Azioni & Accelerazioni", "float"),
    ("acc_volume", "AM", "AM: Volume Acc", "Azioni & Accelerazioni", "float"),
    ("acc_density_time", "AN", "AN: Densità Acc/tempo", "Azioni & Accelerazioni", "float"),
    ("acc_density_space", "AO", "AO: Densità Acc/spazio", "Azioni & Accelerazioni", "float"),
    ("contacts", "AP", "AP: Contatti", "Impatti, Salti & CoD", "float"),
    ("rhie_avg_recovery", "AQ", "AQ: RHIE Recupero Medio", "Impatti, Salti & CoD", "float"),
    ("rhie_total", "AR", "AR: RHIE Totali", "Impatti, Salti & CoD", "float"),
    ("jump_20_40", "AS", "AS: Jump 20-40 cm", "Impatti, Salti & CoD", "float"),
    ("jump_gt_40", "AT", "AT: Jump >40 cm", "Impatti, Salti & CoD", "float"),
    ("cod_right", "AU", "AU: CoD Intensi Destra", "Impatti, Salti & CoD", "float"),
    ("cod_left", "AV", "AV: CoD Intensi Sinistra", "Impatti, Salti & CoD", "float"),
    ("player_load_total", "AW", "AW: Player Load Totale", "Impatti, Salti & CoD", "float"),
    ("actions_gt_70", "AX", "AX: Azioni >70%", "Volume & Velocità", "float"),
    ("actions_gt_85", "AY", "AY: Azioni >85%", "Volume & Velocità", "float"),
]

FIR_COL_LABELS = {col: lbl for col, _, lbl, _, _ in FIR_COLUMNS_META}
FIR_NUMERIC_COLS = [col for col, _, _, _, ctype in FIR_COLUMNS_META if ctype == "float"]
FIR_TEXT_COLS = [col for col, _, _, _, ctype in FIR_COLUMNS_META if ctype in ("text", "date")]

DEFAULT_COACH_TARGETS = {
    "current_match": "ITALIA - SUD AFRICA",
    "current_competition": "Nations Championship",
    "week_type": "SETTIMANA MATCH",
    "target_hml_forwards": 0.70,
    "target_hsr_forwards": 0.40,
    "target_hml_backs": 0.75,
    "target_hsr_backs": 0.50,
    "tolerance": 0.05,
}

# ==============================================================================
# SOGLIE UFFICIALI GPEXE FIR & BENETTON TREVISO (Calibrazione GPS)
# ==============================================================================

GPEXE_SPEED_ZONES = {
    "Z1": {"min": 0.0, "max": 6.0, "label": "Passo (Walking)", "unit": "km/h"},
    "Z2": {"min": 6.0, "max": 18.0, "label": "Corsa a bassa/media intensità (Jogging/Running)", "unit": "km/h"},
    "Z3": {"min": 18.0, "max": 20.0, "label": "Alta Velocità Avanti (HSR 18-20)", "unit": "km/h"},
    "Z4": {"min": 20.0, "max": 25.0, "label": "Alta Velocità TreQuarti (HSR 20-25)", "unit": "km/h"},
    "Z5": {"min": 25.0, "max": 30.0, "label": "Sprint / Altissima Velocità (VHSR 25-30)", "unit": "km/h"},
    "Z6": {"min": 30.0, "max": 99.0, "label": "Max Sprint (>30)", "unit": "km/h"},
    "event_threshold": {"speed": 20.0, "min_duration_s": 0.3},
}

GPEXE_RELATIVE_SPEED_ZONES = {
    "Z1": {"min": 0, "max": 60, "label": "0 - 60% Vmax", "unit": "%"},
    "Z2": {"min": 60, "max": 70, "label": "60 - 70% Vmax", "unit": "%"},
    "Z3": {"min": 70, "max": 80, "label": "70 - 80% Vmax", "unit": "%"},
    "Z4": {"min": 80, "max": 85, "label": "80 - 85% Vmax", "unit": "%"},
    "Z5": {"min": 85, "max": 90, "label": "85 - 90% Vmax", "unit": "%"},
    "Z6": {"min": 90, "max": 100, "label": "> 90% Vmax", "unit": "%"},
    "event_threshold": {"pct_speed": 85, "min_duration_s": 0.0},
}

GPEXE_ACCELERATION_ZONES = {
    "Z1": {"min": 0.0, "max": 2.0, "label": "0 - 2.00 m/s²", "unit": "m/s²"},
    "Z2": {"min": 2.0, "max": 2.5, "label": "2.00 - 2.50 m/s²", "unit": "m/s²"},
    "Z3": {"min": 2.5, "max": 3.0, "label": "2.50 - 3.00 m/s²", "unit": "m/s²"},
    "Z4": {"min": 3.0, "max": 99.0, "label": "> 3.00 m/s²", "unit": "m/s²"},
    "event_threshold": {"acceleration": 2.50, "min_duration_s": 0.5},
}

GPEXE_DECELERATION_ZONES = {
    "Z1": {"min": -2.0, "max": 0.0, "label": "0 a -2.00 m/s²", "unit": "m/s²"},
    "Z2": {"min": -2.5, "max": -2.0, "label": "-2.00 a -2.50 m/s²", "unit": "m/s²"},
    "Z3": {"min": -3.0, "max": -2.5, "label": "-2.50 a -3.00 m/s²", "unit": "m/s²"},
    "Z4": {"min": -99.0, "max": -3.0, "label": "< -3.00 m/s²", "unit": "m/s²"},
    "event_threshold": {"deceleration": -2.50, "min_duration_s": 0.5},
}

GPEXE_POWER_ZONES = {
    "Z1": {"min": 0.0, "max": 5.0, "label": "0 - 5.00 W/kg", "unit": "W/kg"},
    "Z2": {"min": 5.0, "max": 25.5, "label": "5.00 - 25.50 W/kg", "unit": "W/kg"},
    "Z3": {"min": 25.5, "max": 40.0, "label": "25.50 - 40.00 W/kg (HML Z3)", "unit": "W/kg"},
    "Z4": {"min": 40.0, "max": 50.0, "label": "40.00 - 50.00 W/kg (HML Z4)", "unit": "W/kg"},
    "Z5": {"min": 50.0, "max": 999.0, "label": "> 50.00 W/kg (VHML Z5)", "unit": "W/kg"},
    "hml_threshold": 25.5,
    "vhml_threshold": 50.0,
}

GPEXE_IMU_ZONES = {
    "jumps": {
        "Z1": {"min": 0.0, "max": 0.25, "label": "0 - 0.25 m", "unit": "m"},
        "Z2": {"min": 0.25, "max": 0.50, "label": "0.25 - 0.50 m", "unit": "m"},
        "Z3": {"min": 0.50, "max": 99.0, "label": "> 0.50 m", "unit": "m"},
    },
    "impacts": {
        "Z1": {"min": 0.0, "max": 75.0, "label": "0 - 75.00 m/s²", "unit": "m/s²"},
        "Z2": {"min": 75.0, "max": 90.0, "label": "75.00 - 90.00 m/s²", "unit": "m/s²"},
        "Z3": {"min": 90.0, "max": 999.0, "label": "> 90.00 m/s²", "unit": "m/s²"},
    },
}

GPEXE_MATCH_METRICS_INFO = {
    "PoS": "Peak of Speed (Velocità Massima Vmax in km/h)",
    "DT": "Distanza Totale percorsa (m)",
    "DC": "Distanza Corsa (m percorsi a velocità > 6.0 km/h, Zone Z2-Z6)",
    "Hml": "High Metabolic Load (> 25.5 W/kg, Zone Z3 + Z4 + Z5)",
    "VHml": "Very High Metabolic Load (> 50.0 W/kg, Zona Z5)",
    "HSR": "High Speed Running (> 18 km/h per Avanti, > 20 km/h per TreQuarti)",
}


def get_theme() -> dict:
    return {
        "bg": "#F8FAFC",
        "card": "#FFFFFF",
        "card_hover": "#F1F5F9",
        "border": "#E2E8F0",
        "text": "#0F172A",
        "subtext": "#475569",
        "navy": "#002B49",
        "dark": "#031926",
        "accent": "#0066B2",
        "accent2": "#0284C7",
        "gold": "#D4AF37",
        "green": "#10B981",
        "amber": "#F59E0B",
        "red": "#EF4444",
        "purple": "#8B5CF6",
    }


def apply_custom_css(t: dict):
    st.markdown(
        f"""
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');
            html, body, [class*="css"] {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                color: {t['text']};
            }}
            .stApp {{
                background-color: {t['bg']};
            }}
            section[data-testid="stSidebar"] {{
                background: linear-gradient(180deg, #031926 0%, #002B49 100%) !important;
                border-right: 1px solid rgba(212, 175, 55, 0.25);
            }}
            [data-testid="stSidebar"] .stMarkdown,
            [data-testid="stSidebar"] .stCaption,
            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] span:not(button span) {{
                color: #F8FAFC;
            }}
            /* Pulsanti Navigazione Laterale - Stato Non Selezionato (Secondary) */
            section[data-testid="stSidebar"] .stButton > button,
            section[data-testid="stSidebar"] button,
            section[data-testid="stSidebar"] button[kind="secondary"],
            section[data-testid="stSidebar"] [data-testid*="Button"],
            section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"],
            section[data-testid="stSidebar"] [data-testid="baseButton-secondary"] {{
                background: #0E3558 !important;
                background-color: #0E3558 !important;
                color: #FFFFFF !important;
                border: 1px solid rgba(147, 197, 253, 0.40) !important;
                border-radius: 8px !important;
                font-weight: 600 !important;
                font-size: 0.88rem !important;
                padding: 0.55rem 0.85rem !important;
                transition: all 0.18s ease !important;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3) !important;
            }}
            section[data-testid="stSidebar"] .stButton > button *,
            section[data-testid="stSidebar"] button * {{
                color: #FFFFFF !important;
                font-weight: 600 !important;
            }}
            section[data-testid="stSidebar"] .stButton > button:hover,
            section[data-testid="stSidebar"] button:hover {{
                background: #0066B2 !important;
                background-color: #0066B2 !important;
                border-color: #38BDF8 !important;
                color: #FFFFFF !important;
                box-shadow: 0 4px 10px rgba(0, 102, 178, 0.35) !important;
            }}
            /* Pulsante Navigazione Laterale - Pagina Attiva (Primary) */
            section[data-testid="stSidebar"] button[kind="primary"],
            section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"],
            section[data-testid="stSidebar"] [data-testid="baseButton-primary"] {{
                background: linear-gradient(90deg, #0066B2 0%, #0284C7 100%) !important;
                background-color: #0066B2 !important;
                color: #FFFFFF !important;
                border: 1.5px solid #D4AF37 !important;
                border-left: 6px solid #D4AF37 !important;
                font-weight: 800 !important;
                box-shadow: 0 4px 14px rgba(0, 102, 178, 0.55) !important;
            }}
            section[data-testid="stSidebar"] button[kind="primary"] * {{
                color: #FFFFFF !important;
                font-weight: 800 !important;
            }}
            section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div {{
                background-color: rgba(255,255,255,0.08) !important;
                border-color: rgba(255,255,255,0.2) !important;
                color: #FFFFFF !important;
            }}
            /* Menu a Tendina e Popover - Larghezza Automatica e Testo Completo (No Troncamento) */
            div[data-baseweb="select"] {{
                min-width: 220px !important;
            }}
            div[data-baseweb="select"] span,
            div[data-baseweb="select"] div {{
                white-space: nowrap !important;
            }}
            div[data-baseweb="popover"],
            div[data-baseweb="menu"],
            ul[role="listbox"],
            [data-testid="stSelectboxVirtualDropdown"] {{
                min-width: 360px !important;
                max-width: 650px !important;
                width: max-content !important;
                box-shadow: 0 8px 24px rgba(15, 23, 42, 0.20) !important;
                border-radius: 8px !important;
                z-index: 999999 !important;
            }}
            div[data-baseweb="popover"] ul li,
            div[data-baseweb="popover"] div[role="option"],
            ul[role="listbox"] li,
            ul[role="listbox"] div[role="option"],
            [data-testid="stSelectboxVirtualDropdown"] li {{
                white-space: nowrap !important;
                font-size: 0.84rem !important;
                padding: 6px 12px !important;
                overflow: visible !important;
                text-overflow: clip !important;
            }}
            div[data-baseweb="popover"] [role="option"] > div,
            div[data-baseweb="popover"] [role="option"] span,
            ul[role="listbox"] span {{
                overflow: visible !important;
                text-overflow: clip !important;
                white-space: nowrap !important;
            }}
            div[data-baseweb="select"] div {{
                font-size: 0.84rem !important;
            }}
            .fir-kpi-card {{
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-left: 4px solid #0066B2;
                border-radius: 12px;
                padding: 16px 18px;
                box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
            }}
            .fir-kpi-label {{
                font-size: 0.72rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: #64748B;
                margin-bottom: 4px;
            }}
            .fir-kpi-val {{
                font-size: 1.55rem;
                font-weight: 800;
                color: #0F172A;
                font-family: 'JetBrains Mono', monospace;
            }}
            .fir-kpi-sub {{
                font-size: 0.75rem;
                color: #64748B;
                margin-top: 2px;
            }}
            .fir-section-card {{
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
                padding: 20px;
                margin-bottom: 16px;
                box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
            }}
            .fir-badge {{
                display: inline-block;
                padding: 3px 9px;
                border-radius: 999px;
                font-size: 0.72rem;
                font-weight: 700;
                text-transform: uppercase;
            }}

            /* ========================================================= */
            /* STILE GLOBALE SELETTORI, BOTTONI E INPUT (PREMIUM FIR)    */
            /* ========================================================= */
            /* Bottoni Primari Generali (Area Principale) */
            section.main .stButton > button[kind="primary"],
            section.main button[data-testid="stBaseButton-primary"],
            section.main button[data-testid="baseButton-primary"] {{
                background: linear-gradient(135deg, #002B49 0%, #0066B2 100%) !important;
                background-color: #0066B2 !important;
                color: #FFFFFF !important;
                border: 1.5px solid #D4AF37 !important;
                border-radius: 9px !important;
                font-weight: 700 !important;
                font-size: 0.86rem !important;
                padding: 0.50rem 1.0rem !important;
                box-shadow: 0 3px 10px rgba(0, 43, 73, 0.25) !important;
                transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }}
            section.main .stButton > button[kind="primary"]:hover,
            section.main button[data-testid="stBaseButton-primary"]:hover {{
                background: linear-gradient(135deg, #001B30 0%, #00528F 100%) !important;
                color: #FFFFFF !important;
                transform: translateY(-1.5px) !important;
                box-shadow: 0 6px 16px rgba(0, 102, 178, 0.35) !important;
            }}
            section.main .stButton > button[kind="primary"] *,
            section.main button[data-testid="stBaseButton-primary"] * {{
                color: #FFFFFF !important;
                font-weight: 700 !important;
            }}

            /* Bottoni Secondari Generali (Area Principale, escluso dock subnav) */
            section.main .stButton:not(div[class*="st-key-subnav_dock_"] .stButton) > button[kind="secondary"],
            section.main .stButton:not(div[class*="st-key-subnav_dock_"] .stButton) > button:not([kind="primary"]) {{
                background: #FFFFFF !important;
                background-color: #FFFFFF !important;
                color: #0F172A !important;
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 9px !important;
                font-weight: 600 !important;
                font-size: 0.85rem !important;
                padding: 0.45rem 0.90rem !important;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05) !important;
                transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }}
            section.main .stButton:not(div[class*="st-key-subnav_dock_"] .stButton) > button[kind="secondary"]:hover,
            section.main .stButton:not(div[class*="st-key-subnav_dock_"] .stButton) > button:not([kind="primary"]):hover {{
                background: #F0F9FF !important;
                border-color: #0066B2 !important;
                color: #0066B2 !important;
                transform: translateY(-1.5px) !important;
                box-shadow: 0 4px 10px rgba(0, 102, 178, 0.15) !important;
            }}

            /* Bottoni Download PDF / File */
            div.stDownloadButton > button {{
                background: linear-gradient(135deg, #065F46 0%, #059669 100%) !important;
                background-color: #059669 !important;
                color: #FFFFFF !important;
                border: 1.5px solid #34D399 !important;
                border-radius: 9px !important;
                font-weight: 800 !important;
                font-size: 0.86rem !important;
                padding: 0.50rem 1.05rem !important;
                box-shadow: 0 3px 10px rgba(5, 150, 105, 0.28) !important;
                transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }}
            div.stDownloadButton > button:hover {{
                background: linear-gradient(135deg, #044E39 0%, #047857 100%) !important;
                transform: translateY(-1.5px) !important;
                box-shadow: 0 6px 16px rgba(5, 150, 105, 0.40) !important;
            }}
            div.stDownloadButton > button * {{
                color: #FFFFFF !important;
                font-weight: 800 !important;
            }}

            /* Selettori a Tendina (Selectbox nell'area principale) */
            section.main div[data-baseweb="select"] > div {{
                background: #FFFFFF !important;
                background-color: #FFFFFF !important;
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 9px !important;
                font-weight: 600 !important;
                color: #0F172A !important;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
                transition: all 0.18s ease !important;
            }}
            section.main div[data-baseweb="select"] > div:hover {{
                border-color: #0066B2 !important;
            }}
            section.main div[data-baseweb="select"] > div:focus-within {{
                border-color: #0066B2 !important;
                box-shadow: 0 0 0 3px rgba(0, 102, 178, 0.14) !important;
            }}

            /* Campi di Testo & Numerici */
            section.main div[data-baseweb="input"] > div {{
                background: #FFFFFF !important;
                background-color: #FFFFFF !important;
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 9px !important;
                font-weight: 600 !important;
                color: #0F172A !important;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04) !important;
                transition: all 0.18s ease !important;
            }}
            section.main div[data-baseweb="input"] > div:focus-within {{
                border-color: #0066B2 !important;
                box-shadow: 0 0 0 3px rgba(0, 102, 178, 0.14) !important;
            }}

            /* Expanders (Area Principale) */
            section.main div[data-testid="stExpander"] {{
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 12px !important;
                background: #FFFFFF !important;
                box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04) !important;
                overflow: hidden !important;
            }}
            section.main div[data-testid="stExpander"] summary {{
                background: #F8FAFC !important;
                font-weight: 700 !important;
                color: #0F172A !important;
                border-radius: 10px !important;
                padding: 10px 14px !important;
            }}
            section.main div[data-testid="stExpander"] summary:hover {{
                color: #0066B2 !important;
                background: #F0F9FF !important;
            }}

            /* Expanders & Form nella Sidebar (Tema Scuro FIR Coordinato e Leggibile) */
            section[data-testid="stSidebar"] div[data-testid="stExpander"] {{
                border: 1px solid rgba(147, 197, 253, 0.40) !important;
                border-radius: 10px !important;
                background: #0A2742 !important;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.30) !important;
                overflow: hidden !important;
            }}
            section[data-testid="stSidebar"] div[data-testid="stExpander"] summary {{
                background: #0E3558 !important;
                font-weight: 700 !important;
                color: #FFFFFF !important;
                border-radius: 8px !important;
                padding: 10px 14px !important;
            }}
            section[data-testid="stSidebar"] div[data-testid="stExpander"] summary *,
            section[data-testid="stSidebar"] div[data-testid="stExpander"] summary span,
            section[data-testid="stSidebar"] div[data-testid="stExpander"] summary p {{
                color: #FFFFFF !important;
                font-weight: 700 !important;
            }}
            section[data-testid="stSidebar"] div[data-testid="stExpander"] summary:hover {{
                background: #0066B2 !important;
                color: #FFFFFF !important;
            }}
            section[data-testid="stSidebar"] [data-testid="stForm"] {{
                background: rgba(14, 53, 88, 0.55) !important;
                border: 1px solid rgba(147, 197, 253, 0.25) !important;
                border-radius: 8px !important;
                padding: 10px !important;
            }}
            section[data-testid="stSidebar"] div[data-testid="stExpander"] label,
            section[data-testid="stSidebar"] div[data-testid="stExpander"] label p,
            section[data-testid="stSidebar"] [data-testid="stForm"] label,
            section[data-testid="stSidebar"] [data-testid="stForm"] label p {{
                color: #E2E8F0 !important;
                font-weight: 600 !important;
                font-size: 0.80rem !important;
            }}
            section[data-testid="stSidebar"] div[data-baseweb="input"] > div {{
                background-color: #FFFFFF !important;
                border: 1px solid #93C5FD !important;
                border-radius: 7px !important;
            }}
            section[data-testid="stSidebar"] div[data-baseweb="input"] input {{
                color: #0F172A !important;
                -webkit-text-fill-color: #0F172A !important;
                font-weight: 600 !important;
            }}

            /* ========================================================= */
            /* STILE DOCK SUB-NAVIGAZIONE SOTTOPAGINE (PREMIUM FIR LOOK)  */
            /* ========================================================= */
            div[class*="st-key-subnav_dock_"] {{
                background: linear-gradient(180deg, #F8FAFC 0%, #EEF2F6 100%) !important;
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 14px !important;
                padding: 10px 12px 6px 12px !important;
                margin-bottom: 16px !important;
                box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05) !important;
            }}

            /* Pulsanti Sottopagina Inattivi (Secondary) */
            div[class*="st-key-subnav_dock_"] button,
            div[class*="st-key-navbtn_"] button,
            div[class*="st-key-subnav_dock_"] [data-testid="stBaseButton-secondary"],
            div[class*="st-key-navbtn_"] [data-testid="stBaseButton-secondary"] {{
                background: #FFFFFF !important;
                background-color: #FFFFFF !important;
                color: #0F172A !important;
                border: 1.5px solid #CBD5E1 !important;
                border-radius: 10px !important;
                font-size: 0.83rem !important;
                font-weight: 700 !important;
                padding: 0.50rem 0.65rem !important;
                min-height: 48px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                text-align: center !important;
                line-height: 1.25 !important;
                white-space: normal !important;
                word-break: keep-all !important;
                overflow-wrap: normal !important;
                hyphens: none !important;
                -webkit-hyphens: none !important;
                text-wrap: balance !important;
                transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
                box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06) !important;
            }}

            div[class*="st-key-subnav_dock_"] button:hover,
            div[class*="st-key-navbtn_"] button:hover {{
                background: #F0F9FF !important;
                background-color: #F0F9FF !important;
                border-color: #0284C7 !important;
                color: #0066B2 !important;
                transform: translateY(-1.5px) !important;
                box-shadow: 0 4px 12px rgba(2, 132, 199, 0.18) !important;
            }}

            div[class*="st-key-subnav_dock_"] button *,
            div[class*="st-key-navbtn_"] button * {{
                color: #0F172A !important;
                font-weight: 700 !important;
                word-break: keep-all !important;
                overflow-wrap: normal !important;
                hyphens: none !important;
                -webkit-hyphens: none !important;
            }}

            div[class*="st-key-subnav_dock_"] button:hover *,
            div[class*="st-key-navbtn_"] button:hover * {{
                color: #0066B2 !important;
            }}

            /* Pulsante Sottopagina Attivo (Primary - Molto Evidente FIR Navy & Gold) */
            div[class*="st-key-subnav_dock_"] button[kind="primary"],
            div[class*="st-key-navbtn_"] button[kind="primary"],
            div[class*="st-key-subnav_dock_"] [data-testid="stBaseButton-primary"],
            div[class*="st-key-navbtn_"] [data-testid="stBaseButton-primary"] {{
                background: linear-gradient(135deg, #002B49 0%, #0066B2 100%) !important;
                background-color: #0066B2 !important;
                color: #FFFFFF !important;
                border: 2px solid #D4AF37 !important;
                border-radius: 10px !important;
                font-size: 0.85rem !important;
                font-weight: 800 !important;
                padding: 0.50rem 0.65rem !important;
                min-height: 48px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                text-align: center !important;
                line-height: 1.25 !important;
                white-space: normal !important;
                word-break: keep-all !important;
                overflow-wrap: normal !important;
                hyphens: none !important;
                -webkit-hyphens: none !important;
                text-wrap: balance !important;
                box-shadow: 0 4px 14px rgba(0, 102, 178, 0.45), 0 0 0 1px #D4AF37 !important;
                transform: translateY(-1px) !important;
            }}

            div[class*="st-key-subnav_dock_"] button[kind="primary"] *,
            div[class*="st-key-navbtn_"] button[kind="primary"] *,
            div[class*="st-key-subnav_dock_"] [data-testid="stBaseButton-primary"] *,
            div[class*="st-key-navbtn_"] [data-testid="stBaseButton-primary"] * {{
                color: #FFFFFF !important;
                font-weight: 800 !important;
                word-break: keep-all !important;
                overflow-wrap: normal !important;
            }}
            /* Nasconde completamente l'iframe tecnico di scroll-to-top */
            iframe[height="0"] {{
                display: none !important;
                height: 0px !important;
                width: 0px !important;
                margin: 0 !important;
                padding: 0 !important;
                border: none !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _trigger_scroll_to_top_if_needed():
    """
    Porta automaticamente la schermata nella parte più alta ad ogni cambio pagina, sottopagina o login.
    IMPORTANTE: il componente viene sempre renderizzato nella stessa posizione dell'albero Streamlit
    (controllando il contatore lato JS su window.parent) così da NON spostare mai gli indici dei widget
    o degli st.expander nei rerun successivi.
    """
    cur_cnt = int(st.session_state.get("_scroll_top_counter", 0))
    import streamlit.components.v1 as components
    components.html(
        f"""
        <script>
        (function() {{
            const targetCnt = {cur_cnt};
            try {{
                if (window.parent._firLastScrollCnt === targetCnt) {{
                    return;
                }}
                window.parent._firLastScrollCnt = targetCnt;
                function scrollToTopFIR() {{
                    try {{
                        const doc = window.parent.document;
                        const selectors = [
                            'section.main',
                            '[data-testid="stMain"]',
                            '[data-testid="stAppViewContainer"]',
                            '[data-testid="stApp"]',
                            '.main'
                        ];
                        selectors.forEach(sel => {{
                            const el = doc.querySelector(sel);
                            if (el) {{
                                el.scrollTo({{ top: 0, left: 0, behavior: 'instant' }});
                                el.scrollTop = 0;
                            }}
                        }});
                        if (doc.documentElement) doc.documentElement.scrollTop = 0;
                        if (doc.body) doc.body.scrollTop = 0;
                        window.parent.scrollTo(0, 0);
                    }} catch (e) {{}}
                }}
                scrollToTopFIR();
                setTimeout(scrollToTopFIR, 40);
                setTimeout(scrollToTopFIR, 120);
            }} catch (err) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def render_page_header(title: str, subtitle: str, icon: str = "bi-shield-shaded"):
    _trigger_scroll_to_top_if_needed()
    b64_logo = get_logo_base64()
    if b64_logo:
        badge_html = f'<img src="data:image/png;base64,{b64_logo}" style="height:54px; width:auto; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.4));" alt="FIR Logo">'
    else:
        badge_html = f"""
        <div style="width: 46px; height: 46px; border-radius: 12px; background: rgba(212,175,55,0.16);
                    border: 1.5px solid #D4AF37; display: flex; align-items: center; justify-content: center;
                    color: #D4AF37; font-size: 1.35rem;">
            <i class="bi {icon}"></i>
        </div>
        """
    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #031926 0%, #002B49 65%, #004B87 100%);
                    border-radius: 14px; padding: 20px 24px; margin-bottom: 18px;
                    border-left: 5px solid #D4AF37; box-shadow: 0 6px 18px rgba(0,43,73,0.15);
                    display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 16px;">
                {badge_html}
                <div>
                    <div style="font-size: 0.70rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; color: #D4AF37;">
                        FEDERAZIONE ITALIANA RUGBY • NAZIONALE MAGGIORE
                    </div>
                    <h1 style="margin: 2px 0 0 0; font-size: 1.45rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.01em;">
                        {title}
                    </h1>
                    <div style="font-size: 0.82rem; color: #CBD5E1; margin-top: 2px;">
                        {subtitle}
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tab_navigation(page_key: str, tabs: list) -> str:
    """
    Renders a persistent single-click horizontal sub-navigation dock.
    tabs: list of tuples (tab_id, tab_label, bootstrap_icon)
    Returns active tab_id.
    """
    state_key = f"active_subtab_{page_key}"
    valid_ids = [t[0] for t in tabs]
    if state_key not in st.session_state or st.session_state[state_key] not in valid_ids:
        st.session_state[state_key] = valid_ids[0]

    # Smart split: if more than 5 tabs, distribute across 2 balanced rows
    if len(tabs) > 5:
        mid = (len(tabs) + 1) // 2
        tab_rows = [tabs[:mid], tabs[mid:]]
    else:
        tab_rows = [tabs]

    with st.container(key=f"subnav_dock_{page_key}"):
        for r_idx, row_tabs in enumerate(tab_rows):
            if r_idx > 0:
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            cols = st.columns(len(row_tabs))
            for idx, (tid, tlabel, ticon) in enumerate(row_tabs):
                is_active = st.session_state[state_key] == tid
                with cols[idx]:
                    if st.button(
                        tlabel,
                        key=f"navbtn_{page_key}_{tid}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state[state_key] = tid
                        st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
                        st.rerun()

    return st.session_state[state_key]


def render_navigation_cards(page_key: str, cards: list) -> str:
    """
    Rende una griglia elegante di CARD interattive per accedere alle varie analisi di una sezione.
    cards: lista di dizionari o tuple:
      - dict: {"id": str, "title": str, "desc": str, "icon": str}
      - tuple: (id, title, desc, icon)
    Restituisce l'id della card attiva (memorizzato in session_state).
    """
    state_key = f"active_subtab_{page_key}"
    valid_ids = [c["id"] if isinstance(c, dict) else c[0] for c in cards]
    if state_key not in st.session_state or st.session_state[state_key] not in valid_ids:
        st.session_state[state_key] = valid_ids[0]

    norm_cards = []
    for c in cards:
        if isinstance(c, dict):
            norm_cards.append(c)
        else:
            cid = c[0]
            ctitle = c[1]
            cdesc = c[2] if len(c) > 2 else ""
            cicon = c[3] if len(c) > 3 else "bi-grid"
            norm_cards.append({"id": cid, "title": ctitle, "desc": cdesc, "icon": cicon})

    n = len(norm_cards)
    if n <= 3:
        per_row = n
    elif n == 4:
        per_row = 4
    elif n in (5, 6):
        per_row = 3
    elif n in (7, 8):
        per_row = 4
    elif n == 9:
        per_row = 3
    else:
        per_row = 4

    rows = [norm_cards[i:i + per_row] for i in range(0, n, per_row)]

    st.markdown(
        """
        <style>
        .fir-navcard-box {
            border-radius: 12px;
            padding: 10px 12px;
            margin-bottom: 6px;
            min-height: 86px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.2s ease;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        for r_idx, row in enumerate(rows):
            cols = st.columns(len(row))
            for c_idx, item in enumerate(row):
                cid = item["id"]
                title = item["title"]
                desc = item.get("desc", "")
                icon = item.get("icon", "bi-graph-up")
                is_active = (st.session_state[state_key] == cid)

                with cols[c_idx]:
                    card_border = "#D4AF37" if is_active else "#CBD5E1"
                    card_bg = "linear-gradient(135deg, #002B49 0%, #004B87 100%)" if is_active else "#FFFFFF"
                    card_shadow = "0 6px 18px rgba(0,43,73,0.22)" if is_active else "0 2px 6px rgba(15,23,42,0.04)"
                    txt_color = "#FFFFFF" if is_active else "#0F172A"
                    desc_color = "#93C5FD" if is_active else "#64748B"
                    badge_bg = "rgba(212,175,55,0.25)" if is_active else "#F1F5F9"
                    badge_border = "#D4AF37" if is_active else "#E2E8F0"
                    badge_txt = "#D4AF37" if is_active else "#0066B2"
                    status_pill = (
                        '<span style="background:#D4AF37; color:#031926; font-size:0.62rem; font-weight:800; padding:2px 8px; border-radius:99px; text-transform:uppercase; letter-spacing:0.04em;">ATTIVA</span>'
                        if is_active
                        else '<span style="background:#F1F5F9; color:#64748B; font-size:0.62rem; font-weight:700; padding:2px 8px; border-radius:99px; text-transform:uppercase;">SELEZIONA</span>'
                    )

                    card_html = f"""
                    <div class="fir-navcard-box" style="background:{card_bg}; border:2px solid {card_border}; box-shadow:{card_shadow};">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
                            <div style="display:flex; align-items:center; gap:8px; min-width:0;">
                                <div style="width:28px; height:28px; border-radius:8px; background:{badge_bg}; border:1px solid {badge_border}; display:flex; align-items:center; justify-content:center; color:{badge_txt}; font-size:0.95rem; flex-shrink:0;">
                                    <i class="bi {icon}"></i>
                                </div>
                                <div style="font-weight:800; font-size:0.83rem; color:{txt_color}; line-height:1.2; word-break:keep-all;" title="{title}">
                                    {title}
                                </div>
                            </div>
                            <div style="flex-shrink:0;">{status_pill}</div>
                        </div>
                        <div style="font-size:0.71rem; color:{desc_color}; margin-top:5px; line-height:1.2; font-weight:500;">
                            {desc}
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                    btn_label = f"✓ {title}" if is_active else f"Apri {title}"
                    if st.button(
                        btn_label,
                        key=f"cardbtn_{page_key}_{cid}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary",
                    ):
                        st.session_state[state_key] = cid
                        st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
                        st.rerun()
            if r_idx < len(rows) - 1:
                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    return st.session_state[state_key]


def _build_meta_cells_html(meta_items: list) -> str:
    cells = []
    for lbl, val in meta_items:
        cells.append(
            f"<div style='display:flex; flex-direction:column; padding-right:16px; border-right:1px solid #E2E8F0;'>"
            f"<span style='font-size:0.65rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.05em;'>{lbl}</span>"
            f"<span style='font-size:0.84rem; font-weight:800; color:#0F172A;'>{val}</span>"
            f"</div>"
        )
    return "".join(cells)


def render_action_bar(meta_items: list, pdf_options: dict = None, pdf_key: str = None, generate_fn=None, filename_fn=None):
    """Unified Enterprise Action Bar combining context metadata and inline PDF export (same pattern as webapp_tennis_gps)."""
    with st.container(border=True):
        if pdf_options and pdf_key and generate_fn and filename_fn:
            col_info, col_sub_pdf, col_print = st.columns([3.2, 1.8, 1.3], vertical_alignment="center")
            with col_info:
                inner_html = _build_meta_cells_html(meta_items)
                st.markdown(
                    f"<div style='display:flex; align-items:center; gap:16px; flex-wrap:wrap; padding:2px 4px;'>{inner_html}</div>",
                    unsafe_allow_html=True,
                )
            with col_sub_pdf:
                st.markdown(
                    "<div style='font-size:10px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:3px;'>Sezione Report PDF</div>",
                    unsafe_allow_html=True,
                )
                scelta_sub = st.selectbox(
                    "Sottoarea PDF",
                    list(pdf_options.keys()),
                    key=f"sub_{pdf_key}",
                    label_visibility="collapsed",
                )
                codice_sub = pdf_options[scelta_sub]
            with col_print:
                st.markdown(
                    "<div style='font-size:10px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.6px; margin-bottom:3px;'>Esportazione</div>",
                    unsafe_allow_html=True,
                )
                btn_slot = st.empty()
                if btn_slot.button("Genera Report PDF", key=f"btn_{pdf_key}", use_container_width=True):
                    with st.spinner("Elaborazione PDF FIR..."):
                        pdf_bytes = generate_fn(codice_sub)
                    btn_slot.download_button(
                        label="Scarica PDF Pronto",
                        data=pdf_bytes,
                        file_name=filename_fn(codice_sub),
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary",
                        key=f"dl_{pdf_key}",
                    )
        else:
            inner_html = _build_meta_cells_html(meta_items)
            st.markdown(
                f"<div style='display:flex; align-items:center; gap:16px; flex-wrap:wrap; padding:4px 6px;'>{inner_html}</div>",
                unsafe_allow_html=True,
            )

