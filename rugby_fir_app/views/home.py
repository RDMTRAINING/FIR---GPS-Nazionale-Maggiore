import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import render_page_header, render_tab_navigation, render_navigation_cards, render_action_bar, JERSEY_POSITIONS_1_23, ROLE_TO_DEPT
import utils
import global_state
from pdf_generator import crea_pdf_cruscotto_fir, crea_pdf_schieramento_campo, slugify_name


ROLE_ORDER_MAP = {
    "Pilone": 1,
    "Tallonatore": 2,
    "Seconda Linea": 3,
    "Terza Linea": 4,
    "Mediano di Mischia": 5,
    "Apertura": 6,
    "Centro": 7,
    "Ala": 8,
    "Estremo": 8,
}


def _get_role_sort_rank(role_str: str) -> int:
    r = str(role_str or "").lower().strip()
    if "pilon" in r:
        return 1
    if "tallon" in r:
        return 2
    if "second" in r or r in ("2l", "2 l"):
        return 3
    if "terz" in r or "flanker" in r or "numero otto" in r or r in ("3l", "3 l"):
        return 4
    if "mischia" in r or r == "9":
        return 5
    if "apertura" in r or r == "10":
        return 6
    if "centr" in r or r in ("12", "13", "12-13"):
        return 7
    if "ala" in r or "estrem" in r or r in ("11", "14", "15"):
        return 8
    return 9


def _normalize_macro_role(role_str: str) -> str:
    """Normalizza qualsiasi variante specifica di ruolo (es. Primo Centro, Pilone Sinistro, Ala Destra) nei macro-ruoli ufficiali FIR."""
    r = str(role_str or "").lower().strip()
    if "pilon" in r:
        return "Pilone"
    if "tallon" in r:
        return "Tallonatore"
    if "second" in r or r in ("2l", "2 l"):
        return "Seconda Linea"
    if "terz" in r or "flanker" in r or "otto" in r or r in ("3l", "3 l"):
        return "Terza Linea"
    if "mischia" in r or r == "9":
        return "Mediano di Mischia"
    if "apertura" in r or r == "10":
        return "Apertura"
    if "centr" in r or r in ("12", "13", "12-13"):
        return "Centro"
    if "ala" in r or "estrem" in r or r in ("11", "14", "15"):
        return "Ala"
    return str(role_str).strip()


SESSION_TYPE_BASELINES = {
    "Volume": {
        "Avanti": {"distance_m": 4850.0, "m_per_min": 64.0, "run_dist": 2450.0, "hml": 580.0, "hsr": 250.0, "time": 75.0, "max_avg_rd": 3250, "max_avg_hml": 740, "max_avg_hsr": 360},
        "TreQuarti": {"distance_m": 5400.0, "m_per_min": 71.0, "run_dist": 2850.0, "hml": 790.0, "hsr": 340.0, "time": 75.0, "max_avg_rd": 3450, "max_avg_hml": 920, "max_avg_hsr": 460},
    },
    "Velocità": {
        "Avanti": {"distance_m": 4100.0, "m_per_min": 61.2, "run_dist": 2066.0, "hml": 496.0, "hsr": 265.0, "time": 67.4, "max_avg_rd": 3088, "max_avg_hml": 694, "max_avg_hsr": 388},
        "TreQuarti": {"distance_m": 4738.0, "m_per_min": 70.2, "run_dist": 2342.0, "hml": 699.0, "hsr": 310.0, "time": 67.4, "max_avg_rd": 3084, "max_avg_hml": 847, "max_avg_hsr": 424},
    },
    "Rugby": {
        "Avanti": {"distance_m": 3900.0, "m_per_min": 58.0, "run_dist": 1900.0, "hml": 430.0, "hsr": 180.0, "time": 67.0, "max_avg_rd": 2700, "max_avg_hml": 600, "max_avg_hsr": 290},
        "TreQuarti": {"distance_m": 4400.0, "m_per_min": 65.0, "run_dist": 2200.0, "hml": 610.0, "hsr": 260.0, "time": 67.0, "max_avg_rd": 2950, "max_avg_hml": 780, "max_avg_hsr": 380},
    },
    "Team run": {
        "Avanti": {"distance_m": 2200.0, "m_per_min": 48.0, "run_dist": 950.0, "hml": 210.0, "hsr": 70.0, "time": 45.0, "max_avg_rd": 1500, "max_avg_hml": 320, "max_avg_hsr": 130},
        "TreQuarti": {"distance_m": 2600.0, "m_per_min": 55.0, "run_dist": 1200.0, "hml": 310.0, "hsr": 120.0, "time": 45.0, "max_avg_rd": 1800, "max_avg_hml": 420, "max_avg_hsr": 200},
    },
    "Clarity": {
        "Avanti": {"distance_m": 2600.0, "m_per_min": 48.0, "run_dist": 1150.0, "hml": 240.0, "hsr": 90.0, "time": 54.0, "max_avg_rd": 1800, "max_avg_hml": 380, "max_avg_hsr": 160},
        "TreQuarti": {"distance_m": 2950.0, "m_per_min": 54.0, "run_dist": 1350.0, "hml": 340.0, "hsr": 150.0, "time": 54.0, "max_avg_rd": 2050, "max_avg_hml": 490, "max_avg_hsr": 240},
    },
    "Reparto": {
        "Avanti": {"distance_m": 1800.0, "m_per_min": 50.0, "run_dist": 800.0, "hml": 220.0, "hsr": 80.0, "time": 35.0, "max_avg_rd": 1400, "max_avg_hml": 350, "max_avg_hsr": 140},
        "TreQuarti": {"distance_m": 2200.0, "m_per_min": 60.0, "run_dist": 1100.0, "hml": 330.0, "hsr": 150.0, "time": 35.0, "max_avg_rd": 1700, "max_avg_hml": 450, "max_avg_hsr": 220},
    },
    "Extra": {
        "Avanti": {"distance_m": 1200.0, "m_per_min": 55.0, "run_dist": 600.0, "hml": 180.0, "hsr": 90.0, "time": 22.0, "max_avg_rd": 1000, "max_avg_hml": 280, "max_avg_hsr": 150},
        "TreQuarti": {"distance_m": 1500.0, "m_per_min": 65.0, "run_dist": 850.0, "hml": 270.0, "hsr": 160.0, "time": 22.0, "max_avg_rd": 1300, "max_avg_hml": 380, "max_avg_hsr": 230},
    },
    "Lavoro fisico": {
        "Avanti": {"distance_m": 1500.0, "m_per_min": 45.0, "run_dist": 500.0, "hml": 150.0, "hsr": 50.0, "time": 40.0, "max_avg_rd": 1100, "max_avg_hml": 240, "max_avg_hsr": 100},
        "TreQuarti": {"distance_m": 1700.0, "m_per_min": 50.0, "run_dist": 650.0, "hml": 200.0, "hsr": 80.0, "time": 40.0, "max_avg_rd": 1300, "max_avg_hml": 300, "max_avg_hsr": 140},
    },
    "Match": {
        "Avanti": {"distance_m": 5800.0, "m_per_min": 72.5, "run_dist": 3100.0, "hml": 820.0, "hsr": 390.0, "time": 80.0, "max_avg_rd": 4100, "max_avg_hml": 1100, "max_avg_hsr": 550},
        "TreQuarti": {"distance_m": 6800.0, "m_per_min": 85.0, "run_dist": 3900.0, "hml": 1150.0, "hsr": 520.0, "time": 80.0, "max_avg_rd": 4900, "max_avg_hml": 1450, "max_avg_hsr": 720},
    },
    "RTP": {
        "Avanti": {"distance_m": 2500.0, "m_per_min": 50.0, "run_dist": 1100.0, "hml": 220.0, "hsr": 80.0, "time": 50.0, "max_avg_rd": 1600, "max_avg_hml": 350, "max_avg_hsr": 140},
        "TreQuarti": {"distance_m": 2800.0, "m_per_min": 56.0, "run_dist": 1300.0, "hml": 290.0, "hsr": 120.0, "time": 50.0, "max_avg_rd": 1900, "max_avg_hml": 420, "max_avg_hsr": 190},
    },
}
SESSION_TYPE_BASELINES["Collettivo"] = SESSION_TYPE_BASELINES["Rugby"]


def _detect_session_archetype(session_name: str) -> str:
    return utils.detect_fir_session_type(session_name)


def _prepare_session_camp_dataframe(
    sub_gps: pd.DataFrame,
    camp_players: pd.DataFrame,
    players_df: pd.DataFrame,
    status_overrides: dict,
    sum_m_per_min: bool = False,
) -> pd.DataFrame:
    """
    Allinea i dati GPS (di una singola seduta, di una giornata intera o di una settimana intera)
    con i giocatori convocati nel Raduno selezionato:
    - Mantiene l'ordine ufficiale del Raduno (prima Avanti, poi TreQuarti)
    - Se sum_m_per_min=True (Report Giornata / Settimana con più sedute), somma i valori per seduta come nei report FIR.
    """
    gps = sub_gps.copy()
    num_cols = [
        "duration", "distance_m", "m_per_min", "speed_0_6", "speed_6_15", "speed_15_18",
        "speed_18_20", "speed_20_25", "speed_25_72", "mp_25_35", "mp_35_50", "mp_50_100",
        "ai_25_40", "ai_40_50", "ai_50_100", "v_max", "v_max_pct", "profile_max_vel",
    ]
    for c in num_cols:
        if c in gps.columns:
            gps[c] = pd.to_numeric(gps[c], errors="coerce").fillna(0.0)
        else:
            gps[c] = 0.0

    gps["run_dist_calc"] = np.maximum(0.0, gps["distance_m"] - gps["speed_0_6"])
    gps["hml_25"] = gps["mp_25_35"] + gps["mp_35_50"] + gps["mp_50_100"]
    gps["hml_40"] = gps["mp_35_50"] + gps["mp_50_100"]
    gps["vhml_50"] = gps["mp_50_100"]
    gps["power_events"] = gps["ai_25_40"] + gps["ai_40_50"] + gps["ai_50_100"]
    gps["hsr_18"] = gps["speed_18_20"] + gps["speed_20_25"] + gps["speed_25_72"]
    gps["hsr_20"] = gps["speed_20_25"] + gps["speed_25_72"]
    gps["vhsr_25"] = gps["speed_25_72"]

    if not gps.empty:
        mmin_agg_fn = "sum" if sum_m_per_min else "mean"
        gps_agg = (
            gps.groupby("player_name", as_index=False)
            .agg(
                role_gps=("role", "first"),
                duration=("duration", lambda s: np.round(s).sum()),
                distance_m=("distance_m", lambda s: np.round(s).sum()),
                m_per_min=("m_per_min", lambda s: np.round(s).sum() if sum_m_per_min else np.round(s.mean())),
                run_dist=("run_dist_calc", lambda s: np.round(s).sum()),
                hml_25=("hml_25", lambda s: np.round(s).sum()),
                hml_40=("hml_40", lambda s: np.round(s).sum()),
                vhml_50=("vhml_50", lambda s: np.round(s).sum()),
                power_events=("power_events", lambda s: np.round(s).sum()),
                hsr_18=("hsr_18", lambda s: np.round(s).sum()),
                hsr_20=("hsr_20", lambda s: np.round(s).sum()),
                vhsr_25=("vhsr_25", lambda s: np.round(s).sum()),
                v_max=("v_max", "max"),
                v_max_pct=("v_max_pct", "max"),
            )
        )
    else:
        gps_agg = pd.DataFrame(columns=[
            "player_name", "role_gps", "duration", "distance_m", "m_per_min", "run_dist",
            "hml_25", "hml_40", "vhml_50", "power_events", "hsr_18", "hsr_20", "vhsr_25", "v_max", "v_max_pct"
        ])

    roster_map = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip()
            if nm:
                roster_map[nm.upper()] = {
                    "name_display": nm,
                    "role": str(pr.get("role") or "Pilone"),
                    "department": str(pr.get("department") or ROLE_TO_DEPT.get(str(pr.get("role") or ""), "Avanti")),
                    "v_max_roster": float(pr["v_max"]) if pd.notna(pr.get("v_max")) and float(pr.get("v_max") or 0) > 0 else 30.0,
                    "hml_avg_tot": float(pr["hml_avg_tot"]) if pd.notna(pr.get("hml_avg_tot")) else np.nan,
                    "hsr_avg_tot": float(pr["hsr_avg_tot"]) if pd.notna(pr.get("hsr_avg_tot")) else np.nan,
                    "hml_avg_fir": float(pr["hml_avg_fir"]) if pd.notna(pr.get("hml_avg_fir")) else np.nan,
                    "hsr_avg_fir": float(pr["hsr_avg_fir"]) if pd.notna(pr.get("hsr_avg_fir")) else np.nan,
                    "hml_avg_excel": float(pr["hml_avg_excel"]) if pd.notna(pr.get("hml_avg_excel")) else np.nan,
                    "hsr_avg_excel": float(pr["hsr_avg_excel"]) if pd.notna(pr.get("hsr_avg_excel")) else np.nan,
                }

    gps_map = {}
    for _, gr in gps_agg.iterrows():
        p_nm = str(gr["player_name"]).strip()
        gps_map[p_nm.upper()] = gr.to_dict()

    ordered_entries = []
    seen_up = set()

    if not camp_players.empty:
        for _, cpr in camp_players.iterrows():
            c_name = str(cpr.get("player_name") or "").strip()
            if not c_name or c_name.upper() in seen_up:
                continue
            seen_up.add(c_name.upper())
            r_role = str(cpr.get("role") or roster_map.get(c_name.upper(), {}).get("role", "Pilone"))
            r_dept = str(cpr.get("department") or roster_map.get(c_name.upper(), {}).get("department", "Avanti"))
            ordered_entries.append({
                "player_name": c_name,
                "role": r_role,
                "role_rank": _get_role_sort_rank(r_role),
                "department": r_dept,
                "in_camp": True,
            })
    else:
        for _, gr in gps_agg.iterrows():
            g_name = str(gr["player_name"]).strip()
            if g_name.upper() not in seen_up:
                seen_up.add(g_name.upper())
                r_info = roster_map.get(g_name.upper(), {})
                r_role = str(r_info.get("role") or gr.get("role_gps") or "Pilone")
                r_dept = str(r_info.get("department") or ROLE_TO_DEPT.get(r_role, "Avanti"))
                ordered_entries.append({
                    "player_name": g_name,
                    "role": r_role,
                    "role_rank": _get_role_sort_rank(r_role),
                    "department": r_dept,
                    "in_camp": False,
                })

    # Ordina tassativamente per Ruolo secondo specifica FIR:
    # 1. Piloni -> 2. Tallonatori -> 3. Seconde Linee -> 4. Terze Linee -> 5. Mediani di Mischia -> 6. Aperture -> 7. Centri -> 8. Ali\Estremo
    ordered_entries.sort(key=lambda x: (x["role_rank"], x["player_name"]))

    rows = []
    for item in ordered_entries:
        p_name = item["player_name"]
        p_up = p_name.upper()
        g_row = gps_map.get(p_up)
        r_info = roster_map.get(p_up, {})
        role_clean = item["role"]
        role_clean_group = "Ala" if str(role_clean).strip().lower() in ("estremo", "ala-estremo") else role_clean
        dept_clean = "Avanti" if item["role_rank"] <= 4 else "TreQuarti"

        if g_row is not None and float(g_row.get("duration", 0)) > 0:
            dur = int(round(float(g_row["duration"])))
            dist = int(round(float(g_row["distance_m"])))
            m_min_raw = float(g_row["m_per_min"]) if float(g_row["m_per_min"]) > 0 else (dist / dur if dur > 0 else 0.0)
            m_min = int(round(m_min_raw))
            r_dist = int(round(float(g_row["run_dist"])))
            h25 = int(round(float(g_row["hml_25"])))
            h40 = int(round(float(g_row["hml_40"])))
            vh50 = int(round(float(g_row["vhml_50"])))
            pev = int(round(float(g_row["power_events"])))
            hsr18 = int(round(float(g_row["hsr_18"])))
            hsr20 = int(round(float(g_row["hsr_20"])))
            vhsr25 = int(round(float(g_row["vhsr_25"])))
            vmax = round(float(g_row["v_max"]), 1)
            vpct_raw = float(g_row.get("v_max_pct", 0.0))
            if vpct_raw <= 0 and vmax > 0:
                ref_vm = float(r_info.get("v_max_roster", 30.0))
                vpct_raw = (vmax / ref_vm) * 100.0 if ref_vm > 0 else 0.0
            vpct = int(round(vpct_raw))
            default_st = "Full"
        else:
            dur = dist = m_min = r_dist = h25 = h40 = vh50 = pev = hsr18 = hsr20 = vhsr25 = vpct = 0
            vmax = 0.0
            default_st = "Off Feet"

        st_label = status_overrides.get(p_name, default_st)
        rows.append({
            "player_name": p_name,
            "role": role_clean,
            "role_group": role_clean_group,
            "role_ord": _get_role_sort_rank(role_clean),
            "department": dept_clean,
            "dept_ord": 0 if dept_clean == "Avanti" else 1,
            "status": st_label,
            "has_gps": dur > 0,
            "Tempo": dur,
            "Distanza": dist,
            "m_min": m_min,
            "Run_Dist": r_dist,
            "Hml_25": h25,
            "Hml_40": h40,
            "VHml_50": vh50,
            "Power_Events": pev,
            "HSR_18": hsr18,
            "HSR_20": hsr20,
            "VHSR_25": vhsr25,
            "V_max": vmax,
            "V_max_pct": vpct,
            "hml_avg_tot": r_info.get("hml_avg_tot", np.nan),
            "hsr_avg_tot": r_info.get("hsr_avg_tot", np.nan),
            "hml_avg_fir": r_info.get("hml_avg_fir", np.nan),
            "hsr_avg_fir": r_info.get("hsr_avg_fir", np.nan),
            "hml_avg_excel": r_info.get("hml_avg_excel", np.nan),
            "hsr_avg_excel": r_info.get("hsr_avg_excel", np.nan),
        })

    out_df = pd.DataFrame(rows)
    if not out_df.empty and camp_players.empty:
        out_df = out_df.sort_values(by=["dept_ord", "role_ord", "player_name"]).reset_index(drop=True)
    return out_df


def _compute_role_and_dept_averages(df_sess: pd.DataFrame, keep_decimals: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Esclude categoricamente da TUTTE le medie (Ruolo e Reparto) chi ha svolto allenamento Modificato, RTP o Off Feet!
    excluded_statuses = {"MODIFICATO", "MODIFIED", "RTP", "OFF FEET", "NON ATTIVO"}
    active = df_sess[
        (df_sess["has_gps"] == True) &
        (~df_sess["status"].astype(str).str.strip().str.upper().isin(excluded_statuses))
    ].copy()
    metric_cols = ["Tempo", "Distanza", "m_min", "Run_Dist", "Hml_25", "Hml_40", "VHml_50", "Power_Events", "HSR_18", "HSR_20", "VHSR_25", "V_max", "V_max_pct"]
    int_only_cols = {"Tempo", "V_max_pct"}

    roles_list = [
        ("Pilone", "Avanti"),
        ("Tallonatore", "Avanti"),
        ("Seconda Linea", "Avanti"),
        ("Terza Linea", "Avanti"),
        ("Mediano di Mischia", "TreQuarti"),
        ("Apertura", "TreQuarti"),
        ("Centro", "TreQuarti"),
        ("Ala", "TreQuarti"),
    ]

    role_rows = []
    for r_name, r_dept in roles_list:
        sub_r = active[active["role_group"] == r_name]
        row_d = {"Label": r_name, "department": r_dept}
        for mc in metric_cols:
            if sub_r.empty:
                row_d[mc] = 0.0 if (keep_decimals and mc not in int_only_cols) else 0
            elif keep_decimals and mc not in int_only_cols:
                row_d[mc] = round(float(sub_r[mc].mean()), 1)
            else:
                row_d[mc] = int(round(sub_r[mc].mean()))
        role_rows.append(row_d)

    role_df = pd.DataFrame(role_rows)

    dept_rows = []
    for d_label, d_code in [("AVANTI", "Avanti"), ("TREQUARTI", "TreQuarti")]:
        sub_d_roles = role_df[(role_df["department"] == d_code) & (role_df["Tempo"] > 0)]
        row_dept = {"Label": d_label, "department": d_code}
        for mc in metric_cols:
            if sub_d_roles.empty:
                row_dept[mc] = 0.0 if (keep_decimals and mc not in int_only_cols) else 0
            elif keep_decimals and mc not in int_only_cols:
                row_dept[mc] = round(float(sub_d_roles[mc].mean()), 1)
            else:
                row_dept[mc] = int(round(sub_d_roles[mc].mean()))
        dept_rows.append(row_dept)

    return role_df, pd.DataFrame(dept_rows)


def _build_session_report_html(
    df_sess: pd.DataFrame,
    role_df: pd.DataFrame,
    dept_df: pd.DataFrame,
    header_title: str,
    header_sub: str,
    highlight_vmax90: bool = True,
    show_tempo_in_role_table: bool = True,
) -> tuple[str, str]:
    # Metriche numeriche per il ranking Top 5 (Verde) e Bottom 3 (Rosso) per reparto
    metric_keys = [
        "Tempo", "Distanza", "m_min", "Run_Dist", "Hml_25", "Hml_40",
        "VHml_50", "Power_Events", "HSR_18", "HSR_20", "VHSR_25", "V_max", "V_max_pct"
    ]
    top5_set = {k: set() for k in metric_keys}
    bot3_set = {k: set() for k in metric_keys}

    for dept_name in ["Avanti", "TreQuarti"]:
        dept_mask = df_sess["department"] == dept_name
        dept_sub = df_sess[dept_mask]
        for mk in metric_keys:
            s = pd.to_numeric(dept_sub[mk], errors="coerce").fillna(0)
            s_pos = s[s > 0]
            if len(s_pos) >= 1:
                n_top = min(5, len(s_pos))
                top_indices = set(s_pos.nlargest(n_top).index.tolist())
                top5_set[mk].update(top_indices)

                # 3 valori più bassi (>0) non sovrapposti alla Top 5
                if len(s_pos) >= 4:
                    n_bot = min(3, len(s_pos) - n_top if len(s_pos) < n_top + 3 else 3)
                    if n_bot > 0:
                        bot_indices = s_pos.nsmallest(n_bot).index.tolist()
                        for bi in bot_indices:
                            if bi not in top_indices:
                                bot3_set[mk].add(bi)

    rows_ind = ""
    prev_dept = None
    for idx, r in df_sess.iterrows():
        dept = r["department"]
        is_dept_switch = prev_dept is not None and dept != prev_dept
        prev_dept = dept
        top_b = "border-top: 2.5px solid #0284C7;" if is_dept_switch else ""
        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F0F9FF"

        st_val = str(r.get("status") or "Full").strip()
        status_tag = ""
        if st_val.upper() in ("MODIFICATO", "MODIFIED"):
            name_bg = "#FEF08A"  # Giallo per Modificato
            status_tag = " <span style='background:#CA8A04; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px; letter-spacing:0.04em;'>MODIFICATO</span>"
        elif st_val.upper() == "RTP":
            name_bg = "#BAE6FD"  # Celeste per RTP
            status_tag = " <span style='background:#0284C7; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px; letter-spacing:0.04em;'>RTP</span>"
        elif st_val.upper() in ("OFF FEET", "NON ATTIVO"):
            name_bg = "#FECACA"  # Rosso per Off Feet
            status_tag = " <span style='background:#DC2626; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px; letter-spacing:0.04em;'>OFF</span>"
        else:
            name_bg = row_bg

        def _cell_style(col_k: str, extra_border: str = "") -> str:
            if idx in top5_set[col_k]:
                return f"background:#DCFCE7; color:#15803D; font-weight:800; {extra_border}"
            elif idx in bot3_set[col_k]:
                return f"background:#FEE2E2; color:#B91C1C; font-weight:800; {extra_border}"
            return f"background:{row_bg}; color:#0F172A; {extra_border}"

        vmax_str = f"{r['V_max']:.1f}".replace(".", ",") if r["has_gps"] else "0,0"
        vpct_val = int(r["V_max_pct"])
        vhsr_val = r['VHSR_25'] if r['VHSR_25'] > 0 else ''

        rows_ind += (
            f"<tr style='background:{row_bg}; {top_b}'>"
            f"<td style='position:sticky; left:0; z-index:2; background:{name_bg}; box-shadow:2px 0 4px rgba(15,23,42,0.06); padding:3px 10px; font-weight:600; font-size:0.75rem; color:#0F172A; border-bottom:1px solid #CBD5E1; border-right:1px solid #94A3B8; white-space:nowrap;'>{r['player_name']}{status_tag}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Tempo')}'>{r['Tempo']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Distanza')}'>{r['Distanza']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('m_min')}'>{r['m_min']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Run_Dist')}'>{r['Run_Dist']}</td>"
            f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Hml_25')}'>{r['Hml_25']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Hml_40')}'>{r['Hml_40']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('VHml_50')}'>{r['VHml_50']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('Power_Events')}'>{r['Power_Events']}</td>"
            f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('HSR_18')}'>{r['HSR_18']}</td>"
            f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('HSR_20')}'>{r['HSR_20']}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('VHSR_25')}'>{vhsr_val}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('V_max')}'>{vmax_str}</td>"
            f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0; {_cell_style('V_max_pct')}'>{vpct_val}</td>"
            f"</tr>"
        )

    top_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 60%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <div style="font-size:1.08rem; font-weight:800; letter-spacing:0.3px;">{header_title}</div>
                <div style="font-size:0.76rem; color:#BAE6FD;">{header_sub}</div>
            </div>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; font-size:0.72rem; font-weight:700;">
                <span style="background:#FEF08A; color:#854D0E; padding:3px 8px; border-radius:5px;">Giallo - Modificato</span>
                <span style="background:#BAE6FD; color:#0369A1; padding:3px 8px; border-radius:5px;">Celeste - RTP</span>
                <span style="background:#FCA5A5; color:#7F1D1D; padding:3px 8px; border-radius:5px;">Rosso - OFF FEET</span>
                <span style="background:#DCFCE7; color:#15803D; padding:3px 8px; border-radius:5px;">Verde: Top 5 del Reparto</span>
                <span style="background:#FEE2E2; color:#B91C1C; padding:3px 8px; border-radius:5px;">Rosso: 3 Più Bassi del Reparto</span>
            </div>
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800;">
                    <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; box-shadow:2px 0 4px rgba(15,23,42,0.06); padding:6px 10px; text-align:left; border-bottom:2px solid #0F172A; border-right:1px solid #94A3B8;">Giocatore (Raduno)</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">m\\min</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Run Dist</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml &gt;25W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml&gt;40W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHml&gt;50W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power<br>Events</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR &gt;18</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR&gt;20</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHSR&gt;25</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_ind}</tbody>
        </table>
    </div>
    """

    tempo_th = "<th style='padding:5px 5px; text-align:center;'>Tempo</th>" if show_tempo_in_role_table else ""
    rows_role = ""
    for _, rr in role_df.iterrows():
        tempo_td = f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Tempo']}</td>" if show_tempo_in_role_table else ""
        rows_role += (
            f"<tr style='background:#BAE6FD; color:#0F172A;'>"
            f"<td style='padding:4px 10px; font-weight:700; font-size:0.74rem; border-bottom:1px solid #7DD3FC;'>{rr['Label']}</td>"
            f"{tempo_td}"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Distanza']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['m_min']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Run_Dist']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Hml_25']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Hml_40']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['VHml_50']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Power_Events']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['HSR_18']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['HSR_20']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['VHSR_25']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['V_max']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['V_max_pct']}</td>"
            f"</tr>"
        )

    for idx_d, dr in dept_df.iterrows():
        top_sep = "border-top:2px solid #0284C7;" if idx_d == 0 else ""
        tempo_td = f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Tempo']}</td>" if show_tempo_in_role_table else ""
        rows_role += (
            f"<tr style='background:#7DD3FC; color:#031926; font-weight:800; {top_sep}'>"
            f"<td style='padding:5px 10px; font-weight:800; font-size:0.78rem;'>{dr['Label']}</td>"
            f"{tempo_td}"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Distanza']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['m_min']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Run_Dist']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Hml_25']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Hml_40']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['VHml_50']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['Power_Events']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['HSR_18']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['HSR_20']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['VHSR_25']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['V_max']}</td>"
            f"<td style='padding:5px 6px; font-size:0.76rem; text-align:center;'>{dr['V_max_pct']}</td>"
            f"</tr>"
        )

    bot_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#BAE6FD; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <table style="width:100%; border-collapse:collapse; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#7DD3FC; color:#031926; font-size:0.67rem; font-weight:800; border-bottom:2px solid #0284C7;">
                    <th style="padding:5px 10px; text-align:left;">Ruolo / Reparto</th>
                    {tempo_th}
                    <th style="padding:5px 5px; text-align:center;">Distanza</th>
                    <th style="padding:5px 5px; text-align:center;">m\\min</th>
                    <th style="padding:5px 5px; text-align:center;">Run Dist</th>
                    <th style="padding:5px 5px; text-align:center;">Hml &gt;25W</th>
                    <th style="padding:5px 5px; text-align:center;">Hml&gt;40W</th>
                    <th style="padding:5px 5px; text-align:center;">VHml&gt;50W</th>
                    <th style="padding:5px 5px; text-align:center;">N 40\\50W</th>
                    <th style="padding:5px 5px; text-align:center;">HSR &gt;18</th>
                    <th style="padding:5px 5px; text-align:center;">HSR&gt;20</th>
                    <th style="padding:5px 5px; text-align:center;">VHSR&gt;25</th>
                    <th style="padding:5px 5px; text-align:center;">V max</th>
                    <th style="padding:5px 5px; text-align:center;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_role}</tbody>
        </table>
        <div style="background:#002B49; color:#CBD5E1; font-size:0.65rem; padding:4px 10px; border-top:1px solid #0284C7;">
            * <b>Nota di calcolo:</b> Gli atleti in allenamento <b style="color:#FEF08A;">Modificato</b> (giallo) e <b style="color:#BAE6FD;">RTP</b> (celeste) sono automaticamente <u>esclusi</u> dal calcolo delle medie di ruolo e reparto.
        </div>
    </div>
    """

    return (
        "".join(line.strip() for line in top_html.splitlines() if line.strip()),
        "".join(line.strip() for line in bot_html.splitlines() if line.strip()),
    )


def _build_player_sheet_neutral_html(
    df_sess: pd.DataFrame,
    header_title: str,
    header_sub: str,
) -> str:
    """
    Costruisce la scheda neutra per i giocatori:
    - Solo dati individuali (nessuna tabella medie di ruolo/reparto, nessun grafico di analisi)
    - Nessun colore di evidenziazione (niente verde Top 5, niente rosso 3 più bassi, niente badge/colori stato)
    """
    rows_ind = ""
    prev_dept = None
    for idx, (_, r) in enumerate(df_sess.iterrows()):
        dept = r.get("department", "Avanti")
        is_dept_switch = prev_dept is not None and dept != prev_dept
        prev_dept = dept
        top_b = "border-top: 2.5px solid #334155;" if is_dept_switch else ""
        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"

        vmax_str = f"{r['V_max']:.1f}".replace(".", ",") if r["has_gps"] else "0,0"
        vpct_val = int(r["V_max_pct"])
        vhsr_val = r["VHSR_25"] if r["VHSR_25"] > 0 else ""
        cell_base = f"padding:4px 6px; font-size:0.76rem; text-align:center; border-bottom:1px solid #E2E8F0; background:{row_bg}; color:#0F172A;"

        rows_ind += (
            f"<tr style='background:{row_bg}; {top_b}'>"
            f"<td style='position:sticky; left:0; z-index:2; background:{row_bg}; box-shadow:2px 0 4px rgba(15,23,42,0.06); padding:4px 10px; font-weight:600; font-size:0.76rem; color:#0F172A; border-bottom:1px solid #CBD5E1; border-right:1px solid #94A3B8; white-space:nowrap;'>{r['player_name']}</td>"
            f"<td style='{cell_base}'>{r['Tempo']}</td>"
            f"<td style='{cell_base}'>{r['Distanza']}</td>"
            f"<td style='{cell_base}'>{r['m_min']}</td>"
            f"<td style='{cell_base}'>{r['Run_Dist']}</td>"
            f"<td style='{cell_base}'>{r['Hml_25']}</td>"
            f"<td style='{cell_base}'>{r['Hml_40']}</td>"
            f"<td style='{cell_base}'>{r['VHml_50']}</td>"
            f"<td style='{cell_base}'>{r['Power_Events']}</td>"
            f"<td style='{cell_base}'>{r['HSR_18']}</td>"
            f"<td style='{cell_base}'>{r['HSR_20']}</td>"
            f"<td style='{cell_base}'>{vhsr_val}</td>"
            f"<td style='{cell_base}'>{vmax_str}</td>"
            f"<td style='{cell_base}'>{vpct_val}</td>"
            f"</tr>"
        )

    html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 60%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <div style="font-size:1.08rem; font-weight:800; letter-spacing:0.3px;">{header_title}</div>
                <div style="font-size:0.76rem; color:#BAE6FD;">{header_sub}</div>
            </div>
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#F8FAFC; color:#0F172A; font-size:0.69rem; font-weight:800;">
                    <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; box-shadow:2px 0 4px rgba(15,23,42,0.06); padding:6px 10px; text-align:left; border-bottom:2px solid #0F172A; border-right:1px solid #94A3B8;">Giocatore</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">m\\min</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Run Dist</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml &gt;25W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml&gt;40W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHml&gt;50W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power<br>Events</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR &gt;18</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR&gt;20</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHSR&gt;25</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_ind}</tbody>
        </table>
    </div>
    """
    return "".join(line.strip() for line in html.splitlines() if line.strip())


def _build_training_attainment_chart(dept_df: pd.DataFrame, archetype: str) -> go.Figure:
    base = SESSION_TYPE_BASELINES.get(archetype, SESSION_TYPE_BASELINES["Velocità"])
    fw_base = base["Avanti"]
    bk_base = base["TreQuarti"]

    fw_row = dept_df[dept_df["department"] == "Avanti"].iloc[0] if not dept_df[dept_df["department"] == "Avanti"].empty else {}
    bk_row = dept_df[dept_df["department"] == "TreQuarti"].iloc[0] if not dept_df[dept_df["department"] == "TreQuarti"].empty else {}

    categories = ["DISTANZA", "M\\MIN", "RUNNING DISTANCE", "HML", "HSR 18/20", "TIME"]

    fw_pcts = [
        int(round((float(fw_row.get("Distanza", 0)) / fw_base["distance_m"]) * 100)) if fw_base["distance_m"] else 0,
        int(round((float(fw_row.get("m_min", 0)) / fw_base["m_per_min"]) * 100)) if fw_base["m_per_min"] else 0,
        int(round((float(fw_row.get("Run_Dist", 0)) / fw_base["run_dist"]) * 100)) if fw_base["run_dist"] else 0,
        int(round((float(fw_row.get("Hml_25", 0)) / fw_base["hml"]) * 100)) if fw_base["hml"] else 0,
        int(round((float(fw_row.get("HSR_18", 0)) / fw_base["hsr"]) * 100)) if fw_base["hsr"] else 0,
        int(round((float(fw_row.get("Tempo", 0)) / fw_base["time"]) * 100)) if fw_base["time"] else 0,
    ]
    bk_pcts = [
        int(round((float(bk_row.get("Distanza", 0)) / bk_base["distance_m"]) * 100)) if bk_base["distance_m"] else 0,
        int(round((float(bk_row.get("m_min", 0)) / bk_base["m_per_min"]) * 100)) if bk_base["m_per_min"] else 0,
        int(round((float(bk_row.get("Run_Dist", 0)) / bk_base["run_dist"]) * 100)) if bk_base["run_dist"] else 0,
        int(round((float(bk_row.get("Hml_25", 0)) / bk_base["hml"]) * 100)) if bk_base["hml"] else 0,
        int(round((float(bk_row.get("HSR_20", 0)) / bk_base["hsr"]) * 100)) if bk_base["hsr"] else 0,
        int(round((float(bk_row.get("Tempo", 0)) / bk_base["time"]) * 100)) if bk_base["time"] else 0,
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=categories,
            y=fw_pcts,
            name="AVANTI",
            marker_color="#0088CE",
            text=[f"<b>{v}%</b>" for v in fw_pcts],
            textposition="outside",
            width=0.28,
        )
    )
    fig.add_trace(
        go.Bar(
            x=categories,
            y=bk_pcts,
            name="TREQUARTI",
            marker_color="#1B365D",
            text=[f"<b>{v}%</b>" for v in bk_pcts],
            textposition="outside",
            width=0.28,
        )
    )
    fig.add_hline(
        y=100,
        line_dash="dash",
        line_color="#16A34A",
        line_width=2.5,
        annotation_text="Media allenamento (100%)",
        annotation_position="top right",
        annotation_font_color="#15803D",
    )
    max_y = max(max(fw_pcts + bk_pcts, default=120) + 22, 140)
    fig.update_layout(
        title=dict(
            text=f"<b>PERCENTUALE DI RAGGIUNGIMENTO DELLA MEDIA ALLENAMENTO ({archetype.upper()})</b>",
            x=0.5,
            xanchor="center",
            font=dict(size=15, color="#0F172A"),
        ),
        barmode="group",
        height=330,
        margin=dict(l=25, r=25, t=55, b=35),
        plot_bgcolor="#E0F2FE",
        paper_bgcolor="#FFFFFF",
        yaxis=dict(range=[0, max_y], showticklabels=False, showgrid=True, gridcolor="rgba(148,163,184,0.25)"),
        xaxis=dict(tickfont=dict(size=12, family="Inter", color="#0F172A")),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
    )
    return fig


def _build_individual_histogram_figure(df_sess: pd.DataFrame, dept_row: dict, department: str, archetype: str, sort_col: str = "Hml_25") -> go.Figure:
    sub = df_sess[(df_sess["department"] == department) & (df_sess["has_gps"] == True)].copy()
    hsr_col = "HSR_18" if department == "Avanti" else "HSR_20"
    hsr_label = "HSR >18" if department == "Avanti" else "HSR >20"

    base_cfg = SESSION_TYPE_BASELINES.get(archetype, SESSION_TYPE_BASELINES["Velocità"])[department]
    max_avg_row = pd.DataFrame([{
        "player_name": "MAX AVG",
        "Run_Dist": int(base_cfg["max_avg_rd"]),
        "Hml_25": int(base_cfg["max_avg_hml"]),
        hsr_col: int(base_cfg["max_avg_hsr"]),
        "is_benchmark": True,
    }])

    if not sub.empty:
        sub["is_benchmark"] = False
        plot_df = pd.concat([sub[["player_name", "Run_Dist", "Hml_25", hsr_col, "is_benchmark"]], max_avg_row], ignore_index=True)
    else:
        plot_df = max_avg_row

    sort_key = hsr_col if sort_col == "HSR" else sort_col
    plot_df = plot_df.sort_values(by=[sort_key, "Run_Dist"], ascending=[True, True]).reset_index(drop=True)

    x_names = [f"<b>{n}</b>" if n == "MAX AVG" else n for n in plot_df["player_name"]]
    rd_vals = plot_df["Run_Dist"].astype(int).tolist()
    hml_vals = plot_df["Hml_25"].astype(int).tolist()
    hsr_vals = plot_df[hsr_col].astype(int).tolist()

    avg_rd = int(dept_row.get("Run_Dist", 0)) if dept_row else int(np.mean(rd_vals))
    avg_hml = int(dept_row.get("Hml_25", 0)) if dept_row else int(np.mean(hml_vals))
    avg_hsr = int(dept_row.get(hsr_col, 0)) if dept_row else int(np.mean(hsr_vals))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_names,
            y=rd_vals,
            name="Run Distance",
            marker=dict(color=["#22C55E" if n != "<b>MAX AVG</b>" else "#15803D" for n in x_names], line=dict(color="#166534", width=1)),
            text=[f"<b>{v:,}</b>".replace(",", ".") for v in rd_vals],
            textposition="outside",
            textfont=dict(size=10, color="#14532D"),
            width=0.46,
        )
    )
    fig.add_trace(
        go.Bar(
            x=x_names,
            y=hml_vals,
            name="Hml (>25W)",
            marker=dict(color=["#0284C7" if n != "<b>MAX AVG</b>" else "#1E3A8A" for n in x_names], line=dict(color="#0369A1", width=1)),
            text=[f"<b>{v}</b>" for v in hml_vals],
            textposition="outside",
            textfont=dict(size=10, color="#0C4A6E"),
            width=0.46,
        )
    )
    fig.add_trace(
        go.Bar(
            x=x_names,
            y=hsr_vals,
            name=f"HSR 18/20 ({hsr_label})",
            marker=dict(color=["#EF4444" if n != "<b>MAX AVG</b>" else "#991B1B" for n in x_names], line=dict(color="#B91C1C", width=1)),
            text=[f"<b>{v}</b>" for v in hsr_vals],
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(size=10, color="#FFFFFF"),
            width=0.46,
        )
    )

    fig.add_hline(y=avg_rd, line_dash="dash", line_color="#16A34A", line_width=1.8, annotation_text=f"AVG RD ({avg_rd} m)", annotation_position="top left", annotation_font_color="#15803D")
    fig.add_hline(y=avg_hml, line_dash="dash", line_color="#0284C7", line_width=1.8, annotation_text=f"AVG Hml ({avg_hml} m)", annotation_position="top right", annotation_font_color="#0369A1")
    fig.add_hline(y=avg_hsr, line_dash="dash", line_color="#DC2626", line_width=1.8, annotation_text=f"AVG HSR ({avg_hsr} m)", annotation_position="bottom right", annotation_font_color="#B91C1C")

    title_color = "#15803D" if department == "Avanti" else "#DC2626"
    dept_title = "Avanti" if department == "Avanti" else "Trequarti"
    max_rd = max(rd_vals, default=3500) + 450

    fig.update_layout(
        title=dict(text=f"<b style='color:{title_color};'>Dati Individuali {dept_title} — Ordine crescente {sort_col.replace('_25', '')}</b>", x=0.01, xanchor="left", font=dict(size=16)),
        barmode="overlay",
        height=430,
        margin=dict(l=30, r=25, t=50, b=95),
        plot_bgcolor="#F1F5F9",
        paper_bgcolor="#FFFFFF",
        yaxis=dict(range=[0, max_rd], title="Metri (m)", gridcolor="#CBD5E1"),
        xaxis=dict(tickangle=-38, tickfont=dict(size=11, color="#0F172A")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0),
    )
    return fig


def _compute_match_pct_columns(df_in: pd.DataFrame, bench_source: str = "excel") -> pd.DataFrame:
    """
    Calcola per ciascun giocatore:
    - pct_hml_match = Hml_25 / HmlAvg_Match_80' * 100
    - pct_hsr_match = (HSR_18 per Avanti, HSR_20 per Trequarti) / HSRAvg_Match_80' * 100
    """
    df = df_in.copy()
    if bench_source == "fir":
        hml_b_col, hsr_b_col = "hml_avg_fir", "hsr_avg_fir"
    elif bench_source == "tot":
        hml_b_col, hsr_b_col = "hml_avg_tot", "hsr_avg_tot"
    else:
        hml_b_col, hsr_b_col = "hml_avg_excel", "hsr_avg_excel"

    hml_bench = pd.to_numeric(df.get(hml_b_col), errors="coerce").fillna(pd.to_numeric(df.get("hml_avg_tot"), errors="coerce")).replace(0, np.nan)
    hsr_bench = pd.to_numeric(df.get(hsr_b_col), errors="coerce").fillna(pd.to_numeric(df.get("hsr_avg_tot"), errors="coerce")).replace(0, np.nan)

    hsr_player_val = np.where(df["department"] == "Avanti", df["HSR_18"], df["HSR_20"])
    df["hsr_role_val"] = hsr_player_val
    df["hml_bench_used"] = hml_bench.round(0)
    df["hsr_bench_used"] = hsr_bench.round(0)
    df["pct_hml_match"] = np.where(hml_bench > 0, np.round((df["Hml_25"] / hml_bench) * 100.0), 0.0).astype(int)
    df["pct_hsr_match"] = np.where(hsr_bench > 0, np.round((hsr_player_val / hsr_bench) * 100.0), 0.0).astype(int)
    return df


def _build_match_pct_figure(df_with_pct: pd.DataFrame, chart_style: str = "dual_ranking", is_weekly: bool = False) -> go.Figure:
    """
    Costruisce il grafico centrale per Report Giornata e Report Settimanale:
    1. 'dual_ranking' (Standard FIR PDF): Doppio istogramma orizzontale affiancato (% HML MEDI INDIVIDUALI MATCH 80' a sinistra in Blu, % HSR MEDI INDIVIDUALI MATCH 80' a destra in Rosso, ciascuno ordinato in modo crescente dal basso verso l'alto).
    2. 'paired_bars' (Confronto Diretto Atleta): Barre accoppiate HML % vs HSR % sullo stesso giocatore per evidenziare sbilanciamenti metabolico/velocità.
    3. 'quadrant_scatter' (Matrice a 4 Quadranti Workload): Scatter plot % Match HML (X) vs % Match HSR (Y) diviso per Avanti e Trequarti.
    """
    active = df_with_pct[df_with_pct["has_gps"] == True].copy()
    if active.empty:
        return go.Figure()

    ref_line = 150 if is_weekly else 100
    lbl_hml = "% HML MEDIE INDIVIDUALI MATCH 80'" if is_weekly else "% HML MEDI INDIVIDUALI MATCH 80'"
    lbl_hsr = "% HSR MEDIE INDIVIDUALI MATCH 80'" if is_weekly else "% HSR MEDI INDIVIDUALI MATCH 80'"

    if chart_style == "paired_bars":
        s_df = active.sort_values(by=["department", "pct_hml_match"], ascending=[True, False]).reset_index(drop=True)
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=s_df["player_name"],
                y=s_df["pct_hml_match"],
                name=lbl_hml,
                marker_color="#1D4ED8",
                text=[f"<b>{v}%</b>" for v in s_df["pct_hml_match"]],
                textposition="outside",
            )
        )
        fig.add_trace(
            go.Bar(
                x=s_df["player_name"],
                y=s_df["pct_hsr_match"],
                name=lbl_hsr,
                marker_color="#DC2626",
                text=[f"<b>{v}%</b>" for v in s_df["pct_hsr_match"]],
                textposition="outside",
            )
        )
        fig.add_hline(y=100, line_dash="dash", line_color="#16A34A", line_width=2, annotation_text="100% Match (80')", annotation_position="top right")
        if is_weekly:
            fig.add_hline(y=180, line_dash="dot", line_color="#D97706", line_width=1.8, annotation_text="Target Settimanale 180%", annotation_position="top left")
        fig.update_layout(
            title=dict(text=f"<b>Confronto Accoppiato per Atleta: {lbl_hml} vs {lbl_hsr}</b>", x=0.5, xanchor="center"),
            barmode="group",
            height=450,
            margin=dict(l=25, r=25, t=55, b=100),
            plot_bgcolor="#E0F2FE",
            paper_bgcolor="#FFFFFF",
            xaxis=dict(tickangle=-38, tickfont=dict(size=10)),
            yaxis=dict(title="% Riferimento Partita (80')"),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        )
        return fig

    if chart_style == "quadrant_scatter":
        fig = go.Figure()
        for dept_name, col_hex in [("Avanti", "#0284C7"), ("TreQuarti", "#DC2626")]:
            sub_d = active[active["department"] == dept_name]
            if not sub_d.empty:
                fig.add_trace(
                    go.Scatter(
                        x=sub_d["pct_hml_match"],
                        y=sub_d["pct_hsr_match"],
                        mode="markers+text",
                        name=dept_name,
                        text=sub_d["player_name"],
                        textposition="top center",
                        textfont=dict(size=9.5, color="#0F172A"),
                        marker=dict(size=12, color=col_hex, line=dict(width=1.5, color="#FFFFFF")),
                        hovertemplate="<b>%{text}</b><br>% Match HML: <b>%{x}%</b><br>% Match HSR: <b>%{y}%</b><extra></extra>",
                    )
                )
        avg_x = float(active["pct_hml_match"].mean())
        avg_y = float(active["pct_hsr_match"].mean())
        fig.add_vline(x=avg_x, line_dash="dash", line_color="#0284C7", annotation_text=f"Media HML ({avg_x:.0f}%)")
        fig.add_hline(y=avg_y, line_dash="dash", line_color="#DC2626", annotation_text=f"Media HSR ({avg_y:.0f}%)")
        fig.update_layout(
            title=dict(text=f"<b>Matrice Carico Relativo: {lbl_hml} (Asse X) vs {lbl_hsr} (Asse Y)</b>", x=0.5, xanchor="center"),
            height=480,
            margin=dict(l=35, r=35, t=55, b=40),
            plot_bgcolor="#F0F9FF",
            paper_bgcolor="#FFFFFF",
            xaxis=dict(title=lbl_hml, ticksuffix="%", gridcolor="#CBD5E1"),
            yaxis=dict(title=lbl_hsr, ticksuffix="%", gridcolor="#CBD5E1"),
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5),
        )
        return fig

    # Default 'dual_ranking': Doppio grafico a barre orizzontali affiancato identico al PDF FIR
    hml_sorted = active.sort_values(by=["pct_hml_match", "Hml_25"], ascending=[True, True]).reset_index(drop=True)
    hsr_sorted = active.sort_values(by=["pct_hsr_match", "hsr_role_val"], ascending=[True, True]).reset_index(drop=True)

    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=(f"<b>{lbl_hml}</b>", f"<b>{lbl_hsr}</b>"),
        horizontal_spacing=0.18,
    )

    fig.add_trace(
        go.Bar(
            y=hml_sorted["player_name"],
            x=hml_sorted["pct_hml_match"],
            orientation="h",
            name=lbl_hml,
            marker=dict(color="#1E3A8A", line=dict(color="#172554", width=0.8)),
            text=[f"<b>{v}%</b>" for v in hml_sorted["pct_hml_match"]],
            textposition="inside",
            insidetextanchor="end",
            textfont=dict(size=9, color="#FFFFFF"),
            hovertemplate="<b>%{y}</b><br>HML Match 80': <b>%{x}%</b><extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            y=hsr_sorted["player_name"],
            x=hsr_sorted["pct_hsr_match"],
            orientation="h",
            name=lbl_hsr,
            marker=dict(color="#DC2626", line=dict(color="#991B1B", width=0.8)),
            text=[f"<b>{v}%</b>" for v in hsr_sorted["pct_hsr_match"]],
            textposition="inside",
            insidetextanchor="end",
            textfont=dict(size=9, color="#FFFFFF"),
            hovertemplate="<b>%{y}</b><br>HSR Match 80': <b>%{x}%</b><extra></extra>",
        ),
        row=1,
        col=2,
    )

    fig.add_vline(x=100, line_dash="dash", line_color="#16A34A", line_width=1.5, row=1, col=1)
    fig.add_vline(x=100, line_dash="dash", line_color="#16A34A", line_width=1.5, row=1, col=2)

    fig.update_layout(
        height=max(520, len(active) * 16 + 70),
        margin=dict(l=130, r=25, t=45, b=25),
        plot_bgcolor="#BAE6FD",
        paper_bgcolor="#E0F2FE",
        showlegend=False,
        xaxis=dict(showticklabels=False, showgrid=False),
        xaxis2=dict(showticklabels=False, showgrid=False),
        yaxis=dict(tickfont=dict(size=9.5, color="#0F172A")),
        yaxis2=dict(tickfont=dict(size=9.5, color="#0F172A")),
    )
    return fig


def _build_target_stacked_bar_chart(
    counts_dict: dict,
    metric_label: str,
    target_val: float,
    tol_val: float,
) -> go.Figure:
    """
    Costruisce il grafico a barre 100% stacked per Squadra, Avanti, TreQuarti:
    - Sotto target (< Target - Tol): Rosso (#EF4444)
    - Nel target [Target - Tol, Target + Tol]: Verde (#22C55E)
    - Sopra target (> Target + Tol): Ambra (#F59E0B)
    """
    cats = ["SQUADRA", "AVANTI", "TREQUARTI"]
    sotto = [counts_dict[c]["sotto"] for c in cats]
    nel = [counts_dict[c]["nel"] for c in cats]
    sopra = [counts_dict[c]["sopra"] for c in cats]
    totals = [counts_dict[c]["total"] for c in cats]

    pct_sotto = [(s / t * 100) if t > 0 else 0 for s, t in zip(sotto, totals)]
    pct_nel = [(n / t * 100) if t > 0 else 0 for n, t in zip(nel, totals)]
    pct_sopra = [(sp / t * 100) if t > 0 else 0 for sp, t in zip(sopra, totals)]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="SOTTO IL TARGET",
        x=cats, y=pct_sotto,
        marker_color="#EF4444",
        text=[str(v) if v > 0 else "" for v in sotto],
        textposition="inside",
        textfont=dict(color="#FFFFFF", size=12, family="Arial Black"),
    ))
    fig.add_trace(go.Bar(
        name="NEL TARGET",
        x=cats, y=pct_nel,
        marker_color="#22C55E",
        text=[str(v) if v > 0 else "" for v in nel],
        textposition="inside",
        textfont=dict(color="#FFFFFF", size=12, family="Arial Black"),
    ))
    fig.add_trace(go.Bar(
        name="SOPRA IL TARGET",
        x=cats, y=pct_sopra,
        marker_color="#F59E0B",
        text=[str(v) if v > 0 else "" for v in sopra],
        textposition="inside",
        textfont=dict(color="#FFFFFF", size=12, family="Arial Black"),
    ))

    for c, t in zip(cats, totals):
        fig.add_annotation(
            x=c, y=102,
            text=f"<b>{t}</b>",
            showarrow=False,
            font=dict(size=12, color="#002B49"),
        )

    fig.update_layout(
        barmode="stack",
        title=dict(
            text=f"<b>RAGGIUNGIMENTO TARGET {metric_label}</b><br><span style='font-size:10.5px; color:#64748B;'>Target: {target_val:.0f}% (±{tol_val:.0f}%)</span>",
            font=dict(size=13, color="#002B49"),
            x=0.5,
            xanchor="center",
        ),
        yaxis=dict(ticksuffix="%", range=[0, 108], showgrid=True, gridcolor="#E2E8F0"),
        xaxis=dict(tickfont=dict(size=11.5, family="Arial Black", color="#002B49")),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="center",
            x=0.5,
            font=dict(size=10.5, color="#1E293B"),
        ),
        margin=dict(l=35, r=35, t=55, b=80),
        height=370,
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
    )
    return fig


def _get_oval_match_minutes_map(date_str: str) -> dict[str, float]:
    """
    Estrae i minuti ufficiali giocati (Min) da Oval Match per una data di gara (date_str YYYY-MM-DD).
    Indicizza i giocatori sia per nome FIR (fir_player_name) sia per playerFullName (e forma normalizzata).
    """
    clean_dt = str(date_str or "")[:10].strip()
    if not clean_dt:
        return {}
    oval_df = utils.get_oval_matches_df()
    if oval_df.empty:
        return {}
    sub_ov = pd.DataFrame()
    if "match_date" in oval_df.columns:
        sub_ov = oval_df[oval_df["match_date"].astype(str).str[:10] == clean_dt]
    if sub_ov.empty and "date" in oval_df.columns:
        sub_ov = oval_df[oval_df["date"].astype(str).str[:10] == clean_dt]
    if sub_ov.empty:
        return {}

    import unicodedata
    def _norm_key(s: str) -> str:
        s_up = str(s or "").strip().upper()
        return "".join(c for c in unicodedata.normalize("NFD", s_up) if unicodedata.category(c) != "Mn")

    min_map: dict[str, float] = {}
    for _, r in sub_ov.iterrows():
        m_val = float(pd.to_numeric(r.get("Min", 0), errors="coerce") or 0.0)
        for col in ("fir_player_name", "playerFullName", "player"):
            raw_nm = str(r.get(col) or "").strip()
            if not raw_nm or raw_nm.lower() in ("nan", "none"):
                continue
            k_up = raw_nm.upper()
            k_norm = _norm_key(raw_nm)
            min_map[k_up] = max(min_map.get(k_up, 0.0), m_val)
            min_map[k_norm] = max(min_map.get(k_norm, 0.0), m_val)
            ident = utils.resolve_player_identity(raw_nm)
            disp_nm = str(ident.get("name_display") or "").strip()
            if disp_nm:
                d_up = disp_nm.upper()
                d_norm = _norm_key(disp_nm)
                min_map[d_up] = max(min_map.get(d_up, 0.0), m_val)
                min_map[d_norm] = max(min_map.get(d_norm, 0.0), m_val)
    return min_map


def _lookup_oval_minutes(player_name: str, oval_map: dict[str, float]):
    if not oval_map or not player_name:
        return None
    import unicodedata
    p_up = str(player_name).strip().upper()
    if p_up in oval_map:
        return oval_map[p_up]
    p_norm = "".join(c for c in unicodedata.normalize("NFD", p_up) if unicodedata.category(c) != "Mn")
    if p_norm in oval_map:
        return oval_map[p_norm]
    parts = [p for p in p_norm.split() if len(p) >= 3]
    if parts:
        for k, v in oval_map.items():
            if all(p in k for p in parts):
                return v
    return None


def build_target_analysis_bundle(
    df_in: pd.DataFrame,
    target_hml: float,
    target_hsr: float,
    tol: float,
    is_day: bool = False,
    meta: dict = None,
) -> dict:
    """
    Costruisce il bundle dati e grafici per l'analisi TARGET (Sessione o Giornata Cumulata):
    - Classificazione Nel / Sotto / Sopra target
    - Conteggi e 100% stacked bar chart per Squadra, Avanti, TreQuarti
    - Medie Ruolo e Reparto
    - Quando analizza una seduta di tipologia 'Match' (is_day=False), recupera i minuti giocati da Oval
      ed esprime le metriche in Work Rate (/min) tranne V max e % Vmax, calcolando % Match HML e % Match HSR
      in base al tempo giocato (Work Rate rispetto al Work Rate medio Match 80').
    """
    df = df_in.copy()
    bench_source = st.session_state.get("match_bench_source", "excel")
    if "pct_hml_match" not in df.columns or "pct_hsr_match" not in df.columns:
        df = _compute_match_pct_columns(df, bench_source=bench_source)

    sess_type_str = str((meta or {}).get("session_type") or (meta or {}).get("archetype") or "").strip().lower()
    is_match_workrate = (not is_day) and (sess_type_str == "match")

    if is_match_workrate:
        oval_map = _get_oval_match_minutes_map((meta or {}).get("date_str", ""))
        new_tempo = []
        new_has_gps = []
        new_dist = []
        new_mmin = []
        new_run = []
        new_pev = []
        new_hml25 = []
        new_hml40 = []
        new_vhml50 = []
        new_hsr18 = []
        new_hsr20 = []
        new_vhsr25 = []
        new_pct_hml = []
        new_pct_hsr = []

        for _, r in df.iterrows():
            p_name = str(r.get("player_name") or "").strip()
            has_g = bool(r.get("has_gps", False)) and float(r.get("Tempo", 0)) > 0
            ov_min = _lookup_oval_minutes(p_name, oval_map)

            if oval_map:
                if ov_min is not None and ov_min > 0:
                    eff_min = float(ov_min)
                elif ov_min is None and has_g:
                    eff_min = float(r.get("Tempo", 0))
                else:
                    eff_min = 0.0
            else:
                eff_min = float(r.get("Tempo", 0)) if has_g else 0.0

            if eff_min > 0 and has_g:
                raw_dist = float(r.get("Distanza", 0))
                raw_run = float(r.get("Run_Dist", 0))
                raw_pev = float(r.get("Power_Events", 0))
                raw_h25 = float(r.get("Hml_25", 0))
                raw_h40 = float(r.get("Hml_40", 0))
                raw_vh50 = float(r.get("VHml_50", 0))
                raw_hsr18 = float(r.get("HSR_18", 0))
                raw_hsr20 = float(r.get("HSR_20", 0))
                raw_vhsr25 = float(r.get("VHSR_25", 0))

                dept = str(r.get("department") or "Avanti")
                raw_hsr_role = raw_hsr18 if dept == "Avanti" else raw_hsr20

                hml_bench = float(pd.to_numeric(r.get("hml_bench_used", 0), errors="coerce") or 0.0)
                hsr_bench = float(pd.to_numeric(r.get("hsr_bench_used", 0), errors="coerce") or 0.0)

                hml_wr = raw_h25 / eff_min
                hsr_wr = raw_hsr_role / eff_min

                pct_hml = int(round((hml_wr / (hml_bench / 80.0)) * 100.0)) if hml_bench > 0 else 0
                pct_hsr = int(round((hsr_wr / (hsr_bench / 80.0)) * 100.0)) if hsr_bench > 0 else 0

                new_tempo.append(int(round(eff_min)))
                new_has_gps.append(True)
                new_dist.append(round(raw_dist / eff_min, 1))
                new_mmin.append(round(raw_dist / eff_min, 1))
                new_run.append(round(raw_run / eff_min, 1))
                new_pev.append(round(raw_pev / eff_min, 1))
                new_hml25.append(round(hml_wr, 1))
                new_hml40.append(round(raw_h40 / eff_min, 1))
                new_vhml50.append(round(raw_vh50 / eff_min, 1))
                new_hsr18.append(round(raw_hsr18 / eff_min, 1))
                new_hsr20.append(round(raw_hsr20 / eff_min, 1))
                new_vhsr25.append(round(raw_vhsr25 / eff_min, 1))
                new_pct_hml.append(pct_hml)
                new_pct_hsr.append(pct_hsr)
            else:
                new_tempo.append(0)
                new_has_gps.append(False)
                new_dist.append(0.0)
                new_mmin.append(0.0)
                new_run.append(0.0)
                new_pev.append(0.0)
                new_hml25.append(0.0)
                new_hml40.append(0.0)
                new_vhml50.append(0.0)
                new_hsr18.append(0.0)
                new_hsr20.append(0.0)
                new_vhsr25.append(0.0)
                new_pct_hml.append(0)
                new_pct_hsr.append(0)

        df["Tempo"] = new_tempo
        df["has_gps"] = new_has_gps
        df["Distanza"] = new_dist
        df["m_min"] = new_mmin
        df["Run_Dist"] = new_run
        df["Power_Events"] = new_pev
        df["Hml_25"] = new_hml25
        df["Hml_40"] = new_hml40
        df["VHml_50"] = new_vhml50
        df["HSR_18"] = new_hsr18
        df["HSR_20"] = new_hsr20
        df["VHSR_25"] = new_vhsr25
        df["pct_hml_match"] = new_pct_hml
        df["pct_hsr_match"] = new_pct_hsr

    hml_min, hml_max = target_hml - tol, target_hml + tol
    def _classify_hml(val):
        if pd.isna(val) or val <= 0:
            return "Sotto"
        if val < hml_min:
            return "Sotto"
        elif val > hml_max:
            return "Sopra"
        return "Nel"

    hsr_min, hsr_max = target_hsr - tol, target_hsr + tol
    def _classify_hsr(val):
        if pd.isna(val) or val <= 0:
            return "Sotto"
        if val < hsr_min:
            return "Sotto"
        elif val > hsr_max:
            return "Sopra"
        return "Nel"

    df["status_target_hml"] = df["pct_hml_match"].apply(_classify_hml)
    df["status_target_hsr"] = df["pct_hsr_match"].apply(_classify_hsr)

    def _calc_counts(sub_df, stat_col):
        valid = sub_df[sub_df["has_gps"] == True]
        sotto = int((valid[stat_col] == "Sotto").sum())
        nel = int((valid[stat_col] == "Nel").sum())
        sopra = int((valid[stat_col] == "Sopra").sum())
        tot = sotto + nel + sopra
        return {"sotto": sotto, "nel": nel, "sopra": sopra, "total": tot}

    counts_hml = {
        "SQUADRA": _calc_counts(df, "status_target_hml"),
        "AVANTI": _calc_counts(df[df["department"] == "Avanti"], "status_target_hml"),
        "TREQUARTI": _calc_counts(df[df["department"] == "TreQuarti"], "status_target_hml"),
    }

    counts_hsr = {
        "SQUADRA": _calc_counts(df, "status_target_hsr"),
        "AVANTI": _calc_counts(df[df["department"] == "Avanti"], "status_target_hsr"),
        "TREQUARTI": _calc_counts(df[df["department"] == "TreQuarti"], "status_target_hsr"),
    }

    lbl_hml = "HML/min (>25.5W)" if is_match_workrate else "HML 25.5W"
    lbl_hsr = "HSR/min (18\\20)" if is_match_workrate else "HSR 18\\20"
    fig_hml = _build_target_stacked_bar_chart(counts_hml, lbl_hml, target_hml, tol)
    fig_hsr = _build_target_stacked_bar_chart(counts_hsr, lbl_hsr, target_hsr, tol)

    role_df, dept_df = _compute_role_and_dept_averages(df, keep_decimals=is_match_workrate)

    return {
        "df": df,
        "role_df": role_df,
        "dept_df": dept_df,
        "target_hml": target_hml,
        "target_hsr": target_hsr,
        "tol": tol,
        "counts_hml": counts_hml,
        "counts_hsr": counts_hsr,
        "fig_hml": fig_hml,
        "fig_hsr": fig_hsr,
        "is_day": is_day,
        "is_match_workrate": is_match_workrate,
        "meta": meta or {},
    }


def build_settimana_23_bundle(
    hist_df: pd.DataFrame,
    players_df: pd.DataFrame,
    match_info: dict,
    meta: dict,
    bench_source: str = "excel",
) -> dict:
    """
    Costruisce il bundle per l'analisi Settimana 23 Convocati:
    - 23 convocati della gara selezionata (Titolari 1-15 & Finishers 16-23)
    - Dati GPS cumulati della settimana
    - Medie Ruolo e Reparto dei 23 convocati
    - Grafici individuali ordinati 1-23 per % HML e % HSR vs Match 80'
    - KPI: Top 5 HML/HSR, suddivisione fasce, Starters vs Finishers
    """
    match_dt = match_info.get("date_str") if match_info else meta.get("date_str")
    lineup_sum = utils.get_lineup_matches_summary()
    m_row = None
    if not lineup_sum.empty:
        m_sub = lineup_sum[lineup_sum["date_str"] == match_dt]
        m_row = m_sub.iloc[0] if not m_sub.empty else lineup_sum.iloc[0]

    if m_row is None:
        return {"error": "Nessuna gara con schieramento 1-23 salvata."}

    m_date = str(m_row["date_str"])
    m_name = str(m_row["match_name"])
    dtl = utils.get_match_lineup_detail(m_date)
    starters_df = dtl.get("starters", pd.DataFrame())
    finishers_df = dtl.get("finishers", pd.DataFrame())
    convocati = pd.concat([starters_df, finishers_df], ignore_index=True) if not starters_df.empty or not finishers_df.empty else pd.DataFrame()

    if convocati.empty:
        return {"error": f"Nessuno schieramento 1-23 disponibile per {m_name} ({m_date})."}

    # Periodo della settimana: priorità alla settimana del raduno o della gara selezionata
    w_start = meta.get("week_start")
    w_end = meta.get("week_end")
    if not w_start or not w_end:
        try:
            ref_dt_str = m_date or meta.get("date_str", "2026-07-04")
            m_dt = pd.to_datetime(ref_dt_str)
            ws_dt = m_dt - pd.Timedelta(days=m_dt.weekday())
            we_dt = ws_dt + pd.Timedelta(days=6)
            w_start = ws_dt.strftime("%Y-%m-%d")
            w_end = we_dt.strftime("%Y-%m-%d")
        except Exception:
            w_start = "2026-06-29"
            w_end = "2026-07-05"

    week_gps = hist_df[(hist_df["date_str"] >= w_start) & (hist_df["date_str"] <= w_end)].copy()

    status_overrides = utils.get_session_player_statuses().get(f"{meta.get('date_str')}_{meta.get('session_name')}", {})
    df_week_all = _prepare_session_camp_dataframe(week_gps, pd.DataFrame(), players_df, status_overrides, sum_m_per_min=True)
    df_week_all = _compute_match_pct_columns(df_week_all, bench_source=bench_source)

    week_map = {str(r["player_name"]).strip().upper(): r.to_dict() for _, r in df_week_all.iterrows()}

    def _find_week_data(target_name: str):
        tn = str(target_name).strip().upper()
        if tn in week_map:
            return week_map[tn]
        import unicodedata
        tn_norm = "".join(c for c in unicodedata.normalize("NFD", tn) if unicodedata.category(c) != "Mn")
        for k, v in week_map.items():
            k_norm = "".join(c for c in unicodedata.normalize("NFD", k) if unicodedata.category(c) != "Mn")
            if k_norm == tn_norm:
                return v
        parts = [p for p in tn.split() if len(p) >= 3]
        if parts:
            for k, v in week_map.items():
                if all(p in k for p in parts) or all(p in tn for p in [w for w in k.split() if len(w) >= 3]):
                    return v
        return None

    rows_23 = []
    for _, c_row in convocati.iterrows():
        p_name = str(c_row.get("player_name", "")).strip()
        j_num = int(pd.to_numeric(c_row.get("jersey_number", 0), errors="coerce") or 0)
        c_role = str(c_row.get("role", "")).strip()
        is_starter = bool(c_row.get("is_starter", j_num <= 15))

        w_data = _find_week_data(p_name)
        if w_data:
            row_dict = dict(w_data)
            row_dict["jersey_number"] = j_num
            row_dict["is_starter"] = is_starter
            row_dict["role"] = c_role if c_role else row_dict.get("role", "Pilone")
            row_dict["role_group"] = _normalize_macro_role(row_dict["role"])
            row_dict["department"] = "Avanti" if _get_role_sort_rank(row_dict["role"]) <= 4 else "TreQuarti"
        else:
            r_group = _normalize_macro_role(c_role)
            dept = "Avanti" if _get_role_sort_rank(c_role) <= 4 else "TreQuarti"
            row_dict = {
                "player_name": p_name,
                "jersey_number": j_num,
                "is_starter": is_starter,
                "role": c_role,
                "role_group": r_group,
                "department": dept,
                "status": "Off Feet",
                "has_gps": False,
                "Tempo": 0, "Distanza": 0, "m_min": 0, "Run_Dist": 0,
                "Hml_25": 0, "Hml_40": 0, "VHml_50": 0, "Power_Events": 0,
                "HSR_18": 0, "HSR_20": 0, "VHSR_25": 0, "V_max": 0.0, "V_max_pct": 0,
                "pct_hml_match": 0, "pct_hsr_match": 0,
            }
        rows_23.append(row_dict)

    df_23 = pd.DataFrame(rows_23).sort_values("jersey_number").reset_index(drop=True)

    role_df_23, dept_df_23 = _compute_role_and_dept_averages(df_23)
    role_means_dict = {str(r["Label"]): r.to_dict() for _, r in role_df_23.iterrows()}

    # Grafico 1: % HML Match 80' Individuale (23 barre)
    fig_hml_23 = go.Figure()
    fig_hml_23.add_trace(go.Bar(
        x=[f"{r['player_name']}" for _, r in df_23.iterrows()],
        y=df_23["pct_hml_match"],
        marker_color="#0284C7",
        text=[f"{v}%" for v in df_23["pct_hml_match"]],
        textposition="outside",
        textfont=dict(size=8.5, color="#0F172A", family="Arial Black"),
        hovertemplate="<b>%{x}</b><br>% HML Match 80': <b>%{y}%</b><extra></extra>",
    ))
    max_hml = max(100, int(df_23["pct_hml_match"].max() or 100))
    fig_hml_23.update_layout(
        title=dict(text="<b>% Hml in comparazione con la media Match 80' individuale</b>", font=dict(size=12, color="#002B49"), x=0.5),
        yaxis=dict(ticksuffix="%", range=[0, max_hml * 1.18], showgrid=True, gridcolor="#E2E8F0"),
        xaxis=dict(tickangle=-42, tickfont=dict(size=8.5, color="#0F172A")),
        margin=dict(l=35, r=25, t=35, b=75),
        height=260,
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
    )

    # Grafico 2: % HSR Match 80' Individuale (23 barre)
    fig_hsr_23 = go.Figure()
    fig_hsr_23.add_trace(go.Bar(
        x=[f"{r['player_name']}" for _, r in df_23.iterrows()],
        y=df_23["pct_hsr_match"],
        marker_color="#EF4444",
        text=[f"{v}%" for v in df_23["pct_hsr_match"]],
        textposition="outside",
        textfont=dict(size=8.5, color="#0F172A", family="Arial Black"),
        hovertemplate="<b>%{x}</b><br>% HSR Match 80': <b>%{y}%</b><extra></extra>",
    ))
    max_hsr = max(100, int(df_23["pct_hsr_match"].max() or 100))
    fig_hsr_23.update_layout(
        title=dict(text="<b>% HSR 18\\20 in comparazione con la media Match 80' individuale</b>", font=dict(size=12, color="#002B49"), x=0.5),
        yaxis=dict(ticksuffix="%", range=[0, max_hsr * 1.18], showgrid=True, gridcolor="#E2E8F0"),
        xaxis=dict(tickangle=-42, tickfont=dict(size=8.5, color="#0F172A")),
        margin=dict(l=35, r=25, t=35, b=75),
        height=260,
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
    )

    top_5_hml = df_23.sort_values("pct_hml_match", ascending=False).head(5)[["player_name", "pct_hml_match"]].values.tolist()
    top_5_hsr = df_23.sort_values("pct_hsr_match", ascending=False).head(5)[["player_name", "pct_hsr_match"]].values.tolist()

    dist_hml = {
        "sup_200": int((df_23["pct_hml_match"] >= 200).sum()),
        "tra_100_200": int(((df_23["pct_hml_match"] >= 100) & (df_23["pct_hml_match"] < 200)).sum()),
        "sotto_100": int((df_23["pct_hml_match"] < 100).sum()),
    }
    dist_hsr = {
        "sup_200": int((df_23["pct_hsr_match"] >= 200).sum()),
        "tra_100_200": int(((df_23["pct_hsr_match"] >= 100) & (df_23["pct_hsr_match"] < 200)).sum()),
        "sotto_100": int((df_23["pct_hsr_match"] < 100).sum()),
    }

    starters_sub = df_23[df_23["is_starter"] == True]
    finishers_sub = df_23[df_23["is_starter"] == False]
    st_fin = {
        "starters_hml": int(round(starters_sub["pct_hml_match"].mean())) if not starters_sub.empty else 0,
        "starters_hsr": int(round(starters_sub["pct_hsr_match"].mean())) if not starters_sub.empty else 0,
        "finishers_hml": int(round(finishers_sub["pct_hml_match"].mean())) if not finishers_sub.empty else 0,
        "finishers_hsr": int(round(finishers_sub["pct_hsr_match"].mean())) if not finishers_sub.empty else 0,
    }

    kpis = {
        "top_5_hml": top_5_hml,
        "top_5_hsr": top_5_hsr,
        "dist_hml": dist_hml,
        "dist_hsr": dist_hsr,
        "starters_finishers": st_fin,
    }

    return {
        "df_23": df_23,
        "role_df": role_df_23,
        "dept_df": dept_df_23,
        "role_means_dict": role_means_dict,
        "fig_hml_23": fig_hml_23,
        "fig_hsr_23": fig_hsr_23,
        "kpis": kpis,
        "match_info": {"match_name": m_name, "date_str": m_date},
        "meta": meta or {},
    }


def _render_safe_html(html_str: str):
    """
    Renderizza tabelle o frammenti HTML complessi senza rischio di formattazione grezza o markdown code blocks.
    Elimina spazi/tab iniziali riga per riga e unisce il codice in un blocco compatto.
    """
    if not html_str:
        return
    clean = "".join(line.strip() for line in html_str.splitlines() if line.strip())
    st.html(clean)


def _build_target_report_html(
    df_target: pd.DataFrame,
    role_df: pd.DataFrame,
    dept_df: pd.DataFrame,
    header_title: str,
    header_sub: str,
    target_hml: float,
    target_hsr: float,
    tol: float,
    is_day: bool = False,
    is_match_workrate: bool = False,
) -> tuple[str, str]:
    hml_min, hml_max = target_hml - tol, target_hml + tol
    hsr_min, hsr_max = target_hsr - tol, target_hsr + tol

    def _fmt_wr(val, has_g: bool = True) -> str:
        if not has_g:
            return "0,0" if is_match_workrate else "0"
        if is_match_workrate:
            return f"{float(pd.to_numeric(val, errors='coerce') or 0.0):.1f}".replace(".", ",")
        return str(int(round(float(pd.to_numeric(val, errors='coerce') or 0.0))))

    rows_ind = ""
    prev_dept = None
    for idx, r in df_target.iterrows():
        dept = r["department"]
        is_dept_switch = prev_dept is not None and dept != prev_dept
        prev_dept = dept
        top_b = "border-top: 2.5px solid #0284C7;" if is_dept_switch else ""
        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F0F9FF"

        st_val = str(r.get("status") or "Full").strip()
        status_tag = ""
        if st_val.upper() in ("MODIFICATO", "MODIFIED"):
            name_bg = "#FEF08A"
            status_tag = " <span style='background:#CA8A04; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px;'>MOD</span>"
        elif st_val.upper() == "RTP":
            name_bg = "#BAE6FD"
            status_tag = " <span style='background:#0284C7; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px;'>RTP</span>"
        elif st_val.upper() in ("OFF FEET", "NON ATTIVO"):
            name_bg = "#FECACA"
            status_tag = " <span style='background:#DC2626; color:#FFFFFF; font-size:0.60rem; font-weight:800; padding:1px 5px; border-radius:3px; margin-left:4px;'>OFF</span>"
        else:
            name_bg = row_bg

        pct_hml = int(r.get("pct_hml_match", 0))
        pct_hsr = int(r.get("pct_hsr_match", 0))

        if pct_hml > 0:
            if pct_hml < hml_min:
                hml_style = "background:#FEE2E2; color:#B91C1C; font-weight:800;"
            elif pct_hml > hml_max:
                hml_style = "background:#FEF3C7; color:#B45309; font-weight:800;"
            else:
                hml_style = "background:#DCFCE7; color:#15803D; font-weight:800;"
        else:
            hml_style = f"background:{row_bg}; color:#94A3B8;"

        if pct_hsr > 0:
            if pct_hsr < hsr_min:
                hsr_style = "background:#FEE2E2; color:#B91C1C; font-weight:800;"
            elif pct_hsr > hsr_max:
                hsr_style = "background:#FEF3C7; color:#B45309; font-weight:800;"
            else:
                hsr_style = "background:#DCFCE7; color:#15803D; font-weight:800;"
        else:
            hsr_style = f"background:{row_bg}; color:#94A3B8;"

        has_g = bool(r.get("has_gps", True)) and float(r.get("Tempo", 0)) > 0
        vmax_str = f"{r['V_max']:.1f}".replace(".", ",") if has_g else "0,0"
        vpct_disp = int(r["V_max_pct"]) if has_g else 0
        hsr_val = r["HSR_18"] if dept == "Avanti" else r["HSR_20"]

        if not is_day:
            rows_ind += (
                f"<tr style='background:{row_bg}; {top_b}'>"
                f"<td style='position:sticky; left:0; z-index:2; background:{name_bg}; padding:3px 10px; font-weight:600; font-size:0.75rem; color:#0F172A; border-bottom:1px solid #CBD5E1; border-right:1px solid #94A3B8; white-space:nowrap;'>{r['player_name']}{status_tag}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{int(round(float(r['Tempo'])))}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{_fmt_wr(r['Distanza'], has_g)}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{_fmt_wr(r['Power_Events'], has_g)}</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; font-weight:700; text-align:center; border-bottom:1px solid #E2E8F0;'>{_fmt_wr(r['Hml_25'], has_g)}</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {hml_style}'>{pct_hml}%</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; font-weight:700; text-align:center; border-bottom:1px solid #E2E8F0;'>{_fmt_wr(hsr_val, has_g)}</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {hsr_style}'>{pct_hsr}%</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{vmax_str}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{vpct_disp}</td>"
                f"</tr>"
            )
        else:
            rows_ind += (
                f"<tr style='background:{row_bg}; {top_b}'>"
                f"<td style='position:sticky; left:0; z-index:2; background:{name_bg}; padding:3px 10px; font-weight:600; font-size:0.75rem; color:#0F172A; border-bottom:1px solid #CBD5E1; border-right:1px solid #94A3B8; white-space:nowrap;'>{r['player_name']}{status_tag}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['Tempo']}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['Distanza']}</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {hml_style}'>{pct_hml}%</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; font-weight:700; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['Hml_25']}</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; text-align:center; border-bottom:1px solid #E2E8F0; {hsr_style}'>{pct_hsr}%</td>"
                f"<td style='padding:3px 6px; font-size:0.75rem; font-weight:700; text-align:center; border-bottom:1px solid #E2E8F0;'>{hsr_val}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{vmax_str}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{vpct_disp}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['VHml_50']}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['VHSR_25'] if r['VHSR_25'] > 0 else ''}</td>"
                f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #E2E8F0;'>{r['Power_Events']}</td>"
                f"</tr>"
            )

    if not is_day:
        if is_match_workrate:
            th_cols = """
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo (Oval)</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza/min</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power Ev./min</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml/min &gt;25.5W</th>
                <th style="padding:6px 5px; text-align:center; background:#FFF7ED; color:#9A3412; border-bottom:2px solid #EA580C;">% Match HML</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR/min &gt;18\\20</th>
                <th style="padding:6px 5px; text-align:center; background:#FEFCE8; color:#854D0E; border-bottom:2px solid #CA8A04;">% Match HSR</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
            """
        else:
            th_cols = """
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power Ev.</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml &gt;25.5W</th>
                <th style="padding:6px 5px; text-align:center; background:#FFF7ED; color:#9A3412; border-bottom:2px solid #EA580C;">% Match HML</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR &gt;18\\20</th>
                <th style="padding:6px 5px; text-align:center; background:#FEFCE8; color:#854D0E; border-bottom:2px solid #CA8A04;">% Match HSR</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
                <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
            """
    else:
        th_cols = """
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza</th>
            <th style="padding:6px 5px; text-align:center; background:#FFF7ED; color:#9A3412; border-bottom:2px solid #EA580C;">% Match HML</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml &gt;25.5W</th>
            <th style="padding:6px 5px; text-align:center; background:#FEFCE8; color:#854D0E; border-bottom:2px solid #CA8A04;">% Match HSR</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR &gt;18\\20</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHML &gt;50</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHSR &gt;25</th>
            <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power Ev.</th>
        """

    top_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 60%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <div style="font-size:1.08rem; font-weight:800; letter-spacing:0.3px;">{header_title}</div>
                <div style="font-size:0.76rem; color:#BAE6FD;">{header_sub}</div>
            </div>
            <div style="display:flex; gap:8px; align-items:center; font-size:0.72rem; font-weight:700;">
                <span style="background:#DCFCE7; color:#15803D; padding:3px 8px; border-radius:5px;">Verde - TARGET CENTRATO</span>
                <span style="background:#FEE2E2; color:#B91C1C; padding:3px 8px; border-radius:5px;">Rosso - SOTTO IL TARGET</span>
                <span style="background:#FEF3C7; color:#B45309; padding:3px 8px; border-radius:5px;">Giallo - SOPRA IL TARGET</span>
            </div>
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800;">
                    <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; padding:6px 10px; text-align:left; border-bottom:2px solid #0F172A; border-right:1px solid #94A3B8;">Giocatore</th>
                    {th_cols}
                </tr>
            </thead>
            <tbody>{rows_ind}</tbody>
        </table>
    </div>
    """

    # Tabella Medie Ruolo e Reparto per Target
    rows_role = ""
    for _, rr in role_df.iterrows():
        r_dept = rr.get("department", "Avanti")
        hsr_v = rr["HSR_18"] if r_dept == "Avanti" else rr["HSR_20"]
        has_r = float(rr.get("Tempo", 0)) > 0
        rows_role += (
            f"<tr style='background:#BAE6FD; color:#0F172A;'>"
            f"<td style='padding:4px 10px; font-weight:700; font-size:0.74rem; border-bottom:1px solid #7DD3FC;'>{rr['Label']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{_fmt_wr(rr['Distanza'], has_r)}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{_fmt_wr(rr['Hml_25'], has_r)}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{_fmt_wr(hsr_v, has_r)}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{int(round(float(rr['V_max_pct'])))}</td>"
            f"</tr>"
        )
    for _, dr in dept_df.iterrows():
        d_lbl = str(dr["Label"]).upper()
        hsr_v = dr["HSR_18"] if "AVANTI" in d_lbl else dr["HSR_20"]
        has_d = float(dr.get("Tempo", 0)) > 0
        rows_role += (
            f"<tr style='background:#002B49; color:#FFFFFF; font-weight:800; border-top:2px solid #D4AF37;'>"
            f"<td style='padding:6px 10px; font-size:0.78rem; letter-spacing:0.04em;'>{dr['Label']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{_fmt_wr(dr['Distanza'], has_d)}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center; color:#FEF08A;'>{_fmt_wr(dr['Hml_25'], has_d)}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center; color:#FEF08A;'>{_fmt_wr(hsr_v, has_d)}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{int(round(float(dr['V_max_pct'])))}</td>"
            f"</tr>"
        )

    th_dist_role = "Distanza/min" if is_match_workrate else "Distanza"
    th_hml_role = "Hml/min &gt;25.5W" if is_match_workrate else "Hml &gt;25.5W"
    th_hsr_role = "HSR/min &gt;18\\20" if is_match_workrate else "HSR &gt;18\\20"
    role_box_title = (
        "MEDIE WORK RATE (/MIN) PER RUOLO E REPARTO (Minutaggio Oval • Esclusi Modificato, RTP e Off Feet)"
        if is_match_workrate
        else "MEDIE PER RUOLO E REPARTO (Atleti Attivi • Esclusi Modificato, RTP e Off Feet)"
    )

    bot_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; margin-top:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:#002B49; color:#FFFFFF; padding:8px 14px; font-size:0.80rem; font-weight:800; letter-spacing:0.04em;">
            {role_box_title}
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#7DD3FC; color:#031926; font-size:0.68rem; font-weight:800;">
                    <th style="padding:5px 10px; text-align:left; border-bottom:1.5px solid #031926;">Ruolo / Reparto</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">{th_dist_role}</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">{th_hml_role}</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">{th_hsr_role}</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_role}</tbody>
        </table>
    </div>
    """
    return top_html, bot_html


def _build_settimana_23_html(
    df_23: pd.DataFrame,
    role_df: pd.DataFrame,
    dept_df: pd.DataFrame,
    header_title: str,
    header_sub: str,
    role_means_dict: dict,
) -> tuple[str, str]:
    metric_cols = [
        "Tempo", "Distanza", "m_min", "Run_Dist",
        "Hml_25", "Hml_40", "VHml_50", "HSR_18", "HSR_20", "VHSR_25",
        "Power_Events", "V_max", "V_max_pct"
    ]

    rows_ind = ""
    for idx, r in df_23.iterrows():
        j_num = int(r["jersey_number"])
        row_bg = "#FFFFFF" if idx % 2 == 0 else "#F0F9FF"
        starters_border = "border-bottom: 2.5px solid #D97706;" if j_num == 15 else "border-bottom: 1px solid #E2E8F0;"

        j_bg = "#0284C7" if j_num <= 15 else "#D97706"
        j_badge = f"<span style='background:{j_bg}; color:#FFFFFF; font-weight:800; font-size:0.72rem; padding:2px 6px; border-radius:4px;'>{j_num}</span>"

        r_group = str(r.get("role_group", r.get("role", "")))
        r_mean_row = role_means_dict.get(r_group, {})

        cells_td = ""
        for m_col in metric_cols:
            raw_v = float(pd.to_numeric(r.get(m_col, 0), errors="coerce") or 0)
            mean_v = float(pd.to_numeric(r_mean_row.get(m_col, 0), errors="coerce") or 0)

            c_style = f"background:{row_bg}; color:#0F172A;"
            if mean_v > 0 and float(r.get("Tempo", 0)) > 0:
                if raw_v > mean_v * 1.15:
                    c_style = "background:#DCFCE7; color:#15803D; font-weight:800;"
                elif raw_v < mean_v * 0.85:
                    c_style = "background:#FEE2E2; color:#B91C1C; font-weight:800;"

            disp_v = f"{raw_v:.1f}".replace(".", ",") if m_col == "V_max" else str(int(round(raw_v)))
            cells_td += f"<td style='padding:3px 6px; font-size:0.74rem; text-align:center; {starters_border} {c_style}'>{disp_v}</td>"

        rows_ind += (
            f"<tr style='background:{row_bg};'>"
            f"<td style='position:sticky; left:0; z-index:2; background:{row_bg}; padding:3px 8px; font-weight:600; font-size:0.75rem; color:#0F172A; border-right:1px solid #94A3B8; {starters_border} white-space:nowrap;'>{r['player_name']}</td>"
            f"<td style='padding:3px 6px; text-align:center; {starters_border}'>{j_badge}</td>"
            f"{cells_td}"
            f"</tr>"
        )

    top_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:linear-gradient(90deg, #031926 0%, #002B49 60%, #0066B2 100%); color:#FFFFFF; padding:10px 16px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <div style="font-size:1.08rem; font-weight:800; letter-spacing:0.3px;">{header_title}</div>
                <div style="font-size:0.76rem; color:#BAE6FD;">{header_sub}</div>
            </div>
            <div style="display:flex; gap:8px; align-items:center; font-size:0.72rem; font-weight:700;">
                <span style="background:#DCFCE7; color:#15803D; padding:3px 8px; border-radius:5px;">Verde: &gt; +15% rispetto alla media del ruolo</span>
                <span style="background:#FEE2E2; color:#B91C1C; padding:3px 8px; border-radius:5px;">Rosso: &lt; -15% rispetto alla media del ruolo</span>
            </div>
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#F8FAFC; color:#0F172A; font-size:0.68rem; font-weight:800;">
                    <th style="position:sticky; left:0; z-index:4; background:#F8FAFC; padding:6px 10px; text-align:left; border-bottom:2px solid #0F172A; border-right:1px solid #94A3B8;">Giocatore (23 Convocati)</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">N°</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Tempo</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Distanza</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">m\\min</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Run Dist</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml &gt;25W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Hml&gt;40W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHml&gt;50W</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR &gt;18</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">HSR&gt;20</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">VHSR&gt;25</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">Power Ev.</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">V max</th>
                    <th style="padding:6px 5px; text-align:center; border-bottom:2px solid #0F172A;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_ind}</tbody>
        </table>
    </div>
    """

    rows_role = ""
    for _, rr in role_df.iterrows():
        rows_role += (
            f"<tr style='background:#BAE6FD; color:#0F172A;'>"
            f"<td style='padding:4px 10px; font-weight:700; font-size:0.74rem; border-bottom:1px solid #7DD3FC;'>{rr['Label']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Tempo']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Distanza']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['m_min']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Run_Dist']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; font-weight:700; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Hml_25']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Hml_40']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['VHml_50']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['HSR_18']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['HSR_20']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['VHSR_25']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['Power_Events']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['V_max']}</td>"
            f"<td style='padding:4px 6px; font-size:0.74rem; text-align:center; border-bottom:1px solid #7DD3FC;'>{rr['V_max_pct']}</td>"
            f"</tr>"
        )
    for _, dr in dept_df.iterrows():
        rows_role += (
            f"<tr style='background:#002B49; color:#FFFFFF; font-weight:800; border-top:2px solid #D4AF37;'>"
            f"<td style='padding:6px 10px; font-size:0.78rem;'>{dr['Label']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['Tempo']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['Distanza']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['m_min']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['Run_Dist']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center; color:#FEF08A;'>{dr['Hml_25']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['Hml_40']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['VHml_50']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center; color:#FEF08A;'>{dr['HSR_18']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center; color:#FEF08A;'>{dr['HSR_20']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['VHSR_25']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['Power_Events']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['V_max']}</td>"
            f"<td style='padding:6px 6px; font-size:0.78rem; text-align:center;'>{dr['V_max_pct']}</td>"
            f"</tr>"
        )

    bot_html = f"""
    <div style="overflow-x:auto; border:2px solid #0F172A; border-radius:10px; background:#FFFFFF; margin-top:14px; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
        <div style="background:#002B49; color:#FFFFFF; padding:8px 14px; font-size:0.80rem; font-weight:800; letter-spacing:0.04em;">
            MEDIE PER RUOLO E REPARTO — 23 CONVOCATI ALLA GARA
        </div>
        <table style="width:100%; border-collapse:separate; border-spacing:0; font-family:'Inter', sans-serif;">
            <thead>
                <tr style="background:#7DD3FC; color:#031926; font-size:0.68rem; font-weight:800;">
                    <th style="padding:5px 10px; text-align:left; border-bottom:1.5px solid #031926;">Ruolo / Reparto</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Tempo</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Distanza</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">m\\min</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Run Dist</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Hml &gt;25W</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Hml&gt;40W</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">VHml&gt;50W</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">HSR &gt;18</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">HSR&gt;20</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">VHSR&gt;25</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">Power Ev.</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">V max</th>
                    <th style="padding:5px 5px; text-align:center; border-bottom:1.5px solid #031926;">% Vmax</th>
                </tr>
            </thead>
            <tbody>{rows_role}</tbody>
        </table>
    </div>
    """
    return top_html, bot_html


def _render_tab_target_sessione(df_sess: pd.DataFrame, role_sess: pd.DataFrame, dept_sess: pd.DataFrame, meta: dict, status_overrides: dict, target_bundle: dict):
    is_match_wr = bool(target_bundle.get("is_match_workrate", False))
    hml_state_k = "target_match_hml" if is_match_wr else "target_sess_hml"
    hsr_state_k = "target_match_hsr" if is_match_wr else "target_sess_hsr"
    tol_state_k = "target_match_tol" if is_match_wr else "target_sess_tol"

    hml_def = 100 if is_match_wr else 70
    hsr_def = 100 if is_match_wr else 40
    tol_def = 10 if is_match_wr else 5

    # Selettori Target Coaches
    c_t1, c_t2, c_t3 = st.columns([1, 1, 1])
    hml_in = c_t1.number_input("Target HML % MATCH AV:", min_value=10, max_value=250, value=int(st.session_state.get(hml_state_k, hml_def)), step=5, key=f"inp_{hml_state_k}")
    hsr_in = c_t2.number_input("Target HSR % MATCH AV:", min_value=5, max_value=200, value=int(st.session_state.get(hsr_state_k, hsr_def)), step=5, key=f"inp_{hsr_state_k}")
    tol_in = c_t3.number_input("Tolleranza Target % (±):", min_value=1, max_value=25, value=int(st.session_state.get(tol_state_k, tol_def)), step=1, key=f"inp_{tol_state_k}")

    if hml_in != st.session_state.get(hml_state_k, hml_def) or hsr_in != st.session_state.get(hsr_state_k, hsr_def) or tol_in != st.session_state.get(tol_state_k, tol_def):
        st.session_state[hml_state_k] = float(hml_in)
        st.session_state[hsr_state_k] = float(hsr_in)
        st.session_state[tol_state_k] = float(tol_in)
        st.rerun()

    sub_text = (
        f"Analisi Match su Minutaggio Ufficiale Oval (Work Rate /min eccetto V max e % Vmax) • {meta.get('date_disp', meta.get('date_str', ''))} • Benchmark: Match"
        if is_match_wr
        else f"Dati individuali e TARGET • {meta.get('date_disp', meta.get('date_str', ''))} • Benchmark: {meta.get('session_type', meta.get('archetype', ''))}"
    )

    top_html, bot_html = _build_target_report_html(
        target_bundle["df"],
        target_bundle["role_df"],
        target_bundle["dept_df"],
        f"Report Coaches • {meta.get('session_name', '')}",
        sub_text,
        hml_in, hsr_in, tol_in, is_day=False,
        is_match_workrate=is_match_wr,
    )

    _render_safe_html(top_html)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    c_g1, c_g2 = st.columns(2)
    with c_g1:
        st.plotly_chart(target_bundle["fig_hml"], use_container_width=True)
    with c_g2:
        st.plotly_chart(target_bundle["fig_hsr"], use_container_width=True)

    _render_safe_html(bot_html)


def _render_tab_target_giornata(df_day: pd.DataFrame, role_day: pd.DataFrame, dept_day: pd.DataFrame, meta: dict, status_overrides: dict, target_bundle: dict):
    c_t1, c_t2, c_t3 = st.columns([1, 1, 1])
    hml_in = c_t1.number_input("Target HML % MATCH AV (Giornata):", min_value=10, max_value=250, value=int(st.session_state.get("target_day_hml", 60)), step=5, key="inp_target_day_hml")
    hsr_in = c_t2.number_input("Target HSR % MATCH AV (Giornata):", min_value=5, max_value=200, value=int(st.session_state.get("target_day_hsr", 50)), step=5, key="inp_target_day_hsr")
    tol_in = c_t3.number_input("Tolleranza Target % (±):", min_value=1, max_value=25, value=int(st.session_state.get("target_day_tol", 5)), step=1, key="inp_target_day_tol")

    if hml_in != st.session_state.get("target_day_hml") or hsr_in != st.session_state.get("target_day_hsr") or tol_in != st.session_state.get("target_day_tol"):
        st.session_state["target_day_hml"] = float(hml_in)
        st.session_state["target_day_hsr"] = float(hsr_in)
        st.session_state["target_day_tol"] = float(tol_in)
        st.rerun()

    sess_list_str = " • ".join(meta.get("day_sessions_list", []))
    top_html, bot_html = _build_target_report_html(
        target_bundle["df"],
        target_bundle["role_df"],
        target_bundle["dept_df"],
        f"Report TOTALE GIORNATA • {meta.get('date_short', meta.get('date_str', ''))}",
        f"Dati individuali e TARGET Cumulati • Sedute: {sess_list_str}",
        hml_in, hsr_in, tol_in, is_day=True,
    )

    _render_safe_html(top_html)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    c_g1, c_g2 = st.columns(2)
    with c_g1:
        st.plotly_chart(target_bundle["fig_hml"], use_container_width=True)
    with c_g2:
        st.plotly_chart(target_bundle["fig_hsr"], use_container_width=True)

    _render_safe_html(bot_html)


def _render_tab_settimana_23(hist_df: pd.DataFrame, players_df: pd.DataFrame, match_info: dict, meta: dict, bundle_23: dict):
    if "error" in bundle_23:
        st.warning(f"⚠️ {bundle_23['error']}")
        return

    m_info = bundle_23["match_info"]
    top_html, bot_html = _build_settimana_23_html(
        bundle_23["df_23"],
        bundle_23["role_df"],
        bundle_23["dept_df"],
        f"Report Settimana • 23 Convocati — {m_info['match_name']}",
        f"Dati individuali Cumulati • Periodo: {meta.get('week_period_disp', '')} • Gara: {m_info['date_str']}",
        bundle_23["role_means_dict"],
    )

    _render_safe_html(top_html)

    _render_safe_html(bot_html)

    st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)

    # Due grafici individuali ordinati 1-23
    st.plotly_chart(bundle_23["fig_hml_23"], use_container_width=True)
    st.plotly_chart(bundle_23["fig_hsr_23"], use_container_width=True)

    # Box KPI Riassuntivi
    kpis = bundle_23["kpis"]
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:10px; height:100%; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size:0.70rem; font-weight:800; color:#0284C7; text-transform:uppercase; margin-bottom:6px;">
                    🏆 Top % Match HML
                </div>
            """ + "".join([f"<div style='font-size:0.74rem; margin-bottom:3px;'><b>{i+1}. {name}</b>: <span style='color:#0284C7; font-weight:800;'>{val}%</span></div>" for i, (name, val) in enumerate(kpis["top_5_hml"])]) + "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:10px; height:100%; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size:0.70rem; font-weight:800; color:#EF4444; text-transform:uppercase; margin-bottom:6px;">
                    ⚡ Top % Match HSR 18\\20
                </div>
            """ + "".join([f"<div style='font-size:0.74rem; margin-bottom:3px;'><b>{i+1}. {name}</b>: <span style='color:#EF4444; font-weight:800;'>{val}%</span></div>" for i, (name, val) in enumerate(kpis["top_5_hsr"])]) + "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        dh = kpis["dist_hml"]
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:10px; height:100%; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size:0.70rem; font-weight:800; color:#0F172A; text-transform:uppercase; margin-bottom:6px;">
                    📊 Suddivisione % HML
                </div>
                <div style="font-size:0.74rem; margin-bottom:4px;">&bull; Superiore al 200%: <b style="color:#0284C7;">{dh['sup_200']}</b></div>
                <div style="font-size:0.74rem; margin-bottom:4px;">&bull; Tra 100% e 200%: <b style="color:#16A34A;">{dh['tra_100_200']}</b></div>
                <div style="font-size:0.74rem;">&bull; Sotto il 100%: <b style="color:#DC2626;">{dh['sotto_100']}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        dhs = kpis["dist_hsr"]
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:10px; height:100%; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size:0.70rem; font-weight:800; color:#0F172A; text-transform:uppercase; margin-bottom:6px;">
                    📈 Suddivisione % HSR 18\\20
                </div>
                <div style="font-size:0.74rem; margin-bottom:4px;">&bull; Superiore al 200%: <b style="color:#EF4444;">{dhs['sup_200']}</b></div>
                <div style="font-size:0.74rem; margin-bottom:4px;">&bull; Tra 100% e 200%: <b style="color:#16A34A;">{dhs['tra_100_200']}</b></div>
                <div style="font-size:0.74rem;">&bull; Sotto il 100%: <b style="color:#DC2626;">{dhs['sotto_100']}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c5:
        sf = kpis["starters_finishers"]
        st.markdown(
            f"""
            <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:8px; padding:10px; height:100%; box-shadow:0 2px 6px rgba(0,0,0,0.04);">
                <div style="font-size:0.70rem; font-weight:800; color:#D97706; text-transform:uppercase; margin-bottom:6px;">
                    🏉 Starters vs Finishers
                </div>
                <div style="font-size:0.74rem; margin-bottom:3px;"><b>Starters (1-15):</b></div>
                <div style="font-size:0.72rem; color:#64748B; margin-bottom:6px;">HML: <b style="color:#0284C7;">{sf['starters_hml']}%</b> | HSR: <b style="color:#EF4444;">{sf['starters_hsr']}%</b></div>
                <div style="font-size:0.74rem; margin-bottom:3px;"><b>Finishers (16-23):</b></div>
                <div style="font-size:0.72rem; color:#64748B;">HML: <b style="color:#0284C7;">{sf['finishers_hml']}%</b> | HSR: <b style="color:#EF4444;">{sf['finishers_hsr']}%</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_global_camp_and_session_selector(hist_df: pd.DataFrame, active_tab: str = "report_sessione") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, dict]:
    """
    Estrae i dati dal gestore globale senza mostrare menù a tendina ridondanti nella pagina,
    mostrando invece la barra fissa riepilogativa di ciò che è stato selezionato nella barra laterale.
    """
    import global_state

    ctx = global_state.get_current_session_context(hist_df)
    sub_gps_sess = ctx["sub_gps_sess"]
    sub_gps_day = ctx["sub_gps_day"]
    sub_gps_week = ctx["sub_gps_week"]
    camp_players = ctx["camp_players"]
    meta = ctx["meta"]
    match_info = ctx["match_info"]

    # Barra fissa che mostra chiaramente ciò che è stato selezionato nella barra laterale
    view_mode = "match" if active_tab == "campo" else ("settimana_23" if active_tab == "settimana_23" else "session")
    global_state.render_top_context_banner(meta, match_info, view_mode=view_mode)

    return sub_gps_sess, sub_gps_day, sub_gps_week, camp_players, meta, match_info


def _build_pitch_bundle_for_pdf(hist_df: pd.DataFrame, match_info: dict, meta: dict) -> dict:
    """Costruisce il bundle completo per la pagina Trombinoscopio Match nel PDF ufficiale."""
    try:
        match_dt = match_info.get("date_str") if match_info else meta.get("date_str")
        lineup_sum = utils.get_lineup_matches_summary()
        m_row = None
        if not lineup_sum.empty:
            m_sub = lineup_sum[lineup_sum["date_str"] == match_dt]
            m_row = m_sub.iloc[0] if not m_sub.empty else lineup_sum.iloc[0]
        if m_row is None:
            return None

        m_date = str(m_row["date_str"])
        m_name = str(m_row["match_name"])
        dtl = utils.get_match_lineup_detail(m_date)
        starters_df = dtl.get("starters", pd.DataFrame())
        finishers_df = dtl.get("finishers", pd.DataFrame())

        convocati = pd.concat([starters_df, finishers_df], ignore_index=True) if not starters_df.empty or not finishers_df.empty else pd.DataFrame()
        if convocati.empty:
            return None

        oval_df = utils.get_oval_matches_df()
        sub_oval = pd.DataFrame()
        if not oval_df.empty:
            if "match_date" in oval_df.columns:
                sub_oval = oval_df[oval_df["match_date"].astype(str) == str(m_date)].copy()
            if sub_oval.empty and "date" in oval_df.columns:
                sub_oval = oval_df[oval_df["date"].astype(str) == str(m_date)].copy()
        # Estrazione metrica GPS rigorosamente vincolata alla sola seduta indicata nella barra laterale
        target_sess = meta.get("session_name") if meta else None
        if not target_sess:
            target_sess = st.session_state.get("global_selected_session_name")

        match_sess_gps = pd.DataFrame()
        if target_sess and not hist_df.empty and "session_name" in hist_df.columns:
            match_sess_gps = hist_df[(hist_df["date_str"] == str(m_date)) & (hist_df["session_name"] == str(target_sess))].copy()

        if match_sess_gps.empty and not hist_df.empty:
            cand = hist_df[(hist_df["date_str"] == str(m_date)) & (hist_df["session_name"].astype(str).str.lower().str.contains("match"))]
            if not cand.empty:
                match_sess_gps = cand.copy()
            else:
                day_all = hist_df[hist_df["date_str"] == str(m_date)]
                if not day_all.empty:
                    top_s = day_all["session_name"].value_counts().index[0]
                    match_sess_gps = day_all[day_all["session_name"] == top_s].copy()
                else:
                    match_sess_gps = pd.DataFrame()

        day_gps = match_sess_gps

        player_stats = {}
        for _, r in convocati.iterrows():
            pn = str(r.get("player_name", "")).strip()
            jn = int(r.get("jersey_number", 0))
            role = str(r.get("role", "")).strip()
            dept = utils.get_player_department(pn, role, jn)

            m_oval = None
            cic_val = 0.0
            tck_val = 0.0
            rck_val = 0.0
            if not sub_oval.empty:
                mr = pd.DataFrame()
                if "fir_player_name" in sub_oval.columns:
                    mr = sub_oval[sub_oval["fir_player_name"].astype(str).str.strip().str.upper() == pn.upper()]
                if mr.empty and "playerFullName" in sub_oval.columns:
                    mr = sub_oval[sub_oval["playerFullName"].astype(str).str.strip().str.upper() == pn.upper()]
                if mr.empty:
                    j_col_ov = "Jersey" if "Jersey" in sub_oval.columns else ("JERSEY" if "JERSEY" in sub_oval.columns else None)
                    if j_col_ov and jn > 0:
                        mr = sub_oval[pd.to_numeric(sub_oval[j_col_ov], errors="coerce") == jn]
                if not mr.empty:
                    r0_ov = mr.iloc[0]
                    if pd.notna(r0_ov.get("Min")):
                        m_oval = float(pd.to_numeric(r0_ov.get("Min"), errors="coerce") or 0.0)
                    cic_v = pd.to_numeric(r0_ov.get("TotalCarriesInContact"), errors="coerce")
                    tck_v = pd.to_numeric(r0_ov.get("TotalTackleAttempts"), errors="coerce")
                    rck_v = pd.to_numeric(r0_ov.get("TotalEffectiveRuckEntries"), errors="coerce")
                    cic_val = float(cic_v) if pd.notna(cic_v) else 0.0
                    tck_val = float(tck_v) if pd.notna(tck_v) else 0.0
                    rck_val = float(rck_v) if pd.notna(rck_v) else 0.0

            pg = day_gps[day_gps["player_name"].astype(str).str.strip().str.upper() == pn.upper()] if not day_gps.empty else pd.DataFrame()
            if not pg.empty:
                dur = float(pd.to_numeric(pg.get("duration", 0), errors="coerce").fillna(0).mean())
                pos = float(pd.to_numeric(pg.get("v_max", 0), errors="coerce").fillna(0).max())
                dt = float(pd.to_numeric(pg.get("distance_m", 0), errors="coerce").fillna(0).sum())
                sp06 = float(pd.to_numeric(pg.get("speed_0_6", 0), errors="coerce").fillna(0).sum())
                dc = max(0.0, dt - sp06)
                hml = float(pd.to_numeric(pg.get("mp_25_35", 0), errors="coerce").fillna(0).sum() + pd.to_numeric(pg.get("mp_35_50", 0), errors="coerce").fillna(0).sum() + pd.to_numeric(pg.get("mp_50_100", 0), errors="coerce").fillna(0).sum())
                vhml = float(pd.to_numeric(pg.get("mp_50_100", 0), errors="coerce").fillna(0).sum())
                sp18 = float(pd.to_numeric(pg.get("speed_18_20", 0), errors="coerce").fillna(0).sum())
                sp20 = float(pd.to_numeric(pg.get("speed_20_25", 0), errors="coerce").fillna(0).sum())
                sp25 = float(pd.to_numeric(pg.get("speed_25_72", 0), errors="coerce").fillna(0).sum())
                hsr = (sp18 + sp20 + sp25) if dept == "Avanti" else (sp20 + sp25)
                m_eff = m_oval if (m_oval is not None and m_oval > 0) else min(80.0, dur)
            else:
                m_eff = m_oval if (m_oval is not None and m_oval > 0) else 0.0
                pos = dt = dc = hml = vhml = hsr = 0.0

            player_stats[pn] = {
                "minutes": m_eff,
                "PoS": pos,
                "DT": dt,
                "DC": dc,
                "Hml": hml,
                "VHml": vhml,
                "HSR": hsr,
                "CIC": cic_val,
                "TCK": tck_val,
                "RCK": rck_val,
            }

        rep_avgs = {"Avanti": {}, "TreQuarti": {}}
        for dk in ["Avanti", "TreQuarti"]:
            p_dk = [r["player_name"] for _, r in convocati.iterrows() if utils.get_player_department(r.get("player_name"), r.get("role", ""), r.get("jersey_number", 0)) == dk]
            divisor = 8.0 if dk == "Avanti" else 7.0
            tot_dt = sum(player_stats.get(p, {}).get("DT", 0.0) for p in p_dk)
            tot_dc = sum(player_stats.get(p, {}).get("DC", 0.0) for p in p_dk)
            tot_hml = sum(player_stats.get(p, {}).get("Hml", 0.0) for p in p_dk)
            tot_vhml = sum(player_stats.get(p, {}).get("VHml", 0.0) for p in p_dk)
            tot_hsr = sum(player_stats.get(p, {}).get("HSR", 0.0) for p in p_dk)
            tot_cic = sum(player_stats.get(p, {}).get("CIC", 0.0) for p in p_dk)
            tot_tck = sum(player_stats.get(p, {}).get("TCK", 0.0) for p in p_dk)
            tot_rck = sum(player_stats.get(p, {}).get("RCK", 0.0) for p in p_dk)
            tot_min = sum(player_stats.get(p, {}).get("minutes", 0.0) for p in p_dk)
            max_pos = max([player_stats.get(p, {}).get("PoS", 0.0) for p in p_dk] or [0.0])

            rep_avgs[dk] = {
                "n_players": len(p_dk),
                "count": len(p_dk),
                "divisor": int(divisor),
                "DT": tot_dt / divisor,
                "DC": tot_dc / divisor,
                "Hml": tot_hml / divisor,
                "VHml": tot_vhml / divisor,
                "HSR": tot_hsr / divisor,
                "PoS": max_pos,
                "CIC": tot_cic / divisor,
                "TCK": tot_tck / divisor,
                "RCK": tot_rck / divisor,
                "minutes": tot_min / divisor,
            }

        return {
            "match_name": m_name,
            "date_str": m_date,
            "starters_df": starters_df,
            "finishers_df": finishers_df,
            "player_stats": player_stats,
            "rep_averages": rep_avgs,
        }
    except Exception:
        return None


def render_home(t: dict):
    render_analisi_sessione_giornata(t)


def render_analisi_sessione_giornata(t: dict):
    render_page_header(
        "Analisi GPS Sessione & Giornata FIR",
        "Report Allenamento • Report Sessione • Istogramma • Target Sessione • Densità HML & HSR • Trombinoscopio • Report Giornata • Target Giornata • Report Franchigie DAY • Scheda Giocatori",
        "bi-stopwatch-fill",
    )

    cards_sessione = [
        {"id": "story", "title": "Report Allenamento & Storytelling", "desc": "Analisi narrativa seduta, attainment & rankings", "icon": "bi-mic-fill"},
        {"id": "report_sessione", "title": "Report Sessione", "desc": "Tabella analitica seduta e volumi staff", "icon": "bi-table"},
        {"id": "istogramma", "title": "Istogramma", "desc": "Grafico individuale HML >25W per atleta", "icon": "bi-bar-chart-steps"},
        {"id": "target_sessione", "title": "Target Sessione", "desc": "Verifica target % Match con semafori seduta", "icon": "bi-bullseye"},
        {"id": "densita_hml_hsr", "title": "Densità HML & HSR", "desc": "Work rate al minuto da gara (HML/min e HSR/min)", "icon": "bi-lightning-charge-fill"},
        {"id": "campo", "title": "Trombinoscopio", "desc": "Schieramento campo 1-15 e panchina 16-23", "icon": "bi-diagram-3-fill"},
        {"id": "report_giornata", "title": "Report Giornata", "desc": "Cumulato giornaliero di tutte le sedute", "icon": "bi-calendar2-day-fill"},
        {"id": "target_giornata", "title": "Target Giornata", "desc": "Target % Match cumulato sul giorno", "icon": "bi-calendar-check-fill"},
        {"id": "franchigie_day", "title": "Report Franchigie DAY", "desc": "Carico giornaliero atleti Club Benetton & Zebre", "icon": "bi-building"},
        {"id": "scheda_giocatori", "title": "Scheda Giocatori", "desc": "Dati individuali neutrali per stampa e staff", "icon": "bi-person-vcard-fill"},
    ]

    active_tab = render_navigation_cards("analisi_sessione_giornata", cards_sessione)

    # Se l'utente ha selezionato Report Franchigie DAY delega direttamente alla vista franchigie
    if active_tab == "franchigie_day":
        import views.report_6weeks
        views.report_6weeks._render_tab_franchige_day(t)
        return

    hist_df = utils.get_gps_history_df("nazionale")
    if hist_df.empty:
        hist_df = utils.get_gps_history_df("all")
    players_df = utils.get_players_df()

    if hist_df.empty:
        st.info("Nessuna sessione GPS presente nel database.")
        return

    # Barra fissa sincronizzata con la selezione globale nella barra laterale
    sub_gps_sess, sub_gps_day, sub_gps_week, camp_players, meta, match_info = _render_global_camp_and_session_selector(hist_df, active_tab=active_tab)

    if "session_status_overrides" not in st.session_state:
        st.session_state["session_status_overrides"] = {}
    sess_key = f"{meta['date_str']}_{meta['session_name']}"
    saved_statuses = utils.get_session_player_statuses().get(sess_key, {})
    status_overrides = {**saved_statuses, **st.session_state["session_status_overrides"].get(sess_key, {})}

    # Prepara i dataset necessari
    df_sess = _prepare_session_camp_dataframe(sub_gps_sess, camp_players, players_df, status_overrides, sum_m_per_min=False)
    role_sess, dept_sess = _compute_role_and_dept_averages(df_sess)

    df_day = _prepare_session_camp_dataframe(sub_gps_day, camp_players, players_df, status_overrides, sum_m_per_min=True)
    df_day = _compute_match_pct_columns(df_day, bench_source=st.session_state.get("match_bench_source", "excel"))
    role_day, dept_day = _compute_role_and_dept_averages(df_day)

    df_week = _prepare_session_camp_dataframe(sub_gps_week, camp_players, players_df, status_overrides, sum_m_per_min=True)
    df_week = _compute_match_pct_columns(df_week, bench_source=st.session_state.get("match_bench_source", "excel"))
    role_week, dept_week = _compute_role_and_dept_averages(df_week)

    fw_dept_row = dept_sess[dept_sess["department"] == "Avanti"].iloc[0].to_dict() if not dept_sess[dept_sess["department"] == "Avanti"].empty else {}
    bk_dept_row = dept_sess[dept_sess["department"] == "TreQuarti"].iloc[0].to_dict() if not dept_sess[dept_sess["department"] == "TreQuarti"].empty else {}

    sess_bundle = {
        "df": df_sess,
        "role_df": role_sess,
        "dept_df": dept_sess,
        "fig": _build_training_attainment_chart(dept_sess, meta["archetype"]),
        "fig_hist_fw": _build_individual_histogram_figure(df_sess, fw_dept_row, "Avanti", meta["archetype"], sort_col="Hml_25"),
        "fig_hist_bk": _build_individual_histogram_figure(df_sess, bk_dept_row, "TreQuarti", meta["archetype"], sort_col="Hml_25"),
    }
    day_bundle = {
        "df": df_day,
        "role_df": role_day,
        "dept_df": dept_day,
        "date_short": meta["date_short"],
        "sessions_list": meta["day_sessions_list"],
        "fig_match_pct": _build_match_pct_figure(df_day, chart_style="dual_ranking", is_weekly=False),
    }
    week_bundle = {
        "df": df_week,
        "role_df": role_week,
        "dept_df": dept_week,
        "period_str": meta["week_period_disp"],
        "competition": meta["week_competition"],
        "week_name": meta["week_name"],
        "fig_match_pct": _build_match_pct_figure(df_week, chart_style="dual_ranking", is_weekly=True),
    }

    from views.report_comparazione import _build_department_comparison_barchart, build_session_narrative_dict, build_fir_typologies_bundle, build_multisession_comparison_bundle
    comp_base = SESSION_TYPE_BASELINES.get(meta.get("session_type", meta.get("archetype", "Velocità")), SESSION_TYPE_BASELINES["Velocità"])
    av_c = dept_sess[dept_sess["department"] == "Avanti"].iloc[0].to_dict() if not dept_sess[dept_sess["department"] == "Avanti"].empty else {}
    tq_c = dept_sess[dept_sess["department"] == "TreQuarti"].iloc[0].to_dict() if not dept_sess[dept_sess["department"] == "TreQuarti"].empty else {}
    fig_av_comp = _build_department_comparison_barchart(
        "AVANTI",
        {"Dist": float(av_c.get("Distanza", 0)), "Run": float(av_c.get("Run_Dist", 0)), "Hml": float(av_c.get("Hml_25", 0)), "HSR": float(av_c.get("HSR_18", 0))},
        {"Dist": comp_base["Avanti"]["distance_m"], "Run": comp_base["Avanti"]["run_dist"], "Hml": comp_base["Avanti"]["hml"], "HSR": comp_base["Avanti"]["hsr"]},
        "HSR >18", "#0066B2", "#94A3B8", meta.get("session_type", meta["archetype"])
    )
    fig_tq_comp = _build_department_comparison_barchart(
        "TREQUARTI",
        {"Dist": float(tq_c.get("Distanza", 0)), "Run": float(tq_c.get("Run_Dist", 0)), "Hml": float(tq_c.get("Hml_25", 0)), "HSR": float(tq_c.get("HSR_20", 0))},
        {"Dist": comp_base["TreQuarti"]["distance_m"], "Run": comp_base["TreQuarti"]["run_dist"], "Hml": comp_base["TreQuarti"]["hml"], "HSR": comp_base["TreQuarti"]["hsr"]},
        "HSR >20", "#D97706", "#94A3B8", meta.get("session_type", meta["archetype"])
    )

    tq_sub = df_sess[df_sess["department"] == "TreQuarti"]
    av_sub = df_sess[df_sess["department"] == "Avanti"]
    rankings_dict = {
        "top_hml_tq": tq_sub.sort_values("Hml_25", ascending=False).head(5)[["player_name", "Hml_25"]].values.tolist(),
        "top_hml_av": av_sub.sort_values("Hml_25", ascending=False).head(5)[["player_name", "Hml_25"]].values.tolist(),
        "top_hsr_tq": tq_sub.sort_values("HSR_20", ascending=False).head(5)[["player_name", "HSR_20"]].values.tolist(),
        "top_hsr_av": av_sub.sort_values("HSR_18", ascending=False).head(5)[["player_name", "HSR_18"]].values.tolist(),
        "top_vmax_tq": tq_sub.sort_values("V_max", ascending=False).head(5)[["player_name", "V_max"]].values.tolist(),
        "top_vmax_av": av_sub.sort_values("V_max", ascending=False).head(5)[["player_name", "V_max"]].values.tolist(),
        "top_vhml_tq": tq_sub.sort_values("VHml_50", ascending=False).head(5)[["player_name", "VHml_50"]].values.tolist(),
        "top_vhml_av": av_sub.sort_values("Hml_40", ascending=False).head(5)[["player_name", "Hml_40"]].values.tolist(),
        "top_vhsr_tq": tq_sub.sort_values("VHSR_25", ascending=False).head(5)[["player_name", "VHSR_25"]].values.tolist(),
        "top_pev_av": av_sub.sort_values("Power_Events", ascending=False).head(5)[["player_name", "Power_Events"]].values.tolist(),
    }

    cur_t = meta.get("session_type", meta.get("archetype", "Velocità"))
    sess_narrative = build_session_narrative_dict(
        sess_df=df_sess,
        cur_type=cur_t,
        status_map={sess_key: status_overrides},
        meta=meta,
        df_full=hist_df,
    )
    comp_bundle = {
        "fig_av": fig_av_comp,
        "fig_tq": fig_tq_comp,
        "rankings": rankings_dict,
        "narrative": sess_narrative,
    }

    pitch_bundle = _build_pitch_bundle_for_pdf(hist_df, match_info, meta)
    types_map_active = utils.get_fir_session_types()
    typologies_bundle = build_fir_typologies_bundle(hist_df, players_df, types_map_active)
    multisess_bundle = build_multisession_comparison_bundle(hist_df, status_overrides)

    is_match_sess_active = str(meta.get("session_type", meta.get("archetype", ""))).strip().lower() == "match"
    if is_match_sess_active:
        target_sess_hml = float(st.session_state.get("target_match_hml", 100.0))
        target_sess_hsr = float(st.session_state.get("target_match_hsr", 100.0))
        target_sess_tol = float(st.session_state.get("target_match_tol", 10.0))
    else:
        target_sess_hml = float(st.session_state.get("target_sess_hml", 70.0))
        target_sess_hsr = float(st.session_state.get("target_sess_hsr", 40.0))
        target_sess_tol = float(st.session_state.get("target_sess_tol", 5.0))
    target_sess_bundle = build_target_analysis_bundle(
        df_sess, target_sess_hml, target_sess_hsr, target_sess_tol, is_day=False, meta=meta
    )

    target_day_hml = float(st.session_state.get("target_day_hml", 60.0))
    target_day_hsr = float(st.session_state.get("target_day_hsr", 50.0))
    target_day_tol = float(st.session_state.get("target_day_tol", 5.0))
    target_day_bundle = build_target_analysis_bundle(
        df_day, target_day_hml, target_day_hsr, target_day_tol, is_day=True, meta=meta
    )

    settimana_23_bundle = build_settimana_23_bundle(hist_df, players_df, match_info, meta)

    pdf_options_map = {
        "Pacchetto Completo Sessione & Giornata (Tutte le Pagine)": "Tutte",
        "1. Solo Report Sessione (Dati Individuali + Analisi Staff)": "Sessione",
        "2. Solo Report Allenamento & Storytelling (Dati Collettivi)": "Report Generale",
        "3. Solo Istogramma Individuale": "Istogramma",
        "4. Solo Target Sessione (% Match 80')": "Target_Sessione",
        "5. Solo Densità da Gara (HML/min & HSR/min)": "Densita",
        "6. Solo Trombinoscopio Match (1-23 Campo & Panchina)": "Schieramento",
        "7. Solo Report Giornata (% Match 80')": "Giornata",
        "8. Solo Target Giornata (% Match 80')": "Target_Giornata",
        "9. Solo Scheda Giocatori (Dati Individuali Neutri)": "Scheda_Giocatori",
    }

    if active_tab == "campo":
        meta_bar_items = [
            ("GARA UFFICIALE", f"{match_info['date_str']} • {match_info['match_name']}"),
            ("COMPETIZIONE", match_info["competition"]),
            ("FORMAZIONE", "1–15 Titolari + 16–23 Finishers"),
            ("DATI MATCH", "Minutaggi Oval & Dati GPExe"),
        ]
    else:
        meta_bar_items = [
            ("RADUNO", f"{meta['week_name']} ({len(df_sess)} atleti)"),
            ("PERIODO SETTIMANA", meta["week_period_disp"]),
            ("GIORNATA / SEDUTA", f"{meta['date_short']} • {meta['session_name']}"),
            ("SEDUTE GIORNATA", f"{len(meta['day_sessions_list'])} ({', '.join(meta['day_sessions_list'])})"),
        ]

    hide_zero_players = st.session_state.get("chk_scheda_giocatori_only_active", False)
    sess_bundle["df_players_sheet"] = df_sess[df_sess["Tempo"] > 0].reset_index(drop=True) if hide_zero_players else df_sess

    render_action_bar(
        meta_items=meta_bar_items,
        pdf_options=pdf_options_map,
        pdf_key="fir_cruscotto_sessione_pdf",
        generate_fn=lambda codice_sub: crea_pdf_cruscotto_fir(
            codice_sub, meta, sess_bundle, day_bundle, week_bundle,
            comp_bundle=comp_bundle, pitch_bundle=pitch_bundle,
            multisess_bundle=multisess_bundle, typologies_bundle=typologies_bundle,
            target_sess_bundle=target_sess_bundle, target_day_bundle=target_day_bundle,
            settimana_23_bundle=settimana_23_bundle,
        ),
        filename_fn=lambda codice_sub: f"FIR_Report_{codice_sub}_{slugify_name(meta['session_name'])}_{meta['date_str']}.pdf",
    )

    if active_tab == "story":
        import views.report_comparazione
        types_map = utils.get_fir_session_types()
        status_map = utils.get_session_player_statuses()
        df_full = views.report_comparazione._prepare_fir_data_with_metrics(hist_df, players_df, types_map)
        ctx = global_state.get_current_session_context(df_full)
        views.report_comparazione._render_tab_report_seduta_story(df_full, status_map, types_map, ctx, t)
    elif active_tab == "report_sessione":
        _render_tab_report_sessione(df_sess, role_sess, dept_sess, meta, sess_key, status_overrides, sess_bundle["fig"])
    elif active_tab == "istogramma":
        _render_tab_istogramma(df_sess, dept_sess, meta)
    elif active_tab == "target_sessione":
        _render_tab_target_sessione(df_sess, role_sess, dept_sess, meta, status_overrides, target_sess_bundle)
    elif active_tab == "densita_hml_hsr":
        import views.report_comparazione
        types_map = utils.get_fir_session_types()
        status_map = utils.get_session_player_statuses()
        df_full = views.report_comparazione._prepare_fir_data_with_metrics(hist_df, players_df, types_map)
        ctx = global_state.get_current_session_context(df_full)
        views.report_comparazione._render_tab_densita_gara(df_full, players_df, status_map, ctx)
    elif active_tab == "campo":
        _render_tab_campo(hist_df, players_df, t, match_info=match_info, meta=meta)
    elif active_tab == "report_giornata":
        _render_tab_report_giornata_or_settimana(df_day, role_day, dept_day, meta, is_weekly=False)
    elif active_tab == "target_giornata":
        _render_tab_target_giornata(df_day, role_day, dept_day, meta, status_overrides, target_day_bundle)
    elif active_tab == "scheda_giocatori":
        _render_tab_scheda_giocatori(df_sess, meta, sess_bundle, day_bundle, week_bundle)


def render_analisi_settimana(t: dict):
    render_page_header(
        "Analisi GPS Settimana & Carichi Raduno FIR",
        "Report Settimana • 23 Convocati • Semaforo Vmax • Report Franchigie • Report 6 Weeks GPS • Report 6/12 Weeks Minuti",
        "bi-calendar-range-fill",
    )

    cards_settimana = [
        {"id": "report_settimana", "title": "Report Settimana", "desc": "Carico cumulato settimanale del Raduno e % Match", "icon": "bi-calendar-week-fill"},
        {"id": "settimana_23", "title": "23 Convocati Settimana", "desc": "Monitoraggio esclusivo dei 23 a referto gara", "icon": "bi-people-fill"},
        {"id": "semaforo_vmax", "title": "Semaforo Vmax", "desc": "Esposizione alta velocità e prevenzione hamstring", "icon": "bi-speedometer2"},
        {"id": "franchigie_day_w", "title": "Report Franchigie Day", "desc": "Carico giornaliero atleti Club Benetton / Zebre", "icon": "bi-building"},
        {"id": "report_6weeks_gps", "title": "Report 6 Weeks GPS", "desc": "Carichi GPS 6 settimane a ritroso, ACWR acuto/cronico e Vmax", "icon": "bi-bar-chart-steps"},
        {"id": "report_12weeks_minuti", "title": "Report 6/12 Weeks Minuti", "desc": "Matrice minutaggio 12 settimane Oval, gare e presenze G.I.N.", "icon": "bi-grid-3x3-gap-fill"},
    ]

    active_tab = render_navigation_cards("analisi_settimana", cards_settimana)

    if active_tab == "franchigie_day_w":
        import views.report_6weeks
        views.report_6weeks._render_tab_franchige_day(t)
        return
    elif active_tab in ("report_6weeks_gps", "report_6weeks"):
        import views.report_6weeks
        views.report_6weeks._render_tab_report_6weeks(t)
        return
    elif active_tab in ("report_12weeks_minuti", "report_gin"):
        import views.oval_match
        df_oval = utils.get_oval_matches_df()
        views.oval_match._render_tab_report_gin(df_oval)
        return

    hist_df = utils.get_gps_history_df("nazionale")
    if hist_df.empty:
        hist_df = utils.get_gps_history_df("all")
    players_df = utils.get_players_df()

    if hist_df.empty:
        st.info("Nessuna sessione GPS presente nel database.")
        return

    sub_gps_sess, sub_gps_day, sub_gps_week, camp_players, meta, match_info = _render_global_camp_and_session_selector(hist_df, active_tab=active_tab)

    if "session_status_overrides" not in st.session_state:
        st.session_state["session_status_overrides"] = {}
    sess_key = f"{meta['date_str']}_{meta['session_name']}"
    saved_statuses = utils.get_session_player_statuses().get(sess_key, {})
    status_overrides = {**saved_statuses, **st.session_state["session_status_overrides"].get(sess_key, {})}

    df_sess = _prepare_session_camp_dataframe(sub_gps_sess, camp_players, players_df, status_overrides, sum_m_per_min=False)
    role_sess, dept_sess = _compute_role_and_dept_averages(df_sess)

    df_day = _prepare_session_camp_dataframe(sub_gps_day, camp_players, players_df, status_overrides, sum_m_per_min=True)
    df_day = _compute_match_pct_columns(df_day, bench_source=st.session_state.get("match_bench_source", "excel"))
    role_day, dept_day = _compute_role_and_dept_averages(df_day)

    df_week = _prepare_session_camp_dataframe(sub_gps_week, camp_players, players_df, status_overrides, sum_m_per_min=True)
    df_week = _compute_match_pct_columns(df_week, bench_source=st.session_state.get("match_bench_source", "excel"))
    role_week, dept_week = _compute_role_and_dept_averages(df_week)

    settimana_23_bundle = build_settimana_23_bundle(hist_df, players_df, match_info, meta)

    week_bundle = {
        "df": df_week,
        "role_df": role_week,
        "dept_df": dept_week,
        "period_str": meta["week_period_disp"],
        "competition": meta["week_competition"],
        "week_name": meta["week_name"],
        "fig_match_pct": _build_match_pct_figure(df_week, chart_style="dual_ranking", is_weekly=True),
    }
    sess_bundle = {"df": df_sess, "role_df": role_sess, "dept_df": dept_sess, "fig": None}
    day_bundle = {"df": df_day, "role_df": role_day, "dept_df": dept_day, "date_short": meta["date_short"]}

    pdf_options_week = {
        "Pacchetto Completo Settimana (Tutte le Pagine del Raduno)": "Tutte_Settimana",
        "1. Solo Report Settimana (Dati Individuali & % Match 80')": "Settimana",
        "2. Solo 23 Convocati Settimana (Monitoraggio Referto Gara & KPI)": "Settimana_23",
        "3. Solo Semaforo Vmax (Esposizione Alta Velocità & Hamstring)": "Semaforo_Vmax",
    }

    render_action_bar(
        meta_items=[
            ("RADUNO", f"{meta['week_name']} ({len(df_week)} atleti)"),
            ("PERIODO SETTIMANA", meta["week_period_disp"]),
            ("COMPETIZIONE", meta["week_competition"]),
            ("PARTITA RIFERIMENTO", f"{match_info.get('date_str', '')} • {match_info.get('match_name', 'Gara')}" if match_info else "Nessuna gara vincolata"),
        ],
        pdf_options=pdf_options_week,
        pdf_key="fir_cruscotto_settimana_pdf",
        generate_fn=lambda codice_sub: crea_pdf_cruscotto_fir(
            codice_sub, meta, sess_bundle, day_bundle, week_bundle,
            settimana_23_bundle=settimana_23_bundle,
        ),
        filename_fn=lambda codice_sub: f"FIR_Settimana_{codice_sub}_{slugify_name(meta['week_name'])}_{meta['date_str']}.pdf",
    )

    if active_tab == "semaforo_vmax":
        import views.report_comparazione
        types_map = utils.get_fir_session_types()
        df_full = views.report_comparazione._prepare_fir_data_with_metrics(hist_df, players_df, types_map)
        ctx = global_state.get_current_session_context(df_full)
        views.report_comparazione._render_tab_semaforo_vmax(df_full, players_df, ctx)
    elif active_tab == "settimana_23":
        _render_tab_settimana_23(hist_df, players_df, match_info, meta, settimana_23_bundle)
    else:
        _render_tab_report_giornata_or_settimana(df_week, role_week, dept_week, meta, is_weekly=True)


def _render_tab_scheda_giocatori(df_sess: pd.DataFrame, meta: dict, sess_bundle: dict, day_bundle: dict, week_bundle: dict):
    c_opt, c_btn = st.columns([2.4, 1.6])
    with c_opt:
        only_active = st.checkbox(
            "Nascondi giocatori con 0 minuti nella seduta (mostra solo atleti scesi in campo)",
            value=False,
            key="chk_scheda_giocatori_only_active",
        )
    df_view = df_sess[df_sess["Tempo"] > 0].reset_index(drop=True) if only_active else df_sess
    sess_bundle["df_players_sheet"] = df_view

    with c_btn:
        pdf_bytes = crea_pdf_cruscotto_fir(
            "Scheda_Giocatori", meta, sess_bundle, day_bundle, week_bundle
        )
        fname = f"FIR_Scheda_Giocatori_{slugify_name(meta['session_name'])}_{meta['date_str']}.pdf"
        st.download_button(
            label="📄 Scarica PDF Scheda Dati Giocatori (Senza Colori)",
            data=pdf_bytes,
            file_name=fname,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
            key="btn_dl_pdf_scheda_giocatori_direct",
        )

    neutral_html = _build_player_sheet_neutral_html(
        df_view,
        f"Scheda Dati Giocatori — {meta['session_name']}",
        f"Data: {meta['date_short']} • Raduno: {meta['week_name']} ({meta['week_competition']})",
    )
    _render_safe_html(neutral_html)


def _render_tab_report_sessione(df_sess: pd.DataFrame, role_df: pd.DataFrame, dept_df: pd.DataFrame, meta: dict, sess_key: str, status_overrides: dict, fig_att: go.Figure):
    with st.expander("⚙️ Gestione Stato Giocatori (Modificato Giallo • RTP Celeste • Full) & Opzioni Visive", expanded=False):
        col_m1, col_m2, col_m3, col_m4 = st.columns([2.0, 1.4, 1.1, 1.3])
        sel_players = col_m1.multiselect(
            "Seleziona Atleti da aggiornare:",
            df_sess["player_name"].tolist(),
            key="st_multi_players",
            placeholder="Scegli uno o più giocatori...",
        )
        sel_st_label = col_m2.selectbox(
            "Assegna Stato:",
            ["Modificato (Giallo • Escluso da Medie)", "RTP (Celeste • Escluso da Medie)", "Full (Normale • Incluso in Medie)", "Off Feet (Non Attivo)"],
            key="st_sel_val",
        )
        st_clean = "Modificato" if "Modificato" in sel_st_label else ("RTP" if "RTP" in sel_st_label else ("Off Feet" if "Off Feet" in sel_st_label else "Full"))

        if col_m3.button("Salva Stato", type="primary", use_container_width=True, key="btn_apply_st_ovr"):
            if sel_players:
                updates = {p: st_clean for p in sel_players}
                utils.set_bulk_player_status_in_session(meta["date_str"], meta["session_name"], updates)
                st.session_state["session_status_overrides"][sess_key] = {**status_overrides, **updates}
                st.success(f"Aggiornati {len(sel_players)} atleti a '{st_clean}' (salvato persistentemente)!")
                st.rerun()
            else:
                st.warning("Seleziona almeno un atleta dalla lista.")

        if col_m4.button("Ripristina a Full", type="secondary", use_container_width=True, key="btn_reset_all_full"):
            all_full = {p: "Full" for p in df_sess["player_name"].tolist()}
            utils.set_bulk_player_status_in_session(meta["date_str"], meta["session_name"], all_full)
            st.session_state["session_status_overrides"][sess_key] = all_full
            st.success("Tutti gli atleti della seduta ripristinati a 'Full'!")
            st.rerun()

        # Visualizzazione badge riassunto atleti con stato speciale
        mod_atleti = [p for p, s in status_overrides.items() if s in ("Modificato", "Modified")]
        rtp_atleti = [p for p, s in status_overrides.items() if s == "RTP"]
        off_atleti = [p for p, s in status_overrides.items() if s == "Off Feet"]

        c_badge1, c_badge2 = st.columns([3.0, 1.0])
        with c_badge1:
            if mod_atleti or rtp_atleti or off_atleti:
                html_badges = "<div style='display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-top:6px; font-size:0.75rem;'>"
                if mod_atleti:
                    html_badges += f"<span style='background:#FEF08A; color:#713F12; font-weight:800; padding:2px 8px; border-radius:4px; border:1px solid #CA8A04;'>🟡 MODIFICATO ({len(mod_atleti)}): {', '.join(mod_atleti)}</span>"
                if rtp_atleti:
                    html_badges += f"<span style='background:#BAE6FD; color:#0369A1; font-weight:800; padding:2px 8px; border-radius:4px; border:1px solid #0284C7;'>🔵 RTP ({len(rtp_atleti)}): {', '.join(rtp_atleti)}</span>"
                if off_atleti:
                    html_badges += f"<span style='background:#FECACA; color:#991B1B; font-weight:800; padding:2px 8px; border-radius:4px; border:1px solid #DC2626;'>🔴 OFF FEET ({len(off_atleti)}): {', '.join(off_atleti)}</span>"
                html_badges += "</div>"
                st.markdown(html_badges, unsafe_allow_html=True)
            else:
                st.markdown("<div style='font-size:0.75rem; color:#64748B; margin-top:4px;'>Tutti i convocati sono attualmente in stato <b>Full (Normale)</b> e inclusi nelle medie.</div>", unsafe_allow_html=True)
        with c_badge2:
            highlight_vmax = st.checkbox("Evidenzia Vmax ≥ 90%", value=True, key="chk_hl_vmax90")

    top_html, bot_html = _build_session_report_html(
        df_sess,
        role_df,
        dept_df,
        f"Report Sessione — Dati Individuali ({meta['session_name']})",
        f"Data: {meta['date_short']} • Raduno: {meta['week_name']} ({meta['week_competition']})",
        highlight_vmax90=st.session_state.get("chk_hl_vmax90", True),
        show_tempo_in_role_table=True,
    )

    _render_safe_html(top_html)
    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
    st.plotly_chart(fig_att, use_container_width=True)
    _render_safe_html(bot_html)


def _render_tab_istogramma(df_sess: pd.DataFrame, dept_df: pd.DataFrame, meta: dict):
    c_sort, c_info = st.columns([1.8, 2.2])
    sort_choice = c_sort.selectbox(
        "Ordina Istogramma Individuale per:",
        ["Hml_25", "Run_Dist", "HSR"],
        format_func=lambda k: {
            "Hml_25": "Ordine crescente Hml (>25W) — Standard FIR",
            "Run_Dist": "Ordine crescente Run Distance (>6 km/h)",
            "HSR": "Ordine crescente HSR (>18 Avanti / >20 Trequarti)",
        }[k],
        index=0,
        key="hist_sort_col",
    )
    c_info.info(
        f"**Seduta analizzata**: `{meta['date_str']} • {meta['session_name']}` — "
        f"La barra **MAX AVG** e le linee tratteggiate **AVG RD**, **AVG Hml**, **AVG HSR** sono posizionate automaticamente."
    )

    fw_dept_row = dept_df[dept_df["department"] == "Avanti"].iloc[0].to_dict() if not dept_df[dept_df["department"] == "Avanti"].empty else {}
    bk_dept_row = dept_df[dept_df["department"] == "TreQuarti"].iloc[0].to_dict() if not dept_df[dept_df["department"] == "TreQuarti"].empty else {}

    fig_fw = _build_individual_histogram_figure(df_sess, fw_dept_row, "Avanti", meta["archetype"], sort_col=sort_choice)
    st.plotly_chart(fig_fw, use_container_width=True)

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    fig_bk = _build_individual_histogram_figure(df_sess, bk_dept_row, "TreQuarti", meta["archetype"], sort_col=sort_choice)
    st.plotly_chart(fig_bk, use_container_width=True)


def _render_tab_report_giornata_or_settimana(df_agg: pd.DataFrame, role_df: pd.DataFrame, dept_df: pd.DataFrame, meta: dict, is_weekly: bool = False):
    key_prefix = "week" if is_weekly else "day"
    if is_weekly:
        h_title = f"Report Settimanale — Dati Individuali ({meta['week_name']})"
        h_sub = f"Periodo: {meta['week_period_disp']} • {meta['week_competition']} • Sedute sommate ({len(meta['week_sessions_list'])}): {', '.join(meta['week_sessions_list'])}"
    else:
        h_title = f"Report Giornata — Dati Individuali ({meta['date_short']})"
        h_sub = f"Sedute sommate nella giornata ({len(meta['day_sessions_list'])}): {', '.join(meta['day_sessions_list'])}"

    # Selettori per il grafico % Match 80' e fonte Benchmark
    opt1, opt2 = st.columns([2.2, 1.8])
    chart_style = opt1.selectbox(
        "Visualizzazione Grafico % HML & % HSR Match 80':",
        ["dual_ranking", "paired_bars", "quadrant_scatter"],
        format_func=lambda k: {
            "dual_ranking": "1. Doppio Ranking Orizzontale Affiancato (Layout Ufficiale FIR PDF)",
            "paired_bars": "2. Barre Accoppiate per Giocatore (% HML vs % HSR fianco a fianco)",
            "quadrant_scatter": "3. Matrice a 4 Quadranti Workload (% HML su X vs % HSR su Y)",
        }[k],
        index=0,
        key=f"{key_prefix}_chart_style",
    )
    bench_src = opt2.selectbox(
        "Fonte Benchmark Match 80' per il calcolo delle %:",
        ["excel", "tot", "fir"],
        format_func=lambda k: {
            "excel": "Benchmark Storico Roster FIR (Allineato al PDF)",
            "tot": "Media Match 80' Calcolata — Totale (Nazionale + Club)",
            "fir": "Media Match 80' Calcolata — Solo Nazionale (FIR)",
        }[k],
        index=0,
        key=f"{key_prefix}_bench_src",
    )

    df_plot = _compute_match_pct_columns(df_agg, bench_source=bench_src)

    # Indicatore atleti Modificati / RTP nella giornata/settimana
    mod_day = [r["player_name"] for _, r in df_plot.iterrows() if str(r.get("status", "")).upper() in ("MODIFICATO", "MODIFIED")]
    rtp_day = [r["player_name"] for _, r in df_plot.iterrows() if str(r.get("status", "")).upper() == "RTP"]
    if mod_day or rtp_day:
        msg_parts = []
        if mod_day:
            msg_parts.append(f"<span style='background:#FEF08A; color:#713F12; font-weight:800; padding:2px 7px; border-radius:4px; border:1px solid #CA8A04;'>🟡 MODIFICATO ({len(mod_day)}): {', '.join(mod_day)}</span>")
        if rtp_day:
            msg_parts.append(f"<span style='background:#BAE6FD; color:#0369A1; font-weight:800; padding:2px 7px; border-radius:4px; border:1px solid #0284C7;'>🔵 RTP ({len(rtp_day)}): {', '.join(rtp_day)}</span>")
        st.markdown(
            f"<div style='display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:0.76rem; padding:6px 12px; background:rgba(255,255,255,0.06); border:1px solid #CBD5E1; border-radius:6px; margin-bottom:12px;'>"
            f"<b>Stato Atleti:</b> {' '.join(msg_parts)} "
            f"<span style='color:#64748B;'>— <i>Esclusi automaticamente dalle medie di reparto e ruolo</i></span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    top_html, bot_html = _build_session_report_html(
        df_plot,
        role_df,
        dept_df,
        h_title,
        h_sub,
        highlight_vmax90=True,
        show_tempo_in_role_table=False,
    )

    # 1. Tabella Superiore Dati Individuali (Giornata o Settimana)
    _render_safe_html(top_html)

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # 2. Grafico Centrale: % HML MEDI INDIVIDUALI MATCH 80' & % HSR MEDI INDIVIDUALI MATCH 80'
    fig_pct = _build_match_pct_figure(df_plot, chart_style=chart_style, is_weekly=is_weekly)
    st.plotly_chart(fig_pct, use_container_width=True)

    # 3. Tabella Inferiore Medie per Ruolo e Reparto
    _render_safe_html(bot_html)


def _render_tab_campo(hist_df: pd.DataFrame, players_df: pd.DataFrame, t: dict, match_info: dict = None, meta: dict = None):
    if match_info:
        sel_date = match_info["date_str"]
        match_name = match_info["match_name"]
        competition = match_info["competition"]
    else:
        lineup_summary = utils.get_lineup_matches_summary()
        if lineup_summary.empty:
            st.info("Nessuna formazione 1-23 salvata.")
            return
        match_row = lineup_summary.iloc[0]
        sel_date = str(match_row["date_str"])
        match_name = str(match_row["match_name"])
        competition = str(match_row["competition"])

    detail = utils.get_match_lineup_detail(sel_date)
    starters_df = detail["starters"]
    finishers_df = detail["finishers"]

    # Match metadata formatted in Italian
    try:
        dt_obj = pd.to_datetime(sel_date)
        giorni_ita = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
        mesi_ita = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        date_str_ita = f"{giorni_ita[dt_obj.weekday()]} {dt_obj.day} {mesi_ita[dt_obj.month - 1]} {dt_obj.year}"
    except Exception:
        date_str_ita = sel_date

    match_meta = {
        "title": f"{match_name} {competition}".upper(),
        "date_str": date_str_ita.upper(),
        "slogan": "PRIMI SEMPRE • ATTACCARE SEMPRE",
        "competition": competition.upper(),
    }

    # Estrazione metriche GPS rigorosamente vincolata alla sola seduta indicata nella barra laterale
    target_sess = meta.get("session_name") if meta else None
    if not target_sess:
        target_sess = st.session_state.get("global_selected_session_name")

    match_sess_gps = pd.DataFrame()
    if target_sess and not hist_df.empty and "session_name" in hist_df.columns:
        match_sess_gps = hist_df[(hist_df["date_str"] == str(sel_date)) & (hist_df["session_name"] == str(target_sess))].copy()

    if match_sess_gps.empty and not hist_df.empty:
        cand = hist_df[(hist_df["date_str"] == str(sel_date)) & (hist_df["session_name"].astype(str).str.lower().str.contains("match"))]
        if not cand.empty:
            match_sess_gps = cand.copy()
        else:
            day_all = hist_df[hist_df["date_str"] == str(sel_date)]
            if not day_all.empty:
                top_s = day_all["session_name"].value_counts().index[0]
                match_sess_gps = day_all[day_all["session_name"] == top_s].copy()
            else:
                match_sess_gps = pd.DataFrame()

    day_gps = match_sess_gps

    # Recupero minutaggio ufficiale di gara dal database Oval Match esclusivamente per la data della partita selezionata
    oval_df = utils.get_oval_matches_df()
    sub_oval = pd.DataFrame()
    if not oval_df.empty:
        if "match_date" in oval_df.columns:
            sub_oval = oval_df[oval_df["match_date"].astype(str) == str(sel_date)].copy()
        if sub_oval.empty and "date" in oval_df.columns:
            sub_oval = oval_df[oval_df["date"].astype(str) == str(sel_date)].copy()

    player_stats = {}
    convocati_all = pd.concat([starters_df, finishers_df], ignore_index=True) if not starters_df.empty or not finishers_df.empty else pd.DataFrame()

    for _, r in convocati_all.iterrows():
        p_name = r["player_name"]
        j_num = int(r["jersey_number"])
        role = r.get("role", "")
        dept = utils.get_player_department(p_name, role, j_num)

        # Ricerca minutaggio effettivo in Oval Match
        m_oval = None
        m_oval = None
        cic_val = 0.0
        tck_val = 0.0
        rck_val = 0.0
        if not sub_oval.empty:
            m_row = pd.DataFrame()
            if "fir_player_name" in sub_oval.columns:
                m_row = sub_oval[sub_oval["fir_player_name"].astype(str).str.strip().str.upper() == str(p_name).strip().upper()]
            if m_row.empty and "playerFullName" in sub_oval.columns:
                m_row = sub_oval[sub_oval["playerFullName"].astype(str).str.strip().str.upper() == str(p_name).strip().upper()]
            if m_row.empty:
                j_col_ov = "Jersey" if "Jersey" in sub_oval.columns else ("JERSEY" if "JERSEY" in sub_oval.columns else None)
                if j_col_ov and j_num > 0:
                    m_row = sub_oval[pd.to_numeric(sub_oval[j_col_ov], errors="coerce") == j_num]
            if not m_row.empty:
                r0_ov = m_row.iloc[0]
                if pd.notna(r0_ov.get("Min")):
                    m_oval = float(pd.to_numeric(r0_ov.get("Min"), errors="coerce") or 0.0)
                cic_v = pd.to_numeric(r0_ov.get("TotalCarriesInContact"), errors="coerce")
                tck_v = pd.to_numeric(r0_ov.get("TotalTackleAttempts"), errors="coerce")
                rck_v = pd.to_numeric(r0_ov.get("TotalEffectiveRuckEntries"), errors="coerce")
                cic_val = float(cic_v) if pd.notna(cic_v) else 0.0
                tck_val = float(tck_v) if pd.notna(tck_v) else 0.0
                rck_val = float(rck_v) if pd.notna(rck_v) else 0.0

        p_gps = day_gps[day_gps["player_name"].astype(str).str.strip().str.upper() == str(p_name).strip().upper()] if not day_gps.empty else pd.DataFrame()
        if not p_gps.empty:
            dur = pd.to_numeric(p_gps.get("duration", 0), errors="coerce").fillna(0).mean()
            pos = pd.to_numeric(p_gps.get("v_max", 0), errors="coerce").fillna(0).max()  # PoS = Peak of Speed (Vmax in km/h)
            dt = pd.to_numeric(p_gps.get("distance_m", 0), errors="coerce").fillna(0).sum()
            sp06 = pd.to_numeric(p_gps.get("speed_0_6", 0), errors="coerce").fillna(0).sum()
            dc = max(0.0, dt - sp06)
            mp25 = pd.to_numeric(p_gps.get("mp_25_35", 0), errors="coerce").fillna(0).sum()
            mp35 = pd.to_numeric(p_gps.get("mp_35_50", 0), errors="coerce").fillna(0).sum()
            mp50 = pd.to_numeric(p_gps.get("mp_50_100", 0), errors="coerce").fillna(0).sum()
            hml = mp25 + mp35 + mp50
            vhml = mp50
            sp18 = pd.to_numeric(p_gps.get("speed_18_20", 0), errors="coerce").fillna(0).sum()
            sp20 = pd.to_numeric(p_gps.get("speed_20_25", 0), errors="coerce").fillna(0).sum()
            sp25 = pd.to_numeric(p_gps.get("speed_25_72", 0), errors="coerce").fillna(0).sum()
            hsr = (sp18 + sp20 + sp25) if dept == "Avanti" else (sp20 + sp25)

            # Minuti: priorità assoluta ai dati Oval Match, altrimenti cap ad 80' da GPS
            minuti_effettivi = m_oval if m_oval is not None else min(80.0, dur)

            player_stats[p_name] = {
                "minutes": minuti_effettivi,
                "PoS": pos,
                "DT": dt,
                "DC": dc,
                "Hml": hml,
                "VHml": vhml,
                "HSR": hsr,
                "CIC": cic_val,
                "TCK": tck_val,
                "RCK": rck_val,
            }
        else:
            # Gara non ancora disputata o senza dati GPS: minuti da Oval se presenti, altrimenti 0
            minuti_effettivi = m_oval if m_oval is not None else 0.0
            player_stats[p_name] = {
                "minutes": minuti_effettivi,
                "PoS": 0.0,
                "DT": 0.0,
                "DC": 0.0,
                "Hml": 0.0,
                "VHml": 0.0,
                "HSR": 0.0,
                "CIC": cic_val,
                "TCK": tck_val,
                "RCK": rck_val,
            }

    # Calcolo Medie Reparti: somma di tutti gli Avanti / 8 e somma di tutti i TreQuarti / 7
    rep_averages = {"Avanti": {}, "TreQuarti": {}}
    for dept_key in ["Avanti", "TreQuarti"]:
        p_names_dept = [r["player_name"] for _, r in convocati_all.iterrows() if utils.get_player_department(r.get("player_name"), r.get("role", ""), r.get("jersey_number", 0)) == dept_key]
        divisor = 8.0 if dept_key == "Avanti" else 7.0

        tot_dt = sum(player_stats.get(pn, {}).get("DT", 0.0) for pn in p_names_dept)
        tot_dc = sum(player_stats.get(pn, {}).get("DC", 0.0) for pn in p_names_dept)
        tot_hml = sum(player_stats.get(pn, {}).get("Hml", 0.0) for pn in p_names_dept)
        tot_vhml = sum(player_stats.get(pn, {}).get("VHml", 0.0) for pn in p_names_dept)
        tot_hsr = sum(player_stats.get(pn, {}).get("HSR", 0.0) for pn in p_names_dept)
        tot_cic = sum(player_stats.get(pn, {}).get("CIC", 0.0) for pn in p_names_dept)
        tot_tck = sum(player_stats.get(pn, {}).get("TCK", 0.0) for pn in p_names_dept)
        tot_rck = sum(player_stats.get(pn, {}).get("RCK", 0.0) for pn in p_names_dept)
        tot_min = sum(player_stats.get(pn, {}).get("minutes", 0.0) for pn in p_names_dept)
        max_pos = max([player_stats.get(pn, {}).get("PoS", 0.0) for pn in p_names_dept] or [0.0])

        rep_averages[dept_key] = {
            "DT": tot_dt / divisor,
            "DC": tot_dc / divisor,
            "Hml": tot_hml / divisor,
            "VHml": tot_vhml / divisor,
            "HSR": tot_hsr / divisor,
            "CIC": tot_cic / divisor,
            "TCK": tot_tck / divisor,
            "RCK": tot_rck / divisor,
            "PoS": max_pos,
            "minutes": tot_min / divisor,
            "count": len(p_names_dept),
            "divisor": int(divisor),
        }

    # Action Bar superiore con Export PDF
    meta_bar = [
        ("Gara", match_name),
        ("Data", date_str_ita),
        ("Competizione", competition),
        ("Convocati", f"{len(starters_df) + len(finishers_df)} Atleti"),
        ("Titolari", f"{len(starters_df)}"),
        ("Finishers", f"{len(finishers_df)}"),
    ]

    def _generate_pitch_pdf(_):
        return crea_pdf_schieramento_campo(
            match_meta=match_meta,
            starters_df=starters_df,
            finishers_df=finishers_df,
            player_stats=player_stats,
            rep_averages=rep_averages,
        )

    slug_m = slugify_name(match_name)
    render_action_bar(
        meta_items=meta_bar,
        pdf_options={"Report Ufficiale Trombinoscopio Match (1-23)": "schieramento_1_23"},
        pdf_key=f"pitch_pdf_{sel_date}",
        generate_fn=_generate_pitch_pdf,
        filename_fn=lambda _: f"FIR_Report_Trombinoscopio_Match_{slug_m}_{sel_date}.pdf",
    )

    # --------------------------------------------------------------------------
    # COSTRUZIONE HTML SCHIERAMENTO IN CAMPO
    # --------------------------------------------------------------------------
    starters_map = {int(r["jersey_number"]): r.to_dict() for _, r in starters_df.iterrows()} if not starters_df.empty else {}
    finishers_map = {int(r["jersey_number"]): r.to_dict() for _, r in finishers_df.iterrows()} if not finishers_df.empty else {}

    def _format_player_name(full_name: str) -> str:
        parts = full_name.strip().split()
        if len(parts) >= 3 and parts[1].lower() in ('di', 'de', 'del', 'della', 'da'):
            return f"{parts[0][0]}. {' '.join(parts[1:])}"
        elif len(parts) >= 3:
            return f"{parts[0][0]}. {parts[1][0]}. {' '.join(parts[2:])}"
        elif len(parts) == 2:
            return f"{parts[0][0]}. {parts[1]}"
        return full_name

    roster_role_map = {}
    if not players_df.empty:
        for _, pr in players_df.iterrows():
            nm = str(pr.get("name_display") or "").strip().upper()
            if nm:
                roster_role_map[nm] = str(pr.get("role") or "").strip()

    def _get_html_card_border_color(j_num: int, role_str: str = "", p_name: str = "") -> str:
        # Per i titolari (1-15) il colore della cornice è SEMPRE legato alla posizione/maglia
        if j_num in (1, 2, 3):
            return "#172554"  # Prima Linea (Piloni e Tallonatore)
        if j_num in (4, 5):
            return "#2563EB"  # Seconda Linea
        if j_num in (6, 7, 8):
            return "#38BDF8"  # Terza Linea
        if j_num in (9, 10):
            return "#7F1D1D"  # Mediani di Mischia e Apertura
        if j_num in (12, 13):
            return "#EF4444"  # Centri
        if j_num in (11, 14, 15):
            return "#FDA4AF"  # Ali ed Estremo

        # Per la panchina (16-23) il colore della cornice deve tenere conto
        # ESCLUSIVAMENTE del ruolo salvato nel roster per quell'atleta!
        pn_clean = str(p_name or "").strip().upper()
        r_clean = roster_role_map.get(pn_clean, "").lower()
        if not r_clean:
            ident = utils.resolve_player_identity(p_name)
            r_clean = str(ident.get("role") or role_str or "").lower()

        if "pilon" in r_clean or "tallon" in r_clean or "prima" in r_clean:
            return "#172554"  # Prima Linea
        if "second" in r_clean:
            return "#2563EB"  # Seconda Linea
        if "terz" in r_clean or "flanker" in r_clean or "otto" in r_clean:
            return "#38BDF8"  # Terza Linea
        if "mischia" in r_clean or "apertura" in r_clean or "mediano" in r_clean:
            return "#7F1D1D"  # Mediani
        if "centr" in r_clean:
            return "#EF4444"  # Centri
        if "ala" in r_clean or "estrem" in r_clean or "utility" in r_clean:
            return "#FDA4AF"  # Ali ed Estremo

        return "#172554"

    def _render_player_html_card(j_num: int, is_starter: bool = True, is_halves: bool = False) -> str:
        p_row = starters_map.get(j_num) if j_num in starters_map else (finishers_map.get(j_num) if j_num in finishers_map else {})
        p_name = str(p_row.get("player_name") or f"Maglia {j_num}").strip()
        p_role = str(p_row.get("role") or "").strip()
        # Per la panchina (16-23) il ruolo mostrato sulla card deriva dal Roster FIR
        if j_num >= 16:
            r_from_roster = roster_role_map.get(p_name.upper())
            if r_from_roster:
                p_role = r_from_roster
        border_col = _get_html_card_border_color(j_num, p_role, p_name)
        st_data = player_stats.get(p_name, {})
        minuti_val = st_data.get("minutes", 0)
        pos_val = st_data.get("PoS", 0.0)  # Peak of Speed (Vmax in km/h)
        dt_val = st_data.get("DT", 0.0)
        dc_val = st_data.get("DC", 0.0)
        hml_val = st_data.get("Hml", 0.0)
        vhml_val = st_data.get("VHml", 0.0)
        hsr_val = st_data.get("HSR", 0.0)
        cic_val = st_data.get("CIC", 0.0)
        tck_val = st_data.get("TCK", 0.0)
        rck_val = st_data.get("RCK", 0.0)

        # Foto giocatore (ottimizzata e nitida per il tabellone)
        photo_b64 = utils.get_player_photo_base64(p_name, max_width=120)
        if photo_b64:
            photo_html = f'<img src="data:image/jpeg;base64,{photo_b64}" style="width:28px; height:32px; object-fit:cover; border-radius:4px; border:1px solid #CBD5E1; flex-shrink:0; box-shadow:0 1px 3px rgba(0,0,0,0.15);" alt="{p_name}">'
        else:
            inits = "".join(part[0] for part in p_name.split()[:2]).upper()
            photo_html = f'<div style="width:28px; height:32px; border-radius:4px; background:#E2E8F0; display:flex; align-items:center; justify-content:center; font-size:9.5px; font-weight:800; color:#002B49; flex-shrink:0;">{inits}</div>'

        border_css = f"border: 2.8px solid {border_col}; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.22);"

        short_name = _format_player_name(p_name)
        n_len = len(short_name)
        font_sz = "8.6px" if n_len > 14 else ("9.2px" if n_len > 10 else "9.8px")

        pos_str = f"{pos_val:.1f}" if pos_val > 0 else "0"
        dt_str = f"{int(dt_val):,}".replace(",", ".") if dt_val > 0 else "0"
        dc_str = f"{int(dc_val):,}".replace(",", ".") if dc_val > 0 else "0"
        hml_str = f"{int(hml_val):,}".replace(",", ".") if hml_val > 0 else "0"
        vhml_str = f"{int(vhml_val):,}".replace(",", ".") if vhml_val > 0 else "0"
        hsr_str = f"{int(hsr_val):,}".replace(",", ".") if hsr_val > 0 else "0"
        cic_str = f"{int(round(cic_val))}" if cic_val > 0 else "0"
        tck_str = f"{int(round(tck_val))}" if tck_val > 0 else "0"
        rck_str = f"{int(round(rck_val))}" if rck_val > 0 else "0"

        return f"""
        <div style="background:#FFFFFF; border-radius:9px; {border_css} padding:5px 7px; width:174px; font-family:'Inter', sans-serif; box-sizing:border-box;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:4px; border-bottom:1px solid #E2E8F0; padding-bottom:4px; margin-bottom:4px;">
                <div style="display:flex; align-items:center; gap:4px; min-width:0; flex:1;">
                    <div style="width:20px; height:20px; min-width:20px; border-radius:50%; background:{border_col}; border:1.5px solid #FFFFFF; box-shadow:0 1px 2px rgba(0,0,0,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-weight:900; font-size:10px; flex-shrink:0;">
                        {j_num}
                    </div>
                    {photo_html}
                    <div style="font-size:{font_sz}; font-weight:800; color:#0F172A; white-space:nowrap; overflow:hidden; text-overflow:clip; min-width:0; flex:1;" title="{p_name}">
                        {short_name}
                    </div>
                </div>
                <div style="text-align:right; line-height:1.0; flex-shrink:0; padding-left:2px;">
                    <div style="font-size:6.5px; color:#64748B; font-weight:700; text-transform:uppercase;">min</div>
                    <div style="font-size:10.5px; font-weight:900; color:#0284C7;">{int(round(minuti_val))}</div>
                </div>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:1.5px 5px; font-size:8.8px;">
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">PoS</span><b style="color:#0F172A;">{pos_str}</b></div>
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">DT</span><b style="color:#0F172A;">{dt_str}</b></div>
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">DC</span><b style="color:#0F172A;">{dc_str}</b></div>
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">Hml</span><b style="color:#0F172A;">{hml_str}</b></div>
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">VHml</span><b style="color:#0F172A;">{vhml_str}</b></div>
                <div style="display:flex; justify-content:space-between;"><span style="color:#64748B; font-size:8.0px;">HSR</span><b style="color:#0F172A;">{hsr_str}</b></div>
            </div>
            <div style="margin-top:3px; padding:2px 4px; border-top:1px dashed #CBD5E1; background:#F8FAFC; border-radius:4px; display:grid; grid-template-columns:1fr 1fr 1fr; gap:3px; font-size:8.2px;">
                <div style="display:flex; justify-content:space-between; align-items:center;" title="TotalCarriesInContact (Col. BP)"><span style="color:#64748B; font-size:7.3px; font-weight:700;">CIC</span><b style="color:#0369A1;">{cic_str}</b></div>
                <div style="display:flex; justify-content:space-between; align-items:center;" title="TotalTackleAttempts (Col. BD)"><span style="color:#64748B; font-size:7.3px; font-weight:700;">TCK</span><b style="color:#B91C1C;">{tck_str}</b></div>
                <div style="display:flex; justify-content:space-between; align-items:center;" title="TotalEffectiveRuckEntries (Col. CG)"><span style="color:#64748B; font-size:7.3px; font-weight:700;">RCK</span><b style="color:#047857;">{rck_str}</b></div>
            </div>
        </div>
        """

    # Posizionamento perfetto dei 15 titolari sul campo da rugby (spaziatura netta tra 9-12 e 10-13)
    pos_coords = {
        # 1. Prima Linea (Blu Scuro)
        1: (15, 6.2),    # Pilone Sinistro (1)
        2: (50, 6.2),    # Tallonatore (2)
        3: (85, 6.2),    # Pilone Destro (3)
        # 2. Seconda Linea (Blu Normale)
        4: (32, 19.2),   # Seconda Linea SX (4)
        5: (68, 19.2),   # Seconda Linea DX (5)
        # 3. Terza Linea (Blu Chiaro)
        6: (15, 32.2),   # Flanker Sinistro (6)
        8: (50, 32.2),   # Numero Otto (8)
        7: (85, 32.2),   # Flanker Destro (7)
        # 4. Mediani (Rosso Scuro)
        9: (33, 46.2),   # Mediano di Mischia (9)
        10: (67, 46.2),  # Mediano di Apertura (10)
        # 5. Centri (Rosso Normale) — ben distanziati sotto 9 e 10
        12: (33, 62.8),  # Primo Centro (12)
        13: (67, 62.8),  # Secondo Centro (13)
        # 6. Ali (Rosso Chiaro)
        11: (15, 77.2),  # Ala Sinistra (11)
        14: (85, 77.2),  # Ala Destra (14)
        # 7. Estremo (Rosso Chiaro)
        15: (50, 91.0),  # Estremo (15)
    }

    starters_cards_html = ""
    for j_num, (xp, yp) in pos_coords.items():
        is_red = j_num in (9, 10)
        card_content = _render_player_html_card(j_num, is_starter=True, is_halves=is_red)
        starters_cards_html += f"""
        <div style="position:absolute; left:{xp}%; top:{yp}%; transform:translate(-50%, -50%); z-index:10;">
            {card_content}
        </div>
        """

    # Finishers (Maglie 16–23 in 2 colonne ben spaziate)
    fin_col1_html = "".join([f'<div style="margin-bottom:18px;">{_render_player_html_card(num, is_starter=False)}</div>' for num in [16, 17, 18, 19]])
    fin_col2_html = "".join([f'<div style="margin-bottom:18px;">{_render_player_html_card(num, is_starter=False)}</div>' for num in [20, 21, 22, 23]])

    # Render del tabellone tattico completo (SENZA CERCHIO CENTRALE, campo distanziato 1040px)
    tabellone_html = f"""
    <div style="display:flex; gap:16px; align-items:stretch; margin-bottom:18px;">
        <!-- CAMPO RUGBY (Titolari 1–15) -->
        <div style="flex:3.2; position:relative; min-height:1040px; border-radius:14px; overflow:hidden;
                    background: linear-gradient(180deg, #166534 0%, #15803D 50%, #166534 100%);
                    border:3px solid #FFFFFF; box-shadow:0 8px 24px rgba(15,23,42,0.16);">
            
            <!-- Segnature Rugby Ufficiali (Campo da Rugby: SOLO linee regolamentari) -->
            <!-- 5m In-Goal Line Top -->
            <div style="position:absolute; top:3%; left:0; right:0; border-top:1.5px dashed rgba(255,255,255,0.65);"></div>
            <!-- 22m Line Top -->
            <div style="position:absolute; top:17%; left:0; right:0; border-top:2px solid rgba(255,255,255,0.85);"></div>
            <!-- 10m Line Top -->
            <div style="position:absolute; top:33%; left:0; right:0; border-top:1.5px dashed rgba(255,255,255,0.65);"></div>
            <!-- 50m Metà Campo (linea continua senza cerchio) -->
            <div style="position:absolute; top:50%; left:0; right:0; border-top:2.5px solid #FFFFFF;"></div>
            <!-- 10m Line Bottom -->
            <div style="position:absolute; top:67%; left:0; right:0; border-top:1.5px dashed rgba(255,255,255,0.65);"></div>
            <!-- 22m Line Bottom -->
            <div style="position:absolute; top:83%; left:0; right:0; border-top:2px solid rgba(255,255,255,0.85);"></div>
            <!-- 5m In-Goal Line Bottom -->
            <div style="position:absolute; top:97%; left:0; right:0; border-top:1.5px dashed rgba(255,255,255,0.65);"></div>

            <!-- Titolari 1–15 -->
            {starters_cards_html}
        </div>

        <!-- PANNELLO FINISHERS (Panchina 16–23) -->
        <div style="flex:1.5; min-width:390px; background:#031926; border:2px solid #D4AF37; border-radius:14px; padding:18px 16px; box-shadow:0 8px 24px rgba(0,0,0,0.35); display:flex; flex-direction:column; justify-content:space-between;">
            <div style="text-align:center; padding-bottom:8px; border-bottom:1px solid rgba(212,175,55,0.35); margin-bottom:16px;">
                <div style="font-size:12.5px; font-weight:800; text-transform:uppercase; color:#D4AF37; letter-spacing:0.08em;">
                    FINISHERS (16–23)
                </div>
                <div style="font-size:9.5px; color:#93C5FD; font-weight:600;">
                    PANCHINA GARA
                </div>
            </div>
            
            <div style="display:flex; gap:12px; justify-content:space-between; flex:1; align-items:flex-start;">
                <div style="flex:1;">
                    <div style="font-size:8.5px; font-weight:700; color:#D4AF37; text-align:center; margin-bottom:12px; text-transform:uppercase;">Colonna 1</div>
                    {fin_col1_html}
                </div>
                <div style="flex:1;">
                    <div style="font-size:8.5px; font-weight:700; color:#D4AF37; text-align:center; margin-bottom:12px; text-transform:uppercase;">Colonna 2</div>
                    {fin_col2_html}
                </div>
            </div>
        </div>
    </div>
    """
    clean_tabellone = "".join(line.strip() for line in tabellone_html.splitlines() if line.strip())
    st.html(clean_tabellone)

    # --------------------------------------------------------------------------
    # BOX INFERIORI: MEDIE REPARTI (NORMALIZZATE AD 80') & LEGENDA GPEXE
    # --------------------------------------------------------------------------
    col_b1, col_b2 = st.columns([1.1, 1.2])

    with col_b1:
        avg_f = rep_averages.get("Avanti", {})
        avg_b = rep_averages.get("TreQuarti", {})
        cnt_f = avg_f.get("count", 0)
        cnt_b = avg_b.get("count", 0)

        dt_f = f"{int(avg_f.get('DT', 0)):,}".replace(",", ".")
        dc_f = f"{int(avg_f.get('DC', 0)):,}".replace(",", ".")
        hml_f = f"{int(avg_f.get('Hml', 0)):,}".replace(",", ".")
        vhml_f = f"{int(avg_f.get('VHml', 0)):,}".replace(",", ".")
        hsr_f = f"{int(avg_f.get('HSR', 0)):,}".replace(",", ".")
        cic_f = f"{avg_f.get('CIC', 0):.1f}" if avg_f.get("CIC", 0) > 0 else "0"
        tck_f = f"{avg_f.get('TCK', 0):.1f}" if avg_f.get("TCK", 0) > 0 else "0"
        rck_f = f"{avg_f.get('RCK', 0):.1f}" if avg_f.get("RCK", 0) > 0 else "0"

        dt_b = f"{int(avg_b.get('DT', 0)):,}".replace(",", ".")
        dc_b = f"{int(avg_b.get('DC', 0)):,}".replace(",", ".")
        hml_b = f"{int(avg_b.get('Hml', 0)):,}".replace(",", ".")
        vhml_b = f"{int(avg_b.get('VHml', 0)):,}".replace(",", ".")
        hsr_b = f"{int(avg_b.get('HSR', 0)):,}".replace(",", ".")
        cic_b = f"{avg_b.get('CIC', 0):.1f}" if avg_b.get("CIC", 0) > 0 else "0"
        tck_b = f"{avg_b.get('TCK', 0):.1f}" if avg_b.get("TCK", 0) > 0 else "0"
        rck_b = f"{avg_b.get('RCK', 0):.1f}" if avg_b.get("RCK", 0) > 0 else "0"

        medie_html = f"""
        <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; overflow:hidden; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
            <div style="background:#002B49; color:#FFFFFF; padding:8px 14px; font-size:11px; font-weight:800; letter-spacing:0.04em; display:flex; justify-content:space-between; align-items:center;">
                <span>MEDIE REPARTI &bull; SOMMA AVANTI &divide; 8 &bull; SOMMA TREQUARTI &divide; 7</span>
                <span style="font-size:9.5px; color:#D4AF37; font-weight:700;">RIASSUNTO MATCH (GPS + OVAL)</span>
            </div>
            <div style="padding:10px 12px;">
                <table style="width:100%; border-collapse:collapse; font-size:10.5px; text-align:right;">
                    <thead>
                        <tr style="background:#F1F5F9; color:#475569; font-weight:700; border-bottom:1px solid #CBD5E1;">
                            <th style="padding:5px 6px; text-align:left;">Reparto</th>
                            <th style="padding:5px 5px;">DT (m)</th>
                            <th style="padding:5px 5px;">DC (m)</th>
                            <th style="padding:5px 5px;">Hml (m)</th>
                            <th style="padding:5px 5px;">VHml (m)</th>
                            <th style="padding:5px 5px;">HSR (m)</th>
                            <th style="padding:5px 5px; color:#0369A1;">CIC</th>
                            <th style="padding:5px 5px; color:#B91C1C;">TCK</th>
                            <th style="padding:5px 5px; color:#047857;">RCK</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom:1px solid #E2E8F0;">
                            <td style="padding:6px 6px; text-align:left; font-weight:800; color:#002B49;">Avanti <span style="font-size:9px; color:#64748B; font-weight:500;">(Tot. ÷ 8)</span></td>
                            <td style="padding:6px 5px; font-weight:700;">{dt_f}</td>
                            <td style="padding:6px 5px;">{dc_f}</td>
                            <td style="padding:6px 5px; color:#0284C7; font-weight:700;">{hml_f}</td>
                            <td style="padding:6px 5px;">{vhml_f}</td>
                            <td style="padding:6px 5px; color:#D97706; font-weight:700;">{hsr_f} <span style="font-size:8.5px; color:#64748B;">(&gt;18)</span></td>
                            <td style="padding:6px 5px; color:#0369A1; font-weight:700;">{cic_f}</td>
                            <td style="padding:6px 5px; color:#B91C1C; font-weight:700;">{tck_f}</td>
                            <td style="padding:6px 5px; color:#047857; font-weight:700;">{rck_f}</td>
                        </tr>
                        <tr>
                            <td style="padding:6px 6px; text-align:left; font-weight:800; color:#002B49;">TreQuarti <span style="font-size:9px; color:#64748B; font-weight:500;">(Tot. ÷ 7)</span></td>
                            <td style="padding:6px 5px; font-weight:700;">{dt_b}</td>
                            <td style="padding:6px 5px;">{dc_b}</td>
                            <td style="padding:6px 5px; color:#0284C7; font-weight:700;">{hml_b}</td>
                            <td style="padding:6px 5px;">{vhml_b}</td>
                            <td style="padding:6px 5px; color:#D97706; font-weight:700;">{hsr_b} <span style="font-size:8.5px; color:#64748B;">(&gt;20)</span></td>
                            <td style="padding:6px 5px; color:#0369A1; font-weight:700;">{cic_b}</td>
                            <td style="padding:6px 5px; color:#B91C1C; font-weight:700;">{tck_b}</td>
                            <td style="padding:6px 5px; color:#047857; font-weight:700;">{rck_b}</td>
                        </tr>
                    </tbody>
                </table>
                <div style="font-size:9px; color:#64748B; font-style:italic; margin-top:6px;">
                    * Medie di reparto calcolate sommando i valori effettivi di tutti i giocatori e dividendo per le posizioni in campo (Somma Avanti ÷ 8, Somma TreQuarti ÷ 7).
                </div>
            </div>
        </div>
        """
        st.html("".join(line.strip() for line in medie_html.splitlines() if line.strip()))

    with col_b2:
        legenda_html = f"""
        <div style="background:#FFFFFF; border:1px solid #CBD5E1; border-radius:10px; overflow:hidden; box-shadow:0 3px 10px rgba(15,23,42,0.06);">
            <div style="background:#002B49; color:#FFFFFF; padding:8px 14px; font-size:11px; font-weight:800; letter-spacing:0.04em;">
                LEGENDA METRICHE GPEXE &amp; OVAL MATCH (FIR)
            </div>
            <div style="padding:7px 12px; font-size:10.0px; color:#1E293B; line-height:1.35;">
                <div style="margin-bottom:2px;"><b style="color:#0284C7;">• PoS / DT / DC:</b> Peak of Speed (Vmax km/h) • Distanza Totale (m) • Distanza Corsa &gt;6 km/h (m).</div>
                <div style="margin-bottom:2px;"><b style="color:#0284C7;">• Hml / VHml:</b> High Metabolic Load &gt;25.5 W/kg (m) • Very High Metabolic Load &gt;50.0 W/kg (m).</div>
                <div style="margin-bottom:2px;"><b style="color:#0284C7;">• HSR (High Speed Running):</b> Corsa ad alta velocità (&gt;18 km/h Avanti, &gt;20 km/h TreQuarti).</div>
                <div style="margin-bottom:2px;"><b style="color:#0369A1;">• CIC (TotalCarriesInContact — Col. BP Oval):</b> Carries portati in contatto dall'atleta.</div>
                <div style="margin-bottom:2px;"><b style="color:#B91C1C;">• TCK (TotalTackleAttempts — Col. BD Oval):</b> Placcaggi totali tentati nel match.</div>
                <div><b style="color:#047857;">• RCK (TotalEffectiveRuckEntries — Col. CG Oval):</b> Ingressi efficaci in ruck (pulizie/sicurezza).</div>
            </div>
        </div>
        """
        st.html("".join(line.strip() for line in legenda_html.splitlines() if line.strip()))

    # Slogan Banner finale FIR
    st.markdown(
        f"""
        <div style="margin-top:14px; background:linear-gradient(90deg, #031926 0%, #002B49 50%, #031926 100%);
                    border-radius:10px; padding:10px 18px; text-align:center; border:1px solid rgba(212,175,55,0.4);">
            <span style="font-size:11px; font-weight:800; color:#D4AF37; letter-spacing:0.12em; text-transform:uppercase;">
                FEDERAZIONE ITALIANA RUGBY &bull; NAZIONALE MAGGIORE &bull; {match_meta['title']}
            </span>
            <div style="font-size:10px; color:#FFFFFF; font-weight:700; margin-top:2px;">
                PRIMI SEMPRE &bull; ATTACCARE SEMPRE &bull; {match_meta['date_str']}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
