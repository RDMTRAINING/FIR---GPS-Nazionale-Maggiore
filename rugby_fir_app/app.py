import os
import sys
import importlib

# Assicura priorità assoluta ai moduli di rugby_fir_app
_app_dir = os.path.dirname(os.path.abspath(__file__))
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
elif sys.path[0] != _app_dir:
    sys.path.remove(_app_dir)
    sys.path.insert(0, _app_dir)

import config
if not hasattr(config, "render_navigation_cards"):
    importlib.reload(config)

import streamlit as st
from config import get_theme, apply_custom_css, LOGO_PATH, get_logo_base64
import utils
importlib.reload(utils)
import auth
import views.home
importlib.reload(views.home)
import views.pannello_controllo
import views.storico_gps
import views.oval_match
import views.import_dati
importlib.reload(views.import_dati)
import views.report_6weeks
import views.report_comparazione
import views.admin_utenti
import views.dashboard_home
import views.analisi_individuale
import views.palestra_gymaware
importlib.reload(views.palestra_gymaware)
import views.cambio_password
import global_state
import views.login

st.set_page_config(
    page_title="FIR GPS Analytics Platform | Italrugby",
    page_icon=LOGO_PATH if os.path.exists(LOGO_PATH) else "🏉",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    t = get_theme()
    apply_custom_css(t)

    # Inizializza archivio utenti
    auth.init_auth()

    # Controllo Autenticazione: se non loggato mostra la pagina di login
    if not st.session_state.get("authenticated"):
        views.login.render_login_page(t)
        return

    cur_user = st.session_state.get("current_user", {})
    user_role = st.session_state.get("user_role", "viewer")
    user_fullname = cur_user.get("full_name", "Utente FIR")
    username = cur_user.get("username", "utente")

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = "dashboard_home"

    counts = utils.get_history_team_counts()
    gym_stats = utils.get_gymaware_summary_stats()
    players_df = utils.get_players_df()
    camps_df = utils.get_camps_df()
    matches_df = utils.get_matches_df()
    oval_df = utils.get_oval_matches_df()
    b64_logo = get_logo_base64()

    with st.sidebar:
        logo_img_html = (
            f'<img src="data:image/png;base64,{b64_logo}" style="height:48px; width:auto; filter: drop-shadow(0 2px 5px rgba(0,0,0,0.45));" alt="FIR Logo">'
            if b64_logo
            else '<div style="width:42px; height:42px; border-radius:50%; background:#0066B2; border:2px solid #D4AF37; display:flex; align-items:center; justify-content:center; font-weight:800;">FIR</div>'
        )
        st.markdown(
            f"""
            <div style="padding: 10px 6px 14px 6px; border-bottom: 1px solid rgba(212,175,55,0.28); margin-bottom: 14px;">
                <div style="display:flex; align-items:center; gap:12px;">
                    {logo_img_html}
                    <div>
                        <div style="font-size:1.05rem; font-weight:800; letter-spacing:-0.01em; color:#FFFFFF;">
                            FIR <span style="color:#D4AF37;">GPS PLATFORM</span>
                        </div>
                        <div style="font-size:0.72rem; color:#93C5FD; font-weight:600;">
                            Nazionale Maggiore • Italrugby
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Badge Utente Autenticato & Ruolo
        role_badge = (
            '<span style="background:linear-gradient(90deg, #D4AF37 0%, #F59E0B 100%); color:#031926; font-size:0.65rem; font-weight:800; padding:2px 7px; border-radius:4px; letter-spacing:0.04em;">ADMIN</span>'
            if user_role == "admin"
            else '<span style="background:#0284C7; color:#FFFFFF; font-size:0.65rem; font-weight:800; padding:2px 7px; border-radius:4px; letter-spacing:0.04em;">VISUALIZZATORE</span>'
        )

        st.markdown(
            f"""
            <div style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.15); border-radius:8px; padding:8px 12px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:0.82rem; font-weight:700; color:#FFFFFF; line-height:1.2;">
                        👤 {user_fullname}
                    </div>
                    <div style="font-size:0.68rem; color:#94A3B8;">
                        @{username}
                    </div>
                </div>
                <div>
                    {role_badge}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Pannello Selezione Globale Fisso (rimane visibile in tutte le analisi)
        global_state.render_sidebar_global_panel()

        st.markdown(
            "<div style='font-size:0.70rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:#D4AF37; margin-bottom:8px;'>Navigazione Principale</div>",
            unsafe_allow_html=True,
        )

        FIRST_SUBTABS = {
            "dashboard_home": "home",
            "analisi_sessione_giornata": "story",
            "analisi_settimana": "report_settimana",
            "medie_confronti": "medie_tipologie_fir",
            "analisi_individuale": "gps_atleta",
            "palestra_gymaware": "squadra_ranking",
            "pannello_controllo": "roster",
            "storico_dati": "nazionale",
            "import_dati": "csv_import",
            "cambio_password": "cambio_password",
        }

        # Menu Principale (con nuova sezione Palestra & GymAware dopo Analisi Individuale)
        if user_role == "admin":
            nav_items = [
                ("dashboard_home", "1. 🏠 Home"),
                ("analisi_sessione_giornata", "2. ⏱️ Analisi GPS sessione/giornata"),
                ("analisi_settimana", "3. 🗓️ Analisi GPS settimana"),
                ("medie_confronti", "4. ⚖️ Medie e confronti"),
                ("analisi_individuale", "5. 👤 Analisi individuale"),
                ("palestra_gymaware", "6. 🏋️ Palestra & GymAware (VBT)"),
                ("pannello_controllo", "7. ⚙️ Pannello di controllo FIR"),
                ("storico_dati", "8. 🗄️ Storico dati"),
                ("import_dati", "9. 📥 Importazione"),
                ("cambio_password", "10. 🔑 Cambio password"),
                ("logout", "11. 🚪 Logout"),
            ]
        else:
            # Per profili di sola visualizzazione (Viewer / Staff)
            nav_items = [
                ("analisi_sessione_giornata", "1. ⏱️ Analisi GPS sessione/giornata"),
                ("analisi_settimana", "2. 🗓️ Analisi GPS settimana"),
                ("medie_confronti", "3. ⚖️ Medie e confronti"),
                ("analisi_individuale", "4. 👤 Analisi individuale"),
                ("palestra_gymaware", "5. 🏋️ Palestra & GymAware (VBT)"),
                ("cambio_password", "6. 🔑 Cambio password"),
                ("logout", "7. 🚪 Logout"),
            ]

        for page_id, page_label in nav_items:
            if page_id == "logout":
                if st.button(page_label, key="side_nav_logout", use_container_width=True, type="secondary"):
                    st.session_state["authenticated"] = False
                    st.session_state["active_page"] = "dashboard_home"
                    st.session_state.pop("current_user", None)
                    st.session_state.pop("user_role", None)
                    st.rerun()
                continue

            is_cur = st.session_state["active_page"] == page_id
            if st.button(
                page_label,
                key=f"side_nav_{page_id}",
                use_container_width=True,
                type="primary" if is_cur else "secondary",
            ):
                st.session_state["active_page"] = page_id
                # All'accesso della voce di menu viene mostrata la prima sottopagina disponibile di quella sezione
                if page_id in FIRST_SUBTABS:
                    st.session_state[f"active_subtab_{page_id}"] = FIRST_SUBTABS[page_id]
                st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
                st.rerun()

        st.markdown("<hr style='border-color:rgba(255,255,255,0.12); margin:14px 0;'>", unsafe_allow_html=True)

        st.markdown(
            f"""
            <div style="background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.12); border-radius:10px; padding:12px;">
                <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; color:#D4AF37; margin-bottom:6px;">
                    Stato Database Attivo
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>Atleti in Roster:</span> <b>{len(players_df)}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>Settimane Raduno:</span> <b>{len(camps_df)}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>Partite Storiche:</span> <b>{len(matches_df)}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>Gare Oval Match:</span> <b style="color:#FBBF24;">{len(oval_df):,}</b>
                </div>
                <hr style="border-color:rgba(255,255,255,0.1); margin:6px 0;">
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:3px;">
                    <span>GPS Nazionale (FIR):</span> <b style="color:#38BDF8;">{counts['nazionale']:,}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:3px;">
                    <span>GPS Benetton:</span> <b style="color:#34D399;">{counts['benetton']:,}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; margin-bottom:3px;">
                    <span>GPS Zebre:</span> <b style="color:#A78BFA;">{counts['zebre']:,}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; border-top:1px solid rgba(255,255,255,0.1); padding-top:3px; margin-top:3px; margin-bottom:3px;">
                    <span>Totale GPS:</span> <b>{counts['total']:,}</b>
                </div>
                <div style="font-size:0.78rem; display:flex; justify-content:space-between; border-top:1px solid rgba(255,255,255,0.1); padding-top:3px; margin-top:3px;">
                    <span>GymAware (VBT):</span> <b style="color:#F59E0B;">{gym_stats['total_sets']:,} set</b>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    page = st.session_state["active_page"]
    allowed_viewer_pages = (
        "analisi_sessione_giornata",
        "analisi_settimana",
        "medie_confronti",
        "analisi_individuale",
        "palestra_gymaware",
        "cambio_password",
    )
    if user_role != "admin" and page not in allowed_viewer_pages:
        page = "analisi_sessione_giornata"
        st.session_state["active_page"] = "analisi_sessione_giornata"

    if st.session_state.get("_last_rendered_page") != page:
        st.session_state["_last_rendered_page"] = page
        st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1

    cur_u_info = st.session_state.get("current_user", {})
    if cur_u_info.get("must_change_password") and page != "cambio_password":
        st.warning(
            "⚠️ **Attenzione**: Stai utilizzando una **password provvisoria**. "
            "Per motivi di sicurezza, ti invitiamo a impostare subito una password personale definitiva "
            "nella sezione **'🔑 Cambio password'** dal menu laterale."
        )

    # 1. Home
    if page == "dashboard_home":
        views.dashboard_home.render_dashboard_home(t)
    # 2. Analisi GPS sessione/giornata
    elif page == "analisi_sessione_giornata":
        views.home.render_analisi_sessione_giornata(t)
    # 3. Analisi GPS settimana
    elif page == "analisi_settimana":
        views.home.render_analisi_settimana(t)
    # 4. Medie e confronti
    elif page == "medie_confronti":
        views.report_comparazione.render_medie_e_confronti(t)
    # 5. Analisi individuale
    elif page == "analisi_individuale":
        views.analisi_individuale.render_analisi_individuale(t)
    # 6. Palestra & GymAware (VBT)
    elif page == "palestra_gymaware":
        views.palestra_gymaware.render_palestra_gymaware(t)
    # 7. Pannello di controllo FIR
    elif page == "pannello_controllo":
        if user_role == "admin":
            importlib.reload(views.pannello_controllo)
            views.pannello_controllo.render_pannello_controllo(t)
        else:
            st.error("⛔ Accesso riservato agli amministratori.")
    # 8. Storico dati
    elif page == "storico_dati":
        views.storico_gps.render_storico_gps(t)
    # 9. Importazione
    elif page == "import_dati":
        if user_role == "admin":
            views.import_dati.render_import_dati(t)
        else:
            st.error("⛔ Accesso riservato agli amministratori.")
    # 10. Cambio password
    elif page == "cambio_password":
        views.cambio_password.render_cambio_password(t)
    # Fallback su Home
    else:
        views.dashboard_home.render_dashboard_home(t)


if __name__ == "__main__":
    main()
