# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import streamlit as st
import auth
from config import get_logo_base64


def render_login_page(t: dict):
    b64_logo = get_logo_base64()
    logo_img_html = (
        f'<img src="data:image/png;base64,{b64_logo}" style="height:76px; width:auto; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.35));" alt="FIR Logo">'
        if b64_logo
        else '<div style="width:68px; height:68px; border-radius:50%; background:#0066B2; border:2.5px solid #D4AF37; display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-weight:800; font-size:1.4rem;">FIR</div>'
    )

    _, col_center, _ = st.columns([1.2, 2.0, 1.2])

    with col_center:
        st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #002B49 0%, #0066B2 100%); border-radius:16px 16px 0 0; padding:28px 24px; text-align:center; border:1px solid rgba(212,175,55,0.4); border-bottom:3px solid #D4AF37; box-shadow:0 8px 24px rgba(0,43,73,0.35);">
                <div style="display:flex; justify-content:center; margin-bottom:12px;">
                    {logo_img_html}
                </div>
                <div style="font-size:0.75rem; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:#D4AF37; margin-bottom:4px;">
                    FEDERAZIONE ITALIANA RUGBY &bull; AREA PERFORMANCE
                </div>
                <div style="font-size:1.55rem; font-weight:800; letter-spacing:-0.02em; color:#FFFFFF; margin:0;">
                    FIR GPS PLATFORM
                </div>
                <div style="font-size:0.85rem; color:#93C5FD; font-weight:500; margin-top:4px;">
                    Accesso Riservato Staff Tecnico e Performance Italrugby
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown(
                """
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:none; border-radius:0 0 16px 16px; padding:28px 28px 20px 28px; box-shadow:0 12px 28px rgba(15,23,42,0.08); margin-bottom:16px;">
                """,
                unsafe_allow_html=True,
            )

            with st.form("fir_login_form"):
                st.markdown("<div style='font-size:0.92rem; font-weight:700; color:#0F172A; margin-bottom:8px;'>Inserisci le tue credenziali di accesso</div>", unsafe_allow_html=True)

                username = st.text_input("Email o Nome Utente (Username)", placeholder="Es. nome.cognome@federugby.it oppure admin", key="login_username").strip()
                password = st.text_input("Password", type="password", placeholder="••••••••", key="login_password").strip()

                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button("Accedi alla Piattaforma FIR", type="primary", use_container_width=True)

                if submitted:
                    if not username or not password:
                        st.error("Inserisci sia il nome utente che la password.")
                    else:
                        user_info = auth.verify_user(username, password)
                        if user_info:
                            st.session_state["authenticated"] = True
                            st.session_state["current_user"] = user_info
                            st.session_state["user_role"] = user_info["role"]
                            if user_info["role"] == "admin":
                                st.session_state["active_page"] = "dashboard_home"
                            else:
                                st.session_state["active_page"] = "analisi_sessione_giornata"
                                st.session_state["active_subtab_analisi_sessione_giornata"] = "report_sessione"
                            st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
                            st.success(f"Bentornato, {user_info['full_name']}!")
                            st.rerun()
                        else:
                            st.error("Credenziali non valide. Verifica username e password.")

            st.markdown(
                """
                <div style="margin-top:16px; padding:12px 14px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; font-size:0.75rem; color:#475569;">
                    <b style="color:#002B49;">Profili di Default Disponibili:</b><br>
                    &bull; <b>Admin (Accesso Completo):</b> <code>admin</code> / <code>fir_admin_2026</code><br>
                    &bull; <b>Visualizzatore (Solo Consultazione):</b> <code>staff_fir</code> / <code>fir_staff_2026</code>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
