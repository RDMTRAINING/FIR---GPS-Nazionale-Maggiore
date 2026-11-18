# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo "🧩 Analisi & Confronto Drills" — FIR GPS Analytics Platform.
Funzionalità principali:
  - Caricamento multiplo CSV/Excel o singolo export GPExe multi-drill (auto-splitting type='D', esclusione type='S')
  - Riconoscimento automatico giocatori attivi (esclusione panchina/rotazioni/valori nulli)
  - Metodologia FIR rigorosa: Hml (>25.5W), HSR differenziato (>18 km/h Avanti / >20 km/h Trequarti),
    normalizzazione volumetrica per ruolo (Somma Ruolo / N° Giocatori Attivi del Ruolo)
  - Analisi approfondita Drill vs Drill con integrazione completa del Tempo (Durata, % Tempo, m/min, Hml/min, HSR/min)
  - Drill Bank longitudinale & Arena Confronto Multi-Drill (Radar 6 assi, Mappa Durata×Intensità, Benchmark Δ%)
  - Esportazione PDF istituzionale FIR completa e fedele alla pagina della webapp.
"""

import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config import render_page_header, render_tab_navigation
import drills_manager
import drills_pdf
import utils

# Palette Istituzionale FIR
FIR_AZZURO = "#0066B2"
FIR_ORO = "#D4AF37"
FIR_NAVY = "#031926"
FIR_SLATE = "#475569"
FIR_LIGHT_BG = "#F8FAFC"
FIR_EMERALD = "#10B981"
FIR_CRIMSON = "#DC2626"

DRILL_PALETTE = [
    "#0066B2",  # Azzurro FIR
    "#D4AF37",  # Oro FIR
    "#031926",  # Dark Navy FIR
    "#0EA5E9",  # Sky
    "#10B981",  # Emerald
    "#EA580C",  # Orange
    "#7C3AED",  # Violet
    "#DC2626",  # Crimson
]

METRIC_LABELS_AVG: Dict[str, str] = {
    "Work_Rate": "Work Rate Pro-Capite (m/min)",
    "Total_Distance": "Distanza Media Pro-Capite (m)",
    "HMPD": "Hml Medio Pro-Capite (m)",
    "HMPD_per_Min": "Hml/min Pro-Capite (m/min)",
    "HSR": "HSR Pro-Capite (>18 Av / >20 Tq) (m)",
    "HSR_per_Min": "HSR/min Pro-Capite (m/min)",
    "VHSR": "VHSR >25 km/h Pro-Capite (m)",
    "Duration_Min": "Durata Media (min)",
    "Max_Speed": "Max Speed Media Attivi (km/h)",
    "Max_Speed_Peak": "Picco Max Speed (km/h)",
    "Acc_Events": "Accelerazioni Pro-Capite (n)",
    "Dec_Events": "Decelerazioni Pro-Capite (n)",
    "Avg_MP": "Avg Metabolic Power (W/kg)",
}

METRIC_LABELS_TOTAL: Dict[str, str] = {
    "Total_Distance_Sum": "Distanza Totale Gruppo/Ruolo (m)",
    "HMPD_Sum": "Hml Totale Gruppo/Ruolo (m)",
    "HSR_Sum": "HSR Totale (>18 Av / >20 Tq) (m)",
    "VHSR_Sum": "VHSR Totale Gruppo/Ruolo (m)",
    "Acc_Events_Sum": "Accelerazioni Totali Gruppo/Ruolo (n)",
    "Dec_Events_Sum": "Decelerazioni Totali Gruppo/Ruolo (n)",
    "Duration_Min": "Durata Blocco (min)",
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


def _fmt_mmss(minutes: float) -> str:
    try:
        tot_sec = max(0, int(round(float(minutes) * 60.0)))
        m, s = divmod(tot_sec, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(text or "")).strip("_") or "export"


def _render_kpi_card(label: str, value: str, subtext: str = "", accent: str = FIR_AZZURO) -> str:
    return _clean_html(
        f"""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid {accent};
                    border-radius:12px; padding:13px 15px; box-shadow:0 2px 8px rgba(3,25,38,0.06);">
            <div style="font-size:0.68rem; font-weight:800; text-transform:uppercase;
                        letter-spacing:0.06em; color:#64748B;">{label}</div>
            <div style="font-size:1.35rem; font-weight:900; color:{FIR_NAVY}; margin-top:4px; line-height:1.15;">
                {value}
            </div>
            <div style="font-size:0.72rem; color:#475569; margin-top:4px; font-weight:600;">
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


def _apply_fir_plotly_layout(fig: go.Figure, title: str, height: int = 395) -> go.Figure:
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>",
            font=dict(size=13, color=FIR_NAVY),
            x=0.01,
            xanchor="left",
            y=0.97,
            yanchor="top",
        ),
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8FAFC",
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color=FIR_NAVY, size=11),
        margin=dict(l=56, r=56, t=78, b=52),
        legend=dict(
            orientation="h",
            traceorder="normal",
            yanchor="bottom",
            y=1.01,
            xanchor="center",
            x=0.5,
            font=dict(size=10.5, color=FIR_NAVY),
            bgcolor="rgba(255,255,255,0.90)",
        ),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1", automargin=True, tickfont=dict(color=FIR_NAVY, size=10.5))
    fig.update_yaxes(gridcolor="#E2E8F0", linecolor="#CBD5E1", automargin=True, tickfont=dict(color=FIR_SLATE, size=10.5))
    return fig


def _get_scope_options(df_roles_subset: pd.DataFrame) -> List[str]:
    """Costruisce elenco opzioni Ambito (Intera Squadra, Reparto Avanti/Trequarti, singoli Ruoli presenti)."""
    opts = ["Intera Squadra (Attivi)"]
    if df_roles_subset is None or df_roles_subset.empty:
        return opts
    for dept in ("Avanti", "Trequarti"):
        if (df_roles_subset["Department"] == dept).any():
            opts.append(f"Reparto: {dept}")
    order_map = {r: i for i, r in enumerate(drills_manager.CANONICAL_ROLE_ORDER)}
    roles_present = sorted(
        df_roles_subset["Role"].dropna().unique().tolist(),
        key=lambda x: (order_map.get(x, 99), x),
    )
    for role_name in roles_present:
        opts.append(f"Ruolo: {role_name}")
    return opts


def _build_scoped_drills_df(
    df_master_subset: pd.DataFrame,
    df_roles_subset: pd.DataFrame,
    selected_scope: str,
) -> pd.DataFrame:
    """
    Restituisce un DataFrame 1-riga-per-drill calcolato rigorosamente per lo scope selezionato:
      - Intera Squadra (Attivi): direttamente da `df_master_subset`
      - Reparto / Singolo Ruolo: somma volumetrica degli atleti attivi di quel ruolo/reparto
        divisa per il numero effettivo di atleti attivi di quel ruolo/reparto in ciascun drill!
    """
    if selected_scope == "Intera Squadra (Attivi)" or df_roles_subset is None or df_roles_subset.empty:
        out = df_master_subset.copy()
        if not out.empty and "DSL_per_Min" not in out.columns:
            dur_s = pd.to_numeric(out["Duration_Min"], errors="coerce").replace(0, np.nan)
            out["DSL_per_Min"] = (pd.to_numeric(out["Dynamic_Stress_Load"], errors="coerce").fillna(0.0) / dur_s).fillna(0.0).round(2)
        return out

    if selected_scope.startswith("Reparto: "):
        target_dept = selected_scope.replace("Reparto: ", "")
        sub_r = df_roles_subset[df_roles_subset["Department"] == target_dept].copy()
    elif selected_scope.startswith("Ruolo: "):
        target_role = selected_scope.replace("Ruolo: ", "")
        sub_r = df_roles_subset[df_roles_subset["Role"] == target_role].copy()
    else:
        return df_master_subset.copy()

    if sub_r.empty:
        return pd.DataFrame(columns=df_master_subset.columns)

    if "Duration_Min_Sum" not in sub_r.columns:
        sub_r["Duration_Min_Sum"] = (
            pd.to_numeric(sub_r["Duration_Min"], errors="coerce").fillna(0.0)
            * pd.to_numeric(sub_r["Active_Players_Count"], errors="coerce").fillna(1.0)
        )

    agg = (
        sub_r.groupby(["Session_Date", "Session_Name", "Drill_Name", "Drill_Order"], as_index=False)
        .agg(
            Active_Players_Count=("Active_Players_Count", "sum"),
            Excluded_Players_Count=("Excluded_Players_Count", "sum"),
            Duration_Min_Sum=("Duration_Min_Sum", "sum"),
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
        .reset_index(drop=True)
    )

    n_den = agg["Active_Players_Count"].replace(0, np.nan)
    dur_den = agg["Duration_Min_Sum"].replace(0, np.nan)

    # Normalizzazione volumetrica rigorosa: Somma Ruolo / Numero Giocatori Attivi di quel Ruolo
    agg["Duration_Min"] = (agg["Duration_Min_Sum"] / n_den).fillna(0.0).round(2)
    agg["Total_Distance"] = (agg["Total_Distance_Sum"] / n_den).fillna(0.0).round(2)
    agg["HMPD"] = (agg["HMPD_Sum"] / n_den).fillna(0.0).round(2)
    agg["HSR"] = (agg["HSR_Sum"] / n_den).fillna(0.0).round(2)
    agg["VHSR"] = (agg["VHSR_Sum"] / n_den).fillna(0.0).round(2)
    agg["Dynamic_Stress_Load"] = (agg["Dynamic_Stress_Load_Sum"] / n_den).fillna(0.0).round(2)
    agg["Heavy_Impacts"] = (agg["Heavy_Impacts_Sum"] / n_den).fillna(0.0).round(2)
    agg["Acc_Events"] = (agg["Acc_Events_Sum"] / n_den).fillna(0.0).round(2)
    agg["Dec_Events"] = (agg["Dec_Events_Sum"] / n_den).fillna(0.0).round(2)

    # Intensità relative al tempo rigorose: Somma Volumetrica / Somma Durata Attiva
    agg["Work_Rate"] = (agg["Total_Distance_Sum"] / dur_den).fillna(0.0).round(2)
    agg["HMPD_per_Min"] = (agg["HMPD_Sum"] / dur_den).fillna(0.0).round(2)
    agg["HSR_per_Min"] = (agg["HSR_Sum"] / dur_den).fillna(0.0).round(2)
    agg["DSL_per_Min"] = (agg["Dynamic_Stress_Load_Sum"] / dur_den).fillna(0.0).round(2)
    agg["Max_Speed"] = agg["Max_Speed"].round(2)
    agg["Max_Speed_Peak"] = agg["Max_Speed_Peak"].round(2)
    agg["Avg_MP"] = agg["Avg_MP"].round(2)

    # Porta eventuali colonne reparto da df_master se necessarie per il grafico Avanti vs Trequarti
    if not df_master_subset.empty:
        extra_cols = [
            "Avanti_Active_Count", "Trequarti_Active_Count",
            "Avanti_Work_Rate", "Trequarti_Work_Rate",
            "Avanti_Total_Distance", "Trequarti_Total_Distance",
            "Avanti_Total_Distance_Sum", "Trequarti_Total_Distance_Sum",
            "Avanti_HMPD", "Trequarti_HMPD", "Avanti_HSR", "Trequarti_HSR",
        ]
        avail_extra = [c for c in extra_cols if c in df_master_subset.columns]
        if avail_extra:
            agg = agg.merge(
                df_master_subset[["Session_Date", "Session_Name", "Drill_Name", "Drill_Order"] + avail_extra],
                on=["Session_Date", "Session_Name", "Drill_Name", "Drill_Order"],
                how="left",
            )
    return agg


def _build_compact_role_summary(df_roles_sess: pd.DataFrame) -> pd.DataFrame:
    """Tabella compatta opzionale per ruolo (Σ Ruolo / N° Giocatori Attivi del Ruolo)."""
    if df_roles_sess is None or df_roles_sess.empty:
        return pd.DataFrame()
    df_r = df_roles_sess.copy()
    if "Duration_Min_Sum" not in df_r.columns:
        df_r["Duration_Min_Sum"] = df_r["Duration_Min"] * df_r["Active_Players_Count"]

    agg = (
        df_r.groupby(["Role", "Department"], as_index=False)
        .agg(
            Esecuzioni=("Drill_Order", "count"),
            Attivi_Totali=("Active_Players_Count", "sum"),
            Attivi_Medi=("Active_Players_Count", "mean"),
            Esclusi_Totali=("Excluded_Players_Count", "sum"),
            Duration_Min_Sum=("Duration_Min_Sum", "sum"),
            Total_Distance_Sum=("Total_Distance_Sum", "sum"),
            HMPD_Sum=("HMPD_Sum", "sum"),
            HSR_Sum=("HSR_Sum", "sum"),
            Dynamic_Stress_Load_Sum=("Dynamic_Stress_Load_Sum", "sum"),
            Max_Speed=("Max_Speed", "mean"),
        )
    )
    den = agg["Attivi_Totali"].replace(0, np.nan)
    dur_den = agg["Duration_Min_Sum"].replace(0, np.nan)
    agg["Total_Distance"] = (agg["Total_Distance_Sum"] / den).fillna(0.0).round(1)
    agg["HMPD"] = (agg["HMPD_Sum"] / den).fillna(0.0).round(1)
    agg["HSR"] = (agg["HSR_Sum"] / den).fillna(0.0).round(1)
    agg["Dynamic_Stress_Load"] = (agg["Dynamic_Stress_Load_Sum"] / den).fillna(0.0).round(1)
    agg["Work_Rate"] = (agg["Total_Distance_Sum"] / dur_den).fillna(0.0).round(1)
    agg["Max_Speed"] = agg["Max_Speed"].round(1)
    agg["Attivi_Medi"] = agg["Attivi_Medi"].round(1)

    order_map = {r: i for i, r in enumerate(drills_manager.CANONICAL_ROLE_ORDER)}
    agg["_ord"] = agg["Role"].map(lambda x: order_map.get(x, 99))
    return agg.sort_values(by=["_ord", "Role"]).drop(columns=["_ord"]).reset_index(drop=True)


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
                📤 Caricamento &amp; Associazione Drills di Seduta (GPExe Multi-Drill &amp; CSV Singoli)
            </div>
            <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
                Metodologia FIR attiva: <b>Hml (&gt;25.5W)</b> · <b>HSR differenziato (&gt;18 km/h Avanti / &gt;20 km/h Trequarti)</b> ·
                normalizzazione volumetrica automatica <b>Σ Ruolo / N° Giocatori Attivi del Ruolo</b> (esclusi panchina e rotazioni).
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
                                        · ⏱️ {s_rec['Duration_Min']:.1f}' ({_fmt_mmss(s_rec['Duration_Min'])}) ·
                                        ⚡ <b style="color:{FIR_AZZURO};">{s_rec['Work_Rate']:.1f} m/min</b><br>
                                        <span style="color:#334155;">
                                            <b>Pro-Capite:</b> {s_rec['Total_Distance']:.0f}m · Hml {s_rec['HMPD']:.0f}m ({s_rec['HMPD_per_Min']:.1f}/m) · HSR {s_rec['HSR']:.0f}m · Vmax {s_rec['Max_Speed']:.1f} km/h
                                        </span><br>
                                        <span style="color:#64748B;">
                                            <b>Totale Gruppo:</b> {s_rec['Total_Distance_Sum']:,.0f}m · Hml {s_rec['HMPD_Sum']:,.0f}m · HSR {s_rec['HSR_Sum']:,.0f}m
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
                            f"✅ Archiviati **{inserted_n} drills** per **{session_date_str} — {session_name_str}** "
                            f"con HSR differenziato FIR (>18 Av / >20 Tq) e normalizzazione per ruolo in `drills_master.parquet` + Cloud Storage{replace_note}."
                        )
                        st.rerun()
    else:
        st.info("👁️ Modalità **Visualizzatore**: puoi consultare tutte le analisi comparative tra drills (con filtro per squadra/reparto/ruolo), il Drill Bank longitudinale ed esportare i report PDF.")

    if st.session_state.get("drills_save_feedback"):
        st.success(st.session_state.pop("drills_save_feedback"))

    # =========================================================================
    # SEZIONE B — ANALISI & CONFRONTO TRA I DRILLS DELLA SEDUTA
    # =========================================================================
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
    sec_b_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_AZZURO} 0%, #004B87 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:11px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            📊 Analisi &amp; Confronto Diretto tra i Drills della Seduta
        </div>
        <div style="font-size:0.78rem; color:#E0F2FE; margin-top:2px;">
            Confronta volume, <b>durata/tempo effettivo</b> e densità al minuto (<b>Work Rate, Hml/min, HSR/min</b>)
            tra i blocchi della seduta. Filtra per <b>Squadra, Reparto o Singolo Ruolo</b> (calcolo rigoroso: <b>Σ Ruolo / N° Attivi del Ruolo</b> · HSR &gt;18 km/h Avanti / &gt;20 km/h Trequarti).
        </div>
    </div>
    """
    st.markdown(_clean_html(sec_b_html), unsafe_allow_html=True)

    if df_master.empty:
        st.info(
            "📭 Nessun drill ancora archiviato in `drills_master.parquet`. "
            "Carica uno o più CSV dei drills nella sezione sopra per iniziare il confronto tra drills e popolare il Drill Bank."
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
        f"{r['Session_Date']}  —  {r['Session_Name']}  ({int(r['n_drills'])} drills · ~{r['avg_act']:.0f} attivi · {r['tot_dur']:.1f} min)"
        for _, r in sess_df.iterrows()
    ]

    default_idx = 0
    last_saved = st.session_state.get("drills_last_saved_session")
    if last_saved and last_saved in session_keys:
        default_idx = session_keys.index(last_saved)

    col_sel_s, col_scope_s, col_view_mode, col_del_s = st.columns([2.4, 1.7, 1.8, 0.85])
    with col_sel_s:
        chosen_s_idx = st.selectbox(
            "Seleziona Seduta Archiviata",
            options=list(range(len(session_labels))),
            index=default_idx,
            format_func=lambda i: session_labels[i],
            key="drills_view_session_selector",
        )
    sel_date, sel_name = session_keys[chosen_s_idx]

    df_sess_raw = df_master[
        (df_master["Session_Date"] == sel_date) & (df_master["Session_Name"] == sel_name)
    ].sort_values(by="Drill_Order", ascending=True).reset_index(drop=True)

    df_roles_sess = pd.DataFrame()
    if df_roles is not None and not df_roles.empty:
        df_roles_sess = df_roles[
            (df_roles["Session_Date"] == sel_date) & (df_roles["Session_Name"] == sel_name)
        ].copy()

    scope_opts_sess = _get_scope_options(df_roles_sess)
    with col_scope_s:
        sel_scope_sess = st.selectbox(
            "🎯 Ambito Confronto Drills",
            options=scope_opts_sess,
            key="drills_sess_scope_selector",
            help="Selezionando un Reparto o un singolo Ruolo, tutti i confronti tra i drills della seduta usano la somma volumetrica di quel ruolo divisa per il numero effettivo di giocatori attivi di quel ruolo.",
        )

    with col_view_mode:
        view_mode_sess = st.radio(
            "Modalità Calcolo",
            options=["👤 Pro-Capite (Σ / N° Attivi)", "∑ Totale Gruppo/Ruolo"],
            horizontal=True,
            key="drills_sess_view_mode",
        )
    is_total_mode = view_mode_sess.startswith("∑")

    with col_del_s:
        if is_admin:
            st.markdown("<div style='height:27px;'></div>", unsafe_allow_html=True)
            with st.popover("🗑️", use_container_width=True):
                st.caption(f"Eliminare tutti i **{len(df_sess_raw)} drills** di **{sel_date} — {sel_name}**?")
                if st.button("Conferma Eliminazione", type="primary", key="btn_confirm_del_drill_sess"):
                    del_cnt = drills_manager.delete_session_drills(sel_date, sel_name)
                    st.session_state.pop("drills_last_saved_session", None)
                    st.session_state["drills_save_feedback"] = f"🗑️ Eliminati **{del_cnt} drills** della seduta {sel_date} — {sel_name}."
                    st.rerun()

    # Costruisci DataFrame drills della seduta coerente con lo scope (Squadra / Reparto / Ruolo)
    df_sess = _build_scoped_drills_df(df_sess_raw, df_roles_sess, sel_scope_sess)
    if df_sess.empty:
        st.info(f"Nessun dato attivo trovato per **{sel_scope_sess}** nella seduta selezionata.")
        return

    df_sess = df_sess.sort_values(by="Drill_Order", ascending=True).reset_index(drop=True)
    tot_dur = float(df_sess["Duration_Min"].sum())
    df_sess["Time_Share_%"] = np.where(tot_dur > 0, (df_sess["Duration_Min"] / tot_dur) * 100.0, 0.0).round(1)
    mean_wr_sess = float(df_sess["Work_Rate"].mean())
    df_sess["Delta_WR_%"] = np.where(mean_wr_sess > 0, ((df_sess["Work_Rate"] - mean_wr_sess) / mean_wr_sess) * 100.0, 0.0).round(1)

    # 5 Card KPI Seduta (Tempo integrato + Distanza/WR + Hml + HSR differenziato + Vmax/Acc-Dec)
    avg_act_p = float(df_sess["Active_Players_Count"].mean())
    tot_exc_p = int(df_sess["Excluded_Players_Count"].sum())

    if is_total_mode:
        dist_kpi = float(df_sess["Total_Distance_Sum"].sum())
        hml_kpi = float(df_sess["HMPD_Sum"].sum())
        hsr_kpi = float(df_sess["HSR_Sum"].sum())
        acc_kpi = float(df_sess["Acc_Events_Sum"].sum())
        dec_kpi = float(df_sess["Dec_Events_Sum"].sum())
        wr_sess_avg = round(float(df_sess["Total_Distance"].sum()) / tot_dur, 1) if tot_dur > 0 else float(df_sess["Work_Rate"].mean())
        hml_min_avg = round(float(df_sess["HMPD"].sum()) / tot_dur, 1) if tot_dur > 0 else float(df_sess["HMPD_per_Min"].mean())
        hsr_min_avg = round(float(df_sess["HSR"].sum()) / tot_dur, 1) if tot_dur > 0 else float(df_sess["HSR_per_Min"].mean())
        kpis_sess = [
            ("Drills & Tempo Totale", f"{len(df_sess)} Drills · {tot_dur:.1f}'", f"⏱️ {_fmt_mmss(tot_dur)} · ✅ ~{avg_act_p:.0f} att./drill ({sel_scope_sess})", FIR_NAVY),
            ("Distanza Totale & WR", f"{dist_kpi:,.0f} m", f"⚡ WR Pro-Cap.: {wr_sess_avg:.1f} m/min", FIR_AZZURO),
            ("Hml Totale (>25.5W)", f"{hml_kpi:,.0f} m", f"🔥 Media: {hml_min_avg:.1f} Hml/min pro-cap.", FIR_ORO),
            ("HSR Totale (>18/>20)", f"{hsr_kpi:,.0f} m", f"🏃 Media: {hsr_min_avg:.1f} HSR/min pro-cap.", FIR_AZZURO),
            ("Acc & Dec Totali", f"{acc_kpi:,.0f} / {dec_kpi:,.0f}", f"⚡ Acc: {acc_kpi:,.0f} · Dec: {dec_kpi:,.0f}", FIR_NAVY),
        ]
    else:
        dist_kpi = float(df_sess["Total_Distance"].sum())
        wr_sess_avg = round(dist_kpi / tot_dur, 1) if tot_dur > 0 else float(df_sess["Work_Rate"].mean())
        hml_kpi = float(df_sess["HMPD"].sum())
        hml_min_avg = round(hml_kpi / tot_dur, 1) if tot_dur > 0 else float(df_sess["HMPD_per_Min"].mean())
        hsr_kpi = float(df_sess["HSR"].sum())
        hsr_min_avg = round(hsr_kpi / tot_dur, 1) if tot_dur > 0 else float(df_sess["HSR_per_Min"].mean())
        avg_vmax = float(df_sess["Max_Speed"].mean())
        peak_vmax = float(df_sess["Max_Speed_Peak"].max()) if df_sess["Max_Speed_Peak"].max() > 0 else float(df_sess["Max_Speed"].max())
        acc_kpi = float(df_sess["Acc_Events"].sum())
        dec_kpi = float(df_sess["Dec_Events"].sum())
        kpis_sess = [
            ("Drills & Tempo Totale", f"{len(df_sess)} Drills · {tot_dur:.1f}'", f"⏱️ {_fmt_mmss(tot_dur)} · ✅ ~{avg_act_p:.0f} att. · 🚫 {tot_exc_p} escl.", FIR_NAVY),
            ("Distanza & Work Rate", f"{dist_kpi:,.0f} m", f"⚡ WR Medio: {wr_sess_avg:.1f} m/min", FIR_AZZURO),
            ("Hml Pro-Capite (>25.5W)", f"{hml_kpi:,.0f} m", f"🔥 Intensità: {hml_min_avg:.1f} Hml/min", FIR_ORO),
            ("HSR (>18 Av / >20 Tq)", f"{hsr_kpi:,.0f} m", f"🏃 Intensità: {hsr_min_avg:.1f} HSR/min", FIR_AZZURO),
            ("Picco Vmax & Acc/Dec", f"{peak_vmax:.1f} km/h", f"🚀 Med.: {avg_vmax:.1f} · Acc {acc_kpi:.1f} / Dec {dec_kpi:.1f}", FIR_NAVY),
        ]

    k_cols = st.columns(5)
    for col_w, (kl, kv, ks, ka) in zip(k_cols, kpis_sess):
        with col_w:
            st.markdown(_render_kpi_card(kl, kv, ks, ka), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    df_sess["Drill_Label"] = df_sess.apply(
        lambda r: f"#{int(r['Drill_Order'])} {r['Drill_Name']}<br>({r['Duration_Min']:.1f}' · {int(r['Active_Players_Count'])} att.)",
        axis=1,
    )

    # =========================================================================
    # RIGA GRAFICI 1 — VOLUME & TEMPO vs WORK RATE  |  INTENSITÀ RELATIVA AL MINUTO
    # =========================================================================
    col_g1, col_g2 = st.columns(2)
    wr_vals = pd.to_numeric(df_sess["Work_Rate"], errors="coerce").fillna(0.0)
    wr_min = float(wr_vals.min()) if not wr_vals.empty else 0.0
    wr_max = float(wr_vals.max()) if not wr_vals.empty else 100.0
    wr_span = max(wr_max - wr_min, 6.0)

    with col_g1:
        dist_col = "Total_Distance_Sum" if is_total_mode else "Total_Distance"
        dist_title = "Distanza Totale (m)" if is_total_mode else "Distanza Pro-Capite (m)"
        max_dist_v = max(float(pd.to_numeric(df_sess[dist_col], errors="coerce").fillna(0.0).max()), 1.0)

        fig_vol_wr = make_subplots(specs=[[{"secondary_y": True}]])
        fig_vol_wr.add_trace(
            go.Bar(
                x=df_sess["Drill_Label"],
                y=df_sess[dist_col],
                name=dist_title,
                marker=dict(color=FIR_AZZURO, line=dict(color=FIR_NAVY, width=1)),
                text=[f"<b>{v:,.0f}m</b><br>({d:.1f}')" for v, d in zip(df_sess[dist_col], df_sess["Duration_Min"])],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(color="#FFFFFF", size=11),
                cliponaxis=False,
            ),
            secondary_y=False,
        )
        fig_vol_wr.add_trace(
            go.Scatter(
                x=df_sess["Drill_Label"],
                y=df_sess["Work_Rate"],
                name="Work Rate (m/min)",
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=9, color=FIR_ORO, line=dict(color=FIR_NAVY, width=1.6)),
                text=[f"<b>{v:.1f}</b>" for v in df_sess["Work_Rate"]],
                textposition="top center",
                textfont=dict(color=FIR_NAVY, size=11),
                cliponaxis=False,
            ),
            secondary_y=True,
        )
        fig_vol_wr.update_yaxes(title_text=dist_title, range=[0, max_dist_v * 1.38], secondary_y=False)
        fig_vol_wr.update_yaxes(
            title_text="Work Rate (m/min)",
            range=[max(0.0, wr_min - wr_span * 2.2), wr_max + wr_span * 0.55],
            secondary_y=True,
            showgrid=False,
        )
        _apply_fir_plotly_layout(
            fig_vol_wr,
            f"Volume & Durata vs Work Rate — {sel_scope_sess}",
            height=400,
        )
        st.plotly_chart(fig_vol_wr, use_container_width=True)

    with col_g2:
        max_rate_v = max(
            float(pd.to_numeric(df_sess["HMPD_per_Min"], errors="coerce").fillna(0.0).max()),
            float(pd.to_numeric(df_sess["HSR_per_Min"], errors="coerce").fillna(0.0).max()),
            1.0,
        )
        fig_rates = make_subplots(specs=[[{"secondary_y": True}]])
        fig_rates.add_trace(
            go.Bar(
                x=df_sess["Drill_Label"],
                y=df_sess["HMPD_per_Min"],
                name="Hml/min (m/min)",
                marker=dict(color=FIR_NAVY, line=dict(color=FIR_NAVY, width=1)),
                text=[f"<b>{v:.1f}</b>" for v in df_sess["HMPD_per_Min"]],
                textposition="outside",
                textfont=dict(color=FIR_NAVY, size=10.5),
                cliponaxis=False,
            ),
            secondary_y=False,
        )
        fig_rates.add_trace(
            go.Bar(
                x=df_sess["Drill_Label"],
                y=df_sess["HSR_per_Min"],
                name="HSR/min (>18/>20)",
                marker=dict(color=FIR_ORO, line=dict(color=FIR_NAVY, width=1)),
                text=[f"<b>{v:.1f}</b>" for v in df_sess["HSR_per_Min"]],
                textposition="outside",
                textfont=dict(color=FIR_NAVY, size=10.5),
                cliponaxis=False,
            ),
            secondary_y=False,
        )
        fig_rates.add_trace(
            go.Scatter(
                x=df_sess["Drill_Label"],
                y=df_sess["Work_Rate"],
                name="Work Rate (m/min)",
                mode="lines+markers+text",
                line=dict(color=FIR_AZZURO, width=2.6, dash="dot"),
                marker=dict(size=8.5, color=FIR_AZZURO, line=dict(color="#FFFFFF", width=1.4)),
                text=[f"<b>{v:.1f}</b>" for v in df_sess["Work_Rate"]],
                textposition="top center",
                textfont=dict(color=FIR_AZZURO, size=10.5),
                cliponaxis=False,
            ),
            secondary_y=True,
        )
        fig_rates.update_layout(barmode="group")
        fig_rates.update_yaxes(title_text="Hml/min & HSR/min (m/min)", range=[0, max_rate_v * 1.52], secondary_y=False)
        fig_rates.update_yaxes(
            title_text="Work Rate (m/min)",
            range=[max(0.0, wr_min - wr_span * 2.4), wr_max + wr_span * 0.55],
            secondary_y=True,
            showgrid=False,
        )
        _apply_fir_plotly_layout(
            fig_rates,
            f"Intensità al Minuto (Hml/min · HSR/min · Work Rate) — {sel_scope_sess}",
            height=400,
        )
        st.plotly_chart(fig_rates, use_container_width=True)

    # =========================================================================
    # RIGA GRAFICI 2 — MAPPA DURATA × INTENSITÀ  |  RIPARTIZIONE % TEMPO E CARICO
    # =========================================================================
    col_g3, col_g4 = st.columns(2)
    with col_g3:
        y_matrix_opts = {
            "Work_Rate": "Work Rate (m/min)",
            "HMPD_per_Min": "Hml/min (m/min)",
            "HSR_per_Min": "HSR/min (>18 Av / >20 Tq)",
        }
        sel_y_mat = st.selectbox(
            "Asse Y Mappa Operativa Drills (Durata × Intensità)",
            options=list(y_matrix_opts.keys()),
            format_func=lambda k: y_matrix_opts[k],
            key="drills_sess_matrix_y",
        )
        hml_size_col = "HMPD_Sum" if is_total_mode else "HMPD"
        max_sz = max(float(df_sess[hml_size_col].max()), 1.0)
        bubble_sizes = [max(16.0, (float(v) / max_sz) * 44.0) for v in df_sess[hml_size_col]]
        bubble_colors = [DRILL_PALETTE[i % len(DRILL_PALETTE)] for i in range(len(df_sess))]

        fig_matrix = go.Figure()
        fig_matrix.add_trace(
            go.Scatter(
                x=df_sess["Duration_Min"],
                y=df_sess[sel_y_mat],
                mode="markers+text",
                marker=dict(
                    size=bubble_sizes,
                    color=bubble_colors,
                    opacity=0.88,
                    line=dict(color=FIR_NAVY, width=1.8),
                ),
                text=[f"<b>#{int(r['Drill_Order'])} {r['Drill_Name']}</b>" for _, r in df_sess.iterrows()],
                textposition="top center",
                textfont=dict(size=10.5, color=FIR_NAVY),
                cliponaxis=False,
                customdata=np.stack(
                    [
                        df_sess["Total_Distance"],
                        df_sess["HMPD"],
                        df_sess["HSR"],
                        df_sess["Work_Rate"],
                    ],
                    axis=-1,
                ),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Durata: %{x:.1f} min<br>"
                    + f"{y_matrix_opts[sel_y_mat]}: " + "%{y:.1f}<br>"
                    "Dist Pro-Cap: %{customdata[0]:,.0f} m<br>"
                    "Hml Pro-Cap: %{customdata[1]:,.1f} m<br>"
                    "HSR Pro-Cap: %{customdata[2]:,.1f} m<extra></extra>"
                ),
                showlegend=False,
            )
        )
        if len(df_sess) >= 2:
            mean_x = float(df_sess["Duration_Min"].mean())
            mean_y = float(df_sess[sel_y_mat].mean())
            fig_matrix.add_vline(x=mean_x, line_dash="dash", line_color="#94A3B8", line_width=1.4)
            fig_matrix.add_hline(y=mean_y, line_dash="dash", line_color="#94A3B8", line_width=1.4)

        xm_min = float(df_sess["Duration_Min"].min())
        xm_max = float(df_sess["Duration_Min"].max())
        ym_min = float(df_sess[sel_y_mat].min())
        ym_max = float(df_sess[sel_y_mat].max())
        xm_pad = max((xm_max - xm_min) * 0.25, 0.9)
        ym_pad = max((ym_max - ym_min) * 0.32, 1.8)

        fig_matrix.update_xaxes(title_text="Durata Effettiva Drill (min)", range=[max(0.0, xm_min - xm_pad), xm_max + xm_pad])
        fig_matrix.update_yaxes(title_text=y_matrix_opts[sel_y_mat], range=[max(0.0, ym_min - ym_pad), ym_max + ym_pad * 1.35])
        _apply_fir_plotly_layout(
            fig_matrix,
            f"Mappa Operativa: Durata × {y_matrix_opts[sel_y_mat]} (bolla = Hml)",
            height=370,
        )
        fig_matrix.update_layout(margin=dict(l=58, r=28, t=64, b=52), hovermode="closest")
        st.plotly_chart(fig_matrix, use_container_width=True)

    with col_g4:
        st.markdown("<div style='height:28px; padding-top:6px; font-size:0.78rem; font-weight:700; color:#475569;'>Quota % di Tempo e Carico assorbita da ciascun Drill nella Seduta</div>", unsafe_allow_html=True)
        share_metrics = [
            ("Tempo (%)", "Duration_Min"),
            ("Distanza (%)", "Total_Distance_Sum" if is_total_mode else "Total_Distance"),
            ("Hml (%)", "HMPD_Sum" if is_total_mode else "HMPD"),
            ("HSR (%)", "HSR_Sum" if is_total_mode else "HSR"),
        ]
        fig_share = go.Figure()
        cat_labels = [m[0] for m in share_metrics]
        totals_map = {m[1]: max(float(df_sess[m[1]].sum()), 1e-6) for m in share_metrics}

        for d_idx, (_, r) in enumerate(df_sess.iterrows()):
            pct_vals = [round(float(r[m[1]]) / totals_map[m[1]] * 100.0, 1) for m in share_metrics]
            fig_share.add_trace(
                go.Bar(
                    y=cat_labels,
                    x=pct_vals,
                    name=f"#{int(r['Drill_Order'])} {r['Drill_Name']}",
                    orientation="h",
                    marker=dict(color=DRILL_PALETTE[d_idx % len(DRILL_PALETTE)], line=dict(color="#FFFFFF", width=1.2)),
                    text=[f"<b>{p:.0f}%</b>" if p >= 9 else "" for p in pct_vals],
                    textposition="inside",
                    insidetextanchor="middle",
                    textfont=dict(color="#FFFFFF", size=11),
                    hovertemplate="<b>%{fullData.name}</b><br>%{y}: %{x:.1f}%<extra></extra>",
                )
            )
        fig_share.update_layout(barmode="stack")
        fig_share.update_xaxes(range=[0, 100], ticksuffix="%")
        _apply_fir_plotly_layout(
            fig_share,
            f"Ripartizione % Tempo vs Carico — {sel_name}",
            height=370,
        )
        fig_share.update_layout(margin=dict(l=92, r=24, t=78, b=46), hovermode="y unified")
        fig_share.update_yaxes(tickfont=dict(color=FIR_NAVY, size=11), automargin=True)
        st.plotly_chart(fig_share, use_container_width=True)

    # =========================================================================
    # RIGA GRAFICO 3 — CONFRONTO VOLUMETRICO & MECCANICO SELETTIVO TRA DRILLS
    # =========================================================================
    has_reparti = (
        "Avanti_Active_Count" in df_sess.columns
        and "Trequarti_Active_Count" in df_sess.columns
        and df_sess["Avanti_Active_Count"].fillna(0).sum() > 0
        and df_sess["Trequarti_Active_Count"].fillna(0).sum() > 0
    )
    sec_modes = [
        "Hml (m) vs HSR (m) [>18 Av / >20 Tq]",
        "Max Speed Media vs Picco (km/h)",
        "Accelerazioni vs Decelerazioni",
    ]
    if has_reparti and sel_scope_sess == "Intera Squadra (Attivi)":
        sec_modes.insert(1, "Avanti vs Trequarti tra i Drills")

    g_sec_mode = st.selectbox(
        "Confronto Secondario Volumetrico / Meccanico tra Drills",
        options=sec_modes,
        key="drills_sess_chart_sec_mode",
    )

    if g_sec_mode.startswith("Hml (m)"):
        c_hml = "HMPD_Sum" if is_total_mode else "HMPD"
        c_hsr = "HSR_Sum" if is_total_mode else "HSR"
        tag_m = "Totale" if is_total_mode else "Pro-Capite"
        fig_sec = go.Figure()
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_hml], name=f"Hml ({tag_m})", marker_color=FIR_NAVY, text=[f"{v:,.0f}" for v in df_sess[c_hml]], textposition="outside"))
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_hsr], name=f"HSR >18/>20 ({tag_m})", marker_color=FIR_ORO, text=[f"{v:,.0f}" for v in df_sess[c_hsr]], textposition="outside"))
        fig_sec.update_layout(barmode="group")
        _apply_fir_plotly_layout(fig_sec, f"Confronto Alta Intensità tra Drills: Hml (m) vs HSR (m) ({tag_m} · {sel_scope_sess})", height=350)
    elif g_sec_mode == "Avanti vs Trequarti tra i Drills":
        fig_sec = go.Figure()
        if is_total_mode:
            fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Avanti_Total_Distance_Sum"], name="Avanti Dist. Totale (m)", marker_color=FIR_AZZURO, text=[f"{v:,.0f}" for v in df_sess["Avanti_Total_Distance_Sum"]], textposition="outside"))
            fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Trequarti_Total_Distance_Sum"], name="Trequarti Dist. Totale (m)", marker_color=FIR_ORO, text=[f"{v:,.0f}" for v in df_sess["Trequarti_Total_Distance_Sum"]], textposition="outside"))
            _apply_fir_plotly_layout(fig_sec, "Carico Totale tra Drills: Avanti vs Trequarti (m)", height=350)
        else:
            fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Avanti_Work_Rate"], name="Avanti WR (m/min)", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Avanti_Work_Rate"]], textposition="outside"))
            fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Trequarti_Work_Rate"], name="Trequarti WR (m/min)", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Trequarti_Work_Rate"]], textposition="outside"))
            _apply_fir_plotly_layout(fig_sec, "Work Rate tra Drills: Avanti vs Trequarti (m/min)", height=350)
        fig_sec.update_layout(barmode="group")
    elif g_sec_mode == "Max Speed Media vs Picco (km/h)":
        fig_sec = go.Figure()
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed"], name="Max Speed Media", marker_color=FIR_AZZURO, text=[f"{v:.1f}" for v in df_sess["Max_Speed"]], textposition="outside"))
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess["Max_Speed_Peak"], name="Picco Individuale", marker_color=FIR_ORO, text=[f"{v:.1f}" for v in df_sess["Max_Speed_Peak"]], textposition="outside"))
        fig_sec.update_layout(barmode="group")
        _apply_fir_plotly_layout(fig_sec, f"Velocità Massima tra Drills ({sel_scope_sess}) (km/h)", height=350)
    else:
        c_acc = "Acc_Events_Sum" if is_total_mode else "Acc_Events"
        c_dec = "Dec_Events_Sum" if is_total_mode else "Dec_Events"
        tag_m = "Totali" if is_total_mode else "Pro-Capite"
        fig_sec = go.Figure()
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_acc], name=f"Acc ({tag_m})", marker_color=FIR_AZZURO, text=[f"{v:,.1f}" for v in df_sess[c_acc]], textposition="outside"))
        fig_sec.add_trace(go.Bar(x=df_sess["Drill_Label"], y=df_sess[c_dec], name=f"Dec ({tag_m})", marker_color=FIR_NAVY, text=[f"{v:,.1f}" for v in df_sess[c_dec]], textposition="outside"))
        fig_sec.update_layout(barmode="group")
        _apply_fir_plotly_layout(fig_sec, f"Eventi Neuromuscolari tra Drills ({tag_m})", height=350)

    fig_sec.update_traces(cliponaxis=False)
    # Aggiunge respiro in alto per evitare taglio etichette barre
    sec_y_max = 0.0
    for tr in fig_sec.data:
        if getattr(tr, "y", None) is not None and len(tr.y) > 0:
            try:
                sec_y_max = max(sec_y_max, float(np.nanmax(pd.to_numeric(list(tr.y), errors="coerce"))))
            except Exception:
                pass
    if sec_y_max > 0:
        fig_sec.update_yaxes(range=[0, sec_y_max * 1.24])
    st.plotly_chart(fig_sec, use_container_width=True)

    # =========================================================================
    # TABELLA COMPARATIVA COMPLETA DRILLS DELLA SEDUTA (CON TEMPO & Δ%)
    # =========================================================================
    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📋 Tabella Comparativa Drills — {sel_date} · {sel_name} · {sel_scope_sess} ({'Totale Gruppo/Ruolo' if is_total_mode else 'Pro-Capite Σ/N° Attivi'})</div>",
        unsafe_allow_html=True,
    )
    df_sess_disp = df_sess.copy()
    df_sess_disp["Durata_mmss"] = df_sess_disp["Duration_Min"].apply(_fmt_mmss)

    if is_total_mode:
        df_table = df_sess_disp[[
            "Drill_Order", "Drill_Name", "Active_Players_Count", "Excluded_Players_Count",
            "Duration_Min", "Durata_mmss", "Time_Share_%",
            "Total_Distance_Sum", "Work_Rate", "HMPD_Sum", "HMPD_per_Min",
            "HSR_Sum", "HSR_per_Min", "Acc_Events_Sum", "Dec_Events_Sum",
        ]].rename(
            columns={
                "Drill_Order": "Ord.",
                "Drill_Name": "Drill",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Escl.",
                "Duration_Min": "Dur. (min)",
                "Durata_mmss": "mm:ss",
                "Time_Share_%": "% Tempo",
                "Total_Distance_Sum": "Dist. Tot (m)",
                "Work_Rate": "WR (m/m)",
                "HMPD_Sum": "Hml Tot (m)",
                "HMPD_per_Min": "Hml/m",
                "HSR_Sum": "HSR Tot (m)",
                "HSR_per_Min": "HSR/m",
                "Acc_Events_Sum": "Acc Tot",
                "Dec_Events_Sum": "Dec Tot",
            }
        )
    else:
        df_table = df_sess_disp[[
            "Drill_Order", "Drill_Name", "Active_Players_Count", "Excluded_Players_Count",
            "Duration_Min", "Durata_mmss", "Time_Share_%",
            "Total_Distance", "Work_Rate", "Delta_WR_%",
            "HMPD", "HMPD_per_Min", "HSR", "HSR_per_Min",
            "Max_Speed", "Max_Speed_Peak", "Acc_Events", "Dec_Events",
        ]].rename(
            columns={
                "Drill_Order": "Ord.",
                "Drill_Name": "Drill",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Escl.",
                "Duration_Min": "Dur. (min)",
                "Durata_mmss": "mm:ss",
                "Time_Share_%": "% Tempo",
                "Total_Distance": "Dist. (m)",
                "Work_Rate": "WR (m/m)",
                "Delta_WR_%": "Δ WR %",
                "HMPD": "Hml (m)",
                "HMPD_per_Min": "Hml/m",
                "HSR": "HSR (m)",
                "HSR_per_Min": "HSR/m",
                "Max_Speed": "Vmax Med.",
                "Max_Speed_Peak": "Vmax Picco",
                "Acc_Events": "Acc",
                "Dec_Events": "Dec",
            }
        )
    st.dataframe(df_table, use_container_width=True, hide_index=True)

    # Prepara dati compatti opzionali per appendice PDF & expander
    df_roles_compact = _build_compact_role_summary(df_roles_sess)
    df_ps_sess = pd.DataFrame()
    df_excl_sess = pd.DataFrame()
    if df_players is not None and not df_players.empty:
        df_ps_sess = df_players[
            (df_players["Session_Date"] == sel_date) & (df_players["Session_Name"] == sel_name)
        ].copy()
        if not df_ps_sess.empty:
            df_excl_sess = df_ps_sess[df_ps_sess["Is_Active"] == False].copy()

    # =========================================================================
    # ACTION BAR — ESPORTAZIONE PDF COMPLETA (FEDELE ALLA PAGINA) & CSV
    # =========================================================================
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    act_c1, act_c2 = st.columns([1.4, 1.0])
    pdf_cache_key = f"drills_sess_pdf_{sel_date}_{sel_name}_{sel_scope_sess}_{is_total_mode}_{sel_y_mat}_{g_sec_mode}"

    with act_c1:
        if st.button(
            "📄 Genera Report PDF Completo Seduta (Fedele alla Pagina)",
            type="primary",
            use_container_width=True,
            key="btn_gen_pdf_drills_sess",
        ):
            with st.spinner("Generazione PDF FIR ad alta risoluzione con tutti i grafici e le tabelle..."):
                pdf_bytes = drills_pdf.crea_pdf_drills_sessione(
                    session_date=sel_date,
                    session_name=sel_name,
                    scope_label=sel_scope_sess,
                    is_total_mode=is_total_mode,
                    df_sess=df_sess,
                    kpis=kpis_sess,
                    fig_vol_wr=fig_vol_wr,
                    fig_rates=fig_rates,
                    fig_matrix=fig_matrix,
                    fig_share=fig_share,
                    fig_sec=fig_sec,
                    df_roles_compact=df_roles_compact if sel_scope_sess == "Intera Squadra (Attivi)" else None,
                    df_excluded=df_excl_sess if not df_excl_sess.empty else None,
                )
                st.session_state["drills_sess_pdf_payload"] = (pdf_cache_key, pdf_bytes)

        cached_pdf = st.session_state.get("drills_sess_pdf_payload")
        if cached_pdf and cached_pdf[0] == pdf_cache_key:
            st.download_button(
                "⬇️ Scarica Report PDF Seduta (.pdf)",
                data=cached_pdf[1],
                file_name=f"FIR_Drills_Seduta_{sel_date}_{_slug(sel_name)}_{_slug(sel_scope_sess)}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_session_drills_pdf",
            )

    with act_c2:
        csv_export_df = df_sess.drop(
            columns=[
                "Drill_Label", "Dynamic_Stress_Load", "DSL_per_Min",
                "Dynamic_Stress_Load_Sum", "Avanti_DSL", "Trequarti_DSL",
                "Avanti_DSL_Sum", "Trequarti_DSL_Sum",
                "Heavy_Impacts", "Heavy_Impacts_Sum",
            ],
            errors="ignore",
        ).rename(
            columns={
                "HMPD": "Hml_m",
                "HMPD_per_Min": "Hml_per_Min",
                "HMPD_Sum": "Hml_Sum_m",
                "Avanti_HMPD": "Avanti_Hml_m",
                "Trequarti_HMPD": "Trequarti_Hml_m",
                "Avanti_HMPD_Sum": "Avanti_Hml_Sum_m",
                "Trequarti_HMPD_Sum": "Trequarti_Hml_Sum_m",
            }
        )
        csv_sess = csv_export_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ Esporta CSV Drills Seduta (Hml + HSR FIR)",
            data=csv_sess,
            file_name=f"FIR_Drills_{sel_date}_{_slug(sel_name)}.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_session_drills_csv",
        )

    # =========================================================================
    # EXPANDER OPZIONALI (CHIUSI DI DEFAULT): RUOLI COMPATTI & DETTAGLIO ATLETI
    # =========================================================================
    if not df_roles_compact.empty:
        with st.expander("📋 Riepilogo Tabellare Volumetrico per Ruolo nella Seduta (opzionale — Σ Ruolo / N° Attivi)", expanded=False):
            st.caption("Suggerimento: per confrontare i drills di un singolo ruolo, usa il selettore **🎯 Ambito Confronto Drills** in alto.")
            st.dataframe(
                df_roles_compact[[
                    "Role", "Department", "Attivi_Medi", "Esclusi_Totali",
                    "Total_Distance", "Total_Distance_Sum", "Work_Rate",
                    "HMPD", "HMPD_Sum", "HSR", "HSR_Sum", "Max_Speed",
                ]].rename(
                    columns={
                        "Role": "Ruolo",
                        "Department": "Reparto",
                        "Attivi_Medi": "Attivi (Med.)",
                        "Esclusi_Totali": "Escl.",
                        "Total_Distance": "Dist. Pro-Cap (m)",
                        "Total_Distance_Sum": "Dist. Tot Ruolo (m)",
                        "Work_Rate": "WR (m/m)",
                        "HMPD": "Hml Pro-Cap (m)",
                        "HMPD_Sum": "Hml Tot Ruolo (m)",
                        "HSR": "HSR Pro-Cap (m)",
                        "HSR_Sum": "HSR Tot Ruolo (m)",
                        "Max_Speed": "Vmax Med.",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

    if not df_ps_sess.empty:
        n_p_act = int(df_ps_sess["Is_Active"].sum())
        n_p_exc = int((~df_ps_sess["Is_Active"]).sum())
        with st.expander(
            f"👥 Dettaglio Individuale Atleti — ✅ {n_p_act} Attivi / 🚫 {n_p_exc} Esclusi (Fuori Campo / Rotazioni)",
            expanded=False,
        ):
            c_pf1, c_pf2 = st.columns([2, 1.5])
            with c_pf1:
                drill_filter = st.selectbox(
                    "Filtra per Drill",
                    options=["Tutti i Drills"] + df_sess_raw["Drill_Name"].tolist(),
                    key="drills_player_detail_filter",
                )
            with c_pf2:
                status_filter = st.radio(
                    "Stato Partecipazione",
                    options=["Tutti", "Solo Attivi", "Solo Esclusi (Fuori Campo)"],
                    horizontal=True,
                    key="drills_player_status_filter",
                )
            df_ps_f = df_ps_sess.copy()
            if drill_filter != "Tutti i Drills":
                df_ps_f = df_ps_f[df_ps_f["Drill_Name"] == drill_filter]
            if status_filter == "Solo Attivi":
                df_ps_f = df_ps_f[df_ps_f["Is_Active"] == True]
            elif status_filter == "Solo Esclusi (Fuori Campo)":
                df_ps_f = df_ps_f[df_ps_f["Is_Active"] == False]

            df_ps_f["Stato"] = np.where(df_ps_f["Is_Active"], "✅ Attivo", "🚫 Escluso")
            st.dataframe(
                df_ps_f[[
                    "Drill_Order", "Drill_Name", "Stato", "Player_Name", "Role", "Department",
                    "Duration_Min", "Total_Distance", "Work_Rate", "HMPD", "HSR",
                    "Max_Speed", "Acc_Events", "Dec_Events", "Exclusion_Reason",
                ]].rename(
                    columns={
                        "Drill_Order": "Ord.",
                        "Drill_Name": "Drill",
                        "Player_Name": "Atleta",
                        "Role": "Ruolo",
                        "Department": "Reparto",
                        "Duration_Min": "Dur. (min)",
                        "Total_Distance": "Dist. (m)",
                        "Work_Rate": "WR (m/m)",
                        "HMPD": "Hml (m)",
                        "HSR": "HSR (m)",
                        "Max_Speed": "Vmax",
                        "Acc_Events": "Acc",
                        "Dec_Events": "Dec",
                        "Exclusion_Reason": "Motivo Esclusione",
                    }
                ).sort_values(by=["Ord.", "Stato", "WR (m/m)"], ascending=[True, True, False]),
                use_container_width=True,
                hide_index=True,
            )


def _build_bank_catalog_scoped(
    df_master: pd.DataFrame,
    df_roles: pd.DataFrame,
    selected_scope: str,
) -> pd.DataFrame:
    """
    Costruisce il catalogo aggregato per Drill_Name nello scope selezionato
    (Squadra, Reparto o Singolo Ruolo), usando SEMPRE somme volumetriche / numero effettivo atleti attivi
    e somme volumetriche / somma durata attiva per tutti i tassi al minuto!
    """
    scoped = _build_scoped_drills_df(df_master, df_roles, selected_scope)
    if scoped.empty:
        return pd.DataFrame()

    if "Duration_Min_Sum" not in scoped.columns:
        scoped["Duration_Min_Sum"] = scoped["Duration_Min"] * scoped["Active_Players_Count"]

    cat = (
        scoped.groupby("Drill_Name", as_index=False)
        .agg(
            Esecuzioni=("Session_Date", "count"),
            Ultima_Data=("Session_Date", "max"),
            Attivi_Totali=("Active_Players_Count", "sum"),
            Attivi_Medi=("Active_Players_Count", "mean"),
            Duration_Min_Sum=("Duration_Min_Sum", "sum"),
            Total_Distance_Sum=("Total_Distance_Sum", "sum"),
            HMPD_Sum=("HMPD_Sum", "sum"),
            HSR_Sum=("HSR_Sum", "sum"),
            Dynamic_Stress_Load_Sum=("Dynamic_Stress_Load_Sum", "sum"),
            Heavy_Impacts_Sum=("Heavy_Impacts_Sum", "sum"),
            Max_Speed=("Max_Speed", "mean"),
            Max_Speed_Peak=("Max_Speed_Peak", "max"),
        )
    )
    n_den = cat["Attivi_Totali"].replace(0, np.nan)
    dur_den = cat["Duration_Min_Sum"].replace(0, np.nan)
    exec_den = cat["Esecuzioni"].replace(0, np.nan)

    cat["Durata_Media"] = (cat["Duration_Min_Sum"] / n_den).fillna(0.0).round(2)
    cat["Dist_ProCapite"] = (cat["Total_Distance_Sum"] / n_den).fillna(0.0).round(1)
    cat["Dist_Totale_Medio"] = (cat["Total_Distance_Sum"] / exec_den).fillna(0.0).round(1)
    cat["Work_Rate_Medio"] = (cat["Total_Distance_Sum"] / dur_den).fillna(0.0).round(1)
    cat["Hml_ProCapite"] = (cat["HMPD_Sum"] / n_den).fillna(0.0).round(1)
    cat["Hml_Totale_Medio"] = (cat["HMPD_Sum"] / exec_den).fillna(0.0).round(1)
    cat["Hml_per_Min"] = (cat["HMPD_Sum"] / dur_den).fillna(0.0).round(1)
    cat["HSR_ProCapite"] = (cat["HSR_Sum"] / n_den).fillna(0.0).round(1)
    cat["HSR_Totale_Medio"] = (cat["HSR_Sum"] / exec_den).fillna(0.0).round(1)
    cat["HSR_per_Min"] = (cat["HSR_Sum"] / dur_den).fillna(0.0).round(1)
    cat["DSL_ProCapite"] = (cat["Dynamic_Stress_Load_Sum"] / n_den).fillna(0.0).round(1)
    cat["DSL_Totale_Medio"] = (cat["Dynamic_Stress_Load_Sum"] / exec_den).fillna(0.0).round(1)
    cat["DSL_per_Min"] = (cat["Dynamic_Stress_Load_Sum"] / dur_den).fillna(0.0).round(1)
    cat["Heavy_Imp_ProCapite"] = (cat["Heavy_Impacts_Sum"] / n_den).fillna(0.0).round(1)
    cat["Attivi_Medi"] = cat["Attivi_Medi"].round(1)
    cat["Max_Speed"] = cat["Max_Speed"].round(1)
    cat["Max_Speed_Peak"] = cat["Max_Speed_Peak"].round(1)

    return cat.sort_values(by="Work_Rate_Medio", ascending=False).reset_index(drop=True)


def _render_tab_drill_bank(df_master: pd.DataFrame, df_roles: pd.DataFrame):
    banner_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_NAVY} 0%, #002B49 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:12px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            🔍 Archivio Globale &amp; Arena Confronto Multi-Drill — FIR Drill Bank
        </div>
        <div style="font-size:0.78rem; color:#CBD5E1; margin-top:2px;">
            Analizza l'evoluzione longitudinale di un drill e confronta più esercitazioni tra loro (<b>Radar 6 assi, Mappa Durata × Intensità, Benchmark Δ%</b>),
            con filtro per <b>Squadra, Reparto o Singolo Ruolo</b> (<b>Σ Ruolo / N° Attivi del Ruolo</b> · Hml &gt;25.5W · HSR &gt;18 Av / &gt;20 Tq).
        </div>
    </div>
    """
    st.markdown(_clean_html(banner_html), unsafe_allow_html=True)

    if df_master.empty:
        st.info(
            "📭 Il **Drill Bank** è attualmente vuoto. Carica almeno una seduta nel Tab **📂 Gestione & Vista per Sessione** "
            "per sbloccare l'analisi longitudinale e il confronto multi-drill."
        )
        return

    drill_counts = df_master.groupby("Drill_Name").size().sort_values(ascending=False)
    unique_drills = drill_counts.index.tolist()

    # =========================================================================
    # SEZIONE 1 — EVOLUZIONE LONGITUDINALE CROSS-SESSION DI UN DRILL
    # =========================================================================
    r1_c1, r1_c2, r1_c3 = st.columns([2.0, 1.9, 1.9])
    with r1_c1:
        selected_drill = st.selectbox(
            "🎯 Seleziona Drill dallo Storico (Evoluzione nel Tempo)",
            options=unique_drills,
            format_func=lambda d: f"{d}  ({int(drill_counts[d])} esecuzioni)",
            key="drill_bank_select_drill",
        )
    with r1_c2:
        bank_view_mode = st.radio(
            "Modalità Calcolo",
            options=["👤 Pro-Capite (Σ / N° Attivi)", "∑ Totale Gruppo/Ruolo"],
            horizontal=True,
            key="drill_bank_view_mode",
        )
    is_total_mode = bank_view_mode.startswith("∑")

    df_roles_drill = pd.DataFrame()
    if df_roles is not None and not df_roles.empty:
        df_roles_drill = df_roles[df_roles["Drill_Name"] == selected_drill].copy()

    scope_options = _get_scope_options(df_roles_drill)
    with r1_c3:
        selected_scope = st.selectbox(
            "🎯 Ambito / Ruolo (Σ Ruolo / N° Attivi)",
            options=scope_options,
            key="drill_bank_scope_selector",
        )

    df_d_master = df_master[df_master["Drill_Name"] == selected_drill].copy()
    df_d = _build_scoped_drills_df(df_d_master, df_roles_drill, selected_scope)
    if df_d.empty:
        st.info(f"Nessuna esecuzione trovata per **{selected_drill}** nello scope **{selected_scope}**.")
        return

    df_d = df_d.sort_values(by=["Session_Date", "Drill_Order"], ascending=[True, True]).reset_index(drop=True)

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
        default_sec = "Duration_Min" if primary_metric != "Duration_Min" else "HMPD_per_Min"
        def_sec_idx = sec_options.index(default_sec) if default_sec in sec_options else 0
        secondary_metric = st.selectbox(
            "Metrica Secondaria (Linea — es. Durata o Hml/min)",
            options=sec_options,
            index=def_sec_idx,
            format_func=lambda k: "— Nessuna —" if k == "Nessuna" else metric_dict[k],
            key=f"drill_bank_secondary_{is_total_mode}",
        )

    # 5 Card KPI Longitudinali (integrando Durata e Hml)
    n_exec = len(df_d)
    avg_act_hist = float(df_d["Active_Players_Count"].mean())
    avg_dur_hist = float(df_d["Duration_Min"].mean())
    p_series = pd.to_numeric(df_d[primary_metric], errors="coerce").fillna(0.0)
    p_mean_val = float(p_series.mean())
    p_last_val = float(p_series.iloc[-1])
    delta_p_pct = ((p_last_val - p_mean_val) / p_mean_val * 100.0) if p_mean_val > 0 else 0.0
    delta_sign = "+" if delta_p_pct >= 0 else ""

    hml_col = "HMPD_Sum" if is_total_mode else "HMPD"
    hsr_col = "HSR_Sum" if is_total_mode else "HSR"
    acc_col = "Acc_Events_Sum" if is_total_mode else "Acc_Events"
    dec_col = "Dec_Events_Sum" if is_total_mode else "Dec_Events"

    kpis_bank = [
        ("Esecuzioni & Durata", f"{n_exec} sed. · {avg_dur_hist:.1f}'", f"⏱️ {_fmt_mmss(avg_dur_hist)} · ✅ ~{avg_act_hist:.1f} att. ({selected_scope})", FIR_NAVY),
        (metric_dict[primary_metric][:26], f"{p_mean_val:,.1f}", f"Ultima: {p_last_val:,.1f} ({delta_sign}{delta_p_pct:.1f}%)", FIR_AZZURO),
        ("Hml Medio" + (" (Tot.)" if is_total_mode else " (Pro-Cap.)"), f"{df_d[hml_col].mean():,.0f} m", f"🔥 {df_d['HMPD_per_Min'].mean():.1f} Hml/min", FIR_ORO),
        ("HSR (>18 Av / >20 Tq)", f"{df_d[hsr_col].mean():,.0f} m", f"🏃 {df_d['HSR_per_Min'].mean():.1f} HSR/min", FIR_AZZURO),
        ("Picco Vmax & Acc/Dec", f"{df_d['Max_Speed_Peak'].max():.1f} km/h", f"🚀 Med.: {df_d['Max_Speed'].mean():.1f} · Acc {df_d[acc_col].mean():,.1f} / Dec {df_d[dec_col].mean():,.1f}", FIR_NAVY),
    ]
    kb_cols = st.columns(5)
    for col_w, (kl, kv, ks, ka) in zip(kb_cols, kpis_bank):
        with col_w:
            st.markdown(_render_kpi_card(kl, kv, ks, ka), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    df_d["Exec_Label"] = df_d.apply(
        lambda r: f"{r['Session_Date']}<br>{r['Session_Name']}<br>({r['Duration_Min']:.1f}' · {int(r['Active_Players_Count'])} att.)",
        axis=1,
    )

    col_bl1, col_bl2 = st.columns([1.35, 1.0])
    with col_bl1:
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
            line_width=1.8,
            annotation_text=f"Media: {p_mean_val:,.1f}",
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
        _apply_fir_plotly_layout(fig_long, f"Evoluzione Longitudinale: {selected_drill} ({selected_scope})", height=385)
        st.plotly_chart(fig_long, use_container_width=True)

    with col_bl2:
        fig_hi = go.Figure()
        fig_hi.add_trace(
            go.Scatter(
                x=df_d["Exec_Label"],
                y=df_d[hml_col],
                name=f"Hml ({'Totale' if is_total_mode else 'Pro-Capite'})",
                mode="lines+markers+text",
                line=dict(color=FIR_NAVY, width=3),
                marker=dict(size=8, color=FIR_NAVY),
                text=[f"{v:,.0f}" for v in df_d[hml_col]],
                textposition="top center",
                fill="tozeroy",
                fillcolor="rgba(3,25,38,0.08)",
            )
        )
        fig_hi.add_trace(
            go.Scatter(
                x=df_d["Exec_Label"],
                y=df_d[hsr_col],
                name=f"HSR >18/>20 ({'Totale' if is_total_mode else 'Pro-Capite'})",
                mode="lines+markers+text",
                line=dict(color=FIR_ORO, width=3),
                marker=dict(size=8, color=FIR_ORO),
                text=[f"{v:,.0f}" for v in df_d[hsr_col]],
                textposition="bottom center",
            )
        )
        _apply_fir_plotly_layout(fig_hi, f"Trend Alta Intensità: Hml (m) & HSR (m) — {selected_drill}", height=385)
        st.plotly_chart(fig_hi, use_container_width=True)

    # Tabella Storica Esecuzioni
    df_hist_view = df_d.copy()
    mean_wr_h = float(df_hist_view["Work_Rate"].mean())
    df_hist_view["Delta_WR_%"] = np.where(mean_wr_h > 0, ((df_hist_view["Work_Rate"] - mean_wr_h) / mean_wr_h) * 100.0, 0.0).round(1)

    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📑 Storico Esecuzioni Cross-Session: {selected_drill} ({selected_scope})</div>",
        unsafe_allow_html=True,
    )
    st.dataframe(
        df_hist_view[[
            "Session_Date", "Session_Name", "Drill_Order", "Active_Players_Count", "Excluded_Players_Count",
            "Duration_Min", "Total_Distance", "Total_Distance_Sum", "Work_Rate", "Delta_WR_%",
            "HMPD", "HMPD_per_Min", "HSR", "HSR_per_Min", "Max_Speed", "Acc_Events", "Dec_Events",
        ]].rename(
            columns={
                "Session_Date": "Data",
                "Session_Name": "Allenamento",
                "Drill_Order": "Ord.",
                "Active_Players_Count": "Attivi",
                "Excluded_Players_Count": "Escl.",
                "Duration_Min": "Dur. (min)",
                "Total_Distance": "Dist. Pro-Cap (m)",
                "Total_Distance_Sum": "Dist. Tot (m)",
                "Work_Rate": "WR (m/m)",
                "Delta_WR_%": "Δ WR %",
                "HMPD": "Hml (m)",
                "HMPD_per_Min": "Hml/m",
                "HSR": "HSR (m)",
                "HSR_per_Min": "HSR/m",
                "Max_Speed": "Vmax Med.",
                "Acc_Events": "Acc",
                "Dec_Events": "Dec",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    # =========================================================================
    # SEZIONE 2 — ARENA CONFRONTO MULTI-DRILL (POTENZIATA!)
    # =========================================================================
    st.markdown("<hr style='margin:22px 0; border-color:#CBD5E1;'>", unsafe_allow_html=True)
    arena_html = f"""
    <div style="background:linear-gradient(90deg, {FIR_AZZURO} 0%, {FIR_NAVY} 100%);
                border-left:4px solid {FIR_ORO}; border-radius:10px;
                padding:11px 16px; margin-bottom:14px;">
        <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF;">
            ⚖️ Arena Confronto Multi-Drill — Profili Normalizzati, Tempo &amp; Benchmark Δ%
        </div>
        <div style="font-size:0.78rem; color:#E0F2FE; margin-top:2px;">
            Confronta 2 o più esercitazioni diverse dell'intero archivio su <b>Durata, Volume e Intensità al Minuto</b>
            per la squadra intera o per uno specifico ruolo (<b>Σ Ruolo / N° Giocatori Attivi del Ruolo</b>).
        </div>
    </div>
    """
    st.markdown(_clean_html(arena_html), unsafe_allow_html=True)

    all_scope_opts = _get_scope_options(df_roles)
    ar_c1, ar_c2, ar_c3 = st.columns([2.2, 1.5, 1.5])
    with ar_c2:
        multi_scope = st.selectbox(
            "🎯 Ambito Confronto Multi-Drill",
            options=all_scope_opts,
            key="drill_bank_multi_scope",
        )

    bank_summary = _build_bank_catalog_scoped(df_master, df_roles, multi_scope)
    if bank_summary.empty:
        st.info(f"Nessun dato disponibile nel catalogo per **{multi_scope}**.")
        return

    avail_drills_cat = bank_summary["Drill_Name"].tolist()
    with ar_c1:
        compare_drills = st.multiselect(
            "Seleziona Drills da Confrontare (fino a 8)",
            options=avail_drills_cat,
            default=avail_drills_cat[: min(6, len(avail_drills_cat))],
            key="drill_bank_compare_multi",
        )
    with ar_c3:
        bench_opts = compare_drills if compare_drills else avail_drills_cat
        benchmark_drill = st.selectbox(
            "📌 Drill di Riferimento (Benchmark Δ%)",
            options=bench_opts,
            index=0,
            key="drill_bank_benchmark_drill",
        )

    fig_radar = None
    fig_bank_matrix = None
    fig_comp = None
    df_diff_table = pd.DataFrame()

    if len(compare_drills) >= 2:
        comp_df = bank_summary[bank_summary["Drill_Name"].isin(compare_drills)].copy()
        # Mantieni ordine selezionato
        order_sel = {d: i for i, d in enumerate(compare_drills)}
        comp_df["_ord"] = comp_df["Drill_Name"].map(lambda x: order_sel.get(x, 99))
        comp_df = comp_df.sort_values("_ord").drop(columns=["_ord"]).reset_index(drop=True)

        # 1. RADAR MULTI-METRICA (6 Assi Normalizzati 0-100) + 2. MAPPA DURATA × INTENSITÀ
        m_c1, m_c2 = st.columns(2)
        with m_c1:
            radar_axes = [
                ("Durata (min)", "Durata_Media"),
                ("Dist. (m)", "Dist_ProCapite"),
                ("Work Rate", "Work_Rate_Medio"),
                ("Hml/min", "Hml_per_Min"),
                ("HSR/min", "HSR_per_Min"),
                ("Vmax Media", "Max_Speed"),
            ]
            max_per_axis = {col: max(float(comp_df[col].max()), 1e-6) for _, col in radar_axes}
            theta_labels = [ax[0] for ax in radar_axes] + [radar_axes[0][0]]

            fig_radar = go.Figure()
            for idx_r, (_, row_d) in enumerate(comp_df.head(6).iterrows()):
                r_norm = [round(float(row_d[col]) / max_per_axis[col] * 100.0, 1) for _, col in radar_axes]
                r_raw = [float(row_d[col]) for _, col in radar_axes]
                r_norm.append(r_norm[0])
                r_raw.append(r_raw[0])
                col_hex = DRILL_PALETTE[idx_r % len(DRILL_PALETTE)]
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=r_norm,
                        theta=theta_labels,
                        fill="toself",
                        opacity=0.28,
                        line=dict(color=col_hex, width=2.5),
                        name=str(row_d["Drill_Name"]),
                        customdata=r_raw,
                        hovertemplate="<b>%{fullData.name}</b><br>%{theta}: %{customdata:.1f} (%{r:.0f}% del max)<extra></extra>",
                    )
                )
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 105], ticksuffix="%", gridcolor="#E2E8F0", tickfont=dict(size=9)),
                    angularaxis=dict(tickfont=dict(size=10.5, color=FIR_NAVY)),
                    bgcolor="#F8FAFC",
                ),
            )
            _apply_fir_plotly_layout(fig_radar, f"Profilo Multi-Metrica Drills (Radar 6 Assi · {multi_scope})", height=385)
            fig_radar.update_layout(hovermode="closest")
            st.plotly_chart(fig_radar, use_container_width=True)

        with m_c2:
            mat_y_choice = st.selectbox(
                "Asse Y Mappa Multi-Drill (Durata × Intensità)",
                options=["Work_Rate_Medio", "Hml_per_Min", "HSR_per_Min"],
                format_func=lambda k: {
                    "Work_Rate_Medio": "Work Rate Medio (m/min)",
                    "Hml_per_Min": "Hml/min (m/min)",
                    "HSR_per_Min": "HSR/min (>18 Av / >20 Tq)",
                }[k],
                key="drill_bank_matrix_y",
            )
            max_hml_b = max(float(comp_df["Hml_ProCapite"].max()), 1.0)
            sz_b = [max(16.0, float(v) / max_hml_b * 42.0) for v in comp_df["Hml_ProCapite"]]
            col_b = [DRILL_PALETTE[i % len(DRILL_PALETTE)] for i in range(len(comp_df))]

            fig_bank_matrix = go.Figure()
            fig_bank_matrix.add_trace(
                go.Scatter(
                    x=comp_df["Durata_Media"],
                    y=comp_df[mat_y_choice],
                    mode="markers+text",
                    marker=dict(size=sz_b, color=col_b, opacity=0.88, line=dict(color=FIR_NAVY, width=1.8)),
                    text=[f"<b>{d}</b>" for d in comp_df["Drill_Name"]],
                    textposition="top center",
                    textfont=dict(size=10.5, color=FIR_NAVY),
                    cliponaxis=False,
                    customdata=np.stack(
                        [comp_df["Dist_ProCapite"], comp_df["Hml_ProCapite"], comp_df["HSR_ProCapite"], comp_df["Esecuzioni"]],
                        axis=-1,
                    ),
                    hovertemplate=(
                        "<b>%{text}</b> (%{customdata[3]:.0f} sed.)<br>"
                        "Durata Media: %{x:.1f} min<br>"
                        "Intensità: %{y:.1f}<br>"
                        "Dist. Pro-Cap: %{customdata[0]:,.0f} m · Hml: %{customdata[1]:,.0f} m · HSR: %{customdata[2]:,.0f} m<extra></extra>"
                    ),
                    showlegend=False,
                )
            )
            fig_bank_matrix.add_vline(x=float(comp_df["Durata_Media"].mean()), line_dash="dash", line_color="#94A3B8", line_width=1.4)
            fig_bank_matrix.add_hline(y=float(comp_df[mat_y_choice].mean()), line_dash="dash", line_color="#94A3B8", line_width=1.4)
            bx_min, bx_max = float(comp_df["Durata_Media"].min()), float(comp_df["Durata_Media"].max())
            by_min, by_max = float(comp_df[mat_y_choice].min()), float(comp_df[mat_y_choice].max())
            bx_pad = max((bx_max - bx_min) * 0.25, 0.9)
            by_pad = max((by_max - by_min) * 0.32, 1.8)
            fig_bank_matrix.update_xaxes(title_text="Durata Media Drill (min)", range=[max(0.0, bx_min - bx_pad), bx_max + bx_pad])
            fig_bank_matrix.update_yaxes(title_text=mat_y_choice.replace("_", " "), range=[max(0.0, by_min - by_pad), by_max + by_pad * 1.35])
            _apply_fir_plotly_layout(fig_bank_matrix, "Mappa Durata × Intensità tra Drills (bolla = Hml)", height=365)
            fig_bank_matrix.update_layout(margin=dict(l=58, r=28, t=64, b=52), hovermode="closest")
            st.plotly_chart(fig_bank_matrix, use_container_width=True)

        # 3. CONFRONTO BARRE + TABELLA DIFFERENZIALE Δ% RISPETTO AL BENCHMARK
        comp_metric_map = (
            {
                "Dist_Totale_Medio": "Distanza Totale Media Gruppo/Ruolo (m)",
                "Hml_Totale_Medio": "Hml Totale Medio Gruppo/Ruolo (m)",
                "HSR_Totale_Medio": "HSR Totale Medio (>18/>20) (m)",
                "Work_Rate_Medio": "Work Rate Pro-Capite (m/min)",
                "Durata_Media": "Durata Media (min)",
            }
            if is_total_mode
            else {
                "Work_Rate_Medio": "Work Rate Pro-Capite (m/min)",
                "Hml_per_Min": "Hml/min Pro-Capite (m/min)",
                "HSR_per_Min": "HSR/min Pro-Capite (>18 Av / >20 Tq)",
                "Dist_ProCapite": "Distanza Pro-Capite (m)",
                "Hml_ProCapite": "Hml Pro-Capite (m)",
                "HSR_ProCapite": "HSR Pro-Capite (>18 Av / >20 Tq) (m)",
                "Durata_Media": "Durata Media (min)",
                "Max_Speed": "Max Speed Media (km/h)",
            }
        )
        comp_metric = st.selectbox(
            "Metrica Confronto a Barre Multi-Drill",
            options=list(comp_metric_map.keys()),
            format_func=lambda k: comp_metric_map[k],
            key=f"drill_bank_compare_metric_{is_total_mode}",
        )
        comp_sorted = comp_df.sort_values(by=comp_metric, ascending=False)
        comp_max_y = max(float(comp_sorted[comp_metric].max()), 1.0)
        fig_comp = go.Figure(
            go.Bar(
                x=comp_sorted["Drill_Name"],
                y=comp_sorted[comp_metric],
                marker=dict(
                    color=[FIR_ORO if d == benchmark_drill else FIR_AZZURO for d in comp_sorted["Drill_Name"]],
                    line=dict(color=FIR_NAVY, width=1.2),
                ),
                text=[f"<b>{v:,.1f}</b><br>({dur:.1f}')" for v, dur in zip(comp_sorted[comp_metric], comp_sorted["Durata_Media"])],
                textposition="outside",
                cliponaxis=False,
            )
        )
        _apply_fir_plotly_layout(
            fig_comp,
            f"Confronto Diretto Multi-Drill — {comp_metric_map[comp_metric]} (Oro = Benchmark '{benchmark_drill}')",
            height=365,
        )
        fig_comp.update_yaxes(range=[0, comp_max_y * 1.28])
        fig_comp.update_layout(showlegend=False)
        st.plotly_chart(fig_comp, use_container_width=True)

        # Tabella Differenziale Δ% vs Drill Benchmark
        bench_row_df = comp_df[comp_df["Drill_Name"] == benchmark_drill]
        if not bench_row_df.empty:
            br = bench_row_df.iloc[0]

            def _fmt_delta(val: float, ref: float, unit: str = "", dec: int = 1) -> str:
                if ref <= 0:
                    return f"{val:,.{dec}f}{unit}"
                dp = (val - ref) / ref * 100.0
                if abs(dp) < 0.05:
                    return f"{val:,.{dec}f}{unit} (rif.)"
                sgn = "+" if dp > 0 else ""
                return f"{val:,.{dec}f}{unit} ({sgn}{dp:.0f}%)"

            diff_rows = []
            for _, r in comp_df.iterrows():
                is_ref = r["Drill_Name"] == benchmark_drill
                lbl_d = f"⭐ {r['Drill_Name']}" if is_ref else str(r["Drill_Name"])
                diff_rows.append({
                    "Drill": lbl_d,
                    "Durata (min)": _fmt_delta(float(r["Durata_Media"]), float(br["Durata_Media"]), "'", 1),
                    "Dist. Pro-Cap": _fmt_delta(float(r["Dist_ProCapite"]), float(br["Dist_ProCapite"]), "m", 0),
                    "Work Rate": _fmt_delta(float(r["Work_Rate_Medio"]), float(br["Work_Rate_Medio"]), "", 1),
                    "Hml (m)": _fmt_delta(float(r["Hml_ProCapite"]), float(br["Hml_ProCapite"]), "m", 0),
                    "Hml/min": _fmt_delta(float(r["Hml_per_Min"]), float(br["Hml_per_Min"]), "", 1),
                    "HSR (>18/>20)": _fmt_delta(float(r["HSR_ProCapite"]), float(br["HSR_ProCapite"]), "m", 0),
                    "HSR/min": _fmt_delta(float(r["HSR_per_Min"]), float(br["HSR_per_Min"]), "", 1),
                    "Vmax Med.": _fmt_delta(float(r["Max_Speed"]), float(br["Max_Speed"]), "", 1),
                })
            df_diff_table = pd.DataFrame(diff_rows)
            st.markdown(
                f"<div style='font-size:0.88rem; font-weight:800; color:{FIR_NAVY}; margin:6px 0;'>📊 Tabella Differenziale Multi-Drill (Δ% rispetto a ⭐ {benchmark_drill} · {multi_scope})</div>",
                unsafe_allow_html=True,
            )
            st.dataframe(df_diff_table, use_container_width=True, hide_index=True)
    else:
        st.info("ℹ️ Seleziona almeno **2 drills** nel selettore sopra (o archivia almeno 2 drills diversi) per attivare il Radar 6 assi, la Mappa Durata×Intensità e il Benchmark Δ%.")

    # Catalogo Completo Drill Bank
    st.markdown(
        f"<div style='font-size:0.9rem; font-weight:800; color:{FIR_NAVY}; margin:10px 0 6px 0;'>📚 Catalogo Completo Drill Bank — {multi_scope} ({len(bank_summary)} drills)</div>",
        unsafe_allow_html=True,
    )
    df_cat_disp = bank_summary[[
        "Drill_Name", "Esecuzioni", "Ultima_Data", "Attivi_Medi", "Durata_Media",
        "Dist_ProCapite", "Work_Rate_Medio", "Hml_ProCapite", "Hml_per_Min",
        "HSR_ProCapite", "HSR_per_Min", "Max_Speed", "Max_Speed_Peak",
    ]].rename(
        columns={
            "Drill_Name": "Drill",
            "Esecuzioni": "Sed.",
            "Ultima_Data": "Ultima Data",
            "Attivi_Medi": "Attivi Med.",
            "Durata_Media": "Dur. (min)",
            "Dist_ProCapite": "Dist. (m)",
            "Work_Rate_Medio": "WR (m/m)",
            "Hml_ProCapite": "Hml (m)",
            "Hml_per_Min": "Hml/m",
            "HSR_ProCapite": "HSR (m)",
            "HSR_per_Min": "HSR/m",
            "Max_Speed": "Vmax Med.",
            "Max_Speed_Peak": "Vmax Picco",
        }
    )
    st.dataframe(df_cat_disp, use_container_width=True, hide_index=True)

    # =========================================================================
    # ACTION BAR TAB 2 — ESPORTAZIONE PDF COMPLETA DRILL BANK & CSV
    # =========================================================================
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    b_act1, b_act2, b_act3 = st.columns([1.5, 1.0, 1.0])
    bank_pdf_key = f"drills_bank_pdf_{selected_drill}_{selected_scope}_{is_total_mode}_{multi_scope}_{benchmark_drill}_{len(compare_drills)}"

    with b_act1:
        if st.button(
            "📄 Genera Report PDF Drill Bank & Confronto Multi-Drill",
            type="primary",
            use_container_width=True,
            key="btn_gen_pdf_drill_bank",
        ):
            with st.spinner("Generazione PDF FIR Drill Bank con grafici longitudinali, Radar, Mappa e Catalogo..."):
                pdf_b = drills_pdf.crea_pdf_drill_bank(
                    selected_drill=selected_drill,
                    scope_label=selected_scope,
                    is_total_mode=is_total_mode,
                    kpis=kpis_bank,
                    df_hist=df_hist_view,
                    fig_long=fig_long,
                    fig_hi=fig_hi,
                    multi_scope_label=multi_scope,
                    benchmark_drill=benchmark_drill,
                    fig_radar=fig_radar,
                    fig_bank_matrix=fig_bank_matrix,
                    fig_comp=fig_comp,
                    df_diff=df_diff_table if not df_diff_table.empty else None,
                    df_catalog=df_cat_disp,
                )
                st.session_state["drills_bank_pdf_payload"] = (bank_pdf_key, pdf_b)

        cached_bpdf = st.session_state.get("drills_bank_pdf_payload")
        if cached_bpdf and cached_bpdf[0] == bank_pdf_key:
            st.download_button(
                "⬇️ Scarica Report PDF Drill Bank (.pdf)",
                data=cached_bpdf[1],
                file_name=f"FIR_DrillBank_{_slug(selected_drill)}_{_slug(selected_scope)}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_drill_bank_pdf",
            )

    with b_act2:
        csv_drill = df_d.drop(
            columns=[
                "Exec_Label", "Dynamic_Stress_Load", "DSL_per_Min",
                "Dynamic_Stress_Load_Sum", "Avanti_DSL", "Trequarti_DSL",
                "Avanti_DSL_Sum", "Trequarti_DSL_Sum",
                "Heavy_Impacts", "Heavy_Impacts_Sum",
            ],
            errors="ignore",
        ).rename(
            columns={"HMPD": "Hml_m", "HMPD_per_Min": "Hml_per_Min", "HMPD_Sum": "Hml_Sum_m"}
        ).to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            f"⬇️ CSV Storico ({selected_drill[:18]})",
            data=csv_drill,
            file_name=f"FIR_DrillBank_{_slug(selected_drill)}.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_drill_bank_single_csv",
        )

    with b_act3:
        csv_cat = df_cat_disp.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⬇️ CSV Catalogo Drill Bank",
            data=csv_cat,
            file_name=f"FIR_DrillBank_Catalogo_{_slug(multi_scope)}.csv",
            mime="text/csv",
            use_container_width=True,
            key="dl_drill_bank_catalog_csv",
        )


def render_analisi_drills(t=None):
    """Entrypoint principale della vista '🧩 Analisi & Confronto Drills'."""
    render_page_header(
        "🧩 Analisi & Confronto Drills",
        "Confronto diretto tra Drills (Volume, Tempo, Intensità al Minuto) · Hml (>25.5W) · HSR FIR (>18 km/h Avanti / >20 km/h Trequarti) · Report PDF",
    )

    user_role = st.session_state.get("user_role", "viewer")
    is_admin = user_role == "admin"

    df_master = drills_manager.load_drills_master()
    df_roles = drills_manager.load_drills_roles_summary()
    df_players = drills_manager.load_drills_players_detail()

    active_tab = render_tab_navigation(
        "analisi_drills_tabs",
        [
            ("sessione", "📂 Gestione & Confronto Drills Seduta", "bi-layers-fill"),
            ("drill_bank", "🔍 Drill Bank & Arena Multi-Drill", "bi-database-fill-gear"),
        ],
    )

    if active_tab == "sessione":
        _render_tab_sessione(df_master, df_roles, df_players, is_admin=is_admin)
    else:
        _render_tab_drill_bank(df_master, df_roles)
