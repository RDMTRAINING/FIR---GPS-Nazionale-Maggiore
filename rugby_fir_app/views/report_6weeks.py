import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import render_page_header, render_tab_navigation, render_action_bar, ROLE_TO_DEPT
import utils
from pdf_generator import crea_pdf_report_6weeks, crea_pdf_report_franchige_day, crea_pdf_singolo_atleta_3w


def _clean_and_render_html(html_str: str):
    """Rimuove spazi e a capo spuri prima del rendering per evitare blocchi pre/code di CommonMark."""
    cleaned = "".join(line.strip() for line in html_str.splitlines() if line.strip())
    if hasattr(st, "html"):
        st.html(cleaned)
    else:
        st.markdown(cleaned, unsafe_allow_html=True)


def _get_available_weeks_options() -> tuple:
    """Genera l'elenco delle settimane (Lunedì — Domenica) a ritroso dal lunedì attuale fino ad Agosto 2024."""
    start_dt = pd.to_datetime("2024-08-01")
    first_mon = start_dt - pd.Timedelta(days=start_dt.weekday())

    import datetime
    today_dt = pd.to_datetime(datetime.date.today())
    today_mon = today_dt - pd.Timedelta(days=today_dt.weekday())
    latest_mon = max(today_mon, pd.Timestamp("2026-11-02"))

    weeks = []
    cur = latest_mon
    default_idx = 0  # Settimana attuale (in corso) posizionata al primo indice per default
    while cur >= first_mon:
        end_w = cur + pd.Timedelta(days=6)
        mon_str = cur.strftime("%Y-%m-%d")
        cur_fmt = cur.strftime("%d/%m/%y")
        end_fmt = end_w.strftime("%d/%m/%y")
        if cur == latest_mon:
            lbl = f"{cur_fmt} – {end_fmt} (Settimana Attuale)"
            default_idx = len(weeks)
        elif cur == pd.Timestamp("2026-10-19"):
            lbl = f"{cur_fmt} – {end_fmt} (Ufficiale FIR)"
        else:
            lbl = f"{cur_fmt} – {end_fmt}"
        weeks.append((mon_str, lbl))
        cur -= pd.Timedelta(days=7)
    return weeks, default_idx


def _render_gin_list_manager():
    p_df = utils.get_players_df().copy()
    if p_df.empty:
        return
    gin_current = set(utils.get_gin_player_names())
    n_gin = len(gin_current)
    n_tot = len(p_df)

    with st.expander(f"Configura Lista G.I.N. da Monitorare ({n_gin} atleti selezionati su {n_tot} nel Roster)", expanded=False):
        st.caption(
            "Seleziona o deseleziona i giocatori che compongono la **Lista G.I.N. (Giocatori di Interesse Nazionale)** da monitorare nel Report 6 Weeks. "
            "Le modifiche sono condivise con il database Oval Match e salvate nel database ufficiale FIR."
        )
        b1, b2, b3, b4 = st.columns([1.3, 1.2, 1.5, 1.3])
        if b1.button("Ripristina Lista G.I.N. Ufficiale (71 atleti)", use_container_width=True, key="btn_6w_gin_reset"):
            utils.reset_gin_to_default()
            st.success("Lista G.I.N. ripristinata ai 71 atleti ufficiali del modello FIR.")
            st.rerun()
        if b2.button("Seleziona Tutti (Intero Roster)", use_container_width=True, key="btn_6w_gin_all"):
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
        sel_camp_lbl = b3.selectbox("Importa Atleti da Raduno", camp_opts, label_visibility="collapsed", key="sel_6w_from_camp")
        if b4.button("Aggiungi Raduno alla Lista G.I.N.", use_container_width=True, disabled=(sel_camp_lbl not in camp_map), key="btn_6w_add_camp"):
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
            height=280,
            key="gin_6w_editor_table",
            column_config={
                "Includi_GIN": st.column_config.CheckboxColumn("Monitora in G.I.N.", default=True),
                "name_display": st.column_config.TextColumn("Giocatore", disabled=True),
                "role": st.column_config.TextColumn("Ruolo", disabled=True),
                "department": st.column_config.TextColumn("Reparto", disabled=True),
                "club": st.column_config.TextColumn("Squadra / Club", disabled=True),
                "birth_year": st.column_config.TextColumn("Anno", disabled=True),
                "opta_id": st.column_config.TextColumn("Codice", disabled=True),
            },
            disabled=(st.session_state.get("user_role") == "viewer"),
        )
        if st.session_state.get("user_role") == "viewer":
            st.caption("🔒 Modifica lista G.I.N. riservata agli amministratori.")
        else:
            if st.button("Salva Lista G.I.N. Personalizzata", type="primary", key="btn_save_6w_gin_list"):
                chosen = edited[edited["Includi_GIN"] == True]["name_display"].dropna().astype(str).tolist()
                utils.save_gin_player_names(chosen)
                st.success(f"Lista G.I.N. salvata con successo ({len(chosen)} giocatori monitorati)!")
                st.rerun()


def _build_single_metric_html(
    rep_df: pd.DataFrame,
    weeks_meta: list,
    metric_key: str,
    meta_data: dict,
    sort_mode: str,
) -> str:
    """Costruisce la tabella HTML per un singolo parametro con le 6 settimane + ACWR + medie di ruolo/reparto."""
    minfo = utils.GPS_6W_METRICS[metric_key]
    is_mx = minfo["is_max"]
    unit_str = f" ({minfo['unit']})" if minfo['unit'] else ""

    # Trova il massimo per le data bars
    all_vals = []
    for _, r in rep_df.iterrows():
        all_vals.extend(r["metrics"][metric_key]["w_vals"])
    max_val = max(all_vals) if all_vals else 100.0
    if max_val <= 0:
        max_val = 1.0

    w_headers_top = ""
    w_headers_dates = ""
    for idx_w, wm in enumerate(weeks_meta):
        is_cur = idx_w == 0
        bg_top = "#064E3B" if is_cur else "#0F172A"
        bg_date = "#ECFDF5" if is_cur else "#F8FAFC"
        color_date = "#065F46" if is_cur else "#475569"
        border_top = "#047857" if is_cur else "#334155"

        w_headers_top += (
            f"<th style='background:{bg_top}; color:#FFFFFF; font-size:0.68rem; font-weight:700; padding:5px 4px; text-align:center; border:1px solid {border_top}; min-width:64px;'>"
            f"{wm['label']}</th>"
        )
        w_headers_dates += (
            f"<th style='background:{bg_date}; color:{color_date}; font-size:0.60rem; padding:2px 2px; text-align:center; border:1px solid #CBD5E1; line-height:1.15;'>"
            f"<div>{wm['start_disp']}</div><div style='border-top:1px solid #CBD5E1;'>{wm['end_disp']}</div></th>"
        )

    rows_html = ""
    prev_dept = None
    for idx_r, r in rep_df.iterrows():
        m_item = r["metrics"][metric_key]
        w_vals = m_item["w_vals"]
        acute = m_item["acute"]
        chronic = m_item["chronic"]
        acwr = m_item["acwr"]

        dept_val = str(r.get("department") or "")
        top_border = ""
        if prev_dept is not None and dept_val != prev_dept:
            top_border = "border-top: 3px solid #0066B2;"
        prev_dept = dept_val

        bg_row = "#FFFFFF" if idx_r % 2 == 0 else "#F8FAFC"

        # 6 Weeks cells
        w_cells = ""
        for w_i in range(6):
            v = w_vals[w_i]
            is_cur = w_i == 0
            if is_mx:
                disp_v = f"{v:.1f}".replace(".", ",") if v > 0 else "0"
            else:
                disp_v = f"{int(round(v)):,}".replace(",", ".") if v > 0 else "0"

            if v > 0:
                pct = min(100, int(round((v / max_val) * 100)))
                bar_bg = "rgba(16, 185, 129, 0.45)" if is_cur else "rgba(56, 189, 248, 0.35)"
                border_cell = "1.5px solid #059669" if is_cur else "1px solid #CBD5E1"
                txt_weight = "800" if is_cur else "600"
                txt_color = "#064E3B" if is_cur else "#0F172A"

                w_cells += (
                    f"<td style='padding:2px 3px; border:1px solid #E2E8F0; text-align:center; min-width:64px;'>"
                    f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:{border_cell}; border-radius:3px; overflow:hidden;'>"
                    f"<div style='position:absolute; left:0; top:0; bottom:0; width:{pct}%; background:{bar_bg};'></div>"
                    f"<div style='position:relative; z-index:1; font-weight:{txt_weight}; font-size:0.71rem; color:{txt_color}; line-height:17px;'>{disp_v}</div>"
                    f"</div></td>"
                )
            else:
                w_cells += "<td style='padding:2px 3px; border:1px solid #E2E8F0; text-align:center; color:#CBD5E1; font-size:0.68rem;'>0</td>"

        # ACWR cell
        acwr_lbl, acwr_bg, acwr_col = utils.get_acwr_status(acwr)
        acwr_str = f"{acwr:.1f}".replace(".", ",") if acwr > 0 else "/"
        chronic_str = f"{chronic:.1f}".replace(".", ",") if is_mx else (f"{int(round(chronic)):,}".replace(",", ".") if chronic > 0 else "0")
        acute_str = f"{acute:.1f}".replace(".", ",") if is_mx else (f"{int(round(acute)):,}".replace(",", ".") if acute > 0 else "0")

        rows_html += f"""
        <tr style='background:{bg_row}; {top_border}'>
            <td style='padding:4px 8px; font-weight:700; font-size:0.75rem; color:#0F172A; border:1px solid #E2E8F0; white-space:nowrap;'>{r['player_name']}</td>
            <td style='padding:4px 6px; font-size:0.70rem; color:#1E40AF; font-weight:600; border:1px solid #E2E8F0; white-space:nowrap;'>{r['role']}</td>
            <td style='padding:4px 6px; font-size:0.70rem; color:#475569; border:1px solid #E2E8F0; white-space:nowrap;'>{r['club']}</td>
            <td style='padding:4px 4px; font-size:0.69rem; color:#64748B; text-align:center; border:1px solid #E2E8F0;'>{r['birth_year']}</td>
            {w_cells}
            <td style='padding:3px 4px; border:1px solid #E2E8F0; border-left:2px solid #0066B2; text-align:center; font-weight:700; font-size:0.72rem; color:#0F172A;'>{acute_str}</td>
            <td style='padding:3px 4px; border:1px solid #E2E8F0; text-align:center; font-size:0.71rem; color:#475569;'>{chronic_str}</td>
            <td style='padding:3px 4px; border:1px solid #E2E8F0; text-align:center;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{acwr_bg}; color:{acwr_col};'>
                    {acwr_str}
                </span>
            </td>
        </tr>
        """

    # Add Role Averages Section
    role_rows_html = ""
    role_avgs = meta_data.get("role_averages", {}).get(metric_key, {})
    for r_name, r_stat in role_avgs.items():
        w_avg_cells = ""
        for w_i in range(6):
            v = r_stat["w_vals"][w_i]
            disp_v = f"{v:.1f}".replace(".", ",") if is_mx else f"{int(round(v)):,}".replace(",", ".")
            w_avg_cells += f"<td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#0F172A; border:1px solid #CBD5E1;'>{disp_v}</td>"

        r_acute_str = f"{r_stat['acute']:.1f}".replace(".", ",") if is_mx else f"{int(round(r_stat['acute'])):,}".replace(",", ".")
        r_chron_str = f"{r_stat['chronic']:.1f}".replace(".", ",") if is_mx else f"{int(round(r_stat['chronic'])):,}".replace(",", ".")
        r_acwr_lbl, r_acwr_bg, r_acwr_col = utils.get_acwr_status(r_stat["acwr"])
        r_acwr_str = f"{r_stat['acwr']:.1f}".replace(".", ",") if r_stat["acwr"] > 0 else "/"

        role_rows_html += f"""
        <tr style='background:#F1F5F9; border-top:1px solid #94A3B8;'>
            <td colspan='4' style='padding:4px 8px; font-weight:800; font-size:0.73rem; color:#1E3A8A; border:1px solid #CBD5E1;'>Media Ruolo: {r_name}</td>
            {w_avg_cells}
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0F172A; border:1px solid #CBD5E1; border-left:2px solid #0066B2;'>{r_acute_str}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:600; font-size:0.71rem; color:#475569; border:1px solid #CBD5E1;'>{r_chron_str}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #CBD5E1;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.71rem; background:{r_acwr_bg}; color:{r_acwr_col};'>{r_acwr_str}</span>
            </td>
        </tr>
        """

    # Add Department & Squad Averages
    dept_avgs = meta_data.get("dept_averages", {}).get(metric_key, {})
    dept_rows_html = ""
    for d_name in ["Avanti", "TreQuarti"]:
        d_stat = dept_avgs.get(d_name, {})
        if d_stat:
            w_avg_cells = ""
            for w_i in range(6):
                v = d_stat["w_vals"][w_i]
                disp_v = f"{v:.1f}".replace(".", ",") if is_mx else f"{int(round(v)):,}".replace(",", ".")
                w_avg_cells += f"<td style='padding:4px 4px; text-align:center; font-weight:800; font-size:0.73rem; color:#0F172A; border:1px solid #94A3B8;'>{disp_v}</td>"

            d_acute_str = f"{d_stat['acute']:.1f}".replace(".", ",") if is_mx else f"{int(round(d_stat['acute'])):,}".replace(",", ".")
            d_chron_str = f"{d_stat['chronic']:.1f}".replace(".", ",") if is_mx else f"{int(round(d_stat['chronic'])):,}".replace(",", ".")
            d_acwr_lbl, d_acwr_bg, d_acwr_col = utils.get_acwr_status(d_stat["acwr"])
            d_acwr_str = f"{d_stat['acwr']:.1f}".replace(".", ",") if d_stat["acwr"] > 0 else "/"

            bg_d = "#FEF3C7" if d_name == "Avanti" else "#E0F2FE"
            col_d = "#92400E" if d_name == "Avanti" else "#0369A1"
            dept_rows_html += f"""
            <tr style='background:{bg_d};'>
                <td colspan='4' style='padding:5px 8px; font-weight:800; font-size:0.75rem; color:{col_d}; border:1px solid #94A3B8;'>MEDIA REPARTO: {d_name.upper()}</td>
                {w_avg_cells}
                <td style='padding:4px 4px; text-align:center; font-weight:800; font-size:0.74rem; color:#0F172A; border:1px solid #94A3B8; border-left:2px solid #0066B2;'>{d_acute_str}</td>
                <td style='padding:4px 4px; text-align:center; font-weight:700; font-size:0.72rem; color:#475569; border:1px solid #94A3B8;'>{d_chron_str}</td>
                <td style='padding:4px 4px; text-align:center; border:1px solid #94A3B8;'>
                    <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{d_acwr_bg}; color:{d_acwr_col};'>{d_acwr_str}</span>
                </td>
            </tr>
            """

    html = f"""
    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(15,23,42,0.06); margin-bottom:16px;">
        <div style="background:linear-gradient(90deg, #002B49 0%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center;">
            <div>
                <span style="font-weight:800; font-size:0.92rem; letter-spacing:0.02em;">CARICO SETTIMANALE &bull; {minfo['name'].upper()}{unit_str}</span>
                <span style="font-size:0.75rem; opacity:0.85; margin-left:12px;">Settimana Selezionata: {weeks_meta[0]['start_disp']} &mdash; {weeks_meta[0]['end_disp']}</span>
            </div>
            <div style="font-size:0.72rem; color:#D4AF37; font-weight:700;">
                ACWR 7GG / 28GG &bull; Modello Gabbett Sweet Spot (0.8 - 1.3)
            </div>
        </div>
        <div style="overflow-x:auto; max-height:680px;">
            <table style="width:100%; border-collapse:collapse; font-family:'Inter', -apple-system, sans-serif; text-align:left;">
                <thead style="position:sticky; top:0; z-index:3;">
                    <tr>
                        <th rowspan="2" style="background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800; padding:6px 8px; border:1px solid #CBD5E1; text-align:left; min-width:145px; position:sticky; left:0; z-index:4;">GIOCATORE</th>
                        <th rowspan="2" style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left; min-width:85px;">RUOLO</th>
                        <th rowspan="2" style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left; min-width:90px;">SQUADRA</th>
                        <th rowspan="2" style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 4px; border:1px solid #CBD5E1; text-align:center; min-width:45px;">ANNO</th>
                        {w_headers_top}
                        <th colspan="3" style="background:#1E3A8A; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #1E40AF; border-left:2px solid #0066B2; text-align:center;">ACWR ULTIMA SETTIMANA (7GG / 28GG)</th>
                    </tr>
                    <tr>
                        {w_headers_dates}
                        <th style="background:#EFF6FF; color:#1E3A8A; font-size:0.62rem; font-weight:700; padding:3px 4px; border:1px solid #BFDBFE; border-left:2px solid #0066B2; text-align:center;">ACUTO (7G)</th>
                        <th style="background:#EFF6FF; color:#1E3A8A; font-size:0.62rem; font-weight:700; padding:3px 4px; border:1px solid #BFDBFE; text-align:center;">CRONICO (28G)</th>
                        <th style="background:#EFF6FF; color:#1E3A8A; font-size:0.62rem; font-weight:800; padding:3px 4px; border:1px solid #BFDBFE; text-align:center;">RATIO ACWR</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                    {role_rows_html}
                    {dept_rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """
    return "".join(line.strip() for line in html.splitlines() if line.strip())


def _build_acwr_matrix_html(rep_df: pd.DataFrame, weeks_meta: list) -> str:
    """Costruisce la matrice riassuntiva ACWR che confronta contemporaneamente le 4 metriche chiave (HML, HSR18, HSR20, DT)."""
    if rep_df.empty:
        return "<div>Nessun dato disponibile.</div>"

    rows_html = ""
    for idx_r, r in rep_df.iterrows():
        bg_row = "#FFFFFF" if idx_r % 2 == 0 else "#F8FAFC"
        m = r["metrics"]

        # HML
        hml_ac = m["HML"]["acute"]
        hml_chr = m["HML"]["chronic"]
        hml_r = m["HML"]["acwr"]
        hml_lbl, hml_bg, hml_col = utils.get_acwr_status(hml_r)

        # HSR 18
        h18_ac = m["HSR_18"]["acute"]
        h18_chr = m["HSR_18"]["chronic"]
        h18_r = m["HSR_18"]["acwr"]
        h18_lbl, h18_bg, h18_col = utils.get_acwr_status(h18_r)

        # HSR 20
        h20_ac = m["HSR_20"]["acute"]
        h20_chr = m["HSR_20"]["chronic"]
        h20_r = m["HSR_20"]["acwr"]
        h20_lbl, h20_bg, h20_col = utils.get_acwr_status(h20_r)

        # DT
        dt_ac = m["DT"]["acute"]
        dt_chr = m["DT"]["chronic"]
        dt_r = m["DT"]["acwr"]
        dt_lbl, dt_bg, dt_col = utils.get_acwr_status(dt_r)

        rows_html += f"""
        <tr style='background:{bg_row};'>
            <td style='padding:4px 8px; font-weight:700; font-size:0.75rem; color:#0F172A; border:1px solid #E2E8F0; white-space:nowrap;'>{r['player_name']}</td>
            <td style='padding:4px 6px; font-size:0.70rem; color:#1E40AF; font-weight:600; border:1px solid #E2E8F0; white-space:nowrap;'>{r['role']}</td>
            <td style='padding:4px 6px; font-size:0.70rem; color:#475569; border:1px solid #E2E8F0; white-space:nowrap;'>{r['club']}</td>
            
            <!-- HML -->
            <td style='padding:3px 4px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0; border-left:2px solid #0284C7;'>{int(round(hml_ac)):,}</td>
            <td style='padding:3px 4px; text-align:center; font-size:0.70rem; color:#64748B; border:1px solid #E2E8F0;'>{int(round(hml_chr)):,}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{hml_bg}; color:{hml_col};'>
                    {hml_r:.1f}
                </span>
            </td>

            <!-- HSR 18 -->
            <td style='padding:3px 4px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0; border-left:2px solid #DC2626;'>{int(round(h18_ac)):,}</td>
            <td style='padding:3px 4px; text-align:center; font-size:0.70rem; color:#64748B; border:1px solid #E2E8F0;'>{int(round(h18_chr)):,}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{h18_bg}; color:{h18_col};'>
                    {h18_r:.1f}
                </span>
            </td>

            <!-- HSR 20 -->
            <td style='padding:3px 4px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0; border-left:2px solid #E11D48;'>{int(round(h20_ac)):,}</td>
            <td style='padding:3px 4px; text-align:center; font-size:0.70rem; color:#64748B; border:1px solid #E2E8F0;'>{int(round(h20_chr)):,}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{h20_bg}; color:{h20_col};'>
                    {h20_r:.1f}
                </span>
            </td>

            <!-- DT -->
            <td style='padding:3px 4px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0; border-left:2px solid #16A34A;'>{int(round(dt_ac)):,}</td>
            <td style='padding:3px 4px; text-align:center; font-size:0.70rem; color:#64748B; border:1px solid #E2E8F0;'>{int(round(dt_chr)):,}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>
                <span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{dt_bg}; color:{dt_col};'>
                    {dt_r:.1f}
                </span>
            </td>
        </tr>
        """

    html = f"""
    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(15,23,42,0.06); margin-bottom:16px;">
        <div style="background:linear-gradient(90deg, #1E3A8A 0%, #0284C7 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:800; font-size:0.92rem; letter-spacing:0.02em;">MATRICE MULTI-PARAMETRICA ACWR (7GG / 28GG) &bull; SETTIMANA: {weeks_meta[0]['start_disp']} &mdash; {weeks_meta[0]['end_disp']}</span>
            <span style="font-size:0.72rem; color:#FEF08A; font-weight:700;">Verde = Ottimale (0.8-1.3) &bull; Arancio = Allerta (1.3-1.5) &bull; Rosso = Pericolo (&gt;1.5)</span>
        </div>
        <div style="overflow-x:auto; max-height:680px;">
            <table style="width:100%; border-collapse:collapse; font-family:'Inter', -apple-system, sans-serif;">
                <thead style="position:sticky; top:0; z-index:3;">
                    <tr>
                        <th rowspan="2" style="background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800; padding:6px 8px; border:1px solid #CBD5E1; text-align:left;">GIOCATORE</th>
                        <th rowspan="2" style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left;">RUOLO</th>
                        <th rowspan="2" style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left;">SQUADRA</th>
                        <th colspan="3" style="background:#0284C7; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #0369A1; border-left:2px solid #0284C7; text-align:center;">HML &gt;25.5W</th>
                        <th colspan="3" style="background:#DC2626; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #B91C1C; border-left:2px solid #DC2626; text-align:center;">HSR &gt;18 KM/H</th>
                        <th colspan="3" style="background:#E11D48; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #BE123C; border-left:2px solid #E11D48; text-align:center;">HSR &gt;20 KM/H</th>
                        <th colspan="3" style="background:#16A34A; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #15803D; border-left:2px solid #16A34A; text-align:center;">DISTANZA TOTALE (DT)</th>
                    </tr>
                    <tr>
                        <th style="background:#EFF6FF; color:#0369A1; font-size:0.61rem; padding:3px 3px; border:1px solid #BFDBFE; text-align:center;">Acuto</th>
                        <th style="background:#EFF6FF; color:#0369A1; font-size:0.61rem; padding:3px 3px; border:1px solid #BFDBFE; text-align:center;">Cronico</th>
                        <th style="background:#EFF6FF; color:#0369A1; font-size:0.61rem; font-weight:800; padding:3px 3px; border:1px solid #BFDBFE; text-align:center;">Ratio</th>

                        <th style="background:#FEF2F2; color:#B91C1C; font-size:0.61rem; padding:3px 3px; border:1px solid #FECACA; text-align:center;">Acuto</th>
                        <th style="background:#FEF2F2; color:#B91C1C; font-size:0.61rem; padding:3px 3px; border:1px solid #FECACA; text-align:center;">Cronico</th>
                        <th style="background:#FEF2F2; color:#B91C1C; font-size:0.61rem; font-weight:800; padding:3px 3px; border:1px solid #FECACA; text-align:center;">Ratio</th>

                        <th style="background:#FFF1F2; color:#9F1239; font-size:0.61rem; padding:3px 3px; border:1px solid #FECDD3; text-align:center;">Acuto</th>
                        <th style="background:#FFF1F2; color:#9F1239; font-size:0.61rem; padding:3px 3px; border:1px solid #FECDD3; text-align:center;">Cronico</th>
                        <th style="background:#FFF1F2; color:#9F1239; font-size:0.61rem; font-weight:800; padding:3px 3px; border:1px solid #FECDD3; text-align:center;">Ratio</th>

                        <th style="background:#F0FDF4; color:#15803D; font-size:0.61rem; padding:3px 3px; border:1px solid #BBF7D0; text-align:center;">Acuto</th>
                        <th style="background:#F0FDF4; color:#15803D; font-size:0.61rem; padding:3px 3px; border:1px solid #BBF7D0; text-align:center;">Cronico</th>
                        <th style="background:#F0FDF4; color:#15803D; font-size:0.61rem; font-weight:800; padding:3px 3px; border:1px solid #BBF7D0; text-align:center;">Ratio</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """
    return "".join(line.strip() for line in html.splitlines() if line.strip())


def _render_tab_report_6weeks(t: dict):
    # Top Expander: Configurazione Lista G.I.N.
    _render_gin_list_manager()

    # Barra Filtri — Riga 1 (Parametro, Settimana da Analizzare, Reparto)
    f1, f2, f3 = st.columns([1.8, 2.8, 1.2])

    metric_opts = [
        ("DT", "1. Distanza Totale (DT)"),
        ("HML", "2. High Metabolic Load (>25.5 W)"),
        ("HSR_18", "3. HSR >18 km/h"),
        ("HSR_20", "4. HSR >20 km/h"),
        ("HSR_25", "5. HSR >25 km/h (Sprint)"),
        ("VMAX", "6. Velocità Massima (Vmax)"),
        ("ACWR", "7. Focus Matrice ACWR (7gg / 28gg)"),
        ("TUTTI", "8. Report Completo Federale (Tutti i 6 Parametri)"),
    ]
    sel_metric = f1.selectbox(
        "Parametro da Visualizzare",
        [m[0] for m in metric_opts],
        format_func=lambda k: dict(metric_opts)[k],
        index=0,
        key="sel_6w_metric",
    )

    week_options, default_week_idx = _get_available_weeks_options()
    week_labels = [w[1] for w in week_options]
    week_dict = {w[1]: w[0] for w in week_options}

    if "sel_6w_week" in st.session_state and "19/10" in str(st.session_state["sel_6w_week"]):
        st.session_state["sel_6w_week"] = week_labels[default_week_idx]

    sel_week_lbl = f2.selectbox(
        "Settimana di Riferimento (Week)",
        week_labels,
        index=default_week_idx,
        help="In automatico posizionato sulla settimana attuale. Seleziona qualsiasi settimana a ritroso.",
        key="sel_6w_week",
    )
    ref_mon_input = week_dict[sel_week_lbl]
    dept_filter = f3.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="sel_6w_dept")

    # Barra Filtri — Riga 2 (Filtro Ruolo, Ordinamento, Sorgente GPS, Ambito GIN, Ricerca Atleta)
    f4, f5, f6, f7, f8 = st.columns([1.3, 1.5, 1.3, 1.3, 2.0])
    roles_list = ["Tutti i Ruoli", "Pilone", "Tallonatore", "Seconda Linea", "Terza Linea", "Mediano di Mischia", "Apertura", "Centro", "Ala", "Estremo"]
    role_filter = f4.selectbox("Filtro Ruolo", roles_list, key="sel_6w_role")

    sort_mode = f5.selectbox(
        "Ordinamento Giocatori",
        ["ruoli", "carico_week", "acwr"],
        format_func=lambda k: {
            "ruoli": "1. Ordine Ufficiale Ruoli FIR (1-8)",
            "carico_week": "2. Ranking Carico Settimana Selezionata",
            "acwr": "3. Ranking ACWR (Rischio Elevato in cima)",
        }[k],
        index=0,
        key="sel_6w_sort",
    )

    team_filter = f6.selectbox(
        "Sorgente Dati GPS",
        ["all", "nazionale", "benetton", "zebre"],
        format_func=lambda k: {
            "all": "Tutti i Team (FIR + Club)",
            "nazionale": "Solo Nazionale (FIR)",
            "benetton": "Solo Benetton Treviso",
            "zebre": "Solo Zebre Parma",
        }[k],
        index=0,
        key="sel_6w_team",
    )

    gin_scope = f7.selectbox(
        "Ambito Monitoraggio",
        ["only_gin", "all_roster"],
        format_func=lambda x: "Solo Lista G.I.N." if x == "only_gin" else "Tutto il Roster FIR",
        index=0,
        key="sel_6w_gin_scope",
    )
    search_q = f8.text_input("Cerca Giocatore / Squadra", placeholder="Nome o squadra...", key="sel_6w_search")

    # Build report data
    active_calc_metric = "HML" if sel_metric == "ACWR" else ("DT" if sel_metric == "TUTTI" else sel_metric)
    rep_data = utils.build_gps_6weeks_report(
        ref_monday_str=ref_mon_input,
        metric=active_calc_metric,
        only_gin=(gin_scope == "only_gin"),
        sort_mode=sort_mode,
        team_filter=team_filter,
    )
    rep_df = rep_data["report_df"]
    weeks_meta = rep_data["weeks_meta"]

    # Filter by dept / role / search query
    if not rep_df.empty:
        if dept_filter != "Tutti":
            rep_df = rep_df[rep_df["department"] == dept_filter].copy()
        if role_filter != "Tutti i Ruoli":
            rep_df = rep_df[rep_df["role"].astype(str).str.contains(role_filter, case=False, na=False)].copy()
        if search_q.strip():
            q = search_q.strip().lower()
            rep_df = rep_df[
                rep_df["player_name"].astype(str).str.lower().str.contains(q)
                | rep_df["club"].astype(str).str.lower().str.contains(q)
            ].copy()
        rep_df = rep_df.reset_index(drop=True)

    # Summary KPI row
    n_atleti = len(rep_df)
    k1, k2, k3, k4 = st.columns(4)

    target_metric_kpi = "DT" if sel_metric in ("ACWR", "TUTTI") else sel_metric
    minfo_kpi = utils.GPS_6W_METRICS[target_metric_kpi]
    is_mx_kpi = minfo_kpi["is_max"]

    acute_vals = [r["metrics"][target_metric_kpi]["acute"] for _, r in rep_df.iterrows() if r["metrics"][target_metric_kpi]["acute"] > 0]
    avg_acute = np.mean(acute_vals) if acute_vals else 0.0

    chron_vals = [r["metrics"][target_metric_kpi]["chronic"] for _, r in rep_df.iterrows() if r["metrics"][target_metric_kpi]["chronic"] > 0]
    avg_chron = np.mean(chron_vals) if chron_vals else 0.0

    acwr_vals = [r["metrics"][target_metric_kpi]["acwr"] for _, r in rep_df.iterrows() if r["metrics"][target_metric_kpi]["acwr"] > 0]
    avg_acwr = np.mean(acwr_vals) if acwr_vals else 0.0

    sweet_spot_count = sum(1 for v in acwr_vals if 0.80 <= v <= 1.30)
    sweet_pct = int(round((sweet_spot_count / len(acwr_vals)) * 100)) if acwr_vals else 0

    if is_mx_kpi:
        k1.metric(f"Media Week: {minfo_kpi['short_name']}", f"{avg_acute:.1f} {minfo_kpi['unit']}", f"{len(acute_vals)} atleti con dati")
        k2.metric(f"Media Cronica 4W", f"{avg_chron:.1f} {minfo_kpi['unit']}", f"Ultime 4 settimane")
    else:
        k1.metric(f"Media Week: {minfo_kpi['short_name']}", f"{int(round(avg_acute)):,} {minfo_kpi['unit']}".replace(",", "."), f"{len(acute_vals)} atleti attivi")
        k2.metric(f"Media Cronica 4W", f"{int(round(avg_chron)):,} {minfo_kpi['unit']}".replace(",", "."), f"Media mobile 28gg")

    k3.metric("ACWR Medio Squadra", f"{avg_acwr:.1f}".replace(".", ","), f"Gabbett Sweet Spot: 0.8 - 1.3")
    k4.metric("Atleti in Sweet Spot", f"{sweet_pct}%", f"{sweet_spot_count} su {len(acwr_vals)} atleti")

    # Enterprise Action Bar con esportazione PDF ReportLab
    action_meta = [
        ("Settimana", f"{weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']}"),
        ("Parametro Attivo", dict(metric_opts)[sel_metric]),
        ("Atleti Monitorati", f"{n_atleti}"),
        ("Ordinamento", "Ruoli FIR" if sort_mode == "ruoli" else ("Carico Week" if sort_mode == "carico_week" else "ACWR")),
        ("Filtro Reparto", dept_filter),
    ]

    pdf_opts = {
        "Report Ufficiale FIR (Tutti i 6 Parametri + ACWR • Stile Federale)": "completo_federale",
        "Report Parametro Attivo (Con Medie Ruolo e Reparto)": "singolo_parametro",
        "Report Suddiviso per Reparto (Avanti & TreQuarti)": "ruoli_split",
    }

    render_action_bar(
        meta_items=action_meta,
        pdf_options=pdf_opts,
        pdf_key=f"rep_6w_{sel_metric}_{ref_mon_input}_{dept_filter}_{role_filter}",
        generate_fn=lambda sub_code: crea_pdf_report_6weeks(
            sub_code=sub_code,
            rep_df=rep_df,
            weeks_meta=weeks_meta,
            metric_key=target_metric_kpi,
            rep_meta=rep_data,
            sort_mode=sort_mode,
        ),
        filename_fn=lambda sub_code: f"FIR_Report_6Weeks_{sel_metric}_{ref_mon_input}.pdf",
    )

    # Render Main View Table
    if sel_metric == "ACWR":
        html_table = _build_acwr_matrix_html(rep_df, weeks_meta)
        _clean_and_render_html(html_table)
    elif sel_metric == "TUTTI":
        _clean_and_render_html(
            """
            <div style="background:#EFF6FF; border:1px solid #BFDBFE; border-left:4px solid #0066B2; border-radius:8px; padding:10px 14px; margin-bottom:14px; font-size:0.82rem; color:#1E3A8A;">
                <b>Modalità Report Federale Multi-Parametro:</b> di seguito sono riportate le 6 tabelle longitudinali corrispondenti alle metriche ufficiali del Report FIR (DT, HML, HSR 18, HSR 20, HSR 25, Vmax) e la matrice ACWR.
            </div>
            """
        )
        for m_k in ["DT", "HML", "HSR_18", "HSR_20", "HSR_25", "VMAX"]:
            html_sub = _build_single_metric_html(rep_df, weeks_meta, m_k, rep_data, sort_mode)
            _clean_and_render_html(html_sub)
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        _clean_and_render_html(_build_acwr_matrix_html(rep_df, weeks_meta))
    else:
        html_table = _build_single_metric_html(rep_df, weeks_meta, sel_metric, rep_data, sort_mode)
        _clean_and_render_html(html_table)


def _build_franchige_day_html_table(rep_df: pd.DataFrame, is_match_day: bool, rep_meta: dict, sort_mode: str) -> str:
    if rep_df.empty:
        return "<div style='padding:20px; color:#64748B;'>Nessun dato disponibile con i filtri selezionati.</div>"

    max_dt = max(int(rep_df["distance_m"].max()), 1000)
    max_hml = max(int(rep_df["hml"].max()), 200)
    max_hsr18 = max(int(rep_df["hsr_18"].max()), 100)
    max_hsr20 = max(int(rep_df["hsr_20"].max()), 80)

    rows_html = ""
    prev_dept = None
    for _, r in rep_df.iterrows():
        dept = r["department"]
        top_border = "border-top: 2px solid #CBD5E1;" if prev_dept and prev_dept != dept and sort_mode == "ruoli" else ""
        prev_dept = dept

        has_data = r["has_gps"] or r["has_match"]
        bg_row = "#FFFFFF" if has_data else "#FAFAFA"

        dur_val = int(round(r["duration"]))
        dur_s = f"{dur_val}'" if dur_val > 0 else "<span style='color:#CBD5E1;'>0</span>"

        # DT progress bar
        dt_v = int(round(r["distance_m"]))
        if dt_v > 0:
            dt_pct = min(100, int(round((dt_v / max_dt) * 100)))
            dt_cell = (
                f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:1px solid #CBD5E1; border-radius:3px; overflow:hidden;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{dt_pct}%; background:rgba(34,197,94,0.38);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:700; font-size:0.72rem; color:#064E3B; line-height:17px;'>{dt_v:,}</div></div>"
            ).replace(",", ".")
        else:
            dt_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>0</span>"

        mmin_v = r["m_per_min"]
        mmin_s = f"{mmin_v:.1f}".replace(".", ",") if mmin_v > 0 else "<span style='color:#CBD5E1;'>0</span>"

        # HML progress bar
        hml_v = int(round(r["hml"]))
        if hml_v > 0:
            hml_pct = min(100, int(round((hml_v / max_hml) * 100)))
            hml_cell = (
                f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:1px solid #CBD5E1; border-radius:3px; overflow:hidden;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{hml_pct}%; background:rgba(56,189,248,0.40);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:700; font-size:0.72rem; color:#0369A1; line-height:17px;'>{hml_v:,}</div></div>"
            ).replace(",", ".")
        else:
            hml_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>0</span>"

        # HSR 18
        h18_v = int(round(r["hsr_18"]))
        if h18_v > 0:
            h18_pct = min(100, int(round((h18_v / max_hsr18) * 100)))
            h18_cell = (
                f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:1px solid #FECACA; border-radius:3px; overflow:hidden;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{h18_pct}%; background:rgba(239,68,68,0.35);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:700; font-size:0.72rem; color:#991B1B; line-height:17px;'>{h18_v:,}</div></div>"
            ).replace(",", ".")
        else:
            h18_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>0</span>"

        # HSR 20
        h20_v = int(round(r["hsr_20"]))
        if h20_v > 0:
            h20_pct = min(100, int(round((h20_v / max_hsr20) * 100)))
            h20_cell = (
                f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:1px solid #FECDD3; border-radius:3px; overflow:hidden;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{h20_pct}%; background:rgba(244,63,94,0.35);'></div>"
                f"<div style='position:relative; z-index:1; font-weight:700; font-size:0.72rem; color:#881337; line-height:17px;'>{h20_v:,}</div></div>"
            ).replace(",", ".")
        else:
            h20_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>0</span>"

        # HSR 25
        h25_v = int(round(r["hsr_25"]))
        h25_s = f"<b>{h25_v}</b>" if h25_v > 0 else "<span style='color:#CBD5E1;'>0</span>"

        # Vmax
        vm_v = r["v_max"]
        if vm_v > 0:
            vm_bg = "#FEF08A" if vm_v >= 30.0 else "#F1F5F9"
            vm_col = "#854D0E" if vm_v >= 30.0 else "#0F172A"
            vm_cell = f"<span style='display:inline-block; padding:1px 6px; border-radius:4px; font-weight:800; font-size:0.72rem; background:{vm_bg}; color:{vm_col};'>{vm_v:.1f}</span>"
        else:
            vm_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>0</span>"

        # Match columns (se Match Day)
        match_tds = ""
        if is_match_day:
            g_title = str(r["game"] or "").strip()
            m_min = int(r["match_min"])
            is_st = bool(r["is_starter"])
            res = str(r["result"] or "").strip()

            if m_min > 0:
                m_pct = min(100, int(round((m_min / 80.0) * 100)))
                cell_border = "2px solid #EF4444" if is_st else "1px solid #93C5FD"
                bar_bg = "rgba(56,189,248,0.50)" if is_st else "rgba(125,211,252,0.38)"
                min_cell = (
                    f"<div style='position:relative; width:100%; height:19px; background:#F8FAFC; border:{cell_border}; border-radius:3px; overflow:hidden;'>"
                    f"<div style='position:absolute; left:0; top:0; bottom:0; width:{m_pct}%; background:{bar_bg};'></div>"
                    f"<div style='position:relative; z-index:1; font-weight:800; font-size:0.72rem; color:#0F172A; line-height:16px;'>{m_min}'</div></div>"
                )
                imp_badge = (
                    "<span style='display:inline-block; padding:1px 5px; border-radius:3px; font-weight:800; font-size:0.67rem; background:#FEE2E2; color:#B91C1C; border:1px solid #FECACA;'>TITOLARE</span>"
                    if is_st
                    else "<span style='display:inline-block; padding:1px 5px; border-radius:3px; font-weight:700; font-size:0.67rem; background:#E0F2FE; color:#0369A1;'>FINISHER</span>"
                )
            else:
                min_cell = "<span style='color:#CBD5E1; font-size:0.70rem;'>-</span>"
                imp_badge = "<span style='color:#CBD5E1; font-size:0.70rem;'>-</span>"

            if res:
                res_bg = "#DCFCE7" if res.startswith("W") else ("#FEE2E2" if res.startswith("L") else "#F1F5F9")
                res_col = "#15803D" if res.startswith("W") else ("#B91C1C" if res.startswith("L") else "#475569")
                res_badge = f"<span style='display:inline-block; padding:1px 5px; border-radius:3px; font-weight:800; font-size:0.68rem; background:{res_bg}; color:{res_col};'>{res}</span>"
            else:
                res_badge = "<span style='color:#CBD5E1; font-size:0.70rem;'>-</span>"

            match_tds = f"""
            <td style='padding:3px 6px; font-size:0.70rem; color:#0F172A; border:1px solid #E2E8F0; white-space:nowrap;'>{g_title if g_title else "<span style='color:#94A3B8;'>-</span>"}</td>
            <td style='padding:2px 4px; border:1px solid #E2E8F0; text-align:center; min-width:55px;'>{min_cell}</td>
            <td style='padding:3px 4px; border:1px solid #E2E8F0; text-align:center; white-space:nowrap;'>{imp_badge}</td>
            <td style='padding:3px 4px; border:1px solid #E2E8F0; text-align:center; border-right:2px solid #0066B2;'>{res_badge}</td>
            """

        rows_html += f"""
        <tr style='background:{bg_row}; {top_border}'>
            <td style='position:sticky; left:0; z-index:2; background:{bg_row}; box-shadow:2px 0 5px rgba(15,23,42,0.08); padding:3px 8px; font-weight:700; font-size:0.75rem; color:#0F172A; border:1px solid #CBD5E1; white-space:nowrap;'>{r['player_name']}</td>
            <td style='padding:3px 6px; font-size:0.70rem; color:#1E40AF; font-weight:600; border:1px solid #E2E8F0; white-space:nowrap;'>{r['role']}</td>
            <td style='padding:3px 6px; font-size:0.70rem; color:#475569; border:1px solid #E2E8F0; white-space:nowrap;'>{r['club']}</td>
            <td style='padding:3px 4px; font-size:0.69rem; color:#64748B; text-align:center; border:1px solid #E2E8F0; border-right:2px solid #0284C7;'>{r['birth_year']}</td>
            {match_tds}
            <td style='padding:3px 4px; text-align:center; font-weight:600; font-size:0.71rem; color:#475569; border:1px solid #E2E8F0;'>{dur_s}</td>
            <td style='padding:2px 4px; text-align:center; border:1px solid #E2E8F0; min-width:70px;'>{dt_cell}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:600; font-size:0.71rem; color:#0F172A; border:1px solid #E2E8F0;'>{mmin_s}</td>
            <td style='padding:2px 4px; text-align:center; border:1px solid #E2E8F0; min-width:68px;'>{hml_cell}</td>
            <td style='padding:2px 4px; text-align:center; border:1px solid #E2E8F0; min-width:64px;'>{h18_cell}</td>
            <td style='padding:2px 4px; text-align:center; border:1px solid #E2E8F0; min-width:60px;'>{h20_cell}</td>
            <td style='padding:3px 4px; text-align:center; font-size:0.71rem; border:1px solid #E2E8F0;'>{h25_s}</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #E2E8F0;'>{vm_cell}</td>
        </tr>
        """

    # Department & Squad Averages
    d_avgs = rep_meta.get("dept_averages", {})
    sq_stat = rep_meta.get("squad_totals", {})

    avg_rows_html = ""
    for d_name in ["Avanti", "TreQuarti"]:
        st_d = d_avgs.get(d_name, {})
        if not st_d or st_d.get("n_tot", 0) == 0:
            continue
        dt_avg = f"{st_d.get('distance_m', 0):,}".replace(",", ".")
        hml_avg = f"{st_d.get('hml', 0):,}".replace(",", ".")
        h18_avg = f"{st_d.get('hsr_18', 0):,}".replace(",", ".")
        h20_avg = f"{st_d.get('hsr_20', 0):,}".replace(",", ".")
        h25_avg = f"{st_d.get('hsr_25', 0):,}".replace(",", ".")
        dur_avg = f"{int(round(st_d.get('duration', 0)))}'"
        mmin_avg = f"{st_d.get('m_per_min', 0.0):.1f}".replace(".", ",")
        vm_avg = f"{st_d.get('v_max_avg', 0.0):.1f}".replace(".", ",")

        m_tds_avg = ""
        if is_match_day:
            m_tds_avg = f"""
            <td style='padding:4px 6px; font-weight:700; font-size:0.71rem; color:#0369A1; border:1px solid #CBD5E1;'>{st_d.get('n_match', 0)} atleti gara</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0F172A; border:1px solid #CBD5E1;'>{int(st_d.get('match_min_avg', 0))}'</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #CBD5E1;'>-</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #CBD5E1; border-right:2px solid #0066B2;'>-</td>
            """

        avg_rows_html += f"""
        <tr style='background:#F1F5F9; border-top:1.5px solid #94A3B8;'>
            <td style='position:sticky; left:0; z-index:2; background:#F1F5F9; padding:4px 8px; font-weight:800; font-size:0.74rem; color:#1E3A8A; border:1px solid #CBD5E1;'>MEDIA REPARTO: {d_name.upper()}</td>
            <td colspan='3' style='padding:4px 6px; font-weight:600; font-size:0.70rem; color:#475569; border:1px solid #CBD5E1; border-right:2px solid #0284C7;'>{st_d.get('n_gps', 0)} atleti GPS</td>
            {m_tds_avg}
            <td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#0F172A; border:1px solid #CBD5E1;'>{dur_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#064E3B; border:1px solid #CBD5E1;'>{dt_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#0F172A; border:1px solid #CBD5E1;'>{mmin_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0369A1; border:1px solid #CBD5E1;'>{hml_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#991B1B; border:1px solid #CBD5E1;'>{h18_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#881337; border:1px solid #CBD5E1;'>{h20_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:700; font-size:0.71rem; color:#0F172A; border:1px solid #CBD5E1;'>{h25_avg}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#854D0E; border:1px solid #CBD5E1;'>{vm_avg}</td>
        </tr>
        """

    # Squad row
    if sq_stat and sq_stat.get("n_tot", 0) > 0:
        dt_sq = f"{sq_stat.get('distance_m', 0):,}".replace(",", ".")
        hml_sq = f"{sq_stat.get('hml', 0):,}".replace(",", ".")
        h18_sq = f"{sq_stat.get('hsr_18', 0):,}".replace(",", ".")
        h20_sq = f"{sq_stat.get('hsr_20', 0):,}".replace(",", ".")
        h25_sq = f"{sq_stat.get('hsr_25', 0):,}".replace(",", ".")
        dur_sq = f"{int(round(sq_stat.get('duration', 0)))}'"
        mmin_sq = f"{sq_stat.get('m_per_min', 0.0):.1f}".replace(".", ",")
        vm_sq = f"{sq_stat.get('v_max_avg', 0.0):.1f}".replace(".", ",")

        m_tds_sq = ""
        if is_match_day:
            m_tds_sq = f"""
            <td style='padding:4px 6px; font-weight:800; font-size:0.71rem; color:#0369A1; border:1px solid #94A3B8;'>{sq_stat.get('n_match', 0)} gare totali</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.73rem; color:#0F172A; border:1px solid #94A3B8;'>{int(sq_stat.get('match_min_avg', 0))}'</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #94A3B8;'>-</td>
            <td style='padding:3px 4px; text-align:center; border:1px solid #94A3B8; border-right:2px solid #0066B2;'>-</td>
            """

        avg_rows_html += f"""
        <tr style='background:#E2E8F0; border-top:2px solid #0066B2;'>
            <td style='position:sticky; left:0; z-index:2; background:#E2E8F0; padding:4px 8px; font-weight:800; font-size:0.75rem; color:#0F172A; border:1px solid #94A3B8;'>MEDIA SQUADRA (G.I.N.)</td>
            <td colspan='3' style='padding:4px 6px; font-weight:700; font-size:0.71rem; color:#334155; border:1px solid #94A3B8; border-right:2px solid #0284C7;'>{sq_stat.get('n_gps', 0)} atleti attivi</td>
            {m_tds_sq}
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0F172A; border:1px solid #94A3B8;'>{dur_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.74rem; color:#064E3B; border:1px solid #94A3B8;'>{dt_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0F172A; border:1px solid #94A3B8;'>{mmin_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.74rem; color:#0369A1; border:1px solid #94A3B8;'>{hml_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#991B1B; border:1px solid #94A3B8;'>{h18_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#881337; border:1px solid #94A3B8;'>{h20_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.72rem; color:#0F172A; border:1px solid #94A3B8;'>{h25_sq}</td>
            <td style='padding:3px 4px; text-align:center; font-weight:800; font-size:0.74rem; color:#854D0E; border:1px solid #94A3B8;'>{vm_sq}</td>
        </tr>
        """

    # Table Header
    match_th = ""
    if is_match_day:
        match_th = """
        <th style="background:#0284C7; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #0369A1; text-align:left;">PARTITA (OVAL)</th>
        <th style="background:#0284C7; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 4px; border:1px solid #0369A1; text-align:center;">MIN</th>
        <th style="background:#0284C7; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 4px; border:1px solid #0369A1; text-align:center;">IMPIEGO</th>
        <th style="background:#0284C7; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 4px; border:1px solid #0369A1; border-right:2px solid #0066B2; text-align:center;">RIS</th>
        """

    date_title = rep_meta.get("date_disp", "")
    badge_type = f"<span style='background:#EF4444; color:#FFFFFF; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.72rem;'>MATCH DAY</span>" if is_match_day else f"<span style='background:#10B981; color:#FFFFFF; padding:2px 8px; border-radius:4px; font-weight:800; font-size:0.72rem;'>ALLENAMENTO</span>"

    html = f"""
    <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden; box-shadow:0 2px 8px rgba(15,23,42,0.06); margin-bottom:16px;">
        <div style="background:linear-gradient(90deg, #031926 0%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-weight:800; font-size:0.95rem; letter-spacing:0.02em;">REPORT CARICHI FRANCHIGE DAY &bull; {date_title}</span>
                {badge_type}
            </div>
            <span style="font-size:0.74rem; color:#E0F2FE;">Colonna NOME bloccata &bull; Bordo Rosso = <b>Starter</b> &bull; Barra Verde = <b>DT</b> &bull; Barra Blu = <b>HML</b></span>
        </div>
        <div style="overflow-x:auto; max-height:700px;">
            <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', -apple-system, sans-serif;">
                <thead style="position:sticky; top:0; z-index:3;">
                    <tr>
                        <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800; padding:6px 8px; border:1px solid #CBD5E1; text-align:left;">GIOCATORE</th>
                        <th style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left;">RUOLO</th>
                        <th style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 6px; border:1px solid #CBD5E1; text-align:left;">SQUADRA</th>
                        <th style="background:#F8FAFC; color:#334155; font-size:0.67rem; font-weight:700; padding:6px 4px; border:1px solid #CBD5E1; border-right:2px solid #0284C7; text-align:center;">ANNO</th>
                        {match_th}
                        <th style="background:#0F172A; color:#FFFFFF; font-size:0.67rem; font-weight:700; padding:5px 4px; border:1px solid #334155; text-align:center;">DURATA</th>
                        <th style="background:#064E3B; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #047857; text-align:center;">DISTANZA (DT)</th>
                        <th style="background:#0F172A; color:#FFFFFF; font-size:0.67rem; font-weight:700; padding:5px 4px; border:1px solid #334155; text-align:center;">m/min</th>
                        <th style="background:#0369A1; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 6px; border:1px solid #0284C7; text-align:center;">HML &gt;25.5W</th>
                        <th style="background:#991B1B; color:#FFFFFF; font-size:0.67rem; font-weight:700; padding:5px 4px; border:1px solid #B91C1C; text-align:center;">HSR &gt;18</th>
                        <th style="background:#881337; color:#FFFFFF; font-size:0.67rem; font-weight:700; padding:5px 4px; border:1px solid #BE123C; text-align:center;">HSR &gt;20</th>
                        <th style="background:#0F172A; color:#FFFFFF; font-size:0.67rem; font-weight:700; padding:5px 4px; border:1px solid #334155; text-align:center;">HSR &gt;25</th>
                        <th style="background:#854D0E; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:5px 4px; border:1px solid #A16207; text-align:center;">V MAX</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                    {avg_rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """
    return "".join(line.strip() for line in html.splitlines() if line.strip())


def _render_tab_franchige_day(t: dict):
    # Top Expander: Configurazione Lista G.I.N.
    _render_gin_list_manager()

    day_options = utils.get_available_franchige_days()
    if not day_options:
        st.warning("Nessuna data trovata nel database GPS o Oval Match.")
        return

    day_labels = [d[1] for d in day_options]
    day_dict = {d[1]: d[0] for d in day_options}

    # Default index: prima giornata Match Day disponibile tra le recenti (es. 24/10/2026 o 31/10/2026) o prima data assoluta
    default_day_idx = 0
    for idx, d_tup in enumerate(day_options):
        if d_tup[2]:  # is_match
            default_day_idx = idx
            break

    # Barra Filtri — Riga 1 (Giorno da Analizzare, Reparto, Ruolo)
    d1, d2, d3 = st.columns([2.8, 1.2, 1.4])

    sel_day_lbl = d1.selectbox(
        "Giorno da Analizzare (Franchige & Nazionale)",
        day_labels,
        index=default_day_idx,
        help="Seleziona qualsiasi data dal 2024 ad oggi. Le giornate con gare ufficiali (URC, Champions, Test Match) sono etichettate come MATCH DAY.",
        key="sel_day_date_picker",
    )
    sel_date_str = day_dict[sel_day_lbl]

    dept_filter = d2.selectbox("Filtro Reparto", ["Tutti", "Avanti", "TreQuarti"], key="day_dept_filter")
    roles_list = ["Tutti i Ruoli", "Pilone", "Tallonatore", "Seconda Linea", "Terza Linea", "Mediano di Mischia", "Apertura", "Centro", "Ala", "Estremo"]
    role_filter = d3.selectbox("Filtro Ruolo", roles_list, key="day_role_filter")

    # Barra Filtri — Riga 2 (Ordinamento, Sorgente GPS, Ambito GIN, Presenza Giornata, Ricerca Atleta)
    d4, d5, d6, d7, d8 = st.columns([1.5, 1.3, 1.3, 1.4, 2.0])

    sort_mode = d4.selectbox(
        "Ordinamento Giocatori",
        ["ruoli", "match_min", "distance_m", "hml", "hsr_18", "v_max"],
        format_func=lambda k: {
            "ruoli": "1. Ordine Ufficiale Ruoli FIR (1-9)",
            "match_min": "2. Minuti Giocati (se Match Day)",
            "distance_m": "3. Distanza Totale (DT)",
            "hml": "4. High Metabolic Load (HML)",
            "hsr_18": "5. High Speed Running (>18 km/h)",
            "v_max": "6. Velocità Massima (Vmax)",
        }[k],
        index=0,
        key="day_sort_mode",
    )

    team_filter = d5.selectbox(
        "Sorgente Dati GPS",
        ["all", "nazionale", "benetton", "zebre"],
        format_func=lambda k: {
            "all": "Tutti i Team (FIR + Club)",
            "nazionale": "Solo Nazionale (FIR)",
            "benetton": "Solo Benetton Treviso",
            "zebre": "Solo Zebre Parma",
        }[k],
        index=0,
        key="day_team_filter",
    )

    gin_scope = d6.selectbox(
        "Ambito Monitoraggio",
        ["only_gin", "all_roster"],
        format_func=lambda x: "Solo Lista G.I.N." if x == "only_gin" else "Tutto il Roster FIR",
        index=0,
        key="day_gin_scope",
    )

    active_filter = d7.selectbox(
        "Presenza Giornata",
        ["all_selected", "only_active"],
        format_func=lambda x: "Tutti gli Atleti Monitorati" if x == "all_selected" else "Solo Attivi Oggi (GPS o Gara)",
        index=0,
        key="day_active_filter",
    )

    search_q = d8.text_input("Cerca Giocatore / Squadra", placeholder="Nome o club...", key="day_search_q")

    # Build Day Data
    day_meta = utils.build_franchige_day_report(
        sel_date_str=sel_date_str,
        only_gin=(gin_scope == "only_gin"),
        sort_mode=sort_mode,
        team_filter=team_filter,
    )
    rep_df = day_meta["report_df"]
    is_match_day = day_meta["is_match_day"]

    # Filter by dept / role / active / search
    if not rep_df.empty:
        if dept_filter != "Tutti":
            rep_df = rep_df[rep_df["department"] == dept_filter].copy()
        if role_filter != "Tutti i Ruoli":
            rep_df = rep_df[rep_df["role"].astype(str).str.contains(role_filter, case=False, na=False)].copy()
        if active_filter == "only_active":
            rep_df = rep_df[(rep_df["has_gps"] == True) | (rep_df["has_match"] == True)].copy()
        if search_q.strip():
            q = search_q.strip().lower()
            rep_df = rep_df[
                rep_df["player_name"].astype(str).str.lower().str.contains(q)
                | rep_df["club"].astype(str).str.lower().str.contains(q)
                | rep_df["game"].astype(str).str.lower().str.contains(q)
            ].copy()
        rep_df = rep_df.reset_index(drop=True)

    # Match Day Banner
    if is_match_day:
        st.markdown(
            f"""
            <div style="background:linear-gradient(90deg, #FFF1F2 0%, #FFE4E6 100%); border:1.5px solid #FECDD3; border-left:6px solid #E11D48; border-radius:10px; padding:10px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-size:0.72rem; font-weight:800; text-transform:uppercase; letter-spacing:0.08em; color:#BE123C;">MATCH DAY RICONOSCIUTO ({day_meta['date_disp']})</span>
                    <div style="font-size:0.92rem; font-weight:800; color:#881337; margin-top:2px;">
                        {day_meta['match_summary']}
                    </div>
                </div>
                <div style="text-align:right;">
                    <span style="display:inline-block; padding:3px 10px; border-radius:6px; background:#BE123C; color:#FFFFFF; font-weight:800; font-size:0.76rem;">GARA UFFICIALE URC / CLUB</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Summary KPI Cards
    sq_stat = day_meta.get("squad_totals", {})
    k1, k2, k3, k4, k5 = st.columns(5)

    n_gps_act = sq_stat.get("n_gps", 0)
    k1.metric("Atleti Attivi GPS", f"{n_gps_act}", f"su {len(rep_df)} monitorati")

    if is_match_day:
        n_match = sq_stat.get("n_match", 0)
        tot_min = sq_stat.get("match_min_tot", 0)
        k2.metric("Atleti in Partita", f"{n_match}", f"{tot_min}' minuti totali")
    else:
        avg_dur = sq_stat.get("duration", 0.0)
        k2.metric("Durata Media Seduta", f"{avg_dur:.0f} min", "Minuti in campo")

    dt_sq = sq_stat.get("distance_m", 0)
    k3.metric("Media Distanza (DT)", f"{dt_sq:,} m".replace(",", "."), f"Media squadra")

    hml_sq = sq_stat.get("hml", 0)
    k4.metric("Media HML (>25.5W)", f"{hml_sq:,} m".replace(",", "."), f"Carico metabolico")

    vm_peak = sq_stat.get("v_max_peak", 0.0)
    # Find fastest player
    fastest_p = ""
    if not rep_df.empty:
        fast_row = rep_df.loc[rep_df["v_max"].idxmax()]
        if fast_row["v_max"] > 0:
            fastest_p = f"{fast_row['player_name'].split()[-1]}"
    k5.metric("Picco Velocità Max", f"{vm_peak:.1f} km/h".replace(".", ","), fastest_p if fastest_p else "Top Squadra")

    # Action Bar con Esportazione PDF
    action_meta = [
        ("Data Analizzata", day_meta["date_disp"]),
        ("Tipo Giornata", "Match Day (Gara Ufficiale)" if is_match_day else "Seduta di Allenamento"),
        ("Atleti Monitorati", f"{len(rep_df)} ({n_gps_act} con GPS)"),
        ("Ordinamento", sort_mode.replace("_", " ").title()),
        ("Filtro Reparto", dept_filter),
    ]

    pdf_opts = {
        "Report Ufficiale Franchige Day (Tabella Coordinata Completa)": "completo",
        "Report Suddiviso per Reparto (Foglio 1: Avanti, Foglio 2: TreQuarti)": "ruoli_split",
    }

    render_action_bar(
        meta_items=action_meta,
        pdf_options=pdf_opts,
        pdf_key=f"rep_day_{sel_date_str}_{dept_filter}_{role_filter}_{active_filter}",
        generate_fn=lambda sub_code: crea_pdf_report_franchige_day(
            sub_code=sub_code,
            rep_df=rep_df,
            date_str=sel_date_str,
            is_match_day=is_match_day,
            rep_meta=day_meta,
            sort_mode=sort_mode,
        ),
        filename_fn=lambda sub_code: f"FIR_Report_Franchige_Day_{sel_date_str}.pdf",
    )

    # Main Interactive HTML Table
    table_html = _build_franchige_day_html_table(rep_df, is_match_day, day_meta, sort_mode)
    _clean_and_render_html(table_html)


def render_report_6weeks(t: dict):
    render_page_header(
        "Report Dati Franchigie",
        "Monitoraggio carichi di lavoro giornalieri (Day Report con Match & Minuti), analisi su 3 settimane per singolo atleta e report longitudinale su 6 settimane con ACWR (7gg / 28gg) per gli atleti G.I.N. (Nazionale + Club Benetton / Zebre)",
        "bi-calendar2-range-fill",
    )

    active_tab = render_tab_navigation(
        "franchige_day_6weeks",
        [
            ("day", "📅 Report Franchigie Day (Carico & Match)", "bi-calendar2-day-fill"),
            ("singolo_atleta_3w", "👤 Analisi Singolo Atleta (3 Settimane)", "bi-person-bounding-box"),
            ("6weeks", "📈 Report 6 Weeks & ACWR Longitudinal", "bi-calendar-range-fill"),
        ],
    )

    if active_tab == "day":
        _render_tab_franchige_day(t)
    elif active_tab == "singolo_atleta_3w":
        _render_tab_singolo_atleta_3w(t)
    else:
        _render_tab_report_6weeks(t)


# ==============================================================================
# 3. ANALISI SINGOLO ATLETA (PASSAPORTO UNIFICATO & 3 SETTIMANE DAY-BY-DAY)
# ==============================================================================
@st.fragment
def _render_tab_singolo_atleta_3w(t: dict):
    st.markdown("### 👤 Passaporto Unificato Giocatore & Analisi Carico (Database Totale FIR + Club + Oval)")
    st.caption("Vista unificata con filtro rapido per Reparto/Ruolo, Semaforo Esposizione Vmax/Vmax%, Densità Specifica (HML/min & HSR/min), Benchmark Match 80', Storico Gare Oval e progressione giornaliera 21 giorni.")

    all_gps = utils.get_gps_history_df("all")
    if all_gps.empty:
        st.info("Nessun dato GPS presente nel database totale.")
        return

    players_df = utils.get_players_df()
    roster_map = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip()
            if nm:
                roster_map[nm.upper()] = pr.to_dict()

    # Opzioni Settimane disponibili
    week_options, default_week_idx = _get_available_weeks_options()
    week_labels = [w[1] for w in week_options]
    week_dict = {w[1]: w[0] for w in week_options}

    if "p3w_sel_week" in st.session_state and "19/10" in str(st.session_state["p3w_sel_week"]):
        st.session_state["p3w_sel_week"] = week_labels[default_week_idx]

    # Barra Filtri Giocatore Unificata (Settimana, Reparto, Ruolo, Giocatore)
    f_col1, f_col2, f_col3, f_col4 = st.columns([1.5, 1.0, 1.2, 2.0])
    sel_week_lbl = f_col1.selectbox(
        "1. Settimana di Riferimento (Week 0)",
        week_labels,
        index=default_week_idx,
        help="La settimana scelta sarà la 'Week 0' e verranno estratte anche le due settimane precedenti (Week -1 e Week -2).",
        key="p3w_sel_week",
    )
    filt_dept = f_col2.selectbox(
        "2. Filtro Reparto",
        ["Tutti", "Avanti", "TreQuarti"],
        key="p3w_filt_dept",
    )
    roles_opts = ["Tutti i Ruoli"] + sorted(list({str(v.get("role") or "") for v in roster_map.values() if str(v.get("role") or "").strip()}))
    filt_role = f_col3.selectbox(
        "3. Filtro Ruolo",
        roles_opts,
        key="p3w_filt_role",
    )

    all_players_raw = sorted(list(set(all_gps["player_name"].dropna().astype(str).tolist())))
    all_players = []
    for pn in all_players_raw:
        pm = roster_map.get(pn.strip().upper(), {})
        r_p = str(pm.get("role") or "Avanti")
        d_p = str(pm.get("department") or ROLE_TO_DEPT.get(r_p, "Avanti"))
        if filt_dept != "Tutti" and d_p != filt_dept:
            continue
        if filt_role != "Tutti i Ruoli" and r_p != filt_role:
            continue
        all_players.append(pn)

    if not all_players:
        all_players = all_players_raw

    pref_idx = 0
    for cand in ["Michele Lamaro", "Danilo Fischetti", "Paolo Garbisi", "Sebastian Negri"]:
        if cand in all_players:
            pref_idx = all_players.index(cand)
            break
    if "p3w_sel_player" in st.session_state and st.session_state["p3w_sel_player"] not in all_players:
        st.session_state["p3w_sel_player"] = all_players[pref_idx]

    sel_player = f_col4.selectbox(
        f"4. Seleziona Atleta ({len(all_players)} disponibili)",
        all_players,
        index=pref_idx,
        key="p3w_sel_player",
    )

    ref_mon_str = week_dict[sel_week_lbl]
    try:
        ref_mon = pd.to_datetime(ref_mon_str)
    except Exception:
        import datetime
        _today = pd.to_datetime(datetime.date.today())
        ref_mon = _today - pd.Timedelta(days=_today.weekday())
    ref_mon = ref_mon - pd.Timedelta(days=ref_mon.weekday())

    # Date dei 3 blocchi settimanali
    w0_mon = ref_mon
    w0_sun = ref_mon + pd.Timedelta(days=6)
    w1_mon = ref_mon - pd.Timedelta(days=7)
    w1_sun = ref_mon - pd.Timedelta(days=1)
    w2_mon = ref_mon - pd.Timedelta(days=14)
    w2_sun = ref_mon - pd.Timedelta(days=8)

    w2_mon_str = w2_mon.strftime("%Y-%m-%d")
    w0_sun_str = w0_sun.strftime("%Y-%m-%d")

    # Informazioni anagrafiche e benchmark giocatore
    p_meta = roster_map.get(sel_player.upper(), {})
    p_role = str(p_meta.get("role") or "Avanti")
    p_dept = str(p_meta.get("department") or ROLE_TO_DEPT.get(p_role, "Avanti"))
    p_club = str(p_meta.get("club") or "FIR")
    p_vmax_ref = float(p_meta.get("v_max") or 30.0)
    if p_vmax_ref <= 0:
        p_vmax_ref = 30.0
    p_hml_80 = float(p_meta.get("match_avg_hml") or p_meta.get("hml_avg_tot") or (560.0 if p_dept == "Avanti" else 880.0))
    p_hsr_80 = float(p_meta.get("match_avg_hsr") or p_meta.get("hsr_avg_tot") or (210.0 if p_dept == "Avanti" else 420.0))
    p_hml_min_ref = p_hml_80 / 80.0
    p_hsr_min_ref = p_hsr_80 / 80.0

    # Storico totale giocatore fino a w0_sun_str per Semaforo Vmax
    p_all_hist = all_gps[
        (all_gps["player_name"].astype(str).str.strip().str.upper() == sel_player.strip().upper())
        & (all_gps["date_str"] <= w0_sun_str)
    ].copy()
    if not p_all_hist.empty:
        p_all_hist["v_max"] = pd.to_numeric(p_all_hist["v_max"], errors="coerce").fillna(0.0)
        p_all_hist["v_max_pct"] = pd.to_numeric(p_all_hist.get("v_max_pct", 0), errors="coerce").fillna(0.0)
        p_all_hist["calc_pct"] = np.where(
            p_all_hist["v_max_pct"] > 0,
            p_all_hist["v_max_pct"],
            (p_all_hist["v_max"] / p_vmax_ref) * 100.0,
        )
        hit85 = p_all_hist[p_all_hist["calc_pct"] >= 85.0]
        hit90 = p_all_hist[p_all_hist["calc_pct"] >= 90.0]
        last85 = str(hit85["date_str"].max()) if not hit85.empty else None
        last90 = str(hit90["date_str"].max()) if not hit90.empty else None
        days85 = int((w0_sun - pd.to_datetime(last85)).days) if last85 else 999
        days90 = int((w0_sun - pd.to_datetime(last90)).days) if last90 else 999
    else:
        last85 = last90 = None
        days85 = days90 = 999

    if days85 <= 7:
        sem_badge = f"🟢 Vmax ≥85%: {days85}gg fa ({last85})"
        sem_bg = "#15803D"
    elif days85 <= 14:
        sem_badge = f"🟡 Vmax ≥85%: {days85}gg fa ({last85})"
        sem_bg = "#B45309"
    else:
        sem_badge = f"🔴 Vmax ≥85%: {'Mai' if not last85 else f'{days85}gg fa'}"
        sem_bg = "#B91C1C"

    # Filtraggio dati GPS del giocatore nel periodo dei 21 giorni
    p_gps = p_all_hist[p_all_hist["date_str"] >= w2_mon_str].copy() if not p_all_hist.empty else pd.DataFrame()

    # Caricamento dati Oval Match per minutaggi di gara (sia 21 giorni che stagione)
    ov_df = utils.get_oval_matches_df()
    p_ov_all = pd.DataFrame()
    p_ov = pd.DataFrame()
    if not ov_df.empty:
        p_ov_all = ov_df[
            (ov_df["fir_player_name"].astype(str).str.strip().str.upper() == sel_player.strip().upper())
            | (ov_df["playerFullName"].astype(str).str.strip().str.upper() == sel_player.strip().upper())
        ].copy()
        if not p_ov_all.empty and "match_date" in p_ov_all.columns:
            p_ov = p_ov_all[(p_ov_all["match_date"].astype(str) >= w2_mon_str) & (p_ov_all["match_date"].astype(str) <= w0_sun_str)]

    season_caps = int((pd.to_numeric(p_ov_all.get("Min", 0), errors="coerce").fillna(0) > 0).sum()) if not p_ov_all.empty else 0
    season_mins = int(pd.to_numeric(p_ov_all.get("Min", 0), errors="coerce").fillna(0).sum()) if not p_ov_all.empty else 0

    # Foto atleta
    photo_b64 = utils.get_player_photo_base64(sel_player, max_width=120)
    if photo_b64:
        photo_html = f'<img src="data:image/jpeg;base64,{photo_b64}" style="width:76px; height:88px; object-fit:cover; border-radius:10px; border:2px solid #D4AF37; box-shadow:0 4px 10px rgba(0,0,0,0.25);" alt="{sel_player}">'
    else:
        inits = "".join(part[0] for part in sel_player.split()[:2]).upper()
        photo_html = f'<div style="width:76px; height:88px; border-radius:10px; background:#002B49; border:2px solid #D4AF37; display:flex; align-items:center; justify-content:center; color:#D4AF37; font-weight:800; font-size:1.8rem; box-shadow:0 4px 10px rgba(0,0,0,0.25);">{inits}</div>'

    # Banner Passaporto Unificato Atleta
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, #002B49 0%, #004D7A 100%); border:2px solid #D4AF37; border-radius:14px; padding:14px 18px; margin:10px 0 16px 0; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px; box-shadow:0 6px 18px rgba(0,0,0,0.25);">
            <div style="display:flex; align-items:center; gap:16px;">
                {photo_html}
                <div>
                    <div style="font-size:0.70rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">PASSAPORTO FISICO &amp; MONITORAGGIO UNIFICATO</div>
                    <div style="font-size:1.65rem; font-weight:800; color:#FFFFFF; margin:2px 0;">{sel_player}</div>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:4px;">
                        <span style="background:#0284C7; color:#FFFFFF; font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px;">{p_role} ({p_dept})</span>
                        <span style="background:#059669; color:#FFFFFF; font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px;">{p_club}</span>
                        <span style="background:{sem_bg}; color:#FFFFFF; font-size:0.72rem; font-weight:800; padding:2px 8px; border-radius:4px;">{sem_badge}</span>
                    </div>
                </div>
            </div>
            <div style="display:flex; gap:12px; flex-wrap:wrap;">
                <div style="background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.16); border-radius:10px; padding:9px 14px; min-width:210px;">
                    <div style="font-size:0.66rem; font-weight:800; text-transform:uppercase; color:#D4AF37; margin-bottom:4px;">BENCHMARK MATCH 80' &amp; DENSITÀ</div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Vmax Profilo: <b>{p_vmax_ref:.1f} km/h</b></div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Target HML 80': <b>{p_hml_80:.0f} m</b> (<b>{p_hml_min_ref:.1f}</b> m/min)</div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Target HSR 80': <b>{p_hsr_80:.0f} m</b> (<b>{p_hsr_min_ref:.2f}</b> m/min)</div>
                </div>
                <div style="background:rgba(255,255,255,0.07); border:1px solid rgba(255,255,255,0.16); border-radius:10px; padding:9px 14px; min-width:210px;">
                    <div style="font-size:0.66rem; font-weight:800; text-transform:uppercase; color:#D4AF37; margin-bottom:4px;">STORICO GARE OVAL &amp; 21 GIORNI</div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Gare Archivio Oval: <b>{season_caps} presenze</b> ({season_mins}' tot)</div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Ultima ≥90% Vmax: <b>{last90 or 'N.D.'}</b></div>
                    <div style="font-size:0.78rem; color:#FFFFFF;">&bull; Finestra 3W: <b>{w2_mon.strftime('%d/%m')} &rarr; {w0_sun.strftime('%d/%m/%y')}</b></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Costruzione tabella completa dei 21 giorni
    giorni_ita = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    mesi_ita = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

    daily_rows = []
    current_day = w2_mon
    while current_day <= w0_sun:
        day_str = current_day.strftime("%Y-%m-%d")
        
        # Settimana di appartenenza
        if current_day < w1_mon:
            w_code = "Week -2"
            w_color = "#93C5FD"
            w_ord = 1
        elif current_day < w0_mon:
            w_code = "Week -1"
            w_color = "#818CF8"
            w_ord = 2
        else:
            w_code = "Week 0 (Attuale)"
            w_color = "#38BDF8"
            w_ord = 3

        day_label = f"{giorni_ita[current_day.weekday()]} {current_day.day} {mesi_ita[current_day.month - 1]}"

        # Ricerca dati GPS
        sub_day = p_gps[p_gps["date_str"] == day_str] if not p_gps.empty else pd.DataFrame()
        has_gps = not sub_day.empty and float(sub_day["distance_m"].sum()) > 0

        # Ricerca dati Oval Match
        sub_ov_day = p_ov[p_ov["match_date"].astype(str) == day_str] if not p_ov.empty else pd.DataFrame()
        has_match = not sub_ov_day.empty

        if has_gps:
            dt = float(sub_day["distance_m"].sum())
            dur = float(sub_day["duration"].sum()) if "duration" in sub_day.columns else 0.0
            sp06 = float(sub_day["speed_0_6"].sum()) if "speed_0_6" in sub_day.columns else 0.0
            dc = max(0.0, dt - sp06)
            
            mp25 = float(sub_day["mp_25_35"].sum()) if "mp_25_35" in sub_day.columns else 0.0
            mp35 = float(sub_day["mp_35_50"].sum()) if "mp_35_50" in sub_day.columns else 0.0
            mp50 = float(sub_day["mp_50_100"].sum()) if "mp_50_100" in sub_day.columns else 0.0
            hml = mp25 + mp35 + mp50
            vhml = mp50

            sp18 = float(sub_day["speed_18_20"].sum()) if "speed_18_20" in sub_day.columns else 0.0
            sp20 = float(sub_day["speed_20_25"].sum()) if "speed_20_25" in sub_day.columns else 0.0
            sp25 = float(sub_day["speed_25_72"].sum()) if "speed_25_72" in sub_day.columns else 0.0
            hsr = (sp18 + sp20 + sp25) if p_dept == "Avanti" else (sp20 + sp25)

            vmax = float(sub_day["v_max"].max()) if "v_max" in sub_day.columns else 0.0
            
            teams = sorted(sub_day["team_name"].dropna().unique().tolist())
            team_disp = ", ".join(teams) if teams else "GPS"

            sess_names = sorted(sub_day["session_name"].dropna().unique().tolist())
            sess_disp = ", ".join(sess_names) if sess_names else "Seduta"

            # Check se la sessione GPS è una partita
            if any(k in sess_disp.lower() for k in ["partita", "match", "vs", "italia", "gara"]):
                has_match = True
        else:
            dt = dur = dc = hml = vhml = hsr = vmax = 0.0
            team_disp = "-"
            sess_disp = "Riposo / Off"

        # Minuti gara e match info
        match_min = 0.0
        match_info = ""
        if has_match:
            if not sub_ov_day.empty:
                match_min = float(sub_ov_day.iloc[0].get("Min") or 0.0)
                opp = str(sub_ov_day.iloc[0].get("opponent") or "").strip()
                match_info = f"vs {opp}" if opp else "Partita Ufficiale"
            else:
                match_min = min(80.0, dur) if dur > 0 else 80.0
                match_info = "Partita"

        daily_rows.append({
            "date": day_str,
            "day_label": day_label,
            "week_code": w_code,
            "week_color": w_color,
            "week_ord": w_ord,
            "team": team_disp,
            "session_name": sess_disp,
            "has_gps": has_gps,
            "is_match": has_match,
            "match_info": match_info,
            "match_min": match_min,
            "DT": dt,
            "DC": dc,
            "Hml": hml,
            "VHml": vhml,
            "HSR": hsr,
            "Vmax": vmax,
            "Duration": dur,
        })
        current_day += pd.Timedelta(days=1)

    df_21 = pd.DataFrame(daily_rows)

    # Calcolo KPI per le 3 Settimane
    week_stats = {}
    for w_code in ["Week -2", "Week -1", "Week 0 (Attuale)"]:
        w_sub = df_21[df_21["week_code"] == w_code]
        week_stats[w_code] = {
            "DT": w_sub["DT"].sum(),
            "DC": w_sub["DC"].sum(),
            "Hml": w_sub["Hml"].sum(),
            "VHml": w_sub["VHml"].sum(),
            "HSR": w_sub["HSR"].sum(),
            "Vmax": w_sub["Vmax"].max(),
            "Sessions": int((w_sub["has_gps"] == True).sum()),
            "Match_Min": w_sub["match_min"].sum(),
            "Matches": int((w_sub["is_match"] == True).sum()),
        }

    # 3 Summary Cards
    col_k1, col_k2, col_k3 = st.columns(3)
    
    st2 = week_stats["Week -2"]
    st1 = week_stats["Week -1"]
    st0 = week_stats["Week 0 (Attuale)"]

    # Deltas
    dt_delta_1 = ((st1["DT"] - st2["DT"]) / st2["DT"] * 100.0) if st2["DT"] > 0 else 0.0
    hml_delta_1 = ((st1["Hml"] - st2["Hml"]) / st2["Hml"] * 100.0) if st2["Hml"] > 0 else 0.0

    dt_delta_0 = ((st0["DT"] - st1["DT"]) / st1["DT"] * 100.0) if st1["DT"] > 0 else 0.0
    hml_delta_0 = ((st0["Hml"] - st1["Hml"]) / st1["Hml"] * 100.0) if st1["Hml"] > 0 else 0.0

    with col_k1:
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #93C5FD; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.75rem; font-weight:800; color:#0369A1; text-transform:uppercase; letter-spacing:0.06em;">WEEK -2 (DUE SETT. FA)</span>
                    <span style="background:#E0F2FE; color:#0369A1; font-size:0.68rem; font-weight:800; padding:2px 7px; border-radius:4px;">{st2['Sessions']} Sedute</span>
                </div>
                <div style="font-size:1.55rem; font-weight:800; color:#0F172A; line-height:1.1;">{int(st2['DT']):,} m</div>
                <div style="font-size:0.75rem; color:#64748B; margin-bottom:10px;">Distanza Totale Settimanale</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.80rem; border-top:1px solid #F1F5F9; padding-top:8px;">
                    <div><span style="color:#64748B;">Hml &gt;25W:</span> <b style="color:#D97706;">{int(st2['Hml']):,} m</b></div>
                    <div><span style="color:#64748B;">HSR:</span> <b style="color:#0F172A;">{int(st2['HSR']):,} m</b></div>
                    <div><span style="color:#64748B;">Vmax:</span> <b style="color:#0F172A;">{st2['Vmax']:.1f} km/h</b></div>
                    <div><span style="color:#64748B;">Minuti Match:</span> <b style="color:#0284C7;">{int(st2['Match_Min'])}'</b></div>
                </div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    with col_k2:
        dt_sign_1 = "+" if dt_delta_1 >= 0 else ""
        delta_color_1 = "#16A34A" if abs(dt_delta_1) <= 15 else ("#D97706" if dt_delta_1 > 0 else "#DC2626")
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #CBD5E1; border-top:5px solid #6366F1; border-radius:12px; padding:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.75rem; font-weight:800; color:#4338CA; text-transform:uppercase; letter-spacing:0.06em;">WEEK -1 (SETTIMANA SCORSA)</span>
                    <span style="background:#EEF2FF; color:#4338CA; font-size:0.68rem; font-weight:800; padding:2px 7px; border-radius:4px;">{st1['Sessions']} Sedute</span>
                </div>
                <div style="display:flex; align-items:baseline; gap:8px;">
                    <div style="font-size:1.55rem; font-weight:800; color:#0F172A; line-height:1.1;">{int(st1['DT']):,} m</div>
                    <span style="font-size:0.75rem; font-weight:800; color:{delta_color_1};">{dt_sign_1}{dt_delta_1:.1f}% vs W-2</span>
                </div>
                <div style="font-size:0.75rem; color:#64748B; margin-bottom:10px;">Distanza Totale Settimanale</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.80rem; border-top:1px solid #F1F5F9; padding-top:8px;">
                    <div><span style="color:#64748B;">Hml &gt;25W:</span> <b style="color:#D97706;">{int(st1['Hml']):,} m</b></div>
                    <div><span style="color:#64748B;">HSR:</span> <b style="color:#0F172A;">{int(st1['HSR']):,} m</b></div>
                    <div><span style="color:#64748B;">Vmax:</span> <b style="color:#0F172A;">{st1['Vmax']:.1f} km/h</b></div>
                    <div><span style="color:#64748B;">Minuti Match:</span> <b style="color:#0284C7;">{int(st1['Match_Min'])}'</b></div>
                </div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    with col_k3:
        dt_sign_0 = "+" if dt_delta_0 >= 0 else ""
        delta_color_0 = "#16A34A" if abs(dt_delta_0) <= 15 else ("#D97706" if dt_delta_0 > 0 else "#DC2626")
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:2px solid #0284C7; border-top:5px solid #0284C7; border-radius:12px; padding:14px; box-shadow:0 4px 12px rgba(2,132,199,0.15);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:0.75rem; font-weight:800; color:#0369A1; text-transform:uppercase; letter-spacing:0.06em;">WEEK 0 (SETTIMANA SELEZIONATA)</span>
                    <span style="background:#E0F2FE; color:#0369A1; font-size:0.68rem; font-weight:800; padding:2px 7px; border-radius:4px;">{st0['Sessions']} Sedute</span>
                </div>
                <div style="display:flex; align-items:baseline; gap:8px;">
                    <div style="font-size:1.55rem; font-weight:800; color:#0F172A; line-height:1.1;">{int(st0['DT']):,} m</div>
                    <span style="font-size:0.75rem; font-weight:800; color:{delta_color_0};">{dt_sign_0}{dt_delta_0:.1f}% vs W-1</span>
                </div>
                <div style="font-size:0.75rem; color:#64748B; margin-bottom:10px;">Distanza Totale Settimanale</div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.80rem; border-top:1px solid #F1F5F9; padding-top:8px;">
                    <div><span style="color:#64748B;">Hml &gt;25W:</span> <b style="color:#D97706;">{int(st0['Hml']):,} m</b></div>
                    <div><span style="color:#64748B;">HSR:</span> <b style="color:#0F172A;">{int(st0['HSR']):,} m</b></div>
                    <div><span style="color:#64748B;">Vmax:</span> <b style="color:#0F172A;">{st0['Vmax']:.1f} km/h</b></div>
                    <div><span style="color:#64748B;">Minuti Match:</span> <b style="color:#0284C7;">{int(st0['Match_Min'])}'</b></div>
                </div>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # GRAFICO PLOTLY DAY-BY-DAY (21 GIORNI)
    # --------------------------------------------------------------------------
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    # Colori barre per settimana
    bar_colors = []
    for _, r in df_21.iterrows():
        if r["is_match"]:
            bar_colors.append("#EF4444")  # Rosso per giorno match
        elif r["week_code"] == "Week -2":
            bar_colors.append("#93C5FD")
        elif r["week_code"] == "Week -1":
            bar_colors.append("#6366F1")
        else:
            bar_colors.append("#0284C7")

    fig.add_trace(
        go.Bar(
            x=df_21["day_label"],
            y=df_21["DT"],
            name="Distanza Totale (m)",
            marker_color=bar_colors,
            opacity=0.88,
            hovertemplate="<b>%{x}</b><br>Distanza: %{y:,.0f} m<extra></extra>",
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            x=df_21["day_label"],
            y=df_21["Hml"],
            name="High Metabolic Load (Hml >25.5W)",
            line=dict(color="#F59E0B", width=2.5),
            marker=dict(size=6, color="#D97706"),
            mode="lines+markers",
            hovertemplate="<b>%{x}</b><br>Hml: %{y:,.0f} m<extra></extra>",
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(
            text=f"<b>Progressione Carichi Giornalieri (21 Giorni) • {sel_player}</b>",
            font=dict(size=14, color="#0F172A"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=50, b=50),
        height=320,
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        hovermode="x unified",
    )
    fig.update_xaxes(tickangle=-45, gridcolor="#E2E8F0")
    fig.update_yaxes(title_text="Distanza Totale (m)", gridcolor="#E2E8F0", secondary_y=False)
    fig.update_yaxes(title_text="Hml (m)", gridcolor="rgba(0,0,0,0)", secondary_y=True)

    st.plotly_chart(fig, use_container_width=True)

    # --------------------------------------------------------------------------
    # ESPORTAZIONE PDF UFFICIALE FIR (ACTION BAR)
    # --------------------------------------------------------------------------
    render_action_bar(
        meta_items=[
            ("Atleta", f"{sel_player} ({p_meta.get('role', '-')})"),
            ("Club", p_meta.get("club", "-")),
            ("Periodo 3 Settimane", f"{w2_mon_str} → {w0_sun_str}"),
            ("Totale 21 Giorni", f"{len(df_21)} registrazioni GPS"),
        ],
        pdf_options={
            "Dossier Completo Atleta (Passaporto GPS 21gg + Day-by-Day + Grafico)": "completo_3w",
        },
        pdf_key=f"bar_3w_{sel_player}_{ref_mon_str}",
        generate_fn=lambda sub_code: crea_pdf_singolo_atleta_3w(
            player_name=sel_player,
            p_meta=p_meta,
            df_21=df_21,
            week_stats=week_stats,
            fig=fig,
            ref_week_lbl=sel_week_lbl,
        ),
        filename_fn=lambda sub_code: f"FIR_Report_3W_{sel_player.replace(' ', '_')}_{w0_sun_str}.pdf",
    )

    # --------------------------------------------------------------------------
    # TABELLA DETTAGLIATA DAY-BY-DAY (21 GIORNI)
    # --------------------------------------------------------------------------
    st.markdown("#### Tabella Carichi Giornalieri Dettagliata (21 Giorni)")

    table_rows = ""
    current_w = None
    w_sub_dt = w_sub_hml = w_sub_hsr = w_sub_min = 0

    for idx, r in df_21.iterrows():
        # Riga separatore e subtotale settimana
        if current_w is not None and r["week_code"] != current_w:
            table_rows += f"""
            <tr style="background:#E2E8F0; font-weight:800; border-top:2px solid #94A3B8; border-bottom:2px solid #94A3B8;">
                <td colspan="4" style="padding:6px 10px; text-align:left; color:#0F172A; text-transform:uppercase; font-size:0.75rem;">SUBTOTALE {current_w}</td>
                <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">{int(w_sub_dt):,}</td>
                <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
                <td style="padding:6px 6px; text-align:center; color:#D97706; font-size:0.76rem;">{int(w_sub_hml):,}</td>
                <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
                <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">{int(w_sub_hsr):,}</td>
                <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
                <td style="padding:6px 6px; text-align:center; color:#0284C7; font-size:0.76rem;">{int(w_sub_min)}'</td>
            </tr>
            """.replace(",", ".")
            w_sub_dt = w_sub_hml = w_sub_hsr = w_sub_min = 0

        current_w = r["week_code"]
        w_sub_dt += r["DT"]
        w_sub_hml += r["Hml"]
        w_sub_hsr += r["HSR"]
        w_sub_min += r["match_min"]

        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"
        if r["is_match"]:
            row_bg = "#FEF3C7"  # Evidenzia giorno match

        # Badge Squadra
        if "Nazionale" in r["team"] or "FIR" in r["team"]:
            team_badge = '<span style="background:#0284C7; color:#FFFFFF; font-size:0.65rem; font-weight:800; padding:1px 6px; border-radius:4px;">FIR</span>'
        elif "Benetton" in r["team"]:
            team_badge = '<span style="background:#059669; color:#FFFFFF; font-size:0.65rem; font-weight:800; padding:1px 6px; border-radius:4px;">BENETTON</span>'
        elif "Zebre" in r["team"]:
            team_badge = '<span style="background:#D97706; color:#FFFFFF; font-size:0.65rem; font-weight:800; padding:1px 6px; border-radius:4px;">ZEBRE</span>'
        else:
            team_badge = f'<span style="color:#64748B; font-size:0.68rem;">{r["team"]}</span>'

        # Badge Seduta / Match
        if r["is_match"]:
            sess_badge = f'<span style="background:#DC2626; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:2px 6px; border-radius:4px;">🏉 MATCH {r["match_info"]}</span>'
        else:
            sess_badge = f'<span style="font-size:0.74rem; color:#0F172A;">{r["session_name"]}</span>'

        match_min_disp = f"<b>{int(r['match_min'])}'</b>" if r["match_min"] > 0 else "-"
        vmax_disp = f"{r['Vmax']:.1f}" if r["Vmax"] > 0 else "-"

        table_rows += f"""
        <tr style="background:{row_bg}; border-bottom:1px solid #E2E8F0;">
            <td style="padding:5px 8px; font-weight:700; font-size:0.72rem; color:{r['week_color']};">{r['week_code']}</td>
            <td style="padding:5px 10px; font-weight:600; font-size:0.74rem; color:#0F172A; white-space:nowrap;">{r['day_label']}</td>
            <td style="padding:5px 8px; text-align:center;">{team_badge}</td>
            <td style="padding:5px 8px;">{sess_badge}</td>
            <td style="padding:5px 6px; text-align:center; font-weight:700; font-size:0.75rem; color:#0F172A;">{int(r['DT']):,}</td>
            <td style="padding:5px 6px; text-align:center; font-size:0.74rem; color:#475569;">{int(r['DC']):,}</td>
            <td style="padding:5px 6px; text-align:center; font-weight:700; font-size:0.75rem; color:#D97706; background:rgba(245,158,11,0.06);">{int(r['Hml']):,}</td>
            <td style="padding:5px 6px; text-align:center; font-size:0.74rem; color:#475569;">{int(r['VHml']):,}</td>
            <td style="padding:5px 6px; text-align:center; font-weight:700; font-size:0.75rem; color:#0F172A;">{int(r['HSR']):,}</td>
            <td style="padding:5px 6px; text-align:center; font-weight:700; font-size:0.74rem; color:#0F172A;">{vmax_disp}</td>
            <td style="padding:5px 6px; text-align:center; font-size:0.75rem; color:#0284C7;">{match_min_disp}</td>
        </tr>
        """.replace(",", ".")

    # Subtotale ultima settimana
    table_rows += f"""
    <tr style="background:#E2E8F0; font-weight:800; border-top:2px solid #94A3B8; border-bottom:2px solid #94A3B8;">
        <td colspan="4" style="padding:6px 10px; text-align:left; color:#0F172A; text-transform:uppercase; font-size:0.75rem;">SUBTOTALE {current_w}</td>
        <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">{int(w_sub_dt):,}</td>
        <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
        <td style="padding:6px 6px; text-align:center; color:#D97706; font-size:0.76rem;">{int(w_sub_hml):,}</td>
        <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
        <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">{int(w_sub_hsr):,}</td>
        <td style="padding:6px 6px; text-align:center; color:#0F172A; font-size:0.76rem;">-</td>
        <td style="padding:6px 6px; text-align:center; color:#0284C7; font-size:0.76rem;">{int(w_sub_min)}'</td>
    </tr>
    """.replace(",", ".")

    # Totale Complessivo 21 Giorni
    tot_dt = df_21["DT"].sum()
    tot_hml = df_21["Hml"].sum()
    tot_hsr = df_21["HSR"].sum()
    tot_min = df_21["match_min"].sum()
    table_rows += f"""
    <tr style="background:#002B49; color:#FFFFFF; font-weight:800; border-top:3px solid #D4AF37;">
        <td colspan="4" style="padding:8px 10px; text-align:left; color:#D4AF37; font-size:0.80rem; letter-spacing:0.04em;">TOTALE COMPLESSIVO 3 SETTIMANE (21 GIORNI)</td>
        <td style="padding:8px 6px; text-align:center; color:#FFFFFF; font-size:0.82rem;">{int(tot_dt):,} m</td>
        <td style="padding:8px 6px; text-align:center; color:#CBD5E1; font-size:0.76rem;">-</td>
        <td style="padding:8px 6px; text-align:center; color:#FBBF24; font-size:0.82rem;">{int(tot_hml):,} m</td>
        <td style="padding:8px 6px; text-align:center; color:#CBD5E1; font-size:0.76rem;">-</td>
        <td style="padding:8px 6px; text-align:center; color:#FFFFFF; font-size:0.82rem;">{int(tot_hsr):,} m</td>
        <td style="padding:8px 6px; text-align:center; color:#CBD5E1; font-size:0.76rem;">-</td>
        <td style="padding:8px 6px; text-align:center; color:#38BDF8; font-size:0.82rem;">{int(tot_min)}' min</td>
    </tr>
    """.replace(",", ".")

    full_table_html = f"""
    <div style="overflow-x:auto; border:2px solid #CBD5E1; border-radius:12px; background:#FFFFFF; box-shadow:0 3px 10px rgba(15,23,42,0.06); margin-bottom:14px;">
        <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#002B49; color:#FFFFFF; font-size:0.70rem; font-weight:800; letter-spacing:0.04em;">
                    <th style="padding:8px 8px; text-align:left; width:95px;">SETTIMANA</th>
                    <th style="padding:8px 10px; text-align:left;">GIORNO & DATA</th>
                    <th style="padding:8px 8px; text-align:center; width:90px;">SQUADRA</th>
                    <th style="padding:8px 8px; text-align:left;">SEDUTA / GARA</th>
                    <th style="padding:8px 6px; text-align:center; width:75px;">DT (m)</th>
                    <th style="padding:8px 6px; text-align:center; width:65px;">DC (m)</th>
                    <th style="padding:8px 6px; text-align:center; width:75px; color:#FBBF24;">Hml (&gt;25W)</th>
                    <th style="padding:8px 6px; text-align:center; width:65px;">VHml (&gt;50W)</th>
                    <th style="padding:8px 6px; text-align:center; width:70px;">HSR (m)</th>
                    <th style="padding:8px 6px; text-align:center; width:65px;">Vmax (km/h)</th>
                    <th style="padding:8px 6px; text-align:center; width:75px; color:#38BDF8;">MIN GARA</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </div>
    """
    _clean_and_render_html(full_table_html)

    # Esportazione CSV
    csv_bytes = df_21.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"📥 Scarica Report 3 Settimane CSV ({sel_player})",
        data=csv_bytes,
        file_name=f"FIR_Analisi_3_Settimane_{sel_player.replace(' ', '_')}_{ref_mon_str}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    if not p_ov_all.empty:
        st.markdown("#### 🏉 Ultime Partite Ufficiali Disputate (Archivio Oval Match — Nazionale & Club)")
        ov_show = p_ov_all.copy()
        if "match_date" in ov_show.columns:
            ov_show = ov_show.sort_values("match_date", ascending=False)
        cols_ov = [c for c in ["match_date", "teamName", "opponent", "JERSEY", "Min", "rseas"] if c in ov_show.columns]
        if cols_ov:
            st.dataframe(
                ov_show[cols_ov].head(15).rename(
                    columns={
                        "match_date": "Data Gara",
                        "teamName": "Squadra",
                        "opponent": "Avversario",
                        "JERSEY": "Maglia N°",
                        "Min": "Minuti Giocati",
                        "rseas": "Stagione",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

