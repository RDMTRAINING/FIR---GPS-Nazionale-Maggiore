import datetime
import streamlit as st
import pandas as pd
from config import render_page_header, render_tab_navigation, render_navigation_cards, FIR_COLUMNS_META, FIR_COL_LABELS
import utils
import views.oval_match


def render_storico_gps(t: dict):
    counts = utils.get_history_team_counts()

    render_page_header(
        "Storico Dati GPS & Archivio Oval FIR",
        f"Database unificato FIR ({counts['total']:,} record attivi • Nazionale: {counts['nazionale']:,} | Benetton: {counts['benetton']:,} | Zebre: {counts['zebre']:,})",
        "bi-database-check",
    )

    cards_storico = [
        {"id": "nazionale", "title": "Dati Nazionale Italiana", "desc": f"Archivio GPS Nazionale Maggiore ({counts['nazionale']:,} righe)", "icon": "bi-shield-fill"},
        {"id": "benetton", "title": "Dati Benetton Treviso", "desc": f"Archivio GPS Club Benetton Rugby ({counts['benetton']:,} righe)", "icon": "bi-building"},
        {"id": "zebre", "title": "Dati Zebre Parma", "desc": f"Archivio GPS Club Zebre Parma ({counts['zebre']:,} righe)", "icon": "bi-building"},
        {"id": "all", "title": "Dati GPS Totali", "desc": f"Database combinato FIR + Franchigie ({counts['total']:,} righe)", "icon": "bi-globe"},
        {"id": "archivio_oval", "title": "Archivio Oval", "desc": "Database gare ufficiali Oval con minutaggi e match stats", "icon": "bi-table"},
    ]

    active_team = render_navigation_cards("storico_gps", cards_storico)

    if active_team == "archivio_oval":
        ov_df = utils.get_oval_matches_df()
        views.oval_match._render_tab_archivio(ov_df)
        return

    # Manual Insert / Edit Expander (Zero Required Fields)
    with st.expander("Inserimento Manuale o Modifica Record GPS (Colonne D - AY • Nessun Campo Obbligatorio)", expanded=False):
        _render_manual_record_form(active_team if active_team != "all" else "nazionale")

    df = utils.get_gps_history_df(active_team)

    if df.empty:
        if active_team in ("benetton", "zebre"):
            st.info(
                f"La partizione **{active_team.upper()}** è attualmente vuota (0 record) come richiesto per evitare dati impaginati erroneamente. "
                "Vai nella pagina **Importa & Mapping Dati Club** per configurare la mappatura colonne dedicata e importare i dati corretti."
            )
        else:
            st.info("Nessun record GPS presente in questa vista.")
        return

    # Filter bar
    f1, f2, f3, f4, f5 = st.columns([1.8, 1.1, 1.1, 1.1, 1.3])
    q_search = f1.text_input("Cerca (Atleta, Seduta, Sigla)", placeholder="Es. Lamaro, Garbisi, Backs...", key=f"hist_q_{active_team}")
    roles_avail = ["Tutti i Ruoli"] + sorted([str(r) for r in df["role"].dropna().unique() if str(r).strip()])
    sel_role = f2.selectbox("Filtro Ruolo", roles_avail, key=f"hist_role_{active_team}")
    d_from = f3.date_input("Data Da", value=None, key=f"hist_dfrom_{active_team}")
    d_to = f4.date_input("Data A", value=None, key=f"hist_dto_{active_team}")
    col_view_mode = f5.selectbox(
        "Vista Colonne",
        [
            "Tutte le Colonne (D - AY)",
            "Sintesi Key KPIs",
            "Potenza Metabolica (MP & A.I.)",
            "Velocità, Azioni & Acc",
            "Contatti, RHIE, Jump & CoD",
        ],
        key=f"hist_viewmode_{active_team}",
    )

    filt = df.copy()
    if sel_role != "Tutti i Ruoli":
        filt = filt[filt["role"].astype(str) == sel_role]
    if d_from is not None:
        filt = filt[filt["date_str"] >= str(d_from)[:10]]
    if d_to is not None:
        filt = filt[filt["date_str"] <= str(d_to)[:10]]
    if q_search.strip():
        s = q_search.strip().lower()
        filt = filt[
            filt["player_name"].astype(str).str.lower().str.contains(s, na=False)
            | filt["session_name"].astype(str).str.lower().str.contains(s, na=False)
            | filt["sigla"].astype(str).str.lower().str.contains(s, na=False)
        ]

    # Column selection by view mode
    base_cols = ["id", "team_name", "player_name", "sigla", "session_name", "date_str", "day_name", "role", "period"]
    if col_view_mode == "Sintesi Key KPIs":
        metric_cols = ["duration", "distance_m", "m_per_min", "mp_25_35", "mp_35_50", "mp_50_100", "v_max", "v_max_pct", "speed_20_25", "speed_25_72", "acc_volume", "contacts", "player_load_total"]
    elif col_view_mode == "Potenza Metabolica (MP & A.I.)":
        metric_cols = ["duration", "distance_m", "m_per_min", "mp_0_12", "mp_12_20", "mp_20_25", "mp_25_35", "mp_35_50", "mp_50_100", "ai_12_20", "ai_20_25", "ai_25_40", "ai_40_50", "ai_50_100"]
    elif col_view_mode == "Velocità, Azioni & Acc":
        metric_cols = ["profile_max_vel", "v_max", "v_max_pct", "speed_0_6", "speed_6_15", "speed_15_18", "speed_18_20", "speed_20_25", "speed_25_72", "actions_gt_6", "actions_gt_15", "actions_gt_18", "actions_gt_20", "actions_gt_25", "acc_volume", "acc_density_time", "acc_density_space"]
    elif col_view_mode == "Contatti, RHIE, Jump & CoD":
        metric_cols = ["contacts", "rhie_avg_recovery", "rhie_total", "jump_20_40", "jump_gt_40", "cod_right", "cod_left", "player_load_total", "actions_gt_70", "actions_gt_85"]
    else:
        metric_cols = [c[0] for c in FIR_COLUMNS_META if c[0] not in base_cols and c[0] != "date"]

    show_cols = [c for c in base_cols + metric_cols if c in filt.columns]
    rename_map = {"id": "ID", "team_name": "Squadra", "date_str": "G: Data"}
    rename_map.update(FIR_COL_LABELS)

    top_bar1, top_bar2, top_bar3 = st.columns([2.0, 1.4, 1.4])
    max_rows = top_bar2.selectbox("Righe mostrate a schermo", [100, 250, 500, 1500, 7000], index=1, key=f"hist_limit_{active_team}")
    top_bar1.caption(f"Record filtrati: **{len(filt):,}** (visualizzati i primi {min(len(filt), max_rows):,}) • Spunta **🗑️ Sel** per eliminare più tracce")

    csv_bytes = filt[show_cols].rename(columns=rename_map).to_csv(index=False).encode("utf-8")
    top_bar3.download_button(
        "Esporta Vista in CSV",
        data=csv_bytes,
        file_name=f"fir_gps_history_{active_team}.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"dl_csv_{active_team}",
    )

    is_admin = st.session_state.get("user_role") == "admin"

    # Tabella Interattiva con Colonna Selezione Checkbox (🗑️ Sel) per eliminazione multipla rapida
    disp_df = filt.head(max_rows)[show_cols].rename(columns=rename_map).copy()
    if is_admin:
        disp_df.insert(0, "🗑️ Sel", False)
        edited_df = st.data_editor(
            disp_df,
            column_config={
                "🗑️ Sel": st.column_config.CheckboxColumn(
                    "🗑️ Sel",
                    help="Spunta questa casella per selezionare la traccia da eliminare",
                    default=False,
                )
            },
            disabled=[c for c in disp_df.columns if c != "🗑️ Sel"],
            hide_index=True,
            use_container_width=True,
            height=560,
            key=f"editor_hist_{active_team}",
        )

        # Se ci sono righe selezionate con la checkbox, mostra il pulsante di eliminazione immediata
        selected_rows = edited_df[edited_df["🗑️ Sel"] == True]
        if not selected_rows.empty:
            sel_cnt = len(selected_rows)
            sel_ids = selected_rows["ID"].tolist()
            st.error(
                f"⚠️ **{sel_cnt} tracce GPS selezionate** nella tabella sottostante. "
                f"Puoi eliminarle tutte in blocco con un solo clic."
            )
            c_act1, c_act2 = st.columns([2.5, 1.5])
            if c_act1.button(
                f"🗑️ ELIMINA DEFINITIVAMENTE LE {sel_cnt} TRACCE SELEZIONATE",
                type="primary",
                use_container_width=True,
                key=f"btn_del_batch_{active_team}",
            ):
                del_count = utils.delete_gps_history_records_by_ids(sel_ids)
                st.success(f"✅ {del_count} tracce GPS eliminate con successo dall'archivio!")
                st.balloons()
                st.rerun()
            if c_act2.button("Deseleziona Tutto", use_container_width=True, key=f"btn_reset_sel_{active_team}"):
                st.rerun()
    else:
        st.dataframe(disp_df, use_container_width=True, hide_index=True, height=560)

    # Sezione Eliminazione Rapida Avanzata (Per Intera Seduta / Per Filtro / Singolo ID)
    if is_admin:
        with st.expander("⚡ Strumenti di Eliminazione Rapida in Blocco (Intera Seduta / Tracce Filtrate / ID)", expanded=False):
            tab_del_sess, tab_del_filt, tab_del_single = st.tabs([
                "1. Elimina Intera Seduta (1-Clic)",
                f"2. Elimina Tutte le Tracce Filtrate ({len(filt):,})",
                "3. Elimina Singolo Record tramite ID",
            ])

            with tab_del_sess:
                st.caption("Seleziona una data e seduta per cancellare con un solo clic tutte le registrazioni GPS associate (es. caricamento errato o duplicato).")
                sess_groups = filt.groupby(["date_str", "session_name"]).size().reset_index(name="tracce")
                sess_opts = [
                    f"{r['date_str']} | {r['session_name']} ({r['tracce']} tracce)"
                    for _, r in sess_groups.iterrows()
                ]
                if sess_opts:
                    c_s1, c_s2 = st.columns([2.4, 1.6])
                    chosen_sess_str = c_s1.selectbox("Seleziona Seduta da Eliminare", sess_opts, key=f"sel_purge_sess_{active_team}")
                    idx_chosen = sess_opts.index(chosen_sess_str)
                    target_row = sess_groups.iloc[idx_chosen]
                    t_date = str(target_row["date_str"])
                    t_sess = str(target_row["session_name"])
                    n_tracce = int(target_row["tracce"])

                    if c_s2.button(
                        f"🗑️ Elimina Tutta la Seduta ({n_tracce} tracce)",
                        type="primary",
                        use_container_width=True,
                        key=f"btn_purge_sess_{active_team}",
                    ):
                        d_cnt = utils.delete_gps_history_session(t_date, t_sess, team_type=active_team)
                        st.success(f"✅ Eliminata la seduta '{t_sess}' del {t_date}: {d_cnt} tracce rimosse dall'archivio!")
                        st.balloons()
                        st.rerun()
                else:
                    st.info("Nessuna seduta identificata nei filtri correnti.")

            with tab_del_filt:
                st.caption(f"Elimina in blocco tutti i **{len(filt):,} record** attualmente corrispondenti ai filtri impostati sopra.")
                c_f1, c_f2 = st.columns([2.2, 1.8])
                chk_confirm_filt = c_f1.checkbox(
                    f"Confermo di voler eliminare definitivamente TUTTI i {len(filt):,} record filtrati",
                    key=f"chk_conf_filt_{active_team}",
                )
                if c_f2.button(
                    f"🗑️ Elimina i {len(filt):,} Record Filtrati",
                    type="primary",
                    disabled=not chk_confirm_filt,
                    use_container_width=True,
                    key=f"btn_purge_filt_{active_team}",
                ):
                    f_ids = filt["id"].tolist()
                    del_cnt = utils.delete_gps_history_records_by_ids(f_ids)
                    st.success(f"✅ {del_cnt} record GPS eliminati dall'archivio!")
                    st.balloons()
                    st.rerun()

            with tab_del_single:
                d1, d2 = st.columns([2, 1])
                del_id = d1.number_input("Inserisci ID del Record da eliminare", min_value=1, step=1, key=f"del_hist_id_{active_team}")
                if d2.button("Elimina Record ID", key=f"btn_del_hist_{active_team}"):
                    utils.delete_gps_history_record(int(del_id))
                    st.success(f"Record #{int(del_id)} eliminato.")
                    st.rerun()


def _render_manual_record_form(default_team: str):
    players_df = utils.get_players_df()
    roster_names = sorted(players_df["name_display"].dropna().unique().tolist()) if not players_df.empty else []

    c1, c2, c3, c4 = st.columns([1.2, 1.8, 1.5, 1.2])
    t_opts = ["nazionale", "benetton", "zebre", "altro"]
    t_idx = t_opts.index(default_team) if default_team in t_opts else 0
    f_team = c1.selectbox("Squadra Destinazione", t_opts, index=t_idx, key="man_team")
    sel_player = c2.selectbox("D: Giocatore (Roster)", roster_names, key="man_player_sel")
    f_sess = c3.text_input("F: Seduta (z)", value="Allenamento Squadra", key="man_sess")
    f_date = c4.date_input("G: Data Seduta", value=datetime.date.today(), key="man_date")

    m1, m2, m3, m4, m5, m6, m7 = st.columns([1.1, 1.2, 1.0, 1.2, 1.1, 1.1, 1.1])
    f_dur = m1.number_input("Durata (min)", min_value=0.0, value=60.0, step=1.0, key="man_dur")
    f_dist = m2.number_input("Distanza (m)", min_value=0.0, value=4500.0, step=50.0, key="man_dist")
    mmin_calc = round(f_dist / f_dur, 1) if f_dur > 0 else 0.0
    m3.metric("m/min (Ricavato)", f"{mmin_calc}")
    f_hml = m4.number_input("HML >25.5W (m)", min_value=0.0, value=500.0, step=10.0, key="man_hml")
    f_hsr18 = m5.number_input("HSR >18 (m)", min_value=0.0, value=250.0, step=10.0, key="man_hsr18")
    f_hsr20 = m6.number_input("HSR >20 (m)", min_value=0.0, value=150.0, step=10.0, key="man_hsr20")
    f_vmax = m7.number_input("V max (km/h)", min_value=0.0, value=28.5, step=0.1, key="man_vmax")

    if st.button("+ Salva Record Manuale nel Database", type="primary", key="btn_save_man_hist"):
        ident = utils.resolve_player_identity(sel_player)
        p_role = ident.get("role") or "Avanti"
        p_sigla = ident.get("code") or ident.get("sigla") or ""
        giorni_ita = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        day_name = giorni_ita[f_date.weekday()]

        rec = {
            "team_type": f_team,
            "player_name": sel_player,
            "sigla": p_sigla,
            "session_name": f_sess,
            "date": str(f_date),
            "day_name": day_name,
            "role": p_role,
            "period": "session",
            "duration": f_dur,
            "distance_m": f_dist,
            "m_per_min": mmin_calc,
            "v_max": f_vmax,
            "mp_25_35": f_hml,
            "speed_18_20": f_hsr18,
            "speed_20_25": f_hsr20,
            "player_load_total": round(f_dist * 0.015, 1),
        }
        new_id = utils.save_gps_history_record(rec)
        st.success(f"Record #{new_id} per {sel_player} salvato con successo.")
        st.rerun()
