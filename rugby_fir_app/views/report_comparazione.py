import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import render_page_header, render_tab_navigation, render_navigation_cards, render_action_bar, ROLE_TO_DEPT
import utils
import global_state
from views.home import SESSION_TYPE_BASELINES
from pdf_generator import crea_pdf_cruscotto_fir, slugify_name


def _clean_and_render_html(html_str: str):
    """Rimuove a capo spuri prima del rendering per prevenire interpretazioni markdown errate."""
    cleaned = "".join(line.strip() for line in html_str.splitlines() if line.strip())
    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def _prepare_fir_data_with_metrics(fir_df: pd.DataFrame, players_df: pd.DataFrame, types_map: dict) -> pd.DataFrame:
    """Prepara il DataFrame delle sessioni FIR calcolando tutte le metriche chiave e i reparti."""
    if fir_df.empty:
        return pd.DataFrame()

    df = fir_df.copy()

    # Roster mapping per reparto e ruolo
    p_dept = {}
    p_role = {}
    p_vmax = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip().upper()
            if nm:
                p_dept[nm] = str(pr.get("department") or ROLE_TO_DEPT.get(str(pr.get("role") or ""), "Avanti"))
                p_role[nm] = str(pr.get("role") or "Avanti")
                p_vmax[nm] = float(pr.get("v_max") or 30.0)

    # Conversione colonne numeriche
    num_cols = [
        "duration", "distance_m", "m_per_min", "speed_0_6", "speed_6_15", "speed_15_18",
        "speed_18_20", "speed_20_25", "speed_25_72", "mp_25_35", "mp_35_50", "mp_50_100",
        "ai_25_40", "ai_40_50", "ai_50_100", "v_max", "v_max_pct"
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        else:
            df[c] = 0.0

    # Metriche calcolate secondo standard FIR GPExe
    df["player_up"] = df["player_name"].astype(str).str.strip().str.upper()
    df["dept"] = df["player_up"].map(p_dept).fillna("Avanti")
    df["role_clean"] = df["player_up"].map(p_role).fillna(df["role"].fillna("Avanti"))
    df["roster_vmax"] = df["player_up"].map(p_vmax).fillna(30.0)

    # Calcolo % Vmax se assente
    df["v_max_pct"] = np.where(
        df["v_max_pct"] > 0,
        df["v_max_pct"],
        np.where(df["roster_vmax"] > 0, (df["v_max"] / df["roster_vmax"]) * 100.0, 0.0)
    )

    # Running distance: distanza sopra i 6 km/h
    df["run_dist"] = np.maximum(0.0, df["distance_m"] - df["speed_0_6"])

    # Metabolic Power & HML
    df["hml_25"] = df["mp_25_35"] + df["mp_35_50"] + df["mp_50_100"]
    df["vhml_40"] = df["mp_35_50"] + df["mp_50_100"]
    df["vhml_50"] = df["mp_50_100"]

    # High Speed Running
    df["hsr_18"] = df["speed_18_20"] + df["speed_20_25"] + df["speed_25_72"]
    df["hsr_20"] = df["speed_20_25"] + df["speed_25_72"]
    df["vhsr_25"] = df["speed_25_72"]

    # Power events: ai_25_40 (come da esportazione GPExe FIR)
    df["power_events"] = df["ai_25_40"]

    # Tipologia assegnata
    df["assigned_type"] = df.apply(
        lambda r: types_map.get(
            f"{r['date_str']}_{r['session_name']}",
            types_map.get(r["session_name"], utils.detect_fir_session_type(r["session_name"]))
        ),
        axis=1
    )

    return df


def render_page(t: dict, show_top_banner: bool = True):
    render_medie_e_confronti(t, show_top_banner=show_top_banner)


def render_medie_e_confronti(t: dict, show_top_banner: bool = True):
    render_page_header(
        "Medie Tipologie Seduta & Confronti FIR",
        "Medie Tipologie Allenamento • Confronto Multi Sessione (2+) • Confronto Settimana Raduno",
        "bi-bar-chart-steps",
    )

    fir_gps = utils.get_gps_history_df("nazionale")
    if fir_gps.empty:
        fir_gps = utils.get_gps_history_df("all")
    if fir_gps.empty:
        st.warning("Nessun dato GPS presente nel database.")
        return

    players_df = utils.get_players_df()
    types_map = utils.get_fir_session_types()
    status_map = utils.get_session_player_statuses()

    df_full = _prepare_fir_data_with_metrics(fir_gps, players_df, types_map)

    cards_confronti = [
        {"id": "medie_tipologie_fir", "title": "Medie Tipologie Allenamento", "desc": "Benchmark di ruolo e reparto per tipologia seduta", "icon": "bi-bar-chart-line-fill"},
        {"id": "confronto_multisessione", "title": "Confronto Multi Sessione", "desc": "Comparazione affiancata tra 2 o più allenamenti", "icon": "bi-layout-split"},
        {"id": "confronto_settimane", "title": "Confronto Settimana Raduno", "desc": "Confronto diretto tra raduni (es. Sud Africa vs Giappone)", "icon": "bi-arrows-angle-contract"},
    ]

    active_tab = render_navigation_cards("medie_e_confronti", cards_confronti)

    from pdf_generator import crea_pdf_cruscotto_fir

    typologies_bundle = build_fir_typologies_bundle(fir_gps, players_df, types_map)
    confronti_meta = {
        "session_name": "Medie & Confronti FIR",
        "date_str": "Database",
        "date_disp": "Benchmark e Comparazioni",
        "week_name": "Nazionale Maggiore",
        "week_period_disp": "Tutte le Gare & Raduni",
        "session_type": "Benchmark",
        "archetype": "Benchmark",
    }

    pdf_opts_confronti = {
        "Pacchetto Completo Medie & Confronti (Tutte le Pagine)": "Confronto",
        "1. Solo Medie Tipologie Allenamento (10 Tipologie FIR & Matrice Ruoli)": "Tipologie",
        "2. Solo Confronto Multi Sessione (Comparazione Grafica & Tabelle)": "Multisess",
        "3. Solo Confronto Settimana Raduno (Raduni Selezionati)": "Confronto_Settimane",
    }

    def _generate_confronti_pdf(codice_sub):
        cur_sel = st.session_state.get("multi_sess_selected", None)
        cur_dept = st.session_state.get("multi_sess_filter_dept", "Tutti (Collettivo)")
        dyn_multisess = build_multisession_comparison_bundle(
            fir_gps,
            status_map=status_map,
            selected_sessions=cur_sel,
            filter_dept=cur_dept,
        )
        cur_wk_a = st.session_state.get("cmp_wk_a", None)
        cur_wk_b = st.session_state.get("cmp_wk_b", None)
        cur_excl = st.session_state.get("cmp_wk_excl_match", True)
        dyn_settimane = build_confronto_settimane_bundle(
            df_full,
            camps_df=utils.get_camps_df(),
            wk_a_key=cur_wk_a,
            wk_b_key=cur_wk_b,
            excl_matches=cur_excl,
        )
        return crea_pdf_cruscotto_fir(
            codice_sub,
            confronti_meta,
            sess_bundle={"df": df_full},
            day_bundle={"df": df_full},
            week_bundle={"df": df_full},
            typologies_bundle=typologies_bundle,
            multisess_bundle=dyn_multisess,
            confronto_settimane_bundle=dyn_settimane,
        )

    render_action_bar(
        meta_items=[
            ("AREA ANALISI", "Medie & Confronti"),
            ("TIPOLOGIE FIR", "10 Archetipi Ufficiali"),
            ("DATI COMBINATI", f"{len(df_full):,} record storici"),
            ("CONFRONTI", "Multi Sessione & Settimane"),
        ],
        pdf_options=pdf_opts_confronti,
        pdf_key="fir_confronti_action_bar_pdf",
        generate_fn=_generate_confronti_pdf,
        filename_fn=lambda codice_sub: f"FIR_Confronti_{codice_sub}.pdf",
    )

    if active_tab == "medie_tipologie_fir":
        _render_tab_medie_tipologie_fir(df_full, t)
    elif active_tab == "confronto_multisessione":
        _render_tab_confronto_multisessione(df_full, status_map, types_map, t)
    elif active_tab == "confronto_settimane":
        _render_tab_confronto_settimane(df_full, players_df, status_map)


# ==============================================================================
# TAB 1: REPORT GENERALE & STORYTELLING DELLA SEDUTA
# ==============================================================================
def build_session_narrative_dict(
    sess_df: pd.DataFrame,
    cur_type: str,
    status_map: dict = None,
    meta: dict = None,
    df_full: pd.DataFrame = None,
) -> dict:
    """
    Costruisce il dizionario strutturato della narrazione esecutiva (Storytelling)
    confrontando la seduta corrente con il benchmark empirico FIR della stessa tipologia.
    Usato in sincrono sia nel cruscotto web che nella generazione del PDF ufficiale.
    """
    if status_map is None:
        status_map = {}
    if meta is None:
        meta = {}

    cur_date_str = meta.get("date_str", "")
    cur_session_name = meta.get("session_name", "")

    # Se status non è ancora associato nel df
    df = sess_df.copy()
    if "player_status" not in df.columns:
        k_sess = f"{cur_date_str}_{cur_session_name}"
        st_over = status_map.get(k_sess, {})
        df["player_status"] = df["player_name"].map(st_over).fillna(df.get("status", "Full"))

    excluded_st = {"MODIFICATO", "MODIFIED", "RTP", "OFF FEET", "NON ATTIVO"}
    st_series = df["player_status"].astype(str).str.strip().str.upper() if "player_status" in df.columns else (df["status"].astype(str).str.strip().str.upper() if "status" in df.columns else pd.Series(["FULL"] * len(df), index=df.index))
    dur_series = df["Tempo"] if "Tempo" in df.columns else (df["duration"] if "duration" in df.columns else pd.Series([1.0] * len(df), index=df.index))
    dur_valid = pd.to_numeric(dur_series, errors="coerce").fillna(0.0) > 0
    active_mask = (~st_series.isin(excluded_st)) & dur_valid
    active_sess = df[active_mask].copy()

    if "department" in active_sess.columns:
        av_cur = active_sess[active_sess["department"] == "Avanti"]
        tq_cur = active_sess[active_sess["department"] == "TreQuarti"]
    elif "dept" in active_sess.columns:
        av_cur = active_sess[active_sess["dept"] == "Avanti"]
        tq_cur = active_sess[active_sess["dept"] == "TreQuarti"]
    else:
        av_cur = active_sess.iloc[0:0]
        tq_cur = active_sess.iloc[0:0]

    # Baseline della tipologia
    base_typ = SESSION_TYPE_BASELINES.get(cur_type, SESSION_TYPE_BASELINES.get("Rugby", SESSION_TYPE_BASELINES["Velocità"]))
    av_base = base_typ.get("Avanti", {})
    tq_base = base_typ.get("TreQuarti", {})

    av_hist_dist = float(av_base.get("distance_m", 4113.0))
    av_hist_run = float(av_base.get("run_dist", 2066.0))
    av_hist_hml = float(av_base.get("hml", 497.0))
    av_hist_hsr18 = float(av_base.get("hsr", 265.0))

    tq_hist_dist = float(tq_base.get("distance_m", 4730.4))
    tq_hist_run = float(tq_base.get("run_dist", 2344.7))
    tq_hist_hml = float(tq_base.get("hml", 698.2))
    tq_hist_hsr20 = float(tq_base.get("hsr", 310.3))

    def _col_mean(sub, *cands):
        for c in cands:
            if c in sub.columns:
                m = pd.to_numeric(sub[c], errors="coerce").mean()
                if pd.notna(m):
                    return float(m)
        return 0.0

    av_cur_dist = _col_mean(av_cur, "distance_m", "Distanza")
    av_cur_run = _col_mean(av_cur, "run_dist", "Run_Dist")
    av_cur_hml = _col_mean(av_cur, "hml_25", "Hml_25")
    av_cur_hsr18 = _col_mean(av_cur, "hsr_18", "HSR_18")

    tq_cur_dist = _col_mean(tq_cur, "distance_m", "Distanza")
    tq_cur_run = _col_mean(tq_cur, "run_dist", "Run_Dist")
    tq_cur_hml = _col_mean(tq_cur, "hml_25", "Hml_25")
    tq_cur_hsr20 = _col_mean(tq_cur, "hsr_20", "HSR_20")

    def delta_pct(cur_v, hist_v):
        if hist_v <= 0:
            return 0.0
        return ((cur_v - hist_v) / hist_v) * 100.0

    av_d_dist = delta_pct(av_cur_dist, av_hist_dist)
    av_d_run = delta_pct(av_cur_run, av_hist_run)
    av_d_hml = delta_pct(av_cur_hml, av_hist_hml)
    av_d_hsr = delta_pct(av_cur_hsr18, av_hist_hsr18)

    tq_d_dist = delta_pct(tq_cur_dist, tq_hist_dist)
    tq_d_run = delta_pct(tq_cur_run, tq_hist_run)
    tq_d_hml = delta_pct(tq_cur_hml, tq_hist_hml)
    tq_d_hsr = delta_pct(tq_cur_hsr20, tq_hist_hsr20)

    team_cur_dist = (av_cur_dist + tq_cur_dist) / 2 if (av_cur_dist and tq_cur_dist) else (av_cur_dist or tq_cur_dist)
    team_hist_dist = (av_hist_dist + tq_hist_dist) / 2
    team_d_dist = delta_pct(team_cur_dist, team_hist_dist)

    if team_d_dist >= 18:
        load_badge = f"🔥 OVERLOAD PEAK (+{team_d_dist:.0f}%)"
        load_color = "#DC2626"
    elif team_d_dist >= 5:
        load_badge = f"⚡ HIGH WORKLOAD (+{team_d_dist:.0f}%)"
        load_color = "#EA580C"
    elif team_d_dist >= -10:
        load_badge = f"🎯 TARGET OPTIMAL ({team_d_dist:+.0f}%)"
        load_color = "#059669"
    else:
        load_badge = f"💧 DELOAD / RECOVERY ({team_d_dist:.0f}%)"
        load_color = "#0284C7"

    vmax_c = "V_max" if "V_max" in df.columns else ("v_max" if "v_max" in df.columns else None)
    top_vmax_row = df.sort_values(vmax_c, ascending=False).iloc[0] if (vmax_c and not df.empty) else None

    hml_c = "Hml_25" if "Hml_25" in df.columns else ("hml_25" if "hml_25" in df.columns else None)
    top_hml_row = df.sort_values(hml_c, ascending=False).iloc[0] if (hml_c and not df.empty) else None

    mod_players = df[df["player_status"].astype(str).str.upper() == "MODIFICATO"]["player_name"].tolist() if "player_status" in df.columns else []
    rtp_players = df[df["player_status"].astype(str).str.upper() == "RTP"]["player_name"].tolist() if "player_status" in df.columns else []

    top_vm_val = float(top_vmax_row[vmax_c]) if (top_vmax_row is not None and vmax_c) else 0.0
    top_vm_pct = float(top_vmax_row.get("V_max_pct", top_vmax_row.get("v_max_pct", 0.0))) if top_vmax_row is not None else 0.0
    top_hml_val = float(top_hml_row[hml_c]) if (top_hml_row is not None and hml_c) else 0.0

    top_speed_str = f"{top_vmax_row['player_name']} ({top_vm_val:.1f} km/h - {top_vm_pct:.0f}% Vmax)" if top_vmax_row is not None else "-"
    top_engine_str = f"{top_hml_row['player_name']} ({top_hml_val:,.0f}m HML)".replace(",", ".") if top_hml_row is not None else "-"
    differenziati_str = f"{len(mod_players) + len(rtp_players)} differenziati ({', '.join(mod_players + rtp_players)})" if (mod_players or rtp_players) else "Nessun differenziato (Tutti Full)"

    story_p = (
        f"Nella seduta di tipologia <b>{cur_type}</b>, il gruppo squadra ha registrato un carico complessivo <b>{'+' if team_d_dist > 0 else ''}{team_d_dist:.1f}%</b> rispetto al volume medio storico di riferimento. "
        f"I <b>TreQuarti</b> hanno totalizzato una media di <b>{tq_cur_dist:,.0f}m</b> di Distanza Totale (<b>{'+' if tq_d_dist > 0 else ''}{tq_d_dist:.1f}%</b> vs benchmark) con un volume di corsa sopra i 6 km/h (Run Dist) pari a <b>{tq_cur_run:,.0f}m ({'+' if tq_d_run > 0 else ''}{tq_d_run:.1f}%)</b> e <b>{tq_cur_hsr20:,.0f}m</b> ad alta velocità (>20 km/h). "
        f"Nel reparto <b>Avanti</b>, il volume di carico metabolico (HML >25.5 W/kg) ha raggiunto <b>{av_cur_hml:,.0f}m ({'+' if av_d_hml > 0 else ''}{av_d_hml:.1f}%)</b>, con una Distanza media di <b>{av_cur_dist:,.0f}m ({'+' if av_d_dist > 0 else ''}{av_d_dist:.1f}%)</b> e <b>{av_cur_hsr18:,.0f}m</b> sopra i 18 km/h."
    )

    kpis = [
        {
            "label": "Distanza Media Seduta",
            "val": f"{int(round(team_cur_dist)):,} m".replace(",", "."),
            "sub": f"{'+' if team_d_dist > 0 else ''}{team_d_dist:.1f}% vs media {cur_type} ({int(round(team_hist_dist)):,}m)".replace(",", "."),
            "color": "#34D399" if team_d_dist >= 0 else "#F87171",
        },
        {
            "label": "High Metabolic Load (HML)",
            "val": f"{int(round((av_cur_hml + tq_cur_hml) / 2)):,} m".replace(",", "."),
            "sub": f"AV: {int(round(av_cur_hml))}m ({'+' if av_d_hml > 0 else ''}{av_d_hml:.0f}%) • TQ: {int(round(tq_cur_hml))}m ({'+' if tq_d_hml > 0 else ''}{tq_d_hml:.0f}%)",
            "color": "#FDE047",
        },
        {
            "label": "Running Distance (>6 km/h)",
            "val": f"{int(round((av_cur_run + tq_cur_run) / 2)):,} m".replace(",", "."),
            "sub": f"AV: {int(round(av_cur_run))}m ({'+' if av_d_run > 0 else ''}{av_d_run:.0f}%) • TQ: {int(round(tq_cur_run))}m ({'+' if tq_d_run > 0 else ''}{tq_d_run:.0f}%)",
            "color": "#38BDF8",
        },
        {
            "label": "High Speed Running (HSR)",
            "val": f"{int(round((av_cur_hsr18 + tq_cur_hsr20) / 2)):,} m".replace(",", "."),
            "sub": f"AV >18: {int(round(av_cur_hsr18))}m ({'+' if av_d_hsr > 0 else ''}{av_d_hsr:.0f}%) • TQ >20: {int(round(tq_cur_hsr20))}m ({'+' if tq_d_hsr > 0 else ''}{tq_d_hsr:.0f}%)",
            "color": "#F472B6",
        },
    ]

    return {
        "cur_type": cur_type,
        "load_badge": load_badge,
        "load_color": load_color,
        "story_text": story_p,
        "top_speed": top_speed_str,
        "top_engine": top_engine_str,
        "differenziati": differenziati_str,
        "kpis": kpis,
        "av_cur": {"Dist": av_cur_dist, "Run": av_cur_run, "Hml": av_cur_hml, "HSR": av_cur_hsr18},
        "av_hist": {"Dist": av_hist_dist, "Run": av_hist_run, "Hml": av_hist_hml, "HSR": av_hist_hsr18},
        "tq_cur": {"Dist": tq_cur_dist, "Run": tq_cur_run, "Hml": tq_cur_hml, "HSR": tq_cur_hsr20},
        "tq_hist": {"Dist": tq_hist_dist, "Run": tq_hist_run, "Hml": tq_hist_hml, "HSR": tq_hist_hsr20},
        "n_active": len(active_sess),
        "n_mod": len(mod_players),
        "n_rtp": len(rtp_players),
    }


def _render_tab_report_seduta_story(df_full: pd.DataFrame, status_map: dict, types_map: dict, ctx: dict, t: dict):
    cur_date_str = ctx["sel_date_str"]
    cur_session_name = ctx["sel_sess_name"]
    cur_type = ctx["cur_type"]

    # Dati sessione corrente: RIGOROSAMENTE solo questa sessione, NON tutta la giornata!
    sess_df = df_full[
        (df_full["date_str"] == cur_date_str) &
        (df_full["session_name"] == cur_session_name)
    ].copy()

    st.caption(f"Analisi focalizzata esclusivamente sulla seduta '{cur_session_name}' ({len(sess_df)} atleti monitorati) — altre sessioni della giornata escluse.")

    # Applica status modificato/rtp
    k_sess = f"{cur_date_str}_{cur_session_name}"
    cur_p_statuses = status_map.get(k_sess, {})
    sess_df["player_status"] = sess_df["player_name"].map(cur_p_statuses).fillna("Full")

    # Giocatori attivi (esclusi Modificato e RTP per il calcolo delle medie)
    excluded_st = {"MODIFICATO", "MODIFIED", "RTP", "OFF FEET", "NON ATTIVO"}
    active_sess = sess_df[
        (~sess_df["player_status"].str.upper().isin(excluded_st)) &
        (sess_df["duration"] > 0)
    ].copy()

    # Calcolo medie reparto per seduta corrente
    av_cur = active_sess[active_sess["dept"] == "Avanti"]
    tq_cur = active_sess[active_sess["dept"] == "TreQuarti"]

    # Benchmark di tipologia: RIGOROSAMENTE vincolato alla stessa tipologia
    base_typ = SESSION_TYPE_BASELINES.get(cur_type, SESSION_TYPE_BASELINES.get("Rugby", SESSION_TYPE_BASELINES["Velocità"]))
    av_base = base_typ.get("Avanti", {})
    tq_base = base_typ.get("TreQuarti", {})

    av_hist_dist = float(av_base.get("distance_m", 4113.0))
    av_hist_run = float(av_base.get("run_dist", 2066.0))
    av_hist_hml = float(av_base.get("hml", 497.0))
    av_hist_hsr18 = float(av_base.get("hsr", 265.0))

    tq_hist_dist = float(tq_base.get("distance_m", 4730.4))
    tq_hist_run = float(tq_base.get("run_dist", 2344.7))
    tq_hist_hml = float(tq_base.get("hml", 698.2))
    tq_hist_hsr20 = float(tq_base.get("hsr", 310.3))

    # Metric averages (con fallback se vuoto)
    av_cur_dist = float(av_cur["distance_m"].mean() or 0.0)
    av_cur_run = float(av_cur["run_dist"].mean() or 0.0)
    av_cur_hml = float(av_cur["hml_25"].mean() or 0.0)
    av_cur_hsr18 = float(av_cur["hsr_18"].mean() or 0.0)
    av_cur_dur = float(av_cur["duration"].mean() or 0.0)

    tq_cur_dist = float(tq_cur["distance_m"].mean() or 0.0)
    tq_cur_run = float(tq_cur["run_dist"].mean() or 0.0)
    tq_cur_hml = float(tq_cur["hml_25"].mean() or 0.0)
    tq_cur_hsr20 = float(tq_cur["hsr_20"].mean() or 0.0)
    tq_cur_dur = float(tq_cur["duration"].mean() or 0.0)


    # Calcolo Delta %
    def delta_pct(cur_v, hist_v):
        if hist_v <= 0:
            return 0.0
        return ((cur_v - hist_v) / hist_v) * 100.0

    av_d_dist = delta_pct(av_cur_dist, av_hist_dist)
    av_d_run = delta_pct(av_cur_run, av_hist_run)
    av_d_hml = delta_pct(av_cur_hml, av_hist_hml)
    av_d_hsr = delta_pct(av_cur_hsr18, av_hist_hsr18)

    tq_d_dist = delta_pct(tq_cur_dist, tq_hist_dist)
    tq_d_run = delta_pct(tq_cur_run, tq_hist_run)
    tq_d_hml = delta_pct(tq_cur_hml, tq_hist_hml)
    tq_d_hsr = delta_pct(tq_cur_hsr20, tq_hist_hsr20)

    # Determinazione Classificazione Storytelling della Seduta
    team_cur_dist = (av_cur_dist + tq_cur_dist) / 2 if (av_cur_dist and tq_cur_dist) else (av_cur_dist or tq_cur_dist)
    team_hist_dist = (av_hist_dist + tq_hist_dist) / 2
    team_d_dist = delta_pct(team_cur_dist, team_hist_dist)

    if team_d_dist >= 18:
        load_badge = "🔥 OVERLOAD PEAK SESSION (+{:.0f}%)".format(team_d_dist)
        load_color = "#DC2626"
    elif team_d_dist >= 5:
        load_badge = "⚡ HIGH WORKLOAD DAY (+{:.0f}%)".format(team_d_dist)
        load_color = "#EA580C"
    elif team_d_dist >= -10:
        load_badge = "🎯 TARGET OPTIMAL SESSION ({:+.0f}%)".format(team_d_dist)
        load_color = "#059669"
    else:
        load_badge = "💧 DELOAD / RECOVERY ({:.0f}%)".format(team_d_dist)
        load_color = "#0284C7"

    # Top Performer della seduta per lo storytelling
    top_vmax_row = sess_df.sort_values("v_max", ascending=False).iloc[0] if not sess_df.empty else None
    top_hml_row = sess_df.sort_values("hml_25", ascending=False).iloc[0] if not sess_df.empty else None
    mod_players = sess_df[sess_df["player_status"].str.upper() == "MODIFICATO"]["player_name"].tolist()
    rtp_players = sess_df[sess_df["player_status"].str.upper() == "RTP"]["player_name"].tolist()

    hist_type_df = df_full[df_full["assigned_type"] == cur_type]
    n_type_sess = len(hist_type_df["session_name"].dropna().unique())

    # ==========================================================================
    # 1. STORYTELLING DELLA SEDUTA (MODO NUOVO ED EFFICACE DI RACCONTARE)
    # ==========================================================================
    story_card_html = f"""
        <div style="background:linear-gradient(135deg, #031926 0%, #002B49 55%, #0066B2 100%); border-radius:14px; border:2px solid #D4AF37; padding:20px 24px; margin-bottom:22px; box-shadow:0 8px 24px rgba(3,25,38,0.30); color:#FFFFFF;">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px; margin-bottom:14px; border-bottom:1px solid rgba(212,175,55,0.3); padding-bottom:12px;">
                <div>
                    <div style="display:flex; align-items:center; gap:10px;">
                        <span style="font-size:0.72rem; font-weight:800; letter-spacing:0.12em; text-transform:uppercase; color:#D4AF37;">
                            FEDERAZIONE ITALIANA RUGBY • SPORT SCIENCE STORYTELLING
                        </span>
                        <span style="background:{load_color}; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:2px 8px; border-radius:999px;">
                            {load_badge}
                        </span>
                    </div>
                    <h2 style="margin:4px 0 0 0; font-size:1.70rem; font-weight:800; letter-spacing:-0.02em; color:#FFFFFF;">
                        Report Allenamento: {cur_session_name}
                    </h2>
                    <div style="font-size:0.80rem; color:#BAE6FD; margin-top:2px;">
                        Data: <b>{cur_date_str}</b> • Tipologia Assegnata: <b style="color:#D4AF37;">{cur_type}</b> • Benchmark di Confronto: <b>{n_type_sess} sedute storiche FIR ({cur_type})</b>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:0.72rem; color:#94A3B8; text-transform:uppercase; letter-spacing:0.05em;">Atleti Monitorati</div>
                    <div style="font-size:1.6rem; font-weight:800; color:#FFFFFF; line-height:1.1;">{len(active_sess)} <span style="font-size:0.85rem; font-weight:600; color:#38BDF8;">Full</span></div>
                    <div style="font-size:0.70rem; color:#FCD34D;">{f'{len(mod_players)} Modificato' if mod_players else ''} {f'• {len(rtp_players)} RTP' if rtp_players else ''}</div>
                </div>
            </div>

            <!-- Narrazione Esecutiva (Cosa è Successo) -->
            <div style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); border-radius:10px; padding:14px 18px; margin-bottom:16px;">
                <div style="font-size:0.72rem; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; color:#D4AF37; margin-bottom:6px;">
                    🎙️ RACCONTO DELLA SEDUTA & HIGHLIGHT TATTICO-FISICI
                </div>
                <div style="font-size:0.92rem; line-height:1.55; color:#F1F5F9;">
                    Nella seduta odierna di tipologia <b>{cur_type}</b>, il gruppo squadra ha registrato un carico complessivo <b>{'+' if team_d_dist > 0 else ''}{team_d_dist:.1f}%</b> rispetto al volume medio storico di riferimento.
                    I <b>TreQuarti</b> hanno totalizzato una media di <b>{tq_cur_dist:,.0f}m</b> di Distanza Totale (<b>{'+' if tq_d_dist > 0 else ''}{tq_d_dist:.1f}%</b> vs benchmark) con un volume di corsa sopra i 6 km/h (Run Dist) pari a <b>{tq_cur_run:,.0f}m ({'+' if tq_d_run > 0 else ''}{tq_d_run:.1f}%)</b> e <b>{tq_cur_hsr20:,.0f}m</b> ad alta velocità (&gt;20 km/h).
                    Nel reparto <b>Avanti</b>, il volume di carico metabolico (HML &gt;25.5 W/kg) ha raggiunto <b>{av_cur_hml:,.0f}m ({'+' if av_d_hml > 0 else ''}{av_d_hml:.1f}%)</b>, con una Distanza media di <b>{av_cur_dist:,.0f}m ({'+' if av_d_dist > 0 else ''}{av_d_dist:.1f}%)</b> e <b>{av_cur_hsr18:,.0f}m</b> sopra i 18 km/h.
                </div>
                <div style="display:flex; flex-wrap:wrap; gap:16px; margin-top:12px; font-size:0.80rem; border-top:1px dashed rgba(255,255,255,0.15); padding-top:10px;">
                    <div style="color:#BAE6FD;">
                        ⚡ <b>Top Speed Seduta:</b> {f"{top_vmax_row['player_name']} ({top_vmax_row['v_max']:.1f} km/h - {top_vmax_row['v_max_pct']:.0f}% Vmax)" if top_vmax_row is not None else "-"}
                    </div>
                    <div style="color:#FDE047;">
                        🔥 <b>Top Metabolic Engine:</b> {f"{top_hml_row['player_name']} ({top_hml_row['hml_25']:.0f}m HML)" if top_hml_row is not None else "-"}
                    </div>
                    <div style="color:#FCA5A5;">
                        🛡️ <b>Gestione Differenziati:</b> {f"{len(mod_players) + len(rtp_players)} atleti esclusi dalle medie ({', '.join(mod_players + rtp_players)})" if (mod_players or rtp_players) else "Nessun differenziato (Tutti Full)"}
                    </div>
                </div>
            </div>

            <!-- Sintesi Metriche a 4 Colonne con Delta -->
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:12px;">
                <div style="background:rgba(255,255,255,0.08); border-radius:8px; padding:10px 14px; border:1px solid rgba(255,255,255,0.12);">
                    <div style="font-size:0.68rem; color:#93C5FD; font-weight:700; text-transform:uppercase;">Distanza Media Seduta</div>
                    <div style="font-size:1.35rem; font-weight:800; color:#FFFFFF;">{team_cur_dist:,.0f} m</div>
                    <div style="font-size:0.74rem; font-weight:700; color:{'#34D399' if team_d_dist >= 0 else '#F87171'};">
                        {'+' if team_d_dist > 0 else ''}{team_d_dist:.1f}% vs media {cur_type} ({team_hist_dist:,.0f}m)
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.08); border-radius:8px; padding:10px 14px; border:1px solid rgba(255,255,255,0.12);">
                    <div style="font-size:0.68rem; color:#93C5FD; font-weight:700; text-transform:uppercase;">High Metabolic Load (HML)</div>
                    <div style="font-size:1.35rem; font-weight:800; color:#FDE047;">{((av_cur_hml + tq_cur_hml)/2):,.0f} m</div>
                    <div style="font-size:0.74rem; font-weight:700; color:#BAE6FD;">
                        AV: {av_cur_hml:,.0f}m ({'+' if av_d_hml > 0 else ''}{av_d_hml:.0f}%) • TQ: {tq_cur_hml:,.0f}m ({'+' if tq_d_hml > 0 else ''}{tq_d_hml:.0f}%)
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.08); border-radius:8px; padding:10px 14px; border:1px solid rgba(255,255,255,0.12);">
                    <div style="font-size:0.68rem; color:#93C5FD; font-weight:700; text-transform:uppercase;">Running Distance (&gt;6 km/h)</div>
                    <div style="font-size:1.35rem; font-weight:800; color:#38BDF8;">{((av_cur_run + tq_cur_run)/2):,.0f} m</div>
                    <div style="font-size:0.74rem; font-weight:700; color:#BAE6FD;">
                        AV: {av_cur_run:,.0f}m ({'+' if av_d_run > 0 else ''}{av_d_run:.0f}%) • TQ: {tq_cur_run:,.0f}m ({'+' if tq_d_run > 0 else ''}{tq_d_run:.0f}%)
                    </div>
                </div>
                <div style="background:rgba(255,255,255,0.08); border-radius:8px; padding:10px 14px; border:1px solid rgba(255,255,255,0.12);">
                    <div style="font-size:0.68rem; color:#93C5FD; font-weight:700; text-transform:uppercase;">High Speed Running (HSR)</div>
                    <div style="font-size:1.35rem; font-weight:800; color:#F472B6;">{((av_cur_hsr18 + tq_cur_hsr20)/2):,.0f} m</div>
                    <div style="font-size:0.74rem; font-weight:700; color:#BAE6FD;">
                        AV &gt;18: {av_cur_hsr18:,.0f}m ({'+' if av_d_hsr > 0 else ''}{av_d_hsr:.0f}%) • TQ &gt;20: {tq_cur_hsr20:,.0f}m ({'+' if tq_d_hsr > 0 else ''}{tq_d_hsr:.0f}%)
                    </div>
                </div>
            </div>
        </div>
    """
    _clean_and_render_html(story_card_html)

    # ==========================================================================
    # 2. CONFRONTO CON MEDIA ALLENAMENTO (PAGINA 1 PDF)
    # ==========================================================================
    st.markdown("#### Confronto con Media Allenamento della stessa Tipologia")
    st.caption(f"Confronto metriche aggregate per reparto: Seduta Corrente vs Media Storica di tutte le sedute FIR '{cur_type}'.")

    col_chart_av, col_chart_tq = st.columns(2)

    with col_chart_av:
        fig_av = _build_department_comparison_barchart(
            dept_name="AVANTI",
            cur_vals={"Dist": av_cur_dist, "Run": av_cur_run, "Hml": av_cur_hml, "HSR": av_cur_hsr18},
            hist_vals={"Dist": av_hist_dist, "Run": av_hist_run, "Hml": av_hist_hml, "HSR": av_hist_hsr18},
            hsr_label="HSR >18",
            primary_color="#0066B2",
            benchmark_color="#94A3B8",
            tipology=cur_type,
        )
        st.plotly_chart(fig_av, use_container_width=True)

    with col_chart_tq:
        fig_tq = _build_department_comparison_barchart(
            dept_name="TREQUARTI",
            cur_vals={"Dist": tq_cur_dist, "Run": tq_cur_run, "Hml": tq_cur_hml, "HSR": tq_cur_hsr20},
            hist_vals={"Dist": tq_hist_dist, "Run": tq_hist_run, "Hml": tq_hist_hml, "HSR": tq_hist_hsr20},
            hsr_label="HSR >20",
            primary_color="#D97706",
            benchmark_color="#94A3B8",
            tipology=cur_type,
        )
        st.plotly_chart(fig_tq, use_container_width=True)

    st.markdown("---")

    # ==========================================================================
    # 3. TOP RANKING PLAYERS (LEADERBOARD A 5 BLOCCHI COME PAGINA 1 PDF)
    # ==========================================================================
    st.markdown("#### TOP RANKING PLAYERS — Classifiche di Seduta per Reparto")
    st.caption("I 5 atleti con i valori più alti registrati nella seduta per ciascun parametro chiave (TreQuarti a sinistra, Avanti a destra).")

    # Preparazione classifiche top 5
    tq_full = active_sess[active_sess["dept"] == "TreQuarti"]
    av_full = active_sess[active_sess["dept"] == "Avanti"]

    # 1. Top Hml
    top_hml_tq = tq_full.sort_values("hml_25", ascending=False).head(5)[["player_name", "hml_25"]].values.tolist()
    top_hml_av = av_full.sort_values("hml_25", ascending=False).head(5)[["player_name", "hml_25"]].values.tolist()

    # 2. Top HSR
    top_hsr_tq = tq_full.sort_values("hsr_20", ascending=False).head(5)[["player_name", "hsr_20"]].values.tolist()
    top_hsr_av = av_full.sort_values("hsr_18", ascending=False).head(5)[["player_name", "hsr_18"]].values.tolist()

    # 3. Top Vmax
    top_vmax_tq = tq_full.sort_values("v_max", ascending=False).head(5)[["player_name", "v_max"]].values.tolist()
    top_vmax_av = av_full.sort_values("v_max", ascending=False).head(5)[["player_name", "v_max"]].values.tolist()

    # 4. Top VHml (TreQuarti >50W, Avanti >40W)
    top_vhml_tq = tq_full.sort_values("vhml_50", ascending=False).head(5)[["player_name", "vhml_50"]].values.tolist()
    top_vhml_av = av_full.sort_values("vhml_40", ascending=False).head(5)[["player_name", "vhml_40"]].values.tolist()

    # 5. Top VHSR >25 (TQ) vs Top Power Events (AV)
    top_vhsr_tq = tq_full.sort_values("vhsr_25", ascending=False).head(5)[["player_name", "vhsr_25"]].values.tolist()
    top_pev_av = av_full.sort_values("power_events", ascending=False).head(5)[["player_name", "power_events"]].values.tolist()

    # Renderizzazione delle 5 coppie di barre orizzontali
    ranking_pairs = [
        ("Top Hml TQ", top_hml_tq, "m", "#93C5FD", "Top Hml AV", top_hml_av, "m", "#C4B5FD"),
        ("Top HSR 20 TQ", top_hsr_tq, "m", "#FCA5A5", "Top HSR 18 AV", top_hsr_av, "m", "#F87171"),
        ("Top Vmax TQ", top_vmax_tq, "km/h", "#F472B6", "TOP VMAX AV", top_vmax_av, "km/h", "#EC4899"),
        ("Top VHml > 50W TQ", top_vhml_tq, "m", "#7DD3FC", "Top VHml > 40W AV", top_vhml_av, "m", "#38BDF8"),
        ("Top VHSR > 25 TQ", top_vhsr_tq, "m", "#6EE7B7", "Top POWER Events AV", top_pev_av, "evt", "#34D399"),
    ]

    for title_tq, data_tq, unit_tq, color_tq, title_av, data_av, unit_av, color_av in ranking_pairs:
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            _render_single_ranking_card(title_tq, data_tq, unit_tq, color_tq)
        with r_col2:
            _render_single_ranking_card(title_av, data_av, unit_av, color_av)
        st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    # ==========================================================================
    # 4. TABELLA COMPLETA GIOCATORI DELLA SEDUTA
    # ==========================================================================
    with st.expander("📋 Visualizza Tabella Completa Atleti della Seduta", expanded=False):
        table_df = sess_df[[
            "player_name", "dept", "role_clean", "player_status", "duration", "distance_m",
            "m_per_min", "run_dist", "hml_25", "vhml_40", "vhml_50", "power_events",
            "hsr_18", "hsr_20", "vhsr_25", "v_max", "v_max_pct"
        ]].copy()

        table_df.columns = [
            "Atleta", "Reparto", "Ruolo", "Stato Seduta", "Tempo (min)", "Distanza (m)",
            "m/min", "Run Dist (m)", "HML 25.5W", "VHML 40W", "VHML 50W", "Power Evt",
            "HSR >18", "HSR >20", "VHSR >25", "Vmax (km/h)", "% Vmax"
        ]

        st.dataframe(
            table_df.sort_values(["Reparto", "Distanza (m)"], ascending=[True, False]),
            use_container_width=True,
            hide_index=True,
        )

        csv_data = table_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Scarica Dati Seduta (CSV)",
            data=csv_data,
            file_name=f"Report_FIR_{cur_date_str}_{cur_session_name}.csv",
            mime="text/csv",
        )


def _render_single_ranking_card(title: str, items: list, unit: str, bar_color: str):
    """Renderizza una card di classifica orizzontale a barre progressive in stile FIR."""
    if not items:
        st.caption(f"{title}: Nessun dato")
        return

    max_val = max([it[1] for it in items]) if items and max([it[1] for it in items]) > 0 else 1.0

    bars_html = ""
    for name, val in items:
        val_f = float(val or 0.0)
        pct = min(100.0, max(8.0, (val_f / max_val) * 100.0))
        val_str = f"{val_f:.1f}" if unit == "km/h" else f"{val_f:,.0f}"

        bars_html += f"""
        <div style="display:flex; align-items:center; margin-bottom:5px; font-size:0.75rem;">
            <div style="width:130px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:600; color:#1E293B;">
                {name}
            </div>
            <div style="flex:1; background:#F1F5F9; border-radius:4px; height:18px; margin:0 8px; position:relative; overflow:hidden;">
                <div style="width:{pct}%; background:{bar_color}; height:100%; border-radius:4px;"></div>
            </div>
            <div style="width:58px; text-align:right; font-weight:800; color:#0F172A;">
                {val_str} <span style="font-size:0.62rem; color:#64748B; font-weight:600;">{unit}</span>
            </div>
        </div>
        """

    card_html = f"""
    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
        <div style="font-size:0.72rem; font-weight:800; text-transform:uppercase; letter-spacing:0.06em; color:#0F172A; margin-bottom:8px; border-bottom:1.5px solid {bar_color}; padding-bottom:3px;">
            {title}
        </div>
        {bars_html}
    </div>
    """
    _clean_and_render_html(card_html)


def _build_department_comparison_barchart(
    dept_name: str,
    cur_vals: dict,
    hist_vals: dict,
    hsr_label: str,
    primary_color: str,
    benchmark_color: str,
    tipology: str,
) -> go.Figure:
    """Costruisce il grafico a barre verticali raggruppate per reparto (come Pagina 1 PDF)."""
    metrics = ["Dist", "Run", "Hml", "HSR"]
    labels = ["Distanza", "Run Dist", "Hml 25.5", hsr_label]

    cur_data = [cur_vals["Dist"], cur_vals["Run"], cur_vals["Hml"], cur_vals["HSR"]]
    hist_data = [hist_vals["Dist"], hist_vals["Run"], hist_vals["Hml"], hist_vals["HSR"]]

    fig = go.Figure()

    # Barra Seduta Corrente
    fig.add_trace(
        go.Bar(
            name=f"{dept_name} (Oggi)",
            x=labels,
            y=cur_data,
            text=[f"{v:,.0f}" if v > 0 else "-" for v in cur_data],
            textposition="outside",
            textfont=dict(size=11, color="#0F172A", family="Arial Black"),
            marker=dict(color=primary_color, line=dict(color="#0F172A", width=1.5)),
        )
    )

    # Barra Media Benchmark Tipologia
    fig.add_trace(
        go.Bar(
            name=f"AVG {dept_name} ({tipology})",
            x=labels,
            y=hist_data,
            text=[f"{v:,.0f}" if v > 0 else "-" for v in hist_data],
            textposition="outside",
            textfont=dict(size=11, color="#475569", family="Arial"),
            marker=dict(color=benchmark_color, line=dict(color="#64748B", width=1)),
        )
    )

    max_y = max(max(cur_data), max(hist_data)) * 1.18

    fig.update_layout(
        title=dict(
            text=f"<b>{dept_name} — CONFRONTO CON MEDIA ALLENAMENTO</b>",
            font=dict(size=13, color="#0F172A", family="Inter, sans-serif"),
            x=0.02,
        ),
        barmode="group",
        bargap=0.25,
        bargroupgap=0.10,
        yaxis=dict(
            range=[0, max_y],
            title="Metri (m)",
            gridcolor="#E2E8F0",
            zerolinecolor="#94A3B8",
        ),
        xaxis=dict(
            tickfont=dict(size=11, color="#0F172A", family="Arial Black"),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
        height=320,
        margin=dict(l=40, r=20, t=55, b=30),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )

    return fig


# ==============================================================================
# TAB 2: MEDIE TIPOLOGIE DI ALLENAMENTO FIR (DATI ESCLUSIVI NAZIONALE MAGGIORE)
# ==============================================================================
def get_fir_typologies_benchmark_summary(df_full: pd.DataFrame) -> list[dict]:
    """
    Estrae il riepilogo tabellare aggregato delle 10 tipologie FIR per l'esportazione PDF.
    """
    clean_df = df_full[df_full["duration"] > 10].copy() if not df_full.empty else pd.DataFrame()
    if clean_df.empty:
        return []
    if "assigned_type" not in clean_df.columns:
        from utils import get_fir_session_types, detect_fir_session_type
        types_map = get_fir_session_types()
        def _get_t(row):
            k = f"{row.get('date_str', '')}_{row.get('session_name', '')}"
            return types_map.get(k) or detect_fir_session_type(row.get("session_name", ""))
        clean_df["assigned_type"] = clean_df.apply(_get_t, axis=1)

    ordered_typologies = ["Volume", "Velocità", "Rugby", "Team run", "Clarity", "Reparto", "Extra", "Lavoro fisico", "Match", "RTP"]

    res = []
    for t_name in ordered_typologies:
        sub_t = clean_df[clean_df["assigned_type"] == t_name].copy()
        n_sess = sub_t["session_name"].nunique() if not sub_t.empty else 0
        if not sub_t.empty:
            sub_dept = sub_t["department"] if "department" in sub_t.columns else sub_t.get("dept", pd.Series(["Avanti"] * len(sub_t), index=sub_t.index))
            av = sub_t[sub_dept == "Avanti"]
            tq = sub_t[sub_dept == "TreQuarti"]
        else:
            av = pd.DataFrame()
            tq = pd.DataFrame()

        def _m(s, *cols):
            for c in cols:
                if c in s.columns:
                    v = pd.to_numeric(s[c], errors="coerce").mean()
                    if pd.notna(v):
                        return float(v)
            return 0.0

        res.append({
            "typology": t_name,
            "n_sess": f"{n_sess}" if n_sess > 0 else "0",
            "av_dist": f"{int(round(_m(av, 'distance_m', 'Distanza'))):,}".replace(",", "."),
            "av_mmin": f"{_m(av, 'm_per_min', 'm_min'):.0f}",
            "av_run": f"{int(round(_m(av, 'run_dist', 'Run_Dist', 'run_distance_m'))):,}".replace(",", "."),
            "av_hml": f"{int(round(_m(av, 'hml_25', 'Hml_25', 'hml_distance_m'))):,}".replace(",", "."),
            "av_hsr": f"{int(round(_m(av, 'hsr_18', 'HSR_18', 'hsr_distance_m'))):,}".replace(",", "."),
            "tq_dist": f"{int(round(_m(tq, 'distance_m', 'Distanza'))):,}".replace(",", "."),
            "tq_mmin": f"{_m(tq, 'm_per_min', 'm_min'):.0f}",
            "tq_run": f"{int(round(_m(tq, 'run_dist', 'Run_Dist', 'run_distance_m'))):,}".replace(",", "."),
            "tq_hml": f"{int(round(_m(tq, 'hml_25', 'Hml_25', 'hml_distance_m'))):,}".replace(",", "."),
            "tq_hsr": f"{int(round(_m(tq, 'hsr_20', 'HSR_20', 'hsr_distance_m'))):,}".replace(",", "."),
        })
    return res


def build_fir_typologies_bundle(df_raw: pd.DataFrame, players_df: pd.DataFrame = None, types_map: dict = None) -> dict:
    """
    Costruisce il bundle per il Report Confronto Sessioni & Benchmark Medie Tipologie FIR:
    restituisce sia la tabella riassuntiva (dati reali) sia i grafici Plotly per il PDF e la vista web.
    """
    if players_df is None:
        players_df = utils.get_players_df()
    if types_map is None:
        types_map = utils.get_fir_session_types()

    df_full = _prepare_fir_data_with_metrics(df_raw, players_df, types_map)
    typ_summary = get_fir_typologies_benchmark_summary(df_full)

    clean_df = df_full[df_full["duration"] > 10].copy()
    ordered_typologies = ["Volume", "Velocità", "Rugby", "Team run", "Clarity", "Reparto", "Extra", "Lavoro fisico", "Match", "RTP"]

    stats_list = []
    for t_name in ordered_typologies:
        sub_t = clean_df[clean_df["assigned_type"] == t_name]
        if sub_t.empty:
            continue
        av = sub_t[sub_t["dept"] == "Avanti"]
        tq = sub_t[sub_t["dept"] == "TreQuarti"]
        stats_list.append({
            "tipologia": t_name,
            "av_dist": float(av["distance_m"].mean() or 0.0),
            "tq_dist": float(tq["distance_m"].mean() or 0.0),
            "av_hml": float(av["hml_25"].mean() or 0.0),
            "tq_hml": float(tq["hml_25"].mean() or 0.0),
            "av_hsr": float(av["hsr_18"].mean() or 0.0),
            "tq_hsr": float(tq["hsr_20"].mean() or 0.0),
        })

    typs_plot = [r["tipologia"] for r in stats_list]

    # 1. Distanza Totale per Reparto
    fig_dist = go.Figure()
    fig_dist.add_trace(go.Bar(
        name="Avanti",
        x=typs_plot,
        y=[r["av_dist"] for r in stats_list],
        marker_color="#0066B2",
        text=[f"{r['av_dist']:.0f}m" for r in stats_list],
        textposition="auto",
    ))
    fig_dist.add_trace(go.Bar(
        name="TreQuarti",
        x=typs_plot,
        y=[r["tq_dist"] for r in stats_list],
        marker_color="#D97706",
        text=[f"{r['tq_dist']:.0f}m" for r in stats_list],
        textposition="auto",
    ))
    fig_dist.update_layout(
        title="<b>Distanza Totale Media (m) per Reparto (10 Tipologie FIR)</b>",
        barmode="group",
        height=330,
        margin=dict(l=35, r=20, t=45, b=40),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        yaxis=dict(gridcolor="#E2E8F0", title="Distanza (m)"),
        xaxis=dict(tickangle=-25),
    )

    # 2. HML e HSR
    fig_hml = go.Figure()
    fig_hml.add_trace(go.Bar(
        name="HML Avanti (>25.5)",
        x=typs_plot,
        y=[r["av_hml"] for r in stats_list],
        marker_color="#38BDF8",
        text=[f"{r['av_hml']:.0f}" for r in stats_list],
        textposition="auto",
    ))
    fig_hml.add_trace(go.Bar(
        name="HML TreQuarti (>25.5)",
        x=typs_plot,
        y=[r["tq_hml"] for r in stats_list],
        marker_color="#FBBF24",
        text=[f"{r['tq_hml']:.0f}" for r in stats_list],
        textposition="auto",
    ))
    fig_hml.add_trace(go.Scatter(
        name="HSR TQ (>20 km/h)",
        x=typs_plot,
        y=[r["tq_hsr"] for r in stats_list],
        mode="lines+markers",
        line=dict(color="#DC2626", width=2.5),
        marker=dict(size=7),
    ))
    fig_hml.add_trace(go.Scatter(
        name="HSR AV (>18 km/h)",
        x=typs_plot,
        y=[r["av_hsr"] for r in stats_list],
        mode="lines+markers",
        line=dict(color="#059669", width=2.5, dash="dot"),
        marker=dict(size=7),
    ))
    fig_hml.update_layout(
        title="<b>Carico Metabolico HML (>25.5 W/kg) e High Speed Running (HSR)</b>",
        barmode="group",
        height=330,
        margin=dict(l=35, r=20, t=45, b=40),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        yaxis=dict(gridcolor="#E2E8F0", title="Metri (m)"),
        xaxis=dict(tickangle=-25),
    )

    return {
        "typologies_data": typ_summary,
        "fig_dist": fig_dist,
        "fig_hml": fig_hml,
    }


def _render_tab_medie_tipologie_fir(df_full: pd.DataFrame, t: dict):
    clean_df = df_full[df_full["duration"] > 10].copy()

    total_gps_records = len(clean_df)
    total_fir_sessions = clean_df["session_name"].nunique()

    # Intestazione Ufficiale FIR
    _clean_and_render_html(f"""
    <div style="background:linear-gradient(135deg, #002B49 0%, #0066B2 100%); border-radius:12px; border:2px solid #D4AF37; padding:18px 22px; margin-bottom:18px; color:#FFFFFF; box-shadow:0 6px 16px rgba(0,0,0,0.25);">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
                <div style="font-size:0.70rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">
                    FEDERAZIONE ITALIANA RUGBY &bull; SPORT SCIENCE &amp; ANALYTICS
                </div>
                <h2 style="margin:3px 0 0 0; font-size:1.65rem; font-weight:800; color:#FFFFFF;">
                    Medie Storiche Tipologie di Allenamento FIR
                </h2>
                <div style="font-size:0.80rem; color:#E0F2FE; margin-top:3px;">
                    Benchmark calcolato <b>esclusivamente</b> sull'archivio GPS ufficiale della Nazionale Maggiore FIR (<b>{total_fir_sessions} sedute</b>, <b>{total_gps_records:,} rilevazioni individuali</b>)
                </div>
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap;">
                <span style="background:rgba(212,175,55,0.22); border:1px solid #D4AF37; color:#FDE047; padding:4px 10px; border-radius:6px; font-weight:800; font-size:0.75rem;">
                    ⚡ HSR FIR: &gt;18 km/h (Avanti) &bull; &gt;20 km/h (TreQuarti)
                </span>
                <span style="background:rgba(255,255,255,0.12); color:#FFFFFF; padding:4px 10px; border-radius:6px; font-weight:700; font-size:0.75rem;">
                    🔥 VHML: &gt;40 W/kg (Avanti) &bull; &gt;50 W/kg (TreQuarti)
                </span>
            </div>
        </div>
    </div>
    """)

    # Filtro Reparto
    f_c1, f_c2 = st.columns([2.2, 1.0])
    rep_view = f_c1.radio(
        "Modalità Visualizzazione Reparto:",
        ["Avanti vs TreQuarti (Dettaglio Comparato)", "Solo Reparto Avanti", "Solo Reparto TreQuarti", "Squadra Complessiva"],
        horizontal=True,
        key="fir_typ_rep_view_radio",
    )
    exclude_differenziati = f_c2.checkbox("Escludi Differenziati (RTP / Modificato)", value=True, key="chk_excl_diff_typ")

    if exclude_differenziati and "player_status" in clean_df.columns:
        analysis_df = clean_df[~clean_df["player_status"].str.upper().isin({"MODIFICATO", "MODIFIED", "RTP", "OFF FEET", "NON ATTIVO"})].copy()
    else:
        analysis_df = clean_df.copy()

    # Tipologie FIR Ufficiali
    ordered_typologies = ["Volume", "Velocità", "Rugby", "Team run", "Clarity", "Reparto", "Extra", "Lavoro fisico", "Match", "RTP"]
    type_badge_colors = {
        "Volume": ("#7C3AED", "#EDE9FE"),
        "Velocità": ("#D97706", "#FEF3C7"),
        "Rugby": ("#0066B2", "#E0F2FE"),
        "Team run": ("#059669", "#D1FAE5"),
        "Clarity": ("#0284C7", "#E0F2FE"),
        "Reparto": ("#0D9488", "#CCFBF1"),
        "Extra": ("#475569", "#F1F5F9"),
        "Lavoro fisico": ("#B45309", "#FFEDD5"),
        "Match": ("#DC2626", "#FEE2E2"),
        "RTP": ("#4338CA", "#E0E7FF"),
    }

    # Calcolo metriche per tipologia
    stats_list = []
    for t_name in ordered_typologies:
        sub_t = analysis_df[analysis_df["assigned_type"] == t_name]
        if sub_t.empty:
            continue
        n_sess = sub_t["session_name"].nunique()
        av = sub_t[sub_t["dept"] == "Avanti"]
        tq = sub_t[sub_t["dept"] == "TreQuarti"]

        stats_list.append({
            "tipologia": t_name,
            "n_sess": n_sess,
            "tot_atleti": len(sub_t),
            "av_atleti": len(av),
            "tq_atleti": len(tq),
            # Durata
            "dur_tot": float(sub_t["duration"].mean() or 0),
            "av_dur": float(av["duration"].mean() or 0),
            "tq_dur": float(tq["duration"].mean() or 0),
            # Distanza
            "dist_tot": float(sub_t["distance_m"].mean() or 0),
            "av_dist": float(av["distance_m"].mean() or 0),
            "tq_dist": float(tq["distance_m"].mean() or 0),
            # Intensità m/min
            "m_min_tot": float(sub_t["m_per_min"].mean() or 0),
            "av_m_min": float(av["m_per_min"].mean() or 0),
            "tq_m_min": float(tq["m_per_min"].mean() or 0),
            # Run Dist >6 km/h
            "run_tot": float(sub_t["run_dist"].mean() or 0),
            "av_run": float(av["run_dist"].mean() or 0),
            "tq_run": float(tq["run_dist"].mean() or 0),
            # HML >25.5 W/kg
            "hml_tot": float(sub_t["hml_25"].mean() or 0),
            "av_hml": float(av["hml_25"].mean() or 0),
            "tq_hml": float(tq["hml_25"].mean() or 0),
            # HSR (>18 Avanti / >20 TreQuarti)
            "av_hsr": float(av["hsr_18"].mean() or 0),
            "tq_hsr": float(tq["hsr_20"].mean() or 0),
            "tot_hsr": float(sub_t["hsr_18"].mean() or 0),
            # VHML (>40 Avanti / >50 TreQuarti)
            "av_vhml": float(av["vhml_40"].mean() or 0),
            "tq_vhml": float(tq["vhml_50"].mean() or 0),
            "tot_vhml": float(sub_t["vhml_40"].mean() or 0),
            # Vmax
            "av_vmax": float(av["v_max"].mean() or 0),
            "tq_vmax": float(tq["v_max"].mean() or 0),
            "tot_vmax": float(sub_t["v_max"].mean() or 0),
            # Power events
            "av_pe": float(av["power_events"].mean() or 0),
            "tq_pe": float(tq["power_events"].mean() or 0),
            "tot_pe": float(sub_t["power_events"].mean() or 0),
        })

    if not stats_list:
        st.warning("Nessun dato FIR disponibile per le tipologie selezionate.")
        return

    # Costruzione Tabella HTML
    table_rows_html = ""
    for r in stats_list:
        tp = r["tipologia"]
        fg_c, bg_c = type_badge_colors.get(tp, ("#0066B2", "#E0F2FE"))
        badge_html = f"<span style='background:{bg_c}; color:{fg_c}; padding:3px 9px; border-radius:6px; font-weight:800; font-size:0.76rem; border:1px solid {fg_c};'>{tp}</span>"

        if rep_view == "Avanti vs TreQuarti (Dettaglio Comparato)":
            table_rows_html += f"""
            <tr style='border-bottom:1px solid #CBD5E1;'>
                <td rowspan='2' style='padding:8px 10px; font-weight:800; vertical-align:middle; background:#F8FAFC;'>
                    {badge_html}
                    <div style='font-size:0.68rem; color:#64748B; margin-top:4px;'>{r['n_sess']} Sedute FIR</div>
                </td>
                <td style='padding:6px 10px; font-weight:700; color:#002B49; background:#EFF6FF;'>AVANTI</td>
                <td style='padding:6px 10px; text-align:center;'>{r['av_atleti']}</td>
                <td style='padding:6px 10px; text-align:center;'>{r['av_dur']:.0f}'</td>
                <td style='padding:6px 10px; text-align:right; font-weight:800; color:#002B49;'>{r['av_dist']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:700; color:#0284C7;'>{r['av_m_min']:.1f}</td>
                <td style='padding:6px 10px; text-align:right;'>{r['av_run']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:700; color:#D97706;'>{r['av_hml']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:800; color:#059669;'>{r['av_hsr']:,.0f}m <span style='font-size:0.65rem; color:#64748B;'>>18</span></td>
                <td style='padding:6px 10px; text-align:right;'>{r['av_vhml']:,.0f}m <span style='font-size:0.65rem; color:#64748B;'>>40</span></td>
                <td style='padding:6px 10px; text-align:right; font-weight:700;'>{r['av_vmax']:.1f}</td>
                <td style='padding:6px 10px; text-align:right;'>{r['av_pe']:.0f}</td>
            </tr>
            <tr style='border-bottom:2px solid #94A3B8;'>
                <td style='padding:6px 10px; font-weight:700; color:#B45309; background:#FEF3C7;'>TREQUARTI</td>
                <td style='padding:6px 10px; text-align:center;'>{r['tq_atleti']}</td>
                <td style='padding:6px 10px; text-align:center;'>{r['tq_dur']:.0f}'</td>
                <td style='padding:6px 10px; text-align:right; font-weight:800; color:#002B49;'>{r['tq_dist']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:700; color:#0284C7;'>{r['tq_m_min']:.1f}</td>
                <td style='padding:6px 10px; text-align:right;'>{r['tq_run']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:700; color:#D97706;'>{r['tq_hml']:,.0f}m</td>
                <td style='padding:6px 10px; text-align:right; font-weight:800; color:#059669;'>{r['tq_hsr']:,.0f}m <span style='font-size:0.65rem; color:#64748B;'>>20</span></td>
                <td style='padding:6px 10px; text-align:right;'>{r['tq_vhml']:,.0f}m <span style='font-size:0.65rem; color:#64748B;'>>50</span></td>
                <td style='padding:6px 10px; text-align:right; font-weight:700;'>{r['tq_vmax']:.1f}</td>
                <td style='padding:6px 10px; text-align:right;'>{r['tq_pe']:.0f}</td>
            </tr>
            """
        elif rep_view == "Solo Reparto Avanti":
            table_rows_html += f"""
            <tr style='border-bottom:1px solid #CBD5E1;'>
                <td style='padding:8px 10px; font-weight:800;'>{badge_html}</td>
                <td style='padding:8px 10px; text-align:center; font-weight:700;'>{r['n_sess']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['av_atleti']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['av_dur']:.0f}'</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#002B49;'>{r['av_dist']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#0284C7;'>{r['av_m_min']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['av_run']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#D97706;'>{r['av_hml']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#059669;'>{r['av_hsr']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right;'>{r['av_vhml']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700;'>{r['av_vmax']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['av_pe']:.0f}</td>
            </tr>
            """
        elif rep_view == "Solo Reparto TreQuarti":
            table_rows_html += f"""
            <tr style='border-bottom:1px solid #CBD5E1;'>
                <td style='padding:8px 10px; font-weight:800;'>{badge_html}</td>
                <td style='padding:8px 10px; text-align:center; font-weight:700;'>{r['n_sess']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['tq_atleti']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['tq_dur']:.0f}'</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#002B49;'>{r['tq_dist']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#0284C7;'>{r['tq_m_min']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['tq_run']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#D97706;'>{r['tq_hml']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#059669;'>{r['tq_hsr']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right;'>{r['tq_vhml']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700;'>{r['tq_vmax']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['tq_pe']:.0f}</td>
            </tr>
            """
        else:
            table_rows_html += f"""
            <tr style='border-bottom:1px solid #CBD5E1;'>
                <td style='padding:8px 10px; font-weight:800;'>{badge_html}</td>
                <td style='padding:8px 10px; text-align:center; font-weight:700;'>{r['n_sess']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['tot_atleti']}</td>
                <td style='padding:8px 10px; text-align:center;'>{r['dur_tot']:.0f}'</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#002B49;'>{r['dist_tot']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#0284C7;'>{r['m_min_tot']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['run_tot']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700; color:#D97706;'>{r['hml_tot']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:800; color:#059669;'>{r['tot_hsr']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right;'>{r['tot_vhml']:,.0f}m</td>
                <td style='padding:8px 10px; text-align:right; font-weight:700;'>{r['tot_vmax']:.1f}</td>
                <td style='padding:8px 10px; text-align:right;'>{r['tot_pe']:.0f}</td>
            </tr>
            """

    col_headers = (
        "<th>Tipologia</th><th>Reparto</th><th>Atleti</th><th>Durata</th><th>Distanza</th><th>m/min</th><th>Run Dist (&gt;6)</th><th>HML (&gt;25.5)</th><th>HSR (Soglia FIR)</th><th>VHML (Soglia FIR)</th><th>Vmax</th><th>Power Ev</th>"
        if rep_view == "Avanti vs TreQuarti (Dettaglio Comparato)"
        else "<th>Tipologia</th><th>N. Sedute</th><th>Atleti</th><th>Durata</th><th>Distanza</th><th>m/min</th><th>Run Dist (&gt;6)</th><th>HML (&gt;25.5)</th><th>HSR (Soglia FIR)</th><th>VHML</th><th>Vmax</th><th>Power Ev</th>"
    )

    table_container_html = f"""
    <div style='overflow-x:auto; background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; box-shadow:0 3px 10px rgba(0,0,0,0.06); margin-bottom:24px;'>
        <table style='width:100%; border-collapse:collapse; font-size:0.82rem; text-align:left; font-family:system-ui, -apple-system, sans-serif;'>
            <thead>
                <tr style='background:#002B49; color:#FFFFFF; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.04em;'>
                    {col_headers}
                </tr>
            </thead>
            <tbody>
                {table_rows_html}
            </tbody>
        </table>
    </div>
    """
    _clean_and_render_html(table_container_html)

    # ==========================================================================
    # GRAFICI COMPARATIVI DELLE TIPOLOGIE FIR
    # ==========================================================================
    st.markdown("#### Confronto Grafico dei Carichi per Tipologia di Allenamento")

    g_col1, g_col2 = st.columns(2)
    with g_col1:
        # 1. Distanza Totale per Reparto
        fig_dist = go.Figure()
        typs_plot = [r["tipologia"] for r in stats_list]
        fig_dist.add_trace(go.Bar(
            name="Avanti",
            x=typs_plot,
            y=[r["av_dist"] for r in stats_list],
            marker_color="#0066B2",
            text=[f"{r['av_dist']:.0f}m" for r in stats_list],
            textposition="auto",
        ))
        fig_dist.add_trace(go.Bar(
            name="TreQuarti",
            x=typs_plot,
            y=[r["tq_dist"] for r in stats_list],
            marker_color="#D97706",
            text=[f"{r['tq_dist']:.0f}m" for r in stats_list],
            textposition="auto",
        ))
        fig_dist.update_layout(
            title="<b>Distanza Totale Media (m) per Reparto</b>",
            barmode="group",
            height=340,
            margin=dict(l=35, r=20, t=45, b=40),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
            yaxis=dict(gridcolor="#E2E8F0", title="Distanza (m)"),
            xaxis=dict(tickangle=-25),
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with g_col2:
        # 2. Carico Metabolico (HML) & Alta Velocità (HSR)
        fig_hml = go.Figure()
        fig_hml.add_trace(go.Bar(
            name="HML Avanti (>25.5)",
            x=typs_plot,
            y=[r["av_hml"] for r in stats_list],
            marker_color="#38BDF8",
            text=[f"{r['av_hml']:.0f}" for r in stats_list],
            textposition="auto",
        ))
        fig_hml.add_trace(go.Bar(
            name="HML TreQuarti (>25.5)",
            x=typs_plot,
            y=[r["tq_hml"] for r in stats_list],
            marker_color="#FBBF24",
            text=[f"{r['tq_hml']:.0f}" for r in stats_list],
            textposition="auto",
        ))
        fig_hml.add_trace(go.Scatter(
            name="HSR TQ (>20 km/h)",
            x=typs_plot,
            y=[r["tq_hsr"] for r in stats_list],
            mode="lines+markers",
            line=dict(color="#DC2626", width=2.5),
            marker=dict(size=7),
        ))
        fig_hml.add_trace(go.Scatter(
            name="HSR AV (>18 km/h)",
            x=typs_plot,
            y=[r["av_hsr"] for r in stats_list],
            mode="lines+markers",
            line=dict(color="#059669", width=2.5, dash="dot"),
            marker=dict(size=7),
        ))
        fig_hml.update_layout(
            title="<b>HML (>25.5 W/kg) e High Speed Running (HSR)</b>",
            barmode="group",
            height=340,
            margin=dict(l=35, r=20, t=45, b=40),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
            legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
            yaxis=dict(gridcolor="#E2E8F0", title="Metri (m)"),
            xaxis=dict(tickangle=-25),
        )
        st.plotly_chart(fig_hml, use_container_width=True)

    # ==========================================================================
    # ESPLORAZIONE SEDUTE STORICHE PER TIPOLOGIA
    # ==========================================================================
    with st.expander("🔍 Esplora Tutte le Singole Sedute FIR di una Tipologia", expanded=False):
        sel_detail_type = st.selectbox(
            "Seleziona Tipologia da Ispezionare:",
            [r["tipologia"] for r in stats_list],
            index=0,
            key="sb_drilldown_fir_type",
        )
        sub_drill = clean_df[clean_df["assigned_type"] == sel_detail_type]
        sessions_in_type = (
            sub_drill.groupby(["date_str", "session_name"], as_index=False)
            .agg(
                atleti=("player_name", "nunique"),
                durata=("duration", "mean"),
                distanza=("distance_m", "mean"),
                hml=("hml_25", "mean"),
                run_dist=("run_dist", "mean"),
                vmax=("v_max", "max"),
            )
            .sort_values("date_str", ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(
            sessions_in_type.rename(columns={
                "date_str": "Data",
                "session_name": "Nome Seduta",
                "atleti": "Atleti Monitorati",
                "durata": "Durata Media (min)",
                "distanza": "Distanza Media (m)",
                "hml": "HML Medio (m)",
                "run_dist": "Run Dist Medio (m)",
                "vmax": "Peak Speed (km/h)",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# TAB 3: CONFRONTO MULTI-SESSIONE (2 O PIÙ SESSIONI - PAGINA 2 PDF)
# ==============================================================================
def build_multisession_comparison_bundle(
    df_full: pd.DataFrame,
    status_map: dict = None,
    selected_sessions: list = None,
    filter_dept: str = "Tutti (Collettivo)",
) -> dict:
    """
    Costruisce il bundle analitico per il Confronto Multi-Sessione (2 o più sedute):
    - Estrae le medie delle sedute selezionate escludendo i differenziati/RTP
    - Calcola la colonna/riga MEDIA ufficiale
    - Genera i grafici a colonne verticali con barra MEDIA verde (come da modello FIR)
    - Genera il radar multidimensionale footprint
    - Costruisce la matrice tabellare comparativa con Min, Max e Delta %
    """
    if status_map is None:
        status_map = utils.get_session_player_statuses()

    if "assigned_type" not in df_full.columns or "hml_25" not in df_full.columns:
        df_full = _prepare_fir_data_with_metrics(
            df_full, utils.get_players_df(), utils.get_fir_session_types()
        )

    unique_sessions = (
        df_full.groupby(["date_str", "session_name"], as_index=False)
        .agg(
            athletes_count=("player_name", "nunique"),
            assigned_type=("assigned_type", "first")
        )
        .sort_values("date_str", ascending=False)
    )

    all_sess_keys = [f"{r['date_str']} | {r['session_name']}" for _, r in unique_sessions.iterrows()]
    session_map = {f"{r['date_str']} | {r['session_name']}": (r["date_str"], r["session_name"]) for _, r in unique_sessions.iterrows()}

    if selected_sessions is None or len(selected_sessions) < 2:
        try:
            stored_sel = st.session_state.get("multi_sess_selected", [])
            if stored_sel and len(stored_sel) >= 2:
                selected_sessions = [s for s in stored_sel if s in all_sess_keys]
        except Exception:
            pass

    if selected_sessions is None or len(selected_sessions) < 2:
        target_names = ["260620 Volume", "260622 Volume", "260624 Volume"]
        def_sel = []
        for sk in all_sess_keys:
            for tn in target_names:
                if tn.lower() in sk.lower():
                    def_sel.append(sk)
                    break
        if len(def_sel) >= 2:
            selected_sessions = def_sel
        else:
            selected_sessions = all_sess_keys[:3] if len(all_sess_keys) >= 3 else all_sess_keys[:2]

    session_summaries = []
    excluded_st = {"MODIFICATO", "MODIFIED", "RTP", "OFF FEET", "NON ATTIVO"}

    for sk in selected_sessions:
        if sk not in session_map:
            continue
        d_str, s_name = session_map[sk]
        k_sess = f"{d_str}_{s_name}"
        cur_p_statuses = status_map.get(k_sess, {})

        sub = df_full[(df_full["date_str"] == d_str) & (df_full["session_name"] == s_name)].copy()
        if "player_status" not in sub.columns:
            sub["player_status"] = sub["player_name"].map(cur_p_statuses).fillna("Full")

        if filter_dept == "Solo Avanti":
            sub = sub[sub["dept"] == "Avanti"]
        elif filter_dept == "Solo TreQuarti":
            sub = sub[sub["dept"] == "TreQuarti"]

        act = sub[(~sub["player_status"].astype(str).str.upper().isin(excluded_st)) & (sub["duration"] > 0)]
        if act.empty:
            act = sub[sub["duration"] > 0]

        session_summaries.append({
            "key": sk,
            "label": s_name,
            "date": d_str,
            "players_count": len(act),
            "Tempo": float(act["duration"].mean() or 0.0),
            "Distanza": float(act["distance_m"].mean() or 0.0),
            "m_min": float(act["m_per_min"].mean() or 0.0),
            "Run_Dist": float(act["run_dist"].mean() or 0.0),
            "HML_25": float(act["hml_25"].mean() or 0.0),
            "HSR_18": float(act["hsr_18"].mean() or 0.0),
            "HSR_20": float(act["hsr_20"].mean() or 0.0),
            "VHSR_25": float(act["vhsr_25"].mean() or 0.0),
            "Power_Events": float(act["power_events"].mean() or 0.0),
            "V_max": float(act["v_max"].max() or 0.0),
        })

    if not session_summaries:
        return {}

    mean_summary = {
        "key": "MEDIA",
        "label": "MEDIA",
        "date": "-",
        "players_count": int(np.mean([s["players_count"] for s in session_summaries])),
        "Tempo": float(np.mean([s["Tempo"] for s in session_summaries])),
        "Distanza": float(np.mean([s["Distanza"] for s in session_summaries])),
        "m_min": float(np.mean([s["m_min"] for s in session_summaries])),
        "Run_Dist": float(np.mean([s["Run_Dist"] for s in session_summaries])),
        "HML_25": float(np.mean([s["HML_25"] for s in session_summaries])),
        "HSR_18": float(np.mean([s["HSR_18"] for s in session_summaries])),
        "HSR_20": float(np.mean([s["HSR_20"] for s in session_summaries])),
        "VHSR_25": float(np.mean([s["VHSR_25"] for s in session_summaries])),
        "Power_Events": float(np.mean([s["Power_Events"] for s in session_summaries])),
        "V_max": float(np.mean([s["V_max"] for s in session_summaries])),
    }

    fig_tempo = _build_vertical_multisession_chart("TEMPO (min)", "Tempo", session_summaries, mean_summary, "min", "#0284C7", "#10B981")
    fig_dist = _build_vertical_multisession_chart("DISTANZA MEDIA (m)", "Distanza", session_summaries, mean_summary, "m", "#0066B2", "#10B981")
    fig_hml = _build_vertical_multisession_chart("HML >25.5W (m)", "HML_25", session_summaries, mean_summary, "m", "#DC2626", "#10B981")
    fig_hsr = _build_vertical_multisession_chart("HSR SPRINT (m)", "HSR_20", session_summaries, mean_summary, "m", "#F59E0B", "#10B981")
    fig_mmin = _build_vertical_multisession_chart("INTENSITÀ (m/min)", "m_min", session_summaries, mean_summary, "m/min", "#6366F1", "#10B981")
    fig_radar = _build_multisession_radar(session_summaries)

    matrix_rows = [
        ("Tempo Seduta (min)", "Tempo", "min"),
        ("Distanza Totale (m)", "Distanza", "m"),
        ("Intensità Media (m/min)", "m_min", "m/min"),
        ("Running Distance >6 km/h (m)", "Run_Dist", "m"),
        ("High Metabolic Load >25.5 W/kg (m)", "HML_25", "m"),
        ("High Speed Running >18 km/h (m)", "HSR_18", "m"),
        ("High Speed Running >20 km/h (m)", "HSR_20", "m"),
        ("Very High Speed >25 km/h (m)", "VHSR_25", "m"),
        ("Power Events (Eventi Potenza)", "Power_Events", "evt"),
        ("Picco Velocità Max (km/h)", "V_max", "km/h"),
    ]

    mat_data = []
    for label, m_key, unit in matrix_rows:
        row = {"Parametro": label}
        vals = []
        for s in session_summaries:
            v = s[m_key]
            vals.append(v)
            row[s["label"]] = f"{v:.1f}" if unit in ("min", "km/h", "m/min") else f"{v:,.0f}".replace(",", ".")

        m_val = mean_summary[m_key]
        row["MEDIA"] = f"{m_val:.1f}" if unit in ("min", "km/h", "m/min") else f"{m_val:,.0f}".replace(",", ".")

        min_v = min(vals)
        max_v = max(vals)
        delta_v = ((max_v - min_v) / min_v * 100.0) if min_v > 0 else 0.0
        row["Min"] = f"{min_v:.1f}" if unit in ("min", "km/h", "m/min") else f"{min_v:,.0f}".replace(",", ".")
        row["Max"] = f"{max_v:.1f}" if unit in ("min", "km/h", "m/min") else f"{max_v:,.0f}".replace(",", ".")
        row["Δ %"] = f"+{delta_v:.0f}%"

        mat_data.append(row)

    mat_df = pd.DataFrame(mat_data)

    return {
        "session_summaries": session_summaries,
        "mean_summary": mean_summary,
        "fig_tempo": fig_tempo,
        "fig_dist": fig_dist,
        "fig_hml": fig_hml,
        "fig_hsr": fig_hsr,
        "fig_mmin": fig_mmin,
        "fig_radar": fig_radar,
        "matrix_df": mat_df,
        "session_labels": [s["label"] for s in session_summaries],
        "filter_dept": filter_dept,
    }


def _render_tab_confronto_multisessione(df_full: pd.DataFrame, status_map: dict, types_map: dict, t: dict):
    st.markdown("### Confronto Sessioni Dati Collettivi")
    st.caption("Seleziona 2 o più sedute FIR per confrontare parametri di volume, intensità metabolica e sprint con calcolo automatico della media del gruppo.")

    unique_sessions = (
        df_full.groupby(["date_str", "session_name"], as_index=False)
        .agg(
            athletes_count=("player_name", "nunique"),
            assigned_type=("assigned_type", "first")
        )
        .sort_values("date_str", ascending=False)
    )

    all_sess_keys = [f"{r['date_str']} | {r['session_name']}" for _, r in unique_sessions.iterrows()]

    # Pre-popola session_state se non presente per mantenere fisse le selezioni
    if "multi_sess_selected" not in st.session_state or not st.session_state["multi_sess_selected"]:
        target_names = ["260620 Volume", "260622 Volume", "260624 Volume"]
        init_sel = []
        for sk in all_sess_keys:
            for tn in target_names:
                if tn.lower() in sk.lower():
                    init_sel.append(sk)
                    break
        if len(init_sel) < 2:
            init_sel = all_sess_keys[:3]
        st.session_state["multi_sess_selected"] = [s for s in init_sel if s in all_sess_keys]

    # Valida che le selezioni esistano tra le chiavi attuali
    valid_selected = [s for s in st.session_state["multi_sess_selected"] if s in all_sess_keys]
    if len(valid_selected) < 2 and len(all_sess_keys) >= 2:
        valid_selected = all_sess_keys[:3]
    st.session_state["multi_sess_selected"] = valid_selected

    if "multi_sess_filter_dept" not in st.session_state:
        st.session_state["multi_sess_filter_dept"] = "Tutti (Collettivo)"

    f_col1, f_col2 = st.columns([3.0, 1.2])
    sel_sessions = f_col1.multiselect(
        "Seleziona le Sessioni da Confrontare (minimo 2):",
        all_sess_keys,
        key="multi_sess_selected",
    )

    filter_dept = f_col2.radio(
        "Filtro Reparto:",
        ["Tutti (Collettivo)", "Solo Avanti", "Solo TreQuarti"],
        horizontal=True,
        key="multi_sess_filter_dept",
    )

    if len(sel_sessions) < 2:
        st.info("💡 Seleziona almeno due sessioni per visualizzare il confronto analitico.")
        return

    bundle = build_multisession_comparison_bundle(
        df_full,
        status_map=status_map,
        selected_sessions=sel_sessions,
        filter_dept=filter_dept,
    )
    if not bundle:
        st.warning("Dati insufficienti per le sessioni selezionate.")
        return

    session_summaries = bundle["session_summaries"]
    mean_summary = bundle["mean_summary"]
    mat_df = bundle["matrix_df"]

    # ==========================================================================
    # I 5 GRAFICI A COLONNE VERTICALI (COME PAGINA 2 DEL PDF)
    # ==========================================================================
    st.markdown("#### Confronto Parametri a Colonne Verticali (con Barra MEDIA)")
    st.caption("Visualizzazione conforme al modello ufficiale FIR (Pag. 2 del Report): ciascun grafico mette a confronto le sedute selezionate con la barra verde della MEDIA.")

    g_col1, g_col2 = st.columns(2)
    with g_col1:
        st.plotly_chart(bundle["fig_tempo"], use_container_width=True)
    with g_col2:
        st.plotly_chart(bundle["fig_dist"], use_container_width=True)

    g_col3, g_col4 = st.columns(2)
    with g_col3:
        st.plotly_chart(bundle["fig_hml"], use_container_width=True)
    with g_col4:
        st.plotly_chart(bundle["fig_hsr"], use_container_width=True)

    g_col5, g_col6 = st.columns(2)
    with g_col5:
        st.plotly_chart(bundle["fig_mmin"], use_container_width=True)
    with g_col6:
        st.plotly_chart(bundle["fig_radar"], use_container_width=True)

    st.markdown("---")

    # ==========================================================================
    # TABELLA SINOTTICA COMPARATIVA A MATRICE
    # ==========================================================================
    st.markdown("#### Matrice Tabellare Comparativa")
    st.dataframe(mat_df, use_container_width=True, hide_index=True)

    csv_mat = mat_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Esporta Matrice Confronto Sessioni (CSV)",
        data=csv_mat,
        file_name=f"Confronto_Sessioni_FIR_{len(session_summaries)}_sedute.csv",
        mime="text/csv",
    )


def _build_vertical_multisession_chart(
    title: str,
    metric_key: str,
    session_list: list,
    mean_item: dict,
    unit: str,
    bar_color: str,
    mean_color: str,
) -> go.Figure:
    """Costruisce un grafico a colonne verticali con le singole sedute e la colonna MEDIA (come Pag. 2 PDF)."""
    x_labels = [s["label"] for s in session_list] + ["MEDIA"]
    y_vals = [s[metric_key] for s in session_list] + [mean_item[metric_key]]
    colors = [bar_color] * len(session_list) + [mean_color]

    # Formattazione testo sopra la barra
    if unit in ("min", "km/h", "m/min"):
        text_labels = [f"{v:.1f}" for v in y_vals]
    else:
        text_labels = [f"{v:,.0f}".replace(",", ".") for v in y_vals]

    fig = go.Figure(
        data=[
            go.Bar(
                x=x_labels,
                y=y_vals,
                text=text_labels,
                textposition="outside",
                textfont=dict(size=12, color="#0F172A", family="Arial Black"),
                marker=dict(
                    color=colors,
                    line=dict(color="#0F172A", width=1.5),
                ),
            )
        ]
    )

    max_y = max(y_vals) * 1.25 if y_vals and max(y_vals) > 0 else 10

    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=13, color="#031926", family="Inter, sans-serif"),
            x=0.5,
            xanchor="center",
        ),
        yaxis=dict(
            range=[0, max_y],
            gridcolor="#E2E8F0",
            zerolinecolor="#94A3B8",
        ),
        xaxis=dict(
            tickfont=dict(size=10, color="#0F172A", family="Arial"),
            tickangle=-15 if len(x_labels) > 3 else 0,
        ),
        height=260,
        margin=dict(l=35, r=20, t=45, b=40),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )

    return fig


def _build_multisession_radar(session_list: list) -> go.Figure:
    """Costruisce un radar Plotly per confrontare le impronte delle sedute normalizzate."""
    categories = [
        "Durata (min)",
        "Distanza (m)",
        "Intensità (m/min)",
        "HML >25.5W",
        "HSR Sprint",
    ]

    # Trova il massimo tra tutte le sessioni per ciascun parametro per normalizzare
    max_dur = max([s["Tempo"] for s in session_list]) or 1.0
    max_dist = max([s["Distanza"] for s in session_list]) or 1.0
    max_mmin = max([s["m_min"] for s in session_list]) or 1.0
    max_hml = max([s["HML_25"] for s in session_list]) or 1.0
    max_hsr = max([s["HSR_20"] for s in session_list]) or 1.0

    color_palette = ["#0284C7", "#EA580C", "#10B981", "#8B5CF6", "#EC4899", "#D97706"]

    fig = go.Figure()

    for idx, s in enumerate(session_list):
        norm_vals = [
            (s["Tempo"] / max_dur) * 100.0,
            (s["Distanza"] / max_dist) * 100.0,
            (s["m_min"] / max_mmin) * 100.0,
            (s["HML_25"] / max_hml) * 100.0,
            (s["HSR_20"] / max_hsr) * 100.0,
        ]
        # Chiudi il radar
        norm_vals_closed = norm_vals + [norm_vals[0]]
        cat_closed = categories + [categories[0]]

        c = color_palette[idx % len(color_palette)]
        fig.add_trace(
            go.Scatterpolar(
                r=norm_vals_closed,
                theta=cat_closed,
                fill="toself",
                fillcolor=f"rgba({int(c[1:3], 16)}, {int(c[3:5], 16)}, {int(c[5:7], 16)}, 0.18)",
                line=dict(color=c, width=2.5),
                name=s["label"],
            )
        )

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 105],
                gridcolor="#E2E8F0",
                tickfont=dict(size=9, color="#64748B"),
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color="#0F172A", family="Arial Black"),
                gridcolor="#CBD5E1",
            ),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.18,
            xanchor="center",
            x=0.5,
            font=dict(size=11),
        ),
        height=380,
        margin=dict(l=40, r=40, t=30, b=50),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )

    return fig


# ==============================================================================
# TAB 4: SEMAFORO ESPOSIZIONE ALTA VELOCITÀ (SOLO Vmax & Vmax%)
# ==============================================================================
@st.fragment
def _render_tab_semaforo_vmax(df_fir: pd.DataFrame, players_df: pd.DataFrame, ctx: dict):
    meta = ctx.get("meta", {})
    camp_players = ctx.get("camp_players", pd.DataFrame())
    ref_date_str = str(meta.get("date_str") or "2026-11-05")[:10]
    w_start = str(meta.get("week_start") or ref_date_str)[:10]
    w_end = str(meta.get("week_end") or ref_date_str)[:10]

    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); color:#FFFFFF; padding:12px 18px; border-radius:10px; border-left:4px solid #D4AF37; margin-bottom:14px;">
            <div style="font-size:0.70rem; font-weight:800; color:#D4AF37; text-transform:uppercase; letter-spacing:0.08em;">
                PREVENZIONE HAMSTRING &bull; MONITORAGGIO ESCLUSIVO SU V MAX &amp; % V MAX
            </div>
            <div style="font-size:1.05rem; font-weight:800; margin-top:2px;">
                🚦 Semaforo Esposizione Alta Velocità (Soglie 85% e 90% Vmax) — Riferimento: {ref_date_str}
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Calcolato esclusivamente da <b>V max (km/h)</b> e <b>% V max</b> (rispetto alla Vmax di profilo Roster) per verificare chi ha toccato almeno l'85% e il 90% della propria velocità massima.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.5, 1.5, 1.2])
    scope_mode = c1.selectbox(
        "Ambito Atleti",
        ["raduno", "roster"],
        format_func=lambda k: "Solo Convocati Raduno Attivo" if k == "raduno" else "Intero Roster Nazionale FIR",
        key="sem_vmax_scope",
    )
    src_mode = c2.selectbox(
        "Storico Sedute Analizzato",
        ["all", "nazionale"],
        format_func=lambda k: "Database Totale (FIR + Benetton + Zebre)" if k == "all" else "Solo Nazionale Italiana (FIR)",
        key="sem_vmax_src",
    )
    dept_f = c3.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="sem_vmax_dept")

    gps_src = utils.get_gps_history_df("all") if src_mode == "all" else df_fir.copy()
    if gps_src.empty:
        st.info("Nessun dato GPS disponibile.")
        return

    gps_src = gps_src.copy()
    gps_src["v_max"] = pd.to_numeric(gps_src.get("v_max", 0), errors="coerce").fillna(0.0)
    gps_src["v_max_pct"] = pd.to_numeric(gps_src.get("v_max_pct", 0), errors="coerce").fillna(0.0)
    gps_src["player_up"] = gps_src["player_name"].astype(str).str.strip().str.upper()

    # Roster map
    roster_map = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip()
            if nm:
                roster_map[nm.upper()] = pr.to_dict()

    if scope_mode == "raduno" and not camp_players.empty:
        target_names = [str(x).strip() for x in camp_players["player_name"].dropna().unique().tolist() if str(x).strip()]
    else:
        target_names = [str(x).strip() for x in players_df["name_display"].dropna().unique().tolist() if str(x).strip()]

    ref_dt = pd.to_datetime(ref_date_str, errors="coerce")
    if pd.isna(ref_dt):
        ref_dt = pd.Timestamp("2026-11-05")
    d21_start = (ref_dt - pd.Timedelta(days=21)).strftime("%Y-%m-%d")

    gps_upto = gps_src[gps_src["date_str"] <= ref_date_str].copy()
    cur_sess_name = str(meta.get("session_name") or "")

    rows = []
    for p_name in target_names:
        p_up = p_name.upper()
        p_info = roster_map.get(p_up, {})
        role = str(p_info.get("role") or "Avanti")
        dept = str(p_info.get("department") or ROLE_TO_DEPT.get(role, "Avanti"))
        if dept_f != "Tutti" and dept != dept_f:
            continue
        roster_vmax = float(p_info.get("v_max") or 30.0)
        if roster_vmax <= 0:
            roster_vmax = 30.0

        p_hist = gps_upto[gps_upto["player_up"] == p_up].copy()
        if not p_hist.empty:
            p_hist["calc_pct"] = np.where(
                p_hist["v_max_pct"] > 0,
                p_hist["v_max_pct"],
                (p_hist["v_max"] / roster_vmax) * 100.0,
            )
        else:
            p_hist["calc_pct"] = pd.Series(dtype=float)

        # Seduta corrente
        p_sess = p_hist[(p_hist["date_str"] == ref_date_str) & (p_hist["session_name"].astype(str) == cur_sess_name)]
        sess_vmax = float(p_sess["v_max"].max()) if not p_sess.empty else 0.0
        sess_pct = float(p_sess["calc_pct"].max()) if not p_sess.empty else 0.0

        # Settimana corrente
        p_week = p_hist[(p_hist["date_str"] >= w_start) & (p_hist["date_str"] <= w_end)]
        week_vmax = float(p_week["v_max"].max()) if not p_week.empty else 0.0
        week_pct = float(p_week["calc_pct"].max()) if not p_week.empty else 0.0

        # Ultime 3 Settimane (21gg)
        p_21 = p_hist[p_hist["date_str"] >= d21_start]
        vmax_21 = float(p_21["v_max"].max()) if not p_21.empty else 0.0
        pct_21 = float(p_21["calc_pct"].max()) if not p_21.empty else 0.0

        # Ultima data >= 85% e >= 90%
        hit_85 = p_hist[p_hist["calc_pct"] >= 85.0]
        hit_90 = p_hist[p_hist["calc_pct"] >= 90.0]

        last_85_dt = str(hit_85["date_str"].max()) if not hit_85.empty else None
        last_90_dt = str(hit_90["date_str"].max()) if not hit_90.empty else None

        days_85 = int((ref_dt - pd.to_datetime(last_85_dt)).days) if last_85_dt else 999
        days_90 = int((ref_dt - pd.to_datetime(last_90_dt)).days) if last_90_dt else 999

        if days_85 <= 7:
            status_lbl = "🟢 Coperto (≤7gg)"
            status_code = "green"
        elif days_85 <= 14:
            status_lbl = "🟡 Richiamo (8-14gg)"
            status_code = "yellow"
        else:
            status_lbl = "🔴 Scoperto (>14gg)"
            status_code = "red"

        rows.append({
            "player_name": p_name,
            "role": role,
            "department": dept,
            "roster_vmax": roster_vmax,
            "sess_vmax": sess_vmax,
            "sess_pct": sess_pct,
            "week_vmax": week_vmax,
            "week_pct": week_pct,
            "vmax_21": vmax_21,
            "pct_21": pct_21,
            "last_85_dt": last_85_dt or "Mai",
            "days_85": days_85,
            "last_90_dt": last_90_dt or "Mai",
            "days_90": days_90,
            "status_lbl": status_lbl,
            "status_code": status_code,
        })

    res_df = pd.DataFrame(rows)
    if res_df.empty:
        st.info("Nessun atleta trovato per i filtri selezionati.")
        return

    n_green = int((res_df["status_code"] == "green").sum())
    n_yellow = int((res_df["status_code"] == "yellow").sum())
    n_red = int((res_df["status_code"] == "red").sum())
    avg_wpct = float(res_df[res_df["week_pct"] > 0]["week_pct"].mean() or 0.0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🟢 Coperti (≥85% ultimi 7gg)", f"{n_green} atleti", f"{(n_green/len(res_df)*100):.0f}% del gruppo")
    k2.metric("🟡 Da Richiamare (8–14gg)", f"{n_yellow} atleti", "Richiamo velocità consigliato")
    k3.metric("🔴 Scoperti (>14gg senza ≥85%)", f"{n_red} atleti", "Attenzione esposizione sprint")
    k4.metric("⚡ Picco Medio % Vmax Settimana", f"{avg_wpct:.1f}%", f"Settimana {w_start} → {w_end}")

    # Grafico a barre Picco % Vmax Settimana vs Ultime 3 Settimane
    chart_df = res_df.sort_values(by=["week_pct", "pct_21"], ascending=[False, False]).reset_index(drop=True)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_df["player_name"],
            y=chart_df["week_pct"],
            name="Picco % Vmax Settimana Raduno",
            marker_color=[
                "#16A34A" if v >= 90 else ("#0284C7" if v >= 85 else ("#F59E0B" if v >= 78 else "#DC2626"))
                for v in chart_df["week_pct"]
            ],
            text=[f"{v:.0f}%" if v > 0 else "" for v in chart_df["week_pct"]],
            textposition="outside",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=chart_df["player_name"],
            y=chart_df["pct_21"],
            mode="markers",
            name="Picco % Vmax Ultime 3 Settimane",
            marker=dict(size=9, color="#0F172A", symbol="diamond", line=dict(width=1.5, color="#D4AF37")),
        )
    )
    fig.add_hline(y=90, line_dash="dash", line_color="#16A34A", line_width=1.8, annotation_text="Soglia 90% Vmax", annotation_position="top right")
    fig.add_hline(y=85, line_dash="dot", line_color="#D97706", line_width=1.8, annotation_text="Soglia 85% Vmax", annotation_position="bottom right")
    fig.update_layout(
        title=dict(text="<b>Esposizione % Vmax: Picco Settimana vs Picco Ultime 3 Settimane</b>", x=0.5, xanchor="center"),
        height=410,
        margin=dict(l=30, r=25, t=50, b=95),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        xaxis=dict(tickangle=-38, tickfont=dict(size=10)),
        yaxis=dict(title="% Vmax Roster", range=[0, 112], ticksuffix="%"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabella HTML dettagliata
    tr_html = ""
    for idx, r in res_df.sort_values(by=["department", "days_85", "player_name"], ascending=[True, False, True]).reset_index(drop=True).iterrows():
        bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"
        if r["status_code"] == "green":
            badge_st = "background:#DCFCE7; color:#15803D; border:1px solid #BBF7D0;"
        elif r["status_code"] == "yellow":
            badge_st = "background:#FEF3C7; color:#B45309; border:1px solid #FDE68A;"
        else:
            badge_st = "background:#FEE2E2; color:#B91C1C; border:1px solid #FECACA;"

        d85_str = f"{r['days_85']} gg fa ({r['last_85_dt']})" if r["days_85"] < 900 else "Oltre 60 gg / N.D."
        d90_str = f"{r['days_90']} gg fa ({r['last_90_dt']})" if r["days_90"] < 900 else "Oltre 60 gg / N.D."

        tr_html += f"""
        <tr style="background:{bg}; border-bottom:1px solid #E2E8F0; font-size:0.76rem;">
            <td style="padding:6px 10px; font-weight:700; color:#0F172A;">{r['player_name']}</td>
            <td style="padding:6px 8px; color:#475569;">{r['role']} ({r['department']})</td>
            <td style="padding:6px 8px; text-align:center; font-weight:800; color:#0369A1; background:#F0F9FF;">{r['roster_vmax']:.1f} km/h</td>
            <td style="padding:6px 8px; text-align:center;">{r['sess_vmax']:.1f} km/h ({r['sess_pct']:.0f}%)</td>
            <td style="padding:6px 8px; text-align:center; font-weight:700;">{r['week_vmax']:.1f} km/h ({r['week_pct']:.0f}%)</td>
            <td style="padding:6px 8px; text-align:center; font-weight:700;">{r['vmax_21']:.1f} km/h ({r['pct_21']:.0f}%)</td>
            <td style="padding:6px 8px; text-align:center;">{d85_str}</td>
            <td style="padding:6px 8px; text-align:center;">{d90_str}</td>
            <td style="padding:6px 8px; text-align:center;"><span style="padding:2px 8px; border-radius:6px; font-weight:800; font-size:0.72rem; {badge_st}">{r['status_lbl']}</span></td>
        </tr>
        """

    tbl_html = f"""
    <div style="overflow-x:auto; border:1.5px solid #CBD5E1; border-radius:10px; background:#FFFFFF;">
        <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#002B49; color:#FFFFFF; font-size:0.70rem; font-weight:800;">
                    <th style="padding:8px 10px; text-align:left;">Giocatore</th>
                    <th style="padding:8px 8px; text-align:left;">Ruolo / Reparto</th>
                    <th style="padding:8px 8px; text-align:center;">Vmax Roster</th>
                    <th style="padding:8px 8px; text-align:center;">Picco Seduta</th>
                    <th style="padding:8px 8px; text-align:center;">Picco Settimana</th>
                    <th style="padding:8px 8px; text-align:center;">Picco 3 Settimane</th>
                    <th style="padding:8px 8px; text-align:center;">Ultima Toccata &ge;85%</th>
                    <th style="padding:8px 8px; text-align:center;">Ultima Toccata &ge;90%</th>
                    <th style="padding:8px 8px; text-align:center;">Semaforo Vmax</th>
                </tr>
            </thead>
            <tbody>{tr_html}</tbody>
        </table>
    </div>
    """
    _clean_and_render_html(tbl_html)


# ==============================================================================
# TAB 5: DENSITÀ DA GARA (SOLO HML/min & HSR/min)
# ==============================================================================
@st.fragment
def _render_tab_densita_gara(df_fir: pd.DataFrame, players_df: pd.DataFrame, status_map: dict, ctx: dict):
    meta = ctx.get("meta", {})
    sub_sess = ctx.get("sub_gps_sess", pd.DataFrame())
    sub_day = ctx.get("sub_gps_day", pd.DataFrame())
    sub_week = ctx.get("sub_gps_week", pd.DataFrame())

    st.markdown(
        f"""
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); color:#FFFFFF; padding:12px 18px; border-radius:10px; border-left:4px solid #D4AF37; margin-bottom:14px;">
            <div style="font-size:0.70rem; font-weight:800; color:#D4AF37; text-transform:uppercase; letter-spacing:0.08em;">
                INTENSITÀ SPECIFICA AL MINUTO &bull; SOLO HML/MIN &amp; HSR/MIN
            </div>
            <div style="font-size:1.05rem; font-weight:800; margin-top:2px;">
                ⏱️ Analisi Densità da Gara: HML/min (&gt;25.5W) e HSR/min (&gt;18 Avanti / &gt;20 TreQuarti)
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Confronta la densità al minuto della seduta con il ritmo medio partita (80') di ogni giocatore per valutare se l'intensità ha replicato o superato le richieste del Match.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([1.8, 1.4])
    agg_mode = c1.selectbox(
        "Orizzonte da Analizzare",
        ["sessione", "giornata", "settimana"],
        format_func=lambda k: {
            "sessione": f"1. Seduta Selezionata ({meta.get('session_name', '')})",
            "giornata": f"2. Giornata Cumulata ({meta.get('date_str', '')})",
            "settimana": f"3. Settimana di Raduno ({meta.get('week_start', '')} → {meta.get('week_end', '')})",
        }[k],
        key="dens_agg_mode",
    )
    dept_f = c2.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="dens_dept_f")

    raw_target = sub_sess if agg_mode == "sessione" else (sub_day if agg_mode == "giornata" else sub_week)
    if raw_target is None or raw_target.empty:
        st.info("Nessun dato GPS disponibile per la selezione corrente.")
        return

    # Map benchmark 80' from players_df
    p_bench = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip().upper()
            if nm:
                role = str(pr.get("role") or "Avanti")
                dept = str(pr.get("department") or ROLE_TO_DEPT.get(role, "Avanti"))
                hml_80 = float(pr.get("match_avg_hml") or pr.get("hml_avg_tot") or (560.0 if dept == "Avanti" else 880.0))
                hsr_80 = float(pr.get("match_avg_hsr") or pr.get("hsr_avg_tot") or (210.0 if dept == "Avanti" else 420.0))
                p_bench[nm] = {
                    "role": role,
                    "dept": dept,
                    "hml_min_match": max(0.1, hml_80 / 80.0),
                    "hsr_min_match": max(0.1, hsr_80 / 80.0),
                }

    df_w = raw_target.copy()
    for col in ["duration", "mp_25_35", "mp_35_50", "mp_50_100", "speed_18_20", "speed_20_25", "speed_25_72"]:
        if col in df_w.columns:
            df_w[col] = pd.to_numeric(df_w[col], errors="coerce").fillna(0.0)
        else:
            df_w[col] = 0.0

    df_w["hml_val"] = df_w["mp_25_35"] + df_w["mp_35_50"] + df_w["mp_50_100"]
    df_w["hsr_18_val"] = df_w["speed_18_20"] + df_w["speed_20_25"] + df_w["speed_25_72"]
    df_w["hsr_20_val"] = df_w["speed_20_25"] + df_w["speed_25_72"]

    grp = df_w.groupby("player_name", as_index=False).agg(
        duration=("duration", "sum"),
        hml=("hml_val", "sum"),
        hsr_18=("hsr_18_val", "sum"),
        hsr_20=("hsr_20_val", "sum"),
    )
    grp = grp[grp["duration"] > 0].copy()
    if grp.empty:
        st.info("Nessun atleta con durata > 0 nella selezione.")
        return

    rows_d = []
    for _, r in grp.iterrows():
        pn = str(r["player_name"]).strip()
        b = p_bench.get(pn.upper(), {"role": "Avanti", "dept": "Avanti", "hml_min_match": 7.0, "hsr_min_match": 2.8})
        dept = b["dept"]
        if dept_f != "Tutti" and dept != dept_f:
            continue
        dur = float(r["duration"])
        hml = float(r["hml"])
        hsr = float(r["hsr_18"] if dept == "Avanti" else r["hsr_20"])
        hml_min = hml / dur if dur > 0 else 0.0
        hsr_min = hsr / dur if dur > 0 else 0.0
        pct_dens_hml = (hml_min / b["hml_min_match"]) * 100.0 if b["hml_min_match"] > 0 else 0.0
        pct_dens_hsr = (hsr_min / b["hsr_min_match"]) * 100.0 if b["hsr_min_match"] > 0 else 0.0

        rows_d.append({
            "player_name": pn,
            "role": b["role"],
            "department": dept,
            "duration": dur,
            "hml": hml,
            "hml_min": hml_min,
            "hml_min_match": b["hml_min_match"],
            "pct_dens_hml": pct_dens_hml,
            "hsr": hsr,
            "hsr_min": hsr_min,
            "hsr_min_match": b["hsr_min_match"],
            "pct_dens_hsr": pct_dens_hsr,
        })

    ddf = pd.DataFrame(rows_d)
    if ddf.empty:
        st.info("Nessun atleta per il reparto selezionato.")
        return

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("⏱️ HML/min Medio", f"{ddf['hml_min'].mean():.1f} m/min", f"{ddf['pct_dens_hml'].mean():.0f}% del ritmo Match")
    k2.metric("⚡ HSR/min Medio", f"{ddf['hsr_min'].mean():.2f} m/min", f"{ddf['pct_dens_hsr'].mean():.0f}% del ritmo Match")
    k3.metric("🔥 Sopra Ritmo Match HML/min (≥100%)", f"{int((ddf['pct_dens_hml'] >= 100).sum())} su {len(ddf)}", "Atleti in sovra-intensità metabolica")
    k4.metric("🚀 Sopra Ritmo Match HSR/min (≥100%)", f"{int((ddf['pct_dens_hsr'] >= 100).sum())} su {len(ddf)}", "Atleti in sovra-intensità velocità")

    # Scatter HML/min vs HSR/min
    fig = go.Figure()
    for d_nm, col_hex in [("Avanti", "#1D4ED8"), ("TreQuarti", "#DC2626")]:
        sub_d = ddf[ddf["department"] == d_nm]
        if not sub_d.empty:
            fig.add_trace(
                go.Scatter(
                    x=sub_d["hml_min"],
                    y=sub_d["hsr_min"],
                    mode="markers+text",
                    name=d_nm,
                    text=sub_d["player_name"],
                    textposition="top center",
                    textfont=dict(size=9.5, color="#0F172A"),
                    marker=dict(size=12, color=col_hex, line=dict(width=1.5, color="#FFFFFF")),
                    hovertemplate="<b>%{text}</b><br>HML/min: <b>%{x:.1f} m/min</b><br>HSR/min: <b>%{y:.2f} m/min</b><extra></extra>",
                )
            )
    fig.add_vline(x=float(ddf["hml_min"].mean()), line_dash="dash", line_color="#1D4ED8", annotation_text=f"Media HML/min ({ddf['hml_min'].mean():.1f})")
    fig.add_hline(y=float(ddf["hsr_min"].mean()), line_dash="dash", line_color="#DC2626", annotation_text=f"Media HSR/min ({ddf['hsr_min'].mean():.2f})")
    fig.update_layout(
        title=dict(text="<b>Matrice Densità Specifica: HML/min (Asse X) vs HSR/min (Asse Y)</b>", x=0.5, xanchor="center"),
        height=440,
        margin=dict(l=35, r=35, t=50, b=40),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        xaxis=dict(title="HML/min (>25.5W metri/minuto)", gridcolor="#CBD5E1"),
        yaxis=dict(title="HSR/min (>18 Avanti / >20 TreQuarti metri/minuto)", gridcolor="#CBD5E1"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Tabella individuale + Medie Reparto
    tr_html = ""
    for idx, r in ddf.sort_values(by=["department", "hml_min"], ascending=[True, False]).reset_index(drop=True).iterrows():
        bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"
        c_hml = "background:#DCFCE7; color:#15803D; font-weight:800;" if r["pct_dens_hml"] >= 100 else ("background:#FEF3C7; color:#B45309; font-weight:700;" if r["pct_dens_hml"] >= 80 else "")
        c_hsr = "background:#DCFCE7; color:#15803D; font-weight:800;" if r["pct_dens_hsr"] >= 100 else ("background:#FEF3C7; color:#B45309; font-weight:700;" if r["pct_dens_hsr"] >= 80 else "")
        tr_html += f"""
        <tr style="background:{bg}; border-bottom:1px solid #E2E8F0; font-size:0.76rem;">
            <td style="padding:6px 10px; font-weight:700; color:#0F172A;">{r['player_name']}</td>
            <td style="padding:6px 8px; color:#475569;">{r['role']} ({r['department']})</td>
            <td style="padding:6px 8px; text-align:center;">{r['duration']:.0f}'</td>
            <td style="padding:6px 8px; text-align:center;">{r['hml']:.0f} m</td>
            <td style="padding:6px 8px; text-align:center; font-weight:800; color:#0369A1;">{r['hml_min']:.1f}</td>
            <td style="padding:6px 8px; text-align:center; color:#64748B;">{r['hml_min_match']:.1f}</td>
            <td style="padding:6px 8px; text-align:center; {c_hml}">{r['pct_dens_hml']:.0f}%</td>
            <td style="padding:6px 8px; text-align:center;">{r['hsr']:.0f} m</td>
            <td style="padding:6px 8px; text-align:center; font-weight:800; color:#DC2626;">{r['hsr_min']:.2f}</td>
            <td style="padding:6px 8px; text-align:center; color:#64748B;">{r['hsr_min_match']:.2f}</td>
            <td style="padding:6px 8px; text-align:center; {c_hsr}">{r['pct_dens_hsr']:.0f}%</td>
        </tr>
        """

    for d_nm in ["Avanti", "TreQuarti"]:
        sub_d = ddf[ddf["department"] == d_nm]
        if not sub_d.empty:
            tr_html += f"""
            <tr style="background:#002B49; color:#FFFFFF; font-weight:800; font-size:0.78rem; border-top:2px solid #D4AF37;">
                <td colspan="2" style="padding:7px 10px; color:#D4AF37;">MEDIA REPARTO {d_nm.upper()} ({len(sub_d)} atleti)</td>
                <td style="padding:7px 8px; text-align:center;">{sub_d['duration'].mean():.0f}'</td>
                <td style="padding:7px 8px; text-align:center;">{sub_d['hml'].mean():.0f} m</td>
                <td style="padding:7px 8px; text-align:center; color:#38BDF8;">{sub_d['hml_min'].mean():.1f}</td>
                <td style="padding:7px 8px; text-align:center;">{sub_d['hml_min_match'].mean():.1f}</td>
                <td style="padding:7px 8px; text-align:center; color:#FEF08A;">{sub_d['pct_dens_hml'].mean():.0f}%</td>
                <td style="padding:7px 8px; text-align:center;">{sub_d['hsr'].mean():.0f} m</td>
                <td style="padding:7px 8px; text-align:center; color:#FCA5A5;">{sub_d['hsr_min'].mean():.2f}</td>
                <td style="padding:7px 8px; text-align:center;">{sub_d['hsr_min_match'].mean():.2f}</td>
                <td style="padding:7px 8px; text-align:center; color:#FEF08A;">{sub_d['pct_dens_hsr'].mean():.0f}%</td>
            </tr>
            """

    tbl_html = f"""
    <div style="overflow-x:auto; border:1.5px solid #CBD5E1; border-radius:10px; background:#FFFFFF;">
        <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#002B49; color:#FFFFFF; font-size:0.70rem; font-weight:800;">
                    <th style="padding:8px 10px; text-align:left;">Giocatore</th>
                    <th style="padding:8px 8px; text-align:left;">Ruolo / Reparto</th>
                    <th style="padding:8px 8px; text-align:center;">Durata</th>
                    <th style="padding:8px 8px; text-align:center;">HML Tot (m)</th>
                    <th style="padding:8px 8px; text-align:center;">HML/min</th>
                    <th style="padding:8px 8px; text-align:center;">Ref Match HML/min</th>
                    <th style="padding:8px 8px; text-align:center;">% Ritmo Match HML</th>
                    <th style="padding:8px 8px; text-align:center;">HSR Tot (m)</th>
                    <th style="padding:8px 8px; text-align:center;">HSR/min</th>
                    <th style="padding:8px 8px; text-align:center;">Ref Match HSR/min</th>
                    <th style="padding:8px 8px; text-align:center;">% Ritmo Match HSR</th>
                </tr>
            </thead>
            <tbody>{tr_html}</tbody>
        </table>
    </div>
    """
    _clean_and_render_html(tbl_html)


# ==============================================================================
# TAB 6: CONFRONTO DIRETTO TRA SETTIMANE DI RADUNO
# ==============================================================================
def get_week_choices(df_fir: pd.DataFrame, camps_df: pd.DataFrame = None) -> list:
    """Restituisce le settimane e raduni disponibili per il confronto che contengono sessioni GPS."""
    if camps_df is None:
        camps_df = utils.get_camps_df()
    if df_fir.empty:
        return []

    fir_dts = pd.to_datetime(df_fir["date_str"], errors="coerce").dropna()
    if fir_dts.empty:
        return []

    week_choices = []
    seen_mons = set()
    if not camps_df.empty:
        for _, cr in camps_df.sort_values("start_date_str", ascending=False).iterrows():
            s_dt = pd.to_datetime(cr["start_date_str"], errors="coerce")
            if pd.notna(s_dt):
                mon = (s_dt - pd.Timedelta(days=s_dt.weekday())).strftime("%Y-%m-%d")
                sun = (pd.to_datetime(mon) + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
                # Includi solo se sono presenti dati GPS per quella settimana
                has_gps = ((df_fir["date_str"] >= mon) & (df_fir["date_str"] <= sun)).any()
                if has_gps:
                    lbl = f"🏕️ {cr['start_date_str']} • {cr['week_name']} ({cr['competition']})"
                    week_choices.append({"key": f"camp_{cr['id']}_{mon}", "mon": mon, "sun": sun, "label": lbl, "short": str(cr["week_name"])})
                    seen_mons.add(mon)

    mons = sorted(set((fir_dts - pd.to_timedelta(fir_dts.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")), reverse=True)
    for m_str in mons:
        if m_str not in seen_mons:
            s_str = (pd.to_datetime(m_str) + pd.Timedelta(days=6)).strftime("%Y-%m-%d")
            sub_w = df_fir[(df_fir["date_str"] >= m_str) & (df_fir["date_str"] <= s_str)]
            if not sub_w.empty:
                s_names = ", ".join(sub_w["session_name"].dropna().unique()[:2])
                lbl = f"🗓️ Settimana {m_str} → {s_str} ({s_names[:35]})"
                week_choices.append({"key": f"wk_{m_str}", "mon": m_str, "sun": s_str, "label": lbl, "short": f"Week {m_str}"})
                seen_mons.add(m_str)

    return week_choices


def build_confronto_settimane_bundle(
    df_fir: pd.DataFrame,
    camps_df: pd.DataFrame = None,
    wk_a_key: str = None,
    wk_b_key: str = None,
    excl_matches: bool = True
) -> dict:
    """
    Costruisce il bundle di confronto tra due settimane di raduno per PDF e Web:
    restituisce wk_a, wk_b, summary_df, fig_h, fig_s, merged_p, df_a, df_b.
    """
    week_choices = get_week_choices(df_fir, camps_df)
    if len(week_choices) < 2:
        return {}
    w_map = {w["key"]: w for w in week_choices}
    if not wk_a_key or wk_a_key not in w_map:
        wk_a_key = week_choices[0]["key"]
    if not wk_b_key or wk_b_key not in w_map:
        wk_b_key = week_choices[min(1, len(week_choices) - 1)]["key"]

    wk_a = w_map[wk_a_key]
    wk_b = w_map[wk_b_key]

    def _agg_week(w_info):
        sub = df_fir[(df_fir["date_str"] >= w_info["mon"]) & (df_fir["date_str"] <= w_info["sun"])].copy()
        if excl_matches and not sub.empty and "assigned_type" in sub.columns:
            sub = sub[sub["assigned_type"] != "Match"].copy()
        if sub.empty:
            return pd.DataFrame()
        hsr_18_col = sub["hsr_18"] if "hsr_18" in sub.columns else pd.Series(0.0, index=sub.index)
        hsr_20_col = sub["hsr_20"] if "hsr_20" in sub.columns else pd.Series(0.0, index=sub.index)
        sub["hsr_spec"] = np.where(sub["dept"] == "Avanti", hsr_18_col, hsr_20_col)
        grp = sub.groupby(["player_name", "dept", "role_clean"], as_index=False).agg(
            duration=("duration", "sum"),
            distance_m=("distance_m", "sum"),
            run_dist=("run_dist", "sum"),
            hml_25=("hml_25", "sum"),
            hsr_spec=("hsr_spec", "sum"),
            v_max=("v_max", "max"),
            v_max_pct=("v_max_pct", "max"),
        )
        grp["hml_min"] = np.where(grp["duration"] > 0, grp["hml_25"] / grp["duration"], 0.0)
        grp["hsr_min"] = np.where(grp["duration"] > 0, grp["hsr_spec"] / grp["duration"], 0.0)
        return grp

    df_a = _agg_week(wk_a)
    df_b = _agg_week(wk_b)

    if df_a.empty or df_b.empty:
        return {}

    summary_rows = []
    for grp_lbl, flt_a, flt_b in [
        ("SQUADRA TOTALE", df_a, df_b),
        ("REPARTO AVANTI", df_a[df_a["dept"] == "Avanti"], df_b[df_b["dept"] == "Avanti"]),
        ("REPARTO TREQUARTI", df_a[df_a["dept"] == "TreQuarti"], df_b[df_b["dept"] == "TreQuarti"]),
    ]:
        if flt_a.empty and flt_b.empty:
            continue
        dt_a, dt_b = float(flt_a["distance_m"].mean() or 0), float(flt_b["distance_m"].mean() or 0)
        hml_a, hml_b = float(flt_a["hml_25"].mean() or 0), float(flt_b["hml_25"].mean() or 0)
        hsr_a, hsr_b = float(flt_a["hsr_spec"].mean() or 0), float(flt_b["hsr_spec"].mean() or 0)
        hm_a, hm_b = float(flt_a["hml_min"].mean() or 0), float(flt_b["hml_min"].mean() or 0)
        sm_a, sm_b = float(flt_a["hsr_min"].mean() or 0), float(flt_b["hsr_min"].mean() or 0)
        vm_a, vm_b = float(flt_a["v_max"].max() or 0), float(flt_b["v_max"].max() or 0)
        summary_rows.append({
            "Gruppo": grp_lbl,
            "Atleti A / B": f"{len(flt_a)} vs {len(flt_b)}",
            f"Distanza ({wk_a['short']})": f"{dt_a:,.0f} m".replace(",", "."),
            f"Distanza ({wk_b['short']})": f"{dt_b:,.0f} m".replace(",", "."),
            "Δ Dist %": f"{((dt_a - dt_b)/dt_b*100):+.1f}%" if dt_b > 0 else "N.D.",
            f"HML ({wk_a['short']})": f"{hml_a:,.0f} m".replace(",", "."),
            f"HML ({wk_b['short']})": f"{hml_b:,.0f} m".replace(",", "."),
            "Δ HML %": f"{((hml_a - hml_b)/hml_b*100):+.1f}%" if hml_b > 0 else "N.D.",
            f"HSR ({wk_a['short']})": f"{hsr_a:,.0f} m".replace(",", "."),
            f"HSR ({wk_b['short']})": f"{hsr_b:,.0f} m".replace(",", "."),
            "Δ HSR %": f"{((hsr_a - hsr_b)/hsr_b*100):+.1f}%" if hsr_b > 0 else "N.D.",
            "HML/min (A vs B)": f"{hm_a:.1f} vs {hm_b:.1f}",
            "HSR/min (A vs B)": f"{sm_a:.2f} vs {sm_b:.2f}",
            "Picco Vmax (A vs B)": f"{vm_a:.1f} vs {vm_b:.1f} km/h",
        })

    summary_df = pd.DataFrame(summary_rows)

    role_a = df_a.groupby("role_clean", as_index=False).agg(hml_a=("hml_25", "mean"), hsr_a=("hsr_spec", "mean"))
    role_b = df_b.groupby("role_clean", as_index=False).agg(hml_b=("hml_25", "mean"), hsr_b=("hsr_spec", "mean"))
    role_cmp = pd.merge(role_a, role_b, on="role_clean", how="outer").fillna(0.0)

    fig_h = go.Figure()
    fig_h.add_trace(go.Bar(x=role_cmp["role_clean"], y=role_cmp["hml_a"], name=wk_a["short"], marker_color="#0284C7"))
    fig_h.add_trace(go.Bar(x=role_cmp["role_clean"], y=role_cmp["hml_b"], name=wk_b["short"], marker_color="#94A3B8"))
    fig_h.update_layout(
        title=dict(text="<b>Media HML >25.5W Cumulato per Ruolo (m)</b>", x=0.5, xanchor="center"),
        barmode="group",
        height=360,
        margin=dict(l=30, r=20, t=45, b=60),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
    )

    fig_s = go.Figure()
    fig_s.add_trace(go.Bar(x=role_cmp["role_clean"], y=role_cmp["hsr_a"], name=wk_a["short"], marker_color="#DC2626"))
    fig_s.add_trace(go.Bar(x=role_cmp["role_clean"], y=role_cmp["hsr_b"], name=wk_b["short"], marker_color="#CBD5E1"))
    fig_s.update_layout(
        title=dict(text="<b>Media HSR >18\\20 Cumulato per Ruolo (m)</b>", x=0.5, xanchor="center"),
        barmode="group",
        height=360,
        margin=dict(l=30, r=20, t=45, b=60),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
    )

    merged_p = pd.merge(
        df_a,
        df_b,
        on="player_name",
        how="inner",
        suffixes=("_A", "_B"),
    )

    return {
        "wk_a": wk_a,
        "wk_b": wk_b,
        "summary_df": summary_df,
        "fig_h": fig_h,
        "fig_s": fig_s,
        "merged_p": merged_p,
        "df_a": df_a,
        "df_b": df_b,
        "week_choices": week_choices,
    }


def _render_tab_confronto_settimane(df_fir: pd.DataFrame, players_df: pd.DataFrame, status_map: dict):
    st.markdown(
        """
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 100%); color:#FFFFFF; padding:12px 18px; border-radius:10px; border-left:4px solid #D4AF37; margin-bottom:14px;">
            <div style="font-size:0.70rem; font-weight:800; color:#D4AF37; text-transform:uppercase; letter-spacing:0.08em;">
                CONFRONTO DIRETTO MICROCICLI TEST MATCH
            </div>
            <div style="font-size:1.05rem; font-weight:800; margin-top:2px;">
                🏕️ Confronto Diretto tra Settimane di Raduno (es. Settimana Sud Africa vs Settimana Giappone)
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Sovrappone i volumi, le intensità (HML/min, HSR/min) e i picchi di velocità tra due settimane di raduno per Squadra, Reparto, Ruolo e Singolo Atleta.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    week_choices = get_week_choices(df_fir)
    if len(week_choices) < 2:
        st.info("Sono necessarie almeno 2 settimane con dati GPS per effettuare il confronto.")
        return

    w_keys = [w["key"] for w in week_choices]
    w_map = {w["key"]: w for w in week_choices}

    # Mantieni selezioni fisse in session_state finché non modificate manualmente dall'utente
    if "cmp_wk_a" not in st.session_state or st.session_state["cmp_wk_a"] not in w_keys:
        st.session_state["cmp_wk_a"] = w_keys[0]
    if "cmp_wk_b" not in st.session_state or st.session_state["cmp_wk_b"] not in w_keys:
        st.session_state["cmp_wk_b"] = w_keys[min(1, len(w_keys) - 1)]
    if "cmp_wk_excl_match" not in st.session_state:
        st.session_state["cmp_wk_excl_match"] = True

    c1, c2, c3 = st.columns([1.8, 1.8, 1.2])
    idx_a = w_keys.index(st.session_state["cmp_wk_a"])
    idx_b = w_keys.index(st.session_state["cmp_wk_b"])
    wk_a_key = c1.selectbox("1. Settimana Raduno A (Riferimento)", w_keys, index=idx_a, format_func=lambda k: w_map[k]["label"], key="cmp_wk_a")
    wk_b_key = c2.selectbox("2. Settimana Raduno B (Confronto)", w_keys, index=idx_b, format_func=lambda k: w_map[k]["label"], key="cmp_wk_b")
    excl_matches = c3.checkbox("Solo Allenamenti (Escludi Match del Sabato)", value=st.session_state["cmp_wk_excl_match"], key="cmp_wk_excl_match")

    bundle = build_confronto_settimane_bundle(
        df_fir,
        wk_a_key=wk_a_key,
        wk_b_key=wk_b_key,
        excl_matches=excl_matches,
    )

    if not bundle:
        st.warning("Una delle due settimane selezionate non contiene sessioni GPS per il filtro scelto.")
        return

    wk_a = bundle["wk_a"]
    wk_b = bundle["wk_b"]
    summary_df = bundle["summary_df"]
    fig_h = bundle["fig_h"]
    fig_s = bundle["fig_s"]
    merged_p = bundle["merged_p"]

    st.markdown(f"#### 📊 Sintesi Comparativa: **{wk_a['short']}** vs **{wk_b['short']}**")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(fig_h, use_container_width=True)
    with g2:
        st.plotly_chart(fig_s, use_container_width=True)

    if not merged_p.empty:
        st.markdown(f"#### 👥 Confronto Individuale Atleti Presenti in Entrambi i Raduni ({len(merged_p)} giocatori)")
        p_rows = []
        for _, r in merged_p.sort_values(by=["dept_A", "player_name"]).iterrows():
            d_hml = r["hml_25_A"] - r["hml_25_B"]
            d_hsr = r["hsr_spec_A"] - r["hsr_spec_B"]
            p_rows.append({
                "Giocatore": r["player_name"],
                "Reparto": r["dept_A"],
                f"HML {wk_a['short']}": int(round(r["hml_25_A"])),
                f"HML {wk_b['short']}": int(round(r["hml_25_B"])),
                "Δ HML (m)": f"{d_hml:+.0f}",
                f"HSR {wk_a['short']}": int(round(r["hsr_spec_A"])),
                f"HSR {wk_b['short']}": int(round(r["hsr_spec_B"])),
                "Δ HSR (m)": f"{d_hsr:+.0f}",
                f"HML/min ({wk_a['short']} vs {wk_b['short']})": f"{r['hml_min_A']:.1f} vs {r['hml_min_B']:.1f}",
                f"HSR/min ({wk_a['short']} vs {wk_b['short']})": f"{r['hsr_min_A']:.2f} vs {r['hsr_min_B']:.2f}",
                f"Vmax ({wk_a['short']} vs {wk_b['short']})": f"{r['v_max_A']:.1f} vs {r['v_max_B']:.1f}",
            })
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
