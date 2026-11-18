# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Modulo di gestione persistenza, parsing multi-formato (GPExe / Catapult / CSV generici)
e logica di Upsert per l'archivio indipendente `drills_master.parquet`
(e dettaglio atleti opzionale `drills_players_detail.parquet`) della FIR GPS Analytics Platform.
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

DRILLS_MASTER_COLUMNS: List[str] = [
    "Session_Date",
    "Session_Name",
    "Drill_Name",
    "Drill_Order",
    "Source_File",
    "Players_Count",
    "Duration_Min",
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
    "Avanti_Work_Rate",
    "Trequarti_Work_Rate",
    "Avanti_HMPD",
    "Trequarti_HMPD",
    "Avanti_HSR",
    "Trequarti_HSR",
    "Updated_At",
]

DRILLS_PLAYERS_COLUMNS: List[str] = [
    "Session_Date",
    "Session_Name",
    "Drill_Name",
    "Drill_Order",
    "Player_Name",
    "Role",
    "Department",
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

# Alias completi per riconoscimento automatico colonne da export GPExe FIR, Benetton, Catapult/Zebre e CSV custom
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

AVANTI_KEYWORDS = (
    "pilone", "tallonatore", "seconda", "terza", "flanker", "numero 8",
    "avanti", "forward", "prop", "hooker", "lock", "back row", "n.8", "no.8",
)
TREQUARTI_KEYWORDS = (
    "mediano", "apertura", "centro", "ala", "estremo", "trequarti",
    "back", "scrum", "fly", "centre", "center", "wing", "fullback",
)


def _norm_col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").replace("\ufeff", "").strip().lower())


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
        # Frazione giorno Excel (es. 0.26666 -> 0.26666 * 60 o * 1440; in GPExe Excel export mm:ss come frazione ore/giorno)
        if 0 < fval < 1:
            # In GPExe export Excel `duration (mm:ss)` talvolta salva 16 min come 16/60 = 0.2666 oppure 16/1440 = 0.0111
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
                # Formato GPExe/Excel esportato come mm:ss:00 quando p2 == 0 e p0 >= 3
                if p2 == 0 and p0 >= 3 and p1 < 60:
                    return round(p0 + p1 / 60.0, 2)
                return round(p0 * 60.0 + p1 + p2 / 60.0, 2)
        except Exception:
            return np.nan
    try:
        return round(float(s.replace(",", ".")), 2)
    except Exception:
        return np.nan


def _find_col(df_cols: List[str], alias_key: str) -> Optional[str]:
    norm_map = {_norm_col(c): c for c in df_cols}
    candidates = DRILL_COL_ALIASES.get(alias_key, [])
    for cand in candidates:
        if cand in norm_map:
            return norm_map[cand]
    for f_norm, orig in norm_map.items():
        for cand in candidates:
            if len(cand) >= 4 and cand in f_norm:
                return orig
    return None


def _classify_department(role_val: Any) -> str:
    s = str(role_val or "").strip().lower()
    if not s:
        return "N/D"
    if any(k in s for k in AVANTI_KEYWORDS):
        return "Avanti"
    if any(k in s for k in TREQUARTI_KEYWORDS):
        return "Trequarti"
    return "N/D"


def suggest_drill_name_from_file(filename: str, df_raw: Optional[pd.DataFrame] = None) -> str:
    """Propone automaticamente un nome pulito per il drill dal CSV o dal nome file."""
    if df_raw is not None and not df_raw.empty:
        hint_col = _find_col(list(df_raw.columns), "drill_hint")
        if hint_col:
            vals = (
                df_raw[hint_col]
                .dropna()
                .astype(str)
                .str.strip()
            )
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
    ext = os.path.splitext(filename.lower())[1]
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


def parse_drill_file(
    file_bytes: bytes,
    filename: str,
    roster_role_map: Optional[Dict[str, Tuple[str, str]]] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """
    Analizza un file CSV/Excel di un singolo drill e restituisce:
      1. Dizionario aggregato del drill (metriche GPS/VBT standard pronte per `drills_master.parquet`)
      2. Lista di dizionari per-atleta (per `drills_players_detail.parquet`)
      3. Nome suggerito del drill
    """
    df = _read_uploaded_dataframe(file_bytes, filename)
    if df.empty:
        raise ValueError(f"Il file '{filename}' risulta vuoto o non leggibile.")

    cols = list(df.columns)
    suggested_name = suggest_drill_name_from_file(filename, df)

    c_player = _find_col(cols, "player_name")
    c_role = _find_col(cols, "role")
    c_dur = _find_col(cols, "duration")
    c_dist = _find_col(cols, "total_distance")
    c_wr = _find_col(cols, "work_rate")
    c_hmpd = _find_col(cols, "hmpd")
    c_hsr = _find_col(cols, "hsr")
    c_vhsr = _find_col(cols, "vhsr")
    c_vmax = _find_col(cols, "max_speed")
    c_vpct = _find_col(cols, "max_speed_pct")
    c_dsl = _find_col(cols, "dsl")
    c_imp = _find_col(cols, "heavy_impacts")
    c_acc = _find_col(cols, "acc_events")
    c_dec = _find_col(cols, "dec_events")
    c_mpe = _find_col(cols, "mpe")
    c_amp = _find_col(cols, "avg_mp")

    # Calcolo HSR/HMPD da bande multiple GPExe se la colonna aggregata diretta manca
    work_df = pd.DataFrame(index=df.index)
    work_df["Player_Name"] = (
        df[c_player].astype(str).str.strip() if c_player else [f"Riga {i+1}" for i in range(len(df))]
    )
    # Rimuove eventuali righe di riepilogo/totale vuote o 'Average'
    if c_player:
        mask_valid = (
            work_df["Player_Name"].str.len() > 0
        ) & (
            ~work_df["Player_Name"].str.lower().isin(["nan", "none", "average", "media", "total", "totale", "team"])
        )
        df = df.loc[mask_valid].copy()
        work_df = work_df.loc[mask_valid].copy()

    if df.empty:
        raise ValueError(f"Nessuna riga valida trovata nel file '{filename}'.")

    if c_role:
        work_df["Role"] = df[c_role].astype(str).str.strip()
    else:
        work_df["Role"] = ""

    # Arricchisce ruolo/reparto dal roster FIR se disponibile
    depts = []
    roles_clean = []
    for pname, rval in zip(work_df["Player_Name"], work_df["Role"]):
        dept = _classify_department(rval)
        final_role = rval if rval and rval.lower() not in ("nan", "none") else ""
        if dept == "N/D" and roster_role_map:
            p_key = _norm_col(pname)
            if p_key in roster_role_map:
                final_role, dept = roster_role_map[p_key]
        roles_clean.append(final_role)
        depts.append(dept)
    work_df["Role"] = roles_clean
    work_df["Department"] = depts

    # Durata in minuti
    if c_dur:
        work_df["Duration_Min"] = df[c_dur].apply(_parse_duration_to_minutes)
    else:
        work_df["Duration_Min"] = np.nan

    # Distanza Totale
    work_df["Total_Distance"] = _parse_numeric_series(df[c_dist]) if c_dist else np.nan

    # Work Rate (m/min): rigorosamente Distanza / Durata se entrambi validi, altrimenti colonna nativa
    wr_native = _parse_numeric_series(df[c_wr]) if c_wr else pd.Series(np.nan, index=df.index)
    if c_wr and "km/h" in _norm_col(c_wr):
        wr_native = wr_native * (1000.0 / 60.0)
    wr_calc = np.where(
        (work_df["Duration_Min"] > 0) & work_df["Total_Distance"].notna(),
        work_df["Total_Distance"] / work_df["Duration_Min"],
        wr_native,
    )
    work_df["Work_Rate"] = pd.to_numeric(wr_calc, errors="coerce")

    # Se manca la durata ma abbiamo Distanza e Work Rate, la ricaviamo
    missing_dur = work_df["Duration_Min"].isna() & (work_df["Work_Rate"] > 0) & (work_df["Total_Distance"] > 0)
    work_df.loc[missing_dur, "Duration_Min"] = (
        work_df.loc[missing_dur, "Total_Distance"] / work_df.loc[missing_dur, "Work_Rate"]
    )

    # HMPD (High Metabolic Power Distance)
    if c_hmpd:
        work_df["HMPD"] = _parse_numeric_series(df[c_hmpd])
    else:
        # Fallback: somma bande met power Z3 + Z4 + Z5 se presenti
        mp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("met power z3 (m)", "met power z4 (m)", "met power z5 (m)"))]
        if mp_cols:
            work_df["HMPD"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in mp_cols)
        else:
            work_df["HMPD"] = 0.0

    # HSR (High Speed Running)
    if c_hsr:
        work_df["HSR"] = _parse_numeric_series(df[c_hsr])
    else:
        sp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("speed z4 (m)", "speed z5 (m)", "speed z6 (m)"))]
        if sp_cols:
            work_df["HSR"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in sp_cols)
        else:
            work_df["HSR"] = 0.0

    # VHSR (>25 km/h)
    if c_vhsr:
        work_df["VHSR"] = _parse_numeric_series(df[c_vhsr])
    else:
        vsp_cols = [c for c in cols if any(k in _norm_col(c) for k in ("speed z5 (m)", "speed z6 (m)"))]
        if vsp_cols:
            work_df["VHSR"] = sum(_parse_numeric_series(df[c]).fillna(0.0) for c in vsp_cols)
        else:
            work_df["VHSR"] = 0.0

    work_df["Max_Speed"] = _parse_numeric_series(df[c_vmax]) if c_vmax else 0.0
    work_df["Max_Speed_Pct"] = _parse_numeric_series(df[c_vpct]) if c_vpct else 0.0
    work_df["Dynamic_Stress_Load"] = _parse_numeric_series(df[c_dsl]) if c_dsl else 0.0
    work_df["Heavy_Impacts"] = _parse_numeric_series(df[c_imp]) if c_imp else 0.0
    work_df["Acc_Events"] = _parse_numeric_series(df[c_acc]) if c_acc else 0.0
    work_df["Dec_Events"] = _parse_numeric_series(df[c_dec]) if c_dec else 0.0
    work_df["Met_Power_Events"] = _parse_numeric_series(df[c_mpe]) if c_mpe else 0.0
    work_df["Avg_MP"] = _parse_numeric_series(df[c_amp]) if c_amp else 0.0

    def _safe_mean(col_name: str, default: float = 0.0) -> float:
        s = pd.to_numeric(work_df[col_name], errors="coerce").dropna()
        return round(float(s.mean()), 2) if not s.empty else default

    def _safe_max(col_name: str, default: float = 0.0) -> float:
        s = pd.to_numeric(work_df[col_name], errors="coerce").dropna()
        return round(float(s.max()), 2) if not s.empty else default

    dur_avg = _safe_mean("Duration_Min", 0.0)
    dist_avg = _safe_mean("Total_Distance", 0.0)
    wr_avg = round(dist_avg / dur_avg, 2) if dur_avg > 0 and dist_avg > 0 else _safe_mean("Work_Rate", 0.0)
    hmpd_avg = _safe_mean("HMPD", 0.0)
    hsr_avg = _safe_mean("HSR", 0.0)

    av_df = work_df[work_df["Department"] == "Avanti"]
    tq_df = work_df[work_df["Department"] == "Trequarti"]

    def _sub_mean(sub: pd.DataFrame, col_name: str) -> float:
        if sub.empty:
            return 0.0
        s = pd.to_numeric(sub[col_name], errors="coerce").dropna()
        return round(float(s.mean()), 2) if not s.empty else 0.0

    summary_rec: Dict[str, Any] = {
        "Source_File": filename,
        "Players_Count": int(len(work_df)),
        "Duration_Min": dur_avg,
        "Total_Distance": dist_avg,
        "Work_Rate": wr_avg,
        "HMPD": hmpd_avg,
        "HMPD_per_Min": round(hmpd_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
        "HSR": hsr_avg,
        "HSR_per_Min": round(hsr_avg / dur_avg, 2) if dur_avg > 0 else 0.0,
        "VHSR": _safe_mean("VHSR", 0.0),
        "Max_Speed": _safe_mean("Max_Speed", 0.0),
        "Max_Speed_Peak": _safe_max("Max_Speed", 0.0),
        "Max_Speed_Pct": _safe_mean("Max_Speed_Pct", 0.0),
        "Dynamic_Stress_Load": _safe_mean("Dynamic_Stress_Load", 0.0),
        "Heavy_Impacts": _safe_mean("Heavy_Impacts", 0.0),
        "Acc_Events": _safe_mean("Acc_Events", 0.0),
        "Dec_Events": _safe_mean("Dec_Events", 0.0),
        "Met_Power_Events": _safe_mean("Met_Power_Events", 0.0),
        "Avg_MP": _safe_mean("Avg_MP", 0.0),
        "Avanti_Work_Rate": _sub_mean(av_df, "Work_Rate"),
        "Trequarti_Work_Rate": _sub_mean(tq_df, "Work_Rate"),
        "Avanti_HMPD": _sub_mean(av_df, "HMPD"),
        "Trequarti_HMPD": _sub_mean(tq_df, "HMPD"),
        "Avanti_HSR": _sub_mean(av_df, "HSR"),
        "Trequarti_HSR": _sub_mean(tq_df, "HSR"),
    }

    player_records: List[Dict[str, Any]] = []
    if c_player and len(work_df) > 1:
        for _, r in work_df.iterrows():
            player_records.append({
                "Player_Name": str(r["Player_Name"]),
                "Role": str(r["Role"]),
                "Department": str(r["Department"]),
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

    return summary_rec, player_records, suggested_name


def _empty_master_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DRILLS_MASTER_COLUMNS)


def _empty_players_df() -> pd.DataFrame:
    return pd.DataFrame(columns=DRILLS_PLAYERS_COLUMNS)


def _load_drills_master_uncached() -> pd.DataFrame:
    df = cloud_storage.load_parquet_with_cloud_sync("drills_master", DRILLS_MASTER_PATH)
    if df is None or df.empty:
        return _empty_master_df()
    for col in DRILLS_MASTER_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0 if col not in ("Session_Date", "Session_Name", "Drill_Name", "Source_File", "Updated_At") else ""
    df["Session_Date"] = df["Session_Date"].astype(str).str.slice(0, 10)
    df["Session_Name"] = df["Session_Name"].astype(str).str.strip()
    df["Drill_Name"] = df["Drill_Name"].astype(str).str.strip()
    df["Drill_Order"] = pd.to_numeric(df["Drill_Order"], errors="coerce").fillna(1).astype(int)
    return df[DRILLS_MASTER_COLUMNS].sort_values(
        by=["Session_Date", "Session_Name", "Drill_Order"],
        ascending=[False, True, True],
    ).reset_index(drop=True)


def _load_drills_players_uncached() -> pd.DataFrame:
    df = cloud_storage.load_parquet_with_cloud_sync("drills_players_detail", DRILLS_PLAYERS_PATH)
    if df is None or df.empty:
        return _empty_players_df()
    for col in DRILLS_PLAYERS_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0 if col not in ("Session_Date", "Session_Name", "Drill_Name", "Player_Name", "Role", "Department") else ""
    df["Session_Date"] = df["Session_Date"].astype(str).str.slice(0, 10)
    df["Session_Name"] = df["Session_Name"].astype(str).str.strip()
    df["Drill_Name"] = df["Drill_Name"].astype(str).str.strip()
    df["Drill_Order"] = pd.to_numeric(df["Drill_Order"], errors="coerce").fillna(1).astype(int)
    return df[DRILLS_PLAYERS_COLUMNS].reset_index(drop=True)


if st is not None:
    @st.cache_data(ttl=3600)
    def load_drills_master() -> pd.DataFrame:
        return _load_drills_master_uncached()

    @st.cache_data(ttl=3600)
    def load_drills_players_detail() -> pd.DataFrame:
        return _load_drills_players_uncached()
else:
    def load_drills_master() -> pd.DataFrame:
        return _load_drills_master_uncached()

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
) -> Tuple[int, int]:
    """
    Logica di Upsert pulita (Prevenzione Duplicati):
    1. Rimuove tutti i vecchi record associati a `(Session_Date, Session_Name)` (case-insensitive).
    2. Inserisce i nuovi record ordinati per `Drill_Order`.
    3. Salva `drills_master.parquet` (e `drills_players_detail.parquet`) su disco locale + Cloud Storage.
    4. Svuota la cache Streamlit (`st.cache_data.clear()`).

    Returns:
        tuple(removed_old_count, inserted_new_count)
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    s_date = str(session_date).strip()[:10]
    s_name = str(session_name).strip()
    s_name_norm = s_name.lower()
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Upsert su drills_master.parquet
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
        row["Players_Count"] = int(rec.get("Players_Count", 1))
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

    # 2. Upsert su drills_players_detail.parquet (dettaglio per atleta)
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
    """Elimina tutti i drill associati a una specifica (Session_Date, Session_Name) con sync cloud."""
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

    df_p_existing = _load_drills_players_uncached()
    if not df_p_existing.empty:
        mask_p_old = (df_p_existing["Session_Date"].astype(str).str.slice(0, 10) == s_date) & (
            df_p_existing["Session_Name"].astype(str).str.strip().str.lower() == s_name_norm
        )
        df_p_clean = df_p_existing.loc[~mask_p_old].reset_index(drop=True)
        cloud_storage.save_parquet_with_cloud_sync("drills_players_detail", df_p_clean, DRILLS_PLAYERS_PATH)

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
