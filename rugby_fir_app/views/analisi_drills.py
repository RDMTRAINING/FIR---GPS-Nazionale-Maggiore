# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo "🧩 Analisi & Confronto Drills" — FIR GPS Analytics Platform.
Permette di caricare, etichettare, archiviare (con Upsert su drills_master.parquet)
e confrontare i singoli blocchi di lavoro (drills) sia all'interno della singola seduta
sia in ottica longitudinale cross-session ("Drill Bank").
"""

import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import render_page_header, render_tab_navigation
import drills_manager
import utils

# Palette Istituzionale FIR
FIR_AZZURO = "#0066B2"
FIR_ORO = "#D4AF37"
FIR_NAVY = "#031926"
FIR_SLATE = "#475569"
FIR_LIGHT_BG = "#F8FAFC"
FIR_SKY = "#0EA5E9"
FIR_EMERALD = "#10B981"
FIR_CRIMSON = "#DC2626"

METRIC_LABELS: Dict[str, str] = {
    "Work_Rate": "Work Rate (m/min)",
    "Total_Distance": "Total Distance (m)",
    "HMPD": "HMPD (m)",
    "HMPD_per_Min": "HMPD / min (m/min)",
    "HSR": "HSR (m)",
    "HSR_per_Min": "HSR / min (m/min)",
    "VHSR": "VHSR >25 km/h (m)",
    "Max_Speed": "Max Speed Media (km/h)",
    "Max_Speed_Peak": "Picco Max Speed (km/h)",
    "Dynamic_Stress_Load": "Dynamic Stress Load / Ext Work",
    "Heavy_Impacts": "Heavy Impacts / Contatti",
    "Acc_Events": "Accelerazioni (n)",
    "Dec_Events": "Decelerazioni (n)",
    "Met_Power_Events": "Met Power Events (n)",
    "Avg_MP": "Avg Metabolic Power (W/kg)",
    "Duration_Min": "Durata (min)",
}

SESSION_PRESETS: List[str] = [
    "Captain's Run",
    "Rifinitura",
    "Volume",
    "Velocità",
    "Rugby",
    "Team Run",
    "Clarity",
    "Reparto",
    "Forza / Lavoro Fisico",
    "Extra",
]


def _clean_html(html_str: str) -> str:
    return "".join(line.strip() for line in str(html_str).splitlines() if line.strip())


def _render_kpi_card(label: str, value: str, subtext: str = "", accent: str = FIR_AZZURO) -> str:
    return _clean_html(
        f"""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid {accent};
                    border-radius:12px; padding:14px 16px; box-shadow:0 2px 8px rgba(3,25,38,0.06);">
            <div style="font-size:0.70rem; font-weight:800; text-transform:uppercase;
                        letter-spacing:0.06em; color:#64748B;">{label}</div>
            <div style="font-size:1.45rem; font-weight:900; color:{FIR_NAVY}; margin-top:4px; line-height:1.15;">
                {value}
            </div>
            <div style="font-size:0.74rem; color:#475569; margin-top:4px; font-weight:600;">
                {subtext}
            </div>
        </div>
        """
    )


def _build_roster_role_map() -> Dict[str, Tuple[str, str]]:
    """Costruisce mappa nome_normalizzato -> (ruolo, reparto) dal roster FIR attivo."""
    role_map: Dict[str, Tuple[str, str]] = {}
    try:
        pdf = utils.get_players_df()
        if pdf is not None and not pdf.empty:
            for _, row in pdf.iterrows():
                pname = str(row.get("name", "") or "").strip()
                role = str(row.get("role", "") or "").strip()
                dept = str(row.get("department", "") or "").strip()
                if not dept or dept == "N/D":
                    dept = drills_manager._classify_department(role)
                if pname:
                    role_map[drills_manager._norm_col(pname)] = (role, dept)
                    parts = pname.split()
                    if len(parts) >= 2:
                        rev = f"{parts[-1]} {' '.join(parts[:-1])}"
                        role_map[drills_manager._norm_col(rev)] = (role, dept)
    except Exception:
        pass
    return role_map


def _get_existing_fir_gps_sessions() -> List[Tuple[str, str]]:
    """Elenca le sedute FIR esistenti in `gps_history` (ordinate dalla più recente) per associazione rapida."""
    sessions: List[Tuple[str, str]] = []
    try:
        hdf = utils.get_gps_history_df(team_type="nazionale")
        if hdf is not None and not hdf.empty and "date" in hdf.columns and "session_name" in hdf.columns:
            pairs = (
                hdf[["date", "session_name"]]
                .dropna()
                .assign(
                    date=lambda d: d["date"].astype(str).str.slice(0, 10),
                    session_name=lambda d: d["session_name"].astype(str).str.strip(),
                )
                .drop_duplicates()
                .sort_values(by=["date", "session_name"], ascending=[False, True])
            )
            for _, r in pairs.head(80).iterrows():
                if r["date"] and r["session_name"]:
                    sessions.append((r["date"], r["session_name"]))
    except Exception:
        pass
    return sessions


def _apply_fir_plotly_layout(fig: go.Figure, title: str, height: int = 390) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=14, color=FIR_NAVY),
            x=0.01,
            xanchor="left",
        ),
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color=FIR_NAVY, size=12),
        margin=dict(l=45, r=45, t=54, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1.0,
            bgcolor="rgba(255,255,255,0.85)",
        ),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1", tickfont=dict(color=FIR_NAVY, size=11))
    fig.update_yaxes(gridcolor="#E2E8F0", linecolor="#CBD5E1", tickfont=dict(color=FIR_SLATE, size=11))
    return fig


def _render_tab_sessione(df_master: pd.DataFrame, df_players: pd.DataFrame, is_admin: bool):
    # =========================================================================
    # SEZIONE A — CARICAMENTO & ASSOCIAZIONE DRILLS (Solo Admin)
    # =========================================================================
    if is_admin:
        banner_html = f"""
        <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                    border-left:4px solid {FIR_ORO}; border-radius:10px;
                    padding:12px 16px; margin-bottom:14px;">
            <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
                📤 Caricamento &amp; Associazione Drills di Seduta
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Seleziona data e nome allenamento, carica i CSV/Excel dei singoli blocchi di lavoro (GPExe, Catapult o custom)
                e assegna a ciascun file il rispettivo <b>Drill_Name</b> e l'ordine cronologico (<b>Drill_Order</b>).
            </div>
        </div>
        """
        st.markdown(_clean_html(banner_html), unsafe_allow_html=True)

        with st.container(border=True):
            fir_sessions = _get_existing_fir_gps_sessions()
            mode_opts = ["Inserimento Manuale (Data + Nome Allenamento)"]
            if fir_sessions:
                mode_opts.insert(0, "Collega a una Seduta FIR già presente nel Database GPS")

            col_mode, col_info = st.columns([2, 3])
            with col_mode:
                sel_mode = st.radio(
                    "Modalità Associazione Sessione Madre",
                    options=mode_opts,
                    horizontal=True,
                    key="drills_session_mode",
                )

            if sel_mode.startswith("Collega") and fir_sessions:
                c_pick, c_override = st.columns([3, 2])
                sess_labels = [f"{d}  —  {n}" for d, n in fir_sessions]
                with c_pick:
                    picked_idx = st.selectbox(
                        "Seduta Madre FIR (Data — Nome Allenamento)",
                        options=list(range(len(sess_labels))),
                        format_func=lambda i: sess_labels[i],
                        key="drills_pick_fir_session",
                    )
                session_date_str, session_name_default = fir_sessions[picked_idx]
                with c_override:
                    session_name_str = st.text_input(
                        "Nome Allenamento (modificabile)",
                        value=session_name_default,
                        key=f"drills_override_name_{session_date_str}_{picked_idx}",
                    ).strip()
            else:
                c_dt, c_preset, c_custom = st.columns([1.2, 1.5, 2.0])
                with c_dt:
                    dt_val = st.date_input(
                        "Data Seduta (Session_Date)",
                        value=datetime.date.today(),
                        format="YYYY-MM-DD",
                        key="drills_manual_date",
                    )
                    session_date_str = dt_val.strftime("%Y-%m-%d")
                with c_preset:
                    preset_choice = st.selectbox(
                        "Tipologia / Preset Allenamento",
                        options=SESSION_PRESETS + ["Personalizzato..."],
                        key="drills_preset_name",
                    )
                with c_custom:
                    default_custom = "" if preset_choice == "Personalizzato..." else preset_choice
                    session_name_str = st.text_input(
                        "Nome Allenamento (Session_Name)",
                        value=default_custom,
                        placeholder="es. Captain's Run, Rifinitura, Forza...",
                        key="drills_custom_name",
                    ).strip()

            # Avviso Upsert preventivo se la sessione esiste già
            if session_date_str and session_name_str:
                existing_cnt = drills_manager.session_exists_in_drills(session_date_str, session_name_str)
                if existing_cnt > 0:
                    st.warning(
                        f"♻️ **Logica Upsert attiva:** esistono già **{existing_cnt} drill(s)** salvati per "
                        f"**{session_date_str} — {session_name_str}**. Al salvataggio i vecchi record di questa seduta "
                        f"verranno ripuliti e sostituiti in modo pulito senza creare duplicati."
                    )

            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            uploaded_files = st.file_uploader(
                "Carica i CSV / Excel dei singoli Drills della seduta (selezione multipla abilitata)",
                type=["csv", "xlsx", "xls"],
                accept_multiple_files=True,
                key="drills_multi_uploader",
                help="Puoi selezionare contemporaneamente tutti i file dei blocchi/drills (es. Warm Up, 1v1 Breakdown, Small Sided Games, Team Run).",
            )

            if uploaded_files:
                roster_map = _build_roster_role_map()
                existing_drill_names = sorted(df_master["Drill_Name"].dropna().unique().tolist()) if not df_master.empty else []

                parsed_items = []
                parse_errors = []
                for idx, uf in enumerate(uploaded_files):
                    try:
                        f_bytes = uf.getvalue()
                        summary_rec, player_recs, suggested = drills_manager.parse_drill_file(
                            f_bytes, uf.name, roster_role_map=roster_map
                        )
                        parsed_items.append((idx, uf.name, summary_rec, player_recs, suggested))
                    except Exception as exc:
                        parse_errors.append(f"❌ **{uf.name}**: {exc}")

                for err in parse_errors:
                    st.error(err)

                if parsed_items:
                    st.markdown(
                        _clean_html(
                            f"""
                            <div style="font-size:0.84rem; font-weight:800; color:{FIR_NAVY};
                                        margin:10px 0 6px 0; padding-bottom:4px;
                                        border-bottom:2px solid {FIR_AZZURO};">
                                🏷️ Assegnazione Dinamica Drill_Name &amp; Sequenza Cronologica (Drill_Order)
                            </div>
                            """
                        ),
                        unsafe_allow_html=True,
                    )
                    if existing_drill_names:
                        st.caption(
                            "💡 Suggerimento: per un confronto longitudinale accurato nel Drill Bank, puoi scegliere un nome già usato in archivio oppure digitarne uno nuovo."
                        )

                    configured_drills = []
                    configured_players = []

                    for pos_i, (orig_idx, fname, s_rec, p_recs, suggested) in enumerate(parsed_items, start=1):
                        key_base = f"drill_cfg_{orig_idx}_{abs(hash(fname)) % 100000}"
                        c_ord, c_bank, c_name, c_prev = st.columns([0.75, 1.65, 2.0, 2.8])
                        with c_ord:
                            d_order = st.number_input(
                                "Ordine",
                                min_value=1,
                                max_value=50,
                                value=pos_i,
                                step=1,
                                key=f"{key_base}_ord",
                            )
                        with c_bank:
                            bank_choice = st.selectbox(
                                "Preset Drill Bank",
                                options=["— Nome manuale —"] + existing_drill_names,
                                key=f"{key_base}_bank",
                            )
                        with c_name:
                            init_name = suggested if bank_choice == "— Nome manuale —" else bank_choice
                            d_name = st.text_input(
                                f"Drill_Name ({fname[:24]})",
                                value=init_name,
                                key=f"{key_base}_name_{bank_choice}",
                            ).strip()
                        with c_prev:
                            st.markdown(
                                _clean_html(
                                    f"""
                                    <div style="background:{FIR_LIGHT_BG}; border:1px solid #CBD5E1;
                                                border-left:3px solid {FIR_AZZURO}; border-radius:8px;
                                                padding:7px 10px; margin-top:22px; font-size:0.75rem; color:{FIR_NAVY};">
                                        <b>{s_rec['Players_Count']} atleti</b> · ⏱️ {s_rec['Duration_Min']:.1f}m ·
                                        📏 <b>{s_rec['Total_Distance']:.0f} m</b> ·
                                        ⚡ <b style="color:{FIR_AZZURO};">{s_rec['Work_Rate']:.1f} m/min</b><br>
                                        <span style="color:#475569;">
                                            HMPD: <b>{s_rec['HMPD']:.0f}m</b> · HSR: <b>{s_rec['HSR']:.0f}m</b> ·
                                            Vmax: <b>{s_rec['Max_Speed']:.1f}</b> · DSL: <b>{s_rec['Dynamic_Stress_Load']:.1f}</b> ·
                                            Imp: <b>{s_rec['Heavy_Impacts']:.1f}</b>
                                        </span>
                                    </div>
                                    """
                                ),
                                unsafe_allow_html=True,
                            )

                        final_dname = d_name or suggested or f"Drill {d_order}"
                        rec_copy = dict(s_rec)
                        rec_copy["Drill_Name"] = final_dname
                        rec_copy["Drill_Order"] = int(d_order)
                        configured_drills.append(rec_copy)

                        for pr in p_recs:
                            pr_copy = dict(pr)
                            pr_copy["Drill_Name"] = final_dname
                            pr_copy["Drill_Order"] = int(d_order)
                            configured_players.append(pr_copy)

                    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                    btn_save = st.button(
                        f"💾 Archivia {len(configured_drills)} Drills in drills_master.parquet ({session_date_str} · {session_name_str or 'Inserisci nome'})",
                        type="primary",
                        use_container_width=True,
                        key="btn_save_session_drills",
                        disabled=(not bool(session_name_str)),
                    )
                    if not session_name_str:
                        st.info("Inserisci un **Nome Allenamento** per abilitare il salvataggio.")

                    if btn_save and session_name_str:
                        removed_n, inserted_n = drills_manager.upsert_session_drills(
                            session_date=session_date_str,
                            session_name=session_name_str,
                            drill_records=configured_drills,
                            player_records=configured_players,
                        )
                        st.session_state["drills_last_saved_session"] = (session_date_str, session_name_str)
                        replace_note = f" (ripuliti e sostituiti {removed_n} vecchi record della seduta)" if removed_n > 0 else ""
                        st.session_state["drills_save_feedback"] = (
                            f"✅ Archiviati **{inserted_n} drills** per **{session_date_str} — {session_name_str}** "
                            f"in `drills_master.parquet` + Cloud Storage{replace_note}."
                        )
                        st.rerun()
    else:
        st.info("👁️ Modalità **Visualizzatore**: puoi consultare tutte le analisi comparative dei drills per seduta e il Drill Bank longitudinale.")

    if st.session_state.get("drills_save_feedback"):
        st.success(st.session_state.pop("drills_save_feedback"))

    # =========================================================================
    # SEZIONE B — VISUALIZZAZIONE IMMEDIATA PER SESSIONE
    # =========================================================================
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    sec_b_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_AZZURO} 0%, #004B87 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:11px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            📊 Analisi Comparativa Drills della Seduta
        </div>
        <div style="font-size:0.78rem; color:#E0F2FE; margin-top:2px;">
            Confronto cronologico (ordinato per <b>Drill_Order</b>) di volume, intensità metabolica, velocità e carico meccanico.
        </div>
    </div>
    """
    st.markdown(_clean_html(sec_b_html), unsafe_allow_html=True)

    if df_master.empty:
        st.info(
            "📭 Nessun drill ancora archiviato in `drills_master.parquet`. "
            "Carica uno o più CSV dei drills nella sezione sopra per iniziare l'analisi di seduta e popolare il Drill Bank."
        )
        return

    # Elenco sessioni uniche salvate (più recente in cima)
    sess_df = (
        df_master.groupby(["Session_Date", "Session_Name"], as_index=False)
        .agg(n_drills=("Drill_Name", "count"), tot_dur=("Duration_Min", "sum"))
        .sort_values(by=["Session_Date", "Session_Name"], ascending=[False, True])
        .reset_index(drop=True)
    )
    session_keys = [(r["Session_Date"], r["Session_Name"]) for _, r in sess_df.iterrows()]
    session_labels = [
        f"{r['Session_Date']}  —  {r['Session_Name']}  ({int(r['n_drills'])} drills · {r['tot_dur']:.0f} min)"
        for _, r in sess_df.iterrows()
    ]

    default_idx = 0
    last_saved = st.session_state.get("drills_last_saved_session")
    if last_saved and last_saved in session_keys:
        default_idx = session_keys.index(last_saved)

    col_sel_s, col_del_s = st.columns([4, 1.3])
    with col_sel_s:
        chosen_s_idx = st.selectbox(
            "Seleziona Seduta Archiviata da Analizzare",
            options=list(range(len(session_labels))),
            index=default_idx,
            format_func=lambda i: session_labels[i],
            key="drills_view_session_selector",
        )
    sel_date, sel_name = session_keys[chosen_s_idx]

    df_sess = df_master[
        (df_master["Session_Date"] == sel_date) & (df_master["Session_Name"] == sel_name)
    ].sort_values(by="Drill_Order", ascending=True).reset_index(drop=True)

    with col_del_s:
        if is_admin:
            st.markdown("<div style='height:27px;'></div>", unsafe_allow_html=True)
            with st.popover("🗑️ Elimina Seduta", use_container_width=True):
                st.caption(f"Rimuovi tutti i **{len(df_sess)} drills** di **{sel_date} — {sel_name}**?")
                if st.button("Conferma Eliminazione", type="primary", key="btn_confirm_del_drill_sess"):
                    del_cnt = drills_manager.delete_session_drills(sel_date, sel_name)
                    st.session_state.pop("drills_last_saved_session", None)
                    st.session_state["drills_save_feedback"] = f"🗑️ Eliminati **{del_cnt} drills** della seduta {sel_date} — {sel_name}."
                    st.rerun()

    # 4 Card KPI Seduta
    tot_dur = float(df_sess["Duration_Min"].sum())
    tot_dist = float(df_sess["Total_Distance"].sum())
    avg_wr = round(tot_dist / tot_dur, 1) if tot_dur > 0 else float(df_sess["Work_Rate"].mean())
    tot_hmpd = float(df_sess["HMPD"].sum())
    tot_hsr = float(df_sess["HSR"].sum())
    peak_vmax = float(df_sess["Max_Speed_Peak"].max()) if df_sess["Max_Speed_Peak"].max() > 0 else float(df_sess["Max_Speed"].max())
    tot_dsl = float(df_sess["Dynamic_Stress_Load"].sum())
    tot_imp = float(df_sess["Heavy_Impacts"].sum())

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            _render_kpi_card("Drills & Durata", f"{len(df_sess)} Drills", f"⏱️ {tot_dur:.1f} min totali", FIR_NAVY),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _render_kpi_card("Distanza & Work Rate", f"{tot_dist:,.0f} m", f"⚡ Media seduta: {avg_wr:.1f} m/min", FIR_AZZURO),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _render_kpi_card("HMPD & HSR Totali", f"{tot_hmpd:,.0f} m", f"🏃 HSR: {tot_hsr:,.0f} m", FIR_ORO),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _render_kpi_card("DSL & Picco Vmax", f"{tot_dsl:,.1f}", f"🚀 Vmax: {peak_vmax:.1f} km/h · Imp: {tot_imp:.0f}", FIR_NAVY),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # Etichette ordinate per Drill_Order
    df_sess["Drill_Label"] = df_sess.apply(lambda r: f"#{int(r['Drill_Order'])} {r['Drill_Name']}", axis=1)

    # Grafici a barre affiancati
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        fig1.add_trace(
            go.Bar(
                x=df_sess["Drill_Label"],
                y=df_sess["Total_Distance"],
                name="Total Distance (m)",
                marker=dict(color=FIR_AZZURO, line=dict(color=FIR_NAVY, width=1)),
                text=[f"{v:.0f}m" for v in df_sess["Total_Distance"]],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Distanza: %{y:.0f} m<extra></extra>",
            ),
            secondary_y=False,
        )
        fig1.add_trace(
            go.Scatter(
                x=df_sess["Drill_Label"],
                y=df_sess["Work_Rate"],
                name="Work Rate (m/min)",
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=9, color=FIR_ORO, line=dict(color=FIR_NAVY, width=1.5)),
                text=[f"{v:.1f}" for v in df_sess["Work_Rate"]],
                textposition="top center",
                textfont=dict(color=FIR_NAVY, size=11),
                hovertemplate="<b>%{x}</b><br>Work Rate: %{y:.1f} m/min<extra></extra>",
            ),
            secondary_y=True,
        )
        fig1.update_yaxes(title_text="Distanza (m)", secondary_y=False)
        fig1.update_yaxes(title_text="Work Rate (m/min)", secondary_y=True, showgrid=False)
        _apply_fir_plotly_layout(fig1, f"Volume (m) vs Intensità (m/min) — {sel_name}", height=390)
        st.plotly_chart(fig1, use_container_width=True)

    with col_g2:
        has_reparti = (df_sess["Avanti_Work_Rate"].sum() > 0) and (df_sess["Trequarti_Work_Rate"].sum() > 0)
        chart_modes = [
            "HMPD (m) vs HSR (m)",
            "Dynamic Stress Load vs Heavy Impacts",
            "Max Speed Media vs Picco (km/h)",
            "Accelerazioni vs Decelerazioni",
        ]
        if has_reparti:
            chart_modes.insert(1, "Avanti vs Trequarti — Work Rate (m/min)")

        g2_mode = st.selectbox("Confronto Secondario Drills", options=chart_modes, key="drills_sess_chart2_mode")

        if g2_mode == "HMPD (m) vs HSR (m)":
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["HMPD"], name="HMPD (m)", marker_color=FIR_NAVY, text=[f"{v:.0f}" for v in df_sess["HMPD"]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["HSR"], name="HSR (m)", marker_color=FIR_ORO, text=[f"{v:.0f}" for v in df_sess["HSR"]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, "Alta Intensità Metabolica & Corsa — HMPD vs HSR", height=350)
        elif g2_mode == "Avanti vs Trequarti — Work Rate (m/min)":
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Avanti_Work_Rate"], name="Avanti (m/min)", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Avanti_Work_Rate"]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Trequarti_Work_Rate"], name="Trequarti (m/min)", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Trequarti_Work_Rate"]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, "Confronto Reparti: Avanti vs Trequarti (Work Rate)", height=350)
        elif g2_mode == "Dynamic Stress Load vs Heavy Impacts":
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Dynamic_Stress_Load"], name="Dynamic Stress Load", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Dynamic_Stress_Load"]], textposition="outside"), secondary_y=False)
            fig2.add_trace(go.Scatter(x=df_sess["Drill_Label"], y=df_sess["Heavy_Impacts"], name="Heavy Impacts", mode="lines+markers+text", line=dict(color=FIR_CRIMSON, width=2.5), marker=dict(size=8), text=[f"{v:.1f}" for v in df_sess["Heavy_Impacts"]], textposition="top center"), secondary_y=True)
            fig2.update_yaxes(title_text="DSL / Ext Work", secondary_y=False)
            fig2.update_yaxes(title_text="Heavy Impacts", secondary_y=True, showgrid=False)
            _apply_fir_plotly_layout(fig2, "Carico Meccanico — DSL vs Heavy Impacts", height=350)
        elif g2_mode == "Max Speed Media vs Picco (km/h)":
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed"], name="Max Speed Media", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Max_Speed"]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed_Peak"], name="Picco Individuale", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Max_Speed_Peak"]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, "Velocità Massima per Drill (km/h)", height=350)
        else:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Acc_Events"], name="Accelerazioni", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Acc_Events"]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Dec_Events"], name="Decelerazioni", marker_color=FIR_NAVY, text=[f"{v:.1f}" for v in df_sess["Dec_Events"]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, "Eventi Neuromuscolari — Accelerazioni vs Decelerazioni", height=350)

        st.plotly_chart(fig2, use_container_width=True)

    # Tabella comparativa completa della seduta
    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📋 Tabella Comparativa Drills — {sel_date} · {sel_name}</div>",
        unsafe_allow_html=True,
    )
    disp_cols = [
        "Drill_Order", "Drill_Name", "Players_Count", "Duration_Min",
        "Total_Distance", "Work_Rate", "HMPD", "HMPD_per_Min",
        "HSR", "HSR_per_Min", "VHSR", "Max_Speed", "Max_Speed_Peak",
        "Dynamic_Stress_Load", "Heavy_Impacts", "Acc_Events", "Dec_Events",
    ]
    df_table = df_sess[disp_cols].rename(
        columns={
            "Drill_Order": "Ord.",
            "Drill_Name": "Drill",
            "Players_Count": "Atleti",
            "Duration_Min": "Durata (m)",
            "Total_Distance": "Distanza (m)",
            "Work_Rate": "Work Rate (m/m)",
            "HMPD": "HMPD (m)",
            "HMPD_per_Min": "HMPD/m",
            "HSR": "HSR (m)",
            "HSR_per_Min": "HSR/m",
            "VHSR": "VHSR (m)",
            "Max_Speed": "Vmax Med",
            "Max_Speed_Peak": "Vmax Picco",
            "Dynamic_Stress_Load": "DSL / ExtWork",
            "Heavy_Impacts": "Heavy Imp.",
            "Acc_Events": "Acc",
            "Dec_Events": "Dec",
        }
    )
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # Export CSV della seduta
    csv_sess = df_sess.drop(columns=["Drill_Label"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Esporta CSV Drills Seduta",
        data=csv_sess,
        file_name=f"FIR_Drills_{sel_date}_{sel_name.replace(' ', '_')}.csv",
        mime="text/csv",
        key="dl_session_drills_csv",
    )

    # Expander Dettaglio Individuale Atleti per Drill (se presente)
    if df_players is not None and not df_players.empty:
        df_ps = df_players[
            (df_players["Session_Date"] == sel_date) & (df_players["Session_Name"] == sel_name)
        ].copy()
        if not df_ps.empty:
            with st.expander(f"👥 Dettaglio Individuale Atleti per Drill ({len(df_ps)} tracce)", expanded=False):
                drill_filter = st.selectbox(
                    "Filtra per Drill",
                    options=["Tutti i Drills"] + df_sess["Drill_Name"].tolist(),
                    key="drills_player_detail_filter",
                )
                if drill_filter != "Tutti i Drills":
                    df_ps = df_ps[df_ps["Drill_Name"] == drill_filter]
                st.dataframe(
                    df_ps[[
                        "Drill_Order", "Drill_Name", "Player_Name", "Role", "Department",
                        "Duration_Min", "Total_Distance", "Work_Rate", "HMPD", "HSR",
                        "Max_Speed", "Dynamic_Stress_Load", "Heavy_Impacts",
                    ]].sort_values(by=["Drill_Order", "Work_Rate"], ascending=[True, False]),
                    use_container_width=True,
                    hide_index=True,
                )


def _render_tab_drill_bank(df_master: pd.DataFrame):
    banner_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:12px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            🔍 Archivio Globale &amp; Analisi Cross-Session — FIR Drill Bank
        </div>
        <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
            Analizza l'evoluzione longitudinale di una specifica esercitazione nel tempo (Work Rate, DSL, HMPD, HSR, Max Speed)
            e confronta i profili di carico dei diversi drills archiviati.
        </div>
    </div>
    """
    st.markdown(_clean_html(banner_html), unsafe_allow_html=True)

    if df_master.empty:
        st.info(
            "📭 Il **Drill Bank** è attualmente vuoto. Carica almeno una seduta nel Tab **📂 Gestione & Vista per Sessione** "
            "per sbloccare l'analisi longitudinale cross-session."
        )
        return

    # Calcolo statistiche globali per Drill_Name
    drill_counts = df_master.groupby("Drill_Name").size().sort_values(ascending=False)
    unique_drills = drill_counts.index.tolist()

    c_pick_d, c_m1, c_m2 = st.columns([2.2, 1.4, 1.4])
    with c_pick_d:
        selected_drill = st.selectbox(
            "🎯 Seleziona Drill dallo Storico (Drill Bank)",
            options=unique_drills,
            format_func=lambda d: f"{d}  ({int(drill_counts[d])} esecuzioni)",
            key="drill_bank_select_drill",
        )
    with c_m1:
        primary_metric = st.selectbox(
            "Metrica Primaria (Barre)",
            options=list(METRIC_LABELS.keys()),
            index=0,  # Work_Rate
            format_func=lambda k: METRIC_LABELS[k],
            key="drill_bank_primary_metric",
        )
    with c_m2:
        sec_options = ["Nessuna"] + list(METRIC_LABELS.keys())
        default_sec_idx = sec_options.index("Dynamic_Stress_Load")
        secondary_metric = st.selectbox(
            "Metrica Secondaria (Linea)",
            options=sec_options,
            index=default_sec_idx,
            format_func=lambda k: "— Nessuna —" if k == "Nessuna" else METRIC_LABELS[k],
            key="drill_bank_secondary_metric",
        )

    df_d = df_master[df_master["Drill_Name"] == selected_drill].sort_values(
        by=["Session_Date", "Drill_Order"], ascending=[True, True]
    ).reset_index(drop=True)

    # KPI Longitudinali del Drill selezionato
    n_exec = len(df_d)
    mean_wr = float(df_d["Work_Rate"].mean())
    last_wr = float(df_d["Work_Rate"].iloc[-1])
    delta_wr_pct = ((last_wr - mean_wr) / mean_wr * 100.0) if mean_wr > 0 else 0.0
    mean_hmpd = float(df_d["HMPD"].mean())
    mean_hsr = float(df_d["HSR"].mean())
    mean_dsl = float(df_d["Dynamic_Stress_Load"].mean())
    mean_imp = float(df_d["Heavy_Impacts"].mean())
    best_vmax = float(df_d["Max_Speed_Peak"].max()) if df_d["Max_Speed_Peak"].max() > 0 else float(df_d["Max_Speed"].max())

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(
            _render_kpi_card("Esecuzioni Storiche", f"{n_exec}", f"Ultima: {df_d['Session_Date'].iloc[-1]}", FIR_NAVY),
            unsafe_allow_html=True,
        )
    with k2:
        delta_sign = "+" if delta_wr_pct >= 0 else ""
        st.markdown(
            _render_kpi_card("Work Rate Medio", f"{mean_wr:.1f} m/m", f"Ultima: {last_wr:.1f} ({delta_sign}{delta_wr_pct:.1f}%)", FIR_AZZURO),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _render_kpi_card("HMPD Medio", f"{mean_hmpd:.0f} m", f"Media/min: {df_d['HMPD_per_Min'].mean():.1f} m/m", FIR_ORO),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _render_kpi_card("HSR Medio", f"{mean_hsr:.0f} m", f"Picco Vmax: {best_vmax:.1f} km/h", FIR_AZZURO),
            unsafe_allow_html=True,
        )
    with k5:
        st.markdown(
            _render_kpi_card("DSL / Ext Work Medio", f"{mean_dsl:.1f}", f"Heavy Imp. medi: {mean_imp:.1f}", FIR_NAVY),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    df_d["Exec_Label"] = df_d.apply(
        lambda r: f"{r['Session_Date']}<br>{r['Session_Name']} (#{int(r['Drill_Order'])})", axis=1
    )

    # Grafico Longitudinale Principale
    fig_long = make_subplots(specs=[[{"secondary_y": True}]])
    p_vals = pd.to_numeric(df_d[primary_metric], errors="coerce").fillna(0.0)
    p_mean = float(p_vals.mean())

    fig_long.add_trace(
        go.Bar(
            x=df_d["Exec_Label"],
            y=p_vals,
            name=METRIC_LABELS[primary_metric],
            marker=dict(color=FIR_AZZURO, line=dict(color=FIR_NAVY, width=1)),
            text=[f"{v:.1f}" for v in p_vals],
            textposition="outside",
        ),
        secondary_y=False,
    )
    fig_long.add_hline(
        y=p_mean,
        line_dash="dash",
        line_color=FIR_NAVY,
        line_width=2,
        annotation_text=f"Media storica: {p_mean:.1f}",
        annotation_position="top left",
        secondary_y=False,
    )

    if secondary_metric != "Nessuna" and secondary_metric != primary_metric:
        s_vals = pd.to_numeric(df_d[secondary_metric], errors="coerce").fillna(0.0)
        fig_long.add_trace(
            go.Scatter(
                x=df_d["Exec_Label"],
                y=s_vals,
                name=METRIC_LABELS[secondary_metric],
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=9, color=FIR_ORO, line=dict(color=FIR_NAVY, width=1.5)),
                text=[f"{v:.1f}" for v in s_vals],
                textposition="top center",
            ),
            secondary_y=True,
        )
        fig_long.update_yaxes(title_text=METRIC_LABELS[secondary_metric], secondary_y=True, showgrid=False)

    fig_long.update_yaxes(title_text=METRIC_LABELS[primary_metric], secondary_y=False)
    _apply_fir_plotly_layout(fig_long, f"Evoluzione Longitudinale: {selected_drill}", height=410)
    st.plotly_chart(fig_long, use_container_width=True)

    # Secondo grafico longitudinale: HMPD & HSR nel tempo
    fig_hi = go.Figure()
    fig_hi.add_trace(
        go.Scatter(
            x=df_d["Exec_Label"],
            y=df_d["HMPD"],
            name="HMPD (m)",
            mode="lines+markers",
            line=dict(color=FIR_NAVY, width=3),
            marker=dict(size=8, color=FIR_NAVY),
            fill="tozeroy",
            fillcolor="rgba(3,25,38,0.08)",
        )
    )
    fig_hi.add_trace(
        go.Scatter(
            x=df_d["Exec_Label"],
            y=df_d["HSR"],
            name="HSR (m)",
            mode="lines+markers",
            line=dict(color=FIR_ORO, width=3),
            marker=dict(size=8, color=FIR_ORO),
        )
    )
    _apply_fir_plotly_layout(fig_hi, f"Trend Alta Intensità nel Tempo (HMPD & HSR) — {selected_drill}", height=330)
    st.plotly_chart(fig_hi, use_container_width=True)

    # Tabella Storica Occorrenze Cross-Session con Delta % vs Media Storica
    df_hist_view = df_d.copy()
    df_hist_view["Delta_WR_%"] = np.where(mean_wr > 0, ((df_hist_view["Work_Rate"] - mean_wr) / mean_wr) * 100.0, 0.0).round(1)
    df_hist_view["Delta_DSL_%"] = np.where(mean_dsl > 0, ((df_hist_view["Dynamic_Stress_Load"] - mean_dsl) / mean_dsl) * 100.0, 0.0).round(1)

    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📑 Storico Completo Esecuzioni: {selected_drill}</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        df_hist_view[[
            "Session_Date", "Session_Name", "Drill_Order", "Players_Count",
            "Duration_Min", "Total_Distance", "Work_Rate", "Delta_WR_%",
            "HMPD", "HSR", "Max_Speed", "Dynamic_Stress_Load", "Delta_DSL_%", "Heavy_Impacts",
        ]].rename(
            columns={
                "Session_Date": "Data",
                "Session_Name": "Allenamento",
                "Drill_Order": "Ord.",
                "Players_Count": "Atleti",
                "Duration_Min": "Durata (m)",
                "Total_Distance": "Distanza (m)",
                "Work_Rate": "Work Rate",
                "Delta_WR_%": "Δ WR %",
                "HMPD": "HMPD (m)",
                "HSR": "HSR (m)",
                "Max_Speed": "Vmax Med",
                "Dynamic_Stress_Load": "DSL",
                "Delta_DSL_%": "Δ DSL %",
                "Heavy_Impacts": "Heavy Imp.",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    csv_drill = df_d.drop(columns=["Exec_Label"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        f"⬇️ Esporta Storico CSV ({selected_drill})",
        data=csv_drill,
        file_name=f"FIR_DrillBank_{selected_drill.replace(' ', '_')}.csv",
        mime="text/csv",
        key="dl_drill_bank_single_csv",
    )

    # =========================================================================
    # CONFRONTO MULTI-DRILL & CATALOGO COMPLETO DRILL BANK
    # =========================================================================
    st.markdown("<hr style='margin:22px 0; border-color:#CBD5E1;'>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:1.0rem; font-weight:900; color:{FIR_NAVY}; margin-bottom:8px;'>⚖️ Confronto Multi-Drill &amp; Catalogo Completo Drill Bank</div>",
        unsafe_allow_html=True,
    )

    bank_summary = (
        df_master.groupby("Drill_Name", as_index=False)
        .agg(
            Esecuzioni=("Session_Date", "count"),
            Ultima_Data=("Session_Date", "max"),
            Durata_Media=("Duration_Min", "mean"),
            Distanza_Media=("Total_Distance", "mean"),
            Work_Rate_Medio=("Work_Rate", "mean"),
            HMPD_Medio=("HMPD", "mean"),
            HMPD_min_Medio=("HMPD_per_Min", "mean"),
            HSR_Medio=("HSR", "mean"),
            Vmax_Media=("Max_Speed", "mean"),
            DSL_Medio=("Dynamic_Stress_Load", "mean"),
            Heavy_Imp_Medi=("Heavy_Impacts", "mean"),
        )
        .sort_values(by="Work_Rate_Medio", ascending=False)
        .reset_index(drop=True)
    )
    for num_c in [
        "Durata_Media", "Distanza_Media", "Work_Rate_Medio", "HMPD_Medio",
        "HMPD_min_Medio", "HSR_Medio", "Vmax_Media", "DSL_Medio", "Heavy_Imp_Medi",
    ]:
        bank_summary[num_c] = bank_summary[num_c].round(1)

    if len(unique_drills) >= 2:
        c_ms, c_cm = st.columns([3, 1.5])
        with c_ms:
            compare_drills = st.multiselect(
                "Seleziona Drills da Confrontare (Medie Storiche)",
                options=unique_drills,
                default=unique_drills[: min(6, len(unique_drills))],
                key="drill_bank_compare_multi",
            )
        with c_cm:
            comp_metric_map = {
                "Work_Rate_Medio": "Work Rate Medio (m/min)",
                "HMPD_Medio": "HMPD Medio (m)",
                "HMPD_min_Medio": "HMPD/min Medio",
                "HSR_Medio": "HSR Medio (m)",
                "Distanza_Media": "Distanza Media (m)",
                "DSL_Medio": "DSL / Ext Work Medio",
                "Heavy_Imp_Medi": "Heavy Impacts Medi",
                "Vmax_Media": "Max Speed Media (km/h)",
            }
            comp_m = st.selectbox(
                "Parametro Confronto",
                options=list(comp_metric_map.keys()),
                format_func=lambda k: comp_metric_map[k],
                key="drill_bank_compare_metric",
            )
        if compare_drills:
            df_cmp = bank_summary[bank_summary["Drill_Name"].isin(compare_drills)].sort_values(by=comp_m, ascending=True)
            fig_cmp = go.Figure(
                go.Bar(
                    y=df_cmp["Drill_Name"],
                    x=df_cmp[comp_m],
                    orientation="h",
                    marker=dict(
                        color=[FIR_ORO if d == selected_drill else FIR_AZZURO for d in df_cmp["Drill_Name"]],
                        line=dict(color=FIR_NAVY, width=1),
                    ),
                    text=[f"{v:.1f}" for v in df_cmp[comp_m]],
                    textposition="outside",
                )
            )
            _apply_fir_plotly_layout(fig_cmp, f"Benchmark Drill Bank — {comp_metric_map[comp_m]}", height=max(300, 48 * len(df_cmp) + 90))
            st.plotly_chart(fig_cmp, use_container_width=True)

    st.dataframe(
        bank_summary.rename(
            columns={
                "Drill_Name": "Drill",
                "Ultima_Data": "Ultima Esec.",
                "Durata_Media": "Durata (m)",
                "Distanza_Media": "Dist. (m)",
                "Work_Rate_Medio": "Work Rate",
                "HMPD_Medio": "HMPD (m)",
                "HMPD_min_Medio": "HMPD/m",
                "HSR_Medio": "HSR (m)",
                "Vmax_Media": "Vmax",
                "DSL_Medio": "DSL",
                "Heavy_Imp_Medi": "Heavy Imp.",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    csv_all = df_master.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Esporta Intero Archivio drills_master.csv",
        data=csv_all,
        file_name="FIR_drills_master_export.csv",
        mime="text/csv",
        key="dl_drill_bank_all_csv",
    )


def render_analisi_drills(t: dict):
    """Entrypoint della pagina 🧩 Analisi & Confronto Drills."""
    render_page_header(
        "🧩 Analisi & Confronto Drills",
        "Archivio persistente blocchi di lavoro (drills_master.parquet), confronto per seduta e Drill Bank longitudinale FIR",
        icon="bi-puzzle-fill",
    )

    user_role = st.session_state.get("user_role", "viewer")
    is_admin = (user_role == "admin")

    active_tab = render_tab_navigation(
        page_key="analisi_drills",
        tabs=[
            ("gestione_sessione", "📂 Gestione & Vista per Sessione", "bi-folder2-open"),
            ("drill_bank", "🔍 Archivio Globale & Cross-Session (Drill Bank)", "bi-search"),
        ],
    )

    df_master = drills_manager.load_drills_master()
    df_players = drills_manager.load_drills_players_detail()

    if active_tab == "gestione_sessione":
        _render_tab_sessione(df_master, df_players, is_admin=is_admin)
    else:
        _render_tab_drill_bank(df_master)
