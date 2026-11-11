import os
import streamlit as st
import pandas as pd
import numpy as np
import utils


def init_global_state(hist_df: pd.DataFrame = None):
    """Inizializza lo stato globale persistente di selezione (Raduno, Sessione, Tipologia e Match Trombinoscopio)."""
    if hist_df is None or hist_df.empty:
        hist_df = utils.get_gps_history_df("nazionale")

    camps_df = utils.get_camps_df()

    # 1. Trova il raduno di default: settimana di calendario attuale (modificabile)
    if "global_camp_label" not in st.session_state or not st.session_state["global_camp_label"]:
        if not camps_df.empty:
            camps_sorted = camps_df.sort_values("start_date", ascending=False).reset_index(drop=True)
            today = pd.Timestamp.now().normalize()
            def_camp = None
            for _, cr in camps_sorted.iterrows():
                s_dt = str(cr.get("start_date") or cr.get("start_date_str") or "")[:10]
                c_start = pd.to_datetime(s_dt, errors="coerce")
                if not pd.isna(c_start):
                    c_end = c_start + pd.Timedelta(days=6)
                    if c_start <= today <= c_end:
                        def_camp = cr
                        break
            if def_camp is None:
                past = camps_sorted[pd.to_datetime(camps_sorted["start_date"], errors="coerce") <= today]
                if not past.empty:
                    def_camp = past.iloc[0]
                else:
                    def_camp = camps_sorted.iloc[0]

            if def_camp is not None:
                s_dt = str(def_camp.get("start_date") or "")[:10]
                w_nm = str(def_camp.get("week_name") or "Raduno")
                lbl = f"{s_dt} • {w_nm}"
                st.session_state["global_camp_label"] = lbl
                st.session_state["global_selected_camp_obj"] = def_camp.to_dict()
                st.session_state["_prev_sb_global_sel_camp"] = lbl

    # 2. Trova la sessione di default per il raduno attivo
    if "global_selected_session_name" not in st.session_state or st.session_state["global_selected_session_name"] is None:
        sel_camp_obj = st.session_state.get("global_selected_camp_obj")
        filtered_df = hist_df
        if sel_camp_obj is not None and hist_df is not None and not hist_df.empty:
            try:
                c_start = pd.to_datetime(str(sel_camp_obj["start_date"])[:10])
                c_end = c_start + pd.Timedelta(days=6)
                s_dts = pd.to_datetime(hist_df["date_str"], errors="coerce")
                filtered_df = hist_df[(s_dts >= c_start) & (s_dts <= c_end)]
            except Exception:
                filtered_df = pd.DataFrame()

        if filtered_df is not None and not filtered_df.empty:
            sessions_summary = (
                filtered_df.groupby(["date_str", "session_name"], as_index=False)
                .agg(atleti=("player_name", "nunique"), righe=("id", "count"))
                .sort_values(["date_str", "righe"], ascending=[False, False])
                .reset_index(drop=True)
            )
            def_row = sessions_summary.iloc[0] if not sessions_summary.empty else None
            if def_row is not None:
                st.session_state["global_selected_date"] = str(def_row["date_str"])
                st.session_state["global_selected_session_name"] = str(def_row["session_name"])
                st.session_state["global_selected_session_key"] = f"{def_row['date_str']} • {def_row['session_name']}"
                st.session_state["global_selected_type"] = utils.get_session_assigned_type(str(def_row["date_str"]), str(def_row["session_name"]))
            else:
                st.session_state["global_selected_date"] = ""
                st.session_state["global_selected_session_name"] = ""
                st.session_state["global_selected_session_key"] = ""
                st.session_state["global_selected_type"] = "Allenamento"
        else:
            st.session_state["global_selected_date"] = ""
            st.session_state["global_selected_session_name"] = ""
            st.session_state["global_selected_session_key"] = ""
            st.session_state["global_selected_type"] = "Allenamento"

    # 3. Inizializza il Match per il Trombinoscopio Match: preferibilmente il match del raduno o la prossima gara
    lineup_summary = utils.get_lineup_matches_summary()
    if not lineup_summary.empty:
        sel_camp_obj = st.session_state.get("global_selected_camp_obj")
        camp_match_r = None
        if sel_camp_obj is not None:
            try:
                c_start = pd.to_datetime(str(sel_camp_obj["start_date"])[:10])
                c_end = c_start + pd.Timedelta(days=6)
                for _, r in lineup_summary.iterrows():
                    m_d = pd.to_datetime(str(r["date_str"])[:10], errors="coerce")
                    if not pd.isna(m_d) and c_start <= m_d <= c_end:
                        camp_match_r = r
                        break
            except Exception:
                pass

        cur_m_lbl = st.session_state.get("global_selected_match_label")
        cur_m_dt = st.session_state.get("global_selected_match_date")
        need_reset = False
        if not cur_m_lbl:
            need_reset = True
        elif camp_match_r is not None and cur_m_dt:
            try:
                c_start = pd.to_datetime(str(sel_camp_obj["start_date"])[:10])
                c_end = c_start + pd.Timedelta(days=6)
                m_d_obj = pd.to_datetime(str(cur_m_dt)[:10], errors="coerce")
                if not (not pd.isna(m_d_obj) and c_start <= m_d_obj <= c_end):
                    need_reset = True
            except Exception:
                pass

        if need_reset:
            target_m = camp_match_r
            if target_m is None and hist_df is not None and not hist_df.empty:
                hist_dates_set = set(hist_df["date_str"].dropna().astype(str).str[:10].unique())
                for _, r in lineup_summary.iterrows():
                    if str(r["date_str"])[:10] in hist_dates_set:
                        target_m = r
                        break
            if target_m is None:
                for _, r in lineup_summary.iterrows():
                    if int(r.get("starters_count", 0)) > 0:
                        target_m = r
                        break
            if target_m is None:
                target_m = lineup_summary.iloc[0]

            m_dt = str(target_m["date_str"])
            m_nm = str(target_m["match_name"])
            m_comp = str(target_m["competition"])
            m_lbl = f"{m_dt} • {m_nm} ({m_comp})"
            st.session_state["global_selected_match_date"] = m_dt
            st.session_state["global_selected_match_name"] = m_nm
            st.session_state["global_selected_match_comp"] = m_comp
            st.session_state["global_selected_match_label"] = m_lbl


def sync_selected_camp_by_id(camp_id: int):
    """Sincronizza la settimana raduno nella barra laterale a partire dall'ID del raduno."""
    camps_df = utils.get_camps_df()
    if camps_df.empty:
        return
    sub = camps_df[camps_df["id"].astype(int) == int(camp_id)]
    if not sub.empty:
        cr = sub.iloc[0]
        s_dt = str(cr.get("start_date") or cr.get("start_date_str") or "")[:10]
        w_nm = str(cr.get("week_name") or "Raduno")
        lbl = f"{s_dt} • {w_nm}"
        st.session_state["global_camp_label"] = lbl
        st.session_state["global_selected_camp_obj"] = cr.to_dict()
        st.session_state["sb_global_sel_camp"] = lbl
        st.session_state["_prev_sb_global_sel_camp"] = lbl
        # reset session key to default for new camp
        st.session_state.pop("global_selected_session_key", None)
        st.session_state.pop("global_selected_date", None)
        st.session_state.pop("global_selected_session_name", None)
        st.session_state.pop("sb_global_sel_sess", None)


def sync_selected_camp_by_date(date_str: str):
    """Sincronizza la settimana raduno nella barra laterale a partire da una data (es. lunedì inizio settimana)."""
    camps_df = utils.get_camps_df()
    if camps_df.empty:
        return
    target_dt = pd.to_datetime(str(date_str)[:10], errors="coerce")
    if pd.isna(target_dt):
        return
    for _, cr in camps_df.sort_values("start_date", ascending=False).iterrows():
        s_dt = str(cr.get("start_date") or cr.get("start_date_str") or "")[:10]
        c_start = pd.to_datetime(s_dt, errors="coerce")
        if not pd.isna(c_start):
            c_end = c_start + pd.Timedelta(days=6)
            if c_start <= target_dt <= c_end or c_start == target_dt:
                sync_selected_camp_by_id(int(cr["id"]))
                return


def sync_selected_session(date_str: str, session_name: str):
    """Sincronizza la seduta GPS nella barra laterale."""
    d_clean = str(date_str).strip()
    s_clean = str(session_name).strip()
    key = f"{d_clean} • {s_clean}"
    st.session_state["global_selected_session_key"] = key
    st.session_state["global_selected_date"] = d_clean
    st.session_state["global_selected_session_name"] = s_clean
    st.session_state["sb_global_sel_sess"] = key
    st.session_state["global_selected_type"] = utils.get_session_assigned_type(d_clean, s_clean)


def sync_selected_match(match_date_or_name: str):
    """Sincronizza il match / partita nella barra laterale a partire dalla data o nome della gara."""
    lineup_summary = utils.get_lineup_matches_summary()
    if lineup_summary.empty:
        return
    q = str(match_date_or_name).strip()
    sub = lineup_summary[lineup_summary["date_str"].astype(str) == q[:10]]
    if sub.empty:
        sub = lineup_summary[lineup_summary["match_name"].astype(str).str.lower() == q.lower()]
    if not sub.empty:
        r = sub.iloc[0]
        m_dt = str(r["date_str"])
        m_nm = str(r["match_name"])
        m_comp = str(r["competition"])
        m_lbl = f"{m_dt} • {m_nm} ({m_comp})"
        st.session_state["global_selected_match_date"] = m_dt
        st.session_state["global_selected_match_name"] = m_nm
        st.session_state["global_selected_match_comp"] = m_comp
        st.session_state["global_selected_match_label"] = m_lbl
        st.session_state["sb_global_sel_match"] = m_lbl


def render_sidebar_global_panel(hist_df: pd.DataFrame = None):
    """
    Renderizza il Pannello di Selezione Globale nella Sidebar.
    Rimane visibile e fisso in tutte le analisi, garantendo la totale sincronizzazione.
    Contiene:
    - Settimana Raduno FIR
    - Seduta GPS da Analizzare
    - Tipologia Benchmark (badge + cambio veloce)
    - Match Trombinoscopio (1-23)
    """
    if hist_df is None or hist_df.empty:
        hist_df = utils.get_gps_history_df("nazionale")

    if hist_df.empty:
        return

    init_global_state(hist_df)

    camps_df = utils.get_camps_df()
    types_map = utils.get_fir_session_types()

    st.markdown(
        """
        <div style="background:linear-gradient(135deg, rgba(0,43,73,0.9) 0%, rgba(0,102,178,0.7) 100%); border:1.5px solid #D4AF37; border-radius:10px; padding:10px 12px; margin-bottom:14px; box-shadow:0 3px 8px rgba(0,0,0,0.25);">
            <div style="font-size:0.74rem; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37; display:flex; align-items:center; gap:6px;">
                <span>🎯</span> <span>SELEZIONE GLOBALE ATTIVA</span>
            </div>
            <div style="font-size:0.68rem; color:#E0F2FE; margin-top:2px; line-height:1.35;">
                I parametri selezionati qui sotto alimentano automaticamente tutte le analisi e i report.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 1. Selezione Raduno: default su settimana attuale di calendario (modificabile)
    camp_options = ["Tutte le Settimane (Senza filtro Raduno)"]
    camp_lookup = {}
    default_camp_idx = 0
    if not camps_df.empty:
        camps_sorted = camps_df.sort_values("start_date", ascending=False).reset_index(drop=True)
        today = pd.Timestamp.now().normalize()
        current_camp_found = False

        for idx_c, cr in camps_sorted.iterrows():
            s_dt = str(cr.get("start_date") or cr.get("start_date_str") or "")[:10]
            w_nm = str(cr.get("week_name") or "Raduno")
            lbl = f"{s_dt} • {w_nm}"
            camp_options.append(lbl)
            camp_lookup[lbl] = cr.to_dict()

            if not current_camp_found:
                c_start = pd.to_datetime(s_dt, errors="coerce")
                if not pd.isna(c_start):
                    c_end = c_start + pd.Timedelta(days=6)
                    if c_start <= today <= c_end:
                        default_camp_idx = idx_c + 1
                        current_camp_found = True

        # Se oggi non rientra esattamente in nessun raduno, trova il raduno <= oggi o il primo disponibile
        if not current_camp_found:
            for idx_c, cr in camps_sorted.iterrows():
                s_dt = str(cr.get("start_date") or cr.get("start_date_str") or "")[:10]
                c_start = pd.to_datetime(s_dt, errors="coerce")
                if not pd.isna(c_start) and c_start <= today:
                    default_camp_idx = idx_c + 1
                    current_camp_found = True
                    break
        if not current_camp_found and len(camp_options) > 1:
            default_camp_idx = 1

    cur_camp_lbl = st.session_state.get("global_camp_label", camp_options[default_camp_idx] if default_camp_idx < len(camp_options) else camp_options[0])
    if cur_camp_lbl not in camp_options:
        cur_camp_lbl = camp_options[default_camp_idx] if default_camp_idx < len(camp_options) else camp_options[0]

    if st.session_state.get("sb_global_sel_camp") not in camp_options:
        st.session_state["sb_global_sel_camp"] = cur_camp_lbl

    sel_camp = st.selectbox(
        "Settimana Raduno FIR:",
        camp_options,
        index=camp_options.index(cur_camp_lbl) if cur_camp_lbl in camp_options else 0,
        key="sb_global_sel_camp",
    )

    # Rilevamento cambio raduno: sincronizza e azzera le selezioni della seduta
    prev_camp = st.session_state.get("_prev_sb_global_sel_camp")
    camp_changed = (prev_camp is not None and prev_camp != sel_camp)
    if camp_changed:
        st.session_state.pop("global_selected_session_key", None)
        st.session_state.pop("global_selected_date", None)
        st.session_state.pop("global_selected_session_name", None)
        st.session_state.pop("sb_global_sel_sess", None)
    st.session_state["_prev_sb_global_sel_camp"] = sel_camp
    st.session_state["global_camp_label"] = sel_camp
    selected_camp_obj = camp_lookup.get(sel_camp)
    st.session_state["global_selected_camp_obj"] = selected_camp_obj

    # 2. Elenco Sessioni (filtrate rigorosamente per raduno se selezionato)
    if not hist_df.empty:
        sessions_summary = (
            hist_df.groupby(["date_str", "session_name"], as_index=False)
            .agg(atleti=("player_name", "nunique"), righe=("id", "count"))
            .sort_values(["date_str", "righe"], ascending=[False, False])
            .reset_index(drop=True)
        )
    else:
        sessions_summary = pd.DataFrame(columns=["date_str", "session_name", "atleti", "righe"])

    if selected_camp_obj is not None:
        try:
            c_start = pd.to_datetime(str(selected_camp_obj["start_date"])[:10])
            c_end = c_start + pd.Timedelta(days=6)
            s_dts = pd.to_datetime(sessions_summary["date_str"], errors="coerce")
            filtered_sessions = sessions_summary[(s_dts >= c_start) & (s_dts <= c_end)].copy()
        except Exception:
            filtered_sessions = pd.DataFrame(columns=sessions_summary.columns)
    else:
        filtered_sessions = sessions_summary

    sess_labels = [f"{r['date_str']} • {r['session_name']}" for _, r in filtered_sessions.iterrows()]
    sess_lookup = {f"{r['date_str']} • {r['session_name']}": (str(r["date_str"]), str(r["session_name"])) for _, r in filtered_sessions.iterrows()}

    if not sess_labels:
        st.selectbox(
            "Seduta GPS da Analizzare:",
            ["Nessuna seduta registrata in questa settimana"],
            disabled=True,
            key=f"sb_global_sel_sess_empty_{sel_camp}",
        )
        st.caption("ℹ️ Nessun dato GPS caricato per il raduno selezionato.")
        st.session_state["global_selected_session_key"] = ""
        st.session_state["global_selected_date"] = ""
        st.session_state["global_selected_session_name"] = ""
        st.session_state["global_selected_type"] = "Allenamento"
        sel_date_str = ""
        sel_sess_name = ""
    else:
        cur_sess_key = st.session_state.get("global_selected_session_key")
        default_sess_idx = sess_labels.index(cur_sess_key) if (cur_sess_key and cur_sess_key in sess_labels) else 0

        if st.session_state.get("sb_global_sel_sess") not in sess_labels:
            st.session_state["sb_global_sel_sess"] = sess_labels[default_sess_idx]

        sel_sess_lbl = st.selectbox(
            "Seduta GPS da Analizzare:",
            sess_labels,
            index=default_sess_idx,
            key="sb_global_sel_sess",
        )

        sel_date_str, sel_sess_name = sess_lookup[sel_sess_lbl]
        st.session_state["global_selected_session_key"] = sel_sess_lbl
        st.session_state["global_selected_date"] = sel_date_str
        st.session_state["global_selected_session_name"] = sel_sess_name

        # 3. Tipologia della sessione scelta: LEGATA AUTOMATICAMENTE E MODIFICABILE CON SELECTBOX DIRETTA
        cur_type = utils.get_session_assigned_type(sel_date_str, sel_sess_name)
        t_idx = utils.FIR_SESSION_TYPOLOGIES.index(cur_type) if cur_type in utils.FIR_SESSION_TYPOLOGIES else 0

        st.markdown(
            "<div style='margin-top:6px; margin-bottom:2px; font-size:0.70rem; font-weight:800; text-transform:uppercase; color:#D4AF37;'>⚡ TIPOLOGIA BENCHMARK FIR:</div>",
            unsafe_allow_html=True,
        )
        sel_type = st.selectbox(
            "Tipologia Benchmark Seduta:",
            utils.FIR_SESSION_TYPOLOGIES,
            index=t_idx,
            key=f"sb_global_type_sel_{sel_date_str}_{sel_sess_name}",
            label_visibility="collapsed",
        )
        if sel_type != cur_type:
            types_map[f"{sel_date_str}_{sel_sess_name}"] = sel_type
            utils.save_fir_session_types(types_map)
            st.session_state["global_selected_type"] = sel_type
            st.rerun()

        st.session_state["global_selected_type"] = sel_type

    # 4. Selezione Match per il Trombinoscopio Match (1-23):
    # Se il raduno ha un match specifico nella settimana, prioritizzalo come default
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    lineup_summary = utils.get_lineup_matches_summary()
    if not lineup_summary.empty:
        lineup_summary["label"] = lineup_summary["date_str"] + " • " + lineup_summary["match_name"] + " (" + lineup_summary["competition"] + ")"
        m_labels = lineup_summary["label"].tolist()
        m_lookup = {
            r["label"]: (str(r["date_str"]), str(r["match_name"]), str(r["competition"]))
            for _, r in lineup_summary.iterrows()
        }

        camp_match_lbl = None
        if selected_camp_obj is not None:
            try:
                c_start = pd.to_datetime(str(selected_camp_obj["start_date"])[:10])
                c_end = c_start + pd.Timedelta(days=6)
                for r_lbl, (r_dt, _, _) in m_lookup.items():
                    m_d = pd.to_datetime(r_dt[:10], errors="coerce")
                    if not pd.isna(m_d) and c_start <= m_d <= c_end:
                        camp_match_lbl = r_lbl
                        break
            except Exception:
                pass

        hist_dates_set = set(hist_df["date_str"].dropna().astype(str).str[:10].unique()) if hist_df is not None and not hist_df.empty else set()
        default_m_lbl = camp_match_lbl
        if default_m_lbl is None:
            for r_lbl, (r_dt, _, _) in m_lookup.items():
                if r_dt[:10] in hist_dates_set:
                    default_m_lbl = r_lbl
                    break
        if default_m_lbl is None:
            for _, r in lineup_summary.iterrows():
                if int(r.get("starters_count", 0)) > 0:
                    default_m_lbl = r["label"]
                    break
        if default_m_lbl is None:
            default_m_lbl = m_labels[0]

        if camp_match_lbl:
            cur_m_d = st.session_state.get("global_selected_match_date")
            is_match_in_camp = False
            if cur_m_d and selected_camp_obj is not None:
                try:
                    c_start = pd.to_datetime(str(selected_camp_obj["start_date"])[:10])
                    c_end = c_start + pd.Timedelta(days=6)
                    m_d_obj = pd.to_datetime(str(cur_m_d)[:10], errors="coerce")
                    if not pd.isna(m_d_obj) and c_start <= m_d_obj <= c_end:
                        is_match_in_camp = True
                except Exception:
                    pass
            if not is_match_in_camp:
                st.session_state["global_selected_match_label"] = camp_match_lbl
                m_d, m_n, m_c = m_lookup[camp_match_lbl]
                st.session_state["global_selected_match_date"] = m_d
                st.session_state["global_selected_match_name"] = m_n
                st.session_state["global_selected_match_comp"] = m_c
                st.session_state.pop("sb_global_sel_match", None)

        cur_m_lbl = st.session_state.get("global_selected_match_label", default_m_lbl)
        if cur_m_lbl not in m_labels:
            cur_m_lbl = default_m_lbl

        if st.session_state.get("sb_global_sel_match") not in m_labels:
            st.session_state["sb_global_sel_match"] = cur_m_lbl

        sel_m_lbl = st.selectbox(
            "Gara (Trombinoscopio Match):",
            m_labels,
            index=m_labels.index(cur_m_lbl),
            key="sb_global_sel_match",
        )
        st.session_state["global_selected_match_label"] = sel_m_lbl
        m_d, m_n, m_c = m_lookup[sel_m_lbl]
        st.session_state["global_selected_match_date"] = m_d
        st.session_state["global_selected_match_name"] = m_n
        st.session_state["global_selected_match_comp"] = m_c

    st.markdown("<hr style='border-color:rgba(255,255,255,0.12); margin:12px 0;'>", unsafe_allow_html=True)


def get_current_session_context(hist_df: pd.DataFrame = None) -> dict:
    """
    Estrae il contesto analitico completo per la sessione globale attiva e per il Trombinoscopio Match.
    Garantisce che:
    1. L'analisi della sessione sia rigorosamente sulla sola sessione selezionata.
    2. Il confronto sia vincolato alla stessa tipologia della sessione scelta.
    3. Il match del Trombinoscopio sia sincronizzato con la selezione nella sidebar.
    """
    if hist_df is None or hist_df.empty:
        hist_df = utils.get_gps_history_df("nazionale")

    init_global_state(hist_df)

    sessions_summary = (
        hist_df.groupby(["date_str", "session_name"], as_index=False)
        .agg(atleti=("player_name", "nunique"), righe=("id", "count"))
        .sort_values(["date_str", "righe"], ascending=[False, False])
        .reset_index(drop=True)
    )
    fallback_dt = str(sessions_summary.iloc[0]["date_str"]) if not sessions_summary.empty else ""
    fallback_nm = str(sessions_summary.iloc[0]["session_name"]) if not sessions_summary.empty else ""

    sel_date_str = st.session_state.get("global_selected_date")
    if sel_date_str is None:
        sel_date_str = fallback_dt
    sel_sess_name = st.session_state.get("global_selected_session_name")
    if sel_sess_name is None:
        sel_sess_name = fallback_nm
    cur_type = st.session_state.get("global_selected_type") or utils.get_session_assigned_type(sel_date_str, sel_sess_name)
    selected_camp = st.session_state.get("global_selected_camp_obj")

    # Dati Convocati Raduno
    cp_df = utils.get_camp_players_df()
    if selected_camp is not None and not cp_df.empty and "id" in selected_camp:
        camp_players = cp_df[cp_df["camp_id"] == int(selected_camp["id"])].copy()
    else:
        camp_players = pd.DataFrame()

    # 1. Filtro rigoroso: solo ed esclusivamente la seduta selezionata
    if sel_date_str and sel_sess_name:
        sub_gps_sess = hist_df[
            (hist_df["date_str"] == sel_date_str) &
            (hist_df["session_name"] == sel_sess_name)
        ].copy()
    else:
        sub_gps_sess = pd.DataFrame(columns=hist_df.columns)

    # 2. Dati della giornata (tutte le sessioni svolte nella stessa data)
    if sel_date_str:
        sub_gps_day = hist_df[hist_df["date_str"] == sel_date_str].copy()
    else:
        sub_gps_day = pd.DataFrame(columns=hist_df.columns)

    # 3. Dati della settimana (periodo lunedì-domenica del raduno o della sessione)
    try:
        if selected_camp is not None and "start_date" in selected_camp:
            w_start = pd.to_datetime(str(selected_camp["start_date"])[:10])
        elif sel_date_str:
            cur_dt = pd.to_datetime(sel_date_str)
            w_start = cur_dt - pd.Timedelta(days=cur_dt.weekday())
        else:
            cur_dt = pd.Timestamp.now().normalize()
            w_start = cur_dt - pd.Timedelta(days=cur_dt.weekday())
        w_end = w_start + pd.Timedelta(days=6)
        w_start_str = w_start.strftime("%Y-%m-%d")
        w_end_str = w_end.strftime("%Y-%m-%d")
        period_disp = f"{w_start.strftime('%d/%m/%y')} — {w_end.strftime('%d/%m/%y')}"
    except Exception:
        w_start_str = sel_date_str
        w_end_str = sel_date_str
        period_disp = sel_date_str

    sub_gps_week = hist_df[(hist_df["date_str"] >= w_start_str) & (hist_df["date_str"] <= w_end_str)].copy()
    day_sessions_list = sorted(sub_gps_day["session_name"].dropna().unique().tolist()) if not sub_gps_day.empty else []
    week_sessions_list = sorted(sub_gps_week["session_name"].dropna().unique().tolist()) if not sub_gps_week.empty else []

    try:
        date_short = pd.to_datetime(sel_date_str).strftime("%d/%m/%y") if sel_date_str else "--"
    except Exception:
        date_short = sel_date_str if sel_date_str else "--"

    meta = {
        "session_name": sel_sess_name if sel_sess_name else "Nessuna seduta registrata",
        "date_str": sel_date_str,
        "date_short": date_short,
        "date_disp": date_short,
        "archetype": cur_type,
        "session_type": cur_type,
        "camp_info": selected_camp,
        "day_sessions_list": day_sessions_list,
        "week_sessions_list": week_sessions_list,
        "week_period_disp": period_disp,
        "week_start": w_start_str,
        "week_end": w_end_str,
        "week_competition": str(selected_camp.get("competition") or "Nazionale Maggiore") if selected_camp else "Nazionale Maggiore",
        "week_name": str(selected_camp.get("week_name") or "Raduno") if selected_camp else "Settimana",
        "camp_name": str(selected_camp.get("week_name") or "Raduno") if selected_camp else "Settimana",
        "week_range": period_disp,
        "session_date": sel_date_str if sel_date_str else "--",
        "session_archetype": cur_type,
    }

    # Match per Trombinoscopio: cerca preferibilmente il match legato al raduno attivo
    default_match_d = "2026-11-14"
    default_match_n = "ITALIA - ARGENTINA"
    default_match_c = "NC Nov 2026"
    if selected_camp is not None and "start_date" in selected_camp:
        try:
            c_start = pd.to_datetime(str(selected_camp["start_date"])[:10])
            c_end = c_start + pd.Timedelta(days=6)
            lineup_summary = utils.get_lineup_matches_summary()
            for _, r in lineup_summary.iterrows():
                m_d = pd.to_datetime(str(r["date_str"])[:10], errors="coerce")
                if not pd.isna(m_d) and c_start <= m_d <= c_end:
                    default_match_d = str(r["date_str"])
                    default_match_n = str(r["match_name"])
                    default_match_c = str(r["competition"])
                    break
        except Exception:
            pass

    sel_m_d = st.session_state.get("global_selected_match_date", default_match_d)
    sel_m_n = st.session_state.get("global_selected_match_name", default_match_n)
    sel_m_c = st.session_state.get("global_selected_match_comp", default_match_c)
    sel_m_lbl = st.session_state.get("global_selected_match_label", f"{sel_m_d} • {sel_m_n} ({sel_m_c})")

    match_info = {
        "date_str": sel_m_d,
        "match_date": sel_m_d,
        "match_name": sel_m_n,
        "competition": sel_m_c,
        "label": sel_m_lbl,
    }

    return {
        "sub_gps_sess": sub_gps_sess,
        "sub_gps_day": sub_gps_day,
        "sub_gps_week": sub_gps_week,
        "camp_players": camp_players,
        "meta": meta,
        "match_info": match_info,
        "sel_date_str": sel_date_str,
        "sel_sess_name": sel_sess_name,
        "cur_type": cur_type,
    }


def render_top_context_banner(meta: dict, match_info: dict = None, is_match_view: bool = False, view_mode: str = None):
    """
    Renderizza una barra fissa ed elegante in cima alla pagina con ciò che è stato selezionato nella sidebar.
    Elimina ogni confusione e rimuove la necessità di menù a tendina ridondanti nelle pagine.
    view_mode: "session" (default), "match" (trombinoscopio), "settimana_23" (report dei 23 convocati)
    """
    if view_mode is None:
        view_mode = "match" if is_match_view else "session"

    if view_mode == "match" and match_info:
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); border-left:5px solid #D4AF37; border-radius:8px; padding:10px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; color:#FFFFFF; box-shadow:0 3px 8px rgba(0,0,0,0.25);">
                <div>
                    <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37;">
                        🏟️ GARA SELEZIONATA • TROMBINOSCOPIO MATCH (1-23 CONVOCATI)
                    </div>
                    <div style="font-size:1.08rem; font-weight:800; color:#FFFFFF;">
                        {match_info['date_str']} • {match_info['match_name']}
                    </div>
                    <div style="font-size:0.72rem; color:#93C5FD; font-weight:600;">
                        Competizione: <b>{match_info['competition']}</b> • Dati GPS e Minutaggi Ufficiali Oval
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="background:rgba(212,175,55,0.18); border:1px solid #D4AF37; color:#FDE047; padding:4px 12px; border-radius:6px; font-weight:800; font-size:0.75rem;">
                        🏉 SCHIERAMENTO 1-23 UFFICIALE FIR
                    </span>
                    <span style="background:rgba(255,255,255,0.08); color:#CBD5E1; padding:4px 8px; border-radius:6px; font-size:0.68rem;">
                        Modificabile dalla barra laterale
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif view_mode == "settimana_23" and match_info:
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); border-left:5px solid #D4AF37; border-radius:8px; padding:10px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; color:#FFFFFF; box-shadow:0 3px 8px rgba(0,0,0,0.25);">
                <div>
                    <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37;">
                        👥 CONFIGURAZIONE ATTIVA • REPORT SETTIMANA 23 CONVOCATI
                    </div>
                    <div style="font-size:1.08rem; font-weight:800; color:#FFFFFF;">
                        Raduno: {meta.get('week_name', 'Raduno')} ({meta.get('week_period_disp', '')}) • {meta.get('week_competition', 'Nazionale Maggiore')}
                    </div>
                    <div style="font-size:0.75rem; color:#93C5FD; font-weight:600;">
                        Gara Selezionata: <b>{match_info.get('date_str', '')} • {match_info.get('match_name', '')}</b> ({match_info.get('competition', '')})
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="background:rgba(212,175,55,0.18); border:1px solid #D4AF37; color:#FDE047; padding:4px 12px; border-radius:6px; font-weight:800; font-size:0.75rem;">
                        🏉 CARICHI CUMULATI 1-23 UFFICIALI FIR
                    </span>
                    <span style="background:rgba(255,255,255,0.08); color:#CBD5E1; padding:4px 8px; border-radius:6px; font-size:0.68rem;">
                        Modificabile dalla barra laterale
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        disp_sess = meta.get('session_name', '')
        disp_dt = meta.get('date_short', meta.get('date_str', ''))
        if not disp_sess or disp_sess == "Nessuna seduta registrata":
            title_text = "<span style='color:#FDE68A;'>Nessuna Seduta Registrata per questa Settimana</span>"
        else:
            title_text = f"{disp_dt} • {disp_sess}"

        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); border-left:5px solid #D4AF37; border-radius:8px; padding:10px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; color:#FFFFFF; box-shadow:0 3px 8px rgba(0,0,0,0.25);">
                <div>
                    <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37;">
                        🎯 CONFIGURAZIONE ATTIVA (BARRA LATERALE)
                    </div>
                    <div style="font-size:1.08rem; font-weight:800; color:#FFFFFF;">
                        {title_text}
                    </div>
                    <div style="font-size:0.72rem; color:#93C5FD; font-weight:600;">
                        Raduno: <b>{meta.get('week_name', 'Raduno')}</b> ({meta.get('week_period_disp', '')}) • {meta.get('week_competition', 'Nazionale Maggiore')}
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="background:rgba(212,175,55,0.18); border:1px solid #D4AF37; color:#FDE047; padding:4px 12px; border-radius:6px; font-weight:800; font-size:0.78rem;">
                        ⚡ Benchmark Vincolato: <b>{meta.get('session_type', meta.get('archetype', 'Velocità'))}</b>
                    </span>
                    <span style="background:rgba(255,255,255,0.08); color:#CBD5E1; padding:4px 8px; border-radius:6px; font-size:0.68rem;">
                        Modificabile dalla barra laterale
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
