import streamlit as st
from config import render_page_header
import auth


def render_cambio_password(t: dict):
    render_page_header(
        "Sicurezza & Credenziali Utente",
        "Modifica e aggiorna la password di accesso alla piattaforma FIR GPS Analytics",
        "bi-key-fill",
    )

    cur_user = st.session_state.get("current_user", {})
    username = cur_user.get("username", "utente")
    full_name = cur_user.get("full_name", "Utente FIR")
    user_role = st.session_state.get("user_role", "viewer")

    col_info, col_form = st.columns([1.2, 1.8])

    with col_info:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1.5px solid #CBD5E1; border-radius:12px; padding:18px 20px; box-shadow:0 3px 10px rgba(15,23,42,0.05); margin-bottom:16px;">
                <div style="font-size:0.75rem; font-weight:800; text-transform:uppercase; color:#D4AF37; letter-spacing:0.06em; margin-bottom:8px;">
                    Profilo Attualmente Connesso
                </div>
                <div style="font-size:1.15rem; font-weight:800; color:#002B49; margin-bottom:2px;">
                    {full_name}
                </div>
                <div style="font-size:0.85rem; color:#64748B; margin-bottom:12px;">
                    Nome utente: <b>@{username}</b>
                </div>
                <div style="display:inline-block; background:{'#FEF3C7' if user_role == 'admin' else '#E0F2FE'}; color:{'#92400E' if user_role == 'admin' else '#0369A1'}; font-weight:800; font-size:0.75rem; padding:3px 10px; border-radius:6px; border:1px solid {'#FDE68A' if user_role == 'admin' else '#BAE6FD'};">
                    Ruolo: {'Amministratore (Admin)' if user_role == 'admin' else 'Staff / Visualizzatore'}
                </div>
                <hr style="border-color:#E2E8F0; margin:14px 0 10px 0;">
                <div style="font-size:0.78rem; color:#475569; line-height:1.4;">
                    🔒 <b>Requisiti di sicurezza:</b>
                    <ul style="margin:4px 0 0 16px; padding:0;">
                        <li>Almeno 6 caratteri</li>
                        <li>Non condividere la password con terzi</li>
                        <li>La modifica ha effetto immediato per i successivi accessi</li>
                    </ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_form:
        with st.container(border=True):
            st.markdown("### 🔑 Modifica Password")
            st.caption("Inserisci la password corrente e definisci la nuova password di accesso:")

            with st.form("form_cambio_password_main"):
                cur_pw = st.text_input("Password Attuale", type="password", placeholder="Inserisci la password attuale...", key="cpw_cur")
                new_pw1 = st.text_input("Nuova Password", type="password", placeholder="Inserisci la nuova password (min. 6 caratteri)...", key="cpw_new1")
                new_pw2 = st.text_input("Conferma Nuova Password", type="password", placeholder="Ripeti la nuova password...", key="cpw_new2")

                submitted = st.form_submit_button("Aggiorna Password Personale", type="primary", use_container_width=True)
                if submitted:
                    if not cur_pw.strip():
                        st.error("Inserisci la password attuale.")
                    elif not new_pw1.strip():
                        st.error("Inserisci la nuova password.")
                    elif len(new_pw1) < 6:
                        st.error("La nuova password deve contenere almeno 6 caratteri.")
                    elif new_pw1 != new_pw2:
                        st.error("Le due nuove password non coincidono.")
                    else:
                        ok, msg = auth.change_user_password(username, cur_pw, new_pw1)
                        if ok:
                            if "current_user" in st.session_state and isinstance(st.session_state["current_user"], dict):
                                st.session_state["current_user"]["must_change_password"] = False
                            st.success(f"✅ {msg}")
                            st.balloons()
                        else:
                            st.error(f"❌ {msg}")
