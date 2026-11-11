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
    raw_sess_date = meta.get("session_date") or meta.get("date_str") or ""
    sess_date = raw_sess_date if raw_sess_date and raw_sess_date != "--" else "In attesa seduta"
    raw_sess_name = meta.get("session_name") or ""
    if not raw_sess_name or raw_sess_name == "Nessuna seduta registrata":
        sess_name = "Nessuna Seduta"
        archetype = meta.get("session_archetype") or meta.get("session_type") or "Standard"
    else:
        sess_name = raw_sess_name
        archetype = meta.get("session_archetype") or meta.get("session_type") or "Standard"

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

    has_valid_gps = False
    dur_val = 0.0
    dt_fw = 0
    dt_bk = 0
    hml_fw = 0
    hml_bk = 0
    top_speed_val = 0.0
    top_speed_player = "--"

    if not sub_sess.empty and "distance_m" in sub_sess.columns:
        sub_clean = sub_sess.copy()
        for col_n in ["duration", "distance_m", "mp_25_35", "v_max"]:
            if col_n in sub_clean.columns:
                sub_clean[col_n] = pd.to_numeric(sub_clean[col_n], errors="coerce").fillna(0.0)

        # Reparto Avanti vs TreQuarti assegnato rigorosamente con la funzione ufficiale FIR
        sub_clean["department"] = sub_clean.apply(
            lambda r: utils.get_player_department(r.get("player_name"), r.get("role")), axis=1
        )
        sub_fw = sub_clean[sub_clean["department"] == "Avanti"]
        sub_bk = sub_clean[sub_clean["department"] == "TreQuarti"]

        dt_fw = _safe_int(sub_fw["distance_m"].mean()) if not sub_fw.empty else 0
        dt_bk = _safe_int(sub_bk["distance_m"].mean()) if not sub_bk.empty else 0
        dur_val = _safe_float(sub_clean["duration"].mean()) if "duration" in sub_clean.columns else 0.0
        hml_fw = _safe_int(sub_fw["mp_25_35"].mean()) if not sub_fw.empty and "mp_25_35" in sub_fw.columns else 0
        hml_bk = _safe_int(sub_bk["mp_25_35"].mean()) if not sub_bk.empty and "mp_25_35" in sub_bk.columns else 0

        if "v_max" in sub_clean.columns:
            vmax_pos = sub_clean[sub_clean["v_max"] > 1.0]
            if not vmax_pos.empty:
                best_row = vmax_pos.sort_values("v_max", ascending=False).iloc[0]
                top_speed_val = _safe_float(best_row["v_max"])
                top_speed_player = str(best_row.get("player_name") or "--")

        if dur_val > 0 or dt_fw > 0 or dt_bk > 0 or top_speed_val > 0:
            has_valid_gps = True

    if not has_valid_gps:
        st.info(f"ℹ️ Nessun dato GPS registrato per la seduta selezionata (<b>{sess_name}</b>). I carichi e le velocità verranno calcolati automaticamente non appena verrà caricato il file GPS.", icon="ℹ️")

    c_g1, c_g2, c_g3, c_g4 = st.columns(4)

    with c_g1:
        dur_str = f"{_safe_int(dur_val)}' min" if has_valid_gps else "-- min"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #0284C7; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#0369A1; text-transform:uppercase;">DURATA SEDUTA</div>
                <div style="font-size:1.6rem; font-weight:900; color:#0F172A; margin:4px 0;">{dur_str}</div>
                <div style="font-size:0.75rem; color:#64748B;">Volume temporale effettivo</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_g2:
        fw_dist_str = f"{dt_fw:,} m".replace(",", ".") if has_valid_gps else "-- m"
        bk_dist_str = f"{dt_bk:,} m".replace(",", ".") if has_valid_gps else "-- m"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #16A34A; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#15803D; text-transform:uppercase;">DISTANZA MEDIA REPARTI</div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                    <div><span style="font-size:0.70rem; color:#64748B;">Avanti:</span> <b style="font-size:1.15rem; color:#0F172A;">{fw_dist_str}</b></div>
                    <div><span style="font-size:0.70rem; color:#64748B;">Trequarti:</span> <b style="font-size:1.15rem; color:#0284C7;">{bk_dist_str}</b></div>
                </div>
                <div style="font-size:0.72rem; color:#64748B; margin-top:4px;">Volume totale medio percorso</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_g3:
        fw_hml_str = f"{hml_fw:,} m".replace(",", ".") if has_valid_gps else "-- m"
        bk_hml_str = f"{hml_bk:,} m".replace(",", ".") if has_valid_gps else "-- m"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #D97706; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#B45309; text-transform:uppercase;">INTENSITÀ (HML &gt;25.5W)</div>
                <div style="display:flex; justify-content:space-between; align-items:baseline; margin-top:4px;">
                    <div><span style="font-size:0.70rem; color:#64748B;">Avanti:</span> <b style="font-size:1.15rem; color:#0F172A;">{fw_hml_str}</b></div>
                    <div><span style="font-size:0.70rem; color:#64748B;">Trequarti:</span> <b style="font-size:1.15rem; color:#D97706;">{bk_hml_str}</b></div>
                </div>
                <div style="font-size:0.72rem; color:#64748B; margin-top:4px;">Metri ad alta potenza metabolica</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_g4:
        vmax_str = f"{_safe_float(top_speed_val):.1f} km/h" if has_valid_gps and top_speed_val > 0 else "-- km/h"
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #9333EA; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="font-size:0.75rem; font-weight:800; color:#7E22CE; text-transform:uppercase;">TOP SPEED ODIERNA</div>
                <div style="font-size:1.55rem; font-weight:900; color:#0F172A; margin:4px 0;">{vmax_str}</div>
                <div style="font-size:0.75rem; color:#7E22CE; font-weight:700;">{top_speed_player}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # SEZIONE 3: HUB DI NAVIGAZIONE RAPIDA
    # --------------------------------------------------------------------------
    st.markdown("### 3. Sezioni Principali della Piattaforma")
    n1, n2, n3, n4 = st.columns(4)

    with n1:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.05rem; font-weight:800; color:#002B49; margin-bottom:4px;">⏱️ Analisi Sessione</div>
                <div style="font-size:0.75rem; color:#64748B;">Report Sessione, Storytelling, Istogramma, Target HML/HSR e Trombinoscopio.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Sessione", key="btn_hub_sess", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_sessione_giornata"
            st.session_state["active_subtab_analisi_sessione_giornata"] = "story"
            st.rerun()

    with n2:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.05rem; font-weight:800; color:#002B49; margin-bottom:4px;">🗓️ Analisi Settimana</div>
                <div style="font-size:0.75rem; color:#64748B;">Report Settimana, 23 Convocati, Semaforo Vmax, Densità e Report 6/12 Weeks.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Settimana", key="btn_hub_week", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_settimana"
            st.session_state["active_subtab_analisi_settimana"] = "report_settimana"
            st.rerun()

    with n3:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.05rem; font-weight:800; color:#002B49; margin-bottom:4px;">👤 Analisi Individuale</div>
                <div style="font-size:0.75rem; color:#64748B;">Passaporto Unificato Atleta 21gg e Scheda Storica Carriera Oval (Caps & Minuti).</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri Individuale", key="btn_hub_indiv", use_container_width=True, type="secondary"):
            st.session_state["active_page"] = "analisi_individuale"
            st.session_state["active_subtab_analisi_individuale"] = "gps_atleta"
            st.rerun()

    with n4:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:14px; min-height:120px;">
                <div style="font-size:1.05rem; font-weight:800; color:#002B49; margin-bottom:4px;">🏋️ Palestra & GymAware</div>
                <div style="font-size:0.75rem; color:#64748B;">Classifiche VBT, Velocità, Potenza, Stima 1RM e Analisi Rep-by-Rep.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Apri GymAware (VBT)", key="btn_hub_gymaware", use_container_width=True, type="primary"):
            st.session_state["active_page"] = "palestra_gymaware"
            st.session_state["active_subtab_palestra_gymaware"] = "squadra_ranking"
            st.rerun()
