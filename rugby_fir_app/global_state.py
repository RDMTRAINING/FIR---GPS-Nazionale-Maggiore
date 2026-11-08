import os
import streamlit as st
import pandas as pd
import numpy as np
import utils


def init_global_state(hist_df: pd.DataFrame = None):
    """Inizializza lo stato globale persistente di selezione (Raduno, Sessione, Tipologia e Match Trombinoscopio)."""
    if hist_df is None or hist_df.empty:
        hist_df = utils.get_gps_history_df("nazionale")

    if hist_df.empty:
        return

    # 1. Trova la sessione di default: "261105 Velocità" se presente, altrimenti la più recente
    if "global_selected_session_name" not in st.session_state or not st.session_state["global_selected_session_name"]:
        sessions_summary = (
            hist_df.groupby(["date_str", "session_name"], as_index=False)
            .agg(atleti=("player_name", "nunique"), righe=("id", "count"))
            .sort_values(["date_str", "righe"], ascending=[False, False])
            .reset_index(drop=True)
        )
        def_row = None
        for _, r in sessions_summary.iterrows():
            if "2026-11-05" in str(r["date_str"]) and "Velocit" in str(r["session_name"]):
                def_row = r
                break
        if def_row is None and not sessions_summary.empty:
            def_row = sessions_summary.iloc[0]

        if def_row is not None:
            st.session_state["global_selected_date"] = str(def_row["date_str"])
            st.session_state["global_selected_session_name"] = str(def_row["session_name"])
            st.session_state["global_selected_session_key"] = f"{def_row['date_str']} • {def_row['session_name']}"

            # Assegna automaticamente la tipologia della sessione scelta
            cur_type = utils.get_session_assigned_type(str(def_row["date_str"]), str(def_row["session_name"]))
            st.session_state["global_selected_type"] = cur_type

    # 2. Inizializza il Match per il Trombinoscopio Match
    if "global_selected_match_label" not in st.session_state or not st.session_state["global_selected_match_label"]:
        lineup_summary = utils.get_lineup_matches_summary()
        if not lineup_summary.empty:
            latest_m = lineup_summary.iloc[0]
            m_dt = str(latest_m["date_str"])
            m_nm = str(latest_m["match_name"])
            m_comp = str(latest_m["competition"])
            m_lbl = f"{m_dt} • {m_nm} ({m_comp})"
            st.session_state["global_selected_match_date"] = m_dt
            st.session_state["global_selected_match_name"] = m_nm
            st.session_state["global_selected_match_comp"] = m_comp
            st.session_state["global_selected_match_label"] = m_lbl


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

    # 1. Selezione Raduno
    camp_options = ["Tutte le Settimane (Senza filtro Raduno)"]
    camp_lookup = {}
    default_camp_idx = 0
    if not camps_df.empty:
        camps_sorted = camps_df.sort_values("start_date", ascending=False).reset_index(drop=True)
        for idx_c, cr in camps_sorted.iterrows():
            s_dt = str(cr.get("start_date") or "")[:10]
            w_nm = str(cr.get("week_name") or "Raduno")
            lbl = f"{s_dt} • {w_nm}"
            camp_options.append(lbl)
            camp_lookup[lbl] = cr.to_dict()
            if s_dt == "2026-11-02":
                default_camp_idx = idx_c + 1

    cur_camp_lbl = st.session_state.get("global_camp_label", camp_options[default_camp_idx] if default_camp_idx < len(camp_options) else camp_options[0])
    sel_camp = st.selectbox(
        "Settimana Raduno FIR:",
        camp_options,
        index=camp_options.index(cur_camp_lbl) if cur_camp_lbl in camp_options else 0,
        key="sb_global_sel_camp",
    )
    st.session_state["global_camp_label"] = sel_camp
    selected_camp_obj = camp_lookup.get(sel_camp)
    st.session_state["global_selected_camp_obj"] = selected_camp_obj

    # 2. Elenco Sessioni (filtrate per raduno se selezionato)
    sessions_summary = (
        hist_df.groupby(["date_str", "session_name"], as_index=False)
        .agg(atleti=("player_name", "nunique"), righe=("id", "count"))
        .sort_values(["date_str", "righe"], ascending=[False, False])
        .reset_index(drop=True)
    )

    if selected_camp_obj is not None:
        try:
            c_start = pd.to_datetime(str(selected_camp_obj["start_date"])[:10])
            c_end = c_start + pd.Timedelta(days=6)
            s_dts = pd.to_datetime(sessions_summary["date_str"], errors="coerce")
            filtered_sessions = sessions_summary[(s_dts >= c_start) & (s_dts <= c_end)].copy()
            if filtered_sessions.empty:
                filtered_sessions = sessions_summary
        except Exception:
            filtered_sessions = sessions_summary
    else:
        filtered_sessions = sessions_summary

    sess_labels = [f"{r['date_str']} • {r['session_name']}" for _, r in filtered_sessions.iterrows()]
    sess_lookup = {f"{r['date_str']} • {r['session_name']}": (str(r["date_str"]), str(r["session_name"])) for _, r in filtered_sessions.iterrows()}

    if not sess_labels:
        st.warning("Nessuna sessione trovata per questo filtro.")
        return

    cur_sess_key = st.session_state.get("global_selected_session_key", sess_labels[0])
    default_sess_idx = sess_labels.index(cur_sess_key) if cur_sess_key in sess_labels else 0

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

    # 4. Selezione Match per il Trombinoscopio Match (1-23)
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    lineup_summary = utils.get_lineup_matches_summary()
    if not lineup_summary.empty:
        lineup_summary["label"] = lineup_summary["date_str"] + " • " + lineup_summary["match_name"] + " (" + lineup_summary["competition"] + ")"
        m_labels = lineup_summary["label"].tolist()
        m_lookup = {
            r["label"]: (str(r["date_str"]), str(r["match_name"]), str(r["competition"]))
            for _, r in lineup_summary.iterrows()
        }

        cur_m_lbl = st.session_state.get("global_selected_match_label", m_labels[0])
        if cur_m_lbl not in m_labels:
            cur_m_lbl = m_labels[0]

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

    sel_date_str = st.session_state.get("global_selected_date", "2026-11-05")
    sel_sess_name = st.session_state.get("global_selected_session_name", "261105 Velocità")
    cur_type = st.session_state.get("global_selected_type") or utils.get_session_assigned_type(sel_date_str, sel_sess_name)
    selected_camp = st.session_state.get("global_selected_camp_obj")

    # Dati Convocati Raduno
    cp_df = utils.get_camp_players_df()
    if selected_camp is not None and not cp_df.empty and "id" in selected_camp:
        camp_players = cp_df[cp_df["camp_id"] == int(selected_camp["id"])].copy()
    else:
        camp_players = pd.DataFrame()

    # 1. Filtro rigoroso: solo ed esclusivamente la seduta selezionata
    sub_gps_sess = hist_df[
        (hist_df["date_str"] == sel_date_str) &
        (hist_df["session_name"] == sel_sess_name)
    ].copy()

    # 2. Dati della giornata (tutte le sessioni svolte nella stessa data)
    sub_gps_day = hist_df[hist_df["date_str"] == sel_date_str].copy()

    # 3. Dati della settimana (periodo lunedì-domenica del raduno o della sessione)
    try:
        if selected_camp is not None and "start_date" in selected_camp:
            w_start = pd.to_datetime(str(selected_camp["start_date"])[:10])
        else:
            cur_dt = pd.to_datetime(sel_date_str)
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
    day_sessions_list = sorted(sub_gps_day["session_name"].dropna().unique().tolist())
    week_sessions_list = sorted(sub_gps_week["session_name"].dropna().unique().tolist())

    try:
        date_short = pd.to_datetime(sel_date_str).strftime("%d/%m/%y")
    except Exception:
        date_short = sel_date_str

    meta = {
        "session_name": sel_sess_name,
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
    }

    # Match per Trombinoscopio
    sel_m_d = st.session_state.get("global_selected_match_date", "2026-11-07")
    sel_m_n = st.session_state.get("global_selected_match_name", "ITALIA - SUD AFRICA")
    sel_m_c = st.session_state.get("global_selected_match_comp", "Autumn Nations Series 2026")
    sel_m_lbl = st.session_state.get("global_selected_match_label", f"{sel_m_d} • {sel_m_n} ({sel_m_c})")

    match_info = {
        "date_str": sel_m_d,
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
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); border-left:5px solid #D4AF37; border-radius:8px; padding:10px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; color:#FFFFFF; box-shadow:0 3px 8px rgba(0,0,0,0.25);">
                <div>
                    <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37;">
                        🎯 CONFIGURAZIONE ATTIVA (BARRA LATERALE)
                    </div>
                    <div style="font-size:1.08rem; font-weight:800; color:#FFFFFF;">
                        {meta.get('date_short', meta.get('date_str', ''))} • {meta.get('session_name', '')}
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
