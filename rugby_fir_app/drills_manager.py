# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo di gestione persistenza, parsing multi-formato (GPExe / Catapult / CSV generici),
riconoscimento automatico giocatori attivi (esclusione panchina/rotazioni),
normalizzazione dinamica per ruolo/numero effettivo e logica di Upsert per:
  - `drills_master.parquet` (1 riga = 1 drill per seduta: Carico Totale + Media Normalizzata Attivi)
  - `drills_roles_summary.parquet` (breakdown per ruolo: Carico Totale Ruolo + Media Pro-Capite Attivi)
  - `drills_players_detail.parquet` (tracce individuali con flag `Is_Active` ed `Exclusion_Reason`)
"""

import io
import os
import re
import datetime
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None

import cloud_storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DRILLS_MASTER_PATH = os.path.join(DATA_DIR, "drills_master.parquet")
DRILLS_PLAYERS_PATH = os.path.join(DATA_DIR, "drills_players_detail.parquet")
DRILLS_ROLES_PATH = os.path.join(DATA_DIR, "drills_roles_summary.parquet")

# Soglie predefinite per riconoscimento automatico giocatori attivi vs fuori campo/rotazione
DEFAULT_MIN_DIST_M = 30.0
DEFAULT_MIN_WR_MPM = 12.0
DEFAULT_MIN_REL_DIST_PCT = 25.0  # % della mediana distanza del gruppo nel drill

DRILLS_MASTER_COLUMNS: List[str] = [
    "Session_Date",
    "Session_Name",
    "Drill_Name",
    "Drill_Order",
    "Source_File",
    "Players_Count",            # Alias retro-compatibile = Active_Players_Count
    "Active_Players_Count",
    "Excluded_Players_Count",
    "Raw_Players_Count",
    "Duration_Min",
    # Medie Normalizzate Pro-Capite (Carico Totale Attivi / Active_Players_Count)
    "Total_Distance",
    "Work_Rate",
    "HMPD",
    "HMPD_per_Min",
    "HSR",
    "HSR_per_Min",
    "VHSR",
    "Max_Speed",
    "Max_Speed_Peak",
    "Max_Speed_Pct",
    "Dynamic_Stress_Load",
    "Heavy_Impacts",
    "Acc_Events",
    "Dec_Events",
    "Met_Power_Events",
    "Avg_MP",
    # Somme Totali del Gruppo Attivo (Carico Totale Erogato nel Blocco)
    "Total_Distance_Sum",
    "HMPD_Sum",
    "HSR_Sum",
    "VHSR_Sum",
    "Dynamic_Stress_Load_Sum",
    "Heavy_Impacts_Sum",
    "Acc_Events_Sum",
    "Dec_Events_Sum",
    "Met_Power_Events_Sum",
    # Split Reparti (Avanti vs Trequarti — Conteggi Attivi, Medie Normalizzate e Somme)
    "Avanti_Active_Count",
    "Trequarti_Active_Count",
    "Avanti_Work_Rate",
    "Trequarti_Work_Rate",
    "Avanti_Total_Distance",
    "Trequarti_Total_Distance",
    "Avanti_Total_Distance_Sum",
    "Trequarti_Total_Distance_Sum",
    "Avanti_HMPD",
    "Trequarti_HMPD",
    "Avanti_HMPD_Sum",
    "Trequarti_HMPD_Sum",
    "Avanti_HSR",
    "Trequarti_HSR",
    "Avanti_HSR_Sum",
    "Trequarti_HSR_Sum",
    "Avanti_DSL",
    "Trequarti_DSL",
    "Avanti_DSL_Sum",
    "Trequarti_DSL_Sum",
    "Updated_At",
]

DRILLS_ROLES_COLUMNS: List[str] = [
    "Session_Date",
    "Session_Name",
    "Drill_Name",
    "Drill_Order",
    "Role",
    "Department",
    "Active_Players_Count",
    "Excluded_Players_Count",
    "Duration_Min",
    # Media Normalizzata Pro-Capite del Ruolo (Carico Totale Ruolo / Active_Players_Count)
    "Total_Distance",
    "Work_Rate",
    "HMPD",
    "HMPD_per_Min",
    "HSR",
    "HSR_per_Min",
    "VHSR",
    "Max_Speed",
    "Max_Speed_Peak",
    "Dynamic_Stress_Load",
    "Heavy_Impacts",
    "Acc_Events",
    "Dec_Events",
    "Avg_MP",
    # Carico Totale del Ruolo (Somma Energetica degli Atleti Attivi del Ruolo)
    "Total_Distance_Sum",
    "HMPD_Sum",
    "HSR_Sum",
    "VHSR_Sum",
    "Dynamic_Stress_Load_Sum",
    "Heavy_Impacts_Sum",
    "Acc_Events_Sum",
    "Dec_Events_Sum",
]

DRILLS_PLAYERS_COLUMNS: List[str] = [
    "Session_Date",
    "Session_Name",
    "Drill_Name",
    "Drill_Order",
    "Player_Name",
    "Role",
    "Department",
    "Is_Active",
    "Exclusion_Reason",
    "Duration_Min",
    "Total_Distance",
    "Work_Rate",
    "HMPD",
    "HSR",
    "VHSR",
    "Max_Speed",
    "Max_Speed_Pct",
    "Dynamic_Stress_Load",
    "Heavy_Impacts",
    "Acc_Events",
    "Dec_Events",
    "Met_Power_Events",
    "Avg_MP",
]

DRILL_COL_ALIASES: Dict[str, List[str]] = {
    "player_name": [
        "athlete", "player", "name", "player name", "athlete name",
        "giocatore", "atleta", "cognome nome", "player_name",
    ],
    "role": [
        "role", "ruolo", "position", "position name", "reparto", "department",
    ],
    "drill_hint": [
        "drill_name", "drill name", "drill", "period name", "period",
        "blocco", "split", "notes", "activity name",
    ],
    "duration": [
        "duration (mm:ss)", "total time (mm:ss)", "duration", "durata",
        "durata (min)", "duration_min", "time (min)", "total time", "total duration",
    ],
    "total_distance": [
        "distance (m)", "total distance (m)", "total distance", "total_distance",
        "distanza (m)", "distanza", "distance",
    ],
    "work_rate": [
        "avg speed (m/min)", "meterage per minute", "work rate", "work_rate",
        "m/min", "m\\min", "metri/min", "avg speed (km/h)",
    ],
    "hmpd": [
        "hmpd", "hmpd (m)", "hmld (m)", "hmld", "distance/met power z3+ (m)",
        "distance > 25,5w (m)", "distance > 25.5w (m)", "hml >25w",
        "mp 25,5 - 35 w (m)", "mp 25.5-35 w",
    ],
    "hsr": [
        "hsr", "hsr (m)", "hsrm (>18km/hr) (m)", "hsrm (>20km/h)",
        "distance/speed z4+ (m)", "hsr >18", "hsr>20",
        "velocità 20-25 km\\h (m)", "velocita 20-25 km/h (m)",
    ],
    "vhsr": [
        "vhsr", "vhsr (m)", "vhsr m (25km/hr)", "distance/speed z5+ (m)",
        "vhsr>25", "velocità 25-72 km\\h (m)", "velocita 25-72 km/h (m)",
    ],
    "max_speed": [
        "max speed (km/h)", "maximum speed (km/h)", "max speed", "max_speed",
        "v max (km/h)", "maximum velocity", "peak speed", "v max", "vmax",
    ],
    "max_speed_pct": [
        "max speed% (%)", "max speed (%)", "max_speed_pct",
        "v max (% max)", "% v max", "pct max speed",
    ],
    "dsl": [
        "dynamic stress load", "dynamic_stress_load", "dsl",
        "total player load", "player load totale", "player load", "playerload",
        "ext workᐩ (j/kg)", "ext work+ (j/kg)", "ext work (j/kg)", "ext work",
        "high ext workᐩ (j/kg)", "tl", "training load", "total acceleration load",
    ],
    "heavy_impacts": [
        "heavy impacts", "heavy_impacts", "impacts z3", "impacts",
        "contatti", "contacts", "collisions", "heavy collisions",
    ],
    "acc_events": [
        "acc events", "acc_events", "# accel >2mss", "bursts",
        "volume acc", "total accelerations", "accelerations",
    ],
    "dec_events": [
        "dec events", "dec_events", "brakes", "total decelerations", "decelerations",
    ],
    "mpe": [
        "met power events", "met_power_events", "mpe", "n azioni >25,5w",
    ],
    "avg_mp": [
        "avg mp (w/kg)", "avg_mp", "average metabolic power", "metabolic power",
    ],
}

# Righe di riepilogo esportate talvolta da GPExe nella colonna athlete (da non contare come atleti)
SUMMARY_ROW_LABELS = {
    "nan", "none", "average", "media", "total", "totale", "team", "squadra", "squad",
    "unassigned role", "unassigned", "all", "overall", "summary", "riepilogo",
    "pilone", "piloni", "tallonatore", "tallonatori", "2 l", "3 l", "seconda linea",
    "terza linea", "9", "10", "centro", "centri", "ala-estremo", "ala", "estremo",
    "avanti", "trequarti", "forwards", "backs",
}

CANONICAL_ROLE_ORDER: List[str] = [
    "Pilone",
    "Tallonatore",
    "Seconda Linea",
    "Terza Linea",
    "Mediano (9)",
    "Apertura (10)",
    "Centro",
    "Ala / Estremo",
    "Altro / N.D.",
]


def _safe_str(val: Any) -> str:
    """Converte in stringa sicura gestendo None e float NaN senza mai sollevare AttributeError."""
    if val is None:
        return ""
    if isinstance(val, (float, np.floating)) and np.isnan(val):
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none") else s


def _norm_col(name: Any) -> str:
    return re.sub(r"\s+", " ", _safe_str(name).replace("\ufeff", "").strip().lower())


def normalize_role_and_department(role_val: Any) -> Tuple[str, str]:
    """
    Normalizza i codici ruolo FIR/GPExe/Catapult (es. 'pilone', '2 l', '3 l', '9', '10',
    'centro', 'ala-estremo', 'tallonatore') in (Ruolo Canonico, Reparto).
    """
    raw_clean = _safe_str(role_val)
    s = re.sub(r"\s+", " ", raw_clean.lower())
    if not s or s in ("nan", "none", "-", "n/d", "n/a", "unassigned", "unassigned role"):
        return "Altro / N.D.", "N/D"

    # Avanti
    if any(k in s for k in ("pilone", "piloni", "prop", "1a linea", "prima linea")):
        return "Pilone", "Avanti"
    if any(k in s for k in ("tallon", "hooker")):
        return "Tallonatore", "Avanti"
    if s in ("2 l", "2l", "2° l", "2a l", "2") or any(k in s for k in ("seconda", "2a linea", "2° linea", "lock")):
        return "Seconda Linea", "Avanti"
    if s in ("3 l", "3l", "3° l", "3a l", "3", "8") or any(k in s for k in ("terza", "3a linea", "3° linea", "flanker", "numero 8", "n.8", "no.8", "back row")):
        return "Terza Linea", "Avanti"
    if any(k in s for k in ("avanti", "forward")):
        return "Avanti (Gen.)", "Avanti"

    # Trequarti
    if s in ("9", "n.9", "no.9") or any(k in s for k in ("mischia", "scrum", "mediano")):
        return "Mediano (9)", "Trequarti"
    if s in ("10", "n.10", "no.10") or any(k in s for k in ("apertura", "fly", "half")):
        return "Apertura (10)", "Trequarti"
    if any(k in s for k in ("centro", "centri", "centre", "center")):
        return "Centro", "Trequarti"
    if any(k in s for k in ("ala", "estremo", "wing", "fullback", "back 3", "back three")):
        return "Ala / Estremo", "Trequarti"
    if any(k in s for k in ("trequarti", "back")):
        return "Trequarti (Gen.)", "Trequarti"

    return str(role_val).strip().title(), "N/D"


def _classify_department(role_val: Any) -> str:
    _, dept = normalize_role_and_department(role_val)
    return dept


def _parse_numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace("%", "", regex=False)
        .str.replace("\xa0", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _parse_duration_to_minutes(val: Any) -> float:
    """Converte durate GPExe/Catapult/Excel (mm:ss, mm:ss:00, hh:mm:ss, frazione giorno, minuti) in minuti float."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    if isinstance(val, (int, float, np.integer, np.floating)):
        fval = float(val)
        if np.isnan(fval) or fval < 0:
            return np.nan
        if 0 < fval < 1:
            if fval <= 0.12:
                return round(fval * 1440.0, 2)
            return round(fval * 60.0, 2)
        return round(fval, 2)

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "-", "n/a"):
        return np.nan
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return round(float(parts[0]) + float(parts[1]) / 60.0, 2)
            if len(parts) == 3:
                p0, p1, p2 = float(parts[0]), float(parts[1]), float(parts[2])
                if p2 == 0 and p0 >= 3 and p1 < 60:
                    return round(p0 + p1 / 60.0, 2)
                return round(p0 * 60.0 + p1 + p2 / 60.0, 2)
        except Exception:
            return np.nan
    try:
        return round(float(s.replace(",", ".")), 2)
    except Exception:
        return np.nan


def _find_col(df_cols: List[str], alias_key: str, df: Optional[pd.DataFrame] = None, require_numeric: bool = False) -> Optional[str]:
    norm_map = {_norm_col(c): c for c in df_cols}
    candidates = DRILL_COL_ALIASES.get(alias_key, [])

    def _has_values(col_name: str) -> bool:
        if df is None or not require_numeric:
            return True
        s = _parse_numeric_series(df[col_name])
        return bool(s.notna().any())

    for cand in candidates:
        if cand in norm_map and _has_values(norm_map[cand]):
            return norm_map[cand]
    for f_norm, orig in norm_map.items():
        for cand in candidates:
            if len(cand) >= 4 and cand in f_norm and _has_values(orig):
                return orig
    return None


def suggest_drill_name_from_file(filename: str, df_raw: Optional[pd.DataFrame] = None) -> str:
    """Propone automaticamente un nome pulito per il drill dal CSV o dal nome file."""
    if df_raw is not None and not df_raw.empty:
        hint_col = _find_col(list(df_raw.columns), "drill_hint")
        if hint_col:
            vals = df_raw[hint_col].dropna().astype(str).str.strip()
            vals = [v for v in vals if v and v.lower() not in ("nan", "none", "unit", "exercise")]
            if vals:
                unique_vals = list(dict.fromkeys(vals))
                if len(unique_vals) == 1 and len(unique_vals[0]) <= 60:
                    return unique_vals[0]

    base = os.path.splitext(os.path.basename(str(filename or "Drill")))[0]
    base = re.sub(r"^(session|drill|export|gpexe)[\s_\-]*", "", base, flags=re.I)
    base = re.sub(r"\d{8}[\-_]\d{4}", "", base)
    base = re.sub(r"[_\-]+", " ", base).strip()
    return base.title() if base else "Drill"


def _read_uploaded_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(_safe_str(filename).lower())[1]
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(io.BytesIO(file_bytes))

    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = file_bytes.decode(enc)
        except Exception:
            continue
        first_line = text.splitlines()[0] if text.splitlines() else ""
        sep = ";" if first_line.count(";") >= first_line.count(",") else ","
        if "\t" in first_line and first_line.count("\t") > max(first_line.count(";"), first_line.count(",")):
            sep = "\t"
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep)
            if df.shape[1] >= 2:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def _detect_active_players(
    work_df: pd.DataFrame,
    min_dist_m: float = DEFAULT_MIN_DIST_M,
    min_wr_mpm: float = DEFAULT_MIN_WR_MPM,
    min_rel_dist_pct: float = DEFAULT_MIN_REL_DIST_PCT,
) -> Tuple[pd.Series, pd.Series]:
    """
    Riconoscimento automatico dei giocatori effettivamente attivi nel drill
    (isolando panchina, rotazioni fuori campo e valori nulli/irrilevanti).

    Criteri:
      1. Distanza nulla / NaN o Durata <= 0 -> Escluso (Nessun dato movimento)
      2. Distanza assoluta < `min_dist_m` (es. <30 m) -> Escluso (Movimento irrilevante / Fuori campo)
      3. Work Rate < `min_wr_mpm` (es. <12 m/min) E Max Speed < 11 km/h E HMPD < 5 m -> Escluso (Panchina / Stazionamento)
      4. Nei drills collettivi (>=4 atleti): se Distanza < `min_rel_dist_pct`% della mediana
         del gruppo attivo E Work Rate < 35% della mediana del gruppo attivo E HMPD < 15 m -> Escluso (Rotazione / Fuori campo)
    """
    n_rows = len(work_df)
    if n_rows == 0:
        return pd.Series(dtype=bool), pd.Series(dtype=str)

    dist = pd.to_numeric(work_df["Total_Distance"], errors="coerce").fillna(0.0)
    dur = pd.to_numeric(work_df["Duration_Min"], errors="coerce").fillna(0.0)
    wr = pd.to_numeric(work_df["Work_Rate"], errors="coerce").fillna(0.0)
    vmax = pd.to_numeric(work_df["Max_Speed"], errors="coerce").fillna(0.0)
    hmpd = pd.to_numeric(work_df["HMPD"], errors="coerce").fillna(0.0)

    # Caso singolo record già pre-aggregato
    if n_rows == 1:
        ok = bool(dist.iloc[0] > 0)
        return pd.Series([ok], index=work_df.index), pd.Series(["" if ok else "Distanza nulla"], index=work_df.index)

    # Calcola mediana robusta escludendo gli zeri puri
    pos_dist = dist[dist >= min_dist_m]
    med_dist = float(pos_dist.median()) if len(pos_dist) >= 3 else 0.0
    pos_wr = wr[dist >= min_dist_m]
    med_wr = float(pos_wr.median()) if len(pos_wr) >= 3 else 0.0

    rel_dist_floor = med_dist * (min_rel_dist_pct / 100.0) if med_dist > 0 else 0.0
    rel_wr_floor = med_wr * 0.35 if med_wr > 0 else 0.0

    is_active_list: List[bool] = []
    reasons_list: List[str] = []

    for idx in work_df.index:
        d_val = float(dist.loc[idx])
        t_val = float(dur.loc[idx])
        w_val = float(wr.loc[idx])
        v_val = float(vmax.loc[idx])
        h_val = float(hmpd.loc[idx])

        if d_val <= 0 or (dur.notna().any() and t_val <= 0):
            is_active_list.append(False)
            reasons_list.append("Valori nulli / Non in campo")
        elif d_val < min_dist_m:
            is_active_list.append(False)
            reasons_list.append(f"Movimento irrilevante ({d_val:.0f}m < {min_dist_m:.0f}m)")
        elif w_val < min_wr_mpm and v_val < 11.0 and h_val < 5.0:
            is_active_list.append(False)
            reasons_list.append(f"Panchina / Stazionamento ({w_val:.1f} m/min, Vmax {v_val:.1f})")
        elif n_rows >= 4 and rel_dist_floor > min_dist_m and d_val < rel_dist_floor and w_val < rel_wr_floor and h_val < 15.0:
            is_active_list.append(False)
            reasons_list.append(f"Rotazione / Fuori campo ({d_val:.0f}m < {min_rel_dist_pct:.0f}% med. {med_dist:.0f}m)")
        else:
            is_active_list.append(True)
            reasons_list.append("")

    # Safeguard: se per soglie estreme risultassero tutti esclusi ma esistono distanze > 0, mantiene quelli con dist > 0
    if not any(is_active_list) and (dist > 0).any():
        is_active_list = [bool(d > 0) for d in dist]
        reasons_list = ["" if ok else "Valori nulli" for ok in is_active_list]

    return pd.Series(is_active_list, index=work_df.index), pd.Series(reasons_list, index=work_df.index)


def _compute_role_summaries(work_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Calcola per ogni ruolo presente nel drill:
      - Numero effettivo di giocatori attivi di quel ruolo (`Active_Players_Count`)
      - Carico Totale del Ruolo (`*_Sum` = somma energetica del ruolo attivo)
      - Media Normalizzata Pro-Capite (`Carico Totale del Ruolo / Active_Players_Count`)
    """
    role_rows: List[Dict[str, Any]] = []
    if work_df.empty:
        return role_rows

    grouped = work_df.groupby(["Role", "Department"], dropna=False)
    for (role_name, dept_name), grp in grouped:
        act = grp[grp["Is_Active"] == True]
        n_act = int(len(act))
        n_exc = int(len(grp) - n_act)
        if n_act == 0:
            continue

        def _sum(c: str) -> float:
            return round(float(pd.to_numeric(act[c], errors="coerce").fillna(0.0).sum()), 2)

        def _norm_avg(c: str) -> float:
            # Media normalizzata esplicita: Somma del Ruolo / Numero Effettivo Atleti Attivi di quel Ruolo
            return round(float(pd.to_numeric(act[c], errors="coerce").fillna(0.0).sum()) / n_act, 2)

        def _max(c: str) -> float:
            s = pd.to_numeric(act[c], errors="coerce").dropna()
            return round(float(s.max()), 2) if not s.empty else 0.0

        dur_avg = _norm_avg("Duration_Min")
        dist_sum = _sum("Total_Distance")
        dist_avg = round(dist_sum / n_act, 2)
        wr_avg = round(dist_avg / dur_avg, 2) if dur_avg > 0 and dist_avg > 0 else _norm_avg("Work_Rate")
        hmpd_sum = _sum("HMPD")
        hmpd_avg = round(hmpd_sum / n_act, 2)
        hsr_sum = _sum("HSR")
        hsr_avg = round(hsr_sum / n_act, 2)
        vhsr_sum = _sum("VHSR")
        dsl_sum = _sum("Dynamic_Stress_Load")
        imp_sum = _sum("Heavy_Impacts")
        acc_sum = _sum("Acc_Events")
        dec_sum = _sum("Dec_Events")

        role_rows.append({
            "Role": str(role_name),
            "Department": str(dept_name),
            "Active_Players_Count": n_act,
            "Excluded_Players_Count": n_exc,
            "Duration_Min": dur_avg,
            "Total_Distance": dist_avg,
            "Work_Rate": wr_avg,
            "HMPD": hmpd_avg,
            "HMPD_per_Min": round(hmpd_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
            "HSR": hsr_avg,
            "HSR_per_Min": round(hsr_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
            "VHSR": round(vhsr_sum / n_act, 2),
            "Max_Speed": _norm_avg("Max_Speed"),
            "Max_Speed_Peak": _max("Max_Speed"),
            "Dynamic_Stress_Load": round(dsl_sum / n_act, 2),
            "Heavy_Impacts": round(imp_sum / n_act, 2),
            "Acc_Events": round(acc_sum / n_act, 2),
            "Dec_Events": round(dec_sum / n_act, 2),
            "Avg_MP": _norm_avg("Avg_MP"),
            "Total_Distance_Sum": dist_sum,
            "HMPD_Sum": hmpd_sum,
            "HSR_Sum": hsr_sum,
            "VHSR_Sum": vhsr_sum,
            "Dynamic_Stress_Load_Sum": dsl_sum,
            "Heavy_Impacts_Sum": imp_sum,
            "Acc_Events_Sum": acc_sum,
            "Dec_Events_Sum": dec_sum,
        })

    order_idx = {r: i for i, r in enumerate(CANONICAL_ROLE_ORDER)}
    role_rows.sort(key=lambda x: (order_idx.get(x["Role"], 99), x["Role"]))
    return role_rows


def _extract_date_from_df(df: pd.DataFrame) -> str:
    """Estrae una data YYYY-MM-DD dalla colonna 'start date/time' o 'date' del CSV se presente."""
    norm_map = {_norm_col(c): c for c in df.columns}
    for key in ("start date/time", "start time", "date", "data", "session date", "session_date"):
        if key in norm_map:
            col = norm_map[key]
            vals = df[col].dropna()
            for v in vals.head(10):
                s = _safe_str(v)
                m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
                if m:
                    return m.group(1)
                m2 = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
                if m2:
                    return f"{m2.group(3)}-{m2.group(2)}-{m2.group(1)}"
    return ""


def _parse_drill_dataframe(
    df: pd.DataFrame,
    filename: str,
    roster_role_map: Optional[Dict[str, Tuple[str, str]]] = None,
    min_dist_m: float = DEFAULT_MIN_DIST_M,
    min_wr_mpm: float = DEFAULT_MIN_WR_MPM,
    min_rel_dist_pct: float = DEFAULT_MIN_REL_DIST_PCT,
    forced_drill_name: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """
    Core parser su un singolo DataFrame (singolo blocco/drill):
      - Rimuove righe di riepilogo GPExe/ruolo (es. 'unassigned role', 'pilone', 'Team', righe con role & starter vuoti)
      - Esegue rilevamento automatico giocatori attivi vs panchina/rotazione
      - Calcola Somme Totali del gruppo attivo + Medie Normalizzate pro-capite + Breakdown per Ruolo.
    """
    if df is None or df.empty:
        raise ValueError(f"Blocco drill vuoto nel file '{filename}'.")

    df = df.copy()
    cols = list(df.columns)
    norm_col_map = {_norm_col(c): c for c in cols}
    suggested_name = _safe_str(forced_drill_name) or suggest_drill_name_from_file(filename, df)

    c_player = _find_col(cols, "player_name")
    c_role = _find_col(cols, "role")
    c_starter = norm_col_map.get("starter")
    c_dur = _find_col(cols, "duration")
    c_dist = _find_col(cols, "total_distance")
    c_wr = _find_col(cols, "work_rate")
    c_hmpd = _find_col(cols, "hmpd")
    c_hsr = _find_col(cols, "hsr")
    c_vhsr = _find_col(cols, "vhsr")
    c_vmax = _find_col(cols, "max_speed", df=df, require_numeric=True)
    c_vpct = _find_col(cols, "max_speed_pct", df=df, require_numeric=True)
    c_dsl = _find_col(cols, "dsl", df=df, require_numeric=True)
    c_imp = _find_col(cols, "heavy_impacts", df=df, require_numeric=True)
    c_acc = _find_col(cols, "acc_events")
    c_dec = _find_col(cols, "dec_events")
    c_mpe = _find_col(cols, "mpe")
    c_amp = _find_col(cols, "avg_mp")

    work_df = pd.DataFrame(index=df.index)
    work_df["Player_Name"] = (
        df[c_player].apply(_safe_str) if c_player else [f"Riga {i+1}" for i in range(len(df))]
    )

    # 1. Filtra righe vuote o righe di riepilogo/ruolo (es. 'unassigned role', 'pilone', 'average', 'Team')
    if c_player:
        mask_valid = (
            work_df["Player_Name"].str.len() > 0
        ) & (
            ~work_df["Player_Name"].str.strip().str.lower().isin(SUMMARY_ROW_LABELS)
        )

        # 2. Filtro strutturale GPExe: nei file GPExe le righe riepilogo di ruolo/squadra in fondo al blocco
        #    hanno sia `role` sia `starter` vuoti/NaN, mentre tutti gli atleti reali hanno almeno uno dei due valorizzato.
        if c_role and c_starter:
            has_role = df[c_role].apply(lambda x: len(_safe_str(x)) > 0)
            has_starter = df[c_starter].apply(lambda x: len(_safe_str(x)) > 0)
            if bool((has_role | has_starter).any()):
                mask_valid = mask_valid & (has_role | has_starter)

        df = df.loc[mask_valid].copy()
        work_df = work_df.loc[mask_valid].copy()

    if df.empty:
        raise ValueError(f"Nessuna riga atleta valida trovata nel file '{filename}'.")

    raw_roles = df[c_role].apply(_safe_str) if c_role else pd.Series([""] * len(df), index=df.index)

    roles_clean: List[str] = []
    depts: List[str] = []
    for pname, rval in zip(work_df["Player_Name"], raw_roles):
        canon_role, dept = normalize_role_and_department(rval)
        if dept == "N/D" and roster_role_map:
            p_key = _norm_col(pname)
            if p_key in roster_role_map:
                r_ros, d_ros = roster_role_map[p_key]
                canon_role, dept = normalize_role_and_department(r_ros)
                if dept == "N/D" and d_ros:
                    dept = _safe_str(d_ros) or "N/D"
        roles_clean.append(canon_role)
        depts.append(dept)
    work_df["Role"] = roles_clean
    work_df["Department"] = depts

    # Durata
    work_df["Duration_Min"] = df[c_dur].apply(_parse_duration_to_minutes) if c_dur else np.nan

    # Distanza Totale
    work_df["Total_Distance"] = _parse_numeric_series(df[c_dist]) if c_dist else np.nan

    # Work Rate (m/min): rigorosamente Distanza / Durata se entrambi validi
    wr_native = _parse_numeric_series(df[c_wr]) if c_wr else pd.Series(np.nan, index=df.index)
    if c_wr and "km/h" in _norm_col(c_wr):
        wr_native = wr_native * (1000.0 / 60.0)
    wr_calc = np.where(
        (work_df["Duration_Min"] > 0) & work_df["Total_Distance"].notna(),
        work_df["Total_Distance"] / work_df["Duration_Min"],
        wr_native,
    )
    work_df["Work_Rate"] = pd.to_numeric(wr_calc, errors="coerce")

    missing_dur = work_df["Duration_Min"].isna() & (work_df["Work_Rate"] > 0) & (work_df["Total_Distance"] > 0)
    work_df.loc[missing_dur, "Duration_Min"] = (
        work_df.loc[missing_dur, "Total_Distance"] / work_df.loc[missing_dur, "Work_Rate"]
    )

    # HMPD
    if c_hmpd:
        work_df["HMPD"] = _parse_numeric_series(df[c_hmpd])
    else:
        mp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("met power z3 (m)", "met power z4 (m)", "met power z5 (m)"))]
        work_df["HMPD"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in mp_cols) if mp_cols else 0.0

    # HSR
    if c_hsr:
        work_df["HSR"] = _parse_numeric_series(df[c_hsr])
    else:
        sp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("speed z4 (m)", "speed z5 (m)", "speed z6 (m)"))]
        work_df["HSR"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in sp_cols) if sp_cols else 0.0

    # VHSR
    if c_vhsr:
        work_df["VHSR"] = _parse_numeric_series(df[c_vhsr])
    else:
        vsp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("speed z5 (m)", "speed z6 (m)"))]
        work_df["VHSR"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in vsp_cols) if vsp_cols else 0.0

    work_df["Max_Speed"] = _parse_numeric_series(df[c_vmax]) if c_vmax else 0.0
    work_df["Max_Speed_Pct"] = _parse_numeric_series(df[c_vpct]) if c_vpct else 0.0
    work_df["Dynamic_Stress_Load"] = _parse_numeric_series(df[c_dsl]) if c_dsl else 0.0
    work_df["Heavy_Impacts"] = _parse_numeric_series(df[c_imp]) if c_imp else 0.0
    work_df["Acc_Events"] = _parse_numeric_series(df[c_acc]) if c_acc else 0.0
    work_df["Dec_Events"] = _parse_numeric_series(df[c_dec]) if c_dec else 0.0
    work_df["Met_Power_Events"] = _parse_numeric_series(df[c_mpe]) if c_mpe else 0.0
    work_df["Avg_MP"] = _parse_numeric_series(df[c_amp]) if c_amp else 0.0

    # 1. Riconoscimento Automatico Giocatori Attivi vs Fuori Campo/Rotazione
    is_act_s, excl_reason_s = _detect_active_players(
        work_df,
        min_dist_m=min_dist_m,
        min_wr_mpm=min_wr_mpm,
        min_rel_dist_pct=min_rel_dist_pct,
    )
    work_df["Is_Active"] = is_act_s
    work_df["Exclusion_Reason"] = excl_reason_s

    active_df = work_df[work_df["Is_Active"] == True].copy()
    n_raw = int(len(work_df))
    n_active = int(len(active_df))
    n_excluded = int(n_raw - n_active)

    # 2. Normalizzazione Dinamica sul Numero Effettivo di Atleti Attivi (`n_active`)
    def _act_sum(col_name: str) -> float:
        if active_df.empty:
            return 0.0
        return round(float(pd.to_numeric(active_df[col_name], errors="coerce").fillna(0.0).sum()), 2)

    def _act_norm_avg(col_name: str) -> float:
        if n_active <= 0:
            return 0.0
        return round(float(pd.to_numeric(active_df[col_name], errors="coerce").fillna(0.0).sum()) / n_active, 2)

    def _act_max(col_name: str) -> float:
        if active_df.empty:
            return 0.0
        s = pd.to_numeric(active_df[col_name], errors="coerce").dropna()
        return round(float(s.max()), 2) if not s.empty else 0.0

    dur_avg = _act_norm_avg("Duration_Min")
    dist_sum = _act_sum("Total_Distance")
    dist_avg = round(dist_sum / n_active, 2) if n_active > 0 else 0.0
    wr_avg = round(dist_avg / dur_avg, 2) if dur_avg > 0 and dist_avg > 0 else _act_norm_avg("Work_Rate")
    hmpd_sum = _act_sum("HMPD")
    hmpd_avg = round(hmpd_sum / n_active, 2) if n_active > 0 else 0.0
    hsr_sum = _act_sum("HSR")
    hsr_avg = round(hsr_sum / n_active, 2) if n_active > 0 else 0.0
    vhsr_sum = _act_sum("VHSR")
    dsl_sum = _act_sum("Dynamic_Stress_Load")
    imp_sum = _act_sum("Heavy_Impacts")
    acc_sum = _act_sum("Acc_Events")
    dec_sum = _act_sum("Dec_Events")
    mpe_sum = _act_sum("Met_Power_Events")

    # Split Reparti (solo atleti attivi di ciascun reparto!)
    av_df = active_df[active_df["Department"] == "Avanti"]
    tq_df = active_df[active_df["Department"] == "Trequarti"]
    n_av = int(len(av_df))
    n_tq = int(len(tq_df))

    def _sub_sum(sub: pd.DataFrame, col_name: str) -> float:
        if sub.empty:
            return 0.0
        return round(float(pd.to_numeric(sub[col_name], errors="coerce").fillna(0.0).sum()), 2)

    def _sub_avg(sub: pd.DataFrame, col_name: str) -> float:
        if sub.empty:
            return 0.0
        return round(float(pd.to_numeric(sub[col_name], errors="coerce").fillna(0.0).sum()) / len(sub), 2)

    av_dist_sum = _sub_sum(av_df, "Total_Distance")
    tq_dist_sum = _sub_sum(tq_df, "Total_Distance")
    av_hmpd_sum = _sub_sum(av_df, "HMPD")
    tq_hmpd_sum = _sub_sum(tq_df, "HMPD")
    av_hsr_sum = _sub_sum(av_df, "HSR")
    tq_hsr_sum = _sub_sum(tq_df, "HSR")
    av_dsl_sum = _sub_sum(av_df, "Dynamic_Stress_Load")
    tq_dsl_sum = _sub_sum(tq_df, "Dynamic_Stress_Load")

    summary_rec: Dict[str, Any] = {
        "Source_File": filename,
        "Players_Count": n_active,
        "Active_Players_Count": n_active,
        "Excluded_Players_Count": n_excluded,
        "Raw_Players_Count": n_raw,
        "Duration_Min": dur_avg,
        # Medie Normalizzate Pro-Capite (Atleti Attivi)
        "Total_Distance": dist_avg,
        "Work_Rate": wr_avg,
        "HMPD": hmpd_avg,
        "HMPD_per_Min": round(hmpd_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
        "HSR": hsr_avg,
        "HSR_per_Min": round(hsr_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
        "VHSR": round(vhsr_sum / n_active, 2) if n_active > 0 else 0.0,
        "Max_Speed": _act_norm_avg("Max_Speed"),
        "Max_Speed_Peak": _act_max("Max_Speed"),
        "Max_Speed_Pct": _act_norm_avg("Max_Speed_Pct"),
        "Dynamic_Stress_Load": round(dsl_sum / n_active, 2) if n_active > 0 else 0.0,
        "Heavy_Impacts": round(imp_sum / n_active, 2) if n_active > 0 else 0.0,
        "Acc_Events": round(acc_sum / n_active, 2) if n_active > 0 else 0.0,
        "Dec_Events": round(dec_sum / n_active, 2) if n_active > 0 else 0.0,
        "Met_Power_Events": round(mpe_sum / n_active, 2) if n_active > 0 else 0.0,
        "Avg_MP": _act_norm_avg("Avg_MP"),
        # Somme Totali del Gruppo Attivo
        "Total_Distance_Sum": dist_sum,
        "HMPD_Sum": hmpd_sum,
        "HSR_Sum": hsr_sum,
        "VHSR_Sum": vhsr_sum,
        "Dynamic_Stress_Load_Sum": dsl_sum,
        "Heavy_Impacts_Sum": imp_sum,
        "Acc_Events_Sum": acc_sum,
        "Dec_Events_Sum": dec_sum,
        "Met_Power_Events_Sum": mpe_sum,
        # Reparti Avanti vs Trequarti
        "Avanti_Active_Count": n_av,
        "Trequarti_Active_Count": n_tq,
        "Avanti_Work_Rate": _sub_avg(av_df, "Work_Rate"),
        "Trequarti_Work_Rate": _sub_avg(tq_df, "Work_Rate"),
        "Avanti_Total_Distance": round(av_dist_sum / n_av, 2) if n_av > 0 else 0.0,
        "Trequarti_Total_Distance": round(tq_dist_sum / n_tq, 2) if n_tq > 0 else 0.0,
        "Avanti_Total_Distance_Sum": av_dist_sum,
        "Trequarti_Total_Distance_Sum": tq_dist_sum,
        "Avanti_HMPD": round(av_hmpd_sum / n_av, 2) if n_av > 0 else 0.0,
        "Trequarti_HMPD": round(tq_hmpd_sum / n_tq, 2) if n_tq > 0 else 0.0,
        "Avanti_HMPD_Sum": av_hmpd_sum,
        "Trequarti_HMPD_Sum": tq_hmpd_sum,
        "Avanti_HSR": round(av_hsr_sum / n_av, 2) if n_av > 0 else 0.0,
        "Trequarti_HSR": round(tq_hsr_sum / n_tq, 2) if n_tq > 0 else 0.0,
        "Avanti_HSR_Sum": av_hsr_sum,
        "Trequarti_HSR_Sum": tq_hsr_sum,
        "Avanti_DSL": round(av_dsl_sum / n_av, 2) if n_av > 0 else 0.0,
        "Trequarti_DSL": round(tq_dsl_sum / n_tq, 2) if n_tq > 0 else 0.0,
        "Avanti_DSL_Sum": av_dsl_sum,
        "Trequarti_DSL_Sum": tq_dsl_sum,
    }

    # 3. Riepilogo Normalizzato per Singolo Ruolo
    role_records = _compute_role_summaries(work_df) if (c_player and len(work_df) > 1) else []

    # 4. Dettaglio Individuale Atleti (tutti, con flag Is_Active + motivo esclusione)
    player_records: List[Dict[str, Any]] = []
    if c_player and len(work_df) > 1:
        for _, r in work_df.iterrows():
            player_records.append({
                "Player_Name": str(r["Player_Name"]),
                "Role": str(r["Role"]),
                "Department": str(r["Department"]),
                "Is_Active": bool(r["Is_Active"]),
                "Exclusion_Reason": str(r["Exclusion_Reason"]),
                "Duration_Min": round(float(r["Duration_Min"]), 2) if pd.notna(r["Duration_Min"]) else 0.0,
                "Total_Distance": round(float(r["Total_Distance"]), 2) if pd.notna(r["Total_Distance"]) else 0.0,
                "Work_Rate": round(float(r["Work_Rate"]), 2) if pd.notna(r["Work_Rate"]) else 0.0,
                "HMPD": round(float(r["HMPD"]), 2) if pd.notna(r["HMPD"]) else 0.0,
                "HSR": round(float(r["HSR"]), 2) if pd.notna(r["HSR"]) else 0.0,
                "VHSR": round(float(r["VHSR"]), 2) if pd.notna(r["VHSR"]) else 0.0,
                "Max_Speed": round(float(r["Max_Speed"]), 2) if pd.notna(r["Max_Speed"]) else 0.0,
                "Max_Speed_Pct": round(float(r["Max_Speed_Pct"]), 2) if pd.notna(r["Max_Speed_Pct"]) else 0.0,
                "Dynamic_Stress_Load": round(float(r["Dynamic_Stress_Load"]), 2) if pd.notna(r["Dynamic_Stress_Load"]) else 0.0,
                "Heavy_Impacts": round(float(r["Heavy_Impacts"]), 2) if pd.notna(r["Heavy_Impacts"]) else 0.0,
                "Acc_Events": round(float(r["Acc_Events"]), 2) if pd.notna(r["Acc_Events"]) else 0.0,
                "Dec_Events": round(float(r["Dec_Events"]), 2) if pd.notna(r["Dec_Events"]) else 0.0,
                "Met_Power_Events": round(float(r["Met_Power_Events"]), 2) if pd.notna(r["Met_Power_Events"]) else 0.0,
                "Avg_MP": round(float(r["Avg_MP"]), 2) if pd.notna(r["Avg_MP"]) else 0.0,
            })

    return summary_rec, player_records, role_records, suggested_name


def parse_drill_file_multi(
    file_bytes: bytes,
    filename: str,
    roster_role_map: Optional[Dict[str, Tuple[str, str]]] = None,
    min_dist_m: float = DEFAULT_MIN_DIST_M,
    min_wr_mpm: float = DEFAULT_MIN_WR_MPM,
    min_rel_dist_pct: float = DEFAULT_MIN_REL_DIST_PCT,
) -> Tuple[List[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], str]], Dict[str, Any]]:
    """
    Parser intelligente single-drill & multi-drill (GPExe / Catapult / CSV generici).
    - Se il CSV è un export multi-blocco GPExe con colonna `type` ('S' = totale seduta, 'D' = singoli drills):
      esclude automaticamente il riepilogo `type == 'S'` (evitando doppi conteggi) e separa automaticamente
      ciascun drill (`type == 'D'`) in ordine cronologico (es. 'collettivo 1', 'collettivo 2', 'collettivo 3').
    - Se il CSV contiene più blocchi/periodi distinti (es. colonna `notes`, `Period Name`, `Drill Name`):
      li separa automaticamente in drills individuali.
    - Se il CSV è un singolo drill: restituisce una lista di 1 elemento.
    """
    df_raw = _read_uploaded_dataframe(file_bytes, filename)
    if df_raw.empty:
        raise ValueError(f"Il file '{filename}' risulta vuoto o non leggibile.")

    cols = list(df_raw.columns)
    norm_map = {_norm_col(c): c for c in cols}
    detected_date = _extract_date_from_df(df_raw)

    file_meta: Dict[str, Any] = {
        "is_multi_drill": False,
        "skipped_session_summary": False,
        "skipped_session_label": "",
        "detected_session_date": detected_date,
        "detected_drill_names": [],
    }

    df_work = df_raw.copy()

    # 1. Rilevamento GPExe `type` ('S' = Sessione intera, 'D' = Drill)
    c_type = norm_map.get("type") or norm_map.get("record type") or norm_map.get("row type")
    has_type_d = False
    if c_type:
        t_vals = df_work[c_type].apply(lambda x: _safe_str(x).upper())
        if bool((t_vals == "D").any()):
            has_type_d = True
            if bool((t_vals == "S").any()):
                file_meta["skipped_session_summary"] = True
                s_df = df_work.loc[t_vals == "S"]
                c_hint_s = _find_col(cols, "drill_hint")
                if c_hint_s:
                    s_labels = [_safe_str(v) for v in s_df[c_hint_s].tolist() if _safe_str(v)]
                    if s_labels:
                        file_meta["skipped_session_label"] = s_labels[0]
            df_work = df_work.loc[t_vals == "D"].copy()

    # 2. Rilevamento blocchi multipli (per colonna drill/period/notes + start date/time)
    c_split = None
    for cand in ("drill_name", "drill name", "drill", "period name", "period", "split", "blocco", "notes"):
        if cand in norm_map:
            non_empty = [v for v in df_work[norm_map[cand]].apply(_safe_str).tolist() if v and v.lower() not in ("unit", "exercise")]
            if non_empty:
                c_split = norm_map[cand]
                break

    c_start = norm_map.get("start date/time") or norm_map.get("start time")

    drill_slices: List[Tuple[str, pd.DataFrame]] = []
    if c_split is not None:
        split_labels = df_work[c_split].apply(_safe_str)
        start_labels = df_work[c_start].apply(_safe_str) if c_start else pd.Series([""] * len(df_work), index=df_work.index)

        # Chiave di blocco = (label, start_time) preservando ordine di comparsa o ordine cronologico
        block_keys_in_order: List[Tuple[str, str]] = []
        seen_keys = set()
        for lbl, st_t in zip(split_labels, start_labels):
            if not lbl or lbl.lower() in ("unit", "exercise"):
                continue
            k = (lbl, st_t)
            if k not in seen_keys:
                seen_keys.add(k)
                block_keys_in_order.append(k)

        # Se esistono almeno 2 blocchi distinti e ciascun blocco rappresenta un vero drill (non note per singolo atleta)
        if len(block_keys_in_order) >= 2:
            # Ordina cronologicamente se c_start è valorizzato
            if c_start and all(bool(k[1]) for k in block_keys_in_order):
                block_keys_in_order.sort(key=lambda k: k[1])

            group_sizes = []
            for lbl, st_t in block_keys_in_order:
                m_blk = (split_labels == lbl) & (start_labels == st_t)
                group_sizes.append(int(m_blk.sum()))

            is_genuine_multi = has_type_d or (max(group_sizes) >= 2 and len(block_keys_in_order) <= max(2, int(len(df_work) * 0.5)))
            if is_genuine_multi:
                # Conta occorrenze dello stesso nome per numerare eventuali blocchi omonimi (es. 'collettivo (1)', '(2)')
                lbl_totals: Dict[str, int] = {}
                for lbl, _ in block_keys_in_order:
                    lbl_totals[lbl] = lbl_totals.get(lbl, 0) + 1
                lbl_seen: Dict[str, int] = {}

                for lbl, st_t in block_keys_in_order:
                    m_blk = (split_labels == lbl) & (start_labels == st_t)
                    sub_df = df_work.loc[m_blk].copy()
                    if lbl_totals[lbl] > 1:
                        lbl_seen[lbl] = lbl_seen.get(lbl, 0) + 1
                        display_lbl = f"{lbl} ({lbl_seen[lbl]})"
                    else:
                        display_lbl = lbl
                    drill_slices.append((display_lbl, sub_df))

    if not drill_slices:
        # Singolo drill (eventualmente già filtrato su type=='D')
        single_hint = None
        if c_split is not None:
            uniq_lbls = list(dict.fromkeys(v for v in df_work[c_split].apply(_safe_str).tolist() if v and v.lower() not in ("unit", "exercise")))
            if len(uniq_lbls) == 1 and len(uniq_lbls[0]) <= 60:
                single_hint = uniq_lbls[0]
        drill_slices = [(single_hint or suggest_drill_name_from_file(filename, df_work), df_work)]

    parsed_results: List[Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], str]] = []
    for lbl, sub_df in drill_slices:
        try:
            res = _parse_drill_dataframe(
                sub_df,
                filename=filename,
                roster_role_map=roster_role_map,
                min_dist_m=min_dist_m,
                min_wr_mpm=min_wr_mpm,
                min_rel_dist_pct=min_rel_dist_pct,
                forced_drill_name=lbl,
            )
            parsed_results.append(res)
            file_meta["detected_drill_names"].append(res[3])
        except ValueError:
            continue

    if not parsed_results:
        raise ValueError(f"Nessuna riga atleta valida trovata nel file '{filename}'.")

    file_meta["is_multi_drill"] = (len(parsed_results) > 1) or bool(file_meta["skipped_session_summary"])
    return parsed_results, file_meta


def parse_drill_file(
    file_bytes: bytes,
    filename: str,
    roster_role_map: Optional[Dict[str, Tuple[str, str]]] = None,
    min_dist_m: float = DEFAULT_MIN_DIST_M,
    min_wr_mpm: float = DEFAULT_MIN_WR_MPM,
    min_rel_dist_pct: float = DEFAULT_MIN_REL_DIST_PCT,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Wrapper retro-compatibile per singolo file CSV/Excel: restituisce il primo drill estratto."""
    parsed_list, _ = parse_drill_file_multi(
        file_bytes=file_bytes,
        filename=filename,
        roster_role_map=roster_role_map,
        min_dist_m=min_dist_m,
        min_wr_mpm=min_wr_mpm,
        min_rel_dist_pct=min_rel_dist_pct,
    )
    return parsed_list[0]


def _empty_master_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DRILLS_MASTER_COLUMNS)


def _empty_players_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DRILLS_PLAYERS_COLUMNS)


def _empty_roles_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DRILLS_ROLES_COLUMNS)


def _load_drills_master_uncached() -> pd.DataFrame:
    df = cloud_storage.load_parquet_with_cloud_sync("drills_master", DRILLS_MASTER_PATH)
    if df is None or df.empty:
        return _empty_master_df()
    str_cols = {"Session_Date", "Session_Name", "Drill_Name", "Source_File", "Updated_At"}
    for col in DRILLS_MASTER_COLUMNS:
        if col not in df.columns:
            if col == "Active_Players_Count" and "Players_Count" in df.columns:
                df[col] = df["Players_Count"]
            elif col == "Raw_Players_Count" and "Players_Count" in df.columns:
                df[col] = df["Players_Count"]
            elif col.endswith("_Sum") and col[:-4] in df.columns and "Players_Count" in df.columns:
                df[col] = (pd.to_numeric(df[col[:-4]], errors="coerce").fillna(0.0) * pd.to_numeric(df["Players_Count"], errors="coerce").fillna(1.0)).round(2)
            else:
                df[col] = "" if col in str_cols else 0.0
    df["Session_Date"] = df["Session_Date"].astype(str).str.slice(0, 10)
    df["Session_Name"] = df["Session_Name"].astype(str).str.strip()
    df["Drill_Name"] = df["Drill_Name"].astype(str).str.strip()
    df["Drill_Order"] = pd.to_numeric(df["Drill_Order"], errors="coerce").fillna(1).astype(int)
    for ic in ("Players_Count", "Active_Players_Count", "Excluded_Players_Count", "Raw_Players_Count", "Avanti_Active_Count", "Trequarti_Active_Count"):
        df[ic] = pd.to_numeric(df[ic], errors="coerce").fillna(0).astype(int)
    return df[DRILLS_MASTER_COLUMNS].sort_values(
        by=["Session_Date", "Session_Name", "Drill_Order"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def _load_drills_roles_uncached() -> pd.DataFrame:
    df = cloud_storage.load_parquet_with_cloud_sync("drills_roles_summary", DRILLS_ROLES_PATH)
    if df is None or df.empty:
        return _empty_roles_df()
    str_cols = {"Session_Date", "Session_Name", "Drill_Name", "Role", "Department"}
    for col in DRILLS_ROLES_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col in str_cols else 0.0
    df["Session_Date"] = df["Session_Date"].astype(str).str.slice(0, 10)
    df["Session_Name"] = df["Session_Name"].astype(str).str.strip()
    df["Drill_Name"] = df["Drill_Name"].astype(str).str.strip()
    df["Drill_Order"] = pd.to_numeric(df["Drill_Order"], errors="coerce").fillna(1).astype(int)
    df["Active_Players_Count"] = pd.to_numeric(df["Active_Players_Count"], errors="coerce").fillna(0).astype(int)
    df["Excluded_Players_Count"] = pd.to_numeric(df["Excluded_Players_Count"], errors="coerce").fillna(0).astype(int)
    return df[DRILLS_ROLES_COLUMNS].reset_index(drop=True)


def _load_drills_players_uncached() -> pd.DataFrame:
    df = cloud_storage.load_parquet_with_cloud_sync("drills_players_detail", DRILLS_PLAYERS_PATH)
    if df is None or df.empty:
        return _empty_players_df()
    str_cols = {"Session_Date", "Session_Name", "Drill_Name", "Player_Name", "Role", "Department", "Exclusion_Reason"}
    for col in DRILLS_PLAYERS_COLUMNS:
        if col not in df.columns:
            if col == "Is_Active":
                df[col] = True
            else:
                df[col] = "" if col in str_cols else 0.0
    df["Session_Date"] = df["Session_Date"].astype(str).str.slice(0, 10)
    df["Session_Name"] = df["Session_Name"].astype(str).str.strip()
    df["Drill_Name"] = df["Drill_Name"].astype(str).str.strip()
    df["Drill_Order"] = pd.to_numeric(df["Drill_Order"], errors="coerce").fillna(1).astype(int)
    df["Is_Active"] = df["Is_Active"].astype(bool)
    return df[DRILLS_PLAYERS_COLUMNS].reset_index(drop=True)


if st is not None:
    @st.cache_data(ttl=3600)
    def load_drills_master() -> pd.DataFrame:
        return _load_drills_master_uncached()

    @st.cache_data(ttl=3600)
    def load_drills_roles_summary() -> pd.DataFrame:
        return _load_drills_roles_uncached()

    @st.cache_data(ttl=3600)
    def load_drills_players_detail() -> pd.DataFrame:
        return _load_drills_players_uncached()
else:
    def load_drills_master() -> pd.DataFrame:
        return _load_drills_master_uncached()

    def load_drills_roles_summary() -> pd.DataFrame:
        return _load_drills_roles_uncached()

    def load_drills_players_detail() -> pd.DataFrame:
        return _load_drills_players_uncached()


def session_exists_in_drills(session_date: str, session_name: str) -> int:
    """Ritorna il numero di drill già archiviati per quella (Session_Date, Session_Name)."""
    df = load_drills_master()
    if df.empty:
        return 0
    s_date = str(session_date).strip()[:10]
    s_name_norm = str(session_name).strip().lower()
    mask = (df["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
        df["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
    )
    return int(mask.sum())


def upsert_session_drills(
    session_date: str,
    session_name: str,
    drill_records: List[Dict[str, Any]],
    player_records: Optional[List[Dict[str, Any]]] = None,
    role_records: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[int, int]:
    """
    Logica di Upsert atomica (Prevenzione Duplicati) su:
      - `drills_master.parquet`
      - `drills_roles_summary.parquet`
      - `drills_players_detail.parquet`
    con sincronizzazione Cloud Storage e `st.cache_data.clear()`.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    s_date = str(session_date).strip()[:10]
    s_name = str(session_name).strip()
    s_name_norm = s_name.lower()
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Upsert drills_master.parquet
    df_existing = _load_drills_master_uncached()
    removed_count = 0
    if not df_existing.empty:
        mask_old = (df_existing["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
            df_existing["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
        )
        removed_count = int(mask_old.sum())
        df_existing = df_existing.loc[~mask_old].copy()

    enriched_rows = []
    for rec in sorted(drill_records, key=lambda x: int(x.get("Drill_Order", 1))):
        row = {col: 0.0 for col in DRILLS_MASTER_COLUMNS}
        row.update(rec)
        row["Session_Date"] = s_date
        row["Session_Name"] = s_name
        row["Drill_Name"] = str(rec.get("Drill_Name", "Drill")).strip()
        row["Drill_Order"] = int(rec.get("Drill_Order", 1))
        act_c = int(rec.get("Active_Players_Count", rec.get("Players_Count", 1)))
        row["Players_Count"] = act_c
        row["Active_Players_Count"] = act_c
        row["Excluded_Players_Count"] = int(rec.get("Excluded_Players_Count", 0))
        row["Raw_Players_Count"] = int(rec.get("Raw_Players_Count", act_c))
        row["Avanti_Active_Count"] = int(rec.get("Avanti_Active_Count", 0))
        row["Trequarti_Active_Count"] = int(rec.get("Trequarti_Active_Count", 0))
        row["Source_File"] = str(rec.get("Source_File", ""))
        row["Updated_At"] = now_iso
        enriched_rows.append(row)

    df_new = pd.DataFrame(enriched_rows, columns=DRILLS_MASTER_COLUMNS)
    df_merged = pd.concat([df_existing, df_new], ignore_index=True) if not df_existing.empty else df_new
    df_merged = df_merged.sort_values(
        by=["Session_Date", "Session_Name", "Drill_Order"],
        ascending=[False, True, True],
    ).reset_index(drop=True)
    cloud_storage.save_parquet_with_cloud_sync("drills_master", df_merged, DRILLS_MASTER_PATH)

    # 2. Upsert drills_roles_summary.parquet
    df_r_existing = _load_drills_roles_uncached()
    if not df_r_existing.empty:
        mask_r_old = (df_r_existing["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
            df_r_existing["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
        )
        df_r_existing = df_r_existing.loc[~mask_r_old].copy()

    if role_records:
        r_rows = []
        for rrec in role_records:
            rrow = {col: 0.0 for col in DRILLS_ROLES_COLUMNS}
            rrow.update(rrec)
            rrow["Session_Date"] = s_date
            rrow["Session_Name"] = s_name
            rrow["Drill_Name"] = str(rrec.get("Drill_Name", "Drill")).strip()
            rrow["Drill_Order"] = int(rrec.get("Drill_Order", 1))
            rrow["Role"] = str(rrec.get("Role", "Altro / N.D.")).strip()
            rrow["Department"] = str(rrec.get("Department", "N/D")).strip()
            rrow["Active_Players_Count"] = int(rrec.get("Active_Players_Count", 0))
            rrow["Excluded_Players_Count"] = int(rrec.get("Excluded_Players_Count", 0))
            r_rows.append(rrow)
        df_r_new = pd.DataFrame(r_rows, columns=DRILLS_ROLES_COLUMNS)
        df_r_merged = pd.concat([df_r_existing, df_r_new], ignore_index=True) if not df_r_existing.empty else df_r_new
        cloud_storage.save_parquet_with_cloud_sync("drills_roles_summary", df_r_merged, DRILLS_ROLES_PATH)
    elif removed_count > 0:
        cloud_storage.save_parquet_with_cloud_sync("drills_roles_summary", df_r_existing, DRILLS_ROLES_PATH)

    # 3. Upsert drills_players_detail.parquet
    df_p_existing = _load_drills_players_uncached()
    if not df_p_existing.empty:
        mask_p_old = (df_p_existing["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
            df_p_existing["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
        )
        df_p_existing = df_p_existing.loc[~mask_p_old].copy()

    if player_records:
        p_rows = []
        for prec in player_records:
            prow = {col: 0.0 for col in DRILLS_PLAYERS_COLUMNS}
            prow.update(prec)
            prow["Session_Date"] = s_date
            prow["Session_Name"] = s_name
            prow["Drill_Name"] = str(prec.get("Drill_Name", "Drill")).strip()
            prow["Drill_Order"] = int(prec.get("Drill_Order", 1))
            prow["Player_Name"] = str(prec.get("Player_Name", "")).strip()
            prow["Role"] = str(prec.get("Role", "")).strip()
            prow["Department"] = str(prec.get("Department", "N/D")).strip()
            prow["Is_Active"] = bool(prec.get("Is_Active", True))
            prow["Exclusion_Reason"] = str(prec.get("Exclusion_Reason", "")).strip()
            p_rows.append(prow)
        df_p_new = pd.DataFrame(p_rows, columns=DRILLS_PLAYERS_COLUMNS)
        df_p_merged = pd.concat([df_p_existing, df_p_new], ignore_index=True) if not df_p_existing.empty else df_p_new
        cloud_storage.save_parquet_with_cloud_sync("drills_players_detail", df_p_merged, DRILLS_PLAYERS_PATH)
    elif removed_count > 0:
        cloud_storage.save_parquet_with_cloud_sync("drills_players_detail", df_p_existing, DRILLS_PLAYERS_PATH)

    if st is not None:
        st.cache_data.clear()

    return removed_count, len(enriched_rows)


def delete_session_drills(session_date: str, session_name: str) -> int:
    """Elimina tutti i drill associati a una specifica (Session_Date, Session_Name) su tutti e 3 i file Parquet."""
    s_date = str(session_date).strip()[:10]
    s_name_norm = str(session_name).strip().lower()

    df_existing = _load_drills_master_uncached()
    if df_existing.empty:
        return 0
    mask_old = (df_existing["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
        df_existing["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
    )
    removed = int(mask_old.sum())
    if removed == 0:
        return 0

    df_clean = df_existing.loc[~mask_old].reset_index(drop=True)
    cloud_storage.save_parquet_with_cloud_sync("drills_master", df_clean, DRILLS_MASTER_PATH)

    for tbl_name, path_val, loader in [
        ("drills_roles_summary", DRILLS_ROLES_PATH, _load_drills_roles_uncached),
        ("drills_players_detail", DRILLS_PLAYERS_PATH, _load_drills_players_uncached),
    ]:
        df_sub = loader()
        if not df_sub.empty:
            mask_s = (df_sub["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
                df_sub["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
            )
            cloud_storage.save_parquet_with_cloud_sync(tbl_name, df_sub.loc[~mask_s].reset_index(drop=True), path_val)

    if st is not None:
        st.cache_data.clear()

    return removed


def get_drills_summary_stats() -> Dict[str, int]:
    """Statistiche rapide per la sidebar dello stato database."""
    df = load_drills_master()
    if df.empty:
        return {"total_drills": 0, "unique_drills": 0, "total_sessions": 0}
    sessions_cnt = df[["Session_Date", "Session_Name"]].drop_duplicates().shape[0]
    return {
        "total_drills": int(len(df)),
        "unique_drills": int(df["Drill_Name"].nunique()),
        "total_sessions": int(sessions_cnt),
    }
