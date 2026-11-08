import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
from config import render_page_header, render_tab_navigation, render_action_bar
from pdf_generator import crea_pdf_report_gin, crea_pdf_scheda_atleta_oval, crea_pdf_archivio_oval
import utils


def _clean_and_render_html(html_str: str):
    """Rimuove spazi e a capo spuri prima del rendering per evitare che CommonMark lo interpreti come blocco di codice pre/code."""
    cleaned = "".join(line.strip() for line in html_str.splitlines() if line.strip())
    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def _get_available_weeks_options(start_date: str = "2024-08-01") -> tuple:
    """Genera l'elenco delle settimane (Lunedì — Domenica) a ritroso dal lunedì attuale fino al 1 Agosto 2024."""
    start_dt = pd.to_datetime(start_date)
    first_mon = start_dt - pd.Timedelta(days=start_dt.weekday())

    # Lunedì di riferimento attuale (allineato con il dataset o data odierna)
    now_dt = max(pd.Timestamp("2026-11-05"), pd.Timestamp.now())
    latest_mon = now_dt - pd.Timedelta(days=now_dt.weekday())  # Es. 2026-11-02
    prev_mon = latest_mon - pd.Timedelta(days=7)  # Es. 2026-10-26 (ultima settimana conclusa fino a domenica)

    weeks = []
    cur = latest_mon
    default_idx = 0
    while cur >= first_mon:
        end_w = cur + pd.Timedelta(days=6)
        mon_str = cur.strftime("%Y-%m-%d")
        cur_fmt = cur.strftime("%d/%m/%y")
        end_fmt = end_w.strftime("%d/%m/%y")
        if cur == prev_mon:
            lbl = f"{cur_fmt} – {end_fmt} (Ultima Conclusa)"
            default_idx = len(weeks)
        elif cur == latest_mon:
            lbl = f"{cur_fmt} – {end_fmt} (In Corso)"
        else:
            lbl = f"{cur_fmt} – {end_fmt}"
        weeks.append((mon_str, lbl))
        cur -= pd.Timedelta(days=7)
    return weeks, default_idx


def _build_gin_html_table(rep_df: pd.DataFrame, weeks_meta: list, ref_mon: str, ref_next_mon: str, season_lbl: str, sort_mode: str) -> str:
    if rep_df.empty:
        return "<div style='padding:16px; color:#64748B;'>Nessun giocatore trovato con i filtri selezionati.</div>"

    max_season_min = max(int(rep_df["season_min"].max()), 80)
    max_6w_min = max(int(rep_df["min_6w"].max()), 80)
    show_opta = sort_mode == "ruoli"
    title_str = (
        "Report 6\\12 Settimane G.I.N. - Ordine per Ruolo"
        if sort_mode == "ruoli"
        else "Report 6\\12 Settimane G.I.N. - Ranking minuti giocati stagionali"
    )

    # Week header columns
    w_headers_top = ""
    w_headers_dates = ""
    for w_i, wm in enumerate(weeks_meta):
        w_div_top = "border-right:2.5px solid #10B981;" if w_i == 5 else "border-right:1px solid #047857;"
        w_div_dt = "border-right:2.5px solid #10B981;" if w_i == 5 else ("border-right:1px solid #A7F3D0;" if w_i < 6 else "border-right:1px solid #CBD5E1;")
        w_min_w = "52px" if w_i < 6 else "36px"
        bg_dt = "#ECFDF5" if w_i < 6 else "#F1F5F9"
        col_dt = "#065F46" if w_i < 6 else "#475569"
        b_col = "#A7F3D0" if w_i < 6 else "#CBD5E1"

        w_headers_top += f"<th style='background:#064E3B; color:#FFFFFF; font-size:0.65rem; padding:4px 2px; text-align:center; border:1px solid #047857; {w_div_top} min-width:{w_min_w};'>{wm['label']}</th>"
        w_headers_dates += (
            f"<th style='background:{bg_dt}; color:{col_dt}; font-size:0.59rem; padding:2px 2px; text-align:center; border:1px solid {b_col}; {w_div_dt} line-height:1.15;'>"
            f"<div>{wm['start_disp'][:5]}</div><div style='border-top:1px solid {b_col};'>{wm['end_disp'][:5]}</div></th>"
        )

    opta_th_top = "<th style='background:#F8FAFC; color:#334155; font-size:0.65rem; padding:4px 6px; border:1px solid #CBD5E1; text-align:center;'>CODICE</th>" if show_opta else ""

    rows_html = ""
    prev_role = None
    for idx_r, r in rep_df.iterrows():
        role_val = str(r.get("role") or "")
        # Subtle role separator border when in "ruoli" mode
        top_border = "border-top: 2px solid #0284C7;" if (show_opta and prev_role is not None and role_val != prev_role) else ""
        prev_role = role_val

        bg_row = "#FFFFFF" if idx_r % 2 == 0 else "#F8FAFC"
        opta_td = f"<td style='padding:3px 6px; font-size:0.68rem; color:#64748B; text-align:center; border:1px solid #E2E8F0;'>{r.get('opta_id', '')}</td>" if show_opta else ""

        # 6W CAPS bar
        c6 = int(r["caps_6w"])
        c6_pct = min(100, int(round((c6 / 6.0) * 100)))
        c6_bar = (
            f"<div style='position:relative; width:100%; height:18px; background:#F1F5F9; border-radius:3px; overflow:hidden;'>"
            f"<div style='position:absolute; left:0; top:0; bottom:0; width:{c6_pct}%; background:rgba(56,189,248,0.45);'></div>"
            f"<div style='position:relative; z-index:1; text-align:center; font-weight:700; font-size:0.73rem; color:#0F172A; line-height:18px;'>{c6}</div></div>"
        )

        # 6W MINUTI bar
        m6 = int(r["min_6w"])
        m6_pct = min(100, int(round((m6 / max_6w_min) * 100))) if m6 > 0 else 0
        m6_bar = (
            f"<div style='position:relative; width:100%; height:18px; background:#F1F5F9; border-radius:3px; overflow:hidden;'>"
            f"<div style='position:absolute; left:0; top:0; bottom:0; width:{m6_pct}%; background:rgba(34,197,94,0.45);'></div>"
            f"<div style='position:relative; z-index:1; text-align:center; font-weight:800; font-size:0.73rem; color:#0F172A; line-height:18px;'>{m6}</div></div>"
        )

        cs_str = str(r["consec_starts_6w"])
        cs_bg = "#FEF08A" if cs_str.isdigit() and int(cs_str) >= 4 else "transparent"
        mc_val = int(r["max_consec_6w"])
        mc_bg = "#FEF08A" if mc_val >= 5 else "transparent"
        t12_val = int(r["tot_12w"])

        # 12 Weeks cells
        w_cells = ""
        w_mins = r["w_mins"]
        w_starts = r["w_starters"]
        w_tips = r["w_tips"]
        for w_i in range(12):
            wm_val = int(w_mins[w_i])
            is_st = bool(w_starts[w_i])
            tip = str(w_tips[w_i] or "").replace("'", "&#39;").replace('"', "&quot;")
            w_div = "border-right:2.5px solid #10B981;" if w_i == 5 else ""
            if wm_val > 0:
                w_pct = min(100, int(round((wm_val / 80.0) * 100)))
                cell_border = "2px solid #EF4444" if is_st else "1px solid #93C5FD"
                bar_color = "rgba(239,68,68,0.22)" if is_st else "rgba(125,211,252,0.38)"
                val_color = "#991B1B" if is_st else "#0369A1"
                w_cells += (
                    f"<td title='{tip}' style='padding:2px 2px; border:1px solid #E2E8F0; {w_div} text-align:center;'>"
                    f"<div style='position:relative; width:100%; height:18px; background:#F8FAFC; border:{cell_border}; border-radius:3px; overflow:hidden;'>"
                    f"<div style='position:absolute; left:0; top:0; bottom:0; width:{w_pct}%; background:{bar_color};'></div>"
                    f"<div style='position:relative; z-index:1; font-weight:700; font-size:0.69rem; color:{val_color}; line-height:15px;'>{wm_val}</div>"
                    f"</div></td>"
                )
            else:
                w_cells += f"<td style='padding:2px 2px; border:1px solid #E2E8F0; {w_div} text-align:center; color:#CBD5E1; font-size:0.68rem;'>0</td>"

        # Season CAPS & MINUTI bar (Red bar like Excel PDF)
        sc_val = int(r["season_caps"])
        sm_val = int(r["season_min"])
        sm_pct = min(100, int(round((sm_val / max_season_min) * 100))) if sm_val > 0 else 0
        sm_bar = (
            f"<div style='position:relative; width:100%; height:18px; background:#FFF1F2; border-radius:3px; overflow:hidden;'>"
            f"<div style='position:absolute; left:0; top:0; bottom:0; width:{sm_pct}%; background:rgba(244,63,94,0.48);'></div>"
            f"<div style='position:relative; z-index:1; text-align:right; padding-right:5px; font-weight:800; font-size:0.74rem; color:#881337; line-height:18px;'>{sm_val}</div></div>"
        )

        rows_html += (
            f"<tr style='background:{bg_row}; {top_border}'>"
            f"<td style='position:sticky; left:0; z-index:2; background:{bg_row}; box-shadow:2px 0 5px rgba(15,23,42,0.08); padding:3px 6px; font-weight:700; font-size:0.72rem; color:#0F172A; border:1px solid #CBD5E1; max-width:130px; overflow:hidden; text-overflow:ellipsis;'>{r['player_name']}</td>"
            f"{opta_td}"
            f"<td style='padding:3px 5px; font-size:0.68rem; color:#1E40AF; font-weight:600; border:1px solid #E2E8F0; border-right:2px solid #047857; text-align:center;'>{role_val}</td>"
            f"{w_cells}"
            f"<td style='padding:3px 5px; font-weight:800; font-size:0.72rem; text-align:center; color:#0F172A; border:1px solid #E2E8F0; border-left:2px solid #BE123C;'>{sc_val}</td>"
            f"<td style='padding:2px 4px; border:1px solid #E2E8F0; border-right:2px solid #B91C1C; min-width:60px;'>{sm_bar}</td>"
            f"<td style='padding:2px 3px; border:1px solid #E2E8F0; min-width:38px;'>{c6_bar}</td>"
            f"<td style='padding:2px 3px; border:1px solid #E2E8F0; min-width:50px;'>{m6_bar}</td>"
            f"<td style='padding:3px 4px; font-weight:700; font-size:0.70rem; text-align:center; background:{cs_bg}; border:1px solid #E2E8F0;'>{cs_str}</td>"
            f"<td style='padding:3px 4px; font-weight:700; font-size:0.70rem; text-align:center; background:{mc_bg}; border:1px solid #E2E8F0;'>{mc_val}</td>"
            f"<td style='padding:3px 4px; font-weight:700; font-size:0.70rem; text-align:center; color:#0369A1; border:1px solid #E2E8F0;'>{t12_val}</td>"
            f"</tr>"
        )

    left_colspan = 3 if show_opta else 2
    html = f"""
    <div style="overflow-x:auto; border:1px solid #CBD5E1; border-radius:10px; box-shadow:0 2px 8px rgba(15,23,42,0.05); background:#FFFFFF;">
        <div style="background:linear-gradient(90deg, #031926 0%, #0066B2 100%); color:#FFFFFF; padding:8px 14px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:800; font-size:0.95rem; letter-spacing:0.3px;">{title_str}</span>
            <span style="font-size:0.76rem; color:#E0F2FE;">Colonna NOME bloccata • Bordo Rosso = <b>STARTER (Titolare)</b> • Barra Blu = Minuti su 80'</span>
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr>
                    <th colspan="{left_colspan}" style="background:#EFF6FF; color:#1E3A8A; font-size:0.72rem; font-weight:800; padding:5px 8px; border:1px solid #BFDBFE; border-right:2px solid #047857; text-align:center;">
                        Settimana analizzata: {ref_mon} — {ref_next_mon}
                    </th>
                    {w_headers_top}
                    <th colspan="2" style="background:#FFF1F2; color:#9F1239; font-size:0.74rem; font-weight:800; padding:5px 6px; border:1px solid #FECDD3; border-left:2px solid #BE123C; border-right:2px solid #B91C1C; text-align:center;">
                        STAGIONE {season_lbl}
                    </th>
                    <th colspan="5" style="background:#FEF2F2; color:#B91C1C; font-size:0.80rem; font-weight:800; padding:5px 6px; border:1px solid #FECACA; text-align:center;">
                        6 WEEKS
                    </th>
                </tr>
                <tr>
                    <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; box-shadow:2px 0 5px rgba(15,23,42,0.08); color:#334155; font-size:0.66rem; padding:4px 6px; border:1px solid #CBD5E1; text-align:left;">NOME</th>
                    {opta_th_top}
                    <th style="background:#F8FAFC; color:#334155; font-size:0.66rem; padding:4px 5px; border:1px solid #CBD5E1; border-right:2px solid #047857; text-align:center;">RUOLO</th>
                    {w_headers_dates}
                    <th style="background:#FFF1F2; color:#9F1239; font-size:0.64rem; padding:3px 5px; border:1px solid #FECDD3; border-left:2px solid #BE123C; text-align:center;">CAPS</th>
                    <th style="background:#FFF1F2; color:#9F1239; font-size:0.64rem; padding:3px 5px; border:1px solid #FECDD3; border-right:2px solid #B91C1C; text-align:center;">MINUTI</th>
                    <th style="background:#FFF5F5; color:#991B1B; font-size:0.63rem; padding:3px 4px; border:1px solid #FECACA; text-align:center;">CAPS</th>
                    <th style="background:#FFF5F5; color:#991B1B; font-size:0.63rem; padding:3px 4px; border:1px solid #FECACA; text-align:center;">MINUTI</th>
                    <th title="Partite da Titolare consecutive nelle ultime 6 settimane ('/' se 0 min nell'ultima settimana)" style="background:#FFF5F5; color:#991B1B; font-size:0.58rem; padding:2px 3px; border:1px solid #FECACA; text-align:center; line-height:1.1;">TITOLARE<br>CONSEC. 6W</th>
                    <th title="Massimo di partite consecutive giocate nelle ultime 6 settimane" style="background:#FFF5F5; color:#991B1B; font-size:0.58rem; padding:2px 3px; border:1px solid #FECACA; text-align:center; line-height:1.1;">CONSEC.<br>MAX 6W</th>
                    <th title="Partite totali disputate nelle ultime 12 settimane" style="background:#FFF5F5; color:#991B1B; font-size:0.58rem; padding:2px 3px; border:1px solid #FECACA; text-align:center; line-height:1.1;">PARTITE<br>TOT 12W</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """
    return "".join(line.strip() for line in html.splitlines() if line.strip())


def _build_ultima_giornata_html(last_df: pd.DataFrame, week_Meta0: dict) -> str:
    if last_df.empty:
        return f"<div style='padding:14px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; color:#64748B;'>Nessuna gara registrata nella settimana {week_Meta0['start_disp']} – {week_Meta0['end_disp']}.</div>"

    rows_html = ""
    for i, r in last_df.iterrows():
        bg = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"
        ha = str(r.get("Home\\Away") or "HOME").upper()
        ha_bg = "#DCFCE7" if ha == "HOME" else "#FEE2E2"
        ha_fg = "#15803D" if ha == "HOME" else "#B91C1C"

        sc = str(r.get("Score") or "").strip()
        if sc.upper().startswith("W"):
            sc_bg, sc_fg = "#DCFCE7", "#15803D"
        elif sc.upper().startswith("L"):
            sc_bg, sc_fg = "#FEE2E2", "#B91C1C"
        else:
            sc_bg, sc_fg = "#FEF3C7", "#B45309"

        tit = str(r.get("Titolare") or "STARTER").upper()
        tit_bg = "#DCFCE7" if tit == "STARTER" else "#FFEDD5"
        tit_fg = "#15803D" if tit == "STARTER" else "#C2410C"

        rows_html += (
            f"<tr style='background:{bg};'>"
            f"<td style='padding:4px 8px; font-weight:700; font-size:0.73rem; color:#0F172A; border:1px solid #E2E8F0; white-space:nowrap;'>{r['NOME']}</td>"
            f"<td style='padding:4px 6px; font-size:0.71rem; color:#475569; text-align:center; border:1px solid #E2E8F0;'>{r['Data']}</td>"
            f"<td style='padding:4px 6px; font-weight:700; font-size:0.68rem; text-align:center; background:{ha_bg}; color:{ha_fg}; border:1px solid #E2E8F0;'>{ha}</td>"
            f"<td style='padding:4px 8px; font-size:0.71rem; color:#1E293B; border:1px solid #E2E8F0;'>{r['Match']}</td>"
            f"<td style='padding:4px 6px; font-weight:700; font-size:0.70rem; text-align:center; background:{sc_bg}; color:{sc_fg}; border:1px solid #E2E8F0; white-space:nowrap;'>{sc}</td>"
            f"<td style='padding:4px 6px; font-weight:700; font-size:0.68rem; text-align:center; background:{tit_bg}; color:{tit_fg}; border:1px solid #E2E8F0;'>{tit}</td>"
            f"<td style='padding:4px 6px; font-weight:800; font-size:0.74rem; text-align:center; color:#0F172A; border:1px solid #E2E8F0;'>{r['Minuti']}</td>"
            f"</tr>"
        )

    html_last = f"""
    <div style="overflow-x:auto; border:1px solid #CBD5E1; border-radius:10px; box-shadow:0 2px 8px rgba(15,23,42,0.05); background:#FFFFFF;">
        <div style="background:#031926; color:#FFFFFF; padding:7px 12px; font-weight:800; font-size:0.86rem; text-align:center; letter-spacing:0.4px;">
            ULTIMA GIORNATA ({week_Meta0['start_disp']} — {week_Meta0['end_disp']} • {len(last_df)} presenze)
        </div>
        <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#F1F5F9; color:#334155; font-size:0.66rem; font-weight:800;">
                    <th style="padding:5px 8px; border:1px solid #CBD5E1; text-align:left;">NOME</th>
                    <th style="padding:5px 6px; border:1px solid #CBD5E1; text-align:center;">Data</th>
                    <th style="padding:5px 6px; border:1px solid #CBD5E1; text-align:center;">Home\\Away</th>
                    <th style="padding:5px 8px; border:1px solid #CBD5E1; text-align:left;">Match</th>
                    <th style="padding:5px 6px; border:1px solid #CBD5E1; text-align:center;">Score</th>
                    <th style="padding:5px 6px; border:1px solid #CBD5E1; text-align:center;">Titolare</th>
                    <th style="padding:5px 6px; border:1px solid #CBD5E1; text-align:center;">Minuti</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """
    return "".join(line.strip() for line in html_last.splitlines() if line.strip())


def _render_manual_match_expander():
    if st.session_state.get("user_role") == "viewer":
        return

    players_df = utils.get_players_df()
    player_names = sorted(players_df["name_display"].dropna().unique().tolist()) if not players_df.empty else []
    if "Marcos Gallorini" not in player_names:
        player_names.append("Marcos Gallorini")
        player_names.sort()

    with st.expander("Aggiungi Manualmente Partita Non Monitorata da Oval", expanded=False):
        st.caption(
            "Inserisci qui una partita giocata da un atleta del Roster non presente nel flusso automatico Oval. "
            "Verrà salvata nell'archivio ufficiale e inclusa subito nel Report 6/12 Settimane G.I.N. e nelle medie Match (80')."
        )
        m1, m2, m3, m4 = st.columns([1.6, 1.1, 1.3, 1.3])
        sel_p = m1.selectbox("Giocatore Roster FIR", player_names, key="man_oval_player")

        default_club = ""
        if not players_df.empty and sel_p in players_df["name_display"].values:
            default_club = str(players_df[players_df["name_display"] == sel_p].iloc[0].get("club") or "")

        m_date = m2.date_input("Data Partita", value=date(2026, 10, 31), key="man_oval_date")
        m_team = m3.text_input("Squadra Giocatore", value=default_club, key="man_oval_team")
        m_opp = m4.text_input("Avversario (es. Valorugby, Viadana)", value="", key="man_oval_opp")

        m5, m6, m7, m8, m9 = st.columns([1.0, 1.2, 1.2, 1.0, 1.1])
        m_ha = m5.selectbox("Home / Away", ["HOME", "AWAY"], key="man_oval_ha")
        m_res = m6.text_input("Risultato (es. W 38-31, L 10-22)", value="W 24-17", key="man_oval_res")
        m_st = m7.selectbox("Impiego", ["STARTER (Titolare)", "FINISHER (Panchina)"], key="man_oval_st")
        m_min = m8.number_input("Minuti Giocati", min_value=1, max_value=100, value=80, step=1, key="man_oval_min")
        m_jer = m9.number_input("Maglia (opz. 1-23)", min_value=0, max_value=23, value=0, step=1, key="man_oval_jer")

        if st.button("Salva Partita Manuale nel Database Oval", type="primary", key="btn_save_manual_oval"):
            game_lbl = f"{m_team} vs {m_opp}" if m_ha == "HOME" else f"{m_opp} vs {m_team}"
            if not m_opp.strip():
                game_lbl = m_team
            utils.add_manual_oval_match({
                "player_name": sel_p,
                "date": str(m_date),
                "team_name": m_team,
                "opponent": m_opp,
                "game": game_lbl,
                "home_away": m_ha,
                "result": m_res,
                "is_starter": m_st.startswith("STARTER"),
                "minutes": m_min,
                "jersey": m_jer if m_jer > 0 else None,
            })
            st.success(f"Partita manuale aggiunta per **{sel_p}** ({m_date} • {game_lbl} • {m_min}' {m_st.split()[0]})!")
            st.rerun()


def _render_delete_oval_match_expander(key_prefix: str = "oval_del"):
    if st.session_state.get("user_role") == "viewer":
        return

    matches_cat = utils.get_oval_distinct_matches_df()
    dates_cat = utils.get_oval_distinct_dates_df()
    n_matches = len(matches_cat)
    n_dates = len(dates_cat)

    with st.expander(f"🗑️ Gestione Eliminazione Partite Oval (per Singolo Match o per Data • {n_matches} gare in archivio)", expanded=False):
        st.caption(
            "Cancellazione rapida dei dati Oval per consentire di **ricaricare un file corretto o aggiornato**. "
            "Puoi eliminare una **singola partita** oppure **tutte le partite di una data/giornata** in un solo clic."
        )
        if matches_cat.empty:
            st.info("Nessuna partita presente nell'archivio Oval.")
            return

        del_mode = st.radio(
            "Modalità di eliminazione:",
            ["🎯 Singola Partita (Match specifico)", "📅 Intera Data (Tutte le partite di quel giorno)"],
            horizontal=True,
            key=f"{key_prefix}_mode_radio",
        )

        if "Singola Partita" in del_mode:
            f_c1, f_c2 = st.columns([1.2, 2.8])
            teams_avail = ["Tutte le Squadre"] + sorted([t for t in matches_cat["teamName"].dropna().unique().tolist() if str(t).strip()])
            sel_tm_del = f_c1.selectbox("Filtra per Squadra", teams_avail, key=f"{key_prefix}_team_flt")

            sub_cat = matches_cat.copy()
            if sel_tm_del != "Tutte le Squadre":
                sub_cat = sub_cat[sub_cat["teamName"] == sel_tm_del].reset_index(drop=True)

            if sub_cat.empty:
                st.warning("Nessuna partita trovata per la squadra selezionata.")
                return

            match_labels = sub_cat["label"].tolist()
            sel_lbl = f_c2.selectbox("Seleziona la Partita da Eliminare", match_labels, key=f"{key_prefix}_match_sel")
            sel_row = sub_cat[sub_cat["label"] == sel_lbl].iloc[0]

            m_date_val = str(sel_row["match_date"])
            m_game_val = str(sel_row["game"])
            m_team_val = str(sel_row["teamName"])
            m_nrec = int(sel_row["n_records"])
            m_prev = str(sel_row["players_preview"])

            st.markdown(
                f"""
                <div style="background:#FEF2F2; border:1px solid #FECACA; border-left:4px solid #DC2626; border-radius:8px; padding:9px 12px; margin:6px 0 10px 0; font-size:0.80rem; color:#7F1D1D;">
                    <b>Partita selezionata:</b> {m_date_val} • <b>{m_game_val or m_team_val}</b> ({m_team_val}) — <b>{m_nrec} record giocatori</b><br/>
                    <span style="font-size:0.74rem; color:#991B1B;"><b>Atleti coinvolti:</b> {m_prev}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            b_c1, b_c2 = st.columns([1.8, 2.2])
            confirm_chk = b_c1.checkbox(
                f"Confermo l'eliminazione dei {m_nrec} record di questa gara",
                value=False,
                key=f"{key_prefix}_confirm_chk",
            )
            if b_c2.button(
                f"🗑️ Elimina Partita ({m_nrec} atleti) dal Database",
                type="primary",
                disabled=not confirm_chk,
                use_container_width=True,
                key=f"{key_prefix}_btn_exec",
            ):
                removed = utils.delete_oval_match_by_game(m_date_val, m_game_val, m_team_val)
                st.success(f"✅ Eliminata la partita **{m_date_val} • {m_game_val}** ({removed} record rimossi). Ora puoi ricaricare il match!")
                st.rerun()

        else:
            # Eliminazione per INTERA DATA
            if dates_cat.empty:
                st.warning("Nessuna data valida trovata nell'archivio.")
                return

            d_labels = dates_cat["label"].tolist()
            sel_date_lbl = st.selectbox("Seleziona la Data / Giornata da Eliminare", d_labels, key=f"{key_prefix}_date_sel")
            sel_date_row = dates_cat[dates_cat["label"] == sel_date_lbl].iloc[0]

            d_val = str(sel_date_row["match_date"])
            d_nmatches = int(sel_date_row["n_matches"])
            d_nrec = int(sel_date_row["n_records"])
            d_games = str(sel_date_row["games_summary"])
            d_teams = str(sel_date_row["teams_summary"])

            st.markdown(
                f"""
                <div style="background:#FFF1F2; border:1px solid #FDA4AF; border-left:4px solid #E11D48; border-radius:8px; padding:10px 14px; margin:6px 0 10px 0; font-size:0.82rem; color:#881337;">
                    <b>📅 Data selezionata:</b> <span style="font-size:0.95rem; font-weight:800;">{d_val}</span> — <b>{d_nmatches} partite</b> ({d_nrec} record atleti totali)<br/>
                    <b>Partite in questa data:</b> {d_games or '-'}<br/>
                    <b>Squadre:</b> {d_teams or '-'}
                </div>
                """,
                unsafe_allow_html=True,
            )

            b_d1, b_d2 = st.columns([1.8, 2.2])
            confirm_date_chk = b_d1.checkbox(
                f"Confermo l'eliminazione di TUTTE le gare del {d_val} ({d_nrec} record)",
                value=False,
                key=f"{key_prefix}_confirm_date_chk",
            )
            if b_d2.button(
                f"🗑️ Elimina Tutte le Partite del {d_val} ({d_nrec} record)",
                type="primary",
                disabled=not confirm_date_chk,
                use_container_width=True,
                key=f"{key_prefix}_btn_date_exec",
            ):
                removed = utils.delete_oval_matches_by_date(d_val)
                st.success(f"✅ Eliminate con successo tutte le partite del **{d_val}** ({removed} record rimossi dal database Oval)!")
                st.rerun()


def render_oval_match(t: dict):
    df = utils.get_oval_matches_df()
    total_rows = len(df)
    n_players = df["fir_player_name"].nunique() if not df.empty and "fir_player_name" in df.columns else 0

    render_page_header(
        "Database Oval Match & Report 6/12 Settimane G.I.N.",
        f"Monitoraggio minutaggio stagionale (1 Agosto – 30 Luglio), Report 6/12 Settimane G.I.N., inserimento gare manuali e archivio Oval ({total_rows:,} gare)",
        "bi-trophy-fill",
    )

    active_tab = render_tab_navigation(
        "oval_match",
        [
            ("report_gin", "🏆 Report 6/12 Settimane G.I.N. (Minuti)", "bi-grid-3x3-gap-fill"),
            ("scheda_atleta", "👤 Scheda Atleta & Minutaggio Storico", "bi-person-badge-fill"),
            ("archivio", f"📋 Archivio Gare Oval & Statistiche ({total_rows:,})", "bi-table"),
        ],
    )

    if active_tab == "report_gin":
        _render_tab_report_gin(df)
    elif active_tab == "scheda_atleta":
        _render_tab_scheda_atleta(df)
    else:
        _render_tab_archivio(df)


def _render_gin_list_manager():
    p_df = utils.get_players_df().copy()
    if p_df.empty:
        return
    gin_current = set(utils.get_gin_player_names())
    n_gin = len(gin_current)
    n_tot = len(p_df)

    with st.expander(f"Configura Lista G.I.N. da Monitorare ({n_gin} atleti selezionati su {n_tot} nel Roster)", expanded=False):
        st.caption(
            "Seleziona o deseleziona i giocatori che compongono la **Lista G.I.N. (Giocatori di Interesse Nazionale)** da monitorare nel Report 6/12 Settimane. "
            "Puoi spuntare i singoli giocatori nella tabella, oppure importare rapidamente i convocati di un Raduno."
        )
        b1, b2, b3, b4 = st.columns([1.3, 1.2, 1.5, 1.3])
        if b1.button("Ripristina Lista G.I.N. Ufficiale (71 atleti)", use_container_width=True, key="btn_gin_reset_def"):
            utils.reset_gin_to_default()
            st.success("Lista G.I.N. ripristinata ai 71 atleti ufficiali del modello FIR.")
            st.rerun()
        if b2.button("Seleziona Tutti (Intero Roster)", use_container_width=True, key="btn_gin_sel_all"):
            utils.save_gin_player_names(p_df["name_display"].dropna().astype(str).tolist())
            st.success("Tutti gli atleti del Roster sono stati inclusi nella Lista G.I.N.")
            st.rerun()

        camps_df = utils.get_camps_df()
        camp_opts = ["Seleziona un Raduno per importare..."]
        camp_map = {}
        if not camps_df.empty:
            for _, cr in camps_df.sort_values("start_date", ascending=False).iterrows():
                lbl = f"{cr.get('name', 'Raduno')} ({cr.get('start_date', '')})"
                camp_opts.append(lbl)
                camp_map[lbl] = int(cr["id"])
        sel_camp_lbl = b3.selectbox("Importa Atleti da Raduno", camp_opts, label_visibility="collapsed", key="sel_gin_from_camp")
        if b4.button("Aggiungi Raduno alla Lista G.I.N.", use_container_width=True, disabled=(sel_camp_lbl not in camp_map), key="btn_gin_add_camp"):
            cid = camp_map[sel_camp_lbl]
            cp_df = utils.get_camp_players_df()
            if not cp_df.empty:
                c_pids = set(cp_df[cp_df["camp_id"] == cid]["player_id"].dropna().astype(int).tolist())
                c_names = set(p_df[p_df["id"].astype(int).isin(c_pids)]["name_display"].dropna().astype(str).tolist())
                updated_gin = sorted(list(gin_current | c_names))
                utils.save_gin_player_names(updated_gin)
                st.success(f"Aggiunti {len(c_names)} atleti del raduno alla Lista G.I.N. (Totale: {len(updated_gin)}).")
                st.rerun()

        edit_df = p_df[["name_display", "role", "department", "club", "birth_year", "opta_id"]].copy()
        edit_df["Includi_GIN"] = edit_df["name_display"].astype(str).isin(gin_current)
        edit_df = edit_df[["Includi_GIN", "name_display", "role", "department", "club", "birth_year", "opta_id"]].sort_values(
            by=["Includi_GIN", "department", "role", "name_display"], ascending=[False, True, True, True]
        ).reset_index(drop=True)

        edited = st.data_editor(
            edit_df,
            hide_index=True,
            use_container_width=True,
            height=300,
            key="gin_list_editor_table",
            column_config={
                "Includi_GIN": st.column_config.CheckboxColumn("Monitora in G.I.N.", default=True),
                "name_display": st.column_config.TextColumn("Giocatore", disabled=True),
                "role": st.column_config.TextColumn("Ruolo", disabled=True),
                "department": st.column_config.TextColumn("Reparto", disabled=True),
                "club": st.column_config.TextColumn("Squadra / Club", disabled=True),
                "birth_year": st.column_config.TextColumn("Anno", disabled=True),
                "opta_id": st.column_config.TextColumn("Codice Oval", disabled=True),
            },
            disabled=(st.session_state.get("user_role") == "viewer"),
        )
        if st.session_state.get("user_role") == "viewer":
            st.caption("🔒 Modifica lista G.I.N. riservata agli amministratori.")
        else:
            if st.button("Salva Lista G.I.N. Personalizzata", type="primary", key="btn_save_custom_gin_list"):
                chosen = edited[edited["Includi_GIN"] == True]["name_display"].dropna().astype(str).tolist()
                utils.save_gin_player_names(chosen)
                st.success(f"Lista G.I.N. salvata con successo ({len(chosen)} giocatori monitorati)!")
                st.rerun()


def _render_tab_report_gin(df: pd.DataFrame):
    # Top expanders: GIN List Manager + Manual Match Entry + Delete Match
    col_exp1, col_exp2, col_exp3 = st.columns(3)
    with col_exp1:
        _render_gin_list_manager()
    with col_exp2:
        _render_manual_match_expander()
    with col_exp3:
        _render_delete_oval_match_expander(key_prefix="oval_del_gin")

    # Filtri Riga 1 (Ordinamento, Settimana da Analizzare, Reparto)
    c1, c2, c3 = st.columns([1.8, 2.8, 1.2])
    sort_mode = c1.selectbox(
        "Ordinamento Report G.I.N.",
        ["minuti", "ruoli", "min_6w"],
        format_func=lambda k: {
            "minuti": "1. Ranking Minuti Stagionali (1 Ago – 30 Lug)",
            "ruoli": "2. Ordine per Ruolo (Pilone → Ala/Estremo)",
            "min_6w": "3. Ranking Minuti 6 WEEKS",
        }[k],
        index=0,
        key="gin_sort_mode",
    )
    week_options, default_week_idx = _get_available_weeks_options("2024-08-01")
    week_labels = [w[1] for w in week_options]
    week_dict = {w[1]: w[0] for w in week_options}

    sel_week_lbl = c2.selectbox(
        "Settimana da Analizzare",
        week_labels,
        index=default_week_idx,
        help="In automatico posizionato sull'ultima settimana conclusa fino a domenica. Seleziona per analizzare qualsiasi settimana a ritroso dal 2024.",
        key="gin_sel_week_dropdown",
    )
    ref_mon_input = week_dict[sel_week_lbl]
    dept_filter = c3.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="gin_dept_filter")

    # Filtri Riga 2 (Filtro Ruolo, Ambito GIN, Ricerca Atleta)
    c4, c5, c6 = st.columns([1.4, 1.6, 2.8])
    roles_avail = ["Tutti i Ruoli", "Pilone", "Tallonatore", "Seconda Linea", "Terza Linea", "Mediano di Mischia", "Apertura", "Centro", "Ala", "Estremo"]
    role_filter = c4.selectbox("Filtro Ruolo", roles_avail, key="gin_role_filter")

    gin_scope = c5.selectbox(
        "Ambito Monitoraggio",
        ["only_gin", "all_roster"],
        format_func=lambda x: "Solo Lista G.I.N." if x == "only_gin" else "Tutto il Roster FIR",
        index=0,
        key="gin_scope_filter",
    )
    search_q = c6.text_input("Cerca Giocatore / Club", placeholder="Nome o squadra...", key="gin_search_q")

    rep_data = utils.build_gin_6_12_report(ref_mon_input, sort_mode=sort_mode, only_gin=(gin_scope == "only_gin"))
    rep_df = rep_data["report_df"]
    weeks_meta = rep_data["weeks_meta"]
    last_round_df = rep_data["last_round_df"]

    if not rep_df.empty:
        if dept_filter != "Tutti":
            rep_df = rep_df[rep_df["department"] == dept_filter].copy()
        if role_filter != "Tutti i Ruoli":
            rep_df = rep_df[rep_df["role"] == role_filter].copy()
        if search_q.strip():
            q = search_q.strip().lower()
            rep_df = rep_df[
                rep_df["player_name"].astype(str).str.lower().str.contains(q)
                | rep_df["club"].astype(str).str.lower().str.contains(q)
            ].copy()
        rep_df = rep_df.reset_index(drop=True)

    # Summary KPIs
    k1, k2, k3, k4 = st.columns(4)
    n_atleti = len(rep_df)
    n_attivi_stag = int((rep_df["season_min"] > 0).sum()) if not rep_df.empty else 0
    avg_min_stag = int(round(rep_df["season_min"].mean())) if not rep_df.empty else 0
    avg_min_6w = int(round(rep_df["min_6w"].mean())) if not rep_df.empty else 0
    n_last_round = len(last_round_df)

    k1.metric("Atleti nel Report G.I.N.", f"{n_atleti}", f"{n_attivi_stag} con min > 0")
    k2.metric(f"Media Minuti Stagione {rep_data['season_label']}", f"{avg_min_stag} min", f"{avg_min_stag/80:.1f} gare eq.")
    k3.metric("Media Minuti 6 WEEKS", f"{avg_min_6w} min", f"{avg_min_6w/80:.1f} gare eq.")
    k4.metric("Presenze Ultima Giornata", f"{n_last_round}", f"{weeks_meta[0]['start_disp']} - {weeks_meta[0]['end_disp']}")

    # Enterprise Action Bar con esportazione PDF integrata (A4 Orizzontale FIR)
    action_meta = [
        ("Settimana", f"{weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']}"),
        ("Stagione", rep_data["season_label"]),
        ("Atleti Monitorati", f"{n_atleti} ({n_attivi_stag} attivi)"),
        ("Ordinamento", "Ranking Minuti" if sort_mode == "minuti" else ("Ruoli FIR" if sort_mode == "ruoli" else "Minuti 6W")),
        ("Filtro Reparto", dept_filter),
    ]

    if sort_mode == "ruoli":
        pdf_opts = {
            "Report Ufficiale Allenatori (Tabella Leggibile per Ruolo + Ultima Giornata)": "default",
            "Report Suddiviso Reparti (2 Fogli: Avanti & TreQuarti + Ultima Giornata)": "ruoli_split",
            "Report Compatto Singola Pagina (Tutto in 1 Pagina + Ultima Giornata)": "completo_1pag",
            "Solo Avanti (1 Foglio)": "solo_avanti",
            "Solo TreQuarti (1 Foglio)": "solo_trequarti",
            "Solo Tabella 6/12 Settimane": "tabella_gin",
            "Solo Ultima Giornata (1 Foglio)": "ultima_giornata",
        }
    else:
        pdf_opts = {
            "Report Ufficiale Allenatori (Tabella Leggibile + Ultima Giornata)": "default",
            "Report Compatto Singola Pagina (Tutto in 1 Pagina + Ultima Giornata)": "completo_1pag",
            "Solo Tabella 6/12 Settimane": "tabella_gin",
            "Report Suddiviso per Reparto (Avanti & TreQuarti)": "ruoli_split",
            "Solo Ultima Giornata (1 Foglio)": "ultima_giornata",
        }

    render_action_bar(
        meta_items=action_meta,
        pdf_options=pdf_opts,
        pdf_key=f"oval_gin_{sort_mode}_{ref_mon_input}_{dept_filter}_{role_filter}",
        generate_fn=lambda sub_code: crea_pdf_report_gin(
            sub_code=sub_code,
            rep_df=rep_df,
            weeks_meta=weeks_meta,
            last_round_df=last_round_df,
            rep_meta=rep_data,
            sort_mode=sort_mode,
        ),
        filename_fn=lambda sub_code: f"FIR_Report_GIN_{sort_mode}_{ref_mon_input}.pdf",
    )

    gin_html = _build_gin_html_table(
        rep_df,
        weeks_meta,
        rep_data["ref_monday_disp"],
        rep_data["ref_next_monday_disp"],
        rep_data["season_label"],
        sort_mode,
    )
    ug_html = _build_ultima_giornata_html(last_round_df, weeks_meta[0])

    # Visualizzazione estesa a tutto schermo
    _clean_and_render_html(gin_html)
    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    _clean_and_render_html(ug_html)


def _render_tab_scheda_atleta(df: pd.DataFrame):
    p_df = utils.get_players_df().copy()
    gin_names = set(utils.get_gin_player_names())

    # Barra di Selezione Giocatore & Filtri Rapidi
    s1, s2, s3, s4 = st.columns([1.5, 1.2, 1.3, 2.8])

    scope_choice = s1.selectbox(
        "Ambito Giocatori",
        ["gin", "all"],
        format_func=lambda x: "Solo Lista G.I.N. (Monitorati)" if x == "gin" else "Tutto il Roster FIR & Oval",
        index=0,
        key="prof_scope_filter",
    )

    dept_choice = s2.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="prof_dept_filter")
    roles_opts = ["Tutti i Ruoli", "Pilone", "Tallonatore", "Seconda Linea", "Terza Linea", "Mediano di Mischia", "Apertura", "Centro", "Ala", "Estremo"]
    role_choice = s3.selectbox("Filtro Ruolo", roles_opts, key="prof_role_filter")

    # Costruisci l'elenco dei giocatori filtrati
    avail_players_df = p_df.copy() if not p_df.empty else pd.DataFrame()
    if not avail_players_df.empty:
        if scope_choice == "gin":
            avail_players_df = avail_players_df[avail_players_df["name_display"].astype(str).str.strip().isin(gin_names)]
        if dept_choice != "Tutti":
            avail_players_df = avail_players_df[avail_players_df["department"] == dept_choice]
        if role_choice != "Tutti i Ruoli":
            avail_players_df = avail_players_df[avail_players_df["role"] == role_choice]
        avail_names = sorted(avail_players_df["name_display"].dropna().astype(str).unique().tolist())
    else:
        avail_names = sorted([str(p) for p in df["fir_player_name"].dropna().unique() if str(p).strip()])

    if not avail_names:
        st.warning("Nessun atleta trovato con i filtri selezionati.")
        return

    # Default index: Lamaro se presente, altrimenti il primo
    default_p_idx = 0
    for target in ["Michele Lamaro", "Ange Capuozzo", "Paolo Garbisi", "Danilo Fischetti"]:
        if target in avail_names:
            default_p_idx = avail_names.index(target)
            break

    sel_player_name = s4.selectbox(
        "Seleziona Atleta da Ispezionare",
        avail_names,
        index=default_p_idx,
        help="Cerca qualsiasi giocatore per visualizzare il minutaggio storico, le squadre in cui ha militato, le presenze da titolare e il dettaglio gare.",
        key="prof_sel_player_name",
    )

    prof = utils.get_athlete_oval_career_profile(sel_player_name)
    if not prof.get("has_oval_data"):
        st.info(f"Nessuna partita ufficiale registrata nel database Oval per **{sel_player_name}**.")
        return

    c_tot = prof["career_totals"]
    s_curr = prof["curr_season_totals"]
    p_name = prof["player_name"]

    # 1. Player Identity Header Card
    photo_b64 = prof.get("photo_b64")
    if photo_b64:
        photo_html = f'<img src="data:image/jpeg;base64,{photo_b64}" style="width:96px; height:122px; object-fit:cover; border-radius:12px; border:2.5px solid #D4AF37; box-shadow:0 6px 14px rgba(0,0,0,0.4);" alt="{p_name}">'
    else:
        initials = "".join([part[0] for part in p_name.split()[:2]]).upper()
        photo_html = f"""
        <div style="width:96px; height:122px; border-radius:12px; background:linear-gradient(135deg, #002B49 0%, #0066B2 100%); border:2.5px solid #D4AF37; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#D4AF37; font-weight:800; font-size:2.0rem; box-shadow:0 6px 14px rgba(0,0,0,0.35);">
            <span>{initials}</span>
            <span style="font-size:0.62rem; color:#93C5FD; font-weight:700; margin-top:3px; letter-spacing:0.05em;">FIR</span>
        </div>
        """

    gin_badge = (
        '<span style="background:#D4AF37; color:#031926; padding:3px 10px; border-radius:999px; font-weight:800; font-size:0.72rem; letter-spacing:0.04em;">G.I.N. MONITORATO</span>'
        if prof.get("is_gin")
        else '<span style="background:rgba(255,255,255,0.18); color:#FFFFFF; padding:3px 10px; border-radius:999px; font-weight:700; font-size:0.72rem;">ROSTER ALLARGATO</span>'
    )

    tot_min_disp = f"{c_tot['total_min']:,}".replace(",", ".")

    card_html = f"""
    <div style="background:linear-gradient(135deg, #031926 0%, #002B49 60%, #004B87 100%); border-radius:14px; padding:20px 24px; margin: 12px 0 20px 0; border-left:6px solid #D4AF37; box-shadow:0 8px 24px rgba(0,43,73,0.18); color:#FFFFFF;">
        <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px;">
            <div style="display:flex; align-items:center; gap:20px;">
                {photo_html}
                <div>
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                        <span style="font-size:0.70rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">FEDERAZIONE ITALIANA RUGBY &bull; NAZIONALE MAGGIORE</span>
                        {gin_badge}
                    </div>
                    <h2 style="margin:0; font-size:1.65rem; font-weight:800; letter-spacing:-0.02em; color:#FFFFFF;">{p_name}</h2>
                    <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:8px;">
                        <span style="background:#0284C7; color:#FFFFFF; padding:3px 10px; border-radius:6px; font-weight:700; font-size:0.74rem;">{prof['role']}</span>
                        <span style="background:rgba(255,255,255,0.12); color:#E0F2FE; padding:3px 10px; border-radius:6px; font-weight:600; font-size:0.74rem;">{prof['department']}</span>
                        <span style="background:#059669; color:#FFFFFF; padding:3px 10px; border-radius:6px; font-weight:700; font-size:0.74rem;">{prof['club']}</span>
                        <span style="background:rgba(255,255,255,0.08); color:#CBD5E1; padding:3px 10px; border-radius:6px; font-size:0.74rem;">Anno {prof['birth_year']} ({prof['age_str']})</span>
                        <span style="color:#94A3B8; font-size:0.74rem;">Codice Oval: <b>{prof['opta_id']}</b></span>
                    </div>
                </div>
            </div>
            <div style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.14); border-radius:10px; padding:12px 18px; min-width:240px;">
                <div style="font-size:0.68rem; font-weight:700; text-transform:uppercase; color:#D4AF37; margin-bottom:6px; letter-spacing:0.08em;">RIEPILOGO RAPIDO CARRIERA</div>
                <div style="font-size:0.80rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span style="color:#CBD5E1;">Presenze Totali (CAPS):</span> <b style="color:#FFFFFF;">{c_tot['total_caps']}</b>
                </div>
                <div style="font-size:0.80rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span style="color:#CBD5E1;">Minuti Totali Giocati:</span> <b style="color:#38BDF8;">{tot_min_disp}' min</b>
                </div>
                <div style="font-size:0.80rem; display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span style="color:#CBD5E1;">Gare da Titolare:</span> <b style="color:#34D399;">{c_tot['total_starts']} ({c_tot['starter_pct']}%)</b>
                </div>
                <div style="font-size:0.80rem; display:flex; justify-content:space-between;">
                    <span style="color:#CBD5E1;">Record Vittorie:</span> <b style="color:#FBBF24;">{c_tot['win_pct']}% W</b>
                </div>
            </div>
        </div>
    </div>
    """
    _clean_and_render_html(card_html)

    # Slot in alto per la Action Bar di esportazione PDF Dossier Atleta (popolato con i grafici e filtri gare)
    pdf_action_slot = st.container()
    fig_s = None
    fig_pie = None
    fig_m = None
    sel_season = "Tutte le Stagioni"
    sel_team_m = "Tutte le Squadre"
    sel_starter = "Tutti"
    sel_outcome = "Tutti"

    # 2. Top KPI Cards Row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        "Presenze Totali (CAPS)",
        f"{c_tot['total_caps']}",
        f"{c_tot['total_starts']} Titolare • {c_tot['total_bench']} Sub",
    )
    k2.metric(
        "Minuti Totali Oval",
        f"{c_tot['total_min']:,}' min".replace(",", "."),
        f"Media {c_tot['avg_min_match']}' a gara",
    )
    k3.metric(
        "Stagione Attuale (2026/27)",
        f"{s_curr['minutes']}' min",
        f"{s_curr['caps']} presenze • {s_curr['starter_pct']}% Starter",
    )
    k4.metric(
        "Squadre Rappresentate",
        f"{c_tot['teams_count']} Team",
        ", ".join(c_tot["teams_list"][:2]) if c_tot["teams_list"] else "Club / Naz.",
    )
    k5.metric(
        "Record Vittorie Carriera",
        f"{c_tot['win_pct']}%",
        f"{c_tot['total_wins']} V • {c_tot['total_losses']} S • {c_tot['total_draws']} P",
    )

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # 3. SEZIONE 1: Analisi Storica per Stagione (2026/27 & Precedenti)
    _clean_and_render_html(
        """
        <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid #0066B2; padding-bottom:6px; margin-bottom:12px;">
            <div style="font-size:1.05rem; font-weight:800; color:#0F172A;">
                <i class="bi bi-calendar-range" style="color:#0066B2; margin-right:6px;"></i>
                Minutaggi & Presenze per Stagione (1 Agosto – 30 Luglio)
            </div>
            <div style="font-size:0.75rem; color:#64748B;">Analisi longitudinale completa delle stagioni sportive registrate in archivio Oval</div>
        </div>
        """
    )

    s_df = prof["seasons_df"]
    s_sum_df = prof.get("seasons_summary_df", pd.DataFrame())
    if not s_df.empty:
        max_s_min = max(int(s_df["minutes"].max()), 1)
        max_s_caps = max(int(s_df["caps"].max()), 1)

        s_rows_html = ""
        for _, sr in s_df.iterrows():
            s_lbl = str(sr["season"])
            is_sub = sr.get("is_subtotal", False)
            is_cur_s = ("2026/27" in s_lbl and not is_sub)

            if is_sub:
                bg_tr = "#F1F5F9"
                bd_tr = "border-top: 1.5px dashed #94A3B8; border-bottom: 1.5px solid #CBD5E1;"
                cur_tag = ""
                s_lbl_disp = f"<span style='font-weight:800; color:#002B49;'>{s_lbl}</span>"
                team_cell = f"<span style='font-size:0.72rem; font-weight:800; color:#475569;'>{sr['team']}</span>"
            else:
                bg_tr = "#FEF3C7" if is_cur_s else "#FFFFFF"
                bd_tr = "border: 2px solid #D97706;" if is_cur_s else ""
                cur_tag = " <span style='background:#F59E0B; color:#FFFFFF; padding:1px 5px; border-radius:3px; font-size:0.65rem; font-weight:800;'>IN CORSO</span>" if is_cur_s else ""
                s_lbl_disp = f"<span style='font-weight:700; color:#0F172A;'>{s_lbl}</span>{cur_tag}"
                tm_name = str(sr["team"])
                tm_bg = "#0066B2" if "ital" in tm_name.lower() else "#059669"
                flag = "🇮🇹 " if "ital" in tm_name.lower() else "🛡️ "
                team_cell = f"<span style='display:inline-block; margin:1px 2px; padding:2px 8px; border-radius:4px; font-size:0.72rem; font-weight:700; background:{tm_bg}; color:#FFFFFF;'>{flag}{tm_name}</span>"

            # Minutes bar / display
            m_val = int(sr["minutes"])
            m_disp = f"{m_val:,}".replace(",", ".")
            m_pct = min(100, int(round((m_val / max_s_min) * 100))) if m_val > 0 else 0
            m_bar = (
                f"<div style='position:relative; width:100%; height:19px; background:#F1F5F9; border-radius:3px; overflow:hidden; border:1px solid #CBD5E1;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{m_pct}%; background:rgba(34,197,94,0.45);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:800; font-size:0.74rem; color:#064E3B; line-height:17px; text-align:center;'>{m_disp}' min</div>"
                f"</div>"
            )

            # Caps bar / display
            c_val = int(sr["caps"])
            c_pct = min(100, int(round((c_val / max_s_caps) * 100))) if c_val > 0 else 0
            c_bar = (
                f"<div style='position:relative; width:100%; height:19px; background:#F1F5F9; border-radius:3px; overflow:hidden; border:1px solid #CBD5E1;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{c_pct}%; background:rgba(56,189,248,0.40);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:800; font-size:0.73rem; color:#0369A1; line-height:17px; text-align:center;'>{c_val}</div>"
                f"</div>"
            )

            # Max 6W cell
            m6w_v = sr.get("max_6w_min")
            if m6w_v is not None and pd.notna(m6w_v) and str(m6w_v) not in ("-", "None", "nan"):
                m6w_cell = f"<span style='background:#002B49; color:#FFFFFF; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.72rem; border:1px solid #D4AF37;'>{int(m6w_v)}' min</span>"
            else:
                m6w_cell = "<span style='color:#94A3B8; font-size:0.72rem;'>-</span>"

            st_f = f"{sr['starts']} <span style='font-size:0.67rem; color:#64748B;'>({sr['starter_pct']:.0f}%)</span>" if not is_sub else f"<b>{sr['starts']} ({sr['starter_pct']:.0f}%)</b>"
            bench_f = str(sr["bench"]) if not is_sub else f"<b>{sr['bench']}</b>"
            avg_f = f"{sr['avg_minutes']:.1f}'" if not is_sub else f"<b>{sr['avg_minutes']:.1f}'</b>"

            s_rows_html += f"""
            <tr style='background:{bg_tr}; {bd_tr}'>
                <td style='padding:5px 8px; font-size:0.78rem; border:1px solid #CBD5E1; white-space:nowrap;'>{s_lbl_disp}</td>
                <td style='padding:4px 6px; border:1px solid #E2E8F0;'>{team_cell}</td>
                <td style='padding:3px 4px; border:1px solid #E2E8F0; min-width:55px;'>{c_bar}</td>
                <td style='padding:4px 6px; text-align:center; font-weight:700; font-size:0.73rem; color:#0F172A; border:1px solid #E2E8F0;'>{st_f}</td>
                <td style='padding:4px 6px; text-align:center; font-size:0.72rem; color:#475569; border:1px solid #E2E8F0;'>{bench_f}</td>
                <td style='padding:3px 6px; border:1px solid #E2E8F0; min-width:85px;'>{m_bar}</td>
                <td style='padding:4px 6px; text-align:center; font-weight:700; font-size:0.73rem; color:#0F172A; border:1px solid #E2E8F0;'>{avg_f}</td>
                <td style='padding:4px 6px; text-align:center; border:1px solid #E2E8F0;'>{m6w_cell}</td>
            </tr>
            """

        tot_c_min = f"{c_tot['total_min']:,}".replace(",", ".")
        peak_6w_tot = c_tot.get("peak_6w_min", 0)
        tot_s_html = f"""
        <tr style='background:#E2E8F0; border-top:2.5px solid #002B49;'>
            <td style='padding:6px 8px; font-weight:800; font-size:0.80rem; color:#0F172A; border:1px solid #94A3B8;'>TOTALE CARRIERA</td>
            <td style='padding:5px 6px; font-weight:700; font-size:0.74rem; color:#334155; border:1px solid #94A3B8;'>{c_tot['teams_count']} Squadre (Club + Naz.)</td>
            <td style='padding:5px 6px; text-align:center; font-weight:800; font-size:0.78rem; color:#0369A1; border:1px solid #94A3B8;'>{c_tot['total_caps']} CAPS</td>
            <td style='padding:5px 6px; text-align:center; font-weight:800; font-size:0.75rem; color:#0F172A; border:1px solid #94A3B8;'>{c_tot['total_starts']} ({c_tot['starter_pct']:.0f}%)</td>
            <td style='padding:5px 6px; text-align:center; font-weight:700; font-size:0.74rem; color:#475569; border:1px solid #94A3B8;'>{c_tot['total_bench']}</td>
            <td style='padding:5px 6px; text-align:center; font-weight:800; font-size:0.80rem; color:#064E3B; border:1px solid #94A3B8;'>{tot_c_min}' min</td>
            <td style='padding:5px 6px; text-align:center; font-weight:800; font-size:0.75rem; color:#0F172A; border:1px solid #94A3B8;'>{c_tot['avg_min_match']:.1f}'</td>
            <td style='padding:5px 6px; text-align:center; font-weight:800; font-size:0.76rem; border:1px solid #94A3B8;'><span style='background:#D4AF37; color:#002B49; padding:2px 8px; border-radius:4px; font-weight:800;'>{peak_6w_tot}' min</span></td>
        </tr>
        """

        table_seasons_html = f"""
        <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; overflow-x:auto; box-shadow:0 2px 8px rgba(15,23,42,0.05); margin-bottom:16px;">
            <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
                <thead>
                    <tr style="background:#002B49; color:#FFFFFF;">
                        <th style="padding:7px 8px; font-size:0.72rem; font-weight:800; text-align:left; border:1px solid #004B87;">STAGIONE</th>
                        <th style="padding:7px 8px; font-size:0.72rem; font-weight:700; text-align:left; border:1px solid #004B87;">SQUADRA / CLUB</th>
                        <th style="padding:7px 6px; font-size:0.72rem; font-weight:800; text-align:center; border:1px solid #004B87;">CAPS</th>
                        <th style="padding:7px 6px; font-size:0.72rem; font-weight:700; text-align:center; border:1px solid #004B87;">TITOLARE</th>
                        <th style="padding:7px 6px; font-size:0.72rem; font-weight:700; text-align:center; border:1px solid #004B87;">SUB (PAN)</th>
                        <th style="padding:7px 8px; font-size:0.72rem; font-weight:800; text-align:center; border:1px solid #004B87;">MINUTI TOTALI</th>
                        <th style="padding:7px 6px; font-size:0.72rem; font-weight:700; text-align:center; border:1px solid #004B87;">MEDIA MIN</th>
                        <th style="padding:7px 8px; font-size:0.72rem; font-weight:800; text-align:center; border:1px solid #004B87; background:#0B1F33;">MAX MINUTI 6 SETT.</th>
                    </tr>
                </thead>
                <tbody>
                    {s_rows_html}
                    {tot_s_html}
                </tbody>
            </table>
        </div>
        """
        _clean_and_render_html(table_seasons_html)

        # Plotly Stacked Bar Chart for Seasons (usando s_sum_df aggregato per stagione)
        chart_source_df = s_sum_df if not s_sum_df.empty else s_df[s_df.get("is_subtotal", False) == False]
        s_plot_df = chart_source_df.sort_values("season", ascending=True).copy()
        s_plot_df["starter_minutes"] = s_plot_df["starts"] * s_plot_df["avg_minutes"]
        s_plot_df["bench_minutes"] = s_plot_df["minutes"] - s_plot_df["starter_minutes"]
        s_plot_df["bench_minutes"] = s_plot_df["bench_minutes"].clip(lower=0)

        fig_s = go.Figure()
        fig_s.add_trace(go.Bar(
            x=s_plot_df["season"],
            y=s_plot_df["starter_minutes"],
            name="Minuti da Titolare",
            marker_color="#0066B2",
            hovertemplate="Stagione %{x}<br>Titolare: %{y:.0f} min<extra></extra>",
        ))
        fig_s.add_trace(go.Bar(
            x=s_plot_df["season"],
            y=s_plot_df["bench_minutes"],
            name="Minuti da Subentrato (Panchina)",
            marker_color="#38BDF8",
            hovertemplate="Stagione %{x}<br>Panchina: %{y:.0f} min<extra></extra>",
        ))
        fig_s.add_trace(go.Scatter(
            x=s_plot_df["season"],
            y=s_plot_df["avg_minutes"],
            name="Media Minuti a Gara",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color="#D97706", width=2.5),
            marker=dict(size=8, color="#B45309"),
            hovertemplate="Media Min/Gara: %{y:.1f}'<extra></extra>",
        ))
        fig_s.update_layout(
            title=dict(text=f"Trend Minuti per Stagione: {p_name}", font=dict(size=14, color="#0F172A", family="Inter")),
            barmode="stack",
            height=280,
            margin=dict(l=40, r=40, t=35, b=25),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(title=None, showgrid=False),
            yaxis=dict(title="Minuti Giocati", showgrid=True, gridcolor="#F1F5F9"),
            yaxis2=dict(title="Media Minuti", overlaying="y", side="right", range=[0, 85], showgrid=False),
            plot_bgcolor="#FFFFFF",
            paper_bgcolor="#FFFFFF",
        )
        st.plotly_chart(fig_s, use_container_width=True)

    # 4. SEZIONE 2: Analisi per Squadra / Club
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    _clean_and_render_html(
        """
        <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid #059669; padding-bottom:6px; margin-bottom:12px;">
            <div style="font-size:1.05rem; font-weight:800; color:#0F172A;">
                <i class="bi bi-shield-check" style="color:#059669; margin-right:6px;"></i>
                Squadre & Club con cui ha giocato in Carriera
            </div>
            <div style="font-size:0.75rem; color:#64748B;">Ripartizione minuti tra Club di appartenenza e Nazionale Italiana</div>
        </div>
        """
    )

    t_df = prof["teams_df"]
    if not t_df.empty:
        col_t1, col_t2 = st.columns([1.6, 1.0])

        with col_t1:
            t_rows_html = ""
            for _, tr in t_df.iterrows():
                is_nat = "ital" in str(tr["team_name"]).lower()
                tm_col = "#0066B2" if is_nat else "#059669"
                w_pill = f"<span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.70rem; background:#DCFCE7; color:#15803D;'>{tr['wins']}V - {tr['losses']}S ({tr['win_pct']:.0f}%)</span>"

                t_min_disp = f"{tr['minutes']:,}".replace(",", ".")
                t_rows_html += f"""
                <tr style='background:#FFFFFF;'>
                    <td style='padding:6px 10px; font-weight:800; font-size:0.78rem; color:{tm_col}; border:1px solid #CBD5E1;'>{tr['team_name']}</td>
                    <td style='padding:5px 8px; font-size:0.73rem; color:#64748B; border:1px solid #E2E8F0;'>{tr['period']}</td>
                    <td style='padding:5px 8px; text-align:center; font-weight:800; font-size:0.76rem; color:#0F172A; border:1px solid #E2E8F0;'>{tr['caps']}</td>
                    <td style='padding:5px 8px; text-align:center; font-size:0.73rem; color:#0F172A; border:1px solid #E2E8F0;'>{tr['starts']} <span style='font-size:0.67rem; color:#64748B;'>({tr['starter_pct']:.0f}%)</span></td>
                    <td style='padding:5px 8px; text-align:center; font-weight:800; font-size:0.78rem; color:#064E3B; border:1px solid #E2E8F0;'>{t_min_disp}' min</td>
                    <td style='padding:5px 8px; text-align:center; border:1px solid #E2E8F0;'>{w_pill}</td>
                </tr>
                """

            table_teams_html = f"""
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; overflow-x:auto; box-shadow:0 2px 8px rgba(15,23,42,0.05);">
                <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
                    <thead>
                        <tr style="background:#0F172A; color:#FFFFFF;">
                            <th style="padding:7px 10px; font-size:0.70rem; font-weight:800; text-align:left; border:1px solid #334155;">SQUADRA / CLUB</th>
                            <th style="padding:7px 8px; font-size:0.70rem; font-weight:700; text-align:left; border:1px solid #334155;">PERIODO</th>
                            <th style="padding:7px 8px; font-size:0.70rem; font-weight:800; text-align:center; border:1px solid #334155;">CAPS</th>
                            <th style="padding:7px 8px; font-size:0.70rem; font-weight:700; text-align:center; border:1px solid #334155;">TITOLARE</th>
                            <th style="padding:7px 8px; font-size:0.70rem; font-weight:800; text-align:center; border:1px solid #334155;">MINUTI TOTALI</th>
                            <th style="padding:7px 8px; font-size:0.70rem; font-weight:800; text-align:center; border:1px solid #334155;">RECORD (W-L)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {t_rows_html}
                    </tbody>
                </table>
            </div>
            """
            _clean_and_render_html(table_teams_html)

        with col_t2:
            fig_pie = px.pie(
                t_df,
                values="minutes",
                names="team_name",
                hole=0.45,
                color_discrete_sequence=["#0066B2", "#059669", "#D97706", "#8B5CF6", "#DC2626"],
            )
            fig_pie.update_layout(
                title=dict(text="Minuti Giocati per Squadra", font=dict(size=12, color="#0F172A")),
                height=230,
                margin=dict(l=10, r=10, t=30, b=10),
                legend=dict(orientation="h", y=-0.1),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # 5. SEZIONE 3: Dettaglio Partite Giocate (Filtro Stagione & Partite)
    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
    _clean_and_render_html(
        """
        <div style="display:flex; align-items:center; justify-content:space-between; border-bottom:2px solid #D97706; padding-bottom:6px; margin-bottom:12px;">
            <div style="font-size:1.05rem; font-weight:800; color:#0F172A;">
                <i class="bi bi-clock-history" style="color:#D97706; margin-right:6px;"></i>
                Dettaglio Gare Disputate & Minutaggi Singola Partita
            </div>
            <div style="font-size:0.75rem; color:#64748B;">Ispezione di tutte le partite giocate nella stagione selezionata</div>
        </div>
        """
    )

    m_df = prof["matches_df"].copy()
    if not m_df.empty:
        # Barra Filtri Partite
        mf1, mf2, mf3, mf4, mf5 = st.columns([1.6, 1.4, 1.2, 1.2, 1.8])

        season_opts = prof["available_seasons"]
        # Default: 2026/27 se ha partite, altrimenti prima stagione
        default_s_idx = 1 if len(season_opts) > 1 and "2026/27" in season_opts[1] else 0
        sel_season = mf1.selectbox("Seleziona Stagione", season_opts, index=default_s_idx, key="prof_m_season")

        teams_sub_list = ["Tutte le Squadre"] + sorted([str(t) for t in m_df["team"].dropna().unique() if str(t).strip()])
        sel_team_m = mf2.selectbox("Filtro Squadra Atleta", teams_sub_list, key="prof_m_team")

        sel_starter = mf3.selectbox("Filtro Impiego", ["Tutti", "Solo Titolare (Starter)", "Solo Sub (Finisher)"], key="prof_m_starter")
        sel_outcome = mf4.selectbox("Filtro Risultato", ["Tutti", "Solo Vittorie (W)", "Solo Sconfitte (L)"], key="prof_m_outcome")
        q_match = mf5.text_input("Cerca Gara / Avversario", placeholder="Es. Glasgow, Castres...", key="prof_m_search")

        # Apply match filters
        if sel_season != "Tutte le Stagioni":
            s_clean = sel_season.split()[0].strip()
            m_df = m_df[m_df["season"] == s_clean]

        if sel_team_m != "Tutte le Squadre":
            m_df = m_df[m_df["team"] == sel_team_m]

        if sel_starter == "Solo Titolare (Starter)":
            m_df = m_df[m_df["is_starter"] == True]
        elif sel_starter == "Solo Sub (Finisher)":
            m_df = m_df[m_df["is_starter"] == False]

        if sel_outcome == "Solo Vittorie (W)":
            m_df = m_df[m_df["outcome"] == "WIN"]
        elif sel_outcome == "Solo Sconfitte (L)":
            m_df = m_df[m_df["outcome"] == "LOSS"]

        if q_match.strip():
            qm = q_match.strip().lower()
            m_df = m_df[
                m_df["game"].astype(str).str.lower().str.contains(qm)
                | m_df["opponent"].astype(str).str.lower().str.contains(qm)
            ]

        m_df = m_df.reset_index(drop=True)

        # Plotly Match Timeline Chart
        if not m_df.empty:
            m_plot_df = m_df.iloc[::-1].copy().reset_index(drop=True)  # Cronologico dal più vecchio al più recente
            color_map = {"WIN": "#10B981", "LOSS": "#EF4444", "DRAW": "#94A3B8"}
            bar_colors = [color_map.get(o, "#0066B2") for o in m_plot_df["outcome"]]

            fig_m = go.Figure()
            fig_m.add_trace(go.Bar(
                x=[f"{r['date_disp']}<br>{r['opponent']}" for _, r in m_plot_df.iterrows()],
                y=m_plot_df["minutes"],
                marker_color=bar_colors,
                text=[f"{int(m)}'" for m in m_plot_df["minutes"]],
                textposition="auto",
                hovertemplate="<b>%{x}</b><br>Minuti: %{y}'<br>Partita: %{customdata[0]}<br>Risultato: %{customdata[1]}<extra></extra>",
                customdata=m_plot_df[["game", "result"]].values,
            ))
            # Target 80' reference line
            fig_m.add_hline(y=80, line_dash="dash", line_color="#DC2626", annotation_text="80' Partita Intera", annotation_position="top right")
            fig_m.update_layout(
                title=dict(text=f"Minuti Giocati Partita per Partita ({len(m_df)} gare visualizzate • Verde=Vittoria, Rosso=Sconfitta)", font=dict(size=13, color="#0F172A")),
                height=260,
                margin=dict(l=35, r=35, t=35, b=30),
                yaxis=dict(title="Minuti Giocati", range=[0, 88], gridcolor="#F1F5F9"),
                xaxis=dict(title=None, showgrid=False),
                plot_bgcolor="#FFFFFF",
                paper_bgcolor="#FFFFFF",
            )
            st.plotly_chart(fig_m, use_container_width=True)

            # Match List Table
            match_rows_html = ""
            for _, mr in m_df.iterrows():
                m_min_raw = pd.to_numeric(mr.get("minutes", 0), errors="coerce")
                m_min = int(round(float(0.0 if pd.isna(m_min_raw) else m_min_raw)))
                m_pct = min(100, int(round((m_min / 80.0) * 100)))
                cell_border = "2px solid #EF4444" if mr["is_starter"] else "1px solid #93C5FD"
                bar_bg = "rgba(56,189,248,0.50)" if mr["is_starter"] else "rgba(125,211,252,0.38)"
                min_cell = (
                    f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:{cell_border}; border-radius:3px; overflow:hidden;'>"
                    f"<div style='position:absolute; left:0; top:0; bottom:0; width:{m_pct}%; background:{bar_bg};'></div>"
                    f"<div style='position:relative; z-index:1; font-weight:800; font-size:0.72rem; color:#0F172A; line-height:16px; text-align:center;'>{m_min}'</div></div>"
                )

                jer_raw = pd.to_numeric(mr.get("jersey", 0), errors="coerce")
                jer_val = int(round(float(0.0 if pd.isna(jer_raw) else jer_raw)))
                jer_tag = f" <span style='font-size:0.67rem; color:#64748B;'>#{jer_val}</span>" if jer_val > 0 else ""
                imp_badge = (
                    f"<span style='display:inline-block; padding:1px 6px; border-radius:3px; font-weight:800; font-size:0.68rem; background:#FEE2E2; color:#B91C1C; border:1px solid #FECACA;'>TITOLARE{jer_tag}</span>"
                    if mr["is_starter"]
                    else f"<span style='display:inline-block; padding:1px 6px; border-radius:3px; font-weight:700; font-size:0.68rem; background:#E0F2FE; color:#0369A1;'>FINISHER{jer_tag}</span>"
                )

                res = str(mr["result"] or "")
                res_bg = "#DCFCE7" if mr["outcome"] == "WIN" else ("#FEE2E2" if mr["outcome"] == "LOSS" else "#F1F5F9")
                res_col = "#15803D" if mr["outcome"] == "WIN" else ("#B91C1C" if mr["outcome"] == "LOSS" else "#475569")
                res_badge = f"<span style='display:inline-block; padding:1px 6px; border-radius:3px; font-weight:800; font-size:0.70rem; background:{res_bg}; color:{res_col};'>{res}</span>" if res else "-"

                ha_bg = "#EFF6FF" if mr["ha"] == "Home" else "#F8FAFC"

                match_rows_html += f"""
                <tr style='background:#FFFFFF;'>
                    <td style='position:sticky; left:0; z-index:2; background:#FFFFFF; padding:4px 8px; font-weight:700; font-size:0.73rem; color:#0F172A; border:1px solid #CBD5E1; white-space:nowrap;'>{mr['date_disp']}</td>
                    <td style='padding:4px 8px; font-weight:700; font-size:0.74rem; color:#0066B2; border:1px solid #E2E8F0; white-space:nowrap;'>{mr['game']}</td>
                    <td style='padding:4px 6px; font-size:0.70rem; color:#334155; border:1px solid #E2E8F0; white-space:nowrap;'>{mr['team']}</td>
                    <td style='padding:4px 6px; font-size:0.70rem; color:#475569; border:1px solid #E2E8F0; white-space:nowrap;'>{mr['opponent']}</td>
                    <td style='padding:4px 4px; text-align:center; font-size:0.69rem; background:{ha_bg}; color:#475569; border:1px solid #E2E8F0;'>{mr['ha']}</td>
                    <td style='padding:2px 4px; border:1px solid #E2E8F0; min-width:60px;'>{min_cell}</td>
                    <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0; white-space:nowrap;'>{imp_badge}</td>
                    <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>{res_badge}</td>
                    <td style='padding:4px 6px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0;'>{mr['carries']}</td>
                    <td style='padding:4px 6px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0;'>{mr['pcm']} m</td>
                    <td style='padding:4px 6px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0;'>{mr['tackles']}</td>
                    <td style='padding:4px 6px; text-align:center; font-weight:700; font-size:0.71rem; color:#0369A1; border:1px solid #E2E8F0;'>{mr['turnovers_won']}</td>
                    <td style='padding:4px 6px; text-align:center; font-size:0.71rem; color:#B91C1C; border:1px solid #E2E8F0;'>{mr['penalties']}</td>
                </tr>
                """

            table_matches_html = f"""
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; overflow-x:auto; max-height:560px; box-shadow:0 2px 8px rgba(15,23,42,0.05); margin-bottom:14px;">
                <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
                    <thead style="position:sticky; top:0; z-index:3;">
                        <tr style="background:#002B49; color:#FFFFFF;">
                            <th style="position:sticky; left:0; z-index:4; background:#002B49; padding:7px 8px; font-size:0.69rem; font-weight:800; text-align:left; border:1px solid #004B87;">DATA</th>
                            <th style="padding:7px 8px; font-size:0.69rem; font-weight:800; text-align:left; border:1px solid #004B87;">PARTITA (OVAL)</th>
                            <th style="padding:7px 6px; font-size:0.69rem; font-weight:700; text-align:left; border:1px solid #004B87;">SQUADRA</th>
                            <th style="padding:7px 6px; font-size:0.69rem; font-weight:700; text-align:left; border:1px solid #004B87;">AVVERSARIO</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">H/A</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:800; text-align:center; border:1px solid #004B87;">MINUTI</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:800; text-align:center; border:1px solid #004B87;">IMPIEGO</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:800; text-align:center; border:1px solid #004B87;">RISULTATO</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">CARRIES</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">METRI ADV</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">PLACCAGGI</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">TURNOVER</th>
                            <th style="padding:7px 4px; font-size:0.69rem; font-weight:700; text-align:center; border:1px solid #004B87;">FALLI</th>
                        </tr>
                    </thead>
                    <tbody>
                        {match_rows_html}
                    </tbody>
                </table>
            </div>
            """
            _clean_and_render_html(table_matches_html)

            # CSV Download
            csv_data = m_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"Scarica Storico Partite di {p_name} (CSV)",
                data=csv_data,
                file_name=f"FIR_Oval_{p_name.replace(' ', '_')}_Partite.csv",
                mime="text/csv",
                key="btn_dl_player_oval_csv",
            )
        else:
            st.info("Nessuna partita trovata con i filtri selezionati.")

    # Popola l'Action Bar PDF in alto con tutte le sezioni e i grafici della Scheda Atleta
    with pdf_action_slot:
        render_action_bar(
            meta_items=[
                ("Atleta", f"{p_name} ({prof['role']})"),
                ("Club / Squadra", prof["club"]),
                ("Carriera Oval", f"{c_tot['total_caps']} CAPS • {c_tot['total_min']:,}' min".replace(",", ".")),
                ("Stagione 2026/27", f"{s_curr['caps']} gare • {s_curr['minutes']}' min"),
                ("Gare Filtrate", f"{len(m_df)} partite ({sel_season})"),
            ],
            pdf_options={
                "Dossier Completo Atleta (Layout Portale: Carriera, Stagioni, Club + Dettaglio Gare)": "completo",
                "Sintesi Carriera, Stagioni, Grafici & Club (2 Pagine)": "sintesi_carriera",
                "Solo Dettaglio Gare Disputate & Statistiche Partita": "solo_gare",
            },
            pdf_key=f"oval_prof_{p_name}_{sel_season}_{sel_team_m}_{sel_starter}_{sel_outcome}",
            generate_fn=lambda sub_code: crea_pdf_scheda_atleta_oval(
                prof=prof,
                matches_df=m_df,
                filter_meta={
                    "season": sel_season,
                    "team": sel_team_m,
                    "starter": sel_starter,
                    "outcome": sel_outcome,
                },
                sub_code=sub_code,
                fig_seasons=fig_s,
                fig_teams=fig_pie,
                fig_matches=fig_m,
            ),
            filename_fn=lambda sub_code: f"FIR_Scheda_Oval_{p_name.replace(' ', '_')}_{sub_code}.pdf",
        )



def _render_tab_archivio(df: pd.DataFrame):
    c_arc_top1, c_arc_top2 = st.columns(2)
    with c_arc_top1:
        _render_manual_match_expander()
    with c_arc_top2:
        _render_delete_oval_match_expander(key_prefix="oval_del_arch")

    if df.empty:
        st.info("Nessun record presente nel database Oval Match.")
        return

    f1, f2, f3, f4, f5 = st.columns([1.6, 1.4, 1.0, 1.0, 1.5])
    players_list = ["Tutti i Giocatori"] + sorted([str(p) for p in df["fir_player_name"].dropna().unique() if str(p).strip()])
    sel_player = f1.selectbox("Giocatore (Roster FIR)", players_list, key="oval_f_player")

    teams_list = ["Tutte le Squadre"] + sorted([str(tm) for tm in df["teamName"].dropna().unique() if str(tm).strip()])
    sel_team = f2.selectbox("Squadra (Club / Nazionale)", teams_list, key="oval_f_team")

    d_from = f3.text_input("Data Da (YYYY-MM-DD)", placeholder="2026-08-01", key="oval_f_dfrom")
    d_to = f4.text_input("Data A (YYYY-MM-DD)", placeholder="2027-07-30", key="oval_f_dto")

    view_mode = f5.selectbox(
        "Gruppo Statistiche",
        [
            "Sintesi Minutaggio & Match",
            "Attacco, Carries & Contatto",
            "Difesa, Placcaggi & Turnover",
            "Ruck & Breakdown",
            "Passaggi, Calci & Touche",
            "Tutte le Colonne Oval (103)",
        ],
        key="oval_f_viewmode",
    )

    filt = df.copy()
    if sel_player != "Tutti i Giocatori":
        filt = filt[filt["fir_player_name"] == sel_player]
    if sel_team != "Tutte le Squadre":
        filt = filt[filt["teamName"] == sel_team]
    if d_from.strip():
        filt = filt[filt["match_date"] >= d_from.strip()[:10]]
    if d_to.strip():
        filt = filt[filt["match_date"] <= d_to.strip()[:10]]

    for num_c in ["Min", "MatchesStarted", "TotalCarries", "PostContactMeters", "TotalTackleAttempts", "MissedTackle", "TotalRuckEntries"]:
        if num_c in filt.columns:
            filt[num_c] = pd.to_numeric(filt[num_c], errors="coerce").fillna(0.0)

    k1, k2, k3, k4, k5 = st.columns(5)
    n_games = len(filt)
    n_starts = int(filt["MatchesStarted"].sum()) if "MatchesStarted" in filt.columns else 0
    tot_min = int(filt["Min"].sum()) if "Min" in filt.columns else 0
    avg_min = filt["Min"].mean() if n_games > 0 else 0.0
    tot_carries = int(filt["TotalCarries"].sum()) if "TotalCarries" in filt.columns else 0
    tot_tackles = int(filt["TotalTackleAttempts"].sum()) if "TotalTackleAttempts" in filt.columns else 0

    for col_ui, lbl, val, sub, color in [
        (k1, "Partite Giocate", f"{n_games:,}", f"Titolare: {n_starts} ({round(n_starts/n_games*100) if n_games else 0}%)", "#0066B2"),
        (k2, "Minuti Totali", f"{tot_min:,} min", f"Equivalenti a {tot_min/80:.1f} gare da 80'", "#D4AF37"),
        (k3, "Media Minuti / Gara", f"{avg_min:.1f} min", "Minutaggio medio", "#10B981"),
        (k4, "Carries Totali", f"{tot_carries:,}", f"Media: {tot_carries/n_games:.1f}/gara" if n_games else "--", "#0284C7"),
        (k5, "Placcaggi Tentati", f"{tot_tackles:,}", f"Media: {tot_tackles/n_games:.1f}/gara" if n_games else "--", "#EF4444"),
    ]:
        col_ui.markdown(
            f"""
            <div class="fir-kpi-card" style="border-left-color: {color};">
                <div class="fir-kpi-label">{lbl}</div>
                <div class="fir-kpi-val">{val}</div>
                <div class="fir-kpi-sub">{sub}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    render_action_bar(
        meta_items=[
            ("Giocatore", sel_player),
            ("Squadra", sel_team),
            ("Periodo", f"{d_from.strip() or 'Inizio'} → {d_to.strip() or 'Oggi'}"),
            ("Gruppo Statistiche", view_mode),
            ("Partite Filtrate", f"{n_games:,} ({tot_min:,}' min)"),
        ],
        pdf_options={
            f"Report Archivio Filtrato — {view_mode} (Fino a 150 gare)": "archivio_150",
            f"Report Compatto Top 50 Gare — {view_mode} (1-2 Pagine)": "archivio_50",
            f"Report Completo Tutte le Gare Filtrate ({min(n_games, 500)} record)": "archivio_all",
        },
        pdf_key=f"oval_arch_{sel_player}_{sel_team}_{d_from}_{d_to}_{view_mode}",
        generate_fn=lambda sub_code: crea_pdf_archivio_oval(
            filt_df=filt,
            view_mode=view_mode,
            filter_meta={
                "player": sel_player,
                "team": sel_team,
                "d_from": d_from.strip(),
                "d_to": d_to.strip(),
            },
            sub_code=sub_code,
        ),
        filename_fn=lambda sub_code: f"FIR_Archivio_Oval_{sel_player.replace(' ', '_')}_{sub_code}.pdf",
    )

    base_cols = ["id", "match_date", "fir_player_name", "playerId", "teamName", "game", "result", "pos", "Jersey", "MatchesStarted", "Min"]
    if view_mode == "Sintesi Minutaggio & Match":
        extra_cols = ["TotalCarries", "PostContactMeters", "DefenderBeaten", "TotalTackleAttempts", "MissedTackle", "TackleSuccessRate", "TotalRuckEntries", "TotalTurnoversWon", "TotalPenalties"]
    elif view_mode == "Attacco, Carries & Contatto":
        extra_cols = ["TotalCarries", "TotalCarriesInContact", "PostContactMeters", "%DominantCarry", "%CrossedGainline", "DefenderBeaten", "Drive", "PickAndGo", "OtherCarry", "%NeutralCarry", "%NegativeCarry"]
    elif view_mode == "Difesa, Placcaggi & Turnover":
        extra_cols = ["TotalTackleAttempts", "MissedTackle", "TackleSuccessRate", "%DominantTackles", "TotalTurnoversWon", "TotalTurnoversConceded", "TotalPenalties", "Free_Kick"]
    elif view_mode == "Ruck & Breakdown":
        extra_cols = ["TotalRuckEntries", "TotalEffectiveRuckEntries", "AttackingRuckEntries", "AttackingRuckCleanedOut", "AttackingRuckSecured", "AttackingRuckAttended", "AttackRuckEntry1st", "AttackRuckEntry2nd", "AttackRuckEntry3rd", "RuckOffense", "RuckOffenseAttack", "RuckOffenseDefence"]
    elif view_mode == "Passaggi, Calci & Touche":
        extra_cols = ["TotalPasses", "CompletePass", "PassError", "%PassSuccess", "TotalKicks", "KickBox", "Contestable", "TotalKickErrors", "TotalLineoutThrows", "ScrumOffense"]
    else:
        extra_cols = [c for c in filt.columns if c not in base_cols]

    show_cols = [c for c in base_cols + extra_cols if c in filt.columns]
    rename_map = {
        "id": "ID",
        "match_date": "Data Match",
        "fir_player_name": "Giocatore FIR",
        "playerId": "Codice Oval",
        "teamName": "Squadra",
        "game": "Partita",
        "result": "Risultato",
        "pos": "Ruolo Match",
        "Jersey": "Maglia",
        "MatchesStarted": "Titolare",
        "Min": "Minuti",
    }

    st.dataframe(filt.head(1000)[show_cols].rename(columns=rename_map), use_container_width=True, hide_index=True, height=500)

    with st.expander("Elimina un Record Partita per ID (es. partita manuale errata)", expanded=False):
        del_c1, del_c2 = st.columns([1.5, 2.5])
        del_id = del_c1.number_input("ID Record da eliminare", min_value=1, value=int(filt["id"].iloc[0]) if not filt.empty and "id" in filt.columns else 1, step=1, key="del_oval_id")
        if del_c2.button("Elimina Record Selezionato", type="secondary", key="btn_del_oval_rec"):
            utils.delete_oval_match_record(int(del_id))
            st.success(f"Record ID {del_id} eliminato con successo.")
            st.rerun()


def _render_tab_upload():
    st.markdown("### Aggiornamento Periodico Database Oval Match via CSV")
    st.caption(
        "Carica un nuovo file `.csv` esportato da Oval (es. `RDM-5.csv`): il sistema aggancia automaticamente gli atleti tramite `playerId` (Codice Oval) "
        "e nome, evitando duplicati sulle partite già presenti e aggiungendo le nuove."
    )
    if st.session_state.get("user_role") == "viewer":
        st.warning("🔒 Accesso Riservato: il profilo attuale è in sola consultazione. Solo gli amministratori possono caricare file CSV.")
        return

    up = st.file_uploader("Seleziona file CSV Oval Match", type=["csv"], key="oval_csv_up")
    if up is not None:
        content = up.getvalue().decode("utf-8-sig", errors="ignore")
        first_line = content.splitlines()[0] if content else ""
        sep = ";" if first_line.count(";") > first_line.count(",") else ","
        up.seek(0)
        new_df = pd.read_csv(up, sep=sep, encoding="utf-8-sig", low_memory=False)
        new_df.columns = [str(c).strip() for c in new_df.columns]
        st.info(f"File letto correttamente: **{len(new_df):,} righe** e **{len(new_df.columns)} colonne**.")
        st.dataframe(new_df.head(8), use_container_width=True)
        if st.button("Conferma e Aggiorna Database Oval Match", type="primary", key="btn_oval_up_confirm"):
            res = utils.import_oval_csv_dataframe(new_df)
            dup_cnt = res.get("duplicates", 0)
            net_new = res.get("net_new", 0)
            dup_df = res.get("duplicate_df", pd.DataFrame())

            if dup_cnt > 0:
                st.warning(f"⚠️ Attenzione: **{dup_cnt:,} record** non sono stati caricati perché **già presenti** nell'archivio Oval Match!")
                with st.expander(f"📋 Dettaglio dei {dup_cnt:,} record duplicati non caricati", expanded=True):
                    show_cols = [c for c in ["date", "fir_player_name", "playerFullName", "teamName", "game", "Min", "points"] if c in dup_df.columns]
                    st.dataframe(dup_df[show_cols], use_container_width=True, hide_index=True)

            if net_new > 0:
                st.success(
                    f"✅ Aggiornamento completato! Nuove prestazioni aggiunte: **{net_new:,}** | "
                    f"Totale archivio Oval Match: **{res.get('total_after', 0):,}**."
                )
                st.balloons()
            elif dup_cnt > 0:
                st.info(f"Nessun nuovo dato da inserire: tutti i {dup_cnt} record del file sono già presenti nell'archivio storico.")
