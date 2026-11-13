# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import io
import streamlit as st
import pandas as pd
import auth
from config import render_page_header


def render_admin_utenti(t: dict):
    render_page_header(
        "Gestione Utenti & Controllo Accessi",
        "Amministrazione profili utente della FIR GPS Platform, creazione massiva (15+ account), email credenziali e reset password provvisorie.",
        "bi-shield-lock-fill",
    )

    cur_user = st.session_state.get("current_user", {})
    cur_username = cur_user.get("username", "")

    if st.session_state.get("user_role") != "admin":
        st.error("⛔ Accesso Negato: questa sezione è riservata esclusivamente agli Amministratori di sistema.")
        return

    mail_cfg = auth.get_mail_config()
    users = auth.get_users()
    n_total = len(users)
    n_admin = sum(1 for u in users if u.get("role") == "admin")
    n_viewer = sum(1 for u in users if u.get("role") == "viewer")
    n_temp = sum(1 for u in users if u.get("must_change_password"))
    n_terms = sum(1 for u in users if u.get("has_accepted_terms"))

    # KPI Row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Profili Utente Totali", f"{n_total}", "Account attivi")
    k2.metric("Amministratori (Full)", f"{n_admin}", "Gestione e configurazione")
    k3.metric("Visualizzatori (Staff)", f"{n_viewer}", "Consultazione & PDF")
    k4.metric("Password Provvisorie", f"{n_temp}", "In attesa di primo cambio")
    k5.metric("Privacy Accettata", f"{n_terms}/{n_total}", "Clickwrap GDPR & IP")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # SEZIONE CONFIGURAZIONE EMAIL DI RIFERIMENTO E PORTALE
    # ==========================================================================
    with st.expander("⚙️ Configurazione Email di Riferimento Mittente & Portale Web FIR", expanded=False):
        st.markdown(
            """
            <div style="font-size:0.82rem; color:#475569; margin-bottom:10px;">
                Questi parametri vengono utilizzati automaticamente per compilare le email con le credenziali (Username e Password Provvisoria) inviate allo staff.
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("form_mail_config"):
            c_m1, c_m2, c_m3 = st.columns([1.5, 1.5, 1.5])
            cfg_sender = c_m1.text_input("Email Mittente FIR di Riferimento", value=mail_cfg.get("sender_email", "gps.performance@federugby.it"))
            cfg_name = c_m2.text_input("Nome Mittente", value=mail_cfg.get("sender_name", "FIR Area Performance & GPS"))
            cfg_url = c_m3.text_input("URL Piattaforma Web", value=mail_cfg.get("app_url", "https://gps.federugby.it"))

            st.markdown("<hr style='margin:10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st.caption("Invio Diretto Server SMTP (Opzionale: se disabilitato, puoi usare il comodissimo pulsante 'Invia via Email Client' o copiare il testo):")

            smtp_on = st.checkbox("Abilita Spedizione Diretta via Server SMTP", value=mail_cfg.get("smtp_enabled", False))
            c_s1, c_s2, c_s3, c_s4 = st.columns(4)
            smtp_h = c_s1.text_input("Host SMTP", value=mail_cfg.get("smtp_host", ""), placeholder="es. smtp.office365.com")
            smtp_p = c_s2.number_input("Porta", value=int(mail_cfg.get("smtp_port", 587)), min_value=25, max_value=65535)
            smtp_u = c_s3.text_input("Username SMTP", value=mail_cfg.get("smtp_user", ""), placeholder="es. performance@federugby.it")
            smtp_pw = c_s4.text_input("Password SMTP", value=mail_cfg.get("smtp_password", ""), type="password")

            btn_save_cfg = st.form_submit_button("Salva Configurazione Email & Portale", type="secondary")
            if btn_save_cfg:
                new_cfg = {
                    "sender_email": cfg_sender.strip(),
                    "sender_name": cfg_name.strip(),
                    "app_url": cfg_url.strip(),
                    "smtp_enabled": smtp_on,
                    "smtp_host": smtp_h.strip(),
                    "smtp_port": int(smtp_p),
                    "smtp_user": smtp_u.strip(),
                    "smtp_password": smtp_pw.strip(),
                    "use_tls": True,
                }
                auth.save_mail_config(new_cfg)
                st.success("Configurazione email e portale salvata con successo!")
                st.rerun()

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # SEZIONE CREAZIONE NUOVI ACCOUNT (SINGOLA & MASSIVA 15+)
    # ==========================================================================
    st.markdown("### ➕ Creazione Nuovi Account & Generazione Credenziali")

    tab_single, tab_mass = st.tabs([
        "👤 Creazione Singola Rapida",
        "⚡ Creazione Massiva (Incolla Lista o Carica CSV per 15+ Account)",
    ])

    # --------------------------------------------------------------------------
    # TAB 1: CREAZIONE SINGOLA RAPIDA
    # --------------------------------------------------------------------------
    with tab_single:
        st.markdown(
            """
            <div style="font-size:0.84rem; color:#475569; margin-bottom:12px;">
                Crea un singolo profilo. L'indirizzo email fungerà da Username ufficiale. Il sistema genera automaticamente una password provvisoria pronta da spedire via email.
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Password provvisoria generata al volo
        if "single_temp_pw" not in st.session_state:
            st.session_state["single_temp_pw"] = auth.generate_temp_password()

        with st.form("form_single_user"):
            c1, c2 = st.columns([1.5, 1.5])
            s_email = c1.text_input("Email Utente / Username", placeholder="es. mario.rossi@federugby.it").strip()
            s_name = c2.text_input("Nome e Cognome Completo", placeholder="es. Mario Rossi").strip()

            c3, c4 = st.columns([1.5, 1.5])
            s_role = c3.selectbox(
                "Ruolo e Permessi",
                ["viewer", "admin"],
                format_func=lambda r: "Visualizzatore / Staff Tecnico (Solo Consultazione & PDF)" if r == "viewer" else "Amministratore (Accesso Completo)",
                index=0,
            )
            s_pw = c4.text_input("Password Provvisoria", value=st.session_state["single_temp_pw"]).strip()

            s_must_change = st.checkbox("Richiedi modifica password al primo accesso", value=True)

            btn_create_single = st.form_submit_button("Crea Account e Prepara Email Credenziali", type="primary", use_container_width=True)

            if btn_create_single:
                if not s_email:
                    st.error("Inserisci l'indirizzo email dell'utente.")
                elif "@" not in s_email or "." not in s_email:
                    st.error("Inserisci un indirizzo email valido (es. nome.cognome@federugby.it).")
                else:
                    if not s_name:
                        s_name = s_email.split("@")[0].replace(".", " ").replace("_", " ").title()
                    ok, msg = auth.create_user(
                        username=s_email,
                        full_name=s_name,
                        role=s_role,
                        password=s_pw,
                        email=s_email,
                        must_change_password=s_must_change,
                    )
                    if ok:
                        st.session_state["last_created_user"] = {
                            "username": s_email,
                            "email": s_email,
                            "full_name": s_name,
                            "role": s_role,
                            "temp_password": s_pw,
                        }
                        st.session_state["single_temp_pw"] = auth.generate_temp_password()
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {msg}")

        # Se appena creato un utente, mostra il box con le credenziali pronte per l'invio
        last_u = st.session_state.get("last_created_user")
        if last_u:
            em_payload = auth.build_credentials_email(last_u, last_u["temp_password"], is_reset=False)
            st.markdown(
                f"""
                <div style="background:#F0FDF4; border:1.5px solid #86EFAC; border-radius:10px; padding:16px 20px; margin-top:14px; box-shadow:0 2px 8px rgba(22,101,52,0.06);">
                    <div style="font-size:0.75rem; font-weight:800; color:#15803D; text-transform:uppercase; letter-spacing:0.06em;">
                        CREDENZIALI GENERATE CON SUCCESSO
                    </div>
                    <div style="font-size:1.1rem; font-weight:800; color:#064E3B; margin-top:2px;">
                        {last_u['full_name']} &bull; <span style="font-size:0.95rem; font-weight:600; color:#047857;">{last_u['email']}</span>
                    </div>
                    <div style="margin-top:8px; font-size:0.86rem; color:#14532D;">
                        Password Provvisoria: <code style="background:#FFFFFF; padding:2px 8px; border-radius:4px; font-size:0.92rem; font-weight:700; border:1px solid #BBF7D0;">{last_u['temp_password']}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col_btn1, col_btn2 = st.columns([1.5, 1.5])
            with col_btn1:
                st.link_button(
                    "📧 Invia via Email Client (Apre Outlook / Mail)",
                    url=em_payload["mailto_url"],
                    type="primary",
                    use_container_width=True,
                )
            with col_btn2:
                if mail_cfg.get("smtp_enabled"):
                    if st.button("🚀 Invia Email Diretta via Server SMTP", key="btn_send_single_smtp", type="secondary", use_container_width=True):
                        ok_s, msg_s = auth.send_smtp_email(last_u["email"], em_payload["subject"], em_payload["body_text"])
                        if ok_s:
                            st.success(msg_s)
                        else:
                            st.error(msg_s)
                else:
                    st.caption("💡 Clicca 'Invia via Email Client' o copia il testo sottostante per spedire le credenziali.")

            with st.expander("📋 Mostra / Copia Testo Completo Email di Benvenuto", expanded=False):
                st.code(em_payload["body_text"], language="text")

    # --------------------------------------------------------------------------
    # TAB 2: CREAZIONE MASSIVA (INCOLLA LISTA 15+ O CARICA CSV)
    # --------------------------------------------------------------------------
    with tab_mass:
        st.markdown(
            """
            <div style="font-size:0.84rem; color:#475569; margin-bottom:12px;">
                <b>Creazione Rapida Multipla (ideale per 15 o più account contemporaneamente):</b><br>
                Incolla direttamente l'elenco degli indirizzi email (uno per riga) oppure carica un file CSV. 
                Il sistema genererà automaticamente per ciascun utente una password provvisoria sicura, imposterà il cambio password obbligatorio al primo accesso e produrrà una tabella riassuntiva esportabile in CSV.
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_in1, col_in2 = st.columns([2.0, 1.2])

        with col_in1:
            raw_paste = st.text_area(
                "Incolla Lista Utenti (uno per riga):",
                placeholder=(
                    "# Esempio 1: solo email (una per riga)\n"
                    "mario.rossi@federugby.it\n"
                    "giuseppe.verdi@benettonrugby.it\n"
                    "luigi.bianchi@zebreparma.it\n\n"
                    "# Esempio 2: con nome e cognome separati da virgola\n"
                    "antonio.ferrari@federugby.it, Antonio Ferrari, viewer\n"
                    "marco.colombo@federugby.it, Marco Colombo, viewer"
                ),
                height=180,
            )

        with col_in2:
            st.markdown("<div style='font-size:0.84rem; font-weight:700; color:#0F172A; margin-bottom:4px;'>Oppure carica file CSV:</div>", unsafe_allow_html=True)
            uploaded_csv = st.file_uploader("Carica file CSV", type=["csv"], label_visibility="collapsed")
            mass_role_default = st.selectbox(
                "Ruolo Predefinito per la lista:",
                ["viewer", "admin"],
                format_func=lambda r: "Visualizzatore / Staff Tecnico" if r == "viewer" else "Amministratore",
                index=0,
            )

        btn_batch_create = st.button("⚡ Crea Tutti gli Account (Genera Password Provvisorie)", type="primary", use_container_width=True)

        if btn_batch_create:
            parsed_entries = []

            # 1. Parsing da CSV se caricato
            if uploaded_csv is not None:
                try:
                    df_up = pd.read_csv(uploaded_csv)
                    # Cerca colonne
                    col_em = next((c for c in df_up.columns if "email" in c.lower() or "mail" in c.lower() or "user" in c.lower()), None)
                    col_nm = next((c for c in df_up.columns if "nome" in c.lower() or "name" in c.lower()), None)
                    col_rl = next((c for c in df_up.columns if "ruolo" in c.lower() or "role" in c.lower()), None)

                    if col_em:
                        for _, r in df_up.iterrows():
                            e_val = str(r[col_em]).strip()
                            if e_val and "@" in e_val:
                                n_val = str(r[col_nm]).strip() if col_nm and pd.notna(r[col_nm]) else ""
                                r_val = str(r[col_rl]).strip() if col_rl and pd.notna(r[col_rl]) else mass_role_default
                                parsed_entries.append({"email": e_val, "full_name": n_val, "role": r_val})
                except Exception as e:
                    st.error(f"Errore lettura file CSV: {e}")

            # 2. Parsing da textarea
            if raw_paste.strip():
                for line in raw_paste.splitlines():
                    l_str = line.strip()
                    if not l_str or l_str.startswith("#"):
                        continue
                    parts = [p.strip() for p in l_str.split(",")]
                    em_part = parts[0]
                    if "@" in em_part:
                        nm_part = parts[1] if len(parts) > 1 else ""
                        rl_part = parts[2].lower() if len(parts) > 2 and parts[2].lower() in ("admin", "viewer") else mass_role_default
                        parsed_entries.append({"email": em_part, "full_name": nm_part, "role": rl_part})

            if not parsed_entries:
                st.warning("Nessun indirizzo email valido individuato. Inserisci almeno un indirizzo email nel box di testo o carica un file CSV.")
            else:
                s_count, created_users, err_list = auth.batch_create_users(parsed_entries, default_role=mass_role_default)
                st.session_state["last_batch_created"] = created_users
                if s_count > 0:
                    st.success(f"🎉 Operazione completata: {s_count} account creati con successo!")
                if err_list:
                    for er in err_list:
                        st.warning(er)
                st.rerun()

        # Risultato dell'ultima creazione massiva
        last_batch = st.session_state.get("last_batch_created", [])
        if last_batch:
            st.markdown(f"#### 📋 Elenco Credenziali Generate per gli Ultimi {len(last_batch)} Account Creati")
            st.caption("Puoi scaricare l'elenco completo in CSV oppure cliccare su ciascun utente per aprire la mail precompilata.")

            batch_df = pd.DataFrame([
                {
                    "Nome Completo": u["full_name"],
                    "Email / Username": u["email"],
                    "Ruolo": "Amministratore" if u["role"] == "admin" else "Visualizzatore",
                    "Password Provvisoria": u["temp_password"],
                }
                for u in last_batch
            ])

            st.dataframe(batch_df, use_container_width=True, hide_index=True)

            csv_buf = io.StringIO()
            batch_df.to_csv(csv_buf, index=False)
            csv_data = csv_buf.getvalue()

            c_d1, c_d2 = st.columns([1.5, 2.5])
            with c_d1:
                st.download_button(
                    "⬇️ Scarica Credenziali in CSV",
                    data=csv_data,
                    file_name="FIR_Credenziali_Nuovi_Account.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                )
            with c_d2:
                if mail_cfg.get("smtp_enabled"):
                    if st.button("🚀 Spedisci Tutte le Email di Benvenuto (SMTP)", key="btn_send_all_batch"):
                        n_sent = 0
                        for u_item in last_batch:
                            ok_s, _ = auth.send_smtp_email(u_item["email"], u_item["subject"], u_item["body_text"])
                            if ok_s:
                                n_sent += 1
                        st.success(f"Spedite con successo {n_sent} email su {len(last_batch)}!")

            with st.expander("📬 Azioni Invio Email Individuali per ciascun nuovo utente", expanded=False):
                for u_item in last_batch:
                    c_row1, c_row2 = st.columns([2.5, 1.0])
                    c_row1.markdown(f"**{u_item['full_name']}** ({u_item['email']}) &bull; Pass: `{u_item['temp_password']}`")
                    c_row2.link_button("📧 Apri Mail", url=u_item["mailto_url"], use_container_width=True)

    st.markdown("<hr style='margin:24px 0 16px 0; border-color:#CBD5E1;'>", unsafe_allow_html=True)

    # ==========================================================================
    # ELENCO UTENTI REGISTRATI & RESET PASSWORD
    # ==========================================================================
    st.markdown("### 👥 Elenco Utenti Registrati & Manutenzione Credenziali")

    f_col1, f_col2 = st.columns([2.2, 1.2])
    search_q = f_col1.text_input("🔍 Cerca utente per Nome, Username o Email:", placeholder="es. rossi, garbisi, admin...").strip().lower()
    filter_role = f_col2.selectbox("Filtra per Ruolo:", ["Tutti i Ruoli", "Solo Amministratori", "Solo Visualizzatori"])

    filtered_users = []
    for u in users:
        u_name = str(u.get("username") or "").lower()
        u_fn = str(u.get("full_name") or "").lower()
        u_em = str(u.get("email") or "").lower()
        u_role = u.get("role", "viewer")

        if search_q and search_q not in u_name and search_q not in u_fn and search_q not in u_em:
            continue
        if filter_role == "Solo Amministratori" and u_role != "admin":
            continue
        if filter_role == "Solo Visualizzatori" and u_role != "viewer":
            continue
        filtered_users.append(u)

    st.caption(f"Visualizzazione di {len(filtered_users)} profili su {len(users)} registrati:")

    for u in filtered_users:
        u_name = u["username"]
        u_email = u.get("email") or (u_name if "@" in u_name else f"{u_name}@federugby.it")
        u_fn = u.get("full_name", u_name)
        u_role = u.get("role", "viewer")
        u_created = u.get("created_at", "—")
        u_login = u.get("last_login") or "Nessun accesso ancora"
        is_prim = u.get("is_primary", False)
        is_self = u_name.lower() == cur_username.lower() or u_email.lower() == cur_username.lower()
        must_chg = u.get("must_change_password", False)

        role_badge = (
            '<span style="background:linear-gradient(90deg, #002B49 0%, #0066B2 100%); color:#D4AF37; padding:3px 10px; border-radius:6px; font-weight:800; font-size:0.75rem; border:1px solid #D4AF37;">AMMINISTRATORE</span>'
            if u_role == "admin"
            else '<span style="background:#F1F5F9; color:#334155; padding:3px 10px; border-radius:6px; font-weight:700; font-size:0.75rem; border:1px solid #CBD5E1;">VISUALIZZATORE (STAFF)</span>'
        )

        pw_badge = (
            ' <span style="background:#FEF3C7; color:#B45309; padding:2px 8px; border-radius:4px; font-size:0.70rem; font-weight:800; border:1px solid #FCD34D;">⚠️ PASSWORD PROVVISORIA</span>'
            if must_chg
            else ' <span style="background:#DCFCE7; color:#15803D; padding:2px 8px; border-radius:4px; font-size:0.70rem; font-weight:700; border:1px solid #86EFAC;">✓ PASSWORD DEFINITIVA</span>'
        )

        has_acc = u.get("has_accepted_terms", False)
        terms_badge = (
            ' <span style="background:#DCFCE7; color:#15803D; padding:2px 8px; border-radius:4px; font-size:0.70rem; font-weight:700; border:1px solid #86EFAC;">✓ PRIVACY & IP ACCETTATI</span>'
            if has_acc
            else ' <span style="background:#FEE2E2; color:#B91C1C; padding:2px 8px; border-radius:4px; font-size:0.70rem; font-weight:800; border:1px solid #FCA5A5;">⏳ PRIVACY DA ACCETTARE</span>'
        )

        prim_tag = ' <span style="background:#FEF3C7; color:#92400E; padding:2px 6px; border-radius:4px; font-size:0.68rem; font-weight:700;">DEFAULT</span>' if is_prim else ""
        self_tag = ' <span style="background:#DCFCE7; color:#166534; padding:2px 6px; border-radius:4px; font-size:0.68rem; font-weight:700;">TU</span>' if is_self else ""

        with st.container():
            st.markdown(
                f"""
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; padding:14px 18px; margin-bottom:12px; box-shadow:0 1px 4px rgba(15,23,42,0.04);">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <div>
                            <div style="font-size:1.02rem; font-weight:800; color:#0F172A;">
                                {u_fn} <span style="font-size:0.82rem; font-weight:600; color:#64748B;">({u_email})</span> {prim_tag} {self_tag} {pw_badge} {terms_badge}
                            </div>
                            <div style="font-size:0.74rem; color:#64748B; margin-top:2px;">
                                Username: <b>@{u_name}</b> &bull; Creato il: <b>{u_created}</b> &bull; Ultimo accesso: <b>{u_login}</b>
                            </div>
                        </div>
                        <div>
                            {role_badge}
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Azioni utente
            col_act1, col_act2, col_act3 = st.columns([2.2, 1.4, 1.0])

            # RESET PASSWORD POTENZIATO
            with col_act1:
                with st.expander(f"🔑 Reset Password per {u_fn}"):
                    st.caption("Scegli la modalità di reimpostazione:")
                    sub_t1, sub_t2 = st.tabs(["⚡ Reset con Password Provvisoria", "✏️ Password Manuale"])

                    with sub_t1:
                        st.markdown("<div style='font-size:0.80rem; color:#475569;'>Genera istantaneamente una nuova password provvisoria sicura e prepara l'email di notifica per l'utente.</div>", unsafe_allow_html=True)
                        if st.button("Genera Password Provvisoria & Resetta", key=f"btn_auto_rst_{u_name}", type="primary"):
                            ok_rst, msg_rst, new_tmp_pw = auth.admin_reset_password_auto(u_name, must_change_password=True)
                            if ok_rst:
                                st.session_state[f"last_reset_{u_name}"] = new_tmp_pw
                                st.success(f"Nuova password provvisoria: `{new_tmp_pw}`")
                                st.rerun()
                            else:
                                st.error(msg_rst)

                        # Se appena resettato, mostra pulsante mailto
                        cur_tmp_pw = st.session_state.get(f"last_reset_{u_name}")
                        if cur_tmp_pw:
                            rst_payload = auth.build_credentials_email(u, cur_tmp_pw, is_reset=True)
                            st.link_button("📧 Invia Email di Reset (Client Posta)", url=rst_payload["mailto_url"], type="secondary", use_container_width=True)
                            with st.popover("📋 Copia Testo Email di Reset"):
                                st.code(rst_payload["body_text"], language="text")

                    with sub_t2:
                        with st.form(f"form_reset_{u_name}"):
                            new_rst_pw = st.text_input("Digita Nuova Password", type="password", key=f"rst_pw_{u_name}").strip()
                            btn_rst = st.form_submit_button("Salva Password Manuale", type="secondary")
                            if btn_rst:
                                ok, msg = auth.admin_reset_password(u_name, new_rst_pw)
                                if ok:
                                    st.success(msg)
                                    st.rerun()
                                else:
                                    st.error(msg)

            # CAMBIA RUOLO
            with col_act2:
                if not is_prim:
                    new_r = st.selectbox(
                        "Ruolo",
                        ["viewer", "admin"],
                        index=0 if u_role == "viewer" else 1,
                        key=f"sel_role_{u_name}",
                        format_func=lambda x: "Visualizzatore" if x == "viewer" else "Amministratore",
                        label_visibility="collapsed",
                    )
                    if new_r != u_role:
                        if st.button("Aggiorna Ruolo", key=f"btn_r_{u_name}", type="secondary"):
                            ok, msg = auth.admin_update_user_role(u_name, new_r)
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                else:
                    st.caption("Ruolo Admin principale bloccato")

            # ELIMINA UTENTE
            with col_act3:
                if not is_prim and not is_self:
                    if st.button("🗑️ Elimina", key=f"btn_del_u_{u_name}", type="secondary"):
                        ok, msg = auth.admin_delete_user(u_name, cur_username)
                        if ok:
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                elif is_self:
                    st.caption("Account tuo")
                elif is_prim:
                    st.caption("Protetto")
