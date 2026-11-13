# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import re
import datetime
import streamlit as st
import pandas as pd
import numpy as np
from config import render_page_header, render_tab_navigation, render_navigation_cards, FIR_COLUMNS_META, FIR_COL_LABELS, RUGBY_ROLES, DEPARTMENTS, ROLE_TO_DEPT
import utils


AUTO_ALIASES = {
    "player_name": ["name", "athlete", "player", "giocatore", "atleta", "player name", "athlete name", "cognome nome"],
    "sigla": ["sigla", "code", "initials", "codice"],
    "session_name": ["z", "session", "nome seduta", "session name", "activity name", "drill", "allenamento"],
    "date": ["data", "date", "session date", "giorno data", "start date"],
    "day_name": ["giorno", "day", "day name", "weekday"],
    "role": ["ruolo", "role", "position", "position name", "reparto"],
    "period": ["periodo", "period", "period name", "blocco", "split"],
    "profile_max_vel": ["profile max velocity (km/h)", "profile max vel", "vmax profilo"],
    "v_max_pct": ["v max (% max)", "max speed% (%)", "% v max", "pct max speed"],
    "duration": ["durata", "duration", "total time", "total duration", "time (min)", "durata (min)"],
    "distance_m": ["distanza (m)", "distance (m)", "total distance", "total distance (m)", "distanza", "distance"],
    "m_per_min": ["m\\min", "m/min", "meterage per minute", "metri/min", "avg speed (m/min)"],
    "mp_0_12": ["mp 0 - 12 w (m)", "mp 0-12 w"],
    "mp_12_20": ["mp 12 -20 w (m)", "mp 12-20 w"],
    "mp_20_25": ["mp 20 - 25,5 w (m)", "mp 20-25.5 w"],
    "mp_25_35": ["mp 25,5 - 35 w (m)", "mp 25.5-35 w", "hml >25w", "hmld"],
    "mp_35_50": ["mp 35 - 50 w (m)", "mp 35-50 w"],
    "mp_50_100": ["mp 50 - 100 w (m)", "mp 50-100 w"],
    "ai_12_20": ["a,i, 12-20 w", "ai 12-20 w"],
    "ai_20_25": ["a,i, 20-25,5 w", "ai 20-25.5 w"],
    "ai_25_40": ["a,i, 25,5-40 w", "ai 25.5-40 w"],
    "ai_40_50": ["a,i, 40-50 w", "ai 40-50 w"],
    "ai_50_100": ["a,i, 50-100 w", "ai 50-100 w"],
    "v_max": ["v max (km/h)", "max speed (km/h)", "maximum velocity", "max vel", "v max", "peak speed"],
    "speed_0_6": ["velocità 0-6 km\\h (m)", "vel 0-6"],
    "speed_6_15": ["velocità 6-15 km\\h (m)", "vel 6-15"],
    "speed_15_18": ["velocità 15-18 km\\h (m)", "vel 15-18"],
    "speed_18_20": ["velocità 18-20 km\\h (m)", "vel 18-20", "hsr >18"],
    "speed_20_25": ["velocità 20-25 km\\h (m)", "vel 20-25", "hsr>20", "velocity band 5 total distance"],
    "speed_25_72": ["velocità 25-72 km\\h (m)", "vel 25-72", "vhsr>25", "velocity band 6 total distance"],
    "actions_gt_6": ["azioni >6 km\\h", "azioni >6"],
    "actions_gt_15": ["azioni >15km\\h", "azioni >15"],
    "actions_gt_18": ["azioni >18km\\h", "azioni >18"],
    "actions_gt_20": ["azioni >20km\\h", "azioni >20"],
    "actions_gt_25": ["azioni >25km\\h", "azioni >25"],
    "acc_volume": ["volume acc", "acc volume", "total accelerations"],
    "acc_density_time": ["densità acc\\tempo", "acc density time"],
    "acc_density_space": ["densità acc\\spazio", "acc density space"],
    "contacts": ["contatti", "contacts", "impacts", "collisions"],
    "rhie_avg_recovery": ["rhie recupero medio", "rhie avg recovery"],
    "rhie_total": ["rhie totali", "rhie total"],
    "jump_20_40": ["jump 20-40cm", "jump 20-40"],
    "jump_gt_40": ["jump >40cm", "jump >40"],
    "cod_right": ["cod intensi destra", "cod right"],
    "cod_left": ["cod intensi sinistra", "cod left"],
    "player_load_total": ["player load totale", "total player load", "player load", "playerload"],
    "actions_gt_70": ["azioni >70%"],
    "actions_gt_85": ["azioni >85%"],
}


def _clean_str(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _auto_detect_col(fir_col: str, file_cols: list, saved_map: dict) -> str:
    if fir_col in saved_map and saved_map[fir_col] in file_cols:
        return saved_map[fir_col]
    cands = AUTO_ALIASES.get(fir_col, [])
    norm_file = {_clean_str(c): c for c in file_cols}
    for cand in cands:
        if cand in norm_file:
            return norm_file[cand]
    for f_norm, orig_c in norm_file.items():
        for cand in cands:
            if cand == f_norm or (len(cand) > 4 and cand in f_norm):
                return orig_c
    return "-- Nessuna --"


def _parse_duration_val(val):
    if pd.isna(val) or val is None or str(val).strip() == "":
        return np.nan
    if isinstance(val, (int, float)):
        if 0 < val < 1:
            return round(float(val) * 24.0 * 60.0, 2)
        return round(float(val), 2)
    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return round(float(parts[0]) + float(parts[1]) / 60.0, 2)
            elif len(parts) == 3:
                return round(float(parts[0]) * 60.0 + float(parts[1]) + float(parts[2]) / 60.0, 2)
        except Exception:
            return np.nan
    try:
        return round(float(s.replace(",", ".")), 2)
    except Exception:
        return np.nan


def _render_gps_quality_check(df_check: pd.DataFrame):
    """
    Controllo Qualità Automatico ('Alert Anomalie GPS') in fase di importazione:
    Verifica spike di Vmax (>37.5 km/h), Vmax% (>103% del Roster), m/min anomali (>155),
    durata <= 0 con distanza > 0, e giocatori non ancora censiti nel Roster FIR.
    """
    if df_check is None or df_check.empty:
        return

    players_df = utils.get_players_df()
    roster_vmax_map = {}
    roster_names_norm = set()
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip()
            if nm:
                nm_up = nm.upper()
                roster_names_norm.add(nm_up)
                roster_vmax_map[nm_up] = float(pr.get("v_max") or 30.0)

    alerts = []
    unmatched_players = set()

    for idx, r in df_check.iterrows():
        p_name = str(r.get("player_name") or "").strip()
        if not p_name or p_name == "0":
            continue
        p_up = p_name.upper()
        sess = str(r.get("session_name") or r.get("date") or "Seduta")
        dt_s = str(r.get("date") or "")[:10]

        ident = utils.resolve_player_identity(p_name)
        matched_pid = ident.get("player_id")
        if matched_pid is None and p_up not in roster_names_norm:
            unmatched_players.add(p_name)

        dur = pd.to_numeric(r.get("duration"), errors="coerce")
        dist = pd.to_numeric(r.get("distance_m"), errors="coerce")
        m_min = pd.to_numeric(r.get("m_per_min"), errors="coerce")
        vmax = pd.to_numeric(r.get("v_max"), errors="coerce")
        vmax_pct = pd.to_numeric(r.get("v_max_pct"), errors="coerce")
        ref_vmax = roster_vmax_map.get(p_up) or float(ident.get("v_max") or 0.0)

        if pd.notna(dist) and dist > 0 and (pd.isna(dur) or dur <= 0):
            alerts.append({
                "Giocatore": p_name,
                "Data": dt_s,
                "Seduta": sess,
                "Tipo Alert": "🔴 Durata Mancante / Zero",
                "Valore Rilevato": f"Durata: {0 if pd.isna(dur) else dur} min (Dist: {dist:.0f} m)",
                "Indicazione": "Impossibile calcolare HML/min, HSR/min e m/min senza durata > 0.",
            })

        if pd.notna(vmax) and vmax > 37.5:
            alerts.append({
                "Giocatore": p_name,
                "Data": dt_s,
                "Seduta": sess,
                "Tipo Alert": "🔴 Spike Velocità Massima (>37.5 km/h)",
                "Valore Rilevato": f"{vmax:.2f} km/h",
                "Indicazione": "Probabile spike satellite del sensore GPS.",
            })
        elif pd.notna(vmax) and ref_vmax > 0 and vmax > ref_vmax * 1.03:
            pct_calc = (vmax / ref_vmax) * 100.0
            alerts.append({
                "Giocatore": p_name,
                "Data": dt_s,
                "Seduta": sess,
                "Tipo Alert": "🟡 Superamento Vmax Roster (>103%)",
                "Valore Rilevato": f"{vmax:.2f} km/h ({pct_calc:.1f}% di {ref_vmax:.1f} km/h)",
                "Indicazione": "Nuovo picco Vmax dell'atleta oppure lieve sovrastima GPS.",
            })
        elif pd.notna(vmax_pct) and vmax_pct > 105.0:
            alerts.append({
                "Giocatore": p_name,
                "Data": dt_s,
                "Seduta": sess,
                "Tipo Alert": "🟡 % Vmax Elevata (>105%)",
                "Valore Rilevato": f"{vmax_pct:.1f}%",
                "Indicazione": "Verificare la Vmax di profilo impostata in GPExe/Roster.",
            })

        if pd.notna(m_min) and m_min > 155.0:
            alerts.append({
                "Giocatore": p_name,
                "Data": dt_s,
                "Seduta": sess,
                "Tipo Alert": "🟠 Densità m/min Anomala (>155 m/min)",
                "Valore Rilevato": f"{m_min:.1f} m/min",
                "Indicazione": "Verificare se la durata del drill/seduta è stata tagliata troppo corta.",
            })

    if not alerts and not unmatched_players:
        st.markdown(
            """
            <div style="background:#ECFDF5; border:1px solid #A7F3D0; border-radius:8px; padding:9px 14px; margin:8px 0 12px 0; color:#065F46; font-size:0.82rem; font-weight:700;">
                🛡️ Controllo Qualità Automatico GPS Superato: nessuna anomalia rilevata (Vmax, Durata, Densità m/min e anagrafica Roster regolari).
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        with st.expander(
            f"🛡️ Alert Controllo Qualità GPS: {len(alerts)} segnalazioni sui valori • {len(unmatched_players)} atleti fuori Roster",
            expanded=True,
        ):
            if unmatched_players:
                st.warning(
                    f"👤 **Atleti non trovati nel Roster Nazionale ({len(unmatched_players)}):** "
                    + ", ".join(sorted(unmatched_players))
                )
            if alerts:
                st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)


def _render_session_status_and_type_config(df_data: pd.DataFrame, key_prefix: str) -> tuple[str, dict]:
    """
    Consente di configurare all'atto del caricamento del file:
    1. Tipologia Seduta FIR (per i benchmark storici)
    2. Atleti in allenamento MODIFICATO (evidenziati in giallo, esclusi dalle medie)
    3. Atleti in RETURN TO PLAY / RTP (evidenziati in celeste, esclusi dalle medie)
    """
    st.markdown("### 3. Configurazione Seduta & Stato Partecipazione Atleti (FIR)")
    st.caption(
        "⚡ **Assegnazione Immediata al Caricamento:** indica la tipologia di seduta e gli atleti con carico differenziato. "
        "Gli atleti **Modificati** e **RTP** vengono esclusi automaticamente da tutte le medie di ruolo, reparto e squadra "
        "ed evidenziati visivamente nelle tabelle (giallo per Modificato, celeste per RTP)."
    )

    sess_col = "session_name" if "session_name" in df_data.columns else None
    first_sess_name = str(df_data[sess_col].dropna().iloc[0]) if sess_col and not df_data[sess_col].dropna().empty else "Allenamento"
    default_typ = utils.detect_fir_session_type(first_sess_name)
    if default_typ not in utils.FIR_SESSION_TYPOLOGIES:
        default_typ = "Rugby"

    athletes = []
    if "player_name" in df_data.columns:
        athletes = sorted([str(p).strip() for p in df_data["player_name"].dropna().unique() if str(p).strip() and str(p).strip() != "0"])

    c_tp, c_mod, c_rtp = st.columns([1.1, 1.45, 1.45])

    sel_type = c_tp.selectbox(
        "⚡ Tipologia Seduta FIR",
        utils.FIR_SESSION_TYPOLOGIES,
        index=utils.FIR_SESSION_TYPOLOGIES.index(default_typ) if default_typ in utils.FIR_SESSION_TYPOLOGIES else 0,
        key=f"{key_prefix}_sel_type",
        help="Usata per confrontare la seduta con lo storico della stessa categoria.",
    )

    sel_mod = c_mod.multiselect(
        "🟡 Atleti MODIFICATO (Carico Ridotto)",
        athletes,
        default=[],
        key=f"{key_prefix}_sel_mod",
        help="Atleti che hanno saltato drill o con minutaggio ridotto. Esclusi dalle medie.",
    )

    avail_rtp = [p for p in athletes if p not in sel_mod]
    sel_rtp = c_rtp.multiselect(
        "🔵 Atleti RTP (Return To Play)",
        avail_rtp,
        default=[],
        key=f"{key_prefix}_sel_rtp",
        help="Atleti in reintegro da infortunio. Esclusi dalle medie.",
    )

    n_full = max(0, len(athletes) - len(sel_mod) - len(sel_rtp))
    st.markdown(
        f"""
        <div style="background:#0F172A; border:1px solid #334155; border-radius:8px; padding:8px 14px; margin-bottom:12px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; font-size:0.80rem;">
            <div style="color:#F8FAFC;">
                <b>Partecipazione:</b>
                <span style="color:#34D399; font-weight:700; margin-left:8px;">🟢 {n_full} Full (Normali)</span> •
                <span style="color:#FDE047; font-weight:700; margin-left:8px;">🟡 {len(sel_mod)} Modificato (Esclusi)</span> •
                <span style="color:#38BDF8; font-weight:700; margin-left:8px;">🔵 {len(sel_rtp)} RTP (Esclusi)</span>
            </div>
            <div style="color:#D4AF37; font-weight:700;">
                Benchmark Selezionato: <b>{sel_type}</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    status_map = {}
    for p in athletes:
        if p in sel_mod:
            status_map[p] = "Modificato"
        elif p in sel_rtp:
            status_map[p] = "RTP"
        else:
            status_map[p] = "Full"

    return sel_type, status_map


def _render_sub_csv_import(t: dict):
    c_src1, c_src2 = st.columns([1.6, 2.4])
    team_choices = {
        "auto": "Riconoscimento Automatico dal CSV (Consigliato)",
        "benetton": "1. GPS Benetton Treviso (GPExe / Catapult)",
        "zebre": "2. GPS Zebre Parma (Catapult / GPExe)",
        "nazionale": "3. GPS Nazionale Italiana (GPExe FIR)",
        "oval": "4. Database Oval Match (Opta Match Stats)",
        "altro": "Altro Formato Personalizzato (Mapping Manuale)",
    }
    sel_profile = c_src1.selectbox(
        "1. Tipo di Export CSV da Caricare",
        list(team_choices.keys()),
        format_func=lambda k: team_choices[k],
        index=0,
        key="imp_team_type",
    )

    c_src2.markdown("<div style='font-size:0.84rem; font-weight:700; color:#0F172A; margin-bottom:4px;'>2. Carica File Export (.csv oppure .xlsx)</div>", unsafe_allow_html=True)
    up_mode = c_src2.radio(
        "Metodo di caricamento:",
        ["Trascina / Sfoglia file dal browser", "Carica da percorso locale / Cartella dati"],
        horizontal=True,
        label_visibility="collapsed",
        key="imp_up_mode",
    )

    uploaded = None
    local_path = None

    if up_mode == "Trascina / Sfoglia file dal browser":
        uploaded = c_src2.file_uploader(
            "Carica File Export (.csv oppure .xlsx)",
            type=["csv", "xlsx", "xls"],
            key="imp_file_uploader",
            label_visibility="collapsed",
        )
    else:
        ex_dir = os.path.join(os.path.dirname(__file__), "..", "data", "esempi_csv")
        sample_files = []
        if os.path.exists(ex_dir):
            sample_files = sorted([f for f in os.listdir(ex_dir) if f.lower().endswith((".csv", ".xlsx", ".xls"))])

        c_l1, c_l2 = c_src2.columns([1.4, 2.6])
        chosen_sample = c_l1.selectbox(
            "File in 'data/esempi_csv':",
            ["(Seleziona...)"] + sample_files,
            key="imp_sample_sel",
        )
        custom_path = c_l2.text_input(
            "Oppure incolla il percorso completo del file sul tuo Mac:",
            placeholder="es. /Users/riccardodimaio/Downloads/RDM-7.csv",
            key="imp_custom_path",
        ).strip()

        if custom_path and os.path.exists(custom_path):
            local_path = custom_path
            c_src2.caption(f"✓ File rilevato: `{os.path.basename(custom_path)}`")
        elif chosen_sample != "(Seleziona...)":
            local_path = os.path.join(ex_dir, chosen_sample)
            c_src2.caption(f"✓ File selezionato: `{chosen_sample}`")

    if uploaded is None and local_path is None:
        st.info(
            "Carica un file `.csv` per uno dei **4 formati ufficiali** (**GPS FIR**, **GPS Benetton**, **GPS Zebre**, **Oval Match**): "
            "il sistema riconosce automaticamente il separatore (`;` o `,`), la struttura del file, filtra le righe di riepilogo ruolo/squadra "
            "e allinea tutte le metriche (inclusi HML >25.5W, HSR 18-20 / 20-25 / >25 km/h e Roster FIR)."
        )
        matches_cat = utils.get_oval_distinct_matches_df()
        if not matches_cat.empty:
            with st.expander(f"🗑️ Elimina una Partita dai Dati Oval per Ricaricarla ({len(matches_cat)} gare in archivio)", expanded=False):
                st.caption("Seleziona una partita già caricata nei Dati Oval per eliminarla completamente prima di ricaricare il file aggiornato.")
                dc1, dc2 = st.columns([1.2, 2.8])
                t_list = ["Tutte le Squadre"] + sorted([t for t in matches_cat["teamName"].dropna().unique().tolist() if str(t).strip()])
                sel_t_imp = dc1.selectbox("Filtra per Squadra", t_list, key="imp_oval_del_team")
                sub_m = matches_cat if sel_t_imp == "Tutte le Squadre" else matches_cat[matches_cat["teamName"] == sel_t_imp].reset_index(drop=True)
                if not sub_m.empty:
                    sel_m_lbl = dc2.selectbox("Partita da Eliminare", sub_m["label"].tolist(), key="imp_oval_del_match")
                    s_row = sub_m[sub_m["label"] == sel_m_lbl].iloc[0]
                    bc1, bc2 = st.columns([1.8, 2.2])
                    chk_del = bc1.checkbox(f"Confermo eliminazione ({int(s_row['n_records'])} giocatori)", value=False, key="imp_oval_del_chk")
                    if bc2.button("🗑️ Elimina Partita dai Dati Oval", type="primary", disabled=not chk_del, use_container_width=True, key="imp_oval_del_btn"):
                        rem = utils.delete_oval_match_by_game(str(s_row["match_date"]), str(s_row["game"]), str(s_row["teamName"]))
                        st.success(f"✅ Partita **{s_row['match_date']} • {s_row['game']}** eliminata ({rem} record rimossi)!")
                        st.rerun()

        gh_all = utils.load_table("gps_history")
        if not gh_all.empty and "date" in gh_all.columns and "session_name" in gh_all.columns:
            u_gps_sess = gh_all[["date", "session_name", "team_type"]].dropna().drop_duplicates().sort_values("date", ascending=False).head(35)
            if not u_gps_sess.empty:
                with st.expander("🗑️ Elimina o Correggi una Seduta GPS Archiviata (ultime 35 sedute)", expanded=False):
                    st.caption("Se hai importato per errore una seduta GPS con la squadra errata o vuoi ricaricarla da zero, puoi eliminarla qui in un click.")
                    col_del1, col_del2 = st.columns([2.5, 1.5])
                    sess_labels = [f"{str(r['date'])[:10]} • {r['session_name']} [{str(r['team_type']).upper()}]" for _, r in u_gps_sess.iterrows()]
                    sel_sess_del = col_del1.selectbox("Seleziona Seduta GPS da Rimuovere", sess_labels, key="imp_gps_del_sel")
                    idx_del = sess_labels.index(sel_sess_del)
                    r_target = u_gps_sess.iloc[idx_del]
                    chk_gps_del = col_del2.checkbox("Confermo eliminazione seduta", value=False, key="imp_gps_del_chk")
                    if col_del2.button("🗑️ Elimina Seduta GPS", type="primary", disabled=not chk_gps_del, use_container_width=True, key="imp_gps_del_btn"):
                        del_n = utils.delete_gps_history_session(str(r_target["date"])[:10], str(r_target["session_name"]), str(r_target["team_type"]))
                        st.success(f"✅ Seduta eliminata ({del_n} record GPS rimossi)!")
                        st.rerun()
        return

    # Read uploaded or local file
    raw_df = pd.DataFrame()
    fname = ""
    if uploaded is not None:
        fname = uploaded.name
        try:
            if fname.lower().endswith((".xlsx", ".xls")):
                xl = pd.ExcelFile(uploaded)
                sheet_names = xl.sheet_names
                sel_sheet = st.selectbox("Seleziona Foglio Excel da importare", sheet_names, index=0, key="imp_xl_sheet")
                raw_df = xl.parse(sel_sheet)
            else:
                content = uploaded.getvalue().decode("utf-8", errors="ignore")
                first_line = content.splitlines()[0] if content else ""
                sep = ";" if first_line.count(";") > first_line.count(",") else ","
                uploaded.seek(0)
                raw_df = pd.read_csv(uploaded, sep=sep, low_memory=False)
        except Exception as e:
            st.error(f"Errore nella lettura del file: {e}")
            return
    elif local_path is not None:
        fname = os.path.basename(local_path)
        try:
            if fname.lower().endswith((".xlsx", ".xls")):
                xl = pd.ExcelFile(local_path)
                sheet_names = xl.sheet_names
                sel_sheet = st.selectbox("Seleziona Foglio Excel da importare", sheet_names, index=0, key="imp_xl_sheet_loc")
                raw_df = xl.parse(sel_sheet)
            else:
                with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline()
                sep = ";" if first_line.count(";") > first_line.count(",") else ","
                raw_df = pd.read_csv(local_path, sep=sep, low_memory=False)
        except Exception as e:
            st.error(f"Errore nella lettura del file locale: {e}")
            return

    if raw_df.empty:
        st.warning("Il file caricato non contiene righe valide.")
        return

    detected_type = utils.detect_csv_export_type(raw_df, fname) if sel_profile == "auto" else sel_profile
    type_labels = {
        "nazionale": "GPS Nazionale Italiana (FIR — GPExe)",
        "benetton": "GPS Benetton Treviso (GPExe)",
        "zebre": "GPS Zebre Parma (Catapult / GPExe)",
        "oval": "Database Oval Match (Opta Match Stats)",
        "altro": "Formato Personalizzato",
    }

    st.success(
        f"File **{fname}** letto correttamente (**{len(raw_df):,} righe**, **{len(raw_df.columns)} colonne**) — "
        f"Profilo rilevato: **{type_labels.get(detected_type, detected_type)}**"
    )

    with st.expander("Anteprima File Originale Caricato (Prime 10 righe)", expanded=False):
        st.dataframe(raw_df.head(10), use_container_width=True)

    # ==========================================================================
    # CASO A: DATABASE OVAL MATCH (RDM-5.csv)
    # ==========================================================================
    if detected_type == "oval":
        st.markdown("### 3. Anteprima Importazione Database Oval Match")
        p_cols = [c for c in ["date", "playerId", "playerFullName", "teamName", "pos", "Min", "Jersey", "game", "result", "TotalCarriesInContact", "TotalTackleAttempts", "TotalEffectiveRuckEntries"] if c in raw_df.columns]
        st.dataframe(raw_df[p_cols].head(20) if p_cols else raw_df.head(20), use_container_width=True, hide_index=True)

        overwrite_oval = st.checkbox(
            "🔄 Sovrascrivi/Aggiorna automaticamente le partite già presenti in archivio se ricaricate",
            value=True,
            key="chk_overwrite_oval_import",
            help="Se attivo, i record già presenti per la stessa partita/giocatore vengono sostituiti con quelli del nuovo file caricato.",
        )

        if st.button(
            f"Conferma e Aggiorna Database Oval Match ({len(raw_df):,} righe)",
            type="primary",
            use_container_width=True,
            key="btn_confirm_oval_import",
        ):
            res = utils.import_oval_csv_dataframe(raw_df, overwrite_existing=overwrite_oval)
            dup_cnt = res.get("duplicates", 0)
            net_new = res.get("net_new", 0)
            overwritten_cnt = res.get("overwritten", 0)
            dup_df = res.get("duplicate_df", pd.DataFrame())

            if dup_cnt > 0:
                st.warning(f"⚠️ Attenzione: **{dup_cnt:,} record** non sono stati caricati perché **già presenti** nell'archivio Oval Match!")
                with st.expander(f"📋 Dettaglio dei {dup_cnt:,} record duplicati non caricati", expanded=True):
                    show_cols = [c for c in ["date", "fir_player_name", "playerFullName", "teamName", "game", "Min", "points"] if c in dup_df.columns]
                    st.dataframe(dup_df[show_cols], use_container_width=True, hide_index=True)

            if net_new > 0:
                ov_msg = f" (di cui **{overwritten_cnt:,}** aggiornati/sovrascritti)" if overwritten_cnt > 0 else ""
                st.success(
                    f"✅ Database Oval Match aggiornato con successo! Prestazioni salvate: **{net_new:,}**{ov_msg} | "
                    f"Totale archivio Oval: **{res.get('total_after', 0):,} righe**. "
                    f"Le medie Match (80') nel Roster sono state ricalcolate automaticamente."
                )
                st.balloons()
            elif dup_cnt > 0:
                st.info(f"Tutti i {dup_cnt} record contenuti nel file sono già archiviati nel database. Nessun nuovo record inserito.")
        return

    # ==========================================================================
    # CASO B: PARSER AUTOMATICO STANDARD GPS (FIR / BENETTON / ZEBRE)
    # ==========================================================================
    t_name_map = {
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
        "nazionale": "Nazionale Italiana",
        "altro": "Altro Club",
    }

    if detected_type != "altro":
        st.markdown("### 3. Destinazione Franchigia & Configurazione Importazione GPS")

        c_dest1, c_dest2 = st.columns([2.3, 1.9])

        team_opts = ["benetton", "zebre", "nazionale"]
        default_team = detected_type if detected_type in team_opts else "benetton"
        def_idx = team_opts.index(default_team) if default_team in team_opts else 0

        sel_team_type = c_dest1.selectbox(
            "🏷️ Squadra / Franchigia di Destinazione:",
            team_opts,
            index=def_idx,
            format_func=lambda x: {
                "benetton": "🟢 Benetton Treviso (GPExe / Catapult)",
                "zebre": "🟡 Zebre Parma (Catapult / GPExe)",
                "nazionale": "🔵 Nazionale Italiana (FIR GPExe)",
            }[x],
            key=f"imp_sel_team_override_{fname}",
            help="Modifica o conferma la franchigia a cui associare i dati. Se il sistema ha rilevato Zebre ma si tratta di Treviso, seleziona Benetton Treviso.",
        )

        only_roster = c_dest2.checkbox(
            "Filtra solo atleti del Roster FIR (consigliato per Benetton e Zebre)",
            value=(sel_team_type in ("benetton", "zebre")),
            key=f"imp_only_roster_{sel_team_type}_{fname}",
            help="Se attivo, include solo gli atleti presenti nel Roster FIR monitorati. Se disattivato, importa tutti gli atleti del file.",
        )

        parsed = utils.parse_standard_gps_csv(raw_df, fname, sel_team_type, only_fir_roster=only_roster)
        std_df = parsed["df"]

        if not std_df.empty:
            info_parts = [
                f"Formato: **{parsed['format_detected']}**",
                f"Destinazione: **{t_name_map[sel_team_type]}** (**{len(std_df):,} righe pronte**)",
            ]
            if parsed["skipped_summary"] > 0:
                info_parts.append(f"**{parsed['skipped_summary']} righe** di riepilogo ruolo/Team escluse automaticamente")
            if parsed["skipped_non_roster"]:
                info_parts.append(f"**{len(parsed['skipped_non_roster'])} atleti** non nel Roster FIR esclusi ({', '.join(parsed['skipped_non_roster'][:5])}{'...' if len(parsed['skipped_non_roster']) > 5 else ''})")
            st.info(" • ".join(info_parts))

            st.markdown(f"#### Anteprima Dati Normalizzati per {t_name_map[sel_team_type]} ({len(std_df):,} righe)")
            prev_cols = [
                "date", "player_name", "sigla", "role", "session_name", "period",
                "duration", "distance_m", "m_per_min", "v_max", "v_max_pct",
                "mp_25_35", "mp_35_50", "mp_50_100", "speed_18_20", "speed_20_25", "speed_25_72",
                "contacts", "player_load_total",
            ]
            prev_cols = [c for c in prev_cols if c in std_df.columns]
            st.dataframe(std_df[prev_cols].head(25).rename(columns=FIR_COL_LABELS), use_container_width=True, hide_index=True)

            # Controllo Qualità Automatico ("Alert Anomalie GPS")
            _render_gps_quality_check(std_df)

            # Assegnazione Tipologia & Stato Atleta (Modificato / RTP)
            chosen_typ, status_map = _render_session_status_and_type_config(std_df, key_prefix="std_gps")

            if st.button(
                f"Conferma e Importa {len(std_df):,} Record in {t_name_map[sel_team_type]}",
                type="primary",
                use_container_width=True,
                key="btn_confirm_auto_gps_import",
            ):
                std_df["status"] = std_df["player_name"].map(status_map).fillna("Full")
                std_df["player_status"] = std_df["status"]

                # Salva tipologia e status giocatori per tutte le sessioni del file
                u_sessions = std_df[["date", "session_name"]].dropna().drop_duplicates() if ("date" in std_df.columns and "session_name" in std_df.columns) else pd.DataFrame()
                fir_types = utils.get_fir_session_types()
                if "session_status_overrides" not in st.session_state:
                    st.session_state["session_status_overrides"] = {}
                if not u_sessions.empty:
                    for _, urow in u_sessions.iterrows():
                        d_s = str(urow["date"])[:10]
                        s_n = str(urow["session_name"]).strip()
                        k_s = f"{d_s}_{s_n}"
                        fir_types[k_s] = chosen_typ
                        utils.set_bulk_player_status_in_session(d_s, s_n, status_map)
                        st.session_state["session_status_overrides"][k_s] = status_map
                    utils.save_fir_session_types(fir_types)

                res = utils.bulk_insert_gps_history(std_df)
                ins_cnt = res.get("inserted", 0) if isinstance(res, dict) else res
                dup_cnt = res.get("duplicates", 0) if isinstance(res, dict) else 0
                dup_df = res.get("duplicate_df", pd.DataFrame()) if isinstance(res, dict) else pd.DataFrame()

                if dup_cnt > 0:
                    st.warning(f"⚠️ Attenzione: **{dup_cnt:,} record** non sono stati caricati perché **già presenti** nel database!")
                    with st.expander(f"📋 Dettaglio dei {dup_cnt:,} record duplicati non caricati", expanded=True):
                        d_cols = [c for c in ["date", "player_name", "session_name", "period", "distance_m", "v_max", "duration"] if c in dup_df.columns]
                        st.dataframe(dup_df[d_cols], use_container_width=True, hide_index=True)

                if ins_cnt > 0:
                    mod_cnt = sum(1 for s in status_map.values() if s == "Modificato")
                    rtp_cnt = sum(1 for s in status_map.values() if s == "RTP")
                    st.success(
                        f"✅ Importazione completata! **{ins_cnt:,} nuovi record** salvati in **{t_name_map[sel_team_type]}** • "
                        f"Tipologia: **{chosen_typ}** | Modificati: **{mod_cnt}** | RTP: **{rtp_cnt}** "
                        f"(aggiornati automaticamente in tutte le analisi e benchmark)."
                    )
                    st.balloons()
                elif dup_cnt > 0:
                    st.info(f"Nessun nuovo dato da inserire: tutti i {dup_cnt} record del file sono già presenti nell'archivio storico.")
            return

    # Load saved mapping for selected team_type
    all_saved_mappings = utils.get_club_mappings()
    saved_map = all_saved_mappings.get(sel_team_type, {})

    file_cols_opts = ["-- Nessuna --"] + [str(c) for c in raw_df.columns]

    st.markdown("### 3. Configura Mappatura Colonne verso Tabella Standard FIR (Colonne D - AY)")
    st.caption("Le colonne con nome compatibile vengono agganciate automaticamente. Puoi personalizzare ogni associazione e salvarla come predefinita per questo club.")

    categories = []
    for _, _, _, cat, _ in FIR_COLUMNS_META:
        if cat not in categories:
            categories.append(cat)

    current_mapping = {}
    for cat in categories:
        cat_fields = [m for m in FIR_COLUMNS_META if m[3] == cat]
        with st.expander(f"Sezione: {cat} ({len(cat_fields)} colonne FIR)", expanded=(cat in ["Anagrafica & Seduta", "Volume & Velocità"])):
            cols_ui = st.columns(4)
            for i, (db_col, ex_col, lbl, _, _) in enumerate(cat_fields):
                default_choice = _auto_detect_col(db_col, [str(c) for c in raw_df.columns], saved_map)
                idx = file_cols_opts.index(default_choice) if default_choice in file_cols_opts else 0
                chosen = cols_ui[i % 4].selectbox(
                    lbl,
                    file_cols_opts,
                    index=idx,
                    key=f"map_{sel_team_type}_{db_col}",
                )
                if chosen != "-- Nessuna --":
                    current_mapping[db_col] = chosen

    # Options for automatic enrichment from Roster
    opt1, opt2, opt3 = st.columns([2, 1.5, 1.5])
    auto_enrich_roster = opt1.checkbox(
        "Riconosci automaticamente gli atleti dal Roster Nazionale (compila Sigla, Ruolo e Vmax Profilo se mancanti)",
        value=True,
        key="imp_auto_roster",
    )
    dur_unit = opt2.selectbox(
        "Formato Colonna Durata nel file sorgente",
        ["Automatico (Minuti / mm:ss / Excel)", "Secondi (dividi per 60)"],
        key="imp_dur_unit",
    )
    if opt3.button(f"Salva Profilo Mapping per {sel_team_type.upper()}", use_container_width=True, key="btn_save_map_profile"):
        utils.save_club_mapping(sel_team_type, current_mapping)
        st.success(f"Profilo di mappatura salvato per {sel_team_type.upper()}!")

    # Build transformed DataFrame preview
    if "player_name" not in current_mapping:
        st.warning("Associa almeno la colonna **D: Giocatore (Name)** per generare l'anteprima e procedere all'importazione.")
        return

    t_name_map = {
        "nazionale": "Nazionale Italiana",
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
        "altro": "Altro Club",
    }

    transformed_rows = []
    for idx_r, srow in raw_df.iterrows():
        raw_p = srow.get(current_mapping["player_name"])
        if pd.isna(raw_p) or not str(raw_p).strip() or str(raw_p).strip() == "0":
            continue

        ident = utils.resolve_player_identity(raw_p) if auto_enrich_roster else {"name_display": str(raw_p).strip(), "sigla": "", "role": "", "v_max": None}

        new_r = {
            "team_type": sel_team_type,
            "team_name": t_name_map.get(sel_team_type, "Altro Club"),
            "source_file": fname,
            "excel_row": int(idx_r) + 2,
        }

        for db_col, _, _, _, ctype in FIR_COLUMNS_META:
            src_c = current_mapping.get(db_col)
            val = srow.get(src_c) if src_c else None

            if db_col == "player_name":
                new_r[db_col] = ident.get("name_display") or str(raw_p).strip()
            elif db_col == "sigla":
                new_r[db_col] = str(val).strip() if pd.notna(val) and str(val).strip() else ident.get("sigla", "")
            elif db_col == "role":
                new_r[db_col] = str(val).strip() if pd.notna(val) and str(val).strip() else ident.get("role", "")
            elif db_col == "profile_max_vel":
                if pd.notna(val) and str(val).strip() != "":
                    try:
                        new_r[db_col] = float(str(val).replace(",", "."))
                    except Exception:
                        new_r[db_col] = ident.get("v_max")
                else:
                    new_r[db_col] = ident.get("v_max")
            elif db_col == "date":
                if pd.notna(val) and str(val).strip():
                    try:
                        new_r[db_col] = pd.to_datetime(val).strftime("%Y-%m-%d")
                    except Exception:
                        new_r[db_col] = str(val).strip()[:10]
                else:
                    new_r[db_col] = None
            elif db_col == "duration":
                d_val = _parse_duration_val(val)
                if dur_unit.startswith("Secondi") and pd.notna(d_val):
                    d_val = round(d_val / 60.0, 2)
                new_r[db_col] = d_val
            elif ctype == "float":
                if pd.notna(val) and str(val).strip() != "":
                    try:
                        new_r[db_col] = float(str(val).replace(",", "."))
                    except Exception:
                        new_r[db_col] = np.nan
                else:
                    new_r[db_col] = np.nan
            else:
                new_r[db_col] = str(val).strip() if pd.notna(val) and str(val).strip() else None

        # Auto-compute m/min if missing and distance + duration exist
        if pd.isna(new_r.get("m_per_min")) and pd.notna(new_r.get("distance_m")) and pd.notna(new_r.get("duration")) and new_r["duration"] > 0:
            new_r["m_per_min"] = round(new_r["distance_m"] / new_r["duration"], 1)

        # Auto-compute v_max_pct if missing and v_max + profile_max_vel exist
        if pd.isna(new_r.get("v_max_pct")) and pd.notna(new_r.get("v_max")) and pd.notna(new_r.get("profile_max_vel")) and new_r["profile_max_vel"] > 0:
            new_r["v_max_pct"] = round((new_r["v_max"] / new_r["profile_max_vel"]) * 100.0, 2)

        # Auto-compute day_name from date if missing
        if not new_r.get("day_name") and new_r.get("date"):
            try:
                new_r["day_name"] = pd.to_datetime(new_r["date"]).strftime("%A")
            except Exception:
                pass

        # If speed_18_20 comes from a cumulative '>18' column and speed_20_25 comes from '>20', subtract >20 so 18-20 is pure
        col_18 = str(current_mapping.get("speed_18_20") or "").lower()
        if ">18" in col_18 and pd.notna(new_r.get("speed_18_20")) and pd.notna(new_r.get("speed_20_25")):
            if new_r["speed_18_20"] >= new_r["speed_20_25"]:
                new_r["speed_18_20"] = round(max(0.0, new_r["speed_18_20"] - new_r["speed_20_25"]), 2)

        transformed_rows.append(new_r)

    preview_df = pd.DataFrame(transformed_rows)
    st.markdown(f"### 4. Anteprima Dati Normalizzati nello Schema FIR ({len(preview_df):,} righe pronte)")
    st.dataframe(preview_df.head(20).rename(columns=FIR_COL_LABELS), use_container_width=True, hide_index=True)

    # Controllo Qualità Automatico ("Alert Anomalie GPS")
    _render_gps_quality_check(preview_df)

    chosen_typ, status_map = _render_session_status_and_type_config(preview_df, key_prefix="custom_gps")

    if st.button(
        f"Conferma e Importa {len(preview_df):,} Record in {t_name_map.get(sel_team_type)}",
        type="primary",
        use_container_width=True,
        key="btn_confirm_bulk_import",
    ):
        preview_df["status"] = preview_df["player_name"].map(status_map).fillna("Full")
        preview_df["player_status"] = preview_df["status"]

        # Salva tipologia e status giocatori per tutte le sessioni del file
        u_sessions = preview_df[["date", "session_name"]].dropna().drop_duplicates() if ("date" in preview_df.columns and "session_name" in preview_df.columns) else pd.DataFrame()
        fir_types = utils.get_fir_session_types()
        if "session_status_overrides" not in st.session_state:
            st.session_state["session_status_overrides"] = {}
        if not u_sessions.empty:
            for _, urow in u_sessions.iterrows():
                d_s = str(urow["date"])[:10]
                s_n = str(urow["session_name"]).strip()
                k_s = f"{d_s}_{s_n}"
                fir_types[k_s] = chosen_typ
                utils.set_bulk_player_status_in_session(d_s, s_n, status_map)
                st.session_state["session_status_overrides"][k_s] = status_map
            utils.save_fir_session_types(fir_types)

        utils.save_club_mapping(sel_team_type, current_mapping)
        res = utils.bulk_insert_gps_history(preview_df)
        ins_cnt = res.get("inserted", 0) if isinstance(res, dict) else res
        dup_cnt = res.get("duplicates", 0) if isinstance(res, dict) else 0
        dup_df = res.get("duplicate_df", pd.DataFrame()) if isinstance(res, dict) else pd.DataFrame()

        if dup_cnt > 0:
            st.warning(f"⚠️ Attenzione: **{dup_cnt:,} record** non sono stati caricati perché **già presenti** nel database!")
            with st.expander(f"📋 Dettaglio dei {dup_cnt:,} record duplicati non caricati", expanded=True):
                d_cols = [c for c in ["date", "player_name", "session_name", "period", "distance_m", "v_max", "duration"] if c in dup_df.columns]
                st.dataframe(dup_df[d_cols], use_container_width=True, hide_index=True)

        if ins_cnt > 0:
            mod_cnt = sum(1 for s in status_map.values() if s == "Modificato")
            rtp_cnt = sum(1 for s in status_map.values() if s == "RTP")
            st.success(
                f"✅ Importazione completata! **{ins_cnt:,} nuovi record** aggiunti in **{t_name_map.get(sel_team_type)}** • "
                f"Tipologia: **{chosen_typ}** | Modificati: **{mod_cnt}** | RTP: **{rtp_cnt}**."
            )
            st.balloons()
        elif dup_cnt > 0:
            st.info(f"Nessun nuovo dato da inserire: tutti i {dup_cnt} record del file sono già presenti nell'archivio storico.")


# ==============================================================================
# SOTTOPAGINA: SESSIONE VIRTUALE & RICOSTRUZIONE GPS DA MEDIE STORICHE
# ==============================================================================
def _render_sub_virtual_session(t: dict):
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #0b1f3a 0%, #172554 100%); border-left: 4px solid #D4AF37; padding: 14px 18px; border-radius: 8px; margin-bottom: 20px;">
            <div style="color: #F8FAFC; font-weight: 700; font-size: 1.05rem; display: flex; align-items: center; gap: 8px;">
                <span>✨ Motore di Generazione & Ricostruzione Sessioni GPS da Medie Storiche</span>
            </div>
            <div style="color: #94A3B8; font-size: 0.86rem; margin-top: 4px;">
                Crea sessioni complete specificando unicamente i minuti di esposizione al carico per ciascun atleta oppure sostituisci la singola riga di un GPS guasto/anomalo in una sessione esistente.
                Tutte le metriche vengono calcolate moltiplicando i ratei medi al minuto per la durata inserita (con gerarchia di fallback: <b>Storico Personale Atleta ➔ Media Ruolo ➔ Media Reparto ➔ Media Squadra</b>).
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mode = st.radio(
        "Seleziona Modalità Operativa",
        [
            "✨ Modalità 1: Crea Nuova Sessione da Zero (Multi-Giocatore con Minuti di Esposizione)",
            "🛠️ Modalità 2: Sostituisci Riga GPS Guasto/Corrotto in Sessione Esistente (1 Singolo Atleta)",
        ],
        key="virt_mode_choice",
        horizontal=True,
    )

    if "Modalità 1" in mode:
        _render_sub_virtual_mode_new(t)
    else:
        _render_sub_virtual_mode_replace(t)


def _render_sub_virtual_mode_new(t: dict):
    st.markdown("### 1. Parametri Generali della Nuova Sessione")
    c1, c2, c3, c4 = st.columns([1.3, 1.2, 1.8, 1.5])

    team_opts = {
        "nazionale": "Nazionale Italiana (FIR)",
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
    }
    sel_team = c1.selectbox(
        "Squadra / Contesto",
        list(team_opts.keys()),
        format_func=lambda k: team_opts[k],
        key="virt_new_team",
    )
    sel_date = c2.date_input(
        "Data Seduta",
        value=datetime.date.today(),
        key="virt_new_date",
    )
    sel_name = c3.text_input(
        "Nome Seduta / Esercizio",
        value="Team Training",
        key="virt_new_name",
        help="Es. Team Training, Velocità Raduno, Skills & Contatto, ecc.",
    )

    typ_opts = utils.FIR_SESSION_TYPOLOGIES
    if "virt_new_typology" not in st.session_state or st.session_state["virt_new_typology"] not in typ_opts:
        def_typ = utils.detect_fir_session_type(sel_name)
        st.session_state["virt_new_typology"] = def_typ if def_typ in typ_opts else typ_opts[0]

    sel_typology = c4.selectbox(
        "Tipologia Seduta FIR",
        typ_opts,
        key="virt_new_typology",
        help="I tassi medi al minuto storici verranno estratti da questa specifica categoria.",
    )

    st.markdown("---")
    st.markdown("### 2. Selezione Atleti & Minuti di Esposizione")
    players_df = utils.get_players_df()
    if players_df.empty:
        st.warning("Nessun giocatore registrato nel Roster.")
        return

    all_players = sorted(players_df["name_display"].dropna().unique().tolist())

    camp_players = []
    if sel_team == "nazionale":
        camps = utils.get_camps_df()
        if not camps.empty:
            if "status" in camps.columns:
                act_camp = camps[camps["status"].astype(str).str.lower() == "in_corso"]
                if act_camp.empty:
                    act_camp = camps.sort_values(by="start_date_str" if "start_date_str" in camps.columns else "start_date", ascending=False).head(1)
            else:
                act_camp = camps.sort_values(by="start_date_str" if "start_date_str" in camps.columns else "start_date", ascending=False).head(1)
            if not act_camp.empty:
                camp_id = int(act_camp.iloc[0]["id"])
                camp_p_df = utils.get_camp_players_df(camp_id)
                if not camp_p_df.empty:
                    p_col = "player_name" if "player_name" in camp_p_df.columns else ("name_display" if "name_display" in camp_p_df.columns else None)
                    if p_col:
                        camp_players = [p for p in camp_p_df[p_col].dropna().tolist() if p in all_players]

    c_btn1, c_btn2, c_btn3 = st.columns([1.6, 1.6, 3.0])
    if c_btn1.button("⛺ Seleziona Atleti del Raduno Attivo" if camp_players else "Seleziona Tutti nel Roster", key="btn_sel_quick_camp"):
        st.session_state["virt_multisel_players"] = camp_players if camp_players else all_players
        st.rerun()
    if c_btn2.button("Deseleziona Tutti", key="btn_desel_all"):
        st.session_state["virt_multisel_players"] = []
        st.rerun()

    if "virt_multisel_players" not in st.session_state:
        st.session_state["virt_multisel_players"] = camp_players if camp_players else all_players[:30]

    valid_sel = [p for p in st.session_state["virt_multisel_players"] if p in all_players]
    st.session_state["virt_multisel_players"] = valid_sel

    chosen_players = st.multiselect(
        "Atleti che hanno partecipato alla seduta",
        all_players,
        key="virt_multisel_players",
    )

    if not chosen_players:
        st.info("Seleziona almeno un giocatore per generare la sessione.")
        return

    cd1, cd2 = st.columns([1.5, 3.5])
    default_dur = cd1.number_input(
        "Minuti di esposizione predefiniti",
        min_value=5.0,
        max_value=180.0,
        value=60.0,
        step=5.0,
        key="virt_def_dur_input",
    )
    if cd2.button("⚡ Applica questi minuti a tutti gli atleti selezionati", key="btn_apply_def_dur"):
        for p in chosen_players:
            st.session_state[f"virt_dur_{p}"] = default_dur
        st.rerun()

    st.caption("Personalizza i minuti per ciascun atleta direttamente nella tabella sottostante (modifica il valore e premi invio):")

    dur_data = []
    for p in chosen_players:
        ident = utils.resolve_player_identity(p)
        curr_min = float(st.session_state.get(f"virt_dur_{p}", default_dur))
        dur_data.append({
            "Atleta": p,
            "Ruolo": ident.get("role") or "Avanti",
            "Reparto": ident.get("department") or utils.ROLE_TO_DEPT.get(ident.get("role"), "Avanti"),
            "Minuti Esposizione": curr_min,
        })
    dur_df = pd.DataFrame(dur_data)

    edited_dur_df = st.data_editor(
        dur_df,
        column_config={
            "Atleta": st.column_config.TextColumn("Atleta", disabled=True),
            "Ruolo": st.column_config.TextColumn("Ruolo", disabled=True),
            "Reparto": st.column_config.TextColumn("Reparto", disabled=True),
            "Minuti Esposizione": st.column_config.NumberColumn(
                "Minuti Esposizione",
                min_value=1.0,
                max_value=180.0,
                step=1.0,
                format="%.0f min",
                required=True,
            ),
        },
        hide_index=True,
        use_container_width=True,
        key="virt_data_editor_minutes",
    )

    for _, r in edited_dur_df.iterrows():
        st.session_state[f"virt_dur_{r['Atleta']}"] = float(r["Minuti Esposizione"])

    st.markdown("---")
    st.markdown("### 3. Anteprima Calcolata da Medie Storiche")

    gen_rows = []
    for _, r in edited_dur_df.iterrows():
        p_name = r["Atleta"]
        d_val = float(r["Minuti Esposizione"])
        if d_val > 0:
            row = utils.generate_virtual_player_gps_row(
                player_name=p_name,
                duration_min=d_val,
                typology=sel_typology,
                date_str=str(sel_date),
                session_name=sel_name,
                team_type=sel_team,
                is_replacement=False,
            )
            gen_rows.append(row)

    if not gen_rows:
        st.warning("Nessun record generabile con durata maggiore di 0.")
        return

    preview_df = pd.DataFrame(gen_rows)
    preview_df["hml_total"] = preview_df["mp_25_35"].fillna(0) + preview_df["mp_35_50"].fillna(0) + preview_df["mp_50_100"].fillna(0)
    preview_df["hsr18_total"] = preview_df["speed_18_20"].fillna(0) + preview_df["speed_20_25"].fillna(0) + preview_df["speed_25_72"].fillna(0)
    preview_df["hsr20_total"] = preview_df["speed_20_25"].fillna(0) + preview_df["speed_25_72"].fillna(0)
    preview_df["vhsr25"] = preview_df["speed_25_72"].fillna(0)

    kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
    kpi1.metric("Atleti Sessione", f"{len(preview_df)}")
    kpi2.metric("Durata Media", f"{round(preview_df['duration'].mean(), 1)} min")
    kpi3.metric("Distanza Media", f"{int(round(preview_df['distance_m'].mean()))} m")
    kpi4.metric("m/min Medio", f"{round(preview_df['m_per_min'].mean(), 1)}")
    kpi5.metric("Hml >25W Med.", f"{int(round(preview_df['hml_total'].mean()))} m")
    kpi6.metric("Vmax Media", f"{round(preview_df['v_max'].mean(), 1)} km/h")

    cols_to_disp = [
        "player_name", "role", "department", "duration", "distance_m", "m_per_min",
        "hml_total", "hsr18_total", "hsr20_total", "vhsr25", "v_max", "v_max_pct",
        "acc_volume", "player_load_total", "source_mode"
    ]
    cols_exist = [c for c in cols_to_disp if c in preview_df.columns]
    rename_prev = {
        "player_name": "Atleta",
        "role": "Ruolo",
        "department": "Reparto",
        "duration": "Tempo (min)",
        "distance_m": "Distanza (m)",
        "m_per_min": "m/min",
        "hml_total": "Hml >25W (m)",
        "hsr18_total": "HSR >18 (m)",
        "hsr20_total": "HSR >20 (m)",
        "vhsr25": "VHSR >25 (m)",
        "v_max": "V max (km/h)",
        "v_max_pct": "% V max",
        "acc_volume": "Acc Vol",
        "player_load_total": "Player Load",
        "source_mode": "Origine Medie",
    }
    st.dataframe(
        preview_df[cols_exist].rename(columns=rename_prev),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    st.markdown("### 4. Salvataggio Sessione nell'Archivio")
    if st.button(
        f"💾 Conferma e Salva Sessione ({len(preview_df)} Atleti) in {team_opts.get(sel_team)}",
        type="primary",
        use_container_width=True,
        key="btn_save_virtual_session",
    ):
        fir_types = utils.get_fir_session_types()
        k_s = f"{str(sel_date)}_{sel_name}"
        fir_types[k_s] = sel_typology
        utils.save_fir_session_types(fir_types)

        res = utils.bulk_insert_gps_history(preview_df)
        ins = res.get("inserted", 0) if isinstance(res, dict) else len(preview_df)
        dup = res.get("duplicates", 0) if isinstance(res, dict) else 0

        utils.get_typology_rates_cache.clear()
        utils.get_distinct_sessions_catalog.clear()

        if ins > 0:
            st.success(
                f"✅ Sessione **{sel_name}** ({str(sel_date)}) salvata con successo! "
                f"**{ins} record** aggiunti in archivio storico per **{team_opts.get(sel_team)}** "
                f"con tipologia **{sel_typology}**."
            )
            st.balloons()
        elif dup > 0:
            st.warning(f"⚠️ Attenzione: tutti i record di questa sessione ({dup}) risultano già presenti nell'archivio storico.")


def _render_sub_virtual_mode_replace(t: dict):
    st.markdown("### 1. Seleziona la Sessione Esistente dall'Archivio")
    c_f1, c_f2 = st.columns([1.2, 2.8])
    team_flt = c_f1.selectbox(
        "Filtra per Squadra",
        ["all", "nazionale", "benetton", "zebre"],
        format_func=lambda x: {"all": "Tutte le Squadre", "nazionale": "Nazionale Italiana", "benetton": "Benetton Treviso", "zebre": "Zebre Parma"}.get(x, x),
        key="virt_rep_team_flt",
    )
    sessions = utils.get_distinct_sessions_catalog(team_flt)
    if not sessions:
        st.warning("Nessuna sessione trovata nell'archivio storico per i criteri selezionati.")
        return

    sess_labels = [s["label"] for s in sessions]
    if "virt_rep_sess_sel" in st.session_state and st.session_state["virt_rep_sess_sel"] not in sess_labels:
        st.session_state["virt_rep_sess_sel"] = sess_labels[0] if sess_labels else None

    chosen_label = c_f2.selectbox(
        "Seleziona Sessione Storica da Modificare",
        sess_labels,
        key="virt_rep_sess_sel",
    )
    chosen_sess = next((s for s in sessions if s["label"] == chosen_label), sessions[0])

    sess_df = utils.get_session_records_for_edit(
        chosen_sess["date"],
        chosen_sess["session_name"],
        chosen_sess["team_type"],
    )
    if sess_df.empty:
        st.error("Impossibile caricare i dati della sessione selezionata.")
        return

    st.markdown("---")
    st.markdown(f"### 2. Seleziona l'Atleta con GPS Guasto o Corrotto (Totale nella seduta: {len(sess_df)} atleti)")

    p_options = []
    p_id_map = {}
    for _, r in sess_df.iterrows():
        p_name = str(r["player_name"]).strip()
        p_id = int(r["id"])
        dur = round(float(r.get("duration") or 0), 1)
        dist = int(round(float(r.get("distance_m") or 0)))
        vmax = round(float(r.get("v_max") or 0), 1)
        role = str(r.get("role") or "")
        period = str(r.get("period") or "session")
        lbl = f"{p_name} ({role}) — [ID #{p_id}] Durata: {dur}' | Dist: {dist}m | Vmax: {vmax} km/h | Periodo: {period}"
        p_options.append(lbl)
        p_id_map[lbl] = r

    if "virt_rep_player_sel" in st.session_state and st.session_state["virt_rep_player_sel"] not in p_options:
        st.session_state["virt_rep_player_sel"] = p_options[0] if p_options else None

    chosen_p_lbl = st.selectbox(
        "Seleziona Atleta da Ricostruire",
        p_options,
        key="virt_rep_player_sel",
    )
    old_row = p_id_map[chosen_p_lbl]
    target_player = str(old_row["player_name"]).strip()
    target_id = int(old_row["id"])

    old_dur = float(old_row.get("duration") or 0.0)
    old_dist = float(old_row.get("distance_m") or 0.0)
    old_mmin = float(old_row.get("m_per_min") or 0.0)
    old_hml = float(old_row.get("mp_25_35") or 0.0) + float(old_row.get("mp_35_50") or 0.0) + float(old_row.get("mp_50_100") or 0.0)
    old_hsr18 = float(old_row.get("speed_18_20") or 0.0) + float(old_row.get("speed_20_25") or 0.0) + float(old_row.get("speed_25_72") or 0.0)
    old_hsr20 = float(old_row.get("speed_20_25") or 0.0) + float(old_row.get("speed_25_72") or 0.0)
    old_vhsr25 = float(old_row.get("speed_25_72") or 0.0)
    old_vmax = float(old_row.get("v_max") or 0.0)

    st.markdown(
        f"""
        <div style="background:#1E293B; border-left:4px solid #EF4444; padding:10px 16px; border-radius:6px; margin:10px 0 16px 0;">
            <div style="color:#FCA5A5; font-weight:700; font-size:0.9rem;">
                ⚠️ Dati Attuali Registrati nel Database (ID #{target_id} • {target_player}):
            </div>
            <div style="color:#F8FAFC; font-size:0.85rem; margin-top:6px; display:flex; flex-wrap:wrap; gap:16px;">
                <span><b>Durata:</b> {old_dur:.1f} min</span>
                <span><b>Distanza:</b> {old_dist:.0f} m</span>
                <span><b>m/min:</b> {old_mmin:.1f}</span>
                <span><b>Hml >25W Totale:</b> {old_hml:.0f} m</span>
                <span><b>HSR >18 Totale:</b> {old_hsr18:.0f} m</span>
                <span><b>HSR >20 Totale:</b> {old_hsr20:.0f} m</span>
                <span><b>V max:</b> {old_vmax:.1f} km/h</span>
                <span><b>Periodo Attuale:</b> {old_row.get('period', '-')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 3. Parametri di Ricostruzione da Medie")
    c_m1, c_m2 = st.columns([1.5, 2.5])

    dur_key = f"virt_rep_real_dur_{target_id}"
    default_rebuild_min = old_dur if old_dur >= 10.0 else round(float(sess_df["duration"].median()), 1)
    if dur_key not in st.session_state:
        st.session_state[dur_key] = float(default_rebuild_min) if default_rebuild_min > 0 else 60.0

    real_duration = c_m1.number_input(
        "Minuti Reali di Esposizione dell'Atleta (durata effettiva giocata/allenata)",
        min_value=1.0,
        max_value=180.0,
        step=1.0,
        key=dur_key,
    )

    typ_opts = utils.FIR_SESSION_TYPOLOGIES
    typ_key = f"virt_rep_typ_sel_{target_id}"
    if typ_key not in st.session_state or st.session_state[typ_key] not in typ_opts:
        cur_typ = chosen_sess["typology"]
        st.session_state[typ_key] = cur_typ if cur_typ in typ_opts else typ_opts[0]

    rebuild_typology = c_m2.selectbox(
        "Tipologia Seduta per il Calcolo dei Tassi Medi al Minuto",
        typ_opts,
        key=typ_key,
    )

    new_row = utils.generate_virtual_player_gps_row(
        player_name=target_player,
        duration_min=real_duration,
        typology=rebuild_typology,
        date_str=chosen_sess["date"],
        session_name=chosen_sess["session_name"],
        team_type=chosen_sess["team_type"],
        is_replacement=True,
    )

    new_row["id"] = target_id
    if "created_at" in old_row and pd.notna(old_row["created_at"]):
        new_row["created_at"] = old_row["created_at"]

    new_hml = float(new_row.get("mp_25_35") or 0.0) + float(new_row.get("mp_35_50") or 0.0) + float(new_row.get("mp_50_100") or 0.0)
    new_hsr18 = float(new_row.get("speed_18_20") or 0.0) + float(new_row.get("speed_20_25") or 0.0) + float(new_row.get("speed_25_72") or 0.0)
    new_hsr20 = float(new_row.get("speed_20_25") or 0.0) + float(new_row.get("speed_25_72") or 0.0)
    new_vhsr25 = float(new_row.get("speed_25_72") or 0.0)

    st.markdown("---")
    st.markdown("### 4. Confronto Dati: Attuale (Guasto) vs Ricostruito da Medie")
    comp_data = [
        {"Parametro": "Minuti Esposizione", "Attuale (Guasto/DB)": f"{old_dur:.1f} min", "Ricostruito (Nuovo)": f"{new_row['duration']:.1f} min"},
        {"Parametro": "Distanza Totale", "Attuale (Guasto/DB)": f"{old_dist:.0f} m", "Ricostruito (Nuovo)": f"{new_row['distance_m']:.0f} m"},
        {"Parametro": "m/min", "Attuale (Guasto/DB)": f"{old_mmin:.1f}", "Ricostruito (Nuovo)": f"{new_row['m_per_min']:.1f}"},
        {"Parametro": "Hml >25W Totale", "Attuale (Guasto/DB)": f"{old_hml:.0f} m", "Ricostruito (Nuovo)": f"{new_hml:.0f} m"},
        {"Parametro": "HSR >18 Totale", "Attuale (Guasto/DB)": f"{old_hsr18:.0f} m", "Ricostruito (Nuovo)": f"{new_hsr18:.0f} m"},
        {"Parametro": "HSR >20 Totale", "Attuale (Guasto/DB)": f"{old_hsr20:.0f} m", "Ricostruito (Nuovo)": f"{new_hsr20:.0f} m"},
        {"Parametro": "VHSR >25", "Attuale (Guasto/DB)": f"{old_vhsr25:.0f} m", "Ricostruito (Nuovo)": f"{new_vhsr25:.0f} m"},
        {"Parametro": "V max", "Attuale (Guasto/DB)": f"{old_vmax:.1f} km/h", "Ricostruito (Nuovo)": f"{new_row['v_max']:.1f} km/h"},
        {"Parametro": "Periodo / Nota", "Attuale (Guasto/DB)": str(old_row.get("period", "-")), "Ricostruito (Nuovo)": str(new_row['period'])},
        {"Parametro": "Origine Medie Applicate", "Attuale (Guasto/DB)": "Caricamento Originale", "Ricostruito (Nuovo)": new_row['source_mode']},
    ]
    st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)

    st.info(
        f"ℹ️ La sostituzione opererà **esclusivamente sulla riga ID #{target_id}** di **{target_player}**. "
        f"Tutti gli altri **{len(sess_df) - 1} atleti** registrati nella sessione del **{chosen_sess['date']} ({chosen_sess['session_name']})** rimarranno inalterati."
    )

    if st.button(
        f"🔄 Conferma e Sostituisci Riga di {target_player} nel Database",
        type="primary",
        use_container_width=True,
        key="btn_confirm_replace_single_gps",
    ):
        utils.save_gps_history_record(new_row, record_id=target_id)
        utils.get_typology_rates_cache.clear()
        utils.get_distinct_sessions_catalog.clear()
        st.success(f"✅ Riga ID #{target_id} di {target_player} sostituita con successo dai dati ricostruiti!")
        st.balloons()
        st.rerun()


# ==============================================================================
# RIEPILOGO ULTIMI CARICAMENTI PER EVITARE DOPPIONI (FIR, ZEBRE, BENETTON, OVAL)
# ==============================================================================
def _get_latest_upload_summary() -> dict:
    """Restituisce data ultima sessione, dettagli attività e conteggio atleti per FIR, Benetton, Zebre e Oval."""
    summary = {
        "nazionale": {"label": "FIR (Nazionale)", "icon": "🇮🇹", "accent": "#0066B2", "date_fmt": "Nessun dato", "details": "Nessuna sessione caricata", "count_str": "0 atleti"},
        "benetton": {"label": "Benetton Rugby", "icon": "🦁", "accent": "#16A34A", "date_fmt": "Nessun dato", "details": "Nessuna sessione caricata", "count_str": "0 atleti"},
        "zebre": {"label": "Zebre Parma", "icon": "🦓", "accent": "#D97706", "date_fmt": "Nessun dato", "details": "Nessuna sessione caricata", "count_str": "0 atleti"},
        "oval": {"label": "Oval Match Data", "icon": "🏉", "accent": "#7C3AED", "date_fmt": "Nessun dato", "details": "Nessun match caricato", "count_str": "0 righe"},
    }

    gh = utils.load_table("gps_history")
    if not gh.empty and "date" in gh.columns:
        gh_valid = gh.copy()
        gh_valid["_dt"] = pd.to_datetime(gh_valid["date"], errors="coerce")
        gh_valid = gh_valid[gh_valid["_dt"].notna()]
        if not gh_valid.empty:
            gh_valid["_team"] = gh_valid["team_type"].fillna("nazionale").astype(str).str.strip().str.lower()
            for t_key in ["nazionale", "benetton", "zebre"]:
                sub = gh_valid[gh_valid["_team"] == t_key]
                if not sub.empty:
                    max_dt = sub["_dt"].max()
                    max_date_str = max_dt.strftime("%Y-%m-%d")
                    date_it = max_dt.strftime("%d/%m/%Y")
                    day_rows = sub[sub["_dt"] == max_dt]
                    sess_names = [
                        str(s).strip()
                        for s in day_rows["session_name"].dropna().unique().tolist()
                        if str(s).strip() and str(s).strip().lower() not in ("none", "nan", "nome attività")
                    ]
                    n_players = day_rows["player_name"].nunique() if "player_name" in day_rows.columns else len(day_rows)
                    n_rows = len(day_rows)
                    sess_label = " • ".join(sess_names[:3]) if sess_names else "Sessione standard"
                    if len(sess_names) > 3:
                        sess_label += f" (+{len(sess_names) - 3})"
                    # Se l'ultima data contiene solo sedute differenziate/RTP/extra, indica anche l'ultima collettiva
                    non_diff = sub[~sub["session_name"].astype(str).str.strip().str.upper().isin(["DIFFERENZIATO", "RETURN TO PLAY", "RTP", "EXTRA", "OFF FEET"])]
                    if not non_diff.empty and non_diff["_dt"].max() < max_dt:
                        coll_dt = non_diff["_dt"].max()
                        coll_rows = non_diff[non_diff["_dt"] == coll_dt]
                        coll_names = [str(s).strip() for s in coll_rows["session_name"].dropna().unique().tolist() if str(s).strip()]
                        coll_str = coll_names[0] if coll_names else "Collettivo"
                        sess_label += f" (Ultima collettiva: {coll_dt.strftime('%d/%m/%Y')} - {coll_str})"
                    summary[t_key]["date_fmt"] = f"{date_it} ({max_date_str})"
                    summary[t_key]["details"] = sess_label
                    summary[t_key]["count_str"] = f"{n_players} atleti ({n_rows} righe)"

    ov = utils.load_table("oval_matches")
    if not ov.empty and "match_date" in ov.columns:
        ov_valid = ov.copy()
        ov_valid["_dt"] = pd.to_datetime(ov_valid["match_date"], errors="coerce")
        ov_valid = ov_valid[ov_valid["_dt"].notna()]
        if not ov_valid.empty:
            max_dt = ov_valid["_dt"].max()
            max_date_str = max_dt.strftime("%Y-%m-%d")
            date_it = max_dt.strftime("%d/%m/%Y")
            day_rows = ov_valid[ov_valid["_dt"] == max_dt]
            teams = []
            for tcol in ["game", "teamName", "teamFullName", "team"]:
                if tcol in day_rows.columns:
                    vals = [
                        str(x).strip()
                        for x in day_rows[tcol].dropna().unique().tolist()
                        if str(x).strip() and str(x).strip().lower() not in ("none", "nan", "team", "game")
                    ]
                    if vals:
                        teams = vals
                        break
            p_col = "fir_player_name" if "fir_player_name" in day_rows.columns else ("playerFullName" if "playerFullName" in day_rows.columns else "player_name")
            n_players = day_rows[p_col].nunique() if p_col in day_rows.columns else len(day_rows)
            teams_label = " • ".join(teams[:3]) if teams else "Match Oval"
            if len(teams) > 3:
                teams_label += f" (+{len(teams) - 3})"
            summary["oval"]["date_fmt"] = f"{date_it} ({max_date_str})"
            summary["oval"]["details"] = teams_label
            summary["oval"]["count_str"] = f"{n_players} atleti ({len(day_rows)} righe)"

    return summary


def _render_last_uploads_banner():
    """Mostra le 4 card con la data dell'ultima sessione caricata per FIR, Zebre, Benetton e Oval."""
    summary = _get_latest_upload_summary()
    cards_html = ""
    for key in ["nazionale", "zebre", "benetton", "oval"]:
        item = summary[key]
        cards_html += (
            f'<div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid {item["accent"]}; '
            f'border-radius:10px; padding:11px 14px; box-shadow:0 1px 3px rgba(15,23,42,0.04);">'
            f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">'
            f'<span style="font-size:0.74rem; font-weight:800; color:#475569; text-transform:uppercase; letter-spacing:0.04em;">'
            f'{item["icon"]} {item["label"]}</span>'
            f'<span style="font-size:0.68rem; font-weight:700; color:{item["accent"]}; background:#F8FAFC; '
            f'border:1px solid #E2E8F0; border-radius:99px; padding:1px 8px;">{item["count_str"]}</span>'
            f'</div>'
            f'<div style="font-size:1.02rem; font-weight:900; color:#0F172A; margin-bottom:2px;">'
            f'📅 {item["date_fmt"]}</div>'
            f'<div style="font-size:0.74rem; font-weight:600; color:#64748B; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" '
            f'title="{item["details"]}">🏷️ {item["details"]}</div>'
            f'</div>'
        )

    banner_html = (
        '<div style="background:#F8FAFC; border:1px solid #CBD5E1; border-radius:12px; padding:12px 16px; margin-bottom:18px;">'
        '<div style="font-size:0.78rem; font-weight:800; color:#1E293B; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:10px;">'
        '🕒 Ultima Sessione Caricata per Sorgente (Controllo Anti-Doppioni)'
        '</div>'
        '<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(215px, 1fr)); gap:12px;">'
        f'{cards_html}'
        '</div>'
        '</div>'
    )
    st.markdown(banner_html, unsafe_allow_html=True)


# ==============================================================================
# ENTRY POINT PRINCIPALE MODULO IMPORT
# ==============================================================================
def render_import_dati(t: dict):
    render_page_header(
        "Importazione Dati & Sessioni Virtuali FIR",
        "Carica export CSV/Excel da GPExe e Catapult oppure genera e ricostruisci sessioni da medie storiche per tipologia",
        "bi-cloud-arrow-up-fill",
    )

    _render_last_uploads_banner()

    if st.session_state.get("user_role") == "viewer":
        st.warning("🔒 Accesso Riservato: il profilo attuale è in modalità Sola Lettura. Solo gli amministratori possono importare o modificare dati.")
        return

    cards_import = [
        {"id": "csv_import", "title": "Importa CSV", "desc": "Caricamento automatico file GPExe, Catapult e Oval", "icon": "bi-file-earmark-arrow-up"},
        {"id": "virtual_session", "title": "Sessione Virtuale", "desc": "Generazione e ricostruzione sessioni da medie storiche", "icon": "bi-magic"},
    ]

    active_sub = render_navigation_cards("import_dati", cards_import)

    if active_sub == "csv_import":
        _render_sub_csv_import(t)
    else:
        _render_sub_virtual_session(t)
