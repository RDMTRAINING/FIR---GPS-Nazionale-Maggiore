import datetime
import streamlit as st
import pandas as pd
from config import render_page_header, render_tab_navigation, render_navigation_cards, RUGBY_ROLES, DEPARTMENTS, ROLE_TO_DEPT, JERSEY_POSITIONS_1_23
import utils
import views.admin_utenti


def render_pannello_controllo(t: dict):
    render_page_header(
        "Pannello di Controllo Organizzativo FIR",
        "Gestione Roster • Atleti Raduno • Storico Partite • Formazione Match • Tipologie Sessioni • Gestione Utenti & Accessi",
        "bi-sliders",
    )

    cards_controllo = [
        {"id": "roster", "title": "Gestione Roster", "desc": "Anagrafica atleti, ruoli, club, Vmax e parametri", "icon": "bi-person-vcard"},
        {"id": "raduni", "title": "Atleti Raduno", "desc": "Convocazioni raduno, composizione e clonazione lista", "icon": "bi-people-fill"},
        {"id": "partite", "title": "Storico Partite", "desc": "Calendario match, risultati e avversari", "icon": "bi-calendar-event"},
        {"id": "formazioni", "title": "Formazione Match", "desc": "Formazione 1-15 titolari e 16-23 finishers", "icon": "bi-shield-check"},
        {"id": "tipologie_sessioni", "title": "Tipologie Sessioni", "desc": "Categorizzazione sedute per benchmark storici", "icon": "bi-tags"},
        {"id": "utenti_accessi", "title": "Gestione Utenti & Accessi", "desc": "Profili staff, credenziali e permessi RBAC", "icon": "bi-person-gear"},
    ]

    active_sub = render_navigation_cards("pannello_controllo", cards_controllo)

    if active_sub == "roster":
        _render_sub_roster(t)
    elif active_sub == "raduni":
        _render_sub_raduni(t)
    elif active_sub == "partite":
        _render_sub_partite(t)
    elif active_sub == "formazioni":
        _render_sub_formazioni(t)
    elif active_sub == "tipologie_sessioni":
        _render_sub_tipologie_sessioni(t)
    elif active_sub == "utenti_accessi":
        if st.session_state.get("user_role") == "admin":
            views.admin_utenti.render_admin_utenti(t)
        else:
            st.error("⛔ Accesso riservato agli amministratori.")


# ==============================================================================
# 1. GESTIONE ROSTER
# ==============================================================================
@st.fragment
def _fragment_roster_editor(players_df: pd.DataFrame):
    mode_col, sel_col = st.columns([1.2, 2.8])
    edit_mode = mode_col.radio("Modalità", ["Nuovo Giocatore", "Modifica Esistente"], horizontal=True, key="roster_edit_mode")
    selected_pid = None
    defaults = {
        "last_name": "", "first_name": "", "birth_year": 2000, "role": "Pilone",
        "department": "Avanti", "club": "Benetton Treviso", "code": "", "opta_id": "",
        "v_max": 30.0, "hml_fir": 533.0, "hsr_fir": 262.0, "match_avg_hml": 480.0, "match_avg_hsr": 202.0,
        "manual_override": False,
    }
    if edit_mode == "Modifica Esistente" and not players_df.empty:
        p_opts = players_df["id"].tolist()
        if "roster_sel_edit_pid" in st.session_state and st.session_state["roster_sel_edit_pid"] not in p_opts:
            st.session_state["roster_sel_edit_pid"] = p_opts[0]
        p_labels = {int(r["id"]): f"{r['name_display']} ({r.get('role', '')} - {r.get('club', '')})" for _, r in players_df.iterrows()}
        selected_pid = sel_col.selectbox("Seleziona Atleta da Modificare", p_opts, format_func=lambda x: p_labels.get(x, str(x)), key="roster_sel_edit_pid")
        matches = players_df[players_df["id"] == selected_pid]
        prow = matches.iloc[0] if not matches.empty else players_df.iloc[0]
        defaults = {
            "last_name": str(prow.get("last_name") or ""),
            "first_name": str(prow.get("first_name") or ""),
            "birth_year": int(prow["birth_year"]) if pd.notna(prow.get("birth_year")) else 2000,
            "role": str(prow.get("role") or "Pilone") if str(prow.get("role") or "") in RUGBY_ROLES else RUGBY_ROLES[0],
            "department": str(prow.get("department") or "Avanti") if str(prow.get("department") or "") in DEPARTMENTS else "Avanti",
            "club": str(prow.get("club") or ""),
            "code": str(prow.get("code") or ""),
            "opta_id": str(prow.get("opta_id") or ""),
            "v_max": float(prow["v_max"]) if pd.notna(prow.get("v_max")) else 30.0,
            "hml_fir": float(prow["hml_avg_fir"]) if pd.notna(prow.get("hml_avg_fir")) else 0.0,
            "hsr_fir": float(prow["hsr_avg_fir"]) if pd.notna(prow.get("hsr_avg_fir")) else 0.0,
            "match_avg_hml": float(prow["match_avg_hml"]) if pd.notna(prow.get("match_avg_hml")) else 480.0,
            "match_avg_hsr": float(prow["match_avg_hsr"]) if pd.notna(prow.get("match_avg_hsr")) else 202.0,
            "manual_override": bool(prow.get("manual_override", False)),
        }

    sfx = f"pid_{selected_pid}" if selected_pid is not None else "new"

    c1, c2, c3, c4 = st.columns(4)
    f_last = c1.text_input("Cognome", value=defaults["last_name"], key=f"f_ros_last_{sfx}")
    f_first = c2.text_input("Nome", value=defaults["first_name"], key=f"f_ros_first_{sfx}")
    f_year = c3.number_input("Anno di Nascita", min_value=1980, max_value=2015, value=defaults["birth_year"], step=1, key=f"f_ros_year_{sfx}")
    role_idx = RUGBY_ROLES.index(defaults["role"]) if defaults["role"] in RUGBY_ROLES else 0
    f_role = c4.selectbox("Ruolo", RUGBY_ROLES, index=role_idx, key=f"f_ros_role_{sfx}")

    c5, c6, c7, c8 = st.columns(4)
    auto_dept = ROLE_TO_DEPT.get(f_role, defaults["department"])
    dept_idx = DEPARTMENTS.index(auto_dept) if auto_dept in DEPARTMENTS else 0
    f_dept = c5.selectbox("Reparto", DEPARTMENTS, index=dept_idx, key=f"f_ros_dept_{sfx}")
    f_club = c6.text_input("Squadra / Club", value=defaults["club"], key=f"f_ros_club_{sfx}")
    f_code = c7.text_input("Sigla Breve (es. LM, GA)", value=defaults["code"], key=f"f_ros_code_{sfx}")
    f_opta = c8.text_input("Codice Oval / Opta ID", value=defaults["opta_id"], key=f"f_ros_opta_{sfx}")

    # Sezione Benchmark Medie Match & Velocità Modificabili
    st.markdown(
        """
        <div style="margin-top:14px; margin-bottom:6px; display:flex; align-items:center; gap:8px;">
            <span style="font-weight:700; color:#0F172A; font-size:0.88rem;">⚡ Dati Benchmark Medie Partita (80') & Performance</span>
            <span style="font-size:0.75rem; color:#64748B;">• Valori modificabili per target analisi % match</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_v, c_hfir, c_sfir, c_htot, c_stot = st.columns(5)
    f_vmax = c_v.number_input(
        "V max (km/h)",
        min_value=15.0,
        max_value=45.0,
        value=float(defaults["v_max"]) if defaults["v_max"] else 30.0,
        step=0.1,
        format="%.2f",
        key=f"f_ros_vmax_{sfx}",
        help="Velocità massima dell'atleta registrata da GPS o inserita manualmente",
    )
    f_hml_fir = c_hfir.number_input(
        "HML 80' (FIR)",
        min_value=0.0,
        max_value=2500.0,
        value=float(defaults.get("hml_fir", 0.0) or 0.0),
        step=5.0,
        format="%.0f",
        key=f"f_ros_hmlfir_{sfx}",
        help="Metri HML (>25.5W) normalizzati a 80' solo Nazionale",
    )
    f_hsr_fir = c_sfir.number_input(
        "HSR 80' (FIR)",
        min_value=0.0,
        max_value=2000.0,
        value=float(defaults.get("hsr_fir", 0.0) or 0.0),
        step=5.0,
        format="%.0f",
        key=f"f_ros_hsrfir_{sfx}",
        help="Metri HSR (>18 Avanti / >20 Trequarti) normalizzati a 80' solo Nazionale",
    )
    f_hml_tot = c_htot.number_input(
        "HML 80' Target Match",
        min_value=0.0,
        max_value=2500.0,
        value=float(defaults.get("match_avg_hml", 0.0) or 0.0),
        step=5.0,
        format="%.0f",
        key=f"f_ros_hmltot_{sfx}",
        help="Target HML medio match (Nazionale + Club), utilizzato come benchmark nelle analisi percentuali",
    )
    f_hsr_tot = c_stot.number_input(
        "HSR 80' Target Match",
        min_value=0.0,
        max_value=2000.0,
        value=float(defaults.get("match_avg_hsr", 0.0) or 0.0),
        step=5.0,
        format="%.0f",
        key=f"f_ros_hsrtot_{sfx}",
        help="Target HSR medio match (Nazionale + Club), utilizzato come benchmark nelle analisi percentuali",
    )

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    if selected_pid is not None:
        c_b1, c_b2, c_b3 = st.columns([1.6, 2.0, 1.2])
        is_curr_manual = bool(defaults.get("manual_override", False))
        if is_curr_manual:
            st.caption("✏️ *Atleta con modifiche manuali attive. Clicca **'🔄 Ricalcola DB'** per ripristinare i valori calcolati da Oval Match e GPS.*")

        if c_b1.button("💾 Salva Atleta", type="primary", use_container_width=True, key=f"btn_ros_save_{sfx}"):
            if not f_last.strip() or not f_first.strip():
                st.warning("Inserisci Cognome e Nome.")
            else:
                utils.save_player(
                    {
                        "last_name": f_last,
                        "first_name": f_first,
                        "birth_year": f_year,
                        "role": f_role,
                        "department": f_dept,
                        "club": f_club,
                        "code": f_code,
                        "opta_id": f_opta,
                        "v_max": f_vmax,
                        "hml_avg_fir": f_hml_fir,
                        "hsr_avg_fir": f_hsr_fir,
                        "hml_avg_tot": f_hml_tot,
                        "hsr_avg_tot": f_hsr_tot,
                        "match_avg_hml": f_hml_tot,
                        "match_avg_hsr": f_hsr_tot,
                        "manual_override": True,
                    },
                    player_id=selected_pid,
                )
                st.success(f"Atleta {f_first} {f_last} salvato con modifiche manuali registrate!")
                st.rerun()

        if c_b2.button("🔄 Ricalcola DB", use_container_width=True, key=f"btn_ros_recalc_{sfx}", help="Ripristina la squadra da Oval, V max da GPS e medie gara 80' calcolate automaticamente dal database"):
            utils.reset_player_manual_overrides(selected_pid)
            st.success("Valori e squadra ripristinati automaticamente dal DB!")
            st.rerun()

        if c_b3.button("🗑️ Elimina", use_container_width=True, key=f"btn_ros_del_{sfx}"):
            utils.delete_player(selected_pid)
            st.success("Atleta rimosso dal roster.")
            st.rerun()
    else:
        c_bnew = st.columns([1.6, 3.2])[0]
        if c_bnew.button("Salva Nuovo Atleta", type="primary", use_container_width=True, key="btn_ros_save_new"):
            if not f_last.strip() or not f_first.strip():
                st.warning("Inserisci Cognome e Nome.")
            else:
                utils.save_player(
                    {
                        "last_name": f_last,
                        "first_name": f_first,
                        "birth_year": f_year,
                        "role": f_role,
                        "department": f_dept,
                        "club": f_club,
                        "code": f_code,
                        "opta_id": f_opta,
                        "v_max": f_vmax,
                        "hml_avg_fir": f_hml_fir,
                        "hsr_avg_fir": f_hsr_fir,
                        "hml_avg_tot": f_hml_tot,
                        "hsr_avg_tot": f_hsr_tot,
                        "match_avg_hml": f_hml_tot,
                        "match_avg_hsr": f_hsr_tot,
                        "manual_override": False,
                    },
                    player_id=None,
                )
                st.success(f"Nuovo atleta {f_first} {f_last} inserito nel roster.")
                st.rerun()


@st.fragment
def _fragment_roster_table(players_df: pd.DataFrame):
    # Filters
    f1, f2, f3 = st.columns([2.2, 1.2, 1.4])
    q_search = f1.text_input("Cerca atleta per cognome, nome, sigla o codice Oval...", key="roster_q_search")
    q_dept = f2.selectbox("Filtro Reparto", ["Tutti i Reparti", "Avanti", "TreQuarti"], key="roster_q_dept")
    clubs_list = ["Tutte le Squadre"] + sorted([str(c) for c in players_df["club"].dropna().unique() if str(c).strip()])
    q_club = f3.selectbox("Filtro Squadra / Club", clubs_list, key="roster_q_club")

    filt = players_df.copy()
    if q_dept != "Tutti i Reparti":
        filt = filt[filt["department"] == q_dept]
    if q_club != "Tutte le Squadre":
        filt = filt[filt["club"].astype(str) == q_club]
    if q_search.strip():
        s = q_search.strip().lower()
        mask = (
            filt["name_display"].astype(str).str.lower().str.contains(s, na=False)
            | filt["last_name"].astype(str).str.lower().str.contains(s, na=False)
            | filt["code"].astype(str).str.lower().str.contains(s, na=False)
            | filt["opta_id"].astype(str).str.lower().str.contains(s, na=False)
        )
        filt = filt[mask].copy()

    # Legend for calculated & color-coded columns
    st.markdown(
        f"""
        <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; margin-bottom:8px;">
            <div style="font-size:0.80rem; color:#475569;">
                Atleti visualizzati: <b>{len(filt)}</b> su {len(players_df)} ({int((filt['department']=='Avanti').sum())} Avanti, {int((filt['department']=='TreQuarti').sum())} Trequarti)
                • <i>HSR Match: >18 km/h per Avanti, >20 km/h per Trequarti (normalizzati a 80', soglia min 30')</i>
            </div>
            <div style="display:flex; gap:8px; font-size:0.74rem; font-weight:700;">
                <span style="background:#FEF3C7; color:#B45309; border:1px solid #FDE68A; padding:2px 8px; border-radius:6px;">
                    ✏️ Valori Inseriti Manualmente
                </span>
                <span style="background:#E0F2FE; color:#0369A1; border:1px solid #BAE6FD; padding:2px 8px; border-radius:6px;">
                    ⚡ Auto (Squadra Oval / Vmax GPS)
                </span>
                <span style="background:#DCFCE7; color:#15803D; border:1px solid #BBF7D0; padding:2px 8px; border-radius:6px;">
                    Verde: Media Partite Giocatore (80')
                </span>
                <span style="background:#F1F5F9; color:#475569; border:1px solid #CBD5E1; padding:2px 8px; border-radius:6px;">
                    Grigio: Media del Ruolo (Fallback)
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    disp_cols = {
        "last_name": "Cognome",
        "first_name": "Nome",
        "name_display": "Nome e Cognome",
        "birth_year": "Anno",
        "role": "Ruolo",
        "club": "Squadra",
        "department": "Reparto",
        "code": "Sigla",
        "v_max": "V max (km/h)",
        "hml_avg_fir": "HML Avg FIR (m)",
        "hsr_avg_fir": "HSR Avg FIR (m)",
        "hml_avg_tot": "HML Avg Tot (m)",
        "hsr_avg_tot": "HSR Avg Tot (m)",
        "origine": "Origine Valori",
    }

    filt_reset = filt.reset_index(drop=True)
    if "manual_override" in filt_reset.columns:
        filt_reset["origine"] = filt_reset["manual_override"].apply(lambda m: "✏️ Manuale" if utils.is_truthy(m) else "⚡ Auto DB")
    else:
        filt_reset["origine"] = "⚡ Auto DB"
    out_df = filt_reset[[c for c in disp_cols.keys() if c in filt_reset.columns]].rename(columns=disp_cols)

    has_fir_flags = filt_reset["has_fir_matches"].tolist() if "has_fir_matches" in filt_reset.columns else [False] * len(out_df)
    has_tot_flags = filt_reset["has_tot_matches"].tolist() if "has_tot_matches" in filt_reset.columns else [False] * len(out_df)
    is_manual_flags = [utils.is_truthy(x) for x in filt_reset["manual_override"]] if "manual_override" in filt_reset.columns else [False] * len(out_df)

    def _style_roster_rows(row):
        idx = row.name
        styles = [""] * len(row)
        col_names = list(row.index)

        if "Origine Valori" in col_names:
            c_orig = col_names.index("Origine Valori")
            if idx < len(is_manual_flags) and is_manual_flags[idx]:
                styles[c_orig] = "background-color: #FEF3C7; color: #B45309; font-weight: 800;"
            else:
                styles[c_orig] = "background-color: #F0FDF4; color: #166534; font-weight: 700;"

        if "Squadra" in col_names and idx < len(is_manual_flags) and is_manual_flags[idx]:
            c_sq = col_names.index("Squadra")
            styles[c_sq] = "background-color: #FFFBEB; color: #B45309; font-weight: 700;"

        if "V max (km/h)" in col_names:
            c_i = col_names.index("V max (km/h)")
            styles[c_i] = "background-color: #E0F2FE; color: #0369A1; font-weight: 700;"

        fir_style = (
            "background-color: #DCFCE7; color: #15803D; font-weight: 700;"
            if has_fir_flags[idx]
            else "background-color: #FEF3C7; color: #B45309; font-style: italic;"
        )
        for cname in ("HML Avg FIR (m)", "HSR Avg FIR (m)"):
            if cname in col_names:
                styles[col_names.index(cname)] = fir_style

        tot_style = (
            "background-color: #DCFCE7; color: #15803D; font-weight: 700;"
            if has_tot_flags[idx]
            else "background-color: #FEF3C7; color: #B45309; font-style: italic;"
        )
        for cname in ("HML Avg Tot (m)", "HSR Avg Tot (m)"):
            if cname in col_names:
                styles[col_names.index(cname)] = tot_style

        return styles

    styled_df = out_df.style.apply(_style_roster_rows, axis=1).format(
        {
            "Anno": lambda v: f"{int(v)}" if pd.notna(v) else "",
            "V max (km/h)": "{:.2f}",
            "HML Avg FIR (m)": "{:.0f}",
            "HSR Avg FIR (m)": "{:.0f}",
            "HML Avg Tot (m)": "{:.0f}",
            "HSR Avg Tot (m)": "{:.0f}",
        },
        na_rep="--",
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True, height=560)


def _render_sub_gestione_gin(players_df: pd.DataFrame):
    """Sottopagina di Gestione Centralizzata della Lista G.I.N. (Gruppo di Interesse Nazionale) valida per tutto il portale."""
    if "gin_managed_names" not in st.session_state:
        st.session_state["gin_managed_names"] = set(utils.get_gin_player_names())
    if "gin_editor_counter" not in st.session_state:
        st.session_state["gin_editor_counter"] = 0

    current_gin_set = st.session_state["gin_managed_names"]
    total_roster = len(players_df)
    df_active = players_df[players_df["name_display"].isin(current_gin_set)]
    n_active = len(df_active)
    n_fw = int((df_active["department"] == "Avanti").sum())
    n_bk = int((df_active["department"] == "TreQuarti").sum())

    # Header Card FIR
    st.markdown(
        """
        <div style="background:linear-gradient(135deg, #031926 0%, #002B49 60%, #004B87 100%); border-radius:12px; padding:18px 22px; margin-bottom:16px; border-left:6px solid #D4AF37; color:#FFFFFF;">
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
                <div>
                    <div style="font-size:0.72rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">FEDERAZIONE ITALIANA RUGBY &bull; CONFIGURAZIONE NAZIONALE</div>
                    <h3 style="margin:2px 0 6px 0; color:#FFFFFF; font-size:1.35rem; font-weight:800;">🌟 Gestione Centralizzata Lista G.I.N. (Gruppo Interesse Nazionale)</h3>
                    <div style="font-size:0.84rem; color:#CBD5E1; max-width:850px; line-height:1.4;">
                        Gli atleti selezionati in questa pagina definiscono la <b>Lista G.I.N. globale</b> utilizzata in tutta la piattaforma: 
                        <b>Dossier Integrato Totale PDF</b>, <b>Report 6/12 Settimane</b>, <b>Analisi Partita Oval</b>, <b>Trombinoscopio Partita</b> e <b>Benchmark</b>.
                    </div>
                </div>
                <div style="text-align:right;">
                    <span style="background:#D4AF37; color:#031926; font-weight:800; padding:4px 12px; border-radius:999px; font-size:0.78rem;">
                        CONFIGURAZIONE GLOBALE PORTALE
                    </span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Indicatori KPI Roster & GIN
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Totale Roster Censito", f"{total_roster} atleti")
    k2.metric("Atleti G.I.N. Selezionati", f"{n_active} atleti", f"{(n_active/max(total_roster,1)*100):.1f}% del Roster")
    k3.metric("Avanti G.I.N.", f"{n_fw} avanti", "Piloni, Tallonatori, 2ª e 3ª Linea")
    k4.metric("TreQuarti G.I.N.", f"{n_bk} trequarti", "Mediani, Centri, Ali ed Estremi")

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Azioni Rapide di Selezione Massiva
    st.markdown("##### 👥 Azioni Rapide di Selezione Massiva")
    st.caption("Usa le azioni rapide per selezionare o deselezionare in blocco, oppure agisci sui singoli atleti nella tabella sottostante:")
    b1, b2, b3, b4, b5, b6, b7 = st.columns(7)

    if b1.button(f"✓ Seleziona Tutti ({total_roster})", use_container_width=True, key="gin_btn_sel_all"):
        st.session_state["gin_managed_names"] = set(players_df["name_display"].dropna().astype(str).tolist())
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b2.button("✕ Deseleziona Tutti", use_container_width=True, key="gin_btn_desel_all"):
        st.session_state["gin_managed_names"] = set()
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b3.button("Solo Avanti", use_container_width=True, key="gin_btn_fw", help="Seleziona solo gli Avanti e toglie la spunta ai TreQuarti"):
        st.session_state["gin_managed_names"] = set(players_df[players_df["department"] == "Avanti"]["name_display"].dropna().tolist())
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b4.button("Solo TreQuarti", use_container_width=True, key="gin_btn_bk", help="Seleziona solo i TreQuarti e toglie la spunta agli Avanti"):
        st.session_state["gin_managed_names"] = set(players_df[players_df["department"] == "TreQuarti"]["name_display"].dropna().tolist())
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b5.button("Solo Benetton", use_container_width=True, key="gin_btn_ben", help="Seleziona solo i tesserati Benetton Rugby"):
        st.session_state["gin_managed_names"] = set(players_df[players_df["club"].astype(str).str.lower().str.contains("benetton", na=False)]["name_display"].dropna().tolist())
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b6.button("Solo Zebre", use_container_width=True, key="gin_btn_zeb", help="Seleziona solo i tesserati Zebre Parma"):
        st.session_state["gin_managed_names"] = set(players_df[players_df["club"].astype(str).str.lower().str.contains("zebre", na=False)]["name_display"].dropna().tolist())
        st.session_state["gin_editor_counter"] += 1
        st.rerun()

    if b7.button("🔄 Ripristina Default (71)", use_container_width=True, key="gin_btn_reset_def", help="Ripristina la lista ufficiale dei 71 atleti G.I.N. FIR"):
        utils.reset_gin_to_default()
        st.session_state["gin_managed_names"] = set(utils.get_gin_player_names())
        st.session_state["gin_editor_counter"] += 1
        st.success("Lista G.I.N. ripristinata ai 71 atleti ufficiali FIR!")
        st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Filtri di visualizzazione tabella
    f_c1, f_c2, f_c3, f_c4 = st.columns([2.0, 1.2, 1.2, 1.2])
    search_q = f_c1.text_input("🔍 Cerca giocatore per nome, cognome, sigla o codice...", key="gin_search_inp")
    filter_dept = f_c2.selectbox("Filtro Reparto", ["Tutti i Reparti", "Avanti", "TreQuarti"], key="gin_flt_dept")
    clubs_list = ["Tutte le Squadre"] + sorted([str(c) for c in players_df["club"].dropna().unique() if str(c).strip()])
    filter_club = f_c3.selectbox("Filtro Squadra", clubs_list, key="gin_flt_club")
    filter_status = f_c4.selectbox("Filtro Stato G.I.N.", ["Tutti gli atleti", "Solo Inclusi G.I.N. (✓)", "Solo Esclusi (✕)"], key="gin_flt_status")

    # Applicazione filtri di visualizzazione
    filt_df = players_df.copy()
    if filter_dept != "Tutti i Reparti":
        filt_df = filt_df[filt_df["department"] == filter_dept]
    if filter_club != "Tutte le Squadre":
        filt_df = filt_df[filt_df["club"].astype(str) == filter_club]
    if search_q.strip():
        sq = search_q.strip().lower()
        mask = (
            filt_df["name_display"].astype(str).str.lower().str.contains(sq, na=False)
            | filt_df["last_name"].astype(str).str.lower().str.contains(sq, na=False)
            | filt_df["code"].astype(str).str.lower().str.contains(sq, na=False)
            | filt_df["opta_id"].astype(str).str.lower().str.contains(sq, na=False)
        )
        filt_df = filt_df[mask]

    # Flag inclusione GIN sincronizzato con lo stato di sessione
    current_sel = st.session_state["gin_managed_names"]
    filt_df["incluso_gin"] = filt_df["name_display"].apply(lambda n: str(n).strip() in current_sel)

    if filter_status == "Solo Inclusi G.I.N. (✓)":
        filt_df = filt_df[filt_df["incluso_gin"] == True]
    elif filter_status == "Solo Esclusi (✕)":
        filt_df = filt_df[filt_df["incluso_gin"] == False]

    # Tabella interattiva con checkbox di abilitazione/disabilitazione
    disp_cols = ["incluso_gin", "name_display", "role", "department", "club", "birth_year", "opta_id", "v_max"]
    for c in disp_cols:
        if c not in filt_df.columns:
            filt_df[c] = ""
    disp_table = filt_df[disp_cols].copy().rename(columns={
        "incluso_gin": "Incluso in G.I.N.",
        "name_display": "Nome e Cognome",
        "role": "Ruolo",
        "department": "Reparto",
        "club": "Squadra / Club",
        "birth_year": "Anno",
        "opta_id": "Codice Oval",
        "v_max": "V max (km/h)",
    })

    editor_key = f"gin_table_editor_{st.session_state['gin_editor_counter']}"
    edited_table = st.data_editor(
        disp_table,
        use_container_width=True,
        hide_index=True,
        height=480,
        disabled=["Nome e Cognome", "Ruolo", "Reparto", "Squadra / Club", "Anno", "Codice Oval", "V max (km/h)"],
        column_config={
            "Incluso in G.I.N.": st.column_config.CheckboxColumn("Incluso in G.I.N.", help="Spunta per includere l'atleta nella lista G.I.N.", default=False),
            "Nome e Cognome": st.column_config.TextColumn("Nome e Cognome", width="medium"),
            "Ruolo": st.column_config.TextColumn("Ruolo", width="medium"),
            "Reparto": st.column_config.TextColumn("Reparto", width="small"),
            "Squadra / Club": st.column_config.TextColumn("Squadra / Club", width="medium"),
            "Anno": st.column_config.TextColumn("Anno", width="small"),
            "Codice Oval": st.column_config.TextColumn("Codice Oval", width="small"),
            "V max (km/h)": st.column_config.NumberColumn("V max (km/h)", format="%.2f", width="small"),
        },
        key=editor_key,
    )

    # Aggiorna lo stato dei nomi selezionati in base alle modifiche utente nella tabella
    if edited_table is not None and not edited_table.empty:
        for _, row in edited_table.iterrows():
            pname = str(row["Nome e Cognome"]).strip()
            is_chk = bool(row["Incluso in G.I.N."])
            if is_chk and pname not in st.session_state["gin_managed_names"]:
                st.session_state["gin_managed_names"].add(pname)
            elif not is_chk and pname in st.session_state["gin_managed_names"]:
                st.session_state["gin_managed_names"].remove(pname)

    # Barra di Salvataggio
    disk_gin_names = set(utils.get_gin_player_names())
    has_unsaved = (st.session_state["gin_managed_names"] != disk_gin_names)

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    col_save, col_info = st.columns([1.6, 2.4])

    if col_save.button("💾 Salva Modifiche Lista G.I.N. per Tutto il Portale", type="primary", use_container_width=True, key="btn_save_gin_all"):
        selected_list = sorted(list(st.session_state["gin_managed_names"]))
        utils.save_gin_player_names(selected_list)
        st.cache_data.clear()
        st.success(f"✅ Lista G.I.N. salvata con successo nel database! {len(selected_list)} atleti attivi in tutti i moduli.")
        st.rerun()

    if has_unsaved:
        col_info.warning(f"⚠️ **Modifiche non salvate**: {len(st.session_state['gin_managed_names'])} atleti selezionati in sessione. Clicca sul pulsante a sinistra per applicarle a tutte le pagine.")
    else:
        col_info.success(f"✓ **Lista Sincronizzata**: {len(disk_gin_names)} atleti G.I.N. attualmente attivi nel database e in tutti i moduli.")


def _render_sub_roster(t: dict):
    players_df = utils.get_players_df()

    tab_anagrafica, tab_gin = st.tabs([
        "📋 Anagrafica & Parametri Roster",
        "🌟 Gestione Lista G.I.N. (Atleti Monitorati)",
    ])

    with tab_anagrafica:
        with st.expander("Aggiungi / Modifica Giocatore nel Roster Nazionale", expanded=False):
            _fragment_roster_editor(players_df)
        _fragment_roster_table(players_df)

    with tab_gin:
        _render_sub_gestione_gin(players_df)


# ==============================================================================
# 2. ATLETI IN RADUNO (CAMPS)
# ==============================================================================
@st.fragment
def _fragment_raduni_create_clone(camps_df: pd.DataFrame):
    t_new, t_clone = st.columns(2)
    with t_new:
        st.markdown("**Nuova Settimana di Raduno**")
        nc_comp = st.text_input("Competizione", value="Nations Championship 2026", key="nc_comp")
        nc_week = st.text_input("Nome Settimana", placeholder="Es. SUD AFRICA, PREPARAZIONE VERONA...", key="nc_week")
        nc_date = st.date_input("Data Inizio (Lunedì)", value=datetime.date.today(), key="nc_date")
        if st.button("+ Crea Settimana Raduno", type="primary", key="btn_create_camp"):
            if nc_week.strip():
                new_cid = utils.save_camp({"competition": nc_comp, "week_name": nc_week, "start_date": str(nc_date)})
                st.session_state["camp_sel_active"] = new_cid
                st.success("Nuovo raduno creato.")
                st.rerun()
            else:
                st.warning("Inserisci il Nome della Settimana.")
    with t_clone:
        st.markdown("**Clona / Copia Settimana Esistente**")
        if not camps_df.empty:
            c_opts = [int(x) for x in camps_df["id"].tolist()]
            c_lbls = {
                int(r["id"]): f"{r['start_date_str']} • {r['week_name']} ({r['competition']}) — {int(r.get('total_count') or 0)} atleti"
                for _, r in camps_df.iterrows()
            }
            if "clone_src_cid" not in st.session_state or st.session_state["clone_src_cid"] not in c_opts:
                with_players = camps_df[camps_df["total_count"].fillna(0).astype(int) > 0]
                st.session_state["clone_src_cid"] = int(with_players.iloc[0]["id"]) if not with_players.empty else c_opts[0]

            src_cid = st.selectbox(
                "Raduno Sorgente da Clonare",
                c_opts,
                format_func=lambda x: c_lbls.get(x, str(x)),
                key="clone_src_cid",
            )

            clone_mode = st.radio(
                "Destinazione Lista Convocati",
                ["Su Settimana Già Creata", "Crea Nuova Settimana"],
                horizontal=True,
                key="clone_target_mode",
            )

            if clone_mode == "Su Settimana Già Creata":
                dst_opts = [cid for cid in c_opts if cid != int(src_cid)]
                if not dst_opts:
                    st.info("Esiste una sola settimana registrata. Crea prima un'altra settimana oppure scegli 'Crea Nuova Settimana'.")
                else:
                    if "clone_dst_cid" not in st.session_state or st.session_state["clone_dst_cid"] not in dst_opts:
                        st.session_state["clone_dst_cid"] = dst_opts[0]
                    dst_cid = st.selectbox(
                        "Settimana di Destinazione (Già Creata)",
                        dst_opts,
                        format_func=lambda x: c_lbls.get(x, str(x)),
                        key="clone_dst_cid",
                    )
                    replace_existing = st.checkbox(
                        "Sostituisci eventuale lista già presente (se deselezionato aggiunge solo i mancanti)",
                        value=True,
                        key="clone_replace_existing",
                    )
                    if st.button("Clona Lista Convocati su Settimana Esistente", type="primary", key="btn_clone_to_existing"):
                        n_copied = utils.copy_camp_players_to_existing_camp(
                            src_cid,
                            dst_cid,
                            replace_existing=replace_existing,
                        )
                        st.session_state["camp_sel_active"] = dst_cid
                        st.success(f"Clonati {n_copied} convocati nella settimana selezionata!")
                        st.rerun()
            else:
                cl_comp = st.text_input("Nuova Competizione", value="Nations Championship 2026", key="cl_comp")
                cl_week = st.text_input("Nuovo Nome Settimana", placeholder="Es. FRANCIA...", key="cl_week")
                cl_date = st.date_input("Nuova Data Inizio", value=datetime.date.today(), key="cl_date")
                if st.button("Clona Lista Convocati in Nuova Settimana", type="primary", key="btn_clone_camp"):
                    new_cid = utils.copy_camp_to_new_week(src_cid, cl_comp, cl_week, str(cl_date))
                    if new_cid > 0:
                        st.session_state["camp_sel_active"] = new_cid
                    st.success("Nuova settimana creata e popolata con tutti i convocati.")
                    st.rerun()


def _fragment_raduni_manage(camps_df: pd.DataFrame, players_df: pd.DataFrame):
    # Ricarica sempre freschi dal database per evitare disallineamenti di cache o frammenti
    camps_df = utils.get_camps_df()
    players_df = utils.get_players_df()

    if "camp_flash_msg" in st.session_state:
        msg = st.session_state.pop("camp_flash_msg")
        st.success(msg)

    # Filters
    fc1, fc2, fc3 = st.columns([1.3, 1.3, 2.4])
    comps_avail = ["Tutte le Competizioni"] + sorted([str(c) for c in camps_df["competition"].dropna().unique() if str(c).strip()])
    sel_comp = fc1.selectbox("Filtro Competizione", comps_avail, key="camp_f_comp")
    q_week = fc2.text_input("Cerca Nome Settimana", placeholder="Es. IRLANDA, VERONA...", key="camp_f_week")

    c_filt = camps_df.copy()
    if sel_comp != "Tutte le Competizioni":
        c_filt = c_filt[c_filt["competition"] == sel_comp]
    if q_week.strip():
        c_filt = c_filt[c_filt["week_name"].astype(str).str.lower().str.contains(q_week.strip().lower(), na=False)]

    if c_filt.empty:
        st.warning("Nessun raduno corrisponde ai filtri.")
        return

    camp_ids = [int(x) for x in c_filt["id"].tolist()]
    if "camp_sel_active" in st.session_state and st.session_state["camp_sel_active"] not in camp_ids:
        st.session_state["camp_sel_active"] = camp_ids[0]
    camp_labels = {
        int(r["id"]): f"{r['start_date_str']} — {r['week_name']} [{r['competition']}] ({int(r.get('total_count') or 0)} atleti)"
        for _, r in c_filt.iterrows()
    }
    active_cid = fc3.selectbox("Seleziona Settimana Raduno Attiva", camp_ids, format_func=lambda x: camp_labels.get(x, str(x)), key="camp_sel_active")

    active_camp = c_filt[c_filt["id"] == active_cid].iloc[0]
    cp_df = utils.get_camp_players_df(active_cid)
    fw_df = cp_df[cp_df["department"] == "Avanti"].copy() if not cp_df.empty else pd.DataFrame()
    bk_df = cp_df[cp_df["department"] == "TreQuarti"].copy() if not cp_df.empty else pd.DataFrame()

    # Header Banner
    h_col1, h_col2 = st.columns([3.5, 1])
    h_col1.markdown(
        f"""
        <div class="fir-section-card" style="background: linear-gradient(90deg, #031926 0%, #002B49 100%); color:#FFFFFF; padding:16px 20px;">
            <div style="font-size:0.72rem; font-weight:700; color:#D4AF37; text-transform:uppercase;">
                {active_camp.get('competition', '')} • INIZIO SETTIMANA: {active_camp.get('start_date_str', '')}
            </div>
            <div style="font-size:1.3rem; font-weight:800; margin-top:2px;">{active_camp.get('week_name', '')}</div>
            <div style="font-size:0.82rem; color:#CBD5E1; margin-top:4px;">
                Convocati Totali: <b>{len(cp_df)}</b> &nbsp;|&nbsp;
                <span style="color:#38BDF8; font-weight:700;">{len(fw_df)} Avanti</span> &nbsp;|&nbsp;
                <span style="color:#FBBF24; font-weight:700;">{len(bk_df)} Trequarti</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with h_col2:
        if st.button("Elimina Raduno", key=f"del_camp_{active_cid}", use_container_width=True):
            utils.delete_camp(active_cid)
            st.session_state["camp_flash_msg"] = "Raduno eliminato con successo."
            st.rerun()

    # Two columns: Avanti vs Trequarti
    col_av, col_tq = st.columns(2)
    already_ids = set(cp_df["player_id"].dropna().astype(int).tolist()) if not cp_df.empty else set()

    with col_av:
        st.markdown(f"#### REPARTO AVANTI ({len(fw_df)})")
        avail_fw = players_df[(players_df["department"] == "Avanti") & (~players_df["id"].isin(already_ids))]
        a1, a2 = st.columns([3, 1])
        if not avail_fw.empty:
            fw_opts = avail_fw["id"].tolist()
            fw_map = {int(r["id"]): f"{r['name_display']} ({r['role']} - {r.get('club','')})" for _, r in avail_fw.iterrows()}
            add_fw_id = a1.selectbox("Aggiungi Avanti", fw_opts, format_func=lambda x: fw_map.get(x, str(x)), label_visibility="collapsed", key="sel_add_fw")
            if a2.button("+ Aggiungi", key="btn_add_fw", use_container_width=True, type="primary"):
                utils.add_player_to_camp(active_cid, add_fw_id)
                p_name_add = fw_map.get(int(add_fw_id), "Giocatore")
                st.session_state.pop("sel_add_fw", None)
                st.session_state["camp_flash_msg"] = f"✅ {p_name_add} aggiunto con successo al raduno!"
                st.rerun()
        if not fw_df.empty:
            st.dataframe(
                fw_df[["player_name", "role", "club", "v_max"]].rename(columns={"player_name": "Atleta", "role": "Ruolo", "club": "Squadra", "v_max": "V max"}),
                use_container_width=True,
                hide_index=True,
            )
            r1, r2 = st.columns([3, 1])
            rem_fw_opts = fw_df["id"].tolist()
            rem_fw_map = {int(r["id"]): str(r["player_name"]) for _, r in fw_df.iterrows()}
            rem_fw_id = r1.selectbox("Rimuovi Avanti", rem_fw_opts, format_func=lambda x: rem_fw_map.get(x, str(x)), label_visibility="collapsed", key="sel_rem_fw")
            if r2.button("Rimuovi", key="btn_rem_fw", use_container_width=True):
                utils.remove_player_from_camp(rem_fw_id, active_cid)
                st.session_state.pop("sel_rem_fw", None)
                st.session_state["camp_flash_msg"] = "🗑️ Giocatore rimosso con successo dal raduno."
                st.rerun()

    with col_tq:
        st.markdown(f"#### REPARTO TREQUARTI ({len(bk_df)})")
        avail_bk = players_df[(players_df["department"] == "TreQuarti") & (~players_df["id"].isin(already_ids))]
        b1, b2 = st.columns([3, 1])
        if not avail_bk.empty:
            bk_opts = avail_bk["id"].tolist()
            bk_map = {int(r["id"]): f"{r['name_display']} ({r['role']} - {r.get('club','')})" for _, r in avail_bk.iterrows()}
            add_bk_id = b1.selectbox("Aggiungi Trequarti", bk_opts, format_func=lambda x: bk_map.get(x, str(x)), label_visibility="collapsed", key="sel_add_bk")
            if b2.button("+ Aggiungi", key="btn_add_bk", use_container_width=True, type="primary"):
                utils.add_player_to_camp(active_cid, add_bk_id)
                p_name_add = bk_map.get(int(add_bk_id), "Giocatore")
                st.session_state.pop("sel_add_bk", None)
                st.session_state["camp_flash_msg"] = f"✅ {p_name_add} aggiunto con successo al raduno!"
                st.rerun()
        if not bk_df.empty:
            st.dataframe(
                bk_df[["player_name", "role", "club", "v_max"]].rename(columns={"player_name": "Atleta", "role": "Ruolo", "club": "Squadra", "v_max": "V max"}),
                use_container_width=True,
                hide_index=True,
            )
            rb1, rb2 = st.columns([3, 1])
            rem_bk_opts = bk_df["id"].tolist()
            rem_bk_map = {int(r["id"]): str(r["player_name"]) for _, r in bk_df.iterrows()}
            rem_bk_id = rb1.selectbox("Rimuovi Trequarti", rem_bk_opts, format_func=lambda x: rem_bk_map.get(x, str(x)), label_visibility="collapsed", key="sel_rem_bk")
            if rb2.button("Rimuovi", key="btn_rem_bk", use_container_width=True):
                utils.remove_player_from_camp(rem_bk_id, active_cid)
                st.session_state.pop("sel_rem_bk", None)
                st.session_state["camp_flash_msg"] = "🗑️ Giocatore rimosso con successo dal raduno."
                st.rerun()


def _render_sub_raduni(t: dict):
    camps_df = utils.get_camps_df()
    players_df = utils.get_players_df()

    with st.expander("Crea Nuova Settimana di Raduno o Clona Settimana Esistente", expanded=False):
        _fragment_raduni_create_clone(camps_df)

    if camps_df.empty:
        st.info("Nessun raduno registrato.")
        return

    _fragment_raduni_manage(camps_df, players_df)


# ==============================================================================
# 3. STORICO PARTITE
# ==============================================================================
@st.fragment
def _fragment_partite_editor():
    mc1, mc2, mc3, mc4, mc5 = st.columns([1.2, 1.5, 1.3, 1.5, 1])
    m_date = mc1.date_input("Data Match", value=datetime.date.today(), key="m_new_date")
    m_name = mc2.text_input("Partita (es. ITALIA - FRANCIA)", key="m_new_name")
    m_comp = mc3.text_input("Competizione (es. 6N 2026)", key="m_new_comp")
    m_lbl = mc4.text_input("Etichetta Completa", key="m_new_lbl")
    if mc5.button("+ Salva Match", type="primary", use_container_width=True, key="btn_save_match"):
        if m_name.strip():
            utils.save_match({"date": str(m_date), "match_name": m_name, "competition": m_comp, "full_label": m_lbl or f"{m_name} {m_comp}"})
            st.success("Partita registrata.")
            st.rerun()


@st.fragment
def _fragment_partite_table(matches_df: pd.DataFrame):
    s1, s2 = st.columns(2)
    q_m = s1.text_input("Cerca partita per avversario o torneo...", key="q_match_search")
    comps_m = ["Tutte le Competizioni"] + sorted([str(c) for c in matches_df["competition"].dropna().unique() if str(c).strip()])
    sel_mc = s2.selectbox("Filtro Competizione", comps_m, key="q_match_comp")

    m_filt = matches_df.copy()
    if sel_mc != "Tutte le Competizioni":
        m_filt = m_filt[m_filt["competition"] == sel_mc]
    if q_m.strip():
        s = q_m.strip().lower()
        m_filt = m_filt[
            m_filt["match_name"].astype(str).str.lower().str.contains(s, na=False)
            | m_filt["full_label"].astype(str).str.lower().str.contains(s, na=False)
        ]

    st.caption(f"Partite trovate: **{len(m_filt)}** su {len(matches_df)}")
    st.dataframe(
        m_filt[["date_str", "match_name", "competition", "full_label"]].rename(
            columns={"date_str": "Data", "match_name": "Partita", "competition": "Competizione", "full_label": "Etichetta Completa"}
        ),
        use_container_width=True,
        hide_index=True,
        height=460,
    )


def _render_sub_partite(t: dict):
    matches_df = utils.get_matches_df()

    c_sync1, c_sync2 = st.columns([1.6, 2.4])
    if c_sync1.button("⚡ Sincronizza Partite da Dati Oval Match", key="btn_sync_matches_oval", type="primary", use_container_width=True):
        n_m, n_l = utils.sync_oval_matches_and_lineups(force=True)
        st.success(f"Sincronizzate {n_m} partite da Dati Oval!")
        st.rerun()
    c_sync2.info("🏉 **Archivio Automatico:** Tutte le gare ufficiali della Nazionale Italiana sono estratte e sincronizzate direttamente dai dati Oval Match.")

    with st.expander("Inserisci / Modifica Partita Internazionale Manuale", expanded=False):
        _fragment_partite_editor()

    _fragment_partite_table(matches_df)


# ==============================================================================
# 4. FORMAZIONE MATCH (1-23 & NON CONVOCATI)
# ==============================================================================
@st.fragment
def _fragment_lineup_editor(sel_date: str, detail: dict, players_df: pd.DataFrame, lineup_summary: pd.DataFrame):
    # Compilazione Rapida / Clona da Partita Precedente
    src_candidates = lineup_summary[
        (lineup_summary["date_str"] != sel_date)
        & ((lineup_summary["starters_count"] + lineup_summary["finishers_count"]) > 0)
    ].copy()
    if not src_candidates.empty:
        st.markdown(
            """
            <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-radius:8px; padding:10px 14px; margin-bottom:12px;">
                <div style="font-size:0.82rem; font-weight:800; color:#1E3A8A;">⚡ Compilazione Rapida 1–23 da Partita Precedente</div>
                <div style="font-size:0.74rem; color:#475569;">Seleziona una gara precedente per copiarne i 23 convocati (1–15 Titolari e 16–23 Finishers) nella gara corrente e modificare solo i cambi.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        qc1, qc2 = st.columns([2.6, 1.4])
        src_dates = src_candidates["date_str"].tolist()
        src_lbl_map = {
            str(r["date_str"]): f"{r['date_str']} — {r['match_name']} ({int(r['starters_count']) + int(r['finishers_count'])} a referto)"
            for _, r in src_candidates.iterrows()
        }
        clone_src_dt = qc1.selectbox(
            "Partita Sorgente da cui Clonare i 23",
            src_dates,
            format_func=lambda d: src_lbl_map.get(str(d), str(d)),
            key=f"lineup_clone_src_{sel_date}",
            label_visibility="collapsed",
        )
        if qc2.button("📋 Clona Formazione 1-23 qui", type="primary", use_container_width=True, key=f"btn_clone_lineup_{sel_date}"):
            n_cloned = utils.clone_match_lineup(clone_src_dt, sel_date, detail.get("match_name", ""))
            # Aggiorna anche lo stato dei 23 selectbox per riflettere subito i nuovi nomi
            new_dtl = utils.get_match_lineup_detail(sel_date)
            new_map = {}
            for df_p in (new_dtl["starters"], new_dtl["finishers"]):
                if not df_p.empty:
                    for _, r in df_p.iterrows():
                        new_map[int(r["jersey_number"])] = str(r["player_name"])
            for j_num in range(1, 24):
                st.session_state[f"ed_j_{sel_date}_{j_num}"] = new_map.get(j_num, "")
            st.success(f"Clonati {n_cloned} giocatori nella formazione del {sel_date}!")
            st.rerun()

    current_map = {}
    for df_p in (detail["starters"], detail["finishers"]):
        if not df_p.empty:
            for _, r in df_p.iterrows():
                current_map[int(r["jersey_number"])] = str(r["player_name"])

    all_player_names = [""] + sorted(players_df["name_display"].dropna().unique().tolist())
    p_roster_role_map = dict(zip(players_df["name_display"].astype(str).str.upper(), players_df["role"])) if not players_df.empty else {}
    e_col1, e_col2 = st.columns(2)
    new_entries = []
    for j_num in range(1, 24):
        pos_label, pos_role, is_st, _, _ = JERSEY_POSITIONS_1_23[j_num]
        display_label = pos_label if is_st else f"Maglia {j_num} (Panchina / Finisher)"
        target_col = e_col1 if is_st else e_col2
        cur_val = current_map.get(j_num, "")
        if cur_val and cur_val not in all_player_names:
            all_player_names.append(cur_val)
        idx_val = all_player_names.index(cur_val) if cur_val in all_player_names else 0
        chosen_p = target_col.selectbox(display_label, all_player_names, index=idx_val, key=f"ed_j_{sel_date}_{j_num}")
        if chosen_p:
            # Per i titolari (1-15) il ruolo è quello della maglia; per la panchina (16-23) è il ruolo ufficiale da Roster
            assigned_role = pos_role if is_st else (p_roster_role_map.get(str(chosen_p).strip().upper()) or pos_role)
            new_entries.append({"jersey_number": j_num, "player_name": chosen_p, "role": assigned_role})

    if st.button("💾 Salva Formazione 1-23", type="primary", key=f"btn_save_lineup_{sel_date}"):
        utils.save_match_lineup(sel_date, detail["match_name"], new_entries, old_date_str=sel_date)
        st.success("Formazione 1-23 aggiornata con successo.")
        st.rerun()


def _render_sub_formazioni(t: dict):
    c_sync1, c_sync2 = st.columns([1.6, 2.4])
    if c_sync1.button("⚡ Sincronizza Formazioni 1-23 da Dati Oval", key="btn_sync_lineups_oval", type="primary", use_container_width=True):
        n_m, n_l = utils.sync_oval_matches_and_lineups(force=True)
        st.success(f"Sincronizzate {n_l} formazioni ufficiali (Maglie 1-23) da Dati Oval Match!")
        st.rerun()
    c_sync2.info("📋 **Formazioni 1-23 Automatiche:** Le formazioni ufficiali (1-15 Titolari, 16-23 Finishers) sono ricavate in automatico dai dati Oval Match o clonabili con 1 click da una gara precedente.")

    lineup_summary = utils.get_lineup_matches_summary()
    players_df = utils.get_players_df()

    if lineup_summary.empty:
        st.info("Nessuna formazione presente.")
        return

    lineup_summary["label"] = (
        lineup_summary["date_str"]
        + " — "
        + lineup_summary["match_name"]
        + " ("
        + lineup_summary["starters_count"].astype(str)
        + " Titolari, "
        + lineup_summary["finishers_count"].astype(str)
        + " Finishers)"
    )

    c_sel, c_info = st.columns([2.2, 1.8])
    sel_lbl = c_sel.selectbox("Seleziona Partita per Formazione (1-23)", lineup_summary["label"].tolist(), index=0, key="lineup_sel_match")
    sel_date = lineup_summary[lineup_summary["label"] == sel_lbl].iloc[0]["date_str"]

    detail = utils.get_match_lineup_detail(sel_date)
    camp_assoc = detail.get("camp_associated")
    n_camp_tot = len(detail.get("all_camp_players", pd.DataFrame()))
    n_conv_tot = len(detail["starters"]) + len(detail["finishers"])
    n_excl_tot = len(detail["non_convocati"])
    if camp_assoc:
        c_info.info(
            f"Raduno della settimana: **{camp_assoc['week_name']}** ({camp_assoc['competition']} • inizio {camp_assoc['start_date']}) — "
            f"**{n_camp_tot} in raduno** − **{n_conv_tot} convocati** = **{n_excl_tot} esclusi**"
        )
    else:
        c_info.caption("Nessun raduno trovato nella settimana del match.")

    # Editor 1-23 inside Expander
    with st.expander("Modifica o Clona Formazione Ufficiale (Maglie 1 - 23)", expanded=False):
        _fragment_lineup_editor(sel_date, detail, players_df, lineup_summary)

    col_st, col_fn = st.columns([1.8, 1.4])
    with col_st:
        st.markdown("#### TITOLARI / STARTERS (Maglie 1 - 15)")
        st_df = detail["starters"]
        if not st_df.empty:
            st.dataframe(
                st_df[["jersey_number", "player_name", "role", "club", "v_max"]].rename(
                    columns={"jersey_number": "N°", "player_name": "Giocatore", "role": "Ruolo", "club": "Squadra", "v_max": "V max"}
                ),
                use_container_width=True,
                hide_index=True,
                height=560,
            )

    with col_fn:
        st.markdown("#### FINISHERS / PANCHINA (Maglie 16 - 23)")
        fn_df = detail["finishers"]
        if not fn_df.empty:
            st.dataframe(
                fn_df[["jersey_number", "player_name", "role", "club"]].rename(
                    columns={"jersey_number": "N°", "player_name": "Giocatore", "role": "Ruolo", "club": "Squadra"}
                ),
                use_container_width=True,
                hide_index=True,
            )

        nc_df = detail["non_convocati"]
        st.markdown(f"#### ESCLUSI DAI 23 / NON CONVOCATI ({len(nc_df)})")
        if not nc_df.empty:
            st.dataframe(
                nc_df[["player_name", "role", "department", "club"]].rename(
                    columns={"player_name": "Giocatore", "role": "Ruolo", "department": "Reparto", "club": "Squadra"}
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Nessun atleta fuori lista 1-23 nel raduno della settimana.")


# ==============================================================================
# 5. ASSEGNAZIONE TIPOLOGIE SESSIONI FIR
# ==============================================================================
@st.fragment
def _fragment_batch_typologies(sess_df: pd.DataFrame):
    c_b1, c_b2, c_b3 = st.columns([2.0, 1.5, 1.2])
    kw = c_b1.text_input("Se il nome sessione contiene la parola:", placeholder="Es: velocit, volume, clarity, match...")
    new_typ = c_b2.selectbox("Assegna Tipologia:", utils.FIR_SESSION_TYPOLOGIES, key="batch_typ_sel")
    if c_b3.button("Applica a Tutte", type="primary", use_container_width=True, key="btn_apply_batch_typ"):
        if kw.strip():
            types_map = utils.get_fir_session_types()
            matched = 0
            for _, r in sess_df.iterrows():
                if kw.strip().lower() in str(r["session_name"]).lower():
                    key = f"{r['date_str']}_{r['session_name']}"
                    types_map[key] = new_typ
                    matched += 1
            utils.save_fir_session_types(types_map)
            st.success(f"Aggiornate con successo {matched} sessioni con tipologia '{new_typ}'!")
            st.rerun()
        else:
            st.warning("Inserisci una parola chiave da cercare.")


@st.fragment
def _fragment_typologies_table(sess_df: pd.DataFrame):
    # Filtri di ricerca tabella
    f_col1, f_col2, f_col3 = st.columns([2.0, 1.5, 1.2])
    search_q = f_col1.text_input("🔍 Cerca per Nome Seduta o Data:", placeholder="Es: 261105, Volume, Scozia...")
    filter_typ = f_col2.selectbox("Filtra per Tipologia:", ["Tutte"] + utils.FIR_SESSION_TYPOLOGIES)

    filtered_df = sess_df.copy()
    if search_q.strip():
        q_low = search_q.strip().lower()
        filtered_df = filtered_df[
            filtered_df["session_name"].astype(str).str.lower().str.contains(q_low)
            | filtered_df["date_str"].astype(str).str.contains(q_low)
        ]
    if filter_typ != "Tutte":
        filtered_df = filtered_df[filtered_df["assigned_type"] == filter_typ]

    st.markdown(f"**Sessioni visualizzate ({len(filtered_df)} di {len(sess_df)})** — *Modifica la colonna 'Tipologia Assegnata' e clicca su Salva Modifiche:*")

    # Data Editor interattivo
    edited_df = st.data_editor(
        filtered_df,
        column_config={
            "date_str": st.column_config.TextColumn("Data Seduta", disabled=True, width="medium"),
            "session_name": st.column_config.TextColumn("Nome Sessione GPS", disabled=True, width="large"),
            "players_count": st.column_config.NumberColumn("Atleti Monitorati", disabled=True, width="small"),
            "assigned_type": st.column_config.SelectboxColumn(
                "Tipologia Assegnata",
                options=utils.FIR_SESSION_TYPOLOGIES,
                required=True,
                width="large",
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="data_editor_fir_session_types",
    )

    if st.button("💾 Salva Modifiche Tipologie Sessioni", type="primary", use_container_width=True, key="btn_save_all_session_types"):
        types_map = utils.get_fir_session_types()
        count_updated = 0
        for _, r in edited_df.iterrows():
            key = f"{r['date_str']}_{r['session_name']}"
            if types_map.get(key) != r["assigned_type"]:
                types_map[key] = r["assigned_type"]
                count_updated += 1
        utils.save_fir_session_types(types_map)
        st.success(f"Salvataggio completato! {count_updated} tipologie aggiornate persistentemente nel database.")
        st.rerun()


def _render_sub_tipologie_sessioni(t: dict):
    st.markdown("### Elenco e Assegnazione Tipologie Sessioni FIR (Nazionale)")
    st.caption("Assegna o modifica la tipologia (Volume, Velocità, Rugby, Team run, Clarity, Reparto, Extra, Lavoro fisico, Match, RTP) per ciascuna seduta FIR.")

    sess_df = utils.get_all_fir_unique_sessions()
    if sess_df.empty:
        st.info("Nessuna sessione GPS della Nazionale Italiana presente nel database.")
        return

    # Indicatori di sintesi per le 10 categorie
    type_counts = sess_df["assigned_type"].value_counts()
    
    r1_cols = st.columns(5)
    r1_cols[0].metric("1. Volume", int(type_counts.get("Volume", 0)))
    r1_cols[1].metric("2. Velocità", int(type_counts.get("Velocità", 0)))
    r1_cols[2].metric("3. Rugby", int(type_counts.get("Rugby", 0)))
    r1_cols[3].metric("4. Team run", int(type_counts.get("Team run", 0)))
    r1_cols[4].metric("5. Clarity", int(type_counts.get("Clarity", 0)))

    r2_cols = st.columns(5)
    r2_cols[0].metric("6. Reparto", int(type_counts.get("Reparto", 0)))
    r2_cols[1].metric("7. Extra", int(type_counts.get("Extra", 0)))
    r2_cols[2].metric("8. Lavoro fisico", int(type_counts.get("Lavoro fisico", 0)))
    r2_cols[3].metric("9. Match", int(type_counts.get("Match", 0)))
    r2_cols[4].metric("10. RTP", int(type_counts.get("RTP", 0)))

    st.markdown("---")

    # Sezione Assegnazione Rapida di Gruppo (Batch)
    with st.expander("⚡ Assegnazione Rapida in Massa (per parola chiave)", expanded=False):
        _fragment_batch_typologies(sess_df)

    _fragment_typologies_table(sess_df)
