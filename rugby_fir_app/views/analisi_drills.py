# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo "🧩 Analisi & Confronto Drills" — FIR GPS Analytics Platform.
Gestisce caricamento multiplo, riconoscimento automatico giocatori attivi (esclusione panchina/rotazioni),
normalizzazione dinamica per ruolo/numero effettivo di atleti attivi,
visualizzazione distinta di Carico Totale Gruppo/Reparto vs Carico Medio Normalizzato pro-capite
e Drill Bank longitudinale cross-session.
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
FIR_EMERALD = "#10B981"
FIR_CRIMSON = "#DC2626"

METRIC_LABELS_AVG: Dict[str, str] = {
    "Work_Rate": "Work Rate Pro-Capite (m/min)",
    "Total_Distance": "Distanza Media Pro-Capite (m)",
    "HMPD": "HMPD Medio Pro-Capite (m)",
    "HMPD_per_Min": "HMPD/min Pro-Capite (m/min)",
    "HSR": "HSR Medio Pro-Capite (m)",
    "HSR_per_Min": "HSR/min Pro-Capite (m/min)",
    "VHSR": "VHSR >25 km/h Pro-Capite (m)",
    "Max_Speed": "Max Speed Media Attivi (km/h)",
    "Max_Speed_Peak": "Picco Max Speed (km/h)",
    "Dynamic_Stress_Load": "DSL / Ext Work Pro-Capite",
    "Heavy_Impacts": "Heavy Impacts Pro-Capite",
    "Acc_Events": "Accelerazioni Pro-Capite (n)",
    "Dec_Events": "Decelerazioni Pro-Capite (n)",
    "Avg_MP": "Avg Metabolic Power (W/kg)",
    "Duration_Min": "Durata Media (min)",
}

METRIC_LABELS_TOTAL: Dict[str, str] = {
    "Total_Distance_Sum": "Distanza Totale Gruppo (m)",
    "HMPD_Sum": "HMPD Totale Gruppo (m)",
    "HSR_Sum": "HSR Totale Gruppo (m)",
    "VHSR_Sum": "VHSR Totale Gruppo (m)",
    "Dynamic_Stress_Load_Sum": "DSL / Ext Work Totale Gruppo",
    "Heavy_Impacts_Sum": "Heavy Impacts Totali Gruppo",
    "Acc_Events_Sum": "Accelerazioni Totali Gruppo (n)",
    "Dec_Events_Sum": "Decelerazioni Totali Gruppo (n)",
}

ROLE_METRIC_PAIRS: Dict[str, Tuple[str, str, str]] = {
    "Total_Distance": ("Distanza (m)", "Total_Distance", "Total_Distance_Sum"),
    "HMPD": ("HMPD (m)", "HMPD", "HMPD_Sum"),
    "HSR": ("HSR (m)", "HSR", "HSR_Sum"),
    "Dynamic_Stress_Load": ("DSL / Ext Work", "Dynamic_Stress_Load", "Dynamic_Stress_Load_Sum"),
    "Heavy_Impacts": ("Heavy Impacts", "Heavy_Impacts", "Heavy_Impacts_Sum"),
    "Acc_Events": ("Accelerazioni (n)", "Acc_Events", "Acc_Events_Sum"),
    "Dec_Events": ("Decelerazioni (n)", "Dec_Events", "Dec_Events_Sum"),
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
            <div style="font-size:1.42rem; font-weight:900; color:{FIR_NAVY}; margin-top:4px; line-height:1.15;">
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
                    _, dept = drills_manager.normalize_role_and_department(role)
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
    """Elenca le sedute FIR esistenti in `gps_history` (ordinate dalla più recente)."""
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


def _render_role_normalization_block(
    df_roles_scope: pd.DataFrame,
    title_prefix: str,
    key_prefix: str,
):
    """
    Sezione riutilizzabile che mostra distintamente:
      - Media Normalizzata Pro-Capite per Ruolo (Carico Totale Ruolo / N° Effettivo Atleti Attivi)
      - Carico Totale Energetico erogato dal Ruolo (Somma Gruppo Attivo)
    """
    if df_roles_scope is None or df_roles_scope.empty:
        st.caption("ℹ️ Dettaglio normalizzato per ruolo disponibile per i drills caricati da CSV multi-atleta con colonna ruolo/roster.")
        return

    sec_role_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:10px 16px; margin:16px 0 12px 0;">
        <div style="font-size:0.92rem; font-weight:800; color:#FFFFFF;">
            🏉 Normalizzazione Dinamica per Ruolo — {title_prefix}
        </div>
        <div style="font-size:0.76rem; color:#CBD5E1; margin-top:2px;">
            Formula applicata su ciascun ruolo: <b>Media Pro-Capite = Carico Totale del Ruolo / Numero Effettivo di Atleti Attivi in Campo</b>
            (esclusi automaticamente panchina e rotazioni).
        </div>
    </div>
    """
    st.markdown(_clean_html(sec_role_html), unsafe_allow_html=True)

    # Aggrega se ci sono più drills/esecuzioni nello scope (mantenendo esatta media pesata sul numero effettivo di attivi!)
    agg = (
        df_roles_scope.groupby(["Role", "Department"], as_index=False)
        .agg(
            Esecuzioni=("Drill_Order", "count"),
            Attivi_Totali=("Active_Players_Count", "sum"),
            Attivi_Medi=("Active_Players_Count", "mean"),
            Esclusi_Totali=("Excluded_Players_Count", "sum"),
            Duration_Min=("Duration_Min", "mean"),
            Total_Distance_Sum=("Total_Distance_Sum", "sum"),
            HMPD_Sum=("HMPD_Sum", "sum"),
            HSR_Sum=("HSR_Sum", "sum"),
            VHSR_Sum=("VHSR_Sum", "sum"),
            Dynamic_Stress_Load_Sum=("Dynamic_Stress_Load_Sum", "sum"),
            Heavy_Impacts_Sum=("Heavy_Impacts_Sum", "sum"),
            Acc_Events_Sum=("Acc_Events_Sum", "sum"),
            Dec_Events_Sum=("Dec_Events_Sum", "sum"),
            Max_Speed=("Max_Speed", "mean"),
            Max_Speed_Peak=("Max_Speed_Peak", "max"),
        )
    )
    # Calcolo rigoroso Media Normalizzata Pro-Capite = Somma Totale del Ruolo / Attivi Totali
    denom = agg["Attivi_Totali"].replace(0, np.nan)
    agg["Total_Distance"] = (agg["Total_Distance_Sum"] / denom).fillna(0.0).round(1)
    agg["HMPD"] = (agg["HMPD_Sum"] / denom).fillna(0.0).round(1)
    agg["HSR"] = (agg["HSR_Sum"] / denom).fillna(0.0).round(1)
    agg["VHSR"] = (agg["VHSR_Sum"] / denom).fillna(0.0).round(1)
    agg["Dynamic_Stress_Load"] = (agg["Dynamic_Stress_Load_Sum"] / denom).fillna(0.0).round(1)
    agg["Heavy_Impacts"] = (agg["Heavy_Impacts_Sum"] / denom).fillna(0.0).round(1)
    agg["Acc_Events"] = (agg["Acc_Events_Sum"] / denom).fillna(0.0).round(1)
    agg["Dec_Events"] = (agg["Dec_Events_Sum"] / denom).fillna(0.0).round(1)
    agg["Work_Rate"] = np.where(agg["Duration_Min"] > 0, agg["Total_Distance"] / agg["Duration_Min"], 0.0).round(1)

    order_map = {r: i for i, r in enumerate(drills_manager.CANONICAL_ROLE_ORDER)}
    agg["_ord"] = agg["Role"].map(lambda x: order_map.get(x, 99))
    agg = agg.sort_values(by=["_ord", "Role"]).drop(columns=["_ord"]).reset_index(drop=True)

    c_rmet, c_rdept = st.columns([2, 1.5])
    with c_rmet:
        sel_rmet = st.selectbox(
            "Metrica da confrontare per Ruolo (Pro-Capite vs Totale Ruolo)",
            options=list(ROLE_METRIC_PAIRS.keys()),
            format_func=lambda k: ROLE_METRIC_PAIRS[k][0],
            key=f"{key_prefix}_role_metric_sel",
        )
    with c_rdept:
        dept_filter = st.radio(
            "Filtro Reparto",
            options=["Tutti", "Avanti", "Trequarti"],
            horizontal=True,
            key=f"{key_prefix}_role_dept_filter",
        )

    if dept_filter != "Tutti":
        agg_plot = agg[agg["Department"] == dept_filter].copy()
    else:
        agg_plot = agg.copy()

    if agg_plot.empty:
        st.info(f"Nessun dato attivo disponibile per il reparto **{dept_filter}**.")
        return

    met_label, col_avg, col_sum = ROLE_METRIC_PAIRS[sel_rmet]
    agg_plot["Role_Tag"] = agg_plot.apply(
        lambda r: f"{r['Role']}<br>(n={r['Attivi_Medi']:.0f} att.)" if r["Esecuzioni"] == 1 else f"{r['Role']}<br>(~{r['Attivi_Medi']:.1f} att.)",
        axis=1,
    )
    bar_colors = [FIR_AZZURO if d == "Avanti" else (FIR_ORO if d == "Trequarti" else FIR_SLATE) for d in agg_plot["Department"]]

    g_left, g_right = st.columns(2)
    with g_left:
        fig_norm = go.Figure(
            go.Bar(
                x=agg_plot["Role_Tag"],
                y=agg_plot[col_avg],
                marker=dict(color=bar_colors, line=dict(color=FIR_NAVY, width=1)),
                text=[f"{v:.1f}" for v in agg_plot[col_avg]],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Media Pro-Capite: %{y:.1f}<extra></extra>",
            )
        )
        _apply_fir_plotly_layout(fig_norm, f"👤 Media Normalizzata Pro-Capite — {met_label}", height=360)
        fig_norm.update_layout(showlegend=False)
        st.plotly_chart(fig_norm, use_container_width=True)

    with g_right:
        fig_tot = go.Figure(
            go.Bar(
                x=agg_plot["Role_Tag"],
                y=agg_plot[col_sum],
                marker=dict(color=FIR_NAVY, line=dict(color=FIR_ORO, width=1.2)),
                text=[f"{v:,.0f}" for v in agg_plot[col_sum]],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Carico Totale Ruolo: %{y:,.1f}<extra></extra>",
            )
        )
        _apply_fir_plotly_layout(fig_tot, f"∑ Carico Totale del Ruolo (Gruppo Attivo) — {met_label}", height=360)
        fig_tot.update_layout(showlegend=False)
        st.plotly_chart(fig_tot, use_container_width=True)

    # Tabella riepilogativa completa per Ruolo (Totale vs Media Pro-Capite)
    st.dataframe(
        agg_plot[[
            "Role", "Department", "Attivi_Medi", "Esclusi_Totali",
            "Total_Distance", "Total_Distance_Sum", "Work_Rate",
            "HMPD", "HMPD_Sum", "HSR", "HSR_Sum",
            "Dynamic_Stress_Load", "Dynamic_Stress_Load_Sum", "Max_Speed",
        ]].rename(
            columns={
                "Role": "Ruolo",
                "Department": "Reparto",
                "Attivi_Medi": "Attivi (Med.)",
                "Esclusi_Totali": "Esclusi",
                "Total_Distance": "Dist. Pro-Capite (m)",
                "Total_Distance_Sum": "Dist. Totale Ruolo (m)",
                "Work_Rate": "WR Pro-Capite",
                "HMPD": "HMPD Pro-Capite",
                "HMPD_Sum": "HMPD Totale Ruolo",
                "HSR": "HSR Pro-Capite",
                "HSR_Sum": "HSR Totale Ruolo",
                "Dynamic_Stress_Load": "DSL Pro-Capite",
                "Dynamic_Stress_Load_Sum": "DSL Totale Ruolo",
                "Max_Speed": "Vmax Med.",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_tab_sessione(
    df_master: pd.DataFrame,
    df_roles: pd.DataFrame,
    df_players: pd.DataFrame,
    is_admin: bool,
):
    # =========================================================================
    # SEZIONE A — CARICAMENTO & ASSOCIAZIONE DRILLS (Solo Admin)
    # =========================================================================
    if is_admin:
        banner_html = f"""
        <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                    border-left:4px solid {FIR_ORO}; border-radius:10px;
                    padding:12px 16px; margin-bottom:14px;">
            <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
                📤 Caricamento &amp; Associazione Drills di Seduta (con Filtro Automatico Giocatori Attivi)
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Il parser isola automaticamente gli atleti in panchina/rotazione o con valori nulli,
                calcolando sia il <b>Carico Totale del Gruppo/Reparto</b> sia la <b>Media Normalizzata pro-capite per Ruolo</b> sul numero effettivo di atleti in campo.
            </div>
        </div>
        """
        st.markdown(_clean_html(banner_html), unsafe_allow_html=True)

        with st.container(border=True):
            fir_sessions = _get_existing_fir_gps_sessions()
            mode_opts = ["Inserimento Manuale (Data + Nome Allenamento)"]
            if fir_sessions:
                mode_opts.insert(0, "Collega a una Seduta FIR già presente nel Database GPS")

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

            # Soglie opzionali di filtro giocatori fuori campo / rotazione
            with st.expander("⚙️ Soglie Riconoscimento Automatico Giocatori Attivi (Fuori Campo / Rotazioni)", expanded=False):
                st.caption(
                    "Un atleta viene escluso automaticamente dal calcolo delle medie del drill se registra valori nulli, "
                    "se percorre meno della distanza minima assoluta, se staziona in panchina o se resta sotto la soglia relativa rispetto alla mediana del gruppo."
                )
                s_c1, s_c2, s_c3 = st.columns(3)
                with s_c1:
                    min_dist_m = st.number_input(
                        "Distanza Minima Assoluta (m)",
                        min_value=0.0,
                        max_value=300.0,
                        value=float(drills_manager.DEFAULT_MIN_DIST_M),
                        step=5.0,
                        key="drills_thresh_dist",
                    )
                with s_c2:
                    min_wr_mpm = st.number_input(
                        "Work Rate Minimo Stazionamento (m/min)",
                        min_value=0.0,
                        max_value=50.0,
                        value=float(drills_manager.DEFAULT_MIN_WR_MPM),
                        step=1.0,
                        key="drills_thresh_wr",
                    )
                with s_c3:
                    min_rel_pct = st.number_input(
                        "Soglia Relativa Rotazione (% mediana drill)",
                        min_value=0.0,
                        max_value=60.0,
                        value=float(drills_manager.DEFAULT_MIN_REL_DIST_PCT),
                        step=5.0,
                        key="drills_thresh_rel",
                    )

            if session_date_str and session_name_str:
                existing_cnt = drills_manager.session_exists_in_drills(session_date_str, session_name_str)
                if existing_cnt > 0:
                    st.warning(
                        f"♻️ **Logica Upsert attiva:** esistono già **{existing_cnt} drill(s)** salvati per "
                        f"**{session_date_str} — {session_name_str}**. Al salvataggio i vecchi record di questa seduta "
                        f"verranno ripuliti e sostituiti in modo pulito senza duplicati."
                    )

            uploaded_files = st.file_uploader(
                "Carica i CSV / Excel dei Drills della seduta (singoli file o export GPExe multi-drill)",
                type=["csv", "xlsx", "xls"],
                accept_multiple_files=True,
                key="drills_multi_uploader",
                help="Puoi caricare più file separati (1 per drill) oppure un singolo export GPExe completo: il parser separerà automaticamente i singoli blocchi (type='D') escludendo il riepilogo totale seduta (type='S').",
            )

            if uploaded_files:
                roster_map = _build_roster_role_map()
                existing_drill_names = sorted(df_master["Drill_Name"].dropna().unique().tolist()) if not df_master.empty else []

                parsed_items = []
                parse_errors = []
                multi_notices = []
                detected_dates = set()

                for idx, uf in enumerate(uploaded_files):
                    try:
                        f_bytes = uf.getvalue()
                        drill_tuples, f_meta = drills_manager.parse_drill_file_multi(
                            f_bytes,
                            uf.name,
                            roster_role_map=roster_map,
                            min_dist_m=min_dist_m,
                            min_wr_mpm=min_wr_mpm,
                            min_rel_dist_pct=min_rel_pct,
                        )
                        if f_meta.get("detected_session_date"):
                            detected_dates.add(f_meta["detected_session_date"])

                        if f_meta.get("is_multi_drill"):
                            d_names_str = ", ".join(f"**{n}**" for n in f_meta.get("detected_drill_names", []))
                            skip_msg = ""
                            if f_meta.get("skipped_session_summary"):
                                s_lbl = f_meta.get("skipped_session_label") or "totale seduta"
                                skip_msg = f" (escluso automaticamente il riepilogo `type='S'` **{s_lbl}** per evitare doppi conteggi)"
                            multi_notices.append(
                                f"✂️ Export GPExe multi-drill rilevato in **{uf.name}**: estratti automaticamente **{len(drill_tuples)} drills** ({d_names_str}){skip_msg}."
                            )

                        for sub_idx, (summary_rec, player_recs, role_recs, suggested) in enumerate(drill_tuples):
                            parsed_items.append((idx, sub_idx, uf.name, summary_rec, player_recs, role_recs, suggested))
                    except Exception as exc:
                        parse_errors.append(f"❌ **{uf.name}**: {exc}")

                for note_msg in multi_notices:
                    st.info(note_msg)
                if detected_dates and session_date_str and session_date_str not in detected_dates:
                    dates_joined = ", ".join(sorted(detected_dates))
                    st.caption(
                        f"📅 Nota: nei file caricati risulta la data **{dates_joined}** "
                        f"(verifica che corrisponda alla `Session_Date` selezionata sopra: **{session_date_str}**)."
                    )
                for err in parse_errors:
                    st.error(err)

                if parsed_items:
                    st.markdown(
                        _clean_html(
                            f"""
                            <div style="font-size:0.84rem; font-weight:800; color:{FIR_NAVY};
                                        margin:10px 0 6px 0; padding-bottom:4px;
                                        border-bottom:2px solid {FIR_AZZURO};">
                                🏷️ Assegnazione Dinamica Drill_Name, Sequenza &amp; Verifica Giocatori Attivi ({len(parsed_items)} blocchi rilevati)
                            </div>
                            """
                        ),
                        unsafe_allow_html=True,
                    )

                    configured_drills = []
                    configured_players = []
                    configured_roles = []
                    excluded_preview_rows = []

                    for pos_i, (orig_idx, sub_idx, fname, s_rec, p_recs, r_recs, suggested) in enumerate(parsed_items, start=1):
                        safe_tag = "".join(ch if ch.isalnum() else "_" for ch in f"{fname}_{suggested}")[:36]
                        key_base = f"drill_cfg_{orig_idx}_{sub_idx}_{safe_tag}"
                        c_ord, c_bank, c_name, c_prev = st.columns([0.70, 1.55, 1.85, 3.1])
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
                            lbl_src = suggested[:22] if len(parsed_items) > len(uploaded_files) else fname[:22]
                            d_name = st.text_input(
                                f"Drill_Name ({lbl_src})",
                                value=init_name,
                                key=f"{key_base}_name_{bank_choice}",
                            ).strip()
                        with c_prev:
                            n_act = s_rec["Active_Players_Count"]
                            n_exc = s_rec["Excluded_Players_Count"]
                            exc_badge = (
                                f"<span style='background:#FEF2F2; color:{FIR_CRIMSON}; border:1px solid #FECACA; padding:1px 6px; border-radius:4px; font-weight:800;'>🚫 {n_exc} esclusi</span>"
                                if n_exc > 0
                                else f"<span style='background:#ECFDF5; color:{FIR_EMERALD}; border:1px solid #A7F3D0; padding:1px 6px; border-radius:4px; font-weight:700;'>0 esclusi</span>"
                            )
                            st.markdown(
                                _clean_html(
                                    f"""
                                    <div style="background:{FIR_LIGHT_BG}; border:1px solid #CBD5E1;
                                                border-left:3px solid {FIR_AZZURO}; border-radius:8px;
                                                padding:7px 10px; margin-top:20px; font-size:0.74rem; color:{FIR_NAVY};">
                                        <span style="background:#EFF6FF; color:{FIR_AZZURO}; border:1px solid #BFDBFE; padding:1px 6px; border-radius:4px; font-weight:800;">
                                            ✅ {n_act} attivi
                                        </span> {exc_badge}
                                        · ⏱️ {s_rec['Duration_Min']:.1f}m ·
                                        ⚡ <b style="color:{FIR_AZZURO};">{s_rec['Work_Rate']:.1f} m/min</b><br>
                                        <span style="color:#334155;">
                                            <b>Pro-Capite:</b> {s_rec['Total_Distance']:.0f}m · HMPD {s_rec['HMPD']:.0f}m · HSR {s_rec['HSR']:.0f}m · DSL {s_rec['Dynamic_Stress_Load']:.1f}
                                        </span><br>
                                        <span style="color:#64748B;">
                                            <b>Totale Gruppo:</b> {s_rec['Total_Distance_Sum']:,.0f}m · HMPD {s_rec['HMPD_Sum']:,.0f}m · DSL {s_rec['Dynamic_Stress_Load_Sum']:,.0f}
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
                            if not pr_copy.get("Is_Active", True):
                                excluded_preview_rows.append({
                                    "Drill": final_dname,
                                    "Atleta": pr_copy["Player_Name"],
                                    "Ruolo": pr_copy["Role"],
                                    "Distanza (m)": pr_copy["Total_Distance"],
                                    "Work Rate": pr_copy["Work_Rate"],
                                    "Vmax": pr_copy["Max_Speed"],
                                    "Motivo Esclusione": pr_copy["Exclusion_Reason"],
                                })

                        for rr in r_recs:
                            rr_copy = dict(rr)
                            rr_copy["Drill_Name"] = final_dname
                            rr_copy["Drill_Order"] = int(d_order)
                            configured_roles.append(rr_copy)

                    if excluded_preview_rows:
                        with st.expander(
                            f"🚫 Anteprima Atleti Esclusi Automaticamente (Fuori Campo / Rotazioni): {len(excluded_preview_rows)} tracce",
                            expanded=False,
                        ):
                            st.dataframe(pd.DataFrame(excluded_preview_rows), use_container_width=True, hide_index=True)

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
                            role_records=configured_roles,
                        )
                        st.session_state["drills_last_saved_session"] = (session_date_str, session_name_str)
                        replace_note = f" (ripuliti e sostituiti {removed_n} vecchi record della seduta)" if removed_n > 0 else ""
                        st.session_state["drills_save_feedback"] = (
                            f"✅ Archiviati **{inserted_n} drills** normalizzati su atleti attivi per **{session_date_str} — {session_name_str}** "
                            f"in `drills_master.parquet` + Cloud Storage{replace_note}."
                        )
                        st.rerun()
    else:
        st.info("👁️ Modalità **Visualizzatore**: puoi consultare tutte le analisi comparative dei drills per seduta, normalizzate per ruolo/attivi, e il Drill Bank longitudinale.")

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
            Scegli se visualizzare il <b>Carico Medio Normalizzato per Atleta Attivo</b> oppure il <b>Carico Totale Energetico del Gruppo/Reparto</b>,
            con breakdown dedicato per singolo ruolo.
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

    sess_df = (
        df_master.groupby(["Session_Date", "Session_Name"], as_index=False)
        .agg(
            n_drills=("Drill_Name", "count"),
            tot_dur=("Duration_Min", "sum"),
            avg_act=("Active_Players_Count", "mean"),
        )
        .sort_values(by=["Session_Date", "Session_Name"], ascending=[False, True])
        .reset_index(drop=True)
    )
    session_keys = [(r["Session_Date"], r["Session_Name"]) for _, r in sess_df.iterrows()]
    session_labels = [
        f"{r['Session_Date']}  —  {r['Session_Name']}  ({int(r['n_drills'])} drills · ~{r['avg_act']:.0f} attivi · {r['tot_dur']:.0f} min)"
        for _, r in sess_df.iterrows()
    ]

    default_idx = 0
    last_saved = st.session_state.get("drills_last_saved_session")
    if last_saved and last_saved in session_keys:
        default_idx = session_keys.index(last_saved)

    col_sel_s, col_view_mode, col_del_s = st.columns([2.8, 2.2, 1.1])
    with col_sel_s:
        chosen_s_idx = st.selectbox(
            "Seleziona Seduta Archiviata",
            options=list(range(len(session_labels))),
            index=default_idx,
            format_func=lambda i: session_labels[i],
            key="drills_view_session_selector",
        )
    sel_date, sel_name = session_keys[chosen_s_idx]

    with col_view_mode:
        view_mode_sess = st.radio(
            "Modalità Calcolo Carico",
            options=["👤 Media Normalizzata (Atleti Attivi)", "∑ Carico Totale Gruppo / Reparto"],
            horizontal=True,
            key="drills_sess_view_mode",
        )
    is_total_mode = view_mode_sess.startswith("∑")

    df_sess = df_master[
        (df_master["Session_Date"] == sel_date) & (df_master["Session_Name"] == sel_name)
    ].sort_values(by="Drill_Order", ascending=True).reset_index(drop=True)

    with col_del_s:
        if is_admin:
            st.markdown("<div style='height:27px;'></div>", unsafe_allow_html=True)
            with st.popover("🗑️ Elimina", use_container_width=True):
                st.caption(f"Rimuovi tutti i **{len(df_sess)} drills** di **{sel_date} — {sel_name}**?")
                if st.button("Conferma Eliminazione", type="primary", key="btn_confirm_del_drill_sess"):
                    del_cnt = drills_manager.delete_session_drills(sel_date, sel_name)
                    st.session_state.pop("drills_last_saved_session", None)
                    st.session_state["drills_save_feedback"] = f"🗑️ Eliminati **{del_cnt} drills** della seduta {sel_date} — {sel_name}."
                    st.rerun()

    # 4 Card KPI Seduta (adattate alla modalità Pro-Capite vs Totale Gruppo)
    tot_dur = float(df_sess["Duration_Min"].sum())
    avg_act_p = float(df_sess["Active_Players_Count"].mean())
    tot_exc_p = int(df_sess["Excluded_Players_Count"].sum())

    if is_total_mode:
        dist_kpi = float(df_sess["Total_Distance_Sum"].sum())
        hmpd_kpi = float(df_sess["HMPD_Sum"].sum())
        hsr_kpi = float(df_sess["HSR_Sum"].sum())
        dsl_kpi = float(df_sess["Dynamic_Stress_Load_Sum"].sum())
        imp_kpi = float(df_sess["Heavy_Impacts_Sum"].sum())
        lbl_k2 = "Distanza Totale Gruppo Attivo"
        sub_k2 = f"Media per drill: {df_sess['Total_Distance_Sum'].mean():,.0f} m"
        lbl_k3 = "HMPD & HSR Totali Gruppo"
        sub_k3 = f"🏃 HSR Gruppo: {hsr_kpi:,.0f} m"
        lbl_k4 = "DSL & Impatti Totali Gruppo"
        sub_k4 = f"💥 Heavy Imp. Gruppo: {imp_kpi:,.0f}"
    else:
        dist_kpi = float(df_sess["Total_Distance"].sum())
        avg_wr = round(dist_kpi / tot_dur, 1) if tot_dur > 0 else float(df_sess["Work_Rate"].mean())
        hmpd_kpi = float(df_sess["HMPD"].sum())
        hsr_kpi = float(df_sess["HSR"].sum())
        dsl_kpi = float(df_sess["Dynamic_Stress_Load"].sum())
        peak_vmax = float(df_sess["Max_Speed_Peak"].max()) if df_sess["Max_Speed_Peak"].max() > 0 else float(df_sess["Max_Speed"].max())
        lbl_k2 = "Distanza Pro-Capite & Work Rate"
        sub_k2 = f"⚡ WR Medio Attivi: {avg_wr:.1f} m/min"
        lbl_k3 = "HMPD & HSR Pro-Capite"
        sub_k3 = f"🏃 HSR Pro-Capite: {hsr_kpi:,.0f} m"
        lbl_k4 = "DSL Pro-Capite & Picco Vmax"
        sub_k4 = f"🚀 Vmax Picco: {peak_vmax:.1f} km/h"

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            _render_kpi_card(
                "Drills & Atleti Attivi",
                f"{len(df_sess)} Drills",
                f"✅ ~{avg_act_p:.0f} attivi/drill · 🚫 {tot_exc_p} escl. · ⏱️ {tot_dur:.0f}m",
                FIR_NAVY,
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(_render_kpi_card(lbl_k2, f"{dist_kpi:,.0f} m", sub_k2, FIR_AZZURO), unsafe_allow_html=True)
    with k3:
        st.markdown(_render_kpi_card(lbl_k3, f"{hmpd_kpi:,.0f} m", sub_k3, FIR_ORO), unsafe_allow_html=True)
    with k4:
        st.markdown(_render_kpi_card(lbl_k4, f"{dsl_kpi:,.1f}", sub_k4, FIR_NAVY), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    df_sess["Drill_Label"] = df_sess.apply(
        lambda r: f"#{int(r['Drill_Order'])} {r['Drill_Name']}<br>({int(r['Active_Players_Count'])} att.)", axis=1
    )

    # Grafici a barre affiancati
    col_g1, col_g2 = st.columns(2)
    with col_g1:
        dist_col = "Total_Distance_Sum" if is_total_mode else "Total_Distance"
        dist_title = "Distanza Totale Gruppo (m)" if is_total_mode else "Distanza Media Pro-Capite (m)"
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        fig1.add_trace(
            go.Bar(
                x=df_sess["Drill_Label"],
                y=df_sess[dist_col],
                name=dist_title,
                marker=dict(color=FIR_AZZURO, line=dict(color=FIR_NAVY, width=1)),
                text=[f"{v:,.0f}m" for v in df_sess[dist_col]],
                textposition="outside",
            ),
            secondary_y=False,
        )
        fig1.add_trace(
            go.Scatter(
                x=df_sess["Drill_Label"],
                y=df_sess["Work_Rate"],
                name="Work Rate Attivi (m/min)",
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=9, color=FIR_ORO, line=dict(color=FIR_NAVY, width=1.5)),
                text=[f"{v:.1f}" for v in df_sess["Work_Rate"]],
                textposition="top center",
                textfont=dict(color=FIR_NAVY, size=11),
            ),
            secondary_y=True,
        )
        fig1.update_yaxes(title_text=dist_title, secondary_y=False)
        fig1.update_yaxes(title_text="Work Rate Pro-Capite (m/min)", secondary_y=True, showgrid=False)
        _apply_fir_plotly_layout(
            fig1,
            f"{'Carico Totale Gruppo' if is_total_mode else 'Media Normalizzata Attivi'} vs Work Rate — {sel_name}",
            height=395,
        )
        st.plotly_chart(fig1, use_container_width=True)

    with col_g2:
        has_reparti = (df_sess["Avanti_Active_Count"].sum() > 0) and (df_sess["Trequarti_Active_Count"].sum() > 0)
        chart_modes = [
            "HMPD (m) vs HSR (m)",
            "Dynamic Stress Load vs Heavy Impacts",
            "Max Speed Media vs Picco (km/h)",
            "Accelerazioni vs Decelerazioni",
        ]
        if has_reparti:
            chart_modes.insert(1, "Avanti vs Trequarti (Reparti)")

        g2_mode = st.selectbox("Confronto Secondario Drills", options=chart_modes, key="drills_sess_chart2_mode")

        if g2_mode == "HMPD (m) vs HSR (m)":
            c_hmpd = "HMPD_Sum" if is_total_mode else "HMPD"
            c_hsr = "HSR_Sum" if is_total_mode else "HSR"
            tag_m = "Totale Gruppo" if is_total_mode else "Pro-Capite Attivi"
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_hmpd], name=f"HMPD {tag_m}", marker_color=FIR_NAVY, text=[f"{v:,.0f}" for v in df_sess[c_hmpd]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_hsr], name=f"HSR {tag_m}", marker_color=FIR_ORO, text=[f"{v:,.0f}" for v in df_sess[c_hsr]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, f"HMPD vs HSR ({tag_m})", height=355)
        elif g2_mode == "Avanti vs Trequarti (Reparti)":
            fig2 = go.Figure()
            if is_total_mode:
                fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Avanti_Total_Distance_Sum"], name="Avanti Dist. Totale (m)", marker_color=FIR_AZZURO, text=[f"{v:,.0f}" for v in df_sess["Avanti_Total_Distance_Sum"]], textposition="outside"))
                fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Trequarti_Total_Distance_Sum"], name="Trequarti Dist. Totale (m)", marker_color=FIR_ORO, text=[f"{v:,.0f}" for v in df_sess["Trequarti_Total_Distance_Sum"]], textposition="outside"))
                _apply_fir_plotly_layout(fig2, "Carico Totale per Reparto: Avanti vs Trequarti (m)", height=355)
            else:
                fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Avanti_Work_Rate"], name="Avanti WR Pro-Capite (m/min)", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Avanti_Work_Rate"]], textposition="outside"))
                fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Trequarti_Work_Rate"], name="Trequarti WR Pro-Capite (m/min)", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Trequarti_Work_Rate"]], textposition="outside"))
                _apply_fir_plotly_layout(fig2, "Work Rate Normalizzato per Reparto: Avanti vs Trequarti", height=355)
            fig2.update_layout(barmode="group")
        elif g2_mode == "Dynamic Stress Load vs Heavy Impacts":
            c_dsl = "Dynamic_Stress_Load_Sum" if is_total_mode else "Dynamic_Stress_Load"
            c_imp = "Heavy_Impacts_Sum" if is_total_mode else "Heavy_Impacts"
            tag_m = "Totale Gruppo" if is_total_mode else "Pro-Capite Attivi"
            fig2 = make_subplots(specs=[[{"secondary_y": True}]])
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_dsl], name=f"DSL ({tag_m})", marker_color=FIR_AZZURO, text=[f"{v:,.1f}" for v in df_sess[c_dsl]], textposition="outside"), secondary_y=False)
            fig2.add_trace(go.Scatter(x=df_sess["Drill_Label"], y=df_sess[c_imp], name=f"Heavy Impacts ({tag_m})", mode="lines+markers+text", line=dict(color=FIR_CRIMSON, width=2.5), marker=dict(size=8), text=[f"{v:,.1f}" for v in df_sess[c_imp]], textposition="top center"), secondary_y=True)
            fig2.update_yaxes(title_text=f"DSL ({tag_m})", secondary_y=False)
            fig2.update_yaxes(title_text=f"Heavy Impacts ({tag_m})", secondary_y=True, showgrid=False)
            _apply_fir_plotly_layout(fig2, f"Carico Meccanico — DSL vs Heavy Impacts ({tag_m})", height=355)
        elif g2_mode == "Max Speed Media vs Picco (km/h)":
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed"], name="Max Speed Media Attivi", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Max_Speed"]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed_Peak"], name="Picco Individuale", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Max_Speed_Peak"]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, "Velocità Massima Atleti Attivi (km/h)", height=355)
        else:
            c_acc = "Acc_Events_Sum" if is_total_mode else "Acc_Events"
            c_dec = "Dec_Events_Sum" if is_total_mode else "Dec_Events"
            tag_m = "Totali Gruppo" if is_total_mode else "Pro-Capite"
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_acc], name=f"Acc ({tag_m})", marker_color=FIR_AZZURO, text=[f"{v:,.1f}" for v in df_sess[c_acc]], textposition="outside"))
            fig2.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_dec], name=f"Dec ({tag_m})", marker_color=FIR_NAVY, text=[f"{v:,.1f}" for v in df_sess[c_dec]], textposition="outside"))
            fig2.update_layout(barmode="group")
            _apply_fir_plotly_layout(fig2, f"Eventi Neuromuscolari ({tag_m})", height=355)

        st.plotly_chart(fig2, use_container_width=True)

    # Tabella comparativa della seduta (mostra chiaramente Attivi, Esclusi, Pro-Capite e Totali Gruppo)
    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📋 Tabella Comparativa Drills — {sel_date} · {sel_name} ({'Carico Totale Gruppo' if is_total_mode else 'Media Normalizzata Pro-Capite Attivi'})</div>",
        unsafe_allow_html=True,
    )
    if is_total_mode:
        df_table = df_sess[[
            "Drill_Order", "Drill_Name", "Active_Players_Count", "Excluded_Players_Count", "Duration_Min",
            "Total_Distance_Sum", "HMPD_Sum", "HSR_Sum", "VHSR_Sum",
            "Dynamic_Stress_Load_Sum", "Heavy_Impacts_Sum", "Acc_Events_Sum", "Dec_Events_Sum",
        ]].rename(
            columns={
                "Drill_Order": "Ord.",
                "Drill_Name": "Drill",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Esclusi",
                "Duration_Min": "Durata (m)",
                "Total_Distance_Sum": "Dist. Tot. Gruppo (m)",
                "HMPD_Sum": "HMPD Tot. (m)",
                "HSR_Sum": "HSR Tot. (m)",
                "VHSR_Sum": "VHSR Tot. (m)",
                "Dynamic_Stress_Load_Sum": "DSL Tot. Gruppo",
                "Heavy_Impacts_Sum": "Heavy Imp. Tot.",
                "Acc_Events_Sum": "Acc Tot.",
                "Dec_Events_Sum": "Dec Tot.",
            }
        )
    else:
        df_table = df_sess[[
            "Drill_Order", "Drill_Name", "Active_Players_Count", "Excluded_Players_Count", "Duration_Min",
            "Total_Distance", "Work_Rate", "HMPD", "HMPD_per_Min",
            "HSR", "HSR_per_Min", "Max_Speed", "Max_Speed_Peak",
            "Dynamic_Stress_Load", "Heavy_Impacts", "Acc_Events", "Dec_Events",
        ]].rename(
            columns={
                "Drill_Order": "Ord.",
                "Drill_Name": "Drill",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Esclusi",
                "Duration_Min": "Durata (m)",
                "Total_Distance": "Dist. Pro-Cap. (m)",
                "Work_Rate": "WR (m/m)",
                "HMPD": "HMPD Pro-Cap.",
                "HMPD_per_Min": "HMPD/m",
                "HSR": "HSR Pro-Cap.",
                "HSR_per_Min": "HSR/m",
                "Max_Speed": "Vmax Med.",
                "Max_Speed_Peak": "Vmax Picco",
                "Dynamic_Stress_Load": "DSL Pro-Cap.",
                "Heavy_Impacts": "Heavy Imp.",
                "Acc_Events": "Acc",
                "Dec_Events": "Dec",
            }
        )
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # Sezione Normalizzazione per Ruolo della seduta (o singolo drill della seduta)
    df_roles_sess = pd.DataFrame()
    if df_roles is not None and not df_roles.empty:
        df_roles_sess = df_roles[
            (df_roles["Session_Date"] == sel_date) & (df_roles["Session_Name"] == sel_name)
        ].copy()

    if not df_roles_sess.empty:
        drill_role_opts = ["Intera Seduta (Tutti i Drills)"] + [
            f"#{int(r['Drill_Order'])} {r['Drill_Name']}" for _, r in df_sess.iterrows()
        ]
        sel_r_drill = st.selectbox(
            "Seleziona Drill per Analisi Normalizzata per Ruolo",
            options=drill_role_opts,
            key="drills_sess_role_drill_pick",
        )
        if sel_r_drill != "Intera Seduta (Tutti i Drills)":
            chosen_ord = int(sel_r_drill.split()[0].replace("#", ""))
            df_roles_sub = df_roles_sess[df_roles_sess["Drill_Order"] == chosen_ord]
        else:
            df_roles_sub = df_roles_sess
        _render_role_normalization_block(df_roles_sub, f"{sel_date} · {sel_name} ({sel_r_drill})", key_prefix="sess_role")

    # Export CSV della seduta
    csv_sess = df_sess.drop(columns=["Drill_Label"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Esporta CSV Drills Seduta (Pro-Capite + Totali Gruppo)",
        data=csv_sess,
        file_name=f"FIR_Drills_{sel_date}_{sel_name.replace(' ', '_')}.csv",
        mime="text/csv",
        key="dl_session_drills_csv",
    )

    # Expander Dettaglio Individuale Atleti (Attivi vs Esclusi / Rotazione)
    if df_players is not None and not df_players.empty:
        df_ps = df_players[
            (df_players["Session_Date"] == sel_date) & (df_players["Session_Name"] == sel_name)
        ].copy()
        if not df_ps.empty:
            n_p_act = int(df_ps["Is_Active"].sum())
            n_p_exc = int((~df_ps["Is_Active"]).sum())
            with st.expander(
                f"👥 Dettaglio Individuale Atleti — ✅ {n_p_act} Attivi / 🚫 {n_p_exc} Esclusi (Fuori Campo / Rotazioni)",
                expanded=False,
            ):
                c_pf1, c_pf2 = st.columns([2, 1.5])
                with c_pf1:
                    drill_filter = st.selectbox(
                        "Filtra per Drill",
                        options=["Tutti i Drills"] + df_sess["Drill_Name"].tolist(),
                        key="drills_player_detail_filter",
                    )
                with c_pf2:
                    status_filter = st.radio(
                        "Stato Partecipazione",
                        options=["Tutti", "Solo Attivi", "Solo Esclusi (Fuori Campo)"],
                        horizontal=True,
                        key="drills_player_status_filter",
                    )
                if drill_filter != "Tutti i Drills":
                    df_ps = df_ps[df_ps["Drill_Name"] == drill_filter]
                if status_filter == "Solo Attivi":
                    df_ps = df_ps[df_ps["Is_Active"] == True]
                elif status_filter == "Solo Esclusi (Fuori Campo)":
                    df_ps = df_ps[df_ps["Is_Active"] == False]

                df_ps_disp = df_ps.copy()
                df_ps_disp["Stato"] = np.where(df_ps_disp["Is_Active"], "✅ Attivo", "🚫 Escluso")
                st.dataframe(
                    df_ps_disp[[
                        "Drill_Order", "Drill_Name", "Stato", "Player_Name", "Role", "Department",
                        "Duration_Min", "Total_Distance", "Work_Rate", "HMPD", "HSR",
                        "Max_Speed", "Dynamic_Stress_Load", "Heavy_Impacts", "Exclusion_Reason",
                    ]].sort_values(by=["Drill_Order", "Stato", "Work_Rate"], ascending=[True, True, False]),
                    use_container_width=True,
                    hide_index=True,
                )


def _render_tab_drill_bank(df_master: pd.DataFrame, df_roles: pd.DataFrame):
    banner_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:12px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            🔍 Archivio Globale &amp; Analisi Cross-Session — FIR Drill Bank
        </div>
        <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
            Confronta l'evoluzione nel tempo di uno stesso drill filtrando per <b>Squadra, Reparto o Singolo Ruolo</b>,
            alternando <b>Media Normalizzata pro-capite su Atleti Attivi</b> e <b>Carico Totale del Gruppo/Reparto</b>.
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

    drill_counts = df_master.groupby("Drill_Name").size().sort_values(ascending=False)
    unique_drills = drill_counts.index.tolist()

    # Controlli superiori: Drill + Modalità Calcolo + Ambito/Ruolo
    r1_c1, r1_c2, r1_c3 = st.columns([2.0, 2.0, 1.8])
    with r1_c1:
        selected_drill = st.selectbox(
            "🎯 Seleziona Drill dallo Storico (Drill Bank)",
            options=unique_drills,
            format_func=lambda d: f"{d}  ({int(drill_counts[d])} esecuzioni)",
            key="drill_bank_select_drill",
        )
    with r1_c2:
        bank_view_mode = st.radio(
            "Modalità Visualizzazione Carico",
            options=["👤 Media Normalizzata Pro-Capite (Attivi)", "∑ Carico Totale Gruppo / Reparto"],
            horizontal=True,
            key="drill_bank_view_mode",
        )
    is_total_mode = bank_view_mode.startswith("∑")

    # Ruoli disponibili per quel drill nello storico
    df_roles_drill = pd.DataFrame()
    if df_roles is not None and not df_roles.empty:
        df_roles_drill = df_roles[df_roles["Drill_Name"] == selected_drill].copy()

    scope_options = ["Intera Squadra (Attivi)"]
    if not df_roles_drill.empty:
        depts_present = [d for d in ("Avanti", "Trequarti") if (df_roles_drill["Department"] == d).any()]
        for d in depts_present:
            scope_options.append(f"Reparto: {d}")
        order_map = {r: i for i, r in enumerate(drills_manager.CANONICAL_ROLE_ORDER)}
        roles_present = sorted(df_roles_drill["Role"].unique().tolist(), key=lambda x: (order_map.get(x, 99), x))
        for r in roles_present:
            scope_options.append(f"Ruolo: {r}")

    with r1_c3:
        selected_scope = st.selectbox(
            "Ambito / Normalizzazione Ruolo",
            options=scope_options,
            key="drill_bank_scope_selector",
        )

    # Costruisce DataFrame longitudinale coerente per lo scope selezionato
    if selected_scope == "Intera Squadra (Attivi)" or df_roles_drill.empty:
        df_d = df_master[df_master["Drill_Name"] == selected_drill].sort_values(
            by=["Session_Date", "Drill_Order"], ascending=[True, True]
        ).reset_index(drop=True)
    elif selected_scope.startswith("Reparto: "):
        target_dept = selected_scope.replace("Reparto: ", "")
        sub_r = df_roles_drill[df_roles_drill["Department"] == target_dept]
        df_d = (
            sub_r.groupby(["Session_Date", "Session_Name", "Drill_Name", "Drill_Order"], as_index=False)
            .agg(
                Active_Players_Count=("Active_Players_Count", "sum"),
                Excluded_Players_Count=("Excluded_Players_Count", "sum"),
                Duration_Min=("Duration_Min", "mean"),
                Total_Distance_Sum=("Total_Distance_Sum", "sum"),
                HMPD_Sum=("HMPD_Sum", "sum"),
                HSR_Sum=("HSR_Sum", "sum"),
                VHSR_Sum=("VHSR_Sum", "sum"),
                Dynamic_Stress_Load_Sum=("Dynamic_Stress_Load_Sum", "sum"),
                Heavy_Impacts_Sum=("Heavy_Impacts_Sum", "sum"),
                Acc_Events_Sum=("Acc_Events_Sum", "sum"),
                Dec_Events_Sum=("Dec_Events_Sum", "sum"),
                Max_Speed=("Max_Speed", "mean"),
                Max_Speed_Peak=("Max_Speed_Peak", "max"),
                Avg_MP=("Avg_MP", "mean"),
            )
            .sort_values(by=["Session_Date", "Drill_Order"], ascending=[True, True])
            .reset_index(drop=True)
        )
        den = df_d["Active_Players_Count"].replace(0, np.nan)
        df_d["Total_Distance"] = (df_d["Total_Distance_Sum"] / den).fillna(0.0).round(2)
        df_d["Work_Rate"] = np.where(df_d["Duration_Min"] > 0, df_d["Total_Distance"] / df_d["Duration_Min"], 0.0).round(2)
        df_d["HMPD"] = (df_d["HMPD_Sum"] / den).fillna(0.0).round(2)
        df_d["HMPD_per_Min"] = np.where(df_d["Duration_Min"] > 0, df_d["HMPD"] / df_d["Duration_Min"], 0.0).round(2)
        df_d["HSR"] = (df_d["HSR_Sum"] / den).fillna(0.0).round(2)
        df_d["HSR_per_Min"] = np.where(df_d["Duration_Min"] > 0, df_d["HSR"] / df_d["Duration_Min"], 0.0).round(2)
        df_d["VHSR"] = (df_d["VHSR_Sum"] / den).fillna(0.0).round(2)
        df_d["Dynamic_Stress_Load"] = (df_d["Dynamic_Stress_Load_Sum"] / den).fillna(0.0).round(2)
        df_d["Heavy_Impacts"] = (df_d["Heavy_Impacts_Sum"] / den).fillna(0.0).round(2)
        df_d["Acc_Events"] = (df_d["Acc_Events_Sum"] / den).fillna(0.0).round(2)
        df_d["Dec_Events"] = (df_d["Dec_Events_Sum"] / den).fillna(0.0).round(2)
    else:
        target_role = selected_scope.replace("Ruolo: ", "")
        df_d = df_roles_drill[df_roles_drill["Role"] == target_role].sort_values(
            by=["Session_Date", "Drill_Order"], ascending=[True, True]
        ).reset_index(drop=True)

    if df_d.empty:
        st.info(f"Nessuna esecuzione trovata per **{selected_drill}** nello scope **{selected_scope}**.")
        return

    # Selettori metriche coerenti con modalità (Media Pro-Capite vs Totale Gruppo)
    metric_dict = METRIC_LABELS_TOTAL if is_total_mode else METRIC_LABELS_AVG
    m_keys = list(metric_dict.keys())
    c_m1, c_m2 = st.columns(2)
    with c_m1:
        primary_metric = st.selectbox(
            "Metrica Primaria (Barre)",
            options=m_keys,
            index=0,
            format_func=lambda k: metric_dict[k],
            key=f"drill_bank_primary_{is_total_mode}",
        )
    with c_m2:
        sec_options = ["Nessuna"] + m_keys
        default_sec = "Dynamic_Stress_Load_Sum" if is_total_mode else "Dynamic_Stress_Load"
        def_sec_idx = sec_options.index(default_sec) if default_sec in sec_options else 0
        secondary_metric = st.selectbox(
            "Metrica Secondaria (Linea)",
            options=sec_options,
            index=def_sec_idx,
            format_func=lambda k: "— Nessuna —" if k == "Nessuna" else metric_dict[k],
            key=f"drill_bank_secondary_{is_total_mode}",
        )

    # 5 Card KPI Longitudinali
    n_exec = len(df_d)
    avg_act_hist = float(df_d["Active_Players_Count"].mean())
    p_series = pd.to_numeric(df_d[primary_metric], errors="coerce").fillna(0.0)
    p_mean_val = float(p_series.mean())
    p_last_val = float(p_series.iloc[-1])
    delta_p_pct = ((p_last_val - p_mean_val) / p_mean_val * 100.0) if p_mean_val > 0 else 0.0
    delta_sign = "+" if delta_p_pct >= 0 else ""

    hmpd_col = "HMPD_Sum" if is_total_mode else "HMPD"
    hsr_col = "HSR_Sum" if is_total_mode else "HSR"
    dsl_col = "Dynamic_Stress_Load_Sum" if is_total_mode else "Dynamic_Stress_Load"
    imp_col = "Heavy_Impacts_Sum" if is_total_mode else "Heavy_Impacts"

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(
            _render_kpi_card("Esecuzioni & Attivi", f"{n_exec} sed.", f"✅ ~{avg_act_hist:.1f} attivi/esec. ({selected_scope})", FIR_NAVY),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            _render_kpi_card(
                metric_dict[primary_metric][:26],
                f"{p_mean_val:,.1f}",
                f"Ultima: {p_last_val:,.1f} ({delta_sign}{delta_p_pct:.1f}%)",
                FIR_AZZURO,
            ),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            _render_kpi_card("HMPD Medio" + (" (Tot.)" if is_total_mode else " (Pro-Cap.)"), f"{df_d[hmpd_col].mean():,.0f} m", f"Range: {df_d[hmpd_col].min():,.0f}–{df_d[hmpd_col].max():,.0f}", FIR_ORO),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            _render_kpi_card("HSR Medio" + (" (Tot.)" if is_total_mode else " (Pro-Cap.)"), f"{df_d[hsr_col].mean():,.0f} m", f"Vmax picco: {df_d['Max_Speed_Peak'].max():.1f} km/h", FIR_AZZURO),
            unsafe_allow_html=True,
        )
    with k5:
        st.markdown(
            _render_kpi_card("DSL Medio" + (" (Tot.)" if is_total_mode else " (Pro-Cap.)"), f"{df_d[dsl_col].mean():,.1f}", f"Heavy Imp.: {df_d[imp_col].mean():,.1f}", FIR_NAVY),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    df_d["Exec_Label"] = df_d.apply(
        lambda r: f"{r['Session_Date']}<br>{r['Session_Name']}<br>({int(r['Active_Players_Count'])} att.)", axis=1
    )

    # Grafico Longitudinale Principale
    fig_long = make_subplots(specs=[[{"secondary_y": True}]])
    fig_long.add_trace(
        go.Bar(
            x=df_d["Exec_Label"],
            y=p_series,
            name=metric_dict[primary_metric],
            marker=dict(color=FIR_AZZURO, line=dict(color=FIR_NAVY, width=1)),
            text=[f"{v:,.1f}" for v in p_series],
            textposition="outside",
        ),
        secondary_y=False,
    )
    fig_long.add_hline(
        y=p_mean_val,
        line_dash="dash",
        line_color=FIR_NAVY,
        line_width=2,
        annotation_text=f"Media storica: {p_mean_val:,.1f}",
        annotation_position="top left",
        secondary_y=False,
    )

    if secondary_metric != "Nessuna" and secondary_metric != primary_metric:
        s_vals = pd.to_numeric(df_d[secondary_metric], errors="coerce").fillna(0.0)
        fig_long.add_trace(
            go.Scatter(
                x=df_d["Exec_Label"],
                y=s_vals,
                name=metric_dict[secondary_metric],
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=9, color=FIR_ORO, line=dict(color=FIR_NAVY, width=1.5)),
                text=[f"{v:,.1f}" for v in s_vals],
                textposition="top center",
            ),
            secondary_y=True,
        )
        fig_long.update_yaxes(title_text=metric_dict[secondary_metric], secondary_y=True, showgrid=False)

    fig_long.update_yaxes(title_text=metric_dict[primary_metric], secondary_y=False)
    _apply_fir_plotly_layout(
        fig_long,
        f"Evoluzione Longitudinale: {selected_drill} — {selected_scope} ({'Totale Gruppo' if is_total_mode else 'Pro-Capite Attivi'})",
        height=420,
    )
    st.plotly_chart(fig_long, use_container_width=True)

    # Trend Alta Intensità (HMPD & HSR)
    fig_hi = go.Figure()
    fig_hi.add_trace(
        go.Scatter(
            x=df_d["Exec_Label"],
            y=df_d[hmpd_col],
            name=f"HMPD ({'Totale' if is_total_mode else 'Pro-Capite'})",
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
            y=df_d[hsr_col],
            name=f"HSR ({'Totale' if is_total_mode else 'Pro-Capite'})",
            mode="lines+markers",
            line=dict(color=FIR_ORO, width=3),
            marker=dict(size=8, color=FIR_ORO),
        )
    )
    _apply_fir_plotly_layout(
        fig_hi,
        f"Trend Alta Intensità (HMPD & HSR) — {selected_drill} ({selected_scope})",
        height=330,
    )
    st.plotly_chart(fig_hi, use_container_width=True)

    # Tabella Storica Occorrenze (mostra Attivi, Esclusi, Pro-Capite, Totale e Delta %)
    df_hist_view = df_d.copy()
    mean_wr_h = float(df_hist_view["Work_Rate"].mean())
    df_hist_view["Delta_Primary_%"] = np.where(p_mean_val > 0, ((p_series - p_mean_val) / p_mean_val) * 100.0, 0.0).round(1)
    df_hist_view["Delta_WR_%"] = np.where(mean_wr_h > 0, ((df_hist_view["Work_Rate"] - mean_wr_h) / mean_wr_h) * 100.0, 0.0).round(1)

    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📑 Storico Esecuzioni Cross-Session: {selected_drill} ({selected_scope})</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        df_hist_view[[
            "Session_Date", "Session_Name", "Drill_Order", "Active_Players_Count", "Excluded_Players_Count",
            "Duration_Min", "Total_Distance", "Total_Distance_Sum", "Work_Rate", "Delta_WR_%",
            "HMPD", "HMPD_Sum", "HSR", "Dynamic_Stress_Load", "Dynamic_Stress_Load_Sum", "Heavy_Impacts",
        ]].rename(
            columns={
                "Session_Date": "Data",
                "Session_Name": "Allenamento",
                "Drill_Order": "Ord.",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Escl.",
                "Duration_Min": "Dur. (m)",
                "Total_Distance": "Dist. Pro-Cap.",
                "Total_Distance_Sum": "Dist. Totale",
                "Work_Rate": "WR Pro-Cap.",
                "Delta_WR_%": "Δ WR %",
                "HMPD": "HMPD Pro-Cap.",
                "HMPD_Sum": "HMPD Totale",
                "HSR": "HSR Pro-Cap.",
                "Dynamic_Stress_Load": "DSL Pro-Cap.",
                "Dynamic_Stress_Load_Sum": "DSL Totale",
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

    # Normalizzazione Storica per Ruolo del Drill selezionato
    if not df_roles_drill.empty:
        _render_role_normalization_block(
            df_roles_drill,
            f"Storico Cross-Session '{selected_drill}' ({n_exec} esecuzioni)",
            key_prefix="bank_role",
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
            Attivi_Medi=("Active_Players_Count", "mean"),
            Durata_Media=("Duration_Min", "mean"),
            Dist_ProCapite=("Total_Distance", "mean"),
            Dist_Totale_Gruppo=("Total_Distance_Sum", "mean"),
            Work_Rate_Medio=("Work_Rate", "mean"),
            HMPD_ProCapite=("HMPD", "mean"),
            HMPD_Totale_Gruppo=("HMPD_Sum", "mean"),
            HSR_ProCapite=("HSR", "mean"),
            DSL_ProCapite=("Dynamic_Stress_Load", "mean"),
            DSL_Totale_Gruppo=("Dynamic_Stress_Load_Sum", "mean"),
            Heavy_Imp_ProCapite=("Heavy_Impacts", "mean"),
        )
        .sort_values(by="Work_Rate_Medio", ascending=False)
        .reset_index(drop=True)
    )
    for num_c in [
        "Attivi_Medi", "Durata_Media", "Dist_ProCapite", "Dist_Totale_Gruppo",
        "Work_Rate_Medio", "HMPD_ProCapite", "HMPD_Totale_Gruppo",
        "HSR_ProCapite", "DSL_ProCapite", "DSL_Totale_Gruppo", "Heavy_Imp_ProCapite",
    ]:
        bank_summary[num_c] = bank_summary[num_c].round(1)

    if len(unique_drills) >= 2:
        c_ms, c_cm = st.columns([3, 1.8])
        with c_ms:
            compare_drills = st.multiselect(
                "Seleziona Drills da Confrontare",
                options=unique_drills,
                default=unique_drills[: min(6, len(unique_drills))],
                key="drill_bank_compare_multi",
            )
        with c_cm:
            comp_metric_map = (
                {
                    "Dist_Totale_Gruppo": "Distanza Totale Media Gruppo (m)",
                    "HMPD_Totale_Gruppo": "HMPD Totale Medio Gruppo (m)",
                    "DSL_Totale_Gruppo": "DSL Totale Medio Gruppo",
                    "Work_Rate_Medio": "Work Rate Pro-Capite (m/min)",
                }
                if is_total_mode
                else {
                    "Work_Rate_Medio": "Work Rate Pro-Capite (m/min)",
                    "Dist_ProCapite": "Distanza Pro-Capite (m)",
                    "HMPD_ProCapite": "HMPD Pro-Capite (m)",
                    "HSR_ProCapite": "HSR Pro-Capite (m)",
                    "DSL_ProCapite": "DSL Pro-Capite",
                    "Heavy_Imp_ProCapite": "Heavy Impacts Pro-Capite",
                }
            )
            comp_m = st.selectbox(
                "Parametro Confronto",
                options=list(comp_metric_map.keys()),
                format_func=lambda k: comp_metric_map[k],
                key=f"drill_bank_compare_metric_{is_total_mode}",
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
                    text=[f"{v:,.1f}" for v in df_cmp[comp_m]],
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
                "Attivi_Medi": "Attivi Med.",
                "Durata_Media": "Dur. (m)",
                "Dist_ProCapite": "Dist. Pro-Cap.",
                "Dist_Totale_Gruppo": "Dist. Tot. Grp",
                "Work_Rate_Medio": "WR Pro-Cap.",
                "HMPD_ProCapite": "HMPD Pro-Cap.",
                "HMPD_Totale_Gruppo": "HMPD Tot. Grp",
                "HSR_ProCapite": "HSR Pro-Cap.",
                "DSL_ProCapite": "DSL Pro-Cap.",
                "DSL_Totale_Gruppo": "DSL Tot. Grp",
                "Heavy_Imp_ProCapite": "Imp. Pro-Cap.",
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
        "Filtro automatico giocatori attivi (rotazioni/fuori campo), normalizzazione dinamica per ruolo e Drill Bank longitudinale FIR",
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
    df_roles = drills_manager.load_drills_roles_summary()
    df_players = drills_manager.load_drills_players_detail()

    if active_tab == "gestione_sessione":
        _render_tab_sessione(df_master, df_roles, df_players, is_admin=is_admin)
    else:
        _render_tab_drill_bank(df_master, df_roles)
