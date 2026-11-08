import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from config import render_page_header, RUGBY_ROLES, ROLE_TO_DEPT
import utils
import global_state


def _safe_int(v, default=0) -> int:
    try:
        if v is None or pd.isna(v) or np.isnan(v):
            return default
        return int(round(float(v)))
    except Exception:
        return default


def _safe_float(v, default=0.0) -> float:
    try:
        if v is None or pd.isna(v) or np.isnan(v):
            return default
        return float(v)
    except Exception:
        return default


def render_dashboard_home(t: dict):
    render_page_header(
        "Cruscotto Esecutivo Nazionale FIR",
        "Panoramica operativa della giornata per la Nazionale Italiana Maggiore • Status raduno, carico seduta odierna e focus match",
        "bi-house-door-fill",
    )

    # 1. Caricamento dati esclusivi della Nazionale Italiana
    hist_naz = utils.get_gps_history_df("nazionale")
    if hist_naz.empty:
        st.info("Nessun dato GPS registrato per la Nazionale Italiana.")
        return

    ctx = global_state.get_current_session_context(hist_naz)
    sub_sess = ctx["sub_gps_sess"]
    sub_day = ctx["sub_gps_day"]
    sub_week = ctx["sub_gps_week"]
    camp_players = ctx["camp_players"]
    meta = ctx["meta"]
    match_info = ctx["match_info"]

    camp_name = meta.get("camp_name", "Nazionale Maggiore")
    week_range = meta.get("week_range", "")
    sess_date = meta.get("session_date", str(datetime.date.today()))
    sess_name = meta.get("session_name", "Seduta Attiva")
    archetype = meta.get("session_archetype", "Standard")

    # --------------------------------------------------------------------------
    # BANNER DI TESTATA: STATO ATTIVO NAZIONALE
    # --------------------------------------------------------------------------
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, #002B49 0%, #004D7A 60%, #0066B2 100%); border:2px solid #D4AF37; border-radius:14px; padding:16px 20px; margin-bottom:18px; color:#FFFFFF; box-shadow:0 6px 18px rgba(0,0,0,0.20);">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
                <div>
                    <div style="font-size:0.72rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">RADUNO NAZIONALE ATTIVO</div>
                    <div style="font-size:1.6rem; font-weight:900; color:#FFFFFF; margin:2px 0;">{camp_name}</div>
                    <div style="font-size:0.80rem; color:#BAE6FD;">Periodo Settimana: <b>{week_range}</b> &bull; Data Seduta: <b>{sess_date}</b></div>
                </div>
                <div style="display:flex; gap:10px; align-items:center;">
                    <div style="background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.20); border-radius:10px; padding:8px 14px; text-align:right;">
                        <div style="font-size:0.68rem; color:#93C5FD; text-transform:uppercase; font-weight:700;">Seduta Analizzata</div>
                        <div style="font-size:1.05rem; font-weight:800; color:#FFFFFF;">{sess_name}</div>
                        <div style="font-size:0.70rem; color:#FDE68A;">Tipologia: <b>{archetype}</b></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------------------------
    # SEZIONE 1: STATUS ATLETI IN RADUNO OGGI
    # --------------------------------------------------------------------------
    n_tot_camp = len(camp_players) if not camp_players.empty else len(sub_sess["player_name"].unique()) if not sub_sess.empty else 0

    # Status degli atleti da session_player_status
    status_map = utils.get_session_player_statuses()
    sess_status = status_map.get(f"{sess_date}_{sess_name}", status_map.get(sess_name, {}))

    cnt_full = 0
    cnt_mod = 0
    cnt_rtp = 0
    cnt_off = 0
    mod_players = []
    rtp_players = []
    off_players = []

    if not camp_players.empty:
        for _, cp in camp_players.iterrows():
            pnm = str(cp.get("player_name") or "")
            st_val = sess_status.get(pnm, "Full").upper()
            if st_val in ("MODIFICATO", "MODIFIED"):
                cnt_mod += 1
                mod_players.append(pnm)
            elif st_val == "RTP":
                cnt_rtp += 1
                rtp_players.append(pnm)
            elif st_val in ("OFF FEET", "NON ATTIVO"):
                cnt_off += 1
                off_players.append(pnm)
            else:
                cnt_full += 1
    else:
        cnt_full = n_tot_camp

    st.markdown("### 1. Monitoraggio Disponibilità Atleti (Oggi)")
    k1, k2, k3, k4, k5 = st.columns(5)

    k1.metric("Totale in Raduno", f"{n_tot_camp} Atleti")
    k2.metric("Regolari (Full)", f"{cnt_full}", delta="Disponibili 100%")
    k3.metric("Modificato", f"{cnt_mod}", delta="Carico ridotto" if cnt_mod > 0 else None, delta_color="off")
    k4.metric("RTP (Differenziato)", f"{cnt_rtp}", delta="In recupero" if cnt_rtp > 0 else None, delta_color="off")
    k5.metric("Off Feet (A Riposo)", f"{cnt_off}", delta="Esclusi" if cnt_off > 0 else None, delta_color="inverse")

    if mod_players or rtp_players or off_players:
        with st.expander("Dettaglio Atleti con Allenamento Modificato o Differenziato", expanded=False):
            c_m1, c_m2, c_m3 = st.columns(3)
            if mod_players:
                c_m1.markdown(f"**Modificato ({len(mod_players)}):** " + ", ".join(mod_players))
            if rtp_players:
                c_m2.markdown(f"**RTP ({len(rtp_players)}):** " + ", ".join(rtp_players))
            if off_players:
                c_m3.markdown(f"**Off Feet ({len(off_players)}):** " + ", ".join(off_players))

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SEZIONE 2: METRICHE CHIAVE DELLA SEDUTA ODIERNA (AVANTI vs TREQUARTI)
    # --------------------------------------------------------------------------
    st.markdown("### 2. Carico & Intensità Seduta Odierna (Nazionale Italiana)")

    dur_val = _safe_float(sub_sess["duration"].mean()) if not sub_sess.empty and "duration" in sub_sess.columns else 0.0
    fw_roles = set(RUGBY_ROLES[:5])
    sub_fw = sub_sess[sub_sess["role"].isin(fw_roles)] if ("role" in sub_sess.columns and not sub_sess.empty) else pd.DataFrame()
    sub_bk = sub_sess[~sub_sess["role"].isin(fw_roles)] if ("role" in sub_sess.columns and not sub_sess.empty) else pd.DataFrame()

    dt_fw = _safe_int(sub_fw["distance_m"].mean()) if not sub_fw.empty and "distance_m" in sub_fw.columns else 0
    dt_bk = _safe_int(sub_bk["distance_m"].mean()) if not sub_bk.empty and "distance_m" in sub_bk.columns else 0

    hml_fw = _safe_int(sub_fw["mp_25_35"].mean()) if not sub_fw.empty and "mp_25_35" in sub_fw.columns else 0
    hml_bk = _safe_int(sub_bk["mp_25_35"].mean()) if not sub_bk.empty and "mp_25_35" in sub_bk.columns else 0

    # Top Speed odierna
    top_speed_val = 0.0
    top_speed_player = "--"
    if not sub_sess.empty and "v_max" in sub_sess.columns:
        vmax_rows = sub_sess[sub_sess["v_max"] > 0].sort_values("v_max", ascending=False)
        if not vmax_rows.empty:
            top_speed_val = _safe_float(vmax_rows.iloc[0]["v_max"])
            top_speed_player = str(vmax_rows.iloc[0]["player_name"])

    c_g1, c_g2, c_g3, c_g4 = st.columns(4)

    with c_g1:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #0284C7; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#0369A1; text-transform:uppercase;">DURATA SEDUTA</div>
                <div style="font-size:1.6rem; font-weight:900; color:#0F172A; margin:4px 0;">{_safe_int(dur_val)}' min</div>
                <div style="font-size:0.75rem; color:#64748B;">Volume temporale effettivo</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_g2:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #16A34A; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#15803D; text-transform:uppercase;">DISTANZA MEDIA REPARTI</div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                    <div><span style="font-size:0.70rem; color:#64748B;">Avanti:</span> <b style="font-size:1.15rem; color:#0F172A;">{dt_fw:,} m</b></div>
                    <div><span style="font-size:0.70rem; color:#64748B;">Trequarti:</span> <b style="font-size:1.15rem; color:#0284C7;">{dt_bk:,} m</b></div>
                </div>
                <div style="font-size:0.72rem; color:#64748B; margin-top:4px;">Volume totale medio percorso</div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    with c_g3:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #D97706; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#B45309; text-transform:uppercase;">INTENSITÀ (HML &gt;25.5W)</div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                    <div><span style="font-size:0.70rem; color:#64748B;">Avanti:</span> <b style="font-size:1.15rem; color:#0F172A;">{hml_fw:,} m</b></div>
                    <div><span style="font-size:0.70rem; color:#64748B;">Trequarti:</span> <b style="font-size:1.15rem; color:#D97706;">{hml_bk:,} m</b></div>
                </div>
                <div style="font-size:0.72rem; color:#64748B; margin-top:4px;">Metri ad alta potenza metabolica</div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    with c_g4:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #9333EA; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#7E22CE; text-transform:uppercase;">TOP SPEED ODIERNA</div>
                <div style="font-size:1.55rem; font-weight:900; color:#0F172A; margin:4px 0;">{_safe_float(top_speed_val):.1f} km/h</div>
                <div style="font-size:0.75rem; color:#7E22CE; font-weight:700;">{top_speed_player}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SEZIONE 3: PROSSIMA PARTITA UFFICIALE & FORMAZIONE (1-23)
    # --------------------------------------------------------------------------
    st.markdown("### 3. Focus Prossimo Match Internazionale")
    m_col1, m_col2 = st.columns([1.8, 1.2])

    target_match = match_info.get("match_name", "GIAPPONE - ITALIA")
    target_comp = match_info.get("competition", "Nations Championship 2026")
    target_date = match_info.get("match_date", "2026-07-04")

    # Lineup details
    lineup_detail = utils.get_match_lineup_detail(target_date)
    starters = lineup_detail.get("starters", pd.DataFrame())
    finishers = lineup_detail.get("finishers", pd.DataFrame())
    n_lineup = len(starters) + len(finishers)

    with m_col1:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #002B49; border-radius:14px; padding:16px; box-shadow:0 4px 14px rgba(0,43,73,0.12);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.72rem; font-weight:800; color:#D4AF37; text-transform:uppercase; letter-spacing:0.08em;">PARTITA INTERNAZIONALE IN PROGRAMMA</span>
                    <span style="background:#0284C7; color:#FFFFFF; font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px;">{target_comp}</span>
                </div>
                <div style="font-size:1.5rem; font-weight:900; color:#002B49; margin-bottom:4px;">{target_match}</div>
                <div style="font-size:0.80rem; color:#475569; margin-bottom:12px;">Data Gara: <b>{target_date}</b> &bull; Formazione: <b>{n_lineup}/23 Atleti Ufficiali Assegnati</b></div>
                <div style="display:flex; gap:10px;">
                    <span style="background:#ECFDF5; color:#065F46; font-size:0.75rem; font-weight:700; padding:3px 10px; border-radius:6px;">{len(starters)} Titolari (1–15)</span>
                    <span style="background:#EFF6FF; color:#1E40AF; font-size:0.75rem; font-weight:700; padding:3px 10px; border-radius:6px;">{len(finishers)} Finishers (16–23)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with m_col2:
        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:14px; padding:16px; height:100%; display:flex; flex-direction:column; justify-content:space-between;">
                <div>
                    <div style="font-size:0.72rem; font-weight:800; color:#0F172A; text-transform:uppercase; margin-bottom:6px;">Accesso Rapido Formazione</div>
                    <div style="font-size:0.78rem; color:#64748B;">Visualizza lo schieramento tattico in campo con foto ufficiali e minutaggi della partita.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("📋 Vai allo Schieramento Campo (1-23)", use_container_width=True, type="primary", key="btn_home_to_lineup"):
            st.session_state["active_page"] = "analisi_sessione_giornata"
            st.session_state["active_subtab_analisi_sessione_giornata"] = "campo"
            st.session_state["_scroll_top_counter"] = st.session_state.get("_scroll_top_counter", 0) + 1
            st.rerun()

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SEZIONE 4: WORKLOAD DELLA SETTIMANA IN CORSO (SOLO NAZIONALE)
    # --------------------------------------------------------------------------
    if not sub_week.empty:
        st.markdown("### 4. Progressione Carichi della Settimana (Nazionale Italiana)")
        # Raggruppamento per data/seduta
        week_grp = sub_week.groupby("date_str", as_index=False).agg(
            distanza_tot=("distance_m", "sum"),
            hml_tot=("mp_25_35", "sum"),
            atleti_count=("player_name", "nunique"),
        )
        week_grp = week_grp.sort_values("date_str")

        fig_w = go.Figure()
        fig_w.add_trace(
            go.Bar(
                x=week_grp["date_str"],
                y=week_grp["distanza_tot"],
                name="Volume Totale Squadra (m)",
                marker_color="#0066B2",
                opacity=0.90,
                hovertemplate="<b>%{x}</b><br>Volume: %{y:,.0f} m<extra></extra>",
            )
        )
        fig_w.update_layout(
            height=260,
            margin=dict(l=40, r=30, t=20, b=40),
            plot_bgcolor="#F8FAFC",
            paper_bgcolor="#FFFFFF",
            font=dict(family="Inter", size=11),
            yaxis=dict(title="Metri Percorsi (Squadra)", gridcolor="#E2E8F0"),
            xaxis=dict(gridcolor="#E2E8F0"),
        )
        st.plotly_chart(fig_w, use_container_width=True)

    # --------------------------------------------------------------------------
    # SEZIONE 5: HUB DI NAVIGAZIONE RAPIDA
    # --------------------------------------------------------------------------
    st.markdown("### 5. Sezioni Principali della Piattaforma")
    n1, n2, n3 = st.columns(3)

    with n1:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.1rem; font-weight:800; color:#002B49; margin-bottom:4px;">⏱️ Analisi GPS Sessione & Giornata</div>
                <div style="font-size:0.75rem; color:#64748B;">Report Sessione, Storytelling, Istogramma, Target HML/HSR, Trombinoscopio e Scheda Giocatori.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Analisi Sessione / Giornata", key="btn_hub_sess", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_sessione_giornata"
            st.session_state["active_subtab_analisi_sessione_giornata"] = "story"
            st.rerun()

    with n2:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.1rem; font-weight:800; color:#002B49; margin-bottom:4px;">🗓️ Analisi GPS Settimana</div>
                <div style="font-size:0.75rem; color:#64748B;">Report Settimana, 23 Convocati, Semaforo Vmax, Densità HML/HSR e Report 6/12 Weeks.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Analisi Settimana", key="btn_hub_week", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_settimana"
            st.session_state["active_subtab_analisi_settimana"] = "report_settimana"
            st.rerun()

    with n3:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.1rem; font-weight:800; color:#002B49; margin-bottom:4px;">👤 Analisi Individuale Atleta</div>
                <div style="font-size:0.75rem; color:#64748B;">Passaporto Unificato Atleta 21gg e Scheda Storica Carriera Oval (Caps & Minuti).</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Analisi Individuale", key="btn_hub_indiv", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_individuale"
            st.session_state["active_subtab_analisi_individuale"] = "gps_atleta"
            st.rerun()
