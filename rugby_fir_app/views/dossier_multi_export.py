import streamlit as st
import pandas as pd
import numpy as np
import utils
try:
    from config import ROLE_TO_DEPT
except ImportError:
    from rugby_fir_app.config import ROLE_TO_DEPT
from pdf_generator import crea_pdf_dossier_multi_giocatore


def _get_available_weeks_options():
    all_gps = utils.get_gps_history_df("all")
    if all_gps.empty or "date_str" not in all_gps.columns:
        import datetime
        _today = pd.to_datetime(datetime.date.today())
        _mon = _today - pd.Timedelta(days=_today.weekday())
        return [(_mon.strftime("%Y-%m-%d"), f"{_mon.strftime('%d/%m/%y')} — {(_mon + pd.Timedelta(days=6)).strftime('%d/%m/%y')}")], 0

    dates = pd.to_datetime(all_gps["date_str"].dropna().unique())
    if len(dates) == 0:
        import datetime
        _today = pd.to_datetime(datetime.date.today())
        _mon = _today - pd.Timedelta(days=_today.weekday())
        return [(_mon.strftime("%Y-%m-%d"), f"{_mon.strftime('%d/%m/%y')} — {(_mon + pd.Timedelta(days=6)).strftime('%d/%m/%y')}")], 0

    camps_df = utils.get_camps_df()
    camp_dates = pd.to_datetime(camps_df["start_date"].dropna().unique()) if not camps_df.empty else pd.DatetimeIndex([])
    all_dates = dates.union(camp_dates) if len(dates) > 0 else camp_dates
    mondays = sorted(list(set(d - pd.Timedelta(days=d.weekday()) for d in all_dates)), reverse=True)
    options = []
    default_idx = 0
    for idx, mon in enumerate(mondays):
        sun = mon + pd.Timedelta(days=6)
        mon_str = mon.strftime("%Y-%m-%d")
        lbl = f"{mon.strftime('%d/%m/%y')} — {sun.strftime('%d/%m/%y')}"
        if mon_str == "2026-10-19":
            default_idx = idx
        options.append((mon_str, lbl))

    return options, default_idx


def render_dossier_multi_export(t: dict = None):
    st.markdown("### 📑 Esportazione Dossier Multi-Giocatore (Lista G.I.N.)")
    st.caption(
        "Strumento di esportazione batch per la compilazione di fascicoli PDF multi-pagina destinati allo staff tecnico e agli allenatori. "
        "Di default sono preselezionati tutti gli atleti della Lista G.I.N. Ufficiale FIR: usa i pulsanti di filtro o deseleziona manualmente i giocatori che non desideri includere nel fascicolo."
    )

    # 1. Caricamento dati e roster
    gin_names = utils.get_gin_player_names()
    p_df = utils.get_players_df()
    roster_map = {}
    if not p_df.empty:
        for _, pr in p_df.iterrows():
            nm = str(pr.get("name_display") or "").strip()
            if nm:
                roster_map[nm.upper()] = pr.to_dict()

    # Inizializzazione stato checkbox atleti in session_state (default: tutti i GIN selezionati)
    for nm in gin_names:
        chk_k = f"dossier_chk_{nm}"
        if chk_k not in st.session_state:
            st.session_state[chk_k] = True

    # Calcolo insieme atleti attualmente selezionati
    sel_set = {nm for nm in gin_names if st.session_state.get(f"dossier_chk_{nm}", True)}

    # 2. Parametri di Configurazione Export
    c_conf1, c_conf2, c_conf3 = st.columns([1.8, 1.4, 1.2])

    tipo_dossier_opts = {
        "integrato": "Dossier Integrato Totale (GPS 21gg + Minuti Oval • 3 pag./atleta)",
        "gps": "Solo Dossier GPS (Passaporto Fisico & Carichi 21gg • 1 pag./atleta)",
        "oval": "Solo Dossier Minuti Oval (Carriera, Stagioni & Squadre • 2 pag./atleta)",
    }
    sel_tipo_key = c_conf1.selectbox(
        "1. Tipologia di Fascicolo PDF",
        list(tipo_dossier_opts.keys()),
        format_func=lambda k: tipo_dossier_opts[k],
        index=0,
        key="dossier_tipo_select",
    )

    week_options, default_week_idx = _get_available_weeks_options()
    week_labels = [w[1] for w in week_options]
    week_dict = {w[1]: w[0] for w in week_options}

    # Sincronizzazione automatica con la settimana della barra laterale
    cur_camp = st.session_state.get("global_selected_camp_obj")
    if cur_camp and "start_date" in cur_camp:
        camp_s_dt = str(cur_camp["start_date"])[:10]
        for w_i, (w_mon, _) in enumerate(week_options):
            if w_mon == camp_s_dt:
                default_week_idx = w_i
                break

    sel_week_lbl = c_conf2.selectbox(
        "2. Settimana GPS di Riferimento (Week 0)",
        week_labels,
        index=default_week_idx,
        help="Sincronizzata automaticamente con la settimana della barra laterale. Definisce la Week 0, Week -1 e Week -2 per l'analisi GPS.",
        key="dossier_week_select",
    )
    ref_mon_str = week_dict[sel_week_lbl]
    if cur_camp is None or str(cur_camp.get("start_date", ""))[:10] != ref_mon_str:
        import global_state
        global_state.sync_selected_camp_by_date(ref_mon_str)

    include_charts = c_conf3.checkbox(
        "Includi Grafici Plotly",
        value=True,
        help="Se attivo genera i grafici giorno per giorno e trend. Se disattivato la generazione è istantanea.",
        key="dossier_inc_charts",
    )

    # 3. Metriche Riassuntive Live
    n_sel = len(sel_set)
    n_tot_gin = len(gin_names)
    pages_per_atleta = 3 if sel_tipo_key == "integrato" else (1 if sel_tipo_key == "gps" else 2)
    idx_pages = 1 if n_sel <= 34 else 2
    est_total_pages = idx_pages + (n_sel * pages_per_atleta) if n_sel > 0 else 0

    n_sel_fw = sum(1 for nm in sel_set if str(roster_map.get(nm.upper(), {}).get("department", "")).lower() == "avanti")
    n_sel_bk = n_sel - n_sel_fw

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Atleti Selezionati", f"{n_sel} / {n_tot_gin}", f"{n_tot_gin - n_sel} esclusi")
    m2.metric("Stima Pagine PDF", f"{est_total_pages} pagine", f"{pages_per_atleta} pag./atleta + Indice")
    m3.metric("Ripartizione Reparti", f"{n_sel_fw} Avanti / {n_sel_bk} TreQuarti")
    m4.metric("Formato Documento", "A4 Orizzontale", "Con Indice & Sommario")

    st.markdown("---")

    # 4. Azioni Rapide di Selezione Massiva (Aggiornano direttamente le checkbox)
    st.markdown("#### 👥 Selezione Atleti da Includere nel Fascicolo")
    st.caption("Usa le azioni rapide per selezionare o deselezionare in blocco, oppure agisci sui singoli atleti:")
    b1, b2, b3, b4, b5, b6 = st.columns(6)

    if b1.button("✓ Seleziona Tutti (70)", key="btn_sel_all_gin", use_container_width=True):
        for nm in gin_names:
            st.session_state[f"dossier_chk_{nm}"] = True
        st.rerun()

    if b2.button("✗ Deseleziona Tutti", key="btn_desel_all_gin", use_container_width=True):
        for nm in gin_names:
            st.session_state[f"dossier_chk_{nm}"] = False
        st.rerun()

    if b3.button("Solo Avanti", key="btn_sel_fw_only", use_container_width=True, help="Seleziona solo gli Avanti e toglie la spunta ai TreQuarti"):
        for nm in gin_names:
            dept = str(roster_map.get(nm.upper(), {}).get("department", "")).lower()
            st.session_state[f"dossier_chk_{nm}"] = (dept == "avanti")
        st.rerun()

    if b4.button("Solo TreQuarti", key="btn_sel_bk_only", use_container_width=True, help="Seleziona solo i TreQuarti e toglie la spunta agli Avanti"):
        for nm in gin_names:
            dept = str(roster_map.get(nm.upper(), {}).get("department", "")).lower()
            st.session_state[f"dossier_chk_{nm}"] = (dept != "avanti")
        st.rerun()

    if b5.button("Solo Benetton", key="btn_sel_ben_only", use_container_width=True, help="Seleziona solo i tesserati Benetton"):
        for nm in gin_names:
            club = str(roster_map.get(nm.upper(), {}).get("club", "")).lower()
            st.session_state[f"dossier_chk_{nm}"] = ("benetton" in club)
        st.rerun()

    if b6.button("Solo Zebre", key="btn_sel_zeb_only", use_container_width=True, help="Seleziona solo i tesserati Zebre"):
        for nm in gin_names:
            club = str(roster_map.get(nm.upper(), {}).get("club", "")).lower()
            st.session_state[f"dossier_chk_{nm}"] = ("zebre" in club)
        st.rerun()

    # Filtri di visualizzazione lista
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    c_f1, c_f2, c_f3 = st.columns([1.2, 1.2, 1.6])
    filter_dept = c_f1.selectbox(
        "Filtro Vista Reparto:",
        ["Tutti i Reparti", "Solo Avanti", "Solo TreQuarti"],
        index=0,
        key="dossier_filter_dept",
    )
    filter_club = c_f2.selectbox(
        "Filtro Vista Club:",
        ["Tutti i Club", "Solo Benetton", "Solo Zebre", "Altri Club / Estero"],
        index=0,
        key="dossier_filter_club",
    )
    search_q = c_f3.text_input(
        "Cerca giocatore per nome o ruolo:",
        placeholder="es. Lamaro, Pilone, Menoncello...",
        key="dossier_search_inp",
    )

    # 5. Griglia Interattiva di Selezione / Deselezione (4 colonne)
    display_players = []
    for nm in gin_names:
        pm = roster_map.get(nm.upper(), {})
        r_p = str(pm.get("role") or "Avanti")
        d_p = str(pm.get("department") or ROLE_TO_DEPT.get(r_p, "Avanti"))
        c_p = str(pm.get("club") or "FIR")

        # Filtro reparto
        if filter_dept == "Solo Avanti" and d_p != "Avanti":
            continue
        if filter_dept == "Solo TreQuarti" and d_p == "Avanti":
            continue

        # Filtro club
        if filter_club == "Solo Benetton" and "benetton" not in c_p.lower():
            continue
        if filter_club == "Solo Zebre" and "zebre" not in c_p.lower():
            continue
        if filter_club == "Altri Club / Estero" and ("benetton" in c_p.lower() or "zebre" in c_p.lower()):
            continue

        # Ricerca testo
        if search_q:
            q_low = search_q.strip().lower()
            if q_low not in nm.lower() and q_low not in r_p.lower() and q_low not in c_p.lower():
                continue

        display_players.append((nm, r_p, d_p, c_p))

    # Azioni su elementi visibili
    c_sub_info, c_sub_b1, c_sub_b2 = st.columns([2.0, 1.0, 1.0])
    c_sub_info.caption(f"Mostrati **{len(display_players)}** su {n_tot_gin} atleti GIN. Spunta o togli la spunta:")
    if len(display_players) < n_tot_gin and len(display_players) > 0:
        if c_sub_b1.button(f"✓ Spunta i {len(display_players)} visibili", key="btn_chk_vis", use_container_width=True):
            for p_nm, _, _, _ in display_players:
                st.session_state[f"dossier_chk_{p_nm}"] = True
            st.rerun()
        if c_sub_b2.button(f"✗ Togli spunta ai {len(display_players)} visibili", key="btn_unchk_vis", use_container_width=True):
            for p_nm, _, _, _ in display_players:
                st.session_state[f"dossier_chk_{p_nm}"] = False
            st.rerun()

    grid_cols = st.columns(4)

    for idx, (p_name, p_role, p_dept, p_club) in enumerate(display_players):
        col = grid_cols[idx % 4]

        # Riquadro compatto con nome, checkbox e badge ruolo/club
        dept_badge_col = "#0284C7" if p_dept == "Avanti" else "#7C3AED"
        club_badge_col = "#059669" if "benetton" in p_club.lower() else ("#D97706" if "zebre" in p_club.lower() else "#475569")

        col.checkbox(
            p_name,
            key=f"dossier_chk_{p_name}",
            help=f"{p_role} ({p_dept}) • {p_club}",
        )
        col.markdown(
            f"<div style='font-size:0.68rem; color:#64748B; margin-top:-6px; margin-bottom:8px;'>"
            f"<span style='color:{dept_badge_col}; font-weight:700;'>{p_role}</span> • "
            f"<span style='color:{club_badge_col}; font-weight:600;'>{p_club}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # 6. Pulsante di Esportazione PDF Batch
    st.markdown("#### 🚀 Avvia Esportazione PDF")

    if n_sel == 0:
        st.warning("⚠️ Nessun atleta selezionato. Seleziona almeno un giocatore per generare il PDF.")
        return

    btn_label = f"📥 Genera Fascicolo PDF ({n_sel} Atleti • ~{est_total_pages} Pagine)"
    if st.button(btn_label, type="primary", use_container_width=True, key="btn_generate_multi_dossier"):
        all_gps = utils.get_gps_history_df("all")
        ov_df = utils.get_oval_matches_df()

        prog_bar = st.progress(0)
        status_txt = st.empty()

        # Ordina gli atleti selezionati secondo l'ordine ufficiale GIN
        ordered_selected = [nm for nm in gin_names if nm in sel_set]

        dossier_payload = []
        for i, p_name in enumerate(ordered_selected):
            pct = int(((i + 1) / float(len(ordered_selected))) * 100)
            prog_bar.progress(pct)
            status_txt.markdown(f"⏳ **Elaborazione atleta {i+1}/{len(ordered_selected)}**: `{p_name}`...")

            # Dati GPS 21 giorni
            gps_data = utils.build_athlete_21d_workload(p_name, ref_mon_str, all_gps, ov_df, roster_map)
            # Profilo Oval
            prof = utils.get_athlete_oval_career_profile(p_name)

            fig_gps = None
            if include_charts and gps_data.get("df_21") is not None and not gps_data["df_21"].empty:
                fig_gps = utils.build_athlete_21d_chart(gps_data["df_21"], p_name)

            dossier_payload.append({
                "player_name": p_name,
                "role": gps_data["role"],
                "department": gps_data["department"],
                "club": gps_data["club"],
                "p_meta": gps_data["p_meta"],
                "df_21": gps_data["df_21"],
                "week_stats": gps_data["week_stats"],
                "fig_gps": fig_gps,
                "prof": prof,
            })

        status_txt.markdown("📄 **Compilazione PDF ReportLab in corso (Copertina, Indice & Schede)...**")
        prog_bar.progress(100)

        pdf_bytes = crea_pdf_dossier_multi_giocatore(
            dossier_payload=dossier_payload,
            ref_week_lbl=sel_week_lbl,
            dossier_type=sel_tipo_key,
            season_lbl="2026/27",
            include_charts=include_charts,
        )

        st.session_state["last_multi_dossier_pdf"] = {
            "bytes": pdf_bytes,
            "filename": f"FIR_Dossier_GIN_{sel_tipo_key}_{ref_mon_str}_{n_sel}atleti.pdf",
            "atleti": n_sel,
            "tipo": tipo_dossier_opts[sel_tipo_key],
        }
        status_txt.empty()
        prog_bar.empty()

    # Mostra pulsante di download se il PDF è stato generato
    if "last_multi_dossier_pdf" in st.session_state:
        res = st.session_state["last_multi_dossier_pdf"]
        mb_size = len(res["bytes"]) / (1024 * 1024)
        st.success(f"✅ **Fascicolo PDF pronto!** Dimensioni: **{mb_size:.2f} MB** • Atleti: **{res['atleti']}** • {res['tipo']}")
        st.download_button(
            label=f"⬇️ Clicca qui per scaricare: {res['filename']}",
            data=res["bytes"],
            file_name=res["filename"],
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key="btn_download_multi_pdf",
        )
