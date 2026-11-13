# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import os
import base64
import json
import re
import unicodedata
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import streamlit as st
from config import FIR_COLUMNS_META, FIR_NUMERIC_COLS, DEFAULT_COACH_TARGETS, ROLE_TO_DEPT, RUGBY_ROLES, DEPARTMENTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_PATH = os.path.join(DATA_DIR, "app_config.json")
FIR_SESSION_TYPES_PATH = os.path.join(DATA_DIR, "fir_session_types.json")
SESSION_PLAYER_STATUS_PATH = os.path.join(DATA_DIR, "session_player_status.json")

FIR_SESSION_TYPOLOGIES = [
    "Volume",
    "Velocità",
    "Rugby",
    "Team run",
    "Clarity",
    "Reparto",
    "Extra",
    "Lavoro fisico",
    "Match",
    "RTP",
]


def detect_fir_session_type(session_name: str) -> str:
    s = str(session_name or "").lower()
    if "rtp" in s:
        return "RTP"
    if "extra" in s or "sprint" in s or "skills" in s:
        return "Extra"
    if "team run" in s or "teamrun" in s or "captain" in s:
        return "Team run"
    if "clarit" in s or "walk" in s:
        return "Clarity"
    if "reparto" in s:
        return "Reparto"
    if any(k in s for k in ["partita", "match", "vs", "italia", "nz", "scozia", "irlanda", "francia", "galles", "inghilterra", "samoa", "tonga", "giappone", "argentina", "georgia", "australia", "south africa", "sud africa", "cile", "namibia"]):
        return "Match"
    if "velocit" in s or "speed" in s:
        return "Velocità"
    if "volum" in s or "intensity" in s:
        return "Volume"
    if any(k in s for k in ["palestra", "gym", "fisico", "weights", "forza"]):
        return "Lavoro fisico"
    return "Rugby"


def get_fir_session_types() -> dict:
    types_map = {}
    if os.path.exists(FIR_SESSION_TYPES_PATH):
        try:
            with open(FIR_SESSION_TYPES_PATH, "r", encoding="utf-8") as f:
                types_map = json.load(f)
        except Exception:
            types_map = {}
    return types_map


def save_fir_session_types(types_map: dict):
    with open(FIR_SESSION_TYPES_PATH, "w", encoding="utf-8") as f:
        json.dump(types_map, f, indent=2, ensure_ascii=False)


def get_session_assigned_type(date_str: str, session_name: str) -> str:
    types_map = get_fir_session_types()
    key = f"{date_str}_{session_name}"
    if key in types_map:
        return types_map[key]
    if session_name in types_map:
        return types_map[session_name]
    return detect_fir_session_type(session_name)


def get_all_fir_unique_sessions() -> pd.DataFrame:
    gh = get_gps_history_df("nazionale")
    if gh.empty:
        return pd.DataFrame(columns=["date_str", "session_name", "players_count", "assigned_type"])
    types_map = get_fir_session_types()
    grp = gh.groupby(["date_str", "session_name"], as_index=False).agg(
        players_count=("player_name", "nunique")
    ).sort_values("date_str", ascending=False)

    types_list = []
    for _, r in grp.iterrows():
        k = f"{r['date_str']}_{r['session_name']}"
        cur_t = types_map.get(k) or types_map.get(r["session_name"]) or detect_fir_session_type(r["session_name"])
        types_list.append(cur_t)
    grp["assigned_type"] = types_list
    return grp.reset_index(drop=True)


def get_session_player_statuses() -> dict:
    if os.path.exists(SESSION_PLAYER_STATUS_PATH):
        try:
            with open(SESSION_PLAYER_STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_session_player_statuses(status_map: dict):
    with open(SESSION_PLAYER_STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status_map, f, indent=2, ensure_ascii=False)


# Alias per retrocompatibilità
get_session_player_status = get_session_player_statuses
save_session_player_status = save_session_player_statuses


def set_player_status_in_session(date_str: str, session_name: str, player_name: str, status: str):
    data = get_session_player_statuses()
    sess_key = f"{date_str}_{session_name}"
    if sess_key not in data:
        data[sess_key] = {}
    data[sess_key][str(player_name).strip()] = status
    save_session_player_statuses(data)


def set_bulk_player_status_in_session(date_str: str, session_name: str, statuses: dict):
    data = get_session_player_statuses()
    sess_key = f"{date_str}_{session_name}"
    if sess_key not in data:
        data[sess_key] = {}
    for p_name, st_val in statuses.items():
        data[sess_key][str(p_name).strip()] = st_val
    save_session_player_statuses(data)


def _parquet_path(table_name: str) -> str:
    return os.path.join(DATA_DIR, f"{table_name}.parquet")


@st.cache_data(ttl=60)
def load_table(table_name: str) -> pd.DataFrame:
    p = _parquet_path(table_name)
    if os.path.exists(p):
        try:
            df = pd.read_parquet(p)
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def is_truthy(v) -> bool:
    """Valuta correttamente se un valore booleano, stringa ('True'/'False') o numerico è vero."""
    if v is None or pd.isna(v):
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "t", "yes")


def save_table(table_name: str, df: pd.DataFrame):
    p = _parquet_path(table_name)
    out = df.copy()
    if "manual_override" in out.columns:
        out["manual_override"] = out["manual_override"].apply(is_truthy).astype(bool)

    for col in out.columns:
        if col == "manual_override":
            continue
        if col in ("date", "start_date", "created_at", "match_date") or out[col].dtype == "object":
            out[col] = out[col].where(out[col].notna(), None)
            out[col] = out[col].apply(lambda x: str(x) if x is not None else None).replace(
                {"NaT": None, "None": None, "nan": None, "<NA>": None}
            )
    out.to_parquet(p, index=False)
    load_table.clear()
    try:
        _compute_dynamic_roster_metrics.clear()
    except Exception:
        pass


def get_next_id(df: pd.DataFrame, id_col: str = "id") -> int:
    if df.empty or id_col not in df.columns:
        return 1
    valid = pd.to_numeric(df[id_col], errors="coerce").dropna()
    return int(valid.max()) + 1 if not valid.empty else 1


# ==============================================================================
# COACH TARGETS & CONFIG
# ==============================================================================
def get_coach_config() -> dict:
    cfg = DEFAULT_COACH_TARGETS.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_coach_config(new_cfg: dict):
    cfg = get_coach_config()
    cfg.update(new_cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ==============================================================================
# 1. AREA GESTIONE ROSTER (players & player_aliases) CON CALCOLO AUTOMATICO
# ==============================================================================
@st.cache_data(ttl=60)
def _compute_dynamic_roster_metrics() -> dict:
    """
    Calcola dinamicamente per ogni atleta (inclusi i nuovi inseriti):
    - opta_id (Codice Oval) da oval_matches
    - v_max massima assoluta da tutto gps_history
    - HML Avg (>25.5W) e HSR Avg (>18 km/h Avanti, >20 km/h Trequarti)
      normalizzati a 80' (solo partite con Min >= 30 su Oval, escluso extra/wu/top-up),
      sia SOLO NAZIONALE (FIR) sia TOTALE (Nazionale + Club),
      con fallback automatico alla media del Ruolo.
    """
    pl = load_table("players")
    gh = load_table("gps_history")
    ov = load_table("oval_matches")

    res = {
        "opta_by_name": {},
        "vmax_by_name": {},
        "club_by_name": {},
        "fir_player_stats": {},
        "tot_player_stats": {},
        "fir_role_avg": {},
        "tot_role_avg": {},
    }

    if not ov.empty:
        # Ordina per data decrescente per prendere la squadra Club più recente per ciascun giocatore
        ov_work = ov.copy()
        ov_work["dt_parsed"] = pd.to_datetime(ov_work["match_date"], errors="coerce")
        ov_sorted_desc = ov_work.sort_values("dt_parsed", ascending=False)

        for _, r in ov_sorted_desc.iterrows():
            oid = str(r.get("playerId") or "").strip().split(".")[0]
            if oid and oid not in ("", "nan", "None", "<NA>"):
                for col in ("fir_player_name", "playerFullName"):
                    nm = str(r.get(col) or "").strip().upper()
                    if nm and nm not in res["opta_by_name"]:
                        res["opta_by_name"][nm] = oid

            # Squadra club più recente (esclusa Italy / Nazionale)
            tm = str(r.get("teamName") or "").strip()
            if tm and tm.lower() not in ("", "none", "nan") and not tm.lower().startswith("ital"):
                for col in ("fir_player_name", "playerFullName"):
                    nm = str(r.get(col) or "").strip().upper()
                    if nm and nm not in res["club_by_name"]:
                        res["club_by_name"][nm] = tm
                if oid and oid not in res["club_by_name"]:
                    res["club_by_name"][oid] = tm

    if gh.empty:
        return res

    gh = gh.copy()
    for c in ["duration", "distance_m", "v_max", "mp_25_35", "mp_35_50", "mp_50_100", "speed_18_20", "speed_20_25", "speed_25_72"]:
        if c in gh.columns:
            gh[c] = pd.to_numeric(gh[c], errors="coerce")
        else:
            gh[c] = np.nan

    # 1. V max assoluta in tutto il database GPS per ogni giocatore (filtro fisiologico <= 38.0 km/h per escludere spike GPS)
    valid_vmax_df = gh.dropna(subset=["player_name", "v_max"])
    valid_vmax_df = valid_vmax_df[(valid_vmax_df["v_max"] >= 15.0) & (valid_vmax_df["v_max"] <= 38.0)]
    vmax_grp = valid_vmax_df.groupby(valid_vmax_df["player_name"].astype(str).str.strip().str.upper())["v_max"].max()
    res["vmax_by_name"] = vmax_grp.round(2).to_dict()

    if ov.empty:
        return res

    # 2. Incrocio Partite GPS + Oval Match (Soglia minima 30 minuti)
    gh["date_str"] = gh["date"].astype(str).str[:10]
    gh["p_up"] = gh["player_name"].astype(str).str.strip().str.upper()

    ov_c = ov.copy()
    ov_c["date_str"] = ov_c["match_date"].astype(str).str[:10]
    ov_c["Min_num"] = pd.to_numeric(ov_c["Min"], errors="coerce")
    ov_c["p_up"] = ov_c["fir_player_name"].astype(str).str.strip().str.upper()
    ov_30 = ov_c[ov_c["Min_num"] >= 30.0].sort_values("Min_num", ascending=False).drop_duplicates(subset=["p_up", "date_str"])

    # Escludi tutto ciò che non è match (extra, wu, warm-up, top-up, attivazione o durate < 25')
    non_match_pat = r"extra|warm|\bwu\b|top[\s\-]?up|attivazione"
    clean_sess = ~gh["session_name"].astype(str).str.lower().str.contains(non_match_pat, regex=True, na=False)
    clean_per = ~gh["period"].astype(str).str.lower().str.contains(non_match_pat, regex=True, na=False)
    gh_cand = gh[clean_sess & clean_per & (gh["duration"].fillna(0) >= 25.0)].copy()

    m = gh_cand.merge(ov_30[["p_up", "date_str", "Min_num"]], on=["p_up", "date_str"], how="inner")
    if m.empty:
        return res

    # Se ci sono più righe GPS nello stesso giorno di gara, prendi la singola riga principale della partita
    m["dur_diff"] = (m["duration"] - m["Min_num"]).abs()
    m = m.sort_values(["dur_diff", "distance_m"], ascending=[True, False]).drop_duplicates(subset=["p_up", "date_str"])

    # Mappa Reparto e Ruolo dal Roster
    dept_map = {}
    role_map = {}
    if not pl.empty:
        for _, pr in pl.iterrows():
            k = str(pr.get("name_display") or "").strip().upper()
            if k:
                dept_map[k] = str(pr.get("department") or "Avanti")
                role_map[k] = str(pr.get("role") or "")

    m["dept"] = m["p_up"].map(dept_map).fillna(
        m["role"].apply(lambda r: "Avanti" if str(r) in ["Avanti", "Pilone", "Tallonatore", "Seconda Linea", "Terza Linea"] else "TreQuarti")
    )
    m["canonical_role"] = m["p_up"].map(role_map).fillna(m["role"].astype(str))

    # Calcolo HML (>25.5W) e HSR (>18 km/h per Avanti, >20 km/h per Trequarti)
    m["hml_raw"] = m["mp_25_35"].fillna(0.0) + m["mp_35_50"].fillna(0.0) + m["mp_50_100"].fillna(0.0)
    m["hsr_gt18"] = m["speed_18_20"].fillna(0.0) + m["speed_20_25"].fillna(0.0) + m["speed_25_72"].fillna(0.0)
    m["hsr_gt20"] = m["speed_20_25"].fillna(0.0) + m["speed_25_72"].fillna(0.0)
    m["hsr_raw"] = np.where(m["dept"] == "Avanti", m["hsr_gt18"], m["hsr_gt20"])

    # Normalizzazione a 80' di match
    m["hml_80"] = (m["hml_raw"] / m["Min_num"]) * 80.0
    m["hsr_80"] = (m["hsr_raw"] / m["Min_num"]) * 80.0

    # Medie Totale (Nazionale + Club)
    tot_p = m.groupby("p_up").agg(hml=("hml_80", "mean"), hsr=("hsr_80", "mean"), cnt=("hml_80", "count")).round(1)
    res["tot_player_stats"] = tot_p.to_dict(orient="index")

    tot_r = m[m["canonical_role"] != ""].groupby("canonical_role").agg(hml=("hml_80", "mean"), hsr=("hsr_80", "mean")).round(1)
    res["tot_role_avg"] = tot_r.to_dict(orient="index")

    # Medie Solo Nazionale (FIR)
    m_fir = m[m["team_type"] == "nazionale"]
    if not m_fir.empty:
        fir_p = m_fir.groupby("p_up").agg(hml=("hml_80", "mean"), hsr=("hsr_80", "mean"), cnt=("hml_80", "count")).round(1)
        res["fir_player_stats"] = fir_p.to_dict(orient="index")

        fir_r = m_fir[m_fir["canonical_role"] != ""].groupby("canonical_role").agg(hml=("hml_80", "mean"), hsr=("hsr_80", "mean")).round(1)
        res["fir_role_avg"] = fir_r.to_dict(orient="index")

    return res


def get_players_df() -> pd.DataFrame:
    df = load_table("players")
    if df.empty:
        return pd.DataFrame(
            columns=[
                "id", "last_name", "first_name", "name_display", "name_sheet",
                "birth_year", "role", "club", "department", "opta_id", "code",
                "v_max", "hml_avg_fir", "hsr_avg_fir", "hml_avg_tot", "hsr_avg_tot",
                "has_fir_matches", "has_tot_matches", "match_avg_hml", "match_avg_hsr",
            ]
        )

    dyn = _compute_dynamic_roster_metrics()
    opta_by_name = dyn["opta_by_name"]
    vmax_by_name = dyn["vmax_by_name"]
    club_by_name = dyn.get("club_by_name", {})
    fir_p = dyn["fir_player_stats"]
    tot_p = dyn["tot_player_stats"]
    fir_r = dyn["fir_role_avg"]
    tot_r = dyn["tot_role_avg"]

    out = df.copy()
    new_opta, new_vmax, vmax_calc_flag = [], [], []
    new_club = []
    hml_fir_list, hsr_fir_list, has_fir_list = [], [], []
    hml_tot_list, hsr_tot_list, has_tot_list = [], [], []

    for _, row in out.iterrows():
        p_key = str(row.get("name_display") or "").strip().upper()
        p_sheet = str(row.get("name_sheet") or "").strip().upper()
        role = str(row.get("role") or "Ala").strip()
        fallback_role = "Ala" if role == "Estremo" and "Estremo" not in tot_r else role

        # 1. Codice Oval automatico da Oval Match (o fallback manuale)
        auto_opta = opta_by_name.get(p_key) or opta_by_name.get(p_sheet)
        cur_opta = str(row.get("opta_id") or "").strip().split(".")[0]
        if cur_opta in ("", "nan", "None"):
            cur_opta = ""
        new_opta.append(auto_opta or cur_opta)

        # 1b. Squadra Club più recente presa automaticamente da Oval Match (esclusa Italy / Nazionale)
        cur_club = str(row.get("club") or "").strip()
        is_man = is_truthy(row.get("manual_override", False))
        auto_club = club_by_name.get(p_key) or club_by_name.get(p_sheet) or club_by_name.get(cur_opta) or club_by_name.get(auto_opta)
        # Se c'è un override manuale e il club è valorizzato, mantiene quello manuale, altrimenti prende auto_club
        if is_man and cur_club:
            chosen_club = cur_club
        else:
            chosen_club = auto_club or cur_club
        new_club.append(chosen_club)

        # 2. V max più alta in tutto il database GPS
        db_vmax = vmax_by_name.get(p_key) or vmax_by_name.get(p_sheet)
        if is_man and pd.notna(row.get("v_max")):
            new_vmax.append(round(float(row["v_max"]), 2))
            vmax_calc_flag.append(False)
        elif db_vmax is not None and pd.notna(db_vmax):
            new_vmax.append(round(float(db_vmax), 2))
            vmax_calc_flag.append(True)
        else:
            man_v = pd.to_numeric(row.get("v_max"), errors="coerce")
            new_vmax.append(round(float(man_v), 2) if pd.notna(man_v) else np.nan)
            vmax_calc_flag.append(False)

        # 3. Solo Nazionale (FIR) HML & HSR (80') o fallback media Ruolo
        fp = fir_p.get(p_key) or fir_p.get(p_sheet)
        if is_man and pd.notna(row.get("hml_avg_fir")):
            hml_fir_list.append(round(float(row["hml_avg_fir"]), 1))
            hsr_fir_list.append(round(float(row["hsr_avg_fir"]), 1) if pd.notna(row.get("hsr_avg_fir")) else (fp["hsr"] if fp else np.nan))
            has_fir_list.append(True)
        elif fp:
            hml_fir_list.append(fp["hml"])
            hsr_fir_list.append(fp["hsr"])
            has_fir_list.append(True)
        else:
            fr = fir_r.get(fallback_role, tot_r.get(fallback_role, {"hml": np.nan, "hsr": np.nan}))
            hml_fir_list.append(fr.get("hml", np.nan))
            hsr_fir_list.append(fr.get("hsr", np.nan))
            has_fir_list.append(False)

        # 4. Totale (Nazionale + Club) HML & HSR (80') o fallback media Ruolo
        tp = tot_p.get(p_key) or tot_p.get(p_sheet)
        if is_man and (pd.notna(row.get("match_avg_hml")) or pd.notna(row.get("hml_avg_tot"))):
            man_hml = row.get("match_avg_hml") if pd.notna(row.get("match_avg_hml")) else row.get("hml_avg_tot")
            man_hsr = row.get("match_avg_hsr") if pd.notna(row.get("match_avg_hsr")) else row.get("hsr_avg_tot")
            hml_tot_list.append(round(float(man_hml), 1))
            hsr_tot_list.append(round(float(man_hsr), 1) if pd.notna(man_hsr) else (tp["hsr"] if tp else np.nan))
            has_tot_list.append(True)
        elif tp:
            hml_tot_list.append(tp["hml"])
            hsr_tot_list.append(tp["hsr"])
            has_tot_list.append(True)
        else:
            tr = tot_r.get(fallback_role, {"hml": np.nan, "hsr": np.nan})
            hml_tot_list.append(tr.get("hml", np.nan))
            hsr_tot_list.append(tr.get("hsr", np.nan))
            has_tot_list.append(False)

    out["opta_id"] = new_opta
    out["club"] = new_club
    out["v_max"] = new_vmax
    out["vmax_is_calc"] = vmax_calc_flag
    out["hml_avg_fir"] = hml_fir_list
    out["hsr_avg_fir"] = hsr_fir_list
    out["has_fir_matches"] = has_fir_list
    out["hml_avg_tot"] = hml_tot_list
    out["hsr_avg_tot"] = hsr_tot_list
    out["has_tot_matches"] = has_tot_list

    # Conserva anche i valori originali del foglio Roster e popola i default con fallback
    out["hml_avg_excel"] = pd.to_numeric(out.get("match_avg_hml"), errors="coerce").fillna(pd.Series(hml_tot_list))
    out["hsr_avg_excel"] = pd.to_numeric(out.get("match_avg_hsr"), errors="coerce").fillna(pd.Series(hsr_tot_list))
    out["match_avg_hml"] = out["hml_avg_tot"].fillna(out["hml_avg_excel"])
    out["match_avg_hsr"] = out["hsr_avg_tot"].fillna(out["hsr_avg_excel"])

    return out.sort_values(by=["department", "role", "last_name"], na_position="last").reset_index(drop=True)


def get_aliases_df() -> pd.DataFrame:
    df = load_table("player_aliases")
    if df.empty:
        return pd.DataFrame(columns=["id", "player_id", "alias", "source"])
    return df


def save_player(data: dict, player_id: int = None) -> int:
    df = load_table("players")
    aliases_df = get_aliases_df()

    last_name = str(data.get("last_name") or "").strip()
    first_name = str(data.get("first_name") or "").strip()
    name_display = str(data.get("name_display") or f"{first_name} {last_name}").strip()
    name_sheet = str(data.get("name_sheet") or f"{last_name} {first_name}").strip()
    role = str(data.get("role") or "Pilone").strip()
    dept = str(data.get("department") or ROLE_TO_DEPT.get(role, "Avanti")).strip()
    club = str(data.get("club") or "").strip()
    opta_id = str(data.get("opta_id") or "").strip()
    code = str(data.get("code") or "").strip().upper()

    def _to_f(v):
        try:
            return float(v) if v not in (None, "") and pd.notna(v) else np.nan
        except Exception:
            return np.nan

    def _to_i(v):
        try:
            return int(float(v)) if v not in (None, "") and pd.notna(v) else None
        except Exception:
            return None

    row_dict = {
        "last_name": last_name,
        "first_name": first_name,
        "name_display": name_display,
        "name_sheet": name_sheet,
        "birth_year": _to_i(data.get("birth_year")),
        "role": role,
        "club": club,
        "department": dept,
        "opta_id": opta_id,
        "code": code,
        "v_max": _to_f(data.get("v_max")),
        "hml_avg_fir": _to_f(data.get("hml_avg_fir")),
        "hsr_avg_fir": _to_f(data.get("hsr_avg_fir")),
        "hml_avg_tot": _to_f(data.get("hml_avg_tot") or data.get("match_avg_hml")),
        "hsr_avg_tot": _to_f(data.get("hsr_avg_tot") or data.get("match_avg_hsr")),
        "match_avg_hml": _to_f(data.get("match_avg_hml")),
        "match_avg_hsr": _to_f(data.get("match_avg_hsr")),
        "match_max_hml": _to_f(data.get("match_max_hml")),
        "match_max_hsr": _to_f(data.get("match_max_hsr")),
        "match_avg_contacts": _to_f(data.get("match_avg_contacts")),
        "manual_override": bool(data.get("manual_override", False)),
    }

    if player_id is not None and not df.empty and player_id in df["id"].values:
        idx = df.index[df["id"] == player_id][0]
        for k, v in row_dict.items():
            df.loc[idx, k] = v
        pid = int(player_id)
    else:
        pid = get_next_id(df)
        row_dict["id"] = pid
        df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)

    save_table("players", df)
    try:
        st.cache_data.clear()
    except Exception:
        pass

    # Register aliases
    existing_aliases = set(aliases_df["alias"].dropna().astype(str).str.upper()) if not aliases_df.empty else set()
    new_alias_rows = []
    next_aid = get_next_id(aliases_df)
    for cand in [name_display, name_sheet, f"{last_name} {first_name}", f"{first_name} {last_name}", code]:
        c_up = str(cand or "").strip().upper()
        if c_up and c_up not in existing_aliases:
            new_alias_rows.append({"id": next_aid, "player_id": pid, "alias": c_up, "source": "app"})
            existing_aliases.add(c_up)
            next_aid += 1
    if new_alias_rows:
        aliases_df = pd.concat([aliases_df, pd.DataFrame(new_alias_rows)], ignore_index=True)
        save_table("player_aliases", aliases_df)

    return pid


def delete_player(player_id: int):
    for tname, col in [
        ("players", "id"),
        ("player_aliases", "player_id"),
        ("camp_players", "player_id"),
    ]:
        df = load_table(tname)
        if not df.empty and col in df.columns:
            df = df[df[col] != player_id].copy()
            save_table(tname, df)


def reset_player_manual_overrides(player_id: int) -> bool:
    """
    Rimuove il flag manuale per l'atleta, ripristinando il calcolo automatico
    della squadra da Oval, V max da GPS e medie benchmark 80'.
    """
    df = load_table("players")
    if not df.empty and player_id in df["id"].values:
        idx = df.index[df["id"] == player_id][0]
        df.loc[idx, "manual_override"] = False
        save_table("players", df)
        try:
            st.cache_data.clear()
        except Exception:
            pass
        return True
    return False


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c))


def resolve_player_identity(raw_name: str) -> dict:
    """
    Risolve qualsiasi variante di nome atleta (es. Cognome Nome, Nome Cognome, accenti, secondo nome, Sigla)
    restituendo dict con player_id, name_display, sigla, role, department, v_max.
    """
    players_df = get_players_df()
    aliases_df = get_aliases_df()
    if not raw_name or pd.isna(raw_name):
        return {"player_id": None, "name_display": "", "sigla": "", "role": "", "department": "", "v_max": None}

    clean = _strip_accents(str(raw_name)).strip().upper()
    if clean in ("NACHO BREX", "BREX NACHO", "J. I. BREX", "JI BREX"):
        clean = "JUAN IGNACIO BREX"
    norm = re.sub(r"[,.\-_]+", " ", clean)
    norm = re.sub(r"\s+", " ", norm).strip()
    parts = norm.split(" ")
    candidates = [clean, norm]
    if len(parts) == 2:
        candidates.append(f"{parts[1]} {parts[0]}")
    elif len(parts) >= 3:
        candidates.extend([
            f"{parts[-1]} {parts[0]}",
            f"{parts[0]} {parts[-1]}",
            f"{parts[0]} {parts[1]}",
            f"{parts[1]} {parts[0]}",
            f"{parts[1]} {parts[2]}",
            f"{parts[2]} {parts[1]}",
        ])

    pid = None
    if not aliases_df.empty:
        al_map = {_strip_accents(k).strip().upper(): v for k, v in zip(aliases_df["alias"], aliases_df["player_id"])}
        for candidate in candidates:
            if candidate in al_map:
                pid = al_map[candidate]
                break

    if pid is None and not players_df.empty:
        for _, prow in players_df.iterrows():
            for col in ("name_display", "name_sheet", "last_name", "code"):
                val = _strip_accents(str(prow.get(col) or "")).strip().upper()
                if not val:
                    continue
                if val in candidates or any(len(c) >= 8 and val.startswith(c) and len(val) - len(c) == 1 for c in candidates):
                    pid = prow["id"]
                    break
            if pid is not None:
                break

    if pid is not None and not players_df.empty:
        m = players_df[players_df["id"] == pid]
        if not m.empty:
            r = m.iloc[0]
            return {
                "player_id": int(r["id"]),
                "name_display": str(r.get("name_display") or raw_name),
                "sigla": str(r.get("code") or ""),
                "role": str(r.get("role") or ""),
                "department": str(r.get("department") or ""),
                "v_max": float(r["v_max"]) if pd.notna(r.get("v_max")) else None,
            }

    # Format Title Case "Nome Cognome" if input is "COGNOME NOME"
    fallback_disp = str(raw_name).strip().title()
    return {"player_id": None, "name_display": fallback_disp, "sigla": "", "role": "", "department": "", "v_max": None}


def get_player_department(player_name: str = "", role: str = "", jersey_number: int = 0) -> str:
    """
    Restituisce con assoluta precisione il reparto di appartenenza ('Avanti' oppure 'TreQuarti'):
    1. Se il numero di maglia è da titolare (1-15):
       - 1 a 8: SEMPRE Avanti (Piloni, Tallonatore, Seconde Linee, Terze Linee)
       - 9 a 15: SEMPRE TreQuarti (Mediano Mischia, Apertura, Centri, Ali, Estremo)
    2. Per la panchina (16-23):
       - Controlla l'anagrafica ufficiale nel Roster FIR (players) tramite resolve_player_identity
       - Se non trovata o ambigua, analizza la stringa del ruolo (inclusi tutti i sinonimi e varianti:
         Ala Sinistra/Destra, Primo/Secondo Centro, Centro/Ala, Flanker, Pilone, ecc.)
    """
    try:
        jn = int(jersey_number) if jersey_number is not None else 0
    except Exception:
        jn = 0

    # 1. Titolari 1-15: reparto rigidamente legato al numero di maglia
    if 1 <= jn <= 8:
        return "Avanti"
    if 9 <= jn <= 15:
        return "TreQuarti"

    # 2. Panchina 16-23: il reparto deriva ESCLUSIVAMENTE dal ruolo/reparto salvato nel Roster FIR
    # poiché in panchina le formazioni possono adottare diverse combinazioni (5-3, 6-2, 7-1, ecc.)
    p_clean = str(player_name or "").strip()
    if p_clean:
        ident = resolve_player_identity(p_clean)
        dept = ident.get("department")
        if dept in ("Avanti", "TreQuarti"):
            return dept
        p_role = str(ident.get("role") or "").lower()
        if any(k in p_role for k in ("pilone", "tallonatore", "seconda", "terza", "flanker", "numero otto", "otto", "avanti")):
            return "Avanti"
        if any(k in p_role for k in ("mediano", "apertura", "centro", "ala", "estremo", "trequarti")):
            return "TreQuarti"

    r_low = str(role or "").strip().lower()
    if any(k in r_low for k in ("pilone", "tallonatore", "seconda", "terza", "flanker", "numero otto", "otto", "avanti", "prop", "hooker", "lock")):
        return "Avanti"
    if any(k in r_low for k in ("mediano", "apertura", "centro", "ala", "estremo", "trequarti", "wing", "fly", "scrum", "fullback")):
        return "TreQuarti"

    return "Avanti"


# ==============================================================================
# 2. AREA ATLETI IN RADUNO (camps & camp_players)
# ==============================================================================
def get_camps_df() -> pd.DataFrame:
    df = load_table("camps")
    if df.empty:
        return pd.DataFrame(columns=["id", "competition", "week_name", "start_date", "forwards_count", "backs_count", "total_count", "notes"])
    df["start_date_str"] = df["start_date"].astype(str).str[:10]
    return df.sort_values(by=["start_date_str", "id"], ascending=[False, False]).reset_index(drop=True)


def get_camp_players_df(camp_id: int = None) -> pd.DataFrame:
    cp_df = load_table("camp_players")
    if cp_df.empty:
        return pd.DataFrame(columns=["id", "camp_id", "player_id", "player_name", "role", "code", "department"])
    if camp_id is not None:
        cp_df = cp_df[cp_df["camp_id"] == camp_id].copy()
    players_df = get_players_df()
    if not players_df.empty and not cp_df.empty:
        p_meta = players_df[["id", "club", "v_max", "match_avg_hml", "match_avg_hsr"]].rename(columns={"id": "player_id"})
        cp_df = cp_df.merge(p_meta, on="player_id", how="left")
    return cp_df.sort_values(by=["department", "role", "player_name"], na_position="last").reset_index(drop=True)


def _recalc_camp_counts(camp_id: int):
    camps_df = load_table("camps")
    cp_df = load_table("camp_players")
    if camps_df.empty or camp_id not in camps_df["id"].values:
        return
    sub = cp_df[cp_df["camp_id"] == camp_id] if not cp_df.empty else pd.DataFrame()
    f_cnt = int((sub["department"] == "Avanti").sum()) if not sub.empty else 0
    b_cnt = int((sub["department"] == "TreQuarti").sum()) if not sub.empty else 0
    idx = camps_df.index[camps_df["id"] == camp_id][0]
    camps_df.loc[idx, "forwards_count"] = f_cnt
    camps_df.loc[idx, "backs_count"] = b_cnt
    camps_df.loc[idx, "total_count"] = f_cnt + b_cnt
    save_table("camps", camps_df)


def save_camp(data: dict, camp_id: int = None) -> int:
    df = load_table("camps")
    row = {
        "competition": str(data.get("competition") or "").strip(),
        "week_name": str(data.get("week_name") or "").strip(),
        "start_date": str(data.get("start_date") or "")[:10],
        "notes": str(data.get("notes") or "").strip(),
    }
    if camp_id is not None and not df.empty and camp_id in df["id"].values:
        idx = df.index[df["id"] == camp_id][0]
        for k, v in row.items():
            df.loc[idx, k] = v
        cid = int(camp_id)
    else:
        cid = get_next_id(df)
        row.update({"id": cid, "forwards_count": 0, "backs_count": 0, "total_count": 0})
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_table("camps", df)
    return cid


def copy_camp_to_new_week(source_camp_id: int, new_comp: str, new_week: str, new_date: str) -> int:
    camps_df = load_table("camps")
    cp_df = load_table("camp_players")
    src = camps_df[camps_df["id"] == source_camp_id]
    if src.empty:
        return -1
    srow = src.iloc[0]
    new_cid = get_next_id(camps_df)
    new_camp_row = {
        "id": new_cid,
        "competition": new_comp.strip() or str(srow.get("competition") or ""),
        "week_name": new_week.strip() or f"Copia di {srow.get('week_name')}",
        "start_date": str(new_date)[:10],
        "forwards_count": int(srow.get("forwards_count") or 0),
        "backs_count": int(srow.get("backs_count") or 0),
        "total_count": int(srow.get("total_count") or 0),
        "notes": f"Clonato da {srow.get('week_name')}",
    }
    camps_df = pd.concat([camps_df, pd.DataFrame([new_camp_row])], ignore_index=True)
    save_table("camps", camps_df)

    if not cp_df.empty:
        src_players = cp_df[cp_df["camp_id"] == source_camp_id].copy()
        if not src_players.empty:
            next_id = get_next_id(cp_df)
            src_players["id"] = range(next_id, next_id + len(src_players))
            src_players["camp_id"] = new_cid
            cp_df = pd.concat([cp_df, src_players], ignore_index=True)
            save_table("camp_players", cp_df)
            _recalc_camp_counts(new_cid)
    return new_cid


def copy_camp_players_to_existing_camp(
    source_camp_id: int,
    target_camp_id: int,
    replace_existing: bool = True,
) -> int:
    """
    Clona la lista dei convocati da `source_camp_id` dentro una settimana già esistente (`target_camp_id`).
    Se `replace_existing=True`, sostituisce eventuale lista già presente nella settimana di destinazione;
    altrimenti aggiunge solo gli atleti non ancora presenti.
    Ritorna il numero di atleti copiati/aggiunti.
    """
    source_camp_id = int(source_camp_id)
    target_camp_id = int(target_camp_id)
    if source_camp_id == target_camp_id:
        return 0

    camps_df = load_table("camps")
    if camps_df.empty or source_camp_id not in camps_df["id"].values or target_camp_id not in camps_df["id"].values:
        return 0

    cp_df = load_table("camp_players")
    if cp_df.empty:
        return 0

    src_players = cp_df[cp_df["camp_id"] == source_camp_id].copy()
    if src_players.empty:
        return 0

    if replace_existing:
        cp_df = cp_df[cp_df["camp_id"] != target_camp_id].copy()
        to_add = src_players.copy()
    else:
        existing_target = cp_df[cp_df["camp_id"] == target_camp_id]
        existing_pids = set(existing_target["player_id"].dropna().astype(int).tolist()) if not existing_target.empty else set()
        to_add = src_players[~src_players["player_id"].dropna().astype(int).isin(existing_pids)].copy()

    if not to_add.empty:
        next_id = get_next_id(cp_df)
        to_add["id"] = range(next_id, next_id + len(to_add))
        to_add["camp_id"] = target_camp_id
        cp_df = pd.concat([cp_df, to_add], ignore_index=True)

    save_table("camp_players", cp_df)
    _recalc_camp_counts(target_camp_id)
    return len(to_add)


def delete_camp(camp_id: int):
    for tname, col in [("camp_players", "camp_id"), ("camps", "id")]:
        df = load_table(tname)
        if not df.empty and col in df.columns:
            df = df[df[col] != camp_id].copy()
            save_table(tname, df)


def add_player_to_camp(camp_id: int, player_id: int):
    camp_id = int(camp_id)
    player_id = int(player_id)
    cp_df = load_table("camp_players")
    players_df = get_players_df()
    p_row = players_df[players_df["id"] == player_id]
    if p_row.empty:
        return
    p = p_row.iloc[0]
    if not cp_df.empty:
        dup = cp_df[(cp_df["camp_id"] == camp_id) & (cp_df["player_id"] == player_id)]
        if not dup.empty:
            return
    new_row = {
        "id": get_next_id(cp_df),
        "camp_id": int(camp_id),
        "player_id": int(player_id),
        "player_name": str(p.get("name_display") or ""),
        "role": str(p.get("role") or ""),
        "code": str(p.get("code") or ""),
        "department": str(p.get("department") or "Avanti"),
    }
    cp_df = pd.concat([cp_df, pd.DataFrame([new_row])], ignore_index=True)
    save_table("camp_players", cp_df)
    _recalc_camp_counts(camp_id)
    try:
        st.cache_data.clear()
    except Exception:
        pass


def remove_player_from_camp(entry_id: int, camp_id: int):
    entry_id = int(entry_id)
    camp_id = int(camp_id)
    cp_df = load_table("camp_players")
    if not cp_df.empty:
        cp_df = cp_df[~((cp_df["id"] == entry_id) & (cp_df["camp_id"] == camp_id))].copy()
        save_table("camp_players", cp_df)
        _recalc_camp_counts(camp_id)
        try:
            st.cache_data.clear()
        except Exception:
            pass


# ==============================================================================
# 3. AREA STORICO PARTITE & 4. FORMAZIONE MATCH (matches & match_lineups)
# ==============================================================================
def get_matches_df() -> pd.DataFrame:
    df = load_table("matches")
    if df.empty:
        return pd.DataFrame(columns=["id", "date", "match_name", "competition", "full_label"])
    df["date_str"] = df["date"].astype(str).str[:10]
    return df.sort_values(by=["date_str", "id"], ascending=[False, False]).reset_index(drop=True)


def save_match(data: dict, match_id: int = None) -> int:
    df = load_table("matches")
    m_date = str(data.get("date") or "")[:10]
    m_name = str(data.get("match_name") or "").strip()
    comp = str(data.get("competition") or "").strip()
    full_label = str(data.get("full_label") or f"{m_name} ({comp})").strip()

    row = {"date": m_date, "match_name": m_name, "competition": comp, "full_label": full_label}
    if match_id is not None and not df.empty and match_id in df["id"].values:
        idx = df.index[df["id"] == match_id][0]
        for k, v in row.items():
            df.loc[idx, k] = v
        mid = int(match_id)
    else:
        mid = get_next_id(df)
        row["id"] = mid
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_table("matches", df)
    return mid


def delete_match(match_id: int):
    df = load_table("matches")
    if not df.empty:
        df = df[df["id"] != match_id].copy()
        save_table("matches", df)
    ldf = load_table("match_lineups")
    if not ldf.empty and "match_id" in ldf.columns:
        ldf = ldf[ldf["match_id"] != match_id].copy()
        save_table("match_lineups", ldf)


def get_lineup_matches_summary() -> pd.DataFrame:
    ldf = load_table("match_lineups")
    mdf = get_matches_df()
    if ldf.empty and mdf.empty:
        return pd.DataFrame(columns=["date_str", "match_name", "competition", "starters_count", "finishers_count"])

    if not ldf.empty:
        ldf["date_str"] = ldf["date"].astype(str).str[:10]
        grp = (
            ldf.groupby("date_str", as_index=False)
            .agg(
                match_name=("match_name", "first"),
                starters_count=("jersey_number", lambda s: int(((s >= 1) & (s <= 15)).sum())),
                finishers_count=("jersey_number", lambda s: int(((s >= 16) & (s <= 23)).sum())),
            )
            .sort_values("date_str", ascending=False)
        )
    else:
        grp = pd.DataFrame(columns=["date_str", "match_name", "starters_count", "finishers_count"])

    if not mdf.empty:
        m_sub = mdf[["date_str", "competition", "match_name"]].drop_duplicates(subset=["date_str"]).rename(columns={"match_name": "m_official"})
        grp = grp.merge(m_sub, on="date_str", how="outer")
        grp["match_name"] = grp["m_official"].combine_first(grp["match_name"]).fillna("Match Nazionale")
        grp["competition"] = grp["competition"].fillna("")
        grp["starters_count"] = pd.to_numeric(grp["starters_count"], errors="coerce").fillna(0).astype(int)
        grp["finishers_count"] = pd.to_numeric(grp["finishers_count"], errors="coerce").fillna(0).astype(int)
        grp = grp.drop(columns=["m_official"], errors="ignore")
    else:
        grp["competition"] = ""
    return grp.sort_values("date_str", ascending=False).reset_index(drop=True)


def clone_match_lineup(source_date_str: str, target_date_str: str, target_match_name: str = "") -> int:
    """
    Clona la formazione 1-23 dalla partita `source_date_str` alla partita `target_date_str`.
    Ritorna il numero di maglie clonate.
    """
    src_clean = str(source_date_str)[:10]
    dst_clean = str(target_date_str)[:10]
    if not src_clean or not dst_clean or src_clean == dst_clean:
        return 0

    src_detail = get_match_lineup_detail(src_clean)
    conv = pd.concat([src_detail.get("starters", pd.DataFrame()), src_detail.get("finishers", pd.DataFrame())], ignore_index=True)
    if conv.empty:
        return 0

    if not target_match_name.strip():
        mdf = get_matches_df()
        m_hit = mdf[mdf["date_str"] == dst_clean] if not mdf.empty else pd.DataFrame()
        if not m_hit.empty:
            target_match_name = str(m_hit.iloc[0]["match_name"])
        else:
            target_match_name = f"Match {dst_clean}"

    entries = []
    for _, r in conv.iterrows():
        entries.append(
            {
                "jersey_number": int(r["jersey_number"]),
                "player_name": str(r["player_name"]),
                "role": str(r.get("role") or ""),
            }
        )
    save_match_lineup(dst_clean, target_match_name, entries, old_date_str=dst_clean)
    return len(entries)


def get_match_lineup_detail(match_date_str: str) -> dict:
    clean_date = str(match_date_str)[:10]
    ldf = load_table("match_lineups")
    players_df = get_players_df()
    camps_df = get_camps_df()

    if not ldf.empty:
        ldf["date_str"] = ldf["date"].astype(str).str[:10]
        sub = ldf[ldf["date_str"] == clean_date].sort_values("jersey_number").copy()
    else:
        sub = pd.DataFrame()

    if not sub.empty and not players_df.empty:
        p_meta = players_df[["id", "club", "department", "v_max", "code"]].rename(columns={"id": "player_id"})
        sub = sub.merge(p_meta, on="player_id", how="left")

    starters = sub[(sub["jersey_number"] >= 1) & (sub["jersey_number"] <= 15)].copy() if not sub.empty else pd.DataFrame()
    finishers = sub[(sub["jersey_number"] >= 16) & (sub["jersey_number"] <= 23)].copy() if not sub.empty else pd.DataFrame()

    convocati_23 = pd.concat([starters, finishers], ignore_index=True)
    lineup_pids = set(convocati_23["player_id"].dropna().astype(int).tolist()) if not convocati_23.empty and "player_id" in convocati_23.columns else set()
    lineup_names = set(convocati_23["player_name"].dropna().astype(str).str.strip().str.upper()) if not convocati_23.empty else set()
    for nm in list(lineup_names):
        ident = resolve_player_identity(nm)
        if ident.get("player_id") is not None:
            lineup_pids.add(int(ident["player_id"]))
        if ident.get("name_display"):
            lineup_names.add(str(ident["name_display"]).strip().upper())

    # Find associated camp of that week: priority to camp starting on the Monday before the match (0 <= match_date - start_date <= 7)
    camp_info = None
    non_convocati = pd.DataFrame()
    camp_players = pd.DataFrame()
    if not camps_df.empty:
        try:
            target_dt = pd.to_datetime(clean_date)
            camps_df = camps_df.copy()
            camps_df["dt"] = pd.to_datetime(camps_df["start_date"].astype(str).str[:10], errors="coerce")
            camps_df["days_after_start"] = (target_dt - camps_df["dt"]).dt.days
            camps_df["abs_diff"] = camps_df["days_after_start"].abs()

            same_week = camps_df[(camps_df["days_after_start"] >= 0) & (camps_df["days_after_start"] <= 7)].sort_values("days_after_start")
            near = same_week if not same_week.empty else camps_df[camps_df["abs_diff"] <= 7].sort_values("abs_diff")

            if not near.empty:
                c_row = near.iloc[0]
                cid = int(c_row["id"])
                camp_info = {
                    "id": cid,
                    "competition": str(c_row.get("competition") or ""),
                    "week_name": str(c_row.get("week_name") or ""),
                    "start_date": str(c_row.get("start_date") or "")[:10],
                }
                camp_players = get_camp_players_df(cid)
                if not camp_players.empty:
                    def _is_in_23(cp_row):
                        cp_pid = cp_row.get("player_id")
                        if pd.notna(cp_pid) and int(cp_pid) in lineup_pids:
                            return True
                        cp_nm = str(cp_row.get("player_name") or "").strip().upper()
                        if cp_nm in lineup_names:
                            return True
                        ident_cp = resolve_player_identity(cp_nm)
                        if ident_cp.get("player_id") is not None and int(ident_cp["player_id"]) in lineup_pids:
                            return True
                        return False

                    mask_in_23 = camp_players.apply(_is_in_23, axis=1)
                    non_convocati = camp_players[~mask_in_23].copy().reset_index(drop=True)
        except Exception:
            pass

    m_name = str(sub["match_name"].iloc[0]) if not sub.empty and pd.notna(sub["match_name"].iloc[0]) else ""
    if not m_name:
        mdf = get_matches_df()
        m_hit = mdf[mdf["date_str"] == clean_date]
        if not m_hit.empty:
            m_name = str(m_hit.iloc[0]["match_name"])

    return {
        "date": clean_date,
        "match_name": m_name,
        "starters": starters,
        "finishers": finishers,
        "non_convocati": non_convocati,
        "camp_associated": camp_info,
        "all_camp_players": camp_players,
    }


def save_match_lineup(match_date_str: str, match_name: str, entries: list, old_date_str: str = None):
    clean_date = str(match_date_str)[:10]
    old_clean = str(old_date_str or match_date_str)[:10]
    ldf = load_table("match_lineups")
    mdf = get_matches_df()

    if not ldf.empty:
        ldf["date_str"] = ldf["date"].astype(str).str[:10]
        ldf = ldf[~ldf["date_str"].isin([clean_date, old_clean])].drop(columns=["date_str"], errors="ignore").copy()

    mid = None
    if not mdf.empty:
        m_hit = mdf[mdf["date_str"] == clean_date]
        if not m_hit.empty:
            mid = int(m_hit.iloc[0]["id"])

    next_id = get_next_id(ldf)
    new_rows = []
    for item in entries:
        j_num = int(item.get("jersey_number", 0))
        p_name = str(item.get("player_name") or "").strip()
        if not p_name or j_num < 1 or j_num > 23:
            continue
        ident = resolve_player_identity(p_name)
        is_starter = 1 <= j_num <= 15
        # Per i titolari 1-15 il ruolo è legato alla posizione; per i finishers 16-23 deriva dal Roster FIR
        if not is_starter:
            role = str(ident.get("role") or item.get("role") or "")
        else:
            role = str(item.get("role") or ident.get("role") or "")
        status = "Starter" if is_starter else "Finisher"
        new_rows.append(
            {
                "id": next_id,
                "match_id": mid,
                "match_name": match_name.strip(),
                "date": clean_date,
                "jersey_number": j_num,
                "player_id": ident.get("player_id"),
                "player_name": ident.get("name_display") or p_name,
                "role": role,
                "is_starter": is_starter,
                "status": status,
            }
        )
        next_id += 1

    if new_rows:
        ldf = pd.concat([ldf, pd.DataFrame(new_rows)], ignore_index=True)
    save_table("match_lineups", ldf)


def delete_match_lineup(match_date_str: str):
    clean_date = str(match_date_str)[:10]
    ldf = load_table("match_lineups")
    if not ldf.empty:
        ldf["date_str"] = ldf["date"].astype(str).str[:10]
        ldf = ldf[ldf["date_str"] != clean_date].drop(columns=["date_str"], errors="ignore").copy()
        save_table("match_lineups", ldf)


def sync_oval_matches_and_lineups(force: bool = False) -> tuple[int, int]:
    """
    Sincronizza automaticamente lo Storico Partite e le Formazioni Ufficiali (Maglie 1-23)
    dai dati Oval Match ufficiali per la Nazionale Italiana (teamName == 'Italy').
    Ritorna (partite_sincronizzate, formazioni_sincronizzate).
    """
    ov_df = get_oval_matches_df()
    if ov_df.empty or "teamName" not in ov_df.columns:
        return 0, 0

    it = ov_df[ov_df["teamName"].astype(str).str.lower() == "italy"].copy()
    if it.empty:
        return 0, 0

    matches_df = get_matches_df()
    existing_dates = set(matches_df["date_str"].tolist()) if not matches_df.empty else set()
    ldf = load_table("match_lineups")
    existing_lineup_dates = set(ldf["date"].astype(str).str[:10].tolist()) if not ldf.empty and "date" in ldf.columns else set()

    m_synced = 0
    l_synced = 0

    for m_date, g_rows in it.groupby("match_date"):
        clean_date = str(m_date)[:10]
        if not clean_date or clean_date in ("NaT", "None", "nan"):
            continue

        first_r = g_rows.iloc[0]
        opp = str(first_r.get("opponent") or first_r.get("opponentFullName") or "").strip()
        game_desc = str(first_r.get("game") or "").strip()
        rseas = str(first_r.get("rseas") or "").strip()

        m_dt = pd.to_datetime(clean_date, errors="coerce")
        year = str(m_dt.year) if pd.notna(m_dt) else (rseas[-4:] if len(rseas) >= 4 else "2026")
        month = m_dt.month if pd.notna(m_dt) else 7

        if month in (2, 3):
            comp = f"6N {year}"
        elif month in (6, 7):
            comp = f"NC {year}" if year == "2026" else f"SUMMER TOUR {year[-2:]}"
        elif month in (10, 11):
            comp = f"NC Nov {year}" if year == "2026" else f"ANS {year}"
        else:
            comp = f"TEST {year}"

        m_name = f"ITALIA - {opp.upper()}" if opp else (game_desc.upper() if game_desc else "ITALIA")
        full_lbl = f"{m_name} {comp}".strip()

        # Save match if not existing or if forced
        if clean_date not in existing_dates or force:
            save_match({"date": clean_date, "match_name": m_name, "competition": comp, "full_label": full_lbl, "source": "oval"})
            m_synced += 1

        # Check for jersey numbers 1-23
        valid_jerseys = g_rows[(g_rows["JERSEY"] >= 1) & (g_rows["JERSEY"] <= 23)].sort_values("JERSEY")
        if len(valid_jerseys) >= 15:
            if clean_date not in existing_lineup_dates or force:
                entries = []
                for _, jr in valid_jerseys.iterrows():
                    j_num = int(jr["JERSEY"])
                    p_name = str(jr.get("fir_player_name") or jr.get("playerFullName") or jr.get("player") or "").strip()
                    pos = str(jr.get("pos") or "").strip()
                    entries.append({"jersey_number": j_num, "player_name": p_name, "role": pos})
                if entries:
                    save_match_lineup(clean_date, m_name, entries)
                    l_synced += 1

    return m_synced, l_synced


# ==============================================================================
# 5. AREA STORICO DATI GPS (gps_history — Foglio FULL D..AY)
# ==============================================================================
def get_gps_history_df(team_type: str = None) -> pd.DataFrame:
    df = load_table("gps_history")
    if df.empty:
        cols = ["id", "team_type", "team_name", "source_file", "excel_row"] + [c[0] for c in FIR_COLUMNS_META]
        return pd.DataFrame(columns=cols)
    df["date_str"] = df["date"].astype(str).replace({"NaT": "", "None": "", "nan": ""}).str[:10]
    if team_type and team_type != "all":
        df = df[df["team_type"] == team_type].copy()
    return df.sort_values(by=["date_str", "id"], ascending=[False, False]).reset_index(drop=True)


def get_history_team_counts() -> dict:
    df = load_table("gps_history")
    counts = {"nazionale": 0, "benetton": 0, "zebre": 0, "altro": 0, "total": len(df)}
    if not df.empty and "team_type" in df.columns:
        vc = df["team_type"].value_counts().to_dict()
        for k, v in vc.items():
            if k in counts:
                counts[k] = int(v)
            else:
                counts["altro"] += int(v)
    return counts


def save_gps_history_record(record_data: dict, record_id: int = None) -> int:
    df = load_table("gps_history")
    t_type = str(record_data.get("team_type") or "nazionale").strip()
    t_name_map = {
        "nazionale": "Nazionale Italiana",
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
    }
    t_name = str(record_data.get("team_name") or t_name_map.get(t_type, "Altro Club")).strip()

    clean_row = {
        "team_type": t_type,
        "team_name": t_name,
        "source_file": str(record_data.get("source_file") or "Inserimento Manuale"),
        "excel_row": record_data.get("excel_row"),
    }

    for col, _, _, _, ctype in FIR_COLUMNS_META:
        if col in record_data:
            val = record_data.get(col)
            if val in (None, ""):
                clean_row[col] = np.nan if ctype == "float" else None
            elif ctype == "float":
                try:
                    clean_row[col] = float(val)
                except Exception:
                    clean_row[col] = np.nan
            elif ctype == "date":
                clean_row[col] = str(val).strip()[:10]
            else:
                clean_row[col] = str(val).strip()

    if record_id is not None and not df.empty and record_id in df["id"].values:
        idx = df.index[df["id"] == record_id][0]
        for k, v in clean_row.items():
            df.loc[idx, k] = v
        rid = int(record_id)
    else:
        rid = get_next_id(df)
        clean_row["id"] = rid
        clean_row["created_at"] = datetime.now().isoformat()
        df = pd.concat([df, pd.DataFrame([clean_row])], ignore_index=True)

    save_table("gps_history", df)
    return rid


def bulk_insert_gps_history(rows_df: pd.DataFrame) -> dict:
    if rows_df.empty:
        return {"inserted": 0, "duplicates": 0, "duplicate_df": pd.DataFrame(), "total": 0}
    df = load_table("gps_history")
    rows_df = rows_df.copy()
    rows_df["created_at"] = datetime.now().isoformat()
    for col in FIR_NUMERIC_COLS:
        if col in rows_df.columns:
            rows_df[col] = pd.to_numeric(rows_df[col], errors="coerce")

    def _make_key_series(d: pd.DataFrame) -> pd.Series:
        tt = d.get("team_type", pd.Series([""] * len(d))).fillna("").astype(str).str.strip().str.lower()
        dt = d.get("date", pd.Series([""] * len(d))).astype(str).str[:10].str.strip()
        pl = d.get("player_name", pd.Series([""] * len(d))).fillna("").astype(str).str.strip().str.upper()
        se = d.get("session_name", pd.Series([""] * len(d))).fillna("").astype(str).str.strip().str.upper()
        pe = d.get("period", pd.Series([""] * len(d))).fillna("").astype(str).str.strip().str.upper()
        di = pd.to_numeric(d.get("distance_m", pd.Series([0] * len(d))), errors="coerce").fillna(0.0).round(0).astype(int).astype(str)
        return tt + "|" + dt + "|" + pl + "|" + se + "|" + pe + "|" + di

    rows_df["_dup_key"] = _make_key_series(rows_df)

    if not df.empty:
        df["_dup_key"] = _make_key_series(df)
        existing_keys = set(df["_dup_key"].dropna().unique())

        is_dup_mask = rows_df["_dup_key"].isin(existing_keys)
        dup_df = rows_df[is_dup_mask].copy().drop(columns=["_dup_key"], errors="ignore")
        new_df = rows_df[~is_dup_mask].copy().drop(columns=["_dup_key"], errors="ignore")
        df = df.drop(columns=["_dup_key"], errors="ignore")
    else:
        dup_df = rows_df.iloc[0:0].copy().drop(columns=["_dup_key"], errors="ignore")
        new_df = rows_df.copy().drop(columns=["_dup_key"], errors="ignore")

    # Duplicati interni al dataset inviato
    if not new_df.empty:
        new_df["_dup_key"] = _make_key_series(new_df)
        internal_dups = new_df[new_df.duplicated(subset=["_dup_key"], keep="first")]
        if not internal_dups.empty:
            dup_df = pd.concat([dup_df, internal_dups.drop(columns=["_dup_key"], errors="ignore")], ignore_index=True)
            new_df = new_df.drop_duplicates(subset=["_dup_key"], keep="first")
        new_df = new_df.drop(columns=["_dup_key"], errors="ignore")

    if not new_df.empty:
        combined = pd.concat([df, new_df], ignore_index=True)
        combined["id"] = range(1, len(combined) + 1)
        save_table("gps_history", combined)
        try:
            get_history_team_counts.clear()
            get_players_df.clear()
        except Exception:
            pass

    return {
        "inserted": len(new_df),
        "duplicates": len(dup_df),
        "duplicate_df": dup_df.reset_index(drop=True),
        "total": len(rows_df),
    }


def delete_gps_history_record(record_id: int):
    df = load_table("gps_history")
    if not df.empty:
        df = df[df["id"] != record_id].copy()
        save_table("gps_history", df)


def delete_gps_history_records_by_ids(record_ids: list[int]) -> int:
    """Elimina velocemente un insieme di record GPS dal database tramite i loro ID univoci."""
    if not record_ids:
        return 0
    df = load_table("gps_history")
    if not df.empty:
        id_set = set(int(x) for x in record_ids)
        before_cnt = len(df)
        df = df[~df["id"].isin(id_set)].copy()
        deleted = before_cnt - len(df)
        if deleted > 0:
            save_table("gps_history", df)
        return deleted
    return 0


def delete_gps_history_session(date_str: str, session_name: str, team_type: str = None) -> int:
    """Elimina in blocco tutte le tracce GPS relative a una specifica seduta e data."""
    df = load_table("gps_history")
    if not df.empty:
        before_cnt = len(df)
        mask = (df["session_name"].astype(str).str.strip() == str(session_name).strip())
        if date_str:
            d_clean = str(date_str)[:10].strip()
            mask &= (df["date"].astype(str).str[:10].str.strip() == d_clean)
        if team_type and team_type != "all":
            mask &= (df["team_type"].astype(str).str.strip().str.lower() == str(team_type).strip().lower())
        df = df[~mask].copy()
        deleted = before_cnt - len(df)
        if deleted > 0:
            save_table("gps_history", df)
        return deleted
    return 0


# ==============================================================================
# 5b. MOTORE DI CALCOLO TASSI MEDI AL MINUTO PER TIPOLOGIA & SESSIONI VIRTUALI
# ==============================================================================
@st.cache_data(ttl=300)
def get_typology_rates_cache() -> dict:
    """
    Calcola e memorizza in cache i tassi medi al minuto (per tutte le metriche GPS)
    ponderati per durata effettiva (sum/sum) e le Vmax caratteristiche (p85) per:
    1. Ogni coppia (atleta, tipologia, team_type) e (atleta, tipologia)
    2. Ogni coppia (ruolo, tipologia, team_type) e (ruolo, tipologia)
    3. Ogni coppia (reparto, tipologia)
    4. Tipologia globale
    """
    gh = load_table("gps_history")
    if gh.empty:
        return {
            "player_team": {}, "player": {},
            "role_team": {}, "role": {},
            "dept": {}, "global": {},
            "rate_cols": []
        }

    types_map = get_fir_session_types()
    d_ser = gh["date"].astype(str).str[:10]
    s_ser = gh["session_name"].fillna("").astype(str).str.strip()
    k_ser = d_ser + "_" + s_ser
    mapped_typ = k_ser.map(types_map)
    unmapped_mask = mapped_typ.isna()
    if unmapped_mask.any():
        fallback_typ = s_ser[unmapped_mask].apply(detect_fir_session_type)
        gh_typ = mapped_typ.fillna(fallback_typ)
    else:
        gh_typ = mapped_typ

    gh = gh.copy()
    gh["typ"] = gh_typ
    gh["p_up"] = gh["player_name"].fillna("").astype(str).str.strip().str.upper()
    gh["team_type_clean"] = gh["team_type"].fillna("nazionale").astype(str).str.strip().str.lower()

    if "department" not in gh.columns:
        gh["department"] = gh["role"].map(ROLE_TO_DEPT).fillna("Avanti")
    else:
        gh["department"] = gh["department"].fillna(gh["role"].map(ROLE_TO_DEPT)).fillna("Avanti")

    dur_ser = pd.to_numeric(gh["duration"], errors="coerce").fillna(0.0)
    mpm_ser = pd.to_numeric(gh["m_per_min"], errors="coerce").fillna(0.0)

    # Filter representative sessions: exclude warm-up micro splits and non-representative walk-throughs for high intensity
    is_low_typ = gh["typ"].isin(["Clarity", "Reparto", "Extra", "RTP"])
    valid_mask = (dur_ser >= 10.0) & (is_low_typ | ((dur_ser >= 20.0) & (mpm_ser >= 35.0)))

    valid_gh = gh[valid_mask].copy()
    if valid_gh.empty:
        valid_gh = gh[dur_ser >= 10.0].copy()

    # Intensive and non-additive columns that must not be scaled linearly by duration
    INTENSIVE_COLS = {
        "profile_max_vel", "v_max", "v_max_pct", "duration",
        "m_per_min", "rhie_avg_recovery", "acc_density_time", "acc_density_space"
    }
    rate_cols = [c for c in FIR_NUMERIC_COLS if c not in INTENSIVE_COLS]

    dur_v = pd.to_numeric(valid_gh["duration"], errors="coerce").fillna(0.0).values
    for c in rate_cols:
        c_vals = pd.to_numeric(valid_gh[c], errors="coerce").fillna(0.0).values
        valid_gh[f"rate_{c}"] = np.where(dur_v > 0, c_vals / dur_v, 0.0)

    rate_col_names = [f"rate_{c}" for c in rate_cols]

    def _calc_grp_rates(grp_df: pd.DataFrame, group_cols: list) -> dict:
        if grp_df.empty:
            return {}
        out_rates = {}
        for k, sub in grp_df.groupby(group_cols):
            n = len(sub)
            vmax_vals = sub["v_max"].dropna()
            if len(vmax_vals) >= 3:
                v_max = float(vmax_vals.quantile(0.85))
            elif not vmax_vals.empty:
                v_max = float(vmax_vals.max())
            else:
                v_max = 28.0

            rhie_s = sub.get("rhie_avg_recovery")
            if rhie_s is not None:
                rhie_nz = rhie_s[rhie_s > 0]
                rhie_val = float(rhie_nz.median()) if not rhie_nz.empty else 0.0
            else:
                rhie_val = 0.0

            row_dict = {
                "sess_cnt": n,
                "v_max": round(v_max, 1),
                "rhie_avg_recovery": round(rhie_val, 1),
            }

            vals = sub[rate_col_names].values
            if n >= 6:
                # Esclusione dei 2 valori più bassi e 2 più alti per formula (tranne per la V max)
                sorted_vals = np.sort(vals, axis=0)
                trimmed = sorted_vals[2:-2, :]
                means = np.mean(trimmed, axis=0)
            elif n == 5:
                # Con 5 sedute, esclusione del valore più basso e del più alto
                sorted_vals = np.sort(vals, axis=0)
                trimmed = sorted_vals[1:-1, :]
                means = np.mean(trimmed, axis=0)
            else:
                means = np.mean(vals, axis=0)

            for idx_c, c in enumerate(rate_cols):
                row_dict[f"rate_{c}"] = float(means[idx_c])

            if len(group_cols) == 1:
                key = str(k).strip()
            elif len(group_cols) == 2:
                key = (str(k[0]).strip(), str(k[1]).strip())
            else:
                key = tuple(str(x).strip() for x in k)
            out_rates[key] = row_dict
        return out_rates

    player_team_rates = _calc_grp_rates(valid_gh, ["p_up", "typ", "team_type_clean"])
    player_rates = _calc_grp_rates(valid_gh, ["p_up", "typ"])

    valid_role = valid_gh[valid_gh["role"].fillna("") != ""].copy()
    role_team_rates = _calc_grp_rates(valid_role, ["role", "typ", "team_type_clean"])
    role_rates = _calc_grp_rates(valid_role, ["role", "typ"])

    valid_dept = valid_gh[valid_gh["department"].fillna("") != ""].copy()
    dept_rates = _calc_grp_rates(valid_dept, ["department", "typ"])

    global_rates = _calc_grp_rates(valid_gh, ["typ"])

    return {
        "player_team": player_team_rates,
        "player": player_rates,
        "role_team": role_team_rates,
        "role": role_rates,
        "dept": dept_rates,
        "global": global_rates,
        "rate_cols": rate_cols,
    }


def get_player_typology_profile(player_name: str, typology: str, team_type: str = None) -> dict:
    """
    Restituisce i tassi medi al minuto e Vmax stimata per un dato giocatore in una specifica tipologia di seduta.
    Gerarchia:
    1. Storico Personale Atleta nel team_type selezionato
    2. Storico Personale Atleta su tutte le sedute
    3. Media Ruolo nel team_type selezionato
    4. Media Ruolo generale
    5. Media Reparto generale
    6. Media Tipologia globale
    """
    cache = get_typology_rates_cache()
    p_ident = resolve_player_identity(player_name)
    p_name_up = str(p_ident.get("name_display") or player_name).strip().upper()
    role = str(p_ident.get("role") or "").strip()
    dept = str(p_ident.get("department") or ROLE_TO_DEPT.get(role, "Avanti")).strip()
    roster_vmax = p_ident.get("v_max")
    sigla = p_ident.get("sigla") or ""
    t_clean = str(team_type or "").strip().lower()

    p_t_rates = cache.get("player_team", {})
    p_rates = cache.get("player", {})
    r_t_rates = cache.get("role_team", {})
    r_rates = cache.get("role", {})
    d_rates = cache.get("dept", {})
    g_rates = cache.get("global", {})

    rates = None
    source_mode = "Media Globale Squadra"

    if t_clean and (p_name_up, typology, t_clean) in p_t_rates:
        rates = p_t_rates[(p_name_up, typology, t_clean)]
        cnt = int(rates.get("sess_cnt", 0))
        t_label = {"nazionale": "Nazionale", "benetton": "Benetton", "zebre": "Zebre"}.get(t_clean, t_clean)
        source_mode = f"Storico Atleta in {t_label} ({cnt} sedute)"
    elif (p_name_up, typology) in p_rates:
        rates = p_rates[(p_name_up, typology)]
        cnt = int(rates.get("sess_cnt", 0))
        source_mode = f"Storico Atleta ({cnt} sedute)"
    elif role and t_clean and (role, typology, t_clean) in r_t_rates:
        rates = r_t_rates[(role, typology, t_clean)]
        cnt = int(rates.get("sess_cnt", 0))
        t_label = {"nazionale": "Nazionale", "benetton": "Benetton", "zebre": "Zebre"}.get(t_clean, t_clean)
        source_mode = f"Media Ruolo {role} in {t_label} ({cnt} sedute)"
    elif role and (role, typology) in r_rates:
        rates = r_rates[(role, typology)]
        cnt = int(rates.get("sess_cnt", 0))
        source_mode = f"Media Ruolo {role} ({cnt} sedute)"
    elif dept and (dept, typology) in d_rates:
        rates = d_rates[(dept, typology)]
        cnt = int(rates.get("sess_cnt", 0))
        source_mode = f"Media Reparto {dept} ({cnt} sedute)"
    elif typology in g_rates:
        rates = g_rates[typology]
        cnt = int(rates.get("sess_cnt", 0))
        source_mode = f"Media Tipologia {typology} ({cnt} sedute)"
    else:
        if dept and (dept, "Rugby") in d_rates:
            rates = d_rates[(dept, "Rugby")]
            source_mode = f"Media Reparto {dept} (Fallback Rugby)"
        else:
            rates = g_rates.get("Rugby", {})
            source_mode = "Media Standard Fallback"

    # Vmax estimation
    est_vmax = rates.get("v_max") if rates else None
    if pd.isna(est_vmax) or est_vmax is None or est_vmax <= 0:
        if roster_vmax and pd.notna(roster_vmax) and roster_vmax > 0:
            est_vmax = float(roster_vmax) * (0.91 if dept == "Avanti" else 0.94)
        else:
            est_vmax = 26.5 if dept == "Avanti" else 29.5

    return {
        "player_name": p_ident.get("name_display") or player_name,
        "sigla": sigla,
        "role": role or "Pilone",
        "department": dept or "Avanti",
        "roster_vmax": roster_vmax,
        "est_vmax": round(float(est_vmax), 1),
        "rates": rates or {},
        "source_mode": source_mode,
        "rate_cols": cache["rate_cols"],
    }


def generate_virtual_player_gps_row(
    player_name: str,
    duration_min: float,
    typology: str,
    date_str: str,
    session_name: str,
    team_type: str = "nazionale",
    is_replacement: bool = False,
    custom_period: str = None,
) -> dict:
    """
    Genera un record completo nello schema standard FIR (Foglio FULL Colonne D-AY)
    moltiplicando i ratei medi al minuto per la durata inserita.
    """
    profile = get_player_typology_profile(player_name, typology, team_type=team_type)
    rates = profile["rates"]
    rate_cols = profile["rate_cols"]

    dur = max(0.1, float(duration_min))
    dist_rate = float(rates.get("rate_distance_m") or (58.0 if profile["department"] == "Avanti" else 68.0))
    dist_m = round(dist_rate * dur, 0)
    m_per_min = round(dist_m / dur, 1)

    v_max = profile["est_vmax"]
    prof_vmax = float(profile["roster_vmax"]) if profile["roster_vmax"] and pd.notna(profile["roster_vmax"]) else v_max
    vmax_pct = round((v_max / prof_vmax) * 100.0, 1) if prof_vmax > 0 else 88.0

    # Weekday in Italian
    try:
        dt = pd.to_datetime(date_str)
        day_names_it = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
        day_name = day_names_it[dt.weekday()]
    except Exception:
        day_name = "seduta"

    period_str = "[Ricostruito da Medie]" if is_replacement else (custom_period or "Sessione Autocreata [Medie]")

    t_map = {
        "nazionale": "Nazionale Italiana",
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
    }
    t_name = t_map.get(str(team_type).strip().lower(), "Nazionale Italiana")

    row = {
        "player_name": profile["player_name"],
        "sigla": profile["sigla"],
        "session_name": str(session_name).strip(),
        "date": str(date_str)[:10].strip(),
        "day_name": day_name,
        "role": profile["role"],
        "period": period_str,
        "department": profile["department"],
        "profile_max_vel": round(prof_vmax, 2),
        "v_max_pct": vmax_pct,
        "duration": round(dur, 1),
        "distance_m": dist_m,
        "m_per_min": m_per_min,
        "v_max": v_max,
        "team_type": team_type,
        "team_name": t_name,
        "source_file": "Ricostruzione GPS da Medie Tipologia",
        "source_mode": profile["source_mode"],
    }

    # Populate all numeric columns from rates
    for c in rate_cols:
        r_val = float(rates.get(f"rate_{c}") or 0.0)
        calc_val = r_val * dur
        if c in ("mp_0_12", "mp_12_20", "mp_20_25", "mp_25_35", "mp_35_50", "mp_50_100",
                 "speed_0_6", "speed_6_15", "speed_15_18", "speed_18_20", "speed_20_25", "speed_25_72"):
            row[c] = round(calc_val, 0)
        elif c in ("actions_gt_6", "actions_gt_15", "actions_gt_18", "actions_gt_20", "actions_gt_25",
                   "contacts", "rhie_total", "jump_20_40", "jump_gt_40", "cod_right", "cod_left"):
            row[c] = round(calc_val, 0)
        elif c in ("acc_volume", "player_load_total"):
            row[c] = round(calc_val, 1)
        else:
            row[c] = round(calc_val, 2)

    # Intensive and non-linear metrics calculated deterministically
    row["distance_m"] = round(dist_m, 0)
    row["duration"] = round(dur, 1)
    row["m_per_min"] = round(dist_m / dur, 1) if dur > 0 else 0.0
    row["acc_density_time"] = round(float(row.get("acc_volume", 0.0)) / dur, 2) if dur > 0 else 0.0
    row["acc_density_space"] = round((float(row.get("acc_volume", 0.0)) / dist_m) * 1000.0, 2) if dist_m > 0 else 0.0
    row["rhie_avg_recovery"] = round(float(rates.get("rhie_avg_recovery") or 0.0), 1)
    row["profile_max_vel"] = round(prof_vmax, 2)
    row["v_max_pct"] = vmax_pct

    # Derived aggregate metrics for display and verification
    row["hml_total"] = round(row.get("mp_25_35", 0) + row.get("mp_35_50", 0) + row.get("mp_50_100", 0), 0)
    row["hsr18_total"] = round(row.get("speed_18_20", 0) + row.get("speed_20_25", 0) + row.get("speed_25_72", 0), 0)
    row["hsr20_total"] = round(row.get("speed_20_25", 0) + row.get("speed_25_72", 0), 0)
    row["vhsr25"] = round(row.get("speed_25_72", 0), 0)

    return row


@st.cache_data(ttl=300)
def get_distinct_sessions_catalog(team_type: str = None) -> list[dict]:
    """Restituisce il catalogo ordinato di tutte le sedute presenti nell'archivio storico GPS."""
    gh = load_table("gps_history")
    if gh.empty:
        return []
    if team_type and team_type != "all":
        gh = gh[gh["team_type"].astype(str).str.strip().str.lower() == str(team_type).strip().lower()]
    if gh.empty:
        return []

    types_map = get_fir_session_types()
    gh["d_str"] = gh["date"].astype(str).str[:10].str.strip()
    gh["s_str"] = gh["session_name"].fillna("").astype(str).str.strip()
    gh = gh[~gh["d_str"].isin(["", "None", "nan", "NaT"]) & ~gh["s_str"].isin(["", "None", "nan"])].copy()
    if gh.empty:
        return []

    grp = gh.groupby(["d_str", "s_str", "team_type"]).agg(
        atleti_cnt=("player_name", "nunique"),
        dur_mean=("duration", "mean"),
        dist_sum=("distance_m", "sum"),
    ).reset_index()

    grp = grp.sort_values(by=["d_str", "s_str"], ascending=[False, True])
    res = []
    for _, r in grp.iterrows():
        d_val = str(r["d_str"])
        s_val = str(r["s_str"])
        k_s = f"{d_val}_{s_val}"
        typ = types_map.get(k_s) or detect_fir_session_type(s_val)
        res.append({
            "date": d_val,
            "session_name": s_val,
            "team_type": str(r["team_type"]),
            "typology": typ,
            "atleti_cnt": int(r["atleti_cnt"]),
            "dur_mean": round(float(r["dur_mean"]), 1),
            "label": f"{d_val} • {s_val} [{typ}] ({int(r['atleti_cnt'])} atleti)",
        })
    return res


def get_session_records_for_edit(date_str: str, session_name: str, team_type: str = None) -> pd.DataFrame:
    """Restituisce le righe registrate per una specifica seduta."""
    gh = load_table("gps_history")
    if gh.empty:
        return pd.DataFrame()
    d_clean = str(date_str)[:10].strip()
    s_clean = str(session_name).strip()
    mask = (gh["date"].astype(str).str[:10].str.strip() == d_clean) & (gh["session_name"].astype(str).str.strip() == s_clean)
    if team_type and team_type != "all":
        mask &= (gh["team_type"].astype(str).str.strip().str.lower() == str(team_type).strip().lower())
    sub = gh[mask].copy()
    if not sub.empty:
        if "department" not in sub.columns:
            sub["department"] = sub["role"].map(ROLE_TO_DEPT).fillna("Avanti")
        sort_cols = [c for c in ["department", "role", "player_name"] if c in sub.columns]
        if sort_cols:
            sub = sub.sort_values(by=sort_cols).reset_index(drop=True)
    return sub


# ==============================================================================
# 6. MOTORE DI MAPPING COLONNE PER CLUB (FIR / BENETTON / ZEBRE)
# ==============================================================================
def get_club_mappings() -> dict:
    df = load_table("club_mappings")
    res = {}
    if not df.empty and "club_name" in df.columns and "mapping_json" in df.columns:
        for _, r in df.iterrows():
            try:
                res[str(r["club_name"])] = json.loads(str(r["mapping_json"]))
            except Exception:
                pass
    return res


def save_club_mapping(club_name: str, mapping_dict: dict):
    df = load_table("club_mappings")
    m_json = json.dumps(mapping_dict, ensure_ascii=False)
    now_str = datetime.now().isoformat()
    if not df.empty and club_name in df["club_name"].values:
        idx = df.index[df["club_name"] == club_name][0]
        df.loc[idx, "mapping_json"] = m_json
        df.loc[idx, "created_at"] = now_str
    else:
        new_row = {"club_name": club_name, "mapping_json": m_json, "created_at": now_str}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_table("club_mappings", df)


# ==============================================================================
# 7. DATABASE OVAL MATCH (oval_matches.parquet)
# ==============================================================================
def get_oval_matches_df() -> pd.DataFrame:
    df = load_table("oval_matches")
    if df.empty:
        return pd.DataFrame()
    date_col = "date" if "date" in df.columns else "match_date"
    if date_col in df.columns:
        df["match_date"] = df[date_col].astype(str).replace({"None": "", "nan": "", "NaT": ""}).str[:10]
        df["date"] = df["match_date"]
    sort_cols = [c for c in ["match_date", "id"] if c in df.columns]
    if sort_cols:
        return df.sort_values(by=sort_cols, ascending=[False] * len(sort_cols)).reset_index(drop=True)
    return df


def import_oval_csv_dataframe(raw_df: pd.DataFrame, overwrite_existing: bool = False) -> dict:
    df = raw_df.copy()
    # Pulisce spazi bianchi o caratteri invisibili/tab dalle colonne (es. '\tTackleComplete', ' TotalRuckEntries ')
    df.columns = [str(c).strip() for c in df.columns]

    # Normalizza varianti di intestazione per le metriche chiave Oval Match (CIC, TCK, RCK)
    for c in list(df.columns):
        c_clean = c.strip()
        c_low = c_clean.lower().replace(" ", "").replace("_", "")
        if c_low == "totalcarriesincontact":
            df = df.rename(columns={c: "TotalCarriesInContact"})
        elif c_low in ("tacklecomplete", "tacklescomplete", "completedtackles", "tacklecompleted"):
            df = df.rename(columns={c: "TackleComplete"})
        elif c_low in ("totalruckentries", "ruckentries", "totalruckentry"):
            df = df.rename(columns={c: "TotalRuckEntries"})

    for num_col in ["TotalCarriesInContact", "TackleComplete", "TotalRuckEntries"]:
        if num_col in df.columns:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)

    if "playerId.1" in df.columns:
        df = df.rename(columns={"playerId.1": "playerId_dup"})

    def _parse_oval_date(row):
        se = str(row.get("scatterExtra") or "")
        if "(" in se and ")" in se:
            inside = se.split("(")[-1].split(")")[0].strip()
            if len(inside) == 10 and inside[4] == "-":
                return inside
        raw_d = str(row.get("date") or "").strip()
        if raw_d and raw_d != "nan":
            if len(raw_d) >= 10 and raw_d[4] == "-":
                return raw_d[:10]
            try:
                return pd.to_datetime(raw_d, format="%d/%m/%y").strftime("%Y-%m-%d")
            except Exception:
                try:
                    return pd.to_datetime(raw_d, dayfirst=True).strftime("%Y-%m-%d")
                except Exception:
                    return raw_d[:10]
        return None

    df["date"] = df.apply(_parse_oval_date, axis=1)
    df["match_date"] = df["date"]
    df["playerId"] = pd.to_numeric(df["playerId"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")

    p_df = get_players_df()
    opta_map = {}
    for _, r in p_df.iterrows():
        oid = str(r.get("opta_id") or "").strip().split(".")[0]
        if oid:
            opta_map[oid] = r["name_display"]

    name_cache = {}
    if "playerFullName" in df.columns:
        for raw_n in df["playerFullName"].dropna().unique():
            ident = resolve_player_identity(raw_n)
            name_cache[raw_n] = ident.get("name_display") or str(raw_n).strip()

    def _resolve_oval_p(row):
        oid = str(row.get("playerId") or "").strip()
        if oid in opta_map:
            return opta_map[oid]
        pfn = str(row.get("playerFullName") or "").strip()
        return name_cache.get(pfn, pfn)

    df["fir_player_name"] = df.apply(_resolve_oval_p, axis=1)

    for c in df.columns:
        if df[c].dtype == "object":
            df[c] = df[c].astype(str).replace({"nan": None, "None": None, "-": None})

    existing = load_table("oval_matches")
    before_cnt = len(existing)

    def _make_oval_key(d):
        pid = d["playerId"].fillna("").astype(str).str.split(".").str[0].str.strip()
        gid = d.get("gameId", pd.Series([""] * len(d))).fillna("").astype(str).str.split(".").str[0].str.strip()
        dt = d["date"].fillna("").astype(str).str[:10].str.strip()
        gm = d.get("game", pd.Series([""] * len(d))).fillna("").astype(str).str.strip().str.upper()
        return pid + "|" + dt + "|" + gid + "|" + gm

    df["_oval_key"] = _make_oval_key(df)
    overwritten_cnt = 0

    if not existing.empty:
        existing["_oval_key"] = _make_oval_key(existing)
        if overwrite_existing:
            new_keys = set(df["_oval_key"].dropna().unique())
            overwritten_mask = existing["_oval_key"].isin(new_keys)
            overwritten_cnt = int(overwritten_mask.sum())
            existing = existing[~overwritten_mask].copy().drop(columns=["_oval_key"], errors="ignore")
            dup_df = df.iloc[0:0].copy().drop(columns=["_oval_key"], errors="ignore")
            new_df = df.copy().drop(columns=["_oval_key"], errors="ignore")
        else:
            exist_keys = set(existing["_oval_key"].dropna().unique())
            is_dup = df["_oval_key"].isin(exist_keys)
            dup_df = df[is_dup].copy().drop(columns=["_oval_key"], errors="ignore")
            new_df = df[~is_dup].copy().drop(columns=["_oval_key"], errors="ignore")
            existing = existing.drop(columns=["_oval_key"], errors="ignore")
    else:
        dup_df = df.iloc[0:0].copy().drop(columns=["_oval_key"], errors="ignore")
        new_df = df.copy().drop(columns=["_oval_key"], errors="ignore")

    # Gestione duplicati interni allo stesso file CSV caricato
    if not new_df.empty:
        new_df["_oval_key"] = _make_oval_key(new_df)
        internal_dups = new_df[new_df.duplicated(subset=["_oval_key"], keep="first")]
        if not internal_dups.empty:
            dup_df = pd.concat([dup_df, internal_dups.drop(columns=["_oval_key"], errors="ignore")], ignore_index=True)
            new_df = new_df.drop_duplicates(subset=["_oval_key"], keep="first")
        new_df = new_df.drop(columns=["_oval_key"], errors="ignore")

    if not new_df.empty:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = existing.copy()

    combined["id"] = range(1, len(combined) + 1)
    save_table("oval_matches", combined)
    try:
        get_oval_matches_df.clear()
    except Exception:
        pass

    return {
        "total_after": len(combined),
        "added_or_updated": len(new_df),
        "net_new": len(new_df),
        "overwritten": overwritten_cnt,
        "duplicates": len(dup_df),
        "duplicate_df": dup_df.reset_index(drop=True),
    }


def add_manual_oval_match(data: dict) -> int:
    """
    Aggiunge manualmente una partita non monitorata da Oval (es. Serie A Elite, Pro D2, Accademia FIR)
    direttamente in oval_matches.parquet.
    """
    df = load_table("oval_matches")
    next_id = get_next_id(df)
    p_name = str(data.get("player_name") or "").strip()
    ident = resolve_player_identity(p_name)
    p_df = get_players_df()
    opta_id = ""
    club_default = ""
    role_default = ""
    if ident.get("player_id") is not None and not p_df.empty:
        m = p_df[p_df["id"] == ident["player_id"]]
        if not m.empty:
            opta_id = str(m.iloc[0].get("opta_id") or "").strip().split(".")[0]
            club_default = str(m.iloc[0].get("club") or "").strip()
            role_default = str(m.iloc[0].get("role") or "").strip()

    parts = p_name.split()
    short_name = f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) >= 2 else p_name
    match_date = _parse_any_date(data.get("date")) or datetime.now().strftime("%Y-%m-%d")
    ha = str(data.get("home_away") or "HOME").upper()
    is_home = ha == "HOME"
    score_str = str(data.get("result") or "").strip()
    starter_bool = bool(data.get("is_starter", True))
    minutes_val = float(data.get("minutes") or 0)
    jersey_val = data.get("jersey")
    team_name = str(data.get("team_name") or club_default or "").strip()
    opponent_name = str(data.get("opponent") or "").strip()
    game_label = str(data.get("game") or "").strip()
    if not game_label:
        game_label = f"{team_name} vs {opponent_name}" if is_home else f"{opponent_name} vs {team_name}"

    gid_manual = int(datetime.now().strftime("%y%m%d%H%M"))
    new_row = {
        "id": next_id,
        "playerId": opta_id or str(ident.get("player_id") or ""),
        "player": short_name,
        "playerFullName": p_name,
        "fir_player_name": p_name,
        "teamName": team_name,
        "teamAbbrevName": team_name,
        "teamFullName": team_name,
        "opponent": opponent_name,
        "opponentFullName": opponent_name,
        "pos": role_default,
        "G": 1,
        "Min": minutes_val,
        "Jersey": int(jersey_val) if jersey_val and pd.notna(jersey_val) and int(jersey_val) > 0 else np.nan,
        "MatchesStarted": 1 if starter_bool else 0,
        "game": game_label,
        "home": "True" if is_home else "False",
        "away": "False" if is_home else "True",
        "win": "True" if score_str.upper().startswith("W") else "False",
        "draw": "True" if score_str.upper().startswith("D") else "False",
        "loss": "True" if score_str.upper().startswith("L") else "False",
        "date": match_date,
        "match_date": match_date,
        "gameId": str(gid_manual),
        "result": score_str,
        "gameStatus": "manual",
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_table("oval_matches", df)
    return next_id


def delete_oval_match_record(record_id: int):
    df = load_table("oval_matches")
    if not df.empty and "id" in df.columns:
        df = df[df["id"] != int(record_id)].copy().reset_index(drop=True)
        save_table("oval_matches", df)


def get_oval_distinct_matches_df() -> pd.DataFrame:
    """
    Raggruppa i record di oval_matches per partita (match_date, game, teamName)
    restituendo l'elenco delle gare distinte presenti in archivio per consentirne
    la selezione e cancellazione rapida in blocco.
    """
    df = get_oval_matches_df()
    if df.empty:
        return pd.DataFrame(columns=["match_date", "game", "teamName", "result", "n_records", "total_min", "players_preview", "label"])

    work = df.copy()
    work["match_date"] = work["match_date"].fillna("").astype(str).str[:10].str.strip()
    work["game"] = work.get("game", pd.Series([""] * len(work))).fillna("").astype(str).str.strip()
    work["teamName"] = work.get("teamName", pd.Series([""] * len(work))).fillna("").astype(str).str.strip()
    work["result"] = work.get("result", pd.Series([""] * len(work))).fillna("").astype(str).str.strip()
    work["_min"] = pd.to_numeric(work.get("Min", 0), errors="coerce").fillna(0.0)
    p_col = "fir_player_name" if "fir_player_name" in work.columns else ("playerFullName" if "playerFullName" in work.columns else "player")
    work["_pname"] = work.get(p_col, pd.Series([""] * len(work))).fillna("").astype(str).str.strip()

    rows = []
    for (m_date, gm, tm), grp in work.groupby(["match_date", "game", "teamName"], dropna=False):
        if not m_date and not gm:
            continue
        res_vals = [r for r in grp["result"].unique().tolist() if r and r.lower() not in ("nan", "none")]
        res_str = res_vals[0] if res_vals else "-"
        p_list = [p for p in grp["_pname"].unique().tolist() if p and p.lower() not in ("nan", "none")]
        n_rec = len(grp)
        tot_min = int(round(grp["_min"].sum()))
        prev = ", ".join(p_list[:6]) + (f" (+{len(p_list) - 6})" if len(p_list) > 6 else "")
        disp_game = gm if gm else (tm if tm else "Partita")
        disp_team = f" [{tm}]" if tm and tm.lower() not in disp_game.lower() else ""
        lbl = f"{m_date} • {disp_game}{disp_team} ({res_str}) — {n_rec} giocatori ({tot_min}' min tot)"
        rows.append({
            "match_date": m_date,
            "game": gm,
            "teamName": tm,
            "result": res_str,
            "n_records": n_rec,
            "total_min": tot_min,
            "players_preview": prev,
            "label": lbl,
        })

    if not rows:
        return pd.DataFrame(columns=["match_date", "game", "teamName", "result", "n_records", "total_min", "players_preview", "label"])

    out_df = pd.DataFrame(rows).sort_values(by=["match_date", "game", "teamName"], ascending=[False, True, True]).reset_index(drop=True)
    return out_df


def delete_oval_match_by_game(match_date: str, game: str, team_name: str = None) -> int:
    """
    Elimina dall'archivio oval_matches tutti i record appartenenti a una specifica partita
    (identificata da data, nome partita e opzionalmente squadra), così da poter ricaricare il match.
    Restituisce il numero di record giocatore rimossi.
    """
    df = load_table("oval_matches")
    if df.empty:
        return 0

    date_col = "date" if "date" in df.columns else "match_date"
    d_series = df[date_col].fillna("").astype(str).replace({"None": "", "nan": "", "NaT": ""}).str[:10].str.strip()
    g_series = df.get("game", pd.Series([""] * len(df))).fillna("").astype(str).replace({"None": "", "nan": ""}).str.strip()
    t_series = df.get("teamName", pd.Series([""] * len(df))).fillna("").astype(str).replace({"None": "", "nan": ""}).str.strip()

    target_d = str(match_date or "").strip()[:10]
    target_g = str(game or "").strip()

    mask = (d_series == target_d) & (g_series == target_g)
    if team_name is not None:
        target_t = str(team_name).strip()
        mask = mask & (t_series == target_t)

    removed_cnt = int(mask.sum())
    if removed_cnt > 0:
        remaining = df[~mask].copy().reset_index(drop=True)
        if not remaining.empty:
            remaining["id"] = range(1, len(remaining) + 1)
        save_table("oval_matches", remaining)
        try:
            get_oval_matches_df.clear()
        except Exception:
            pass
    return removed_cnt


def get_oval_distinct_dates_df() -> pd.DataFrame:
    """
    Raggruppa i record di oval_matches per data (match_date / date)
    restituendo l'elenco delle date distinte presenti in archivio, con numero di partite,
    squadre coinvolte e totale record per consentire la cancellazione in blocco per data.
    """
    df = get_oval_matches_df()
    if df.empty:
        return pd.DataFrame(columns=["match_date", "n_matches", "n_records", "games_summary", "teams_summary", "label"])

    work = df.copy()
    date_col = "date" if "date" in work.columns else "match_date"
    work["match_date"] = work[date_col].fillna("").astype(str).str[:10].str.strip()
    work = work[work["match_date"].str.len() == 10].copy()
    if work.empty:
        return pd.DataFrame(columns=["match_date", "n_matches", "n_records", "games_summary", "teams_summary", "label"])

    work["game"] = work.get("game", pd.Series([""] * len(work))).fillna("").astype(str).str.strip()
    work["teamName"] = work.get("teamName", pd.Series([""] * len(work))).fillna("").astype(str).str.strip()

    rows = []
    for m_date, grp in work.groupby("match_date", dropna=False):
        games = [g for g in grp["game"].unique().tolist() if g and str(g).lower() not in ("nan", "none", "")]
        teams = [t for t in grp["teamName"].unique().tolist() if t and str(t).lower() not in ("nan", "none", "")]
        n_rec = len(grp)
        n_matches = max(len(games), 1)
        g_str = ", ".join(games[:3]) + (f" (+{len(games)-3} altre)" if len(games) > 3 else "")
        t_str = ", ".join(teams[:3]) + (f" (+{len(teams)-3} altre)" if len(teams) > 3 else "")
        desc = g_str or t_str or "Gare"
        lbl = f"{m_date} — {n_matches} gare ({n_rec} atleti) • {desc}"
        rows.append({
            "match_date": m_date,
            "n_matches": n_matches,
            "n_records": n_rec,
            "games_summary": g_str,
            "teams_summary": t_str,
            "label": lbl,
        })
    res_df = pd.DataFrame(rows)
    if not res_df.empty:
        res_df = res_df.sort_values(by="match_date", ascending=False).reset_index(drop=True)
    return res_df


def delete_oval_matches_by_date(match_date: str) -> int:
    """
    Elimina dall'archivio oval_matches TUTTI i record di tutte le partite disputate
    nella data specificata (YYYY-MM-DD), utile per ripulire un'intera giornata e ricaricarla.
    Restituisce il numero di record rimossi.
    """
    df = load_table("oval_matches")
    if df.empty:
        return 0

    date_col = "date" if "date" in df.columns else "match_date"
    d_series = df[date_col].fillna("").astype(str).replace({"None": "", "nan": "", "NaT": ""}).str[:10].str.strip()
    target_d = str(match_date or "").strip()[:10]

    mask = (d_series == target_d)
    removed_cnt = int(mask.sum())
    if removed_cnt > 0:
        remaining = df[~mask].copy().reset_index(drop=True)
        if not remaining.empty:
            remaining["id"] = range(1, len(remaining) + 1)
        save_table("oval_matches", remaining)
        try:
            get_oval_matches_df.clear()
        except Exception:
            pass
    return removed_cnt


DEFAULT_GIN_OPTA_IDS = {
    "123723", "237231", "172284", "229171", "243947", "248730", "118165", "236602", "136875", "206390",
    "244754", "192476", "174824", "107059", "192770", "196513", "244753", "102875", "208272", "128750",
    "174208", "103440", "240668", "255392", "250968", "202160", "143500", "250050", "161390", "197335",
    "120191", "237233", "103534", "236608", "238030", "238037", "256320", "236603", "216977", "241721",
    "110891", "134407", "236573", "229647", "256322", "156253", "201405", "205560", "236598", "229557",
    "130487", "236606", "238034", "153725", "123396", "125052", "207699", "174318", "209105", "159960",
    "248790", "146919", "256313", "253845", "249505", "120989", "130282", "236609", "250740", "244851",
    "255396",
}


def get_gin_player_names() -> list[str]:
    """Restituisce l'elenco dei nomi (name_display) inclusi nella Lista G.I.N. monitorata."""
    p_df = get_players_df()
    if p_df.empty:
        return []
    if "is_gin" not in p_df.columns:
        opta_clean = p_df["opta_id"].astype(str).str.split(".").str[0].str.strip()
        gin_names = p_df[opta_clean.isin(DEFAULT_GIN_OPTA_IDS)]["name_display"].dropna().astype(str).tolist()
    else:
        gin_names = p_df[p_df["is_gin"].astype(str).str.upper().isin(["SI", "TRUE", "1"])]["name_display"].dropna().astype(str).tolist()
    if "Marcos Gallorini" not in gin_names and "244753" in DEFAULT_GIN_OPTA_IDS:
        # Se Gallorini non è ancora nel roster oppure è marcato SI
        if "Marcos Gallorini" not in p_df["name_display"].values:
            gin_names.append("Marcos Gallorini")
    return sorted(list(set(gin_names)))


def save_gin_player_names(selected_names: list[str]):
    """Salva la Lista G.I.N. personalizzata nel database players.parquet."""
    p_df = get_players_df().copy()
    if p_df.empty:
        return
    sel_up = {str(n).strip().upper() for n in selected_names if str(n).strip()}
    p_df["is_gin"] = p_df["name_display"].astype(str).str.strip().str.upper().isin(sel_up).map(lambda x: "SI" if x else "NO")
    save_table("players", p_df)


def reset_gin_to_default():
    """Ripristina la Lista G.I.N. ai 71 giocatori ufficiali del report FIR."""
    p_df = get_players_df().copy()
    if p_df.empty:
        return
    opta_clean = p_df["opta_id"].astype(str).str.split(".").str[0].str.strip()
    p_df["is_gin"] = opta_clean.isin(DEFAULT_GIN_OPTA_IDS).map(lambda x: "SI" if x else "NO")
    save_table("players", p_df)


def build_gin_6_12_report(ref_monday_str: str = "2026-11-02", sort_mode: str = "minuti", only_gin: bool = True) -> dict:
    """
    Costruisce il Report 6\\12 Settimane G.I.N. (identico al modello Excel FIR 'Report Caps GIN MINUTI' e 'RUOLI')
    calcolando:
    - Stagione (1 Agosto - 30 Luglio)
    - 12 colonne settimanali (WEEK .. WEEK-11) a ritroso dal Lunedì della 'Settimana attuale'
    - Blocco 6 WEEKS: CAPS, MINUTI, Partite Titolare Consecutive (6w), Partite Consecutive Massime (6w), Partite Totali (12w)
    - Blocco STAGIONE: CAPS e MINUTI stagionali
    - Tabella ULTIMA GIORNATA: tutte le partite disputate nella WEEK (ultima settimana conclusa)
    """
    p_df = get_players_df().copy()
    ov_df = get_oval_matches_df().copy()

    try:
        ref_monday = pd.to_datetime(str(ref_monday_str)[:10])
    except Exception:
        ref_monday = pd.Timestamp("2026-11-02")
    # Align to Monday if user picked another weekday
    ref_monday = ref_monday - pd.Timedelta(days=ref_monday.weekday())
    ref_sunday = ref_monday + pd.Timedelta(days=6)

    # Determine Season (1 Agosto -> 30 Luglio)
    if ref_monday.month >= 8:
        s_year = ref_monday.year
    else:
        s_year = ref_monday.year - 1
    season_start = pd.Timestamp(f"{s_year}-08-01")
    season_end = pd.Timestamp(f"{s_year + 1}-07-30")
    season_label = f"{s_year}/{str(s_year + 1)[-2:]}"

    # 12 Weeks definitions (w=0 is WEEK 1 [settimana selezionata], w=1 is WEEK-1, ..., w=11 is WEEK-11)
    weeks_meta = []
    for w in range(12):
        w_start = ref_monday - pd.Timedelta(days=7 * w)
        w_end = w_start + pd.Timedelta(days=6)
        w_lbl = "WEEK 1" if w == 0 else f"WEEK-{w}"
        weeks_meta.append({
            "idx": w,
            "label": w_lbl,
            "start_dt": w_start,
            "end_dt": w_end,
            "start_str": w_start.strftime("%Y-%m-%d"),
            "end_str": w_end.strftime("%Y-%m-%d"),
            "start_disp": w_start.strftime("%d/%m/%y"),
            "end_disp": w_end.strftime("%d/%m/%y"),
        })

    if not ov_df.empty:
        ov_df["dt"] = pd.to_datetime(ov_df["match_date"], errors="coerce")
        ov_df["min_num"] = pd.to_numeric(ov_df.get("Min", 0), errors="coerce").fillna(0.0)
        ov_df["started_num"] = pd.to_numeric(ov_df.get("MatchesStarted", 0), errors="coerce").fillna(0.0)
        ov_df["jersey_num"] = pd.to_numeric(ov_df.get("Jersey", np.nan), errors="coerce")
        ov_df["is_starter"] = (ov_df["started_num"] >= 1) | ((ov_df["jersey_num"] >= 1) & (ov_df["jersey_num"] <= 15))
        ov_df["pid_clean"] = ov_df["playerId"].astype(str).str.split(".").str[0].str.strip()
        ov_season = ov_df[(ov_df["dt"] >= season_start) & (ov_df["dt"] <= min(season_end, ref_sunday))].copy()
    else:
        ov_season = pd.DataFrame()

    # Ensure Marcos Gallorini is also included if he has matches in ov_season and isn't in p_df yet
    roster_names_up = set(p_df["name_display"].dropna().astype(str).str.upper())
    if "MARCOS GALLORINI" not in roster_names_up:
        extra_g = pd.DataFrame([{
            "id": 9999,
            "name_display": "Marcos Gallorini",
            "last_name": "Gallorini",
            "first_name": "Marcos",
            "role": "Pilone",
            "department": "Avanti",
            "club": "Benetton Rugby",
            "birth_year": 2004,
            "opta_id": "244753",
            "is_gin": "SI",
        }])
        p_df = pd.concat([p_df, extra_g], ignore_index=True)

    gin_names_up = {n.upper() for n in get_gin_player_names()}
    if only_gin:
        p_df = p_df[p_df["name_display"].astype(str).str.strip().str.upper().isin(gin_names_up)].copy()

    role_order = {
        "Pilone": 1,
        "Tallonatore": 2,
        "Seconda Linea": 3,
        "Terza Linea": 4,
        "Mediano di Mischia": 5,
        "Apertura": 6,
        "Centro": 7,
        "Ala": 8,
        "Estremo": 9,
    }

    report_rows = []
    for _, prow in p_df.iterrows():
        p_name = str(prow.get("name_display") or "").strip()
        if not p_name:
            continue
        p_opta = str(prow.get("opta_id") or "").strip().split(".")[0]
        p_role = str(prow.get("role") or "").strip()
        p_dept = str(prow.get("department") or ROLE_TO_DEPT.get(p_role, "Avanti")).strip()
        p_club = str(prow.get("club") or "").strip()
        p_year = prow.get("birth_year")
        p_year_str = str(int(float(p_year))) if pd.notna(p_year) and str(p_year).strip() not in ("", "nan", "None") else ""

        if not ov_season.empty:
            if p_opta and p_opta not in ("", "nan", "None"):
                p_matches = ov_season[(ov_season["pid_clean"] == p_opta) | (ov_season["fir_player_name"].astype(str).str.upper() == p_name.upper())]
            else:
                p_matches = ov_season[ov_season["fir_player_name"].astype(str).str.upper() == p_name.upper()]
        else:
            p_matches = pd.DataFrame()

        p_played = p_matches[p_matches["min_num"] > 0] if not p_matches.empty else pd.DataFrame()
        season_caps = int(len(p_played))
        season_min = int(round(p_played["min_num"].sum())) if not p_played.empty else 0

        w_mins = []
        w_starters = []
        w_tips = []
        for wm in weeks_meta:
            if not p_played.empty:
                w_sub = p_played[(p_played["dt"] >= wm["start_dt"]) & (p_played["dt"] <= wm["end_dt"])]
            else:
                w_sub = pd.DataFrame()
            if not w_sub.empty:
                m_val = int(round(w_sub["min_num"].sum()))
                st_flag = bool(w_sub["is_starter"].any())
                r0 = w_sub.iloc[-1]
                g_str = str(r0.get("game") or "").strip()
                if g_str in ("None", "nan"):
                    g_str = ""
                res_str = str(r0.get("result") or "").strip()
                if res_str in ("None", "nan"):
                    res_str = ""
                res_part = f" • {res_str}" if res_str else ""
                tip_s = f"{g_str} ({str(r0.get('match_date') or '')[:10]}){res_part} • {'STARTER' if st_flag else 'FINISHER'} ({m_val}')"
            else:
                m_val = 0
                st_flag = False
                tip_s = ""
            w_mins.append(m_val)
            w_starters.append(st_flag)
            w_tips.append(tip_s)

        # 6 WEEKS calculations (indices 0..5)
        mins_6 = w_mins[:6]
        starts_6 = w_starters[:6]
        caps_6w = sum(1 for m in mins_6 if m > 0)
        min_6w = sum(mins_6)

        # Partite Titolare consecutive 6 weeks: '/' if 0 min in WEEK (idx 0), else max consecutive starts in indices 0..5
        if mins_6[0] == 0:
            consec_starts_str = "/"
        else:
            max_s = 0
            cur_s = 0
            for i in range(6):
                if mins_6[i] > 0 and starts_6[i]:
                    cur_s += 1
                    if cur_s > max_s:
                        max_s = cur_s
                else:
                    cur_s = 0
            consec_starts_str = str(max_s)

        # Partite Consecutive Massime 6 weeks: max streak of m > 0 in indices 0..5
        max_c = 0
        cur_c = 0
        for m in mins_6:
            if m > 0:
                cur_c += 1
                if cur_c > max_c:
                    max_c = cur_c
            else:
                cur_c = 0

        # Partite Totali 12 weeks
        tot_12w = sum(1 for m in w_mins if m > 0)

        row_item = {
            "opta_id": p_opta,
            "player_name": p_name,
            "role": p_role,
            "role_ord": role_order.get(p_role, 99),
            "department": p_dept,
            "club": p_club,
            "birth_year": p_year_str,
            "caps_6w": caps_6w,
            "min_6w": min_6w,
            "consec_starts_6w": consec_starts_str,
            "max_consec_6w": max_c,
            "tot_12w": tot_12w,
            "season_caps": season_caps,
            "season_min": season_min,
            "w_mins": w_mins,
            "w_starters": w_starters,
            "w_tips": w_tips,
        }
        for w_i in range(12):
            row_item[f"w_{w_i}"] = w_mins[w_i]
        report_rows.append(row_item)

    rep_df = pd.DataFrame(report_rows)
    if not rep_df.empty:
        if sort_mode == "ruoli":
            rep_df = rep_df.sort_values(by=["role_ord", "season_min", "player_name"], ascending=[True, False, True]).reset_index(drop=True)
        elif sort_mode == "min_6w":
            rep_df = rep_df.sort_values(by=["min_6w", "season_min", "player_name"], ascending=[False, False, True]).reset_index(drop=True)
        else:
            rep_df = rep_df.sort_values(by=["season_min", "min_6w", "season_caps", "player_name"], ascending=[False, False, False, True]).reset_index(drop=True)

    # Build ULTIMA GIORNATA table (all matches in WEEK = weeks_meta[0])
    last_round_rows = []
    if not ov_season.empty and weeks_meta:
        w0 = weeks_meta[0]
        w0_df = ov_season[(ov_season["dt"] >= w0["start_dt"]) & (ov_season["dt"] <= w0["end_dt"]) & (ov_season["min_num"] > 0)].copy()
        w0_df = w0_df.sort_values(by=["dt", "id"], ascending=[True, True])
        for _, mr in w0_df.iterrows():
            fn = str(mr.get("fir_player_name") or mr.get("playerFullName") or "").strip()
            ident_m = resolve_player_identity(fn)
            if ident_m.get("player_id") is None and "GALLORINI" not in fn.upper():
                continue
            resolved_name = (ident_m.get("name_display") or fn).strip()
            if only_gin and resolved_name.upper() not in gin_names_up and "GALLORINI" not in resolved_name.upper():
                continue
            disp_n = str(mr.get("player") or "").strip()
            if not disp_n or disp_n in ("None", "nan"):
                pts = fn.split()
                disp_n = f"{pts[0][0]}. {' '.join(pts[1:])}" if len(pts) >= 2 else fn
            d_raw = mr.get("dt")
            d_fmt = d_raw.strftime("%d/%m/%y") if pd.notna(d_raw) else str(mr.get("match_date") or "")[:10]
            h_str = str(mr.get("home") or "").strip().lower()
            ha_lbl = "HOME" if h_str in ("true", "1", "yes") else "AWAY"
            st_lbl = "STARTER" if bool(mr.get("is_starter")) else "FINISHER"
            last_round_rows.append({
                "id": int(mr["id"]) if pd.notna(mr.get("id")) else 0,
                "NOME": disp_n,
                "Giocatore": ident_m.get("name_display") or fn,
                "Data": d_fmt,
                "Home\\Away": ha_lbl,
                "Match": str(mr.get("game") or f"{mr.get('teamName', '')} vs {mr.get('opponentFullName', '')}"),
                "Score": str(mr.get("result") or ""),
                "Titolare": st_lbl,
                "Minuti": int(round(float(mr.get("min_num") or 0))),
            })

    return {
        "report_df": rep_df,
        "weeks_meta": weeks_meta,
        "last_round_df": pd.DataFrame(last_round_rows),
        "ref_monday_disp": ref_monday.strftime("%d/%m/%y"),
        "ref_next_monday_disp": ref_sunday.strftime("%d/%m/%y"),
        "season_label": season_label,
    }


# ==============================================================================
# 8. PARSER AUTOMATICO DEI 4 FORMATI CSV (FIR GPEXE, BENETTON GPEXE, ZEBRE, OVAL)
# ==============================================================================
GPEXE_SUMMARY_LABELS = {
    "unassigned role", "unassigned", "pilone", "tallonatore", "2 l", "3 l",
    "9", "10", "12-13", "centro", "ala-estremo", "team", "avanti", "trequarti",
}


def detect_csv_export_type(raw_df: pd.DataFrame, fname: str = "") -> str:
    """
    Riconosce automaticamente quale dei 4 CSV è stato caricato:
    - 'oval': RDM-5.csv (Oval Match database)
    - 'nazionale': session_...csv (GPEXE FIR 175 colonne)
    - 'benetton': gpexe_athsessions...csv (GPEXE Benetton 30 colonne) oppure Catapult Benetton
    - 'zebre': export_...csv (Catapult Zebre 34 colonne oppure GPEXE Zebre)
    """
    cols = set(str(c).strip() for c in raw_df.columns)
    cols_lower = {c.lower() for c in cols}
    fn_low = str(fname).lower()

    # 1. Riconoscimento Oval Match (RDM)
    if ("playerid" in cols_lower and ("playerfullname" in cols_lower or "gameid" in cols_lower)) or "totalcarriesincontact" in cols_lower:
        return "oval"
    if "oval" in fn_low or "rdm" in fn_low:
        return "oval"

    # 2. Controllo Nome File esplicito (priorità a Treviso / Benetton se indicato nel nome)
    if any(k in fn_low for k in ("benetton", "treviso", "ghirada", "ben_", "_tv", "tv_")):
        return "benetton"
    if any(k in fn_low for k in ("zebre", "parma", "zeb_")):
        return "zebre"
    if any(k in fn_low for k in ("nazionale", "italy", "fir_")):
        return "nazionale"

    # 3. Analisi Campionaria Atleti presenti nel file (Heuristic Roster Benetton vs Zebre)
    ben_roster_keys = {
        "lamaro", "menoncello", "brex", "zuliani", "negri", "cannone", "ferrari", "spagnolo",
        "lucchesi", "bernasconi", "nicotera", "ruzza", "favretto", "snyman", "izekor", "halafihi",
        "albornoz", "umaga", "garbisi", "marin", "fekitoa", "drago", "gallagher", "watson",
        "mendy", "lynagh", "casarin", "miranda", "zilocchi", "scafton", "tetaz", "alvarez",
        "avaca", "stowers", "manihera", "marini", "scquizzato", "belloni", "smith"
    }
    zeb_roster_keys = {
        "licata", "gesi", "trulla", "prisciantelli", "garcia", "fusco", "lucchin", "morisi",
        "bruno", "bertaccini", "ruggeri", "bianchi", "krumov", "zambonin", "canali", "rimpelli",
        "pitinari", "fischetti", "neculai", "bigi", "ribaldi", "stavile", "bozzoni", "hasa",
        "locatelli", "volpi", "montemauri", "gregorio", "ruffolo", "buonfiglio", "odiase"
    }

    ath_col = None
    for cand in ("athlete", "name", "player_name", "player", "atleta", "giocatore", "playerfullname"):
        if cand in cols_lower:
            for col in raw_df.columns:
                if str(col).strip().lower() == cand:
                    ath_col = col
                    break
            if ath_col:
                break

    ben_score = 0
    zeb_score = 0
    if ath_col and not raw_df.empty:
        sample_names = raw_df[ath_col].dropna().astype(str).unique()[:60]
        for s_n in sample_names:
            s_clean = s_n.lower().split(" - ")[0].strip()
            tokens = set(re.sub(r"[^\w\s]", " ", s_clean).split())
            if tokens & ben_roster_keys:
                ben_score += 1
            if tokens & zeb_roster_keys:
                zeb_score += 1

    # 4. Analisi Campi Testuali (Activity Name, Session Name, Match Labels, Tags, Notes)
    labels_str = ""
    for col_c in ("activity name", "period name", "last match label", "next match label", "category", "tags", "notes"):
        for orig_c in raw_df.columns:
            if str(orig_c).strip().lower() == col_c:
                sample_vals = raw_df[orig_c].dropna().astype(str).unique()[:30]
                labels_str += " " + " ".join(sample_vals).lower()

    if "benetton" in labels_str or "treviso" in labels_str:
        ben_score += 3
    if "zebre" in labels_str:
        zeb_score += 3

    # Se c'è evidenza chiara da roster o etichette
    if ben_score > zeb_score and ben_score >= 1:
        return "benetton"
    if zeb_score > ben_score and zeb_score >= 1:
        return "zebre"

    # 5. Formato GPEXE
    if "start date/time" in cols_lower and "athlete" in cols_lower:
        if len(raw_df.columns) >= 50 or "fir" in labels_str or "nazionale" in labels_str:
            return "nazionale"
        # GPEXE Club (circa 30 colonne): Benetton usa GPEXE standard
        if ben_score >= zeb_score:
            return "benetton"
        return "zebre"

    # 6. Formato Catapult / Altri GPS
    if "period name" in cols_lower or "activity name" in cols_lower or "hsrm (>20km/h)" in cols_lower or "total distance (m)" in cols_lower:
        if ben_score > zeb_score:
            return "benetton"
        return "zebre"

    if ben_score > zeb_score:
        return "benetton"
    return "nazionale"


def _parse_dur_mmss(val) -> float:
    if pd.isna(val) or val is None or str(val).strip() == "":
        return np.nan
    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return round(float(parts[0]) + float(parts[1]) / 60.0, 2)
            elif len(parts) == 3:
                p0 = float(parts[0])
                p1 = float(parts[1])
                p2 = float(parts[2])
                # Se p0 >= 4 oppure il terzo elemento è "00" o "0" (es. "41:42:00" o "34:22:00"),
                # si tratta del formato GPExe/Excel mm:ss[:00], dove p0 sono i minuti e p1 i secondi.
                # (Excel converte automaticamente mm:ss in hh:mm:ss aggiungendo :00 in coda).
                if p0 >= 4.0 or parts[2].strip() in ("00", "0"):
                    return round(p0 + p1 / 60.0, 2)
                # Altrimenti, formato standard hh:mm:ss (es. "01:15:30" -> 1h 15m 30s = 75.5 min)
                return round(p0 * 60.0 + p1 + p2 / 60.0, 2)
        except Exception:
            return np.nan
    try:
        f = float(s.replace(",", "."))
        # Se il numero è > 300 senza ':', si tratta di secondi grezzi (es. 2605 sec = 43.4 min)
        if f > 300.0:
            return round(f / 60.0, 2)
        return round(f, 2)
    except Exception:
        return np.nan


def _parse_num_val(val) -> float:
    if pd.isna(val) or val is None:
        return np.nan
    s = str(val).strip().replace(",", ".")
    if not s or s.lower() in ("nan", "none", "-"):
        return np.nan
    try:
        return float(s)
    except Exception:
        return np.nan


def _parse_any_date(val) -> str:
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None
    if s.isdigit() and 35000 <= int(s) <= 60000:
        return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(s))).strftime("%Y-%m-%d")
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        if "/" in s:
            return pd.to_datetime(s, dayfirst=True).strftime("%Y-%m-%d")
        return pd.to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        return s[:10]


def parse_standard_gps_csv(raw_df: pd.DataFrame, fname: str, team_type: str, only_fir_roster: bool = True) -> dict:
    """
    Converte automaticamente un CSV GPS (GPEXE FIR 175 col, GPEXE Benetton/Zebre 30 col,
    oppure Catapult Zebre 34 col) nel formato standard FIR gps_history.
    Restituisce {'df': DataFrame pronto per bulk_insert_gps_history, 'skipped_non_roster': list, 'skipped_summary': int, 'format_detected': str}
    """
    cols_lower = {str(c).strip().lower(): str(c) for c in raw_df.columns}
    is_gpexe = "start date/time" in cols_lower and "athlete" in cols_lower
    is_catapult_zebre = "period name" in cols_lower or "activity name" in cols_lower or "total distance (m)" in cols_lower

    t_name_map = {
        "nazionale": "Nazionale Italiana",
        "benetton": "Benetton Treviso",
        "zebre": "Zebre Parma",
        "altro": "Altro Club",
    }
    team_name_label = t_name_map.get(team_type, "Nazionale Italiana")

    rows_out = []
    skipped_non_roster = set()
    skipped_summary = 0

    if is_gpexe:
        fmt_desc = f"GPEXE ({len(raw_df.columns)} colonne)"
        for idx_r, r in raw_df.iterrows():
            raw_ath = str(r.get(cols_lower["athlete"]) or "").strip()
            if not raw_ath or raw_ath.lower() in ("nan", "none", "0"):
                continue
            if raw_ath.lower() in GPEXE_SUMMARY_LABELS:
                skipped_summary += 1
                continue
            raw_role = r.get(cols_lower.get("role", "role"))
            if (pd.isna(raw_role) or str(raw_role).strip() == "") and len(raw_ath.split()) == 1:
                skipped_summary += 1
                continue

            ident = resolve_player_identity(raw_ath)
            is_gallorini = "GALLORINI" in raw_ath.upper()
            if only_fir_roster and ident.get("player_id") is None and not is_gallorini:
                skipped_non_roster.add(raw_ath)
                continue

            p_name = "Marcos Gallorini" if is_gallorini and ident.get("player_id") is None else ident.get("name_display") or raw_ath.title()
            p_role = ident.get("role") or ("Pilone" if is_gallorini else str(raw_role or "").strip())
            p_sigla = ident.get("sigla") or ("GM" if is_gallorini else None)
            p_vmax_prof = ident.get("v_max")

            dt_str = _parse_any_date(r.get(cols_lower["start date/time"]))
            cat_val = str(r.get(cols_lower.get("category", "")) or "").strip()
            notes_val = str(r.get(cols_lower.get("notes", "")) or "").strip()
            tags_val = str(r.get(cols_lower.get("tags", "")) or "").strip()
            for v_clean in ("nan", "None"):
                if cat_val == v_clean:
                    cat_val = ""
                if notes_val == v_clean:
                    notes_val = ""
                if tags_val == v_clean:
                    tags_val = ""

            if team_type == "nazionale":
                sess_name = notes_val or cat_val or "Seduta FIR"
                period_val = tags_val or None
            else:
                sess_name = cat_val or notes_val or f"Seduta {team_name_label}"
                period_val = tags_val or notes_val or cat_val or None

            dur_min = _parse_dur_mmss(r.get(cols_lower.get("duration (mm:ss)", "")))
            dist_m = _parse_num_val(r.get(cols_lower.get("distance (m)", "")))

            if "avg speed (m/min)" in cols_lower:
                m_min = _parse_num_val(r.get(cols_lower["avg speed (m/min)"]))
            elif "avg speed (km/h)" in cols_lower:
                av_kmh = _parse_num_val(r.get(cols_lower["avg speed (km/h)"]))
                m_min = round(av_kmh * 1000.0 / 60.0, 1) if pd.notna(av_kmh) and av_kmh > 0 else np.nan
            else:
                m_min = np.nan
            if (pd.isna(m_min) or m_min == 0) and pd.notna(dist_m) and pd.notna(dur_min) and dur_min > 0:
                m_min = round(dist_m / dur_min, 1)

            vmax_val = _parse_num_val(r.get(cols_lower.get("max speed (km/h)", "")))
            vmax_pct = _parse_num_val(r.get(cols_lower.get("max speed% (%)", "")))
            if pd.isna(vmax_pct) and pd.notna(vmax_val) and p_vmax_prof and p_vmax_prof > 0:
                vmax_pct = round((vmax_val / p_vmax_prof) * 100.0, 1)

            z5 = _parse_num_val(r.get(cols_lower.get("distance/speed z5 (m)", "")))
            z6 = _parse_num_val(r.get(cols_lower.get("distance/speed z6 (m)", "")))
            sp_25_72 = (0.0 if pd.isna(z5) else z5) + (0.0 if pd.isna(z6) else z6) if (pd.notna(z5) or pd.notna(z6)) else np.nan

            day_name = None
            if dt_str:
                try:
                    it_days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
                    day_name = it_days[pd.to_datetime(dt_str).weekday()]
                except Exception:
                    day_name = None

            row_dict = {
                "team_type": team_type,
                "team_name": team_name_label,
                "source_file": fname,
                "excel_row": int(idx_r) + 2,
                "player_name": p_name,
                "sigla": p_sigla,
                "session_name": sess_name,
                "date": dt_str,
                "day_name": day_name,
                "role": p_role,
                "period": period_val,
                "profile_max_vel": p_vmax_prof if p_vmax_prof else np.nan,
                "v_max_pct": vmax_pct,
                "duration": dur_min,
                "distance_m": dist_m,
                "m_per_min": m_min,
                "mp_0_12": _parse_num_val(r.get(cols_lower.get("distance/met power z1 (m)", ""))),
                "mp_12_20": np.nan,
                "mp_20_25": _parse_num_val(r.get(cols_lower.get("distance/met power z2 (m)", ""))),
                "mp_25_35": _parse_num_val(r.get(cols_lower.get("distance/met power z3 (m)", ""))),
                "mp_35_50": _parse_num_val(r.get(cols_lower.get("distance/met power z4 (m)", ""))),
                "mp_50_100": _parse_num_val(r.get(cols_lower.get("distance/met power z5 (m)", ""))) if "distance/met power z5 (m)" in cols_lower else 0.0,
                "ai_12_20": np.nan,
                "ai_20_25": np.nan,
                "ai_25_40": _parse_num_val(r.get(cols_lower.get("met power events", ""))),
                "ai_40_50": np.nan,
                "ai_50_100": np.nan,
                "v_max": vmax_val,
                "speed_0_6": _parse_num_val(r.get(cols_lower.get("distance/speed z1 (m)", ""))),
                "speed_6_15": _parse_num_val(r.get(cols_lower.get("distance/speed z2 (m)", ""))),
                "speed_15_18": np.nan,
                "speed_18_20": _parse_num_val(r.get(cols_lower.get("distance/speed z3 (m)", ""))),
                "speed_20_25": _parse_num_val(r.get(cols_lower.get("distance/speed z4 (m)", ""))),
                "speed_25_72": round(sp_25_72, 2) if pd.notna(sp_25_72) else np.nan,
                "actions_gt_6": np.nan,
                "actions_gt_15": np.nan,
                "actions_gt_18": _parse_num_val(r.get(cols_lower.get("speed events", ""))),
                "actions_gt_20": _parse_num_val(r.get(cols_lower.get("%speed events", ""))),
                "actions_gt_25": np.nan,
                "acc_volume": _parse_num_val(r.get(cols_lower.get("acc events", ""))),
                "acc_density_time": np.nan,
                "acc_density_space": np.nan,
                "contacts": _parse_num_val(r.get(cols_lower.get("impacts", ""))),
                "rhie_avg_recovery": np.nan,
                "rhie_total": np.nan,
                "jump_20_40": _parse_num_val(r.get(cols_lower.get("jumps z2", ""))),
                "jump_gt_40": _parse_num_val(r.get(cols_lower.get("jumps z3", ""))),
                "cod_right": np.nan,
                "cod_left": np.nan,
                "player_load_total": np.nan,
                "actions_gt_70": np.nan,
                "actions_gt_85": np.nan,
            }
            rows_out.append(row_dict)

    elif is_catapult_zebre:
        fmt_desc = f"Catapult {team_name_label} ({len(raw_df.columns)} colonne)"
        name_col = cols_lower.get("name", list(raw_df.columns)[0])
        for idx_r, r in raw_df.iterrows():
            raw_full = str(r.get(name_col) or "").strip()
            if not raw_full or raw_full.lower() in ("nan", "none", "0"):
                continue
            raw_ath = raw_full.split(" - ")[0].strip() if " - " in raw_full else raw_full

            ident = resolve_player_identity(raw_ath)
            if only_fir_roster and ident.get("player_id") is None:
                skipped_non_roster.add(raw_ath)
                continue

            p_name = ident.get("name_display") or raw_ath
            p_role = ident.get("role") or ""
            p_sigla = ident.get("sigla") or None
            p_vmax_prof = ident.get("v_max")

            dt_str = _parse_any_date(r.get(cols_lower.get("date", "")))
            sess_name = str(r.get(cols_lower.get("activity name", "")) or "").strip() or f"Seduta {team_name_label}"
            period_val = str(r.get(cols_lower.get("period name", "")) or "").strip() or None

            dur_min = _parse_dur_mmss(r.get(cols_lower.get("duration", "")))
            dist_m = _parse_num_val(r.get(cols_lower.get("total distance (m)", "")))
            m_min = _parse_num_val(r.get(cols_lower.get("meterage per minute", "")))
            vmax_val = _parse_num_val(r.get(cols_lower.get("maximum speed (km/h)", "")))
            vmax_pct = _parse_num_val(r.get(cols_lower.get("max speed (%)", "")))

            hsr_18 = _parse_num_val(r.get(cols_lower.get("hsrm (>18km/hr) (m)", "")))
            hsr_20 = _parse_num_val(r.get(cols_lower.get("hsrm (>20km/h)", "")))
            vhsr_25 = _parse_num_val(r.get(cols_lower.get("vhsr m (25km/hr)", "")))

            c18 = 0.0 if pd.isna(hsr_18) else hsr_18
            c20 = 0.0 if pd.isna(hsr_20) else hsr_20
            c25 = 0.0 if pd.isna(vhsr_25) else vhsr_25

            sp_25_72 = round(max(0.0, c25), 2)
            sp_20_25 = round(max(0.0, c20 - c25), 2)
            sp_18_20 = round(max(0.0, c18 - c20), 2)

            day_name = None
            if dt_str:
                try:
                    it_days = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
                    day_name = it_days[pd.to_datetime(dt_str).weekday()]
                except Exception:
                    day_name = None

            row_dict = {
                "team_type": team_type,
                "team_name": team_name_label,
                "source_file": fname,
                "excel_row": int(idx_r) + 2,
                "player_name": p_name,
                "sigla": p_sigla,
                "session_name": sess_name,
                "date": dt_str,
                "day_name": day_name,
                "role": p_role,
                "period": period_val,
                "profile_max_vel": p_vmax_prof if p_vmax_prof else np.nan,
                "v_max_pct": round(vmax_pct, 2) if pd.notna(vmax_pct) else np.nan,
                "duration": dur_min,
                "distance_m": round(dist_m, 2) if pd.notna(dist_m) else np.nan,
                "m_per_min": round(m_min, 2) if pd.notna(m_min) else np.nan,
                "mp_0_12": np.nan,
                "mp_12_20": _parse_num_val(r.get(cols_lower.get("metabolic power band 2 total distance (m)", ""))),
                "mp_20_25": np.nan,
                "mp_25_35": _parse_num_val(r.get(cols_lower.get("distance > 25,5w (m)", ""))),
                "mp_35_50": 0.0,
                "mp_50_100": 0.0,
                "ai_12_20": np.nan,
                "ai_20_25": np.nan,
                "ai_25_40": _parse_num_val(r.get(cols_lower.get("n azioni >25,5w", ""))),
                "ai_40_50": np.nan,
                "ai_50_100": np.nan,
                "v_max": round(vmax_val, 2) if pd.notna(vmax_val) else np.nan,
                "speed_0_6": np.nan,
                "speed_6_15": np.nan,
                "speed_15_18": np.nan,
                "speed_18_20": sp_18_20,
                "speed_20_25": sp_20_25,
                "speed_25_72": sp_25_72,
                "actions_gt_6": np.nan,
                "actions_gt_15": np.nan,
                "actions_gt_18": np.nan,
                "actions_gt_20": _parse_num_val(r.get(cols_lower.get("efforts >20km", ""))),
                "actions_gt_25": np.nan,
                "acc_volume": _parse_num_val(r.get(cols_lower.get("total acceleration load", ""))),
                "acc_density_time": _parse_num_val(r.get(cols_lower.get("acceleration density", ""))),
                "acc_density_space": _parse_num_val(r.get(cols_lower.get("acceleration density index", ""))),
                "contacts": np.nan,
                "rhie_avg_recovery": np.nan,
                "rhie_total": np.nan,
                "jump_20_40": np.nan,
                "jump_gt_40": np.nan,
                "cod_right": np.nan,
                "cod_left": np.nan,
                "player_load_total": _parse_num_val(r.get(cols_lower.get("total player load", ""))),
                "actions_gt_70": _parse_num_val(r.get(cols_lower.get("efforts >70%", ""))),
                "actions_gt_85": _parse_num_val(r.get(cols_lower.get("efforts >80%", ""))),
            }
            rows_out.append(row_dict)
    else:
        fmt_desc = "Formato Custom"

    return {
        "df": pd.DataFrame(rows_out),
        "skipped_non_roster": sorted(skipped_non_roster),
        "skipped_summary": skipped_summary,
        "format_detected": fmt_desc,
    }


# ==============================================================================
# REPORT 6 WEEKS GPS (CARICHI SETTIMANALI & ACWR)
# ==============================================================================

GPS_6W_METRICS = {
    "DT": {
        "key": "DT",
        "name": "Distanza Totale (DT)",
        "short_name": "DT",
        "unit": "m",
        "desc": "Volume totale di corsa percorso nella settimana (metri)",
        "decimals": 0,
        "is_max": False,
        "color": "#16A34A",
    },
    "HML": {
        "key": "HML",
        "name": "High Metabolic Load (>25.5 W)",
        "short_name": "Hml >25.5 W",
        "unit": "m",
        "desc": "Distanza percorsa ad elevata potenza metabolica (> 25.5 W)",
        "decimals": 0,
        "is_max": False,
        "color": "#0284C7",
    },
    "HSR_18": {
        "key": "HSR_18",
        "name": "High Speed Running (>18 km/h)",
        "short_name": "HSR >18KM\\h",
        "unit": "m",
        "desc": "Metri di corsa ad alta velocità oltre 18 km/h",
        "decimals": 0,
        "is_max": False,
        "color": "#DC2626",
    },
    "HSR_20": {
        "key": "HSR_20",
        "name": "High Speed Running (>20 km/h)",
        "short_name": "HSR >20KM\\h",
        "unit": "m",
        "desc": "Metri di corsa ad alta intensità oltre 20 km/h",
        "decimals": 0,
        "is_max": False,
        "color": "#E11D48",
    },
    "HSR_25": {
        "key": "HSR_25",
        "name": "Sprint / Very High Speed (>25 km/h)",
        "short_name": "HSR >25KM\\h",
        "unit": "m",
        "desc": "Metri percorsi alla massima intensità di sprint (> 25 km/h)",
        "decimals": 0,
        "is_max": False,
        "color": "#9333EA",
    },
    "VMAX": {
        "key": "VMAX",
        "name": "Velocità Massima (Vmax)",
        "short_name": "Vmax",
        "unit": "km/h",
        "desc": "Picco massimo di velocità raggiunto nella settimana (km/h)",
        "decimals": 1,
        "is_max": True,
        "color": "#EA580C",
    },
}


def get_acwr_status(acwr_val: float) -> tuple:
    """Restituisce (label, bg_color, text_color) per il semaforo ACWR (Gabbett Sweet Spot)."""
    if acwr_val is None or np.isnan(acwr_val) or acwr_val <= 0:
        return ("/", "transparent", "#64748B")
    if acwr_val < 0.60:
        return ("Basso", "#FEF3C7", "#92400E")
    elif acwr_val < 0.80:
        return ("Mod. Basso", "#FEF9C3", "#854D0E")
    elif acwr_val <= 1.30:
        return ("Ottimale", "#DCFCE7", "#166534")
    elif acwr_val <= 1.50:
        return ("Allerta", "#FFEDD5", "#9A3412")
    else:
        return ("Pericolo", "#FEE2E2", "#991B1B")


def build_gps_6weeks_report(
    ref_monday_str: str = None,
    metric: str = "DT",
    only_gin: bool = True,
    sort_mode: str = "ruoli",
    team_filter: str = "all",
) -> dict:
    """
    Costruisce il Report Longitudinal 6 Weeks GPS (Carichi Settimanali & ACWR)
    - Allinea 6 settimane (Week di riferimento + 5 settimane precedenti)
    - Per ciascun atleta monitorato GIN calcola le 6 metriche ufficiali FIR (DT, HML, HSR18, HSR20, HSR25, Vmax)
    - Calcola Carico Acuto (7gg), Cronico (28gg) e Ratio ACWR per ogni metrica
    - Calcola medie per Ruolo (Piloni -> Estremi), per Reparto (Avanti, TreQuarti) e Squadra
    """
    gps_raw = get_gps_history_df(None if team_filter == "all" else team_filter).copy()
    p_df = get_players_df().copy()

    # Roster players with display info
    if p_df.empty:
        return {"report_df": pd.DataFrame(), "weeks_meta": [], "role_averages": {}, "dept_averages": {}, "squad_totals": {}}

    # Ensure Marcos Gallorini is included
    if "MARCOS GALLORINI" not in set(p_df["name_display"].dropna().astype(str).str.upper()):
        extra_g = pd.DataFrame([{
            "id": 9999,
            "name_display": "Marcos Gallorini",
            "last_name": "Gallorini",
            "first_name": "Marcos",
            "role": "Pilone",
            "department": "Avanti",
            "club": "Benetton Rugby",
            "birth_year": 2004,
            "opta_id": "244753",
            "is_gin": "SI",
        }])
        p_df = pd.concat([p_df, extra_g], ignore_index=True)

    gin_names_up = {n.upper() for n in get_gin_player_names()}
    if only_gin:
        p_df = p_df[p_df["name_display"].astype(str).str.strip().str.upper().isin(gin_names_up)].copy()

    # Determine reference Monday
    if ref_monday_str:
        try:
            ref_monday = pd.to_datetime(str(ref_monday_str)[:10])
        except Exception:
            _today = pd.to_datetime(datetime.date.today())
            ref_monday = _today - pd.Timedelta(days=_today.weekday())
    else:
        _today = pd.to_datetime(datetime.date.today())
        ref_monday = _today - pd.Timedelta(days=_today.weekday())
    ref_monday = ref_monday - pd.Timedelta(days=ref_monday.weekday())
    ref_sunday = ref_monday + pd.Timedelta(days=6)

    # 6 Weeks metadata (w=0 is Week, w=1 is Week-1, ..., w=5 is Week-5)
    weeks_meta = []
    for w in range(6):
        w_start = ref_monday - pd.Timedelta(days=7 * w)
        w_end = w_start + pd.Timedelta(days=6)
        w_lbl = "Week" if w == 0 else f"Week -{w}" if w != 2 else "Week - 2"
        weeks_meta.append({
            "idx": w,
            "label": w_lbl,
            "start_dt": w_start,
            "end_dt": w_end,
            "start_str": w_start.strftime("%Y-%m-%d"),
            "end_str": w_end.strftime("%Y-%m-%d"),
            "start_disp": w_start.strftime("%d/%m/%y"),
            "end_disp": w_end.strftime("%d/%m/%y"),
        })

    oldest_dt = weeks_meta[5]["start_dt"]
    newest_dt = weeks_meta[0]["end_dt"]

    # Pre-process GPS dataframe
    if not gps_raw.empty:
        gps_raw["dt"] = pd.to_datetime(gps_raw["date"], errors="coerce")
        gps = gps_raw[(gps_raw["dt"] >= oldest_dt) & (gps_raw["dt"] <= newest_dt)].copy()

        # Resolve player names
        res_cache = {}
        resolved_names = []
        for raw_pn in gps["player_name"]:
            if raw_pn not in res_cache:
                ident = resolve_player_identity(raw_pn)
                res_cache[raw_pn] = ident.get("name_display") or raw_pn
            resolved_names.append(res_cache[raw_pn])
        gps["player_resolved"] = resolved_names

        # Numeric conversions
        gps["dist_val"] = pd.to_numeric(gps.get("distance_m", 0), errors="coerce").fillna(0.0)
        gps["mp_25_35_val"] = pd.to_numeric(gps.get("mp_25_35", 0), errors="coerce").fillna(0.0)
        gps["mp_35_50_val"] = pd.to_numeric(gps.get("mp_35_50", 0), errors="coerce").fillna(0.0)
        gps["mp_50_100_val"] = pd.to_numeric(gps.get("mp_50_100", 0), errors="coerce").fillna(0.0)
        gps["hml_val"] = gps["mp_25_35_val"] + gps["mp_35_50_val"] + gps["mp_50_100_val"]

        gps["s18_val"] = pd.to_numeric(gps.get("speed_18_20", 0), errors="coerce").fillna(0.0)
        gps["s20_val"] = pd.to_numeric(gps.get("speed_20_25", 0), errors="coerce").fillna(0.0)
        gps["s25_val"] = pd.to_numeric(gps.get("speed_25_72", 0), errors="coerce").fillna(0.0)

        gps["hsr18_val"] = gps["s18_val"] + gps["s20_val"] + gps["s25_val"]
        gps["hsr20_val"] = gps["s20_val"] + gps["s25_val"]
        gps["hsr25_val"] = gps["s25_val"]
        gps["vmax_val"] = pd.to_numeric(gps.get("v_max", 0), errors="coerce").fillna(0.0)
    else:
        gps = pd.DataFrame()

    # Pre-index GPS by player and week
    player_week_stats = {}
    if not gps.empty:
        for w_idx, wm in enumerate(weeks_meta):
            ws = wm["start_dt"]
            we = wm["end_dt"]
            w_sub = gps[(gps["dt"] >= ws) & (gps["dt"] <= we)]
            if w_sub.empty:
                continue
            for p_up, p_grp in w_sub.groupby(w_sub["player_resolved"].str.upper()):
                if p_up not in player_week_stats:
                    player_week_stats[p_up] = {}
                vmax_max = float(p_grp["vmax_val"].max()) if not p_grp.empty else 0.0
                player_week_stats[p_up][w_idx] = {
                    "DT": float(p_grp["dist_val"].sum()),
                    "HML": float(p_grp["hml_val"].sum()),
                    "HSR_18": float(p_grp["hsr18_val"].sum()),
                    "HSR_20": float(p_grp["hsr20_val"].sum()),
                    "HSR_25": float(p_grp["hsr25_val"].sum()),
                    "VMAX": vmax_max,
                }

    # Role ordering
    role_order = {
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

    rows = []
    for _, prow in p_df.iterrows():
        pname = str(prow.get("name_display", "")).strip()
        pup = pname.upper()
        role = str(prow.get("role") or "Terza Linea")
        dept = str(prow.get("department") or ("Avanti" if role in ("Pilone", "Tallonatore", "Seconda Linea", "Terza Linea") else "TreQuarti"))
        club = str(prow.get("club") or "")
        birth_year = str(prow.get("birth_year") or "")

        # Extract 6-week values for each of the 6 metrics
        w_dict = player_week_stats.get(pup, {})
        metrics_data = {}
        for m_key in GPS_6W_METRICS.keys():
            is_mx = GPS_6W_METRICS[m_key]["is_max"]
            vals = []
            for w in range(6):
                val_raw = w_dict.get(w, {}).get(m_key, 0.0)
                vals.append(val_raw)
            acute = vals[0]
            if is_mx:
                chronic = float(np.max(vals[:4])) if any(v > 0 for v in vals[:4]) else 0.0
                acwr = round(acute / chronic, 2) if chronic > 0 else 0.0
            else:
                chronic = float(np.mean(vals[:4]))
                acwr = round(acute / chronic, 1) if chronic > 0 else 0.0
            metrics_data[m_key] = {
                "w_vals": vals,
                "acute": acute,
                "chronic": chronic,
                "acwr": acwr,
            }

        # Role rank
        r_rank = 9
        for rk, ro in role_order.items():
            if rk.lower() in role.lower():
                r_rank = ro
                break

        row_item = {
            "player_name": pname,
            "role": role,
            "department": dept,
            "club": club,
            "birth_year": birth_year,
            "role_ord": r_rank,
            "dept_ord": 0 if dept == "Avanti" else 1,
            "metrics": metrics_data,
        }
        rows.append(row_item)

    rep_df = pd.DataFrame(rows)

    # Sorting
    if not rep_df.empty:
        if sort_mode == "ruoli":
            rep_df = rep_df.sort_values(by=["dept_ord", "role_ord", "player_name"]).reset_index(drop=True)
        elif sort_mode == "carico_week":
            # Sort by week 0 value of active metric
            m_k = metric if metric in GPS_6W_METRICS else "DT"
            rep_df["sort_val"] = rep_df["metrics"].apply(lambda m: m.get(m_k, {}).get("acute", 0.0))
            rep_df = rep_df.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
        elif sort_mode == "acwr":
            m_k = metric if metric in GPS_6W_METRICS else "HML"
            rep_df["sort_val"] = rep_df["metrics"].apply(lambda m: m.get(m_k, {}).get("acwr", 0.0))
            rep_df = rep_df.sort_values(by="sort_val", ascending=False).reset_index(drop=True)
        else:
            rep_df = rep_df.sort_values(by=["dept_ord", "role_ord", "player_name"]).reset_index(drop=True)

    # Compute Role & Department Averages
    role_averages = {}
    dept_averages = {}
    squad_totals = {}

    roles_unique = [
        ("Pilone", "Avanti"),
        ("Tallonatore", "Avanti"),
        ("Seconda Linea", "Avanti"),
        ("Terza Linea", "Avanti"),
        ("Mediano di Mischia", "TreQuarti"),
        ("Apertura", "TreQuarti"),
        ("Centro", "TreQuarti"),
        ("Ala", "TreQuarti"),
    ]

    for m_key in GPS_6W_METRICS.keys():
        is_mx = GPS_6W_METRICS[m_key]["is_max"]
        role_averages[m_key] = {}
        for r_name, d_name in roles_unique:
            sub = [r for _, r in rep_df.iterrows() if r_name.lower() in str(r["role"]).lower()]
            if sub:
                avg_w = []
                for w in range(6):
                    w_vals = [r["metrics"][m_key]["w_vals"][w] for r in sub if r["metrics"][m_key]["w_vals"][w] > 0]
                    avg_w.append(round(float(np.mean(w_vals)), 1 if is_mx else 0) if w_vals else 0.0)
                acute = avg_w[0]
                chronic = round(float(np.mean(avg_w[:4])), 1 if is_mx else 0)
                acwr = round(acute / chronic, 1) if chronic > 0 else 0.0
                role_averages[m_key][r_name] = {"w_vals": avg_w, "acute": acute, "chronic": chronic, "acwr": acwr}

        dept_averages[m_key] = {}
        for d_name in ["Avanti", "TreQuarti"]:
            sub = [r for _, r in rep_df.iterrows() if r["department"] == d_name]
            if sub:
                avg_w = []
                for w in range(6):
                    w_vals = [r["metrics"][m_key]["w_vals"][w] for r in sub if r["metrics"][m_key]["w_vals"][w] > 0]
                    avg_w.append(round(float(np.mean(w_vals)), 1 if is_mx else 0) if w_vals else 0.0)
                acute = avg_w[0]
                chronic = round(float(np.mean(avg_w[:4])), 1 if is_mx else 0)
                acwr = round(acute / chronic, 1) if chronic > 0 else 0.0
                dept_averages[m_key][d_name] = {"w_vals": avg_w, "acute": acute, "chronic": chronic, "acwr": acwr}

        # Squad
        all_sub = [r for _, r in rep_df.iterrows()]
        if all_sub:
            avg_w = []
            for w in range(6):
                w_vals = [r["metrics"][m_key]["w_vals"][w] for r in all_sub if r["metrics"][m_key]["w_vals"][w] > 0]
                avg_w.append(round(float(np.mean(w_vals)), 1 if is_mx else 0) if w_vals else 0.0)
            acute = avg_w[0]
            chronic = round(float(np.mean(avg_w[:4])), 1 if is_mx else 0)
            acwr = round(acute / chronic, 1) if chronic > 0 else 0.0
            squad_totals[m_key] = {"w_vals": avg_w, "acute": acute, "chronic": chronic, "acwr": acwr}

    return {
        "report_df": rep_df,
        "weeks_meta": weeks_meta,
        "role_averages": role_averages,
        "dept_averages": dept_averages,
        "squad_totals": squad_totals,
        "ref_monday_disp": ref_monday.strftime("%d/%m/%Y"),
        "ref_sunday_disp": ref_sunday.strftime("%d/%m/%Y"),
        "metric": metric,
        "metrics_info": GPS_6W_METRICS,
    }


def get_available_franchige_days() -> list:
    """
    Ritorna la lista delle date disponibili per il Report Franchige Day,
    ordinata a ritroso dalla più recente, con etichetta descrittiva che indica
    se la giornata è un MATCH DAY (gare URC/Test Match) o un giorno di ALLENAMENTO GPS.
    """
    gps_df = get_gps_history_df()
    ov_df = get_oval_matches_df()

    gps_dates = set(gps_df["date_str"].dropna().unique()) if not gps_df.empty and "date_str" in gps_df.columns else set()
    ov_dates = set(ov_df["match_date"].dropna().unique()) if not ov_df.empty and "match_date" in ov_df.columns else set()

    all_dates = sorted([d for d in (gps_dates | ov_dates) if len(str(d)) == 10 and str(d)[:2] in ("20", "19")], reverse=True)

    day_options = []
    for d_str in all_dates:
        try:
            dt = pd.to_datetime(d_str)
            d_fmt = dt.strftime("%d/%m/%y")
        except Exception:
            d_fmt = d_str

        # Check if match day
        is_match = False
        games = []
        if not ov_df.empty and "match_date" in ov_df.columns:
            m_sub = ov_df[ov_df["match_date"] == d_str]
            if not m_sub.empty:
                is_match = True
                games = [str(g).strip() for g in m_sub["game"].dropna().unique() if str(g).strip()]

        # Check GPS count
        n_gps = 0
        if not gps_df.empty and "date_str" in gps_df.columns:
            sub_d = gps_df[gps_df["date_str"] == d_str]
            n_gps = int(sub_d["player_name"].nunique()) if "player_name" in sub_d.columns else len(sub_d)

        if is_match:
            g_desc = " • ".join(games[:2])
            lbl = f"{d_fmt} — MATCH DAY: {g_desc}"
        else:
            lbl = f"{d_fmt} — Allenamento ({n_gps} atleti GPS)"

        day_options.append((d_str, lbl, is_match, " • ".join(games)))

    return day_options


def build_franchige_day_report(
    sel_date_str: str = "2026-10-24",
    only_gin: bool = True,
    sort_mode: str = "ruoli",
    team_filter: str = "all",
) -> dict:
    """
    Costruisce il Report Franchige Day per la singola giornata selezionata:
    - Seleziona i giocatori GIN (o tutto il Roster FIR)
    - Estrae e aggrega il carico GPS giornaliero (DT, m/min, HML, HSR18, HSR20, HSR25, Vmax, Durata)
    - Se la giornata è un Match Day (o l'atleta ha disputato una gara su Oval), estrae Minuti, Partita, Impiego e Risultato
    - Calcola le medie per Ruolo FIR, Reparto (Avanti / TreQuarti) e Squadra
    """
    gps_raw = get_gps_history_df(None if team_filter == "all" else team_filter).copy()
    ov_df = get_oval_matches_df().copy()
    p_df = get_players_df().copy()

    if p_df.empty:
        return {
            "report_df": pd.DataFrame(),
            "is_match_day": False,
            "match_summary": "",
            "date_str": sel_date_str,
            "date_disp": sel_date_str,
            "dept_averages": {},
            "role_averages": {},
            "squad_totals": {},
        }

    # Ensure Marcos Gallorini is present
    if "MARCOS GALLORINI" not in set(p_df["name_display"].dropna().astype(str).str.upper()):
        extra_g = pd.DataFrame([{
            "id": 9999,
            "name_display": "Marcos Gallorini",
            "last_name": "Gallorini",
            "first_name": "Marcos",
            "role": "Pilone",
            "department": "Avanti",
            "club": "Benetton Rugby",
            "birth_year": 2004,
            "opta_id": "244753",
            "is_gin": "SI",
        }])
        p_df = pd.concat([p_df, extra_g], ignore_index=True)

    gin_names_up = {n.upper() for n in get_gin_player_names()}
    if only_gin:
        p_df = p_df[p_df["name_display"].astype(str).str.strip().str.upper().isin(gin_names_up)].copy()

    try:
        dt_obj = pd.to_datetime(sel_date_str)
        date_disp = dt_obj.strftime("%d/%m/%Y")
    except Exception:
        date_disp = sel_date_str

    # Filter GPS for sel_date_str
    if not gps_raw.empty and "date_str" in gps_raw.columns:
        gps_day = gps_raw[gps_raw["date_str"] == sel_date_str].copy()
    else:
        gps_day = pd.DataFrame()

    # Filter Oval for sel_date_str
    if not ov_df.empty and "match_date" in ov_df.columns:
        ov_day = ov_df[ov_df["match_date"] == sel_date_str].copy()
    else:
        ov_day = pd.DataFrame()

    is_match_day = not ov_day.empty
    match_games = [str(g).strip() for g in ov_day["game"].dropna().unique() if str(g).strip()] if is_match_day else []
    match_summary = " • ".join(match_games) if match_games else ("Nessuna partita ufficiale registrata" if not is_match_day else "Match Day")

    # Map GPS rows by normalized player key
    gps_by_player = {}
    if not gps_day.empty:
        res_cache = {}
        resolved_names = []
        for raw_pn in gps_day["player_name"]:
            if raw_pn not in res_cache:
                ident = resolve_player_identity(raw_pn)
                res_cache[raw_pn] = ident.get("name_display") or str(raw_pn)
            resolved_names.append(res_cache[raw_pn])
        gps_day["norm_name"] = resolved_names

        for p_norm, p_group in gps_day.groupby("norm_name"):
            tot_dur = float(pd.to_numeric(p_group.get("duration", 0), errors="coerce").fillna(0).sum())
            tot_dist = float(pd.to_numeric(p_group.get("distance_m", 0), errors="coerce").fillna(0).sum())
            m_min = round(tot_dist / tot_dur, 1) if tot_dur > 0 else float(pd.to_numeric(p_group.get("m_per_min", 0), errors="coerce").fillna(0).mean())

            # HML (>25.5 W)
            mp25 = pd.to_numeric(p_group.get("mp_25_35", 0), errors="coerce").fillna(0).sum()
            mp35 = pd.to_numeric(p_group.get("mp_35_50", 0), errors="coerce").fillna(0).sum()
            mp50 = pd.to_numeric(p_group.get("mp_50_100", 0), errors="coerce").fillna(0).sum()
            tot_hml = float(mp25 + mp35 + mp50)

            # HSR zones
            sp18 = pd.to_numeric(p_group.get("speed_18_20", 0), errors="coerce").fillna(0).sum()
            sp20 = pd.to_numeric(p_group.get("speed_20_25", 0), errors="coerce").fillna(0).sum()
            sp25 = pd.to_numeric(p_group.get("speed_25_72", 0), errors="coerce").fillna(0).sum()
            tot_hsr18 = float(sp18 + sp20 + sp25)
            tot_hsr20 = float(sp20 + sp25)
            tot_hsr25 = float(sp25)

            v_peak = float(pd.to_numeric(p_group.get("v_max", 0), errors="coerce").fillna(0).max())
            t_names = [str(t).strip() for t in p_group.get("team_name", pd.Series()).dropna().unique() if str(t).strip()]
            s_names = [str(s).strip() for s in p_group.get("session_name", pd.Series()).dropna().unique() if str(s).strip()]

            gps_by_player[str(p_norm).upper()] = {
                "duration": round(tot_dur, 1),
                "distance_m": round(tot_dist, 1),
                "m_per_min": round(m_min, 1),
                "hml": round(tot_hml, 1),
                "hsr_18": round(tot_hsr18, 1),
                "hsr_20": round(tot_hsr20, 1),
                "hsr_25": round(tot_hsr25, 1),
                "v_max": round(v_peak, 2),
                "team_name": ", ".join(t_names),
                "session_name": ", ".join(s_names),
                "has_gps": (tot_dist > 0 or tot_dur > 0),
            }

    # Map Oval rows by normalized player key
    oval_by_player = {}
    if not ov_day.empty:
        for _, ov_row in ov_day.iterrows():
            raw_p = str(ov_row.get("fir_player_name") or ov_row.get("Player") or "").strip()
            ident = resolve_player_identity(raw_p)
            norm_p = ident.get("name_display") or raw_p
            min_val = float(pd.to_numeric(ov_row.get("Min", 0), errors="coerce") or 0)
            st_val = float(pd.to_numeric(ov_row.get("MatchesStarted", 0), errors="coerce") or 0)
            jer_val = float(pd.to_numeric(ov_row.get("Jersey", 0), errors="coerce") or 0)
            is_st = (st_val >= 1) or (1 <= jer_val <= 15)

            oval_by_player[str(norm_p).upper()] = {
                "game": str(ov_row.get("game") or "").strip(),
                "match_min": int(round(min_val)),
                "is_starter": is_st,
                "jersey": int(jer_val) if jer_val > 0 else 0,
                "result": str(ov_row.get("result") or "").strip(),
                "team_name": str(ov_row.get("teamName") or ov_row.get("team") or "").strip(),
                "has_match": True,
            }

    role_order = {
        "Pilone": 1,
        "Tallonatore": 2,
        "Seconda Linea": 3,
        "Terza Linea": 4,
        "Mediano di Mischia": 5,
        "Apertura": 6,
        "Centro": 7,
        "Ala": 8,
        "Estremo": 9,
    }

    report_rows = []
    for _, prow in p_df.iterrows():
        p_name = str(prow.get("name_display") or "").strip()
        if not p_name:
            continue
        p_up = p_name.upper()
        role = str(prow.get("role") or "").strip()
        dept = str(prow.get("department") or ROLE_TO_DEPT.get(role, "Avanti")).strip()
        club = str(prow.get("club") or "").strip()
        b_year = str(prow.get("birth_year") or "").split(".")[0].strip()

        # GPS data
        g_info = gps_by_player.get(p_up, {
            "duration": 0.0,
            "distance_m": 0.0,
            "m_per_min": 0.0,
            "hml": 0.0,
            "hsr_18": 0.0,
            "hsr_20": 0.0,
            "hsr_25": 0.0,
            "v_max": 0.0,
            "team_name": club,
            "session_name": "",
            "has_gps": False,
        })

        # Match data
        o_info = oval_by_player.get(p_up, {
            "game": "",
            "match_min": 0,
            "is_starter": False,
            "jersey": 0,
            "result": "",
            "team_name": "",
            "has_match": False,
        })

        report_rows.append({
            "player_name": p_name,
            "role": role,
            "department": dept,
            "club": club,
            "birth_year": b_year,
            "role_idx": role_order.get(role, 99),
            # Match columns
            "has_match": o_info["has_match"],
            "game": o_info["game"],
            "match_min": o_info["match_min"],
            "is_starter": o_info["is_starter"],
            "jersey": o_info["jersey"],
            "result": o_info["result"],
            "match_team": o_info["team_name"],
            # GPS columns
            "has_gps": g_info["has_gps"],
            "duration": g_info["duration"],
            "distance_m": g_info["distance_m"],
            "m_per_min": g_info["m_per_min"],
            "hml": g_info["hml"],
            "hsr_18": g_info["hsr_18"],
            "hsr_20": g_info["hsr_20"],
            "hsr_25": g_info["hsr_25"],
            "v_max": g_info["v_max"],
            "session_name": g_info["session_name"],
        })

    rep_df = pd.DataFrame(report_rows)
    if rep_df.empty:
        return {
            "report_df": pd.DataFrame(),
            "is_match_day": is_match_day,
            "match_summary": match_summary,
            "date_str": sel_date_str,
            "date_disp": date_disp,
            "dept_averages": {},
            "role_averages": {},
            "squad_totals": {},
        }

    # Sorting
    if sort_mode == "ruoli":
        rep_df = rep_df.sort_values(by=["role_idx", "player_name"], ascending=[True, True])
    elif sort_mode == "match_min":
        rep_df = rep_df.sort_values(by=["has_match", "match_min", "distance_m"], ascending=[False, False, False])
    elif sort_mode == "distance_m":
        rep_df = rep_df.sort_values(by=["has_gps", "distance_m", "hml"], ascending=[False, False, False])
    elif sort_mode == "hml":
        rep_df = rep_df.sort_values(by=["has_gps", "hml", "distance_m"], ascending=[False, False, False])
    elif sort_mode == "hsr_18":
        rep_df = rep_df.sort_values(by=["has_gps", "hsr_18", "v_max"], ascending=[False, False, False])
    elif sort_mode == "v_max":
        rep_df = rep_df.sort_values(by=["has_gps", "v_max"], ascending=[False, False])
    else:
        rep_df = rep_df.sort_values(by=["role_idx", "player_name"])

    rep_df = rep_df.reset_index(drop=True)

    # Department & Role Averages (only considering athletes with active GPS or Match)
    def _calc_stats(subset: pd.DataFrame) -> dict:
        if subset.empty:
            return {
                "n_tot": 0, "n_gps": 0, "n_match": 0, "match_min_avg": 0, "match_min_tot": 0,
                "duration": 0, "distance_m": 0, "m_per_min": 0, "hml": 0,
                "hsr_18": 0, "hsr_20": 0, "hsr_25": 0, "v_max_avg": 0.0, "v_max_peak": 0.0,
            }
        gps_act = subset[subset["has_gps"] == True]
        m_act = subset[subset["has_match"] == True]

        return {
            "n_tot": len(subset),
            "n_gps": len(gps_act),
            "n_match": len(m_act),
            "match_min_avg": int(round(m_act["match_min"].mean())) if not m_act.empty else 0,
            "match_min_tot": int(m_act["match_min"].sum()) if not m_act.empty else 0,
            "duration": round(float(gps_act["duration"].mean()), 1) if not gps_act.empty else 0.0,
            "distance_m": int(round(gps_act["distance_m"].mean())) if not gps_act.empty else 0,
            "m_per_min": round(float(gps_act["m_per_min"].mean()), 1) if not gps_act.empty else 0.0,
            "hml": int(round(gps_act["hml"].mean())) if not gps_act.empty else 0,
            "hsr_18": int(round(gps_act["hsr_18"].mean())) if not gps_act.empty else 0,
            "hsr_20": int(round(gps_act["hsr_20"].mean())) if not gps_act.empty else 0,
            "hsr_25": int(round(gps_act["hsr_25"].mean())) if not gps_act.empty else 0,
            "v_max_avg": round(float(gps_act["v_max"].mean()), 1) if not gps_act.empty else 0.0,
            "v_max_peak": round(float(gps_act["v_max"].max()), 2) if not gps_act.empty else 0.0,
        }

    dept_averages = {
        "Avanti": _calc_stats(rep_df[rep_df["department"] == "Avanti"]),
        "TreQuarti": _calc_stats(rep_df[rep_df["department"] == "TreQuarti"]),
    }
    squad_totals = _calc_stats(rep_df)

    role_averages = {}
    for r_k in ["Pilone", "Tallonatore", "Seconda Linea", "Terza Linea", "Mediano di Mischia", "Apertura", "Centro", "Ala", "Estremo"]:
        sub_r = rep_df[rep_df["role"] == r_k]
        if not sub_r.empty:
            role_averages[r_k] = _calc_stats(sub_r)

    return {
        "report_df": rep_df,
        "is_match_day": is_match_day,
        "match_summary": match_summary,
        "match_games": match_games,
        "date_str": sel_date_str,
        "date_disp": date_disp,
        "dept_averages": dept_averages,
        "role_averages": role_averages,
        "squad_totals": squad_totals,
    }


_PHOTO_CACHE = {}

PHOTO_MAPPINGS_FILE = os.path.join(os.path.dirname(__file__), "data", "player_photos.json")

def clear_photo_cache():
    """Svuota la cache in memoria delle foto giocatori per forzare la rilettura istantanea dal disco."""
    global _PHOTO_CACHE
    _PHOTO_CACHE.clear()

def get_player_photo_mappings() -> dict:
    """Carica la mappatura ufficiale nome giocatore -> percorso relativo foto."""
    if os.path.exists(PHOTO_MAPPINGS_FILE):
        try:
            with open(PHOTO_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    if "mappings" in data and isinstance(data["mappings"], dict):
                        return data["mappings"]
                    return data
        except Exception:
            pass
    return {}

def get_player_photo_doubts() -> dict:
    """Restituisce eventuali dubbi di abbinamento foto rilevati automaticamente."""
    if os.path.exists(PHOTO_MAPPINGS_FILE):
        try:
            with open(PHOTO_MAPPINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "doubts" in data and isinstance(data["doubts"], dict):
                    return data["doubts"]
        except Exception:
            pass
    return {}

def save_player_photo_mappings(mappings: dict, doubts: dict = None) -> bool:
    """Salva la mappatura foto nel file JSON e svuota la cache delle immagini."""
    try:
        payload = {
            "mappings": mappings,
            "doubts": doubts or {},
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(PHOTO_MAPPINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        clear_photo_cache()
        return True
    except Exception as e:
        print(f"Errore nel salvataggio player_photos.json: {e}")
        return False

def get_all_data_image_files() -> list:
    """Scansiona ricorsivamente la cartella 'data' e restituisce tutti i file immagine (.jpg, .png, ecc.) come percorsi relativi."""
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if not os.path.exists(data_dir):
        return []
    valid_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
    images = []
    for root, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            if f.lower().endswith(valid_exts):
                full_p = os.path.join(root, f)
                rel_p = os.path.relpath(full_p, data_dir)
                images.append(rel_p)
    return sorted(images)

def encode_image_file_to_base64(file_path: str, max_width: int = 240) -> str:
    """Carica un file immagine da disco, converte trasparenze e restituisce la stringa JPEG in base64."""
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        from PIL import Image
        import io
        with Image.open(file_path) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
                bg.paste(im, mask=im.split()[3])
                im = bg
            else:
                im = im.convert("RGB")

            w, h = im.size
            if w > max_width:
                new_h = int(round(h * (max_width / float(w))))
                im = im.resize((max_width, new_h), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        try:
            with open(file_path, "rb") as img_f:
                return base64.b64encode(img_f.read()).decode("utf-8")
        except Exception:
            return ""

def scan_and_auto_match_photos(players_df: pd.DataFrame = None, existing_mappings: dict = None) -> tuple:
    """
    Cerca automaticamente la corrispondenza tra i giocatori del roster e i file immagine presenti in data/.
    Regola fondamentale: SE HA DUBBI NON INSERISCE LA FOTO (lascia vuoto / sigla e registra il dubbio).
    
    Restituisce: (mappings, doubts)
    """
    import unicodedata
    if players_df is None or players_df.empty:
        players_df = get_players_df()
        
    image_files = get_all_data_image_files()
    mappings = dict(existing_mappings or {})
    doubts = {}
    
    def _norm(txt: str) -> str:
        t = unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode("utf-8")
        return re.sub(r"[^a-zA-Z0-9]+", " ", t).lower().strip()
        
    # Calcolo frequenza cognomi nel roster per individuare cognomi condivisi (ambigui)
    surname_counts = {}
    for _, p in players_df.iterrows():
        last = _norm(p.get("last_name") or "")
        if last:
            surname_counts[last] = surname_counts.get(last, 0) + 1
    ambiguous_surnames = {k for k, v in surname_counts.items() if v > 1}
    
    for _, p in players_df.iterrows():
        p_name = str(p["name_display"]).strip()
        first = _norm(p.get("first_name") or "")
        last = _norm(p.get("last_name") or "")
        
        candidates = []
        for rel in image_files:
            bname = os.path.splitext(os.path.basename(rel))[0]
            b_norm = _norm(bname)
            
            # Priorità 1: Sia il nome che il cognome sono presenti nel file (min 3 caratteri ciascuno)
            has_first = bool(first and len(first) >= 3 and (first in b_norm))
            has_last = bool(last and len(last) >= 3 and (last in b_norm))
            
            if has_first and has_last:
                candidates.append((1, rel, b_norm))
            # Priorità 2: Cognome unico nel roster (minimo 4 caratteri)
            elif has_last and len(last) >= 4 and (last not in ambiguous_surnames):
                candidates.append((2, rel, b_norm))
            # NOTA: MAI match sul solo nome proprio per evitare scambi di persona!
            
        if not candidates:
            if p_name not in mappings:
                mappings[p_name] = ""
            continue
            
        unique_basenames = {c[2] for c in candidates}
        if len(candidates) == 1:
            # Corrispondenza univoca certa
            mappings[p_name] = candidates[0][1]
        elif len(unique_basenames) == 1:
            # Stesso identico file presente in cartelle diverse (es. players 2 vs Piloni)
            # Preferisci la cartella 'players 2' o la prima
            p2 = [c[1] for c in candidates if "players 2" in c[1]]
            mappings[p_name] = p2[0] if p2 else candidates[0][1]
        else:
            # DUBBIO REALE: più file con nomi diversi corrispondono all'atleta!
            # Regola utente: SE HA DUBBI NON DEVE INSERIRE LA FOTO!
            doubts[p_name] = [c[1] for c in candidates]
            # Lascia vuoto se non c'era già una scelta manuale
            if p_name not in mappings:
                mappings[p_name] = ""
                
    return mappings, doubts

def get_player_photo_base64(player_name: str, max_width: int = 240, force_refresh: bool = False) -> str:
    """
    Restituisce la foto ufficiale del giocatore codificata in Base64 JPEG.
    Priorità assoluta alla mappatura utente salvata in player_photos.json:
    - Se associato a un file: carica quel file specifico.
    - Se l'utente ha scelto 'nessuna foto' o eliminato: restituisce stringa vuota (mostra sigla).
    - Se non presente nel file di mapping: esegue la scansione euristica di fallback.
    """
    p_clean = str(player_name).strip()
    if not p_clean:
        return ""

    import time
    import unicodedata
    now_ts = time.time()
    cache_key = (p_clean.upper(), max_width)

    # Controllo cache in memoria con verifica dinamica del file
    if not force_refresh and cache_key in _PHOTO_CACHE:
        cached_b64, cached_path, cached_mtime, cached_at = _PHOTO_CACHE[cache_key]
        if not cached_b64:
            if (now_ts - cached_at) < 1.5:
                return ""
        else:
            try:
                if cached_path and os.path.exists(cached_path) and os.path.getmtime(cached_path) == cached_mtime:
                    return cached_b64
            except Exception:
                pass

    data_dir = os.path.join(os.path.dirname(__file__), "data")

    # 1. Controlla prima la mappatura ufficiale in player_photos.json
    mappings = get_player_photo_mappings()
    matched_path = None

    if p_clean in mappings:
        rel_target = str(mappings[p_clean] or "").strip()
        if not rel_target or rel_target.upper() in ("NONE", "NULL", "-- NESSUNA FOTO (MOSTRA SOLO SIGLA) --", "--"):
            # L'utente ha esplicitamente rimosso o disabilitato la foto per mostrare la sola sigla
            _PHOTO_CACHE[cache_key] = ("", "", 0, now_ts)
            return ""
        cand = os.path.join(data_dir, rel_target) if not os.path.isabs(rel_target) else rel_target
        if os.path.exists(cand):
            matched_path = cand

    # 2. Se non trovato tramite mappatura diretta, prova matching euristico di fallback
    if not matched_path:
        def _norm(txt: str) -> str:
            t = unicodedata.normalize("NFKD", str(txt)).encode("ASCII", "ignore").decode("utf-8")
            return re.sub(r"[^a-zA-Z0-9]+", " ", t).lower().strip()

        p_norm = _norm(p_clean)
        parts = p_norm.split()
        first = parts[0] if len(parts) >= 2 else ""
        last = parts[-1] if parts else ""
        surname_parts = parts[1:] if len(parts) >= 2 else parts

        candidates = []
        valid_exts = (".jpg", ".png", ".jpeg", ".webp", ".bmp")

        for root, dirs, files in os.walk(data_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in files:
                f_low = f.lower()
                if f_low.endswith(valid_exts) and not f.startswith("."):
                    full_p = os.path.join(root, f)
                    f_norm = _norm(f)

                    if len(parts) >= 2 and all(p in f_norm for p in parts if len(p) >= 3):
                        candidates.append((0, full_p))
                    elif first and first in f_norm and any(sp in f_norm for sp in surname_parts if len(sp) >= 4):
                        candidates.append((1, full_p))
                    elif last and last in f_norm and first and first in f_norm:
                        candidates.append((1, full_p))
                    elif any(sp in f_norm for sp in surname_parts if len(sp) >= 4):
                        candidates.append((2, full_p))
                    elif last and len(last) >= 4 and last in f_norm:
                        candidates.append((2, full_p))

        if not candidates:
            _PHOTO_CACHE[cache_key] = ("", "", 0, now_ts)
            return ""

        candidates.sort(key=lambda item: (item[0], -os.path.getmtime(item[1]) if os.path.exists(item[1]) else 0))
        matched_path = candidates[0][1]

    matched_mtime = os.path.getmtime(matched_path) if os.path.exists(matched_path) else 0
    b64_str = encode_image_file_to_base64(matched_path, max_width=max_width)
    _PHOTO_CACHE[cache_key] = (b64_str, matched_path, matched_mtime, now_ts)
    return b64_str


def get_athlete_oval_career_profile(player_name: str) -> dict:
    """
    Estrae l'analisi completa della carriera e dei minutaggi per un singolo atleta dai dati Oval Match:
    - Informazioni anagrafiche e foto federale
    - Indicatori KPI di carriera (CAPS, Minuti, % Titolare, Record W-D-L)
    - Indicatori della stagione attuale (2026/27)
    - Analisi storica per stagione (2026/27 e stagioni precedenti)
    - Analisi squadre e club con cui ha giocato in carriera
    - Dettaglio cronologico di tutte le partite disputate con statistiche
    """
    p_df = get_players_df().copy()
    ov_df = get_oval_matches_df().copy()

    # Canonical player info
    p_row = pd.Series()
    p_canon = str(player_name).strip()
    if not p_df.empty:
        # Match by name_display
        m_p = p_df[p_df["name_display"].astype(str).str.strip().str.upper() == p_canon.upper()]
        if not m_p.empty:
            p_row = m_p.iloc[0]
            p_canon = str(p_row.get("name_display") or p_canon)

    role = str(p_row.get("role") or "").strip()
    dept = str(p_row.get("department") or ROLE_TO_DEPT.get(role, "Avanti")).strip()
    club = str(p_row.get("club") or "").strip()
    b_year = str(p_row.get("birth_year") or "").split(".")[0].strip()
    opta_id = str(p_row.get("opta_id") or "").split(".")[0].strip()
    is_gin = str(p_row.get("is_gin") or "SI").strip().upper() == "SI"

    # Calculate age
    age_str = ""
    if b_year.isdigit():
        age_str = f"{2026 - int(b_year)} anni"

    photo_b64 = get_player_photo_base64(p_canon)

    # Filter Oval matches for this player
    if ov_df.empty or "fir_player_name" not in ov_df.columns:
        return {
            "player_name": p_canon,
            "role": role,
            "department": dept,
            "club": club,
            "birth_year": b_year,
            "age_str": age_str,
            "opta_id": opta_id,
            "is_gin": is_gin,
            "photo_b64": photo_b64,
            "has_oval_data": False,
            "career_totals": {},
            "curr_season_totals": {},
            "seasons_df": pd.DataFrame(),
            "teams_df": pd.DataFrame(),
            "matches_df": pd.DataFrame(),
            "available_seasons": ["Tutte le Stagioni"],
        }

    # Normalize name match
    sub_ov = ov_df[ov_df["fir_player_name"].astype(str).str.strip().str.upper() == p_canon.upper()].copy()
    if sub_ov.empty:
        # Try last name matching
        parts = p_canon.split()
        if len(parts) >= 2:
            sub_ov = ov_df[ov_df["fir_player_name"].astype(str).str.upper().str.contains(parts[-1].upper())].copy()

    if sub_ov.empty:
        return {
            "player_name": p_canon,
            "role": role,
            "department": dept,
            "club": club,
            "birth_year": b_year,
            "age_str": age_str,
            "opta_id": opta_id,
            "is_gin": is_gin,
            "photo_b64": photo_b64,
            "has_oval_data": False,
            "career_totals": {},
            "curr_season_totals": {},
            "seasons_df": pd.DataFrame(),
            "teams_df": pd.DataFrame(),
            "matches_df": pd.DataFrame(),
            "available_seasons": ["Tutte le Stagioni"],
        }

    # Enrich sub_ov matches
    sub_ov["dt"] = pd.to_datetime(sub_ov["match_date"], errors="coerce")
    sub_ov = sub_ov.sort_values("dt", ascending=False).reset_index(drop=True)

    # Determine Rugby Season (1 Aug -> 30 Jul)
    def _get_season_str(d):
        if pd.isnull(d):
            return "N/A"
        y = d.year if d.month >= 8 else d.year - 1
        return f"{y}/{str(y + 1)[-2:]}"

    sub_ov["season"] = sub_ov["dt"].apply(_get_season_str)
    sub_ov["min_num"] = pd.to_numeric(sub_ov.get("Min", 0), errors="coerce").fillna(0.0)
    sub_ov["started_num"] = pd.to_numeric(sub_ov.get("MatchesStarted", 0), errors="coerce").fillna(0.0)
    sub_ov["jersey_num"] = pd.to_numeric(sub_ov.get("Jersey", np.nan), errors="coerce").fillna(0.0)
    sub_ov["is_starter"] = (sub_ov["started_num"] >= 1) | ((sub_ov["jersey_num"] >= 1) & (sub_ov["jersey_num"] <= 15))

    sub_ov["is_win"] = sub_ov.get("win", False).astype(str).str.lower() == "true"
    sub_ov["is_loss"] = sub_ov.get("loss", False).astype(str).str.lower() == "true"
    sub_ov["is_draw"] = sub_ov.get("draw", False).astype(str).str.lower() == "true"

    # Numeric stats if available
    sub_ov["carries_num"] = pd.to_numeric(sub_ov.get("TotalCarries", 0), errors="coerce").fillna(0.0)
    sub_ov["pcm_num"] = pd.to_numeric(sub_ov.get("PostContactMeters", 0), errors="coerce").fillna(0.0)
    sub_ov["tackles_num"] = pd.to_numeric(sub_ov.get("TotalTackleAttempts", 0), errors="coerce").fillna(0.0)
    sub_ov["missed_tackles_num"] = pd.to_numeric(sub_ov.get("MissedTackle", 0), errors="coerce").fillna(0.0)
    sub_ov["turnovers_won_num"] = pd.to_numeric(sub_ov.get("TotalTurnoversWon", 0), errors="coerce").fillna(0.0)
    sub_ov["penalties_num"] = pd.to_numeric(sub_ov.get("TotalPenalties", 0), errors="coerce").fillna(0.0)

    # 1. Career Totals
    total_caps = len(sub_ov)
    total_min = int(round(sub_ov["min_num"].sum()))
    total_starts = int(sub_ov["is_starter"].sum())
    total_bench = total_caps - total_starts
    starter_pct = round((total_starts / total_caps) * 100, 1) if total_caps > 0 else 0.0
    avg_min_match = round(total_min / total_caps, 1) if total_caps > 0 else 0.0

    total_wins = int(sub_ov["is_win"].sum())
    total_losses = int(sub_ov["is_loss"].sum())
    total_draws = int(sub_ov["is_draw"].sum())
    win_pct = round((total_wins / total_caps) * 100, 1) if total_caps > 0 else 0.0

    career_teams = [str(t).strip() for t in sub_ov["teamName"].dropna().unique() if str(t).strip() and str(t).strip().lower() != "none"]

    career_totals = {
        "total_caps": total_caps,
        "total_min": total_min,
        "total_starts": total_starts,
        "total_bench": total_bench,
        "starter_pct": starter_pct,
        "avg_min_match": avg_min_match,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "total_draws": total_draws,
        "win_pct": win_pct,
        "teams_count": len(career_teams),
        "teams_list": career_teams,
        "first_match_dt": sub_ov["dt"].min().strftime("%d/%m/%Y") if pd.notnull(sub_ov["dt"].min()) else "-",
        "last_match_dt": sub_ov["dt"].max().strftime("%d/%m/%Y") if pd.notnull(sub_ov["dt"].max()) else "-",
    }

    # 2. Current Season Stats (2026/27)
    curr_df = sub_ov[sub_ov["season"] == "2026/27"].copy()
    if not curr_df.empty:
        curr_caps = len(curr_df)
        curr_min = int(round(curr_df["min_num"].sum()))
        curr_starts = int(curr_df["is_starter"].sum())
        curr_bench = curr_caps - curr_starts
        curr_starter_pct = round((curr_starts / curr_caps) * 100, 1) if curr_caps > 0 else 0.0
        curr_avg_min = round(curr_min / curr_caps, 1) if curr_caps > 0 else 0.0
        curr_wins = int(curr_df["is_win"].sum())
        curr_losses = int(curr_df["is_loss"].sum())
        curr_teams = [str(t).strip() for t in curr_df["teamName"].dropna().unique() if str(t).strip()]
    else:
        curr_caps = 0
        curr_min = 0
        curr_starts = 0
        curr_bench = 0
        curr_starter_pct = 0.0
        curr_avg_min = 0.0
        curr_wins = 0
        curr_losses = 0
        curr_teams = []

    curr_season_totals = {
        "season_label": "2026/27",
        "caps": curr_caps,
        "minutes": curr_min,
        "starts": curr_starts,
        "bench": curr_bench,
        "starter_pct": curr_starter_pct,
        "avg_min": curr_avg_min,
        "wins": curr_wins,
        "losses": curr_losses,
        "teams": curr_teams,
    }

    def _calc_season_max_6w(grp_df):
        if grp_df.empty:
            return 0
        valid_df = grp_df.dropna(subset=["dt"]).sort_values("dt")
        if valid_df.empty:
            return int(round(grp_df["min_num"].sum()))

        # Metodo 1: Finestra mobile di 42 giorni (rolling 6W calendar)
        max_42d = 0
        for _, r in valid_df.iterrows():
            d_end = r["dt"]
            d_start = d_end - pd.Timedelta(days=41)
            sum_m = valid_df[(valid_df["dt"] >= d_start) & (valid_df["dt"] <= d_end)]["min_num"].sum()
            if sum_m > max_42d:
                max_42d = sum_m

        # Metodo 2: Settimane ISO (Lunedi-Domenica)
        d_min = valid_df["dt"].min()
        d_max = valid_df["dt"].max()
        start_mon = d_min - pd.Timedelta(days=d_min.weekday())
        end_sun = d_max + pd.Timedelta(days=(6 - d_max.weekday()))
        all_mondays = pd.date_range(start=start_mon, end=end_sun, freq="W-MON")
        weekly_mins = []
        for m in all_mondays:
            s = m + pd.Timedelta(days=6)
            w_m = valid_df[(valid_df["dt"] >= m) & (valid_df["dt"] <= s)]["min_num"].sum()
            weekly_mins.append(w_m)

        w_arr = np.array(weekly_mins)
        max_weekly_6w = 0
        if len(w_arr) >= 6:
            rolling_6w = np.convolve(w_arr, np.ones(6, dtype=int), mode="valid")
            max_weekly_6w = int(rolling_6w.max())
        else:
            max_weekly_6w = int(w_arr.sum()) if len(w_arr) > 0 else 0

        return int(round(max(max_42d, max_weekly_6w)))

    # 3. Breakdown by Season & Team
    seasons_rows = []
    seasons_summary_rows = []
    # Sort seasons descending
    all_seasons_sorted = sorted([s for s in sub_ov["season"].unique() if s != "N/A"], reverse=True)
    for s_lbl in all_seasons_sorted:
        s_grp = sub_ov[sub_ov["season"] == s_lbl]
        s_caps = len(s_grp)
        s_min = int(round(s_grp["min_num"].sum()))
        s_starts = int(s_grp["is_starter"].sum())
        s_bench = s_caps - s_starts
        s_st_pct = round((s_starts / s_caps) * 100, 1) if s_caps > 0 else 0.0
        s_avg_min = round(s_min / s_caps, 1) if s_caps > 0 else 0.0
        s_w = int(s_grp["is_win"].sum())
        s_l = int(s_grp["is_loss"].sum())
        s_d = int(s_grp["is_draw"].sum())
        s_wpct = round((s_w / s_caps) * 100, 1) if s_caps > 0 else 0.0
        s_max_6w = _calc_season_max_6w(s_grp)

        # Dettaglio per squadra in questa stagione
        teams_in_season = []
        for tm_name, tm_sub in s_grp.groupby("teamName"):
            tm_clean = str(tm_name).strip()
            if not tm_clean or tm_clean.lower() == "none":
                continue
            tm_caps = len(tm_sub)
            tm_min = int(round(tm_sub["min_num"].sum()))
            tm_starts = int(tm_sub["is_starter"].sum())
            tm_bench = tm_caps - tm_starts
            tm_st_pct = round((tm_starts / tm_caps) * 100, 1) if tm_caps > 0 else 0.0
            tm_avg_min = round(tm_min / tm_caps, 1) if tm_caps > 0 else 0.0
            tm_w = int(tm_sub["is_win"].sum())
            tm_l = int(tm_sub["is_loss"].sum())
            tm_d = int(tm_sub["is_draw"].sum())
            tm_wpct = round((tm_w / tm_caps) * 100, 1) if tm_caps > 0 else 0.0
            teams_in_season.append({
                "team": tm_clean,
                "caps": tm_caps,
                "starts": tm_starts,
                "bench": tm_bench,
                "starter_pct": tm_st_pct,
                "minutes": tm_min,
                "avg_minutes": tm_avg_min,
                "wins": tm_w,
                "losses": tm_l,
                "draws": tm_d,
                "win_pct": tm_wpct,
            })

        # Ordina: Nazionale (Italy) prima, poi Club per minuti decrescenti
        teams_in_season.sort(key=lambda x: (0 if "ital" in x["team"].lower() else 1, -x["minutes"]))

        seasons_summary_rows.append({
            "season": s_lbl,
            "teams": ", ".join([t["team"] for t in teams_in_season]) if teams_in_season else "-",
            "teams_list": [t["team"] for t in teams_in_season],
            "caps": s_caps,
            "starts": s_starts,
            "bench": s_bench,
            "starter_pct": s_st_pct,
            "minutes": s_min,
            "avg_minutes": s_avg_min,
            "max_6w_min": s_max_6w,
            "wins": s_w,
            "losses": s_l,
            "draws": s_d,
            "win_pct": s_wpct,
        })

        if len(teams_in_season) <= 1:
            tm_item = teams_in_season[0] if teams_in_season else {
                "team": "-", "caps": s_caps, "starts": s_starts, "bench": s_bench,
                "starter_pct": s_st_pct, "minutes": s_min, "avg_minutes": s_avg_min,
                "wins": s_w, "losses": s_l, "draws": s_d, "win_pct": s_wpct,
            }
            seasons_rows.append({
                "season": s_lbl,
                "team": tm_item["team"],
                "caps": tm_item["caps"],
                "starts": tm_item["starts"],
                "bench": tm_item["bench"],
                "starter_pct": tm_item["starter_pct"],
                "minutes": tm_item["minutes"],
                "avg_minutes": tm_item["avg_minutes"],
                "max_6w_min": s_max_6w,
                "wins": tm_item["wins"],
                "losses": tm_item["losses"],
                "draws": tm_item["draws"],
                "win_pct": tm_item["win_pct"],
                "is_single": True,
                "is_subtotal": False,
            })
        else:
            for tm_item in teams_in_season:
                seasons_rows.append({
                    "season": s_lbl,
                    "team": tm_item["team"],
                    "caps": tm_item["caps"],
                    "starts": tm_item["starts"],
                    "bench": tm_item["bench"],
                    "starter_pct": tm_item["starter_pct"],
                    "minutes": tm_item["minutes"],
                    "avg_minutes": tm_item["avg_minutes"],
                    "max_6w_min": None,
                    "wins": tm_item["wins"],
                    "losses": tm_item["losses"],
                    "draws": tm_item["draws"],
                    "win_pct": tm_item["win_pct"],
                    "is_single": False,
                    "is_subtotal": False,
                })
            # Riga Sub-totale per la stagione
            seasons_rows.append({
                "season": f"{s_lbl} TOT.",
                "team": f"Tutte le Squadre ({len(teams_in_season)})",
                "caps": s_caps,
                "starts": s_starts,
                "bench": s_bench,
                "starter_pct": s_st_pct,
                "minutes": s_min,
                "avg_minutes": s_avg_min,
                "max_6w_min": s_max_6w,
                "wins": s_w,
                "losses": s_l,
                "draws": s_d,
                "win_pct": s_wpct,
                "is_single": False,
                "is_subtotal": True,
            })

    seasons_df = pd.DataFrame(seasons_rows)
    seasons_summary_df = pd.DataFrame(seasons_summary_rows)

    peak_6w_career = max([r["max_6w_min"] for r in seasons_summary_rows if r.get("max_6w_min")], default=0)
    career_totals["peak_6w_min"] = peak_6w_career

    # 4. Breakdown by Team / Club (Career)
    teams_rows = []
    for t_name, t_grp in sub_ov.groupby("teamName"):
        t_clean = str(t_name).strip()
        if not t_clean or t_clean.lower() == "none":
            continue
        t_caps = len(t_grp)
        t_min = int(round(t_grp["min_num"].sum()))
        t_starts = int(t_grp["is_starter"].sum())
        t_st_pct = round((t_starts / t_caps) * 100, 1) if t_caps > 0 else 0.0
        t_w = int(t_grp["is_win"].sum())
        t_l = int(t_grp["is_loss"].sum())
        t_d = int(t_grp["is_draw"].sum())
        t_wpct = round((t_w / t_caps) * 100, 1) if t_caps > 0 else 0.0
        first_d = t_grp["dt"].min()
        last_d = t_grp["dt"].max()
        span_s = f"{first_d.year} – {last_d.year}" if pd.notnull(first_d) and pd.notnull(last_d) else "-"

        teams_rows.append({
            "team_name": t_clean,
            "period": span_s,
            "caps": t_caps,
            "starts": t_starts,
            "minutes": t_min,
            "starter_pct": t_st_pct,
            "wins": t_w,
            "losses": t_l,
            "draws": t_d,
            "win_pct": t_wpct,
        })
    teams_df = pd.DataFrame(teams_rows).sort_values("minutes", ascending=False).reset_index(drop=True) if teams_rows else pd.DataFrame()

    # 5. Formatted Matches DataFrame
    matches_list = []
    for _, mrow in sub_ov.iterrows():
        dt_v = mrow["dt"]
        d_disp = dt_v.strftime("%d/%m/%Y") if pd.notnull(dt_v) else str(mrow.get("match_date") or "")
        d_raw = mrow.get("match_date") or ""
        g_name = str(mrow.get("game") or "").strip()
        t_name = str(mrow.get("teamName") or "").strip()
        opp = str(mrow.get("opponent") or "").strip()
        ha = "Home" if str(mrow.get("home")).lower() == "true" else ("Away" if str(mrow.get("away")).lower() == "true" else "-")
        m_val = int(round(mrow["min_num"]))
        is_st = bool(mrow["is_starter"])
        jer = int(mrow["jersey_num"]) if mrow["jersey_num"] > 0 else 0
        res = str(mrow.get("result") or "").strip()
        w_lbl = "WIN" if mrow["is_win"] else ("LOSS" if mrow["is_loss"] else ("DRAW" if mrow["is_draw"] else "-"))

        matches_list.append({
            "match_date": d_raw,
            "date_disp": d_disp,
            "season": mrow["season"],
            "game": g_name,
            "team": t_name,
            "opponent": opp,
            "ha": ha,
            "minutes": m_val,
            "is_starter": is_st,
            "impiego": "TITOLARE" if is_st else "FINISHER",
            "jersey": jer,
            "result": res,
            "outcome": w_lbl,
            "carries": int(round(mrow["carries_num"])),
            "pcm": round(float(mrow["pcm_num"]), 1),
            "tackles": int(round(mrow["tackles_num"])),
            "turnovers_won": int(round(mrow["turnovers_won_num"])),
            "penalties": int(round(mrow["penalties_num"])),
        })
    matches_df = pd.DataFrame(matches_list)

    available_seasons = ["Tutte le Stagioni"] + all_seasons_sorted

    return {
        "player_name": p_canon,
        "role": role,
        "department": dept,
        "club": club,
        "birth_year": b_year,
        "age_str": age_str,
        "opta_id": opta_id,
        "is_gin": is_gin,
        "photo_b64": photo_b64,
        "has_oval_data": True,
        "career_totals": career_totals,
        "curr_season_totals": curr_season_totals,
        "seasons_df": seasons_df,
        "seasons_summary_df": seasons_summary_df,
        "teams_df": teams_df,
        "matches_df": matches_df,
        "available_seasons": available_seasons,
    }


def build_athlete_21d_workload(
    player_name: str,
    ref_mon,
    all_gps: pd.DataFrame = None,
    ov_df: pd.DataFrame = None,
    roster_map: dict = None,
) -> dict:
    """
    Calcola l'analisi completa dei carichi longitudinali su 21 giorni (Week -2, Week -1, Week 0)
    per un singolo atleta, unificando le sedute GPS (FIR + Club) e le presenze/minuti Oval Match.
    """
    if all_gps is None:
        all_gps = get_gps_history_df("all")
    if ov_df is None:
        ov_df = get_oval_matches_df()
    if roster_map is None:
        p_df = get_players_df()
        roster_map = {}
        if not p_df.empty:
            for _, pr in p_df.iterrows():
                nm = str(pr.get("name_display") or "").strip()
                if nm:
                    roster_map[nm.upper()] = pr.to_dict()

    try:
        ref_mon_dt = pd.to_datetime(ref_mon)
    except Exception:
        ref_mon_dt = pd.Timestamp.now()
    ref_mon_dt = ref_mon_dt - pd.Timedelta(days=ref_mon_dt.weekday())

    w0_mon = ref_mon_dt
    w0_sun = ref_mon_dt + pd.Timedelta(days=6)
    w1_mon = ref_mon_dt - pd.Timedelta(days=7)
    w1_sun = ref_mon_dt - pd.Timedelta(days=1)
    w2_mon = ref_mon_dt - pd.Timedelta(days=14)
    w2_sun = ref_mon_dt - pd.Timedelta(days=8)

    w2_mon_str = w2_mon.strftime("%Y-%m-%d")
    w0_sun_str = w0_sun.strftime("%Y-%m-%d")

    p_meta = roster_map.get(str(player_name).strip().upper(), {})
    p_role = str(p_meta.get("role") or "Avanti")
    p_dept = str(p_meta.get("department") or ROLE_TO_DEPT.get(p_role, "Avanti"))
    p_club = str(p_meta.get("club") or "FIR")
    p_vmax_ref = float(p_meta.get("v_max") or 30.0)
    if p_vmax_ref <= 0:
        p_vmax_ref = 30.0

    p_all_hist = all_gps[
        (all_gps["player_name"].astype(str).str.strip().str.upper() == str(player_name).strip().upper())
        & (all_gps["date_str"] <= w0_sun_str)
    ].copy() if not all_gps.empty else pd.DataFrame()

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

    p_gps = p_all_hist[p_all_hist["date_str"] >= w2_mon_str].copy() if not p_all_hist.empty else pd.DataFrame()

    p_ov_all = pd.DataFrame()
    p_ov = pd.DataFrame()
    if not ov_df.empty:
        p_ov_all = ov_df[
            (ov_df["fir_player_name"].astype(str).str.strip().str.upper() == str(player_name).strip().upper())
            | (ov_df["playerFullName"].astype(str).str.strip().str.upper() == str(player_name).strip().upper())
        ].copy()
        if not p_ov_all.empty and "match_date" in p_ov_all.columns:
            p_ov = p_ov_all[(p_ov_all["match_date"].astype(str) >= w2_mon_str) & (p_ov_all["match_date"].astype(str) <= w0_sun_str)]

    giorni_ita = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
    mesi_ita = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

    daily_rows = []
    current_day = w2_mon
    while current_day <= w0_sun:
        day_str = current_day.strftime("%Y-%m-%d")
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
        sub_day = p_gps[p_gps["date_str"] == day_str] if not p_gps.empty else pd.DataFrame()
        has_gps = not sub_day.empty and float(sub_day["distance_m"].sum()) > 0

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
            if any(k in sess_disp.lower() for k in ["partita", "match", "vs", "italia", "gara"]):
                has_match = True
        else:
            dt = dur = dc = hml = vhml = hsr = vmax = 0.0
            team_disp = "-"
            sess_disp = "Riposo / Off"

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

    return {
        "player_name": player_name,
        "p_meta": p_meta,
        "role": p_role,
        "department": p_dept,
        "club": p_club,
        "v_max_ref": p_vmax_ref,
        "df_21": df_21,
        "week_stats": week_stats,
        "days85": days85,
        "days90": days90,
        "last85": last85,
        "last90": last90,
        "w0_mon": w0_mon,
        "w0_sun": w0_sun,
        "w2_mon": w2_mon,
        "w0_sun_str": w0_sun_str,
        "w2_mon_str": w2_mon_str,
    }


def build_athlete_21d_chart(df_21: pd.DataFrame, player_name: str):
    """Costruisce il grafico Plotly giorno per giorno su 21 giorni per il report atleta."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return None

    if df_21 is None or df_21.empty:
        return None

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    bar_colors = []
    for _, r in df_21.iterrows():
        if r["is_match"]:
            bar_colors.append("#EF4444")
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
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=df_21["day_label"],
            y=df_21["Hml"],
            name="Hml >25.5W",
            line=dict(color="#F59E0B", width=2.5),
            marker=dict(size=6, color="#D97706"),
            mode="lines+markers",
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(
            text=f"<b>Progressione Carichi Giornalieri (21 Giorni) • {player_name}</b>",
            font=dict(size=12, color="#0F172A"),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=30, r=30, t=35, b=40),
        height=220,
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
    )
    fig.update_xaxes(tickangle=-45, gridcolor="#E2E8F0")
    fig.update_yaxes(title_text="Distanza (m)", gridcolor="#E2E8F0", secondary_y=False)
    fig.update_yaxes(title_text="Hml (m)", gridcolor="rgba(0,0,0,0)", secondary_y=True)
    return fig


# ==============================================================================
# SEZIONE GYMAWARE (VBT) — VELOCITY BASED TRAINING & ANALISI PALESTRA
# ==============================================================================
import sqlite3

GYMAWARE_DB_PATH = os.path.join(DATA_DIR, "rugby_database.sqlite")
GYMAWARE_SEED_CSV = os.path.join(DATA_DIR, "261109 - Rep Statistics Table.csv")


def get_gymaware_conn():
    return sqlite3.connect(GYMAWARE_DB_PATH)


def init_gymaware_db():
    """Inizializza la tabella gymaware_data nel database SQLite e popola con i dati di seed se vuota."""
    conn = get_gymaware_conn()
    cur = conn.cursor()
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS gymaware_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        athlete_name TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        date TEXT,
        time TEXT,
        exercise TEXT NOT NULL,
        set_id TEXT,
        body_weight REAL,
        body_weight_pct REAL,
        bar_weight REAL,
        total_weight REAL,
        row_type TEXT NOT NULL,
        rep_number INTEGER,
        mean_power REAL,
        mean_velocity REAL,
        peak_velocity REAL,
        mean_power_wkg REAL,
        height REAL,
        dip REAL,
        notes TEXT,
        sensor TEXT,
        hardware TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )
    conn.commit()

    # Se la tabella è vuota, carica il file seed se disponibile
    count = cur.execute("SELECT COUNT(*) FROM gymaware_data").fetchone()[0]
    if count == 0 and os.path.exists(GYMAWARE_SEED_CSV):
        try:
            df_seed = pd.read_csv(GYMAWARE_SEED_CSV)
            save_gymaware_from_df(df_seed, conn=conn, replace_all=True)
        except Exception as e:
            print(f"Errore auto-seed GymAware: {e}")
    conn.close()


def save_gymaware_from_df(df: pd.DataFrame, conn=None, replace_all=False) -> int:
    """Normalizza e inserisce un DataFrame GymAware nel database SQLite."""
    close_conn = False
    if conn is None:
        conn = get_gymaware_conn()
        close_conn = True

    cur = conn.cursor()
    if replace_all:
        cur.execute("DELETE FROM gymaware_data")
        conn.commit()

    # Normalizza i nomi delle colonne rimuovendo spazi
    col_map = {c: c.strip().lower() for c in df.columns}
    df_norm = df.rename(columns=col_map)

    def get_col(df_src, aliases):
        for a in aliases:
            if a.lower() in df_src.columns:
                return df_src[a.lower()]
        return pd.Series([None] * len(df_src))

    first_name_s = get_col(df_norm, ["first name", "firstname", "first_name"])
    last_name_s = get_col(df_norm, ["last name", "lastname", "last_name"])
    athlete_s = get_col(df_norm, ["athlete", "athlete_name", "player"])

    # Calcola athlete_name
    athlete_names = []
    for fn, ln, ath in zip(first_name_s, last_name_s, athlete_s):
        if pd.notna(fn) or pd.notna(ln):
            name = f"{str(fn or '').strip()} {str(ln or '').strip()}".strip()
        elif pd.notna(ath):
            name = str(ath).strip()
        else:
            name = "Sconosciuto"
        athlete_names.append(name)

    def to_clean_float(series):
        return pd.to_numeric(series.astype(str).str.replace(",", "."), errors="coerce")

    def to_clean_int(series):
        s = to_clean_float(series)
        return s.apply(lambda x: int(x) if pd.notna(x) else None)

    date_s = get_col(df_norm, ["date", "data"]).astype(str).str.strip().replace("nan", "")
    time_s = get_col(df_norm, ["time", "ora"]).astype(str).str.strip().replace("nan", "")
    exercise_s = get_col(df_norm, ["exercise", "esercizio", "exercise name"]).astype(str).str.strip()
    set_id_s = get_col(df_norm, ["set id", "set_id", "set"]).astype(str).str.strip()
    row_type_s = get_col(df_norm, ["row type", "row_type"]).astype(str).str.strip()

    bw_s = to_clean_float(get_col(df_norm, ["body weight (kg)", "body weight", "body_weight"]))
    bwp_s = to_clean_float(get_col(df_norm, ["body weight %", "body_weight_pct"]))
    bar_s = to_clean_float(get_col(df_norm, ["bar weight (kg)", "bar weight", "bar_weight"]))
    tot_w_s = to_clean_float(get_col(df_norm, ["total weight (kg)", "total weight", "total_weight"]))
    rep_num_s = to_clean_int(get_col(df_norm, ["rep number", "rep_number", "rep"]))

    m_pwr_s = to_clean_float(get_col(df_norm, ["mean power (w)", "mean power", "mean_power"]))
    m_vel_s = to_clean_float(get_col(df_norm, ["mean velocity (m/s)", "mean velocity", "mean_velocity"]))
    p_vel_s = to_clean_float(get_col(df_norm, ["peak velocity (m/s)", "peak velocity", "peak_velocity"]))
    pwr_kg_s = to_clean_float(get_col(df_norm, ["mean power (w/kg)", "mean_power_wkg"]))
    height_s = to_clean_float(get_col(df_norm, ["height (m)", "height"]))
    dip_s = to_clean_float(get_col(df_norm, ["dip (m)", "dip"]))

    notes_s = get_col(df_norm, ["notes", "note"]).astype(str).str.strip().replace("nan", "")
    sensor_s = get_col(df_norm, ["sensor"]).astype(str).str.strip().replace("nan", "")
    hw_s = get_col(df_norm, ["hardware"]).astype(str).str.strip().replace("nan", "")

    rows_to_insert = []
    for i in range(len(df_norm)):
        rows_to_insert.append((
            athlete_names[i],
            str(first_name_s.iloc[i] or "").strip(),
            str(last_name_s.iloc[i] or "").strip(),
            date_s.iloc[i],
            time_s.iloc[i],
            exercise_s.iloc[i],
            set_id_s.iloc[i],
            float(bw_s.iloc[i]) if pd.notna(bw_s.iloc[i]) else None,
            float(bwp_s.iloc[i]) if pd.notna(bwp_s.iloc[i]) else None,
            float(bar_s.iloc[i]) if pd.notna(bar_s.iloc[i]) else None,
            float(tot_w_s.iloc[i]) if pd.notna(tot_w_s.iloc[i]) else None,
            row_type_s.iloc[i],
            int(rep_num_s.iloc[i]) if pd.notna(rep_num_s.iloc[i]) else None,
            float(m_pwr_s.iloc[i]) if pd.notna(m_pwr_s.iloc[i]) else None,
            float(m_vel_s.iloc[i]) if pd.notna(m_vel_s.iloc[i]) else None,
            float(p_vel_s.iloc[i]) if pd.notna(p_vel_s.iloc[i]) else None,
            float(pwr_kg_s.iloc[i]) if pd.notna(pwr_kg_s.iloc[i]) else None,
            float(height_s.iloc[i]) if pd.notna(height_s.iloc[i]) else None,
            float(dip_s.iloc[i]) if pd.notna(dip_s.iloc[i]) else None,
            notes_s.iloc[i],
            sensor_s.iloc[i],
            hw_s.iloc[i],
        ))

    cur.executemany(
        """
    INSERT INTO gymaware_data (
        athlete_name, first_name, last_name, date, time, exercise, set_id,
        body_weight, body_weight_pct, bar_weight, total_weight,
        row_type, rep_number, mean_power, mean_velocity, peak_velocity,
        mean_power_wkg, height, dip, notes, sensor, hardware
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        rows_to_insert,
    )
    conn.commit()
    inserted_count = len(rows_to_insert)

    if close_conn:
        conn.close()
    return inserted_count


def _format_gymaware_date_to_iso(d_val) -> str:
    if not d_val:
        return ""
    if hasattr(d_val, "strftime"):
        return d_val.strftime("%Y-%m-%d")
    s = str(d_val).strip()
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        return f"{s[6:10]}-{s[3:5]}-{s[0:2]}"
    return s


def _normalize_gymaware_date_str(d_val) -> str:
    """Normalizza un valore data in stringa 'DD/MM/YYYY' usata come chiave in SQLite."""
    if not d_val:
        return ""
    if hasattr(d_val, "strftime"):
        return d_val.strftime("%d/%m/%Y")
    s = str(d_val).strip()
    # Se arriva in formato YYYY-MM-DD o YYYY-MM-DD HH:MM:SS
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"
    return s


def get_gymaware_df(
    exercise: str = None,
    athlete: str = None,
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    row_type = None,
) -> pd.DataFrame:
    """Interroga la tabella gymaware_data con filtri opzionali su esercizio, atleta, data o periodo."""
    init_gymaware_db()
    conn = get_gymaware_conn()

    query = "SELECT * FROM gymaware_data WHERE 1=1"
    params = []

    if exercise and exercise != "Tutti":
        query += " AND exercise = ?"
        params.append(exercise)
    if athlete and athlete != "Tutti":
        query += " AND athlete_name = ?"
        params.append(athlete)
    if start_date and end_date:
        s_iso = _format_gymaware_date_to_iso(start_date)
        e_iso = _format_gymaware_date_to_iso(end_date)
        query += " AND (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) BETWEEN ? AND ?"
        params.extend([s_iso, e_iso])
    elif date and date != "Tutte le date":
        norm_d = _normalize_gymaware_date_str(date)
        query += " AND date = ?"
        params.append(norm_d)
    if row_type:
        if isinstance(row_type, (list, tuple)):
            placeholders = ",".join(["?"] * len(row_type))
            query += f" AND row_type IN ({placeholders})"
            params.extend(row_type)
        else:
            query += " AND row_type = ?"
            params.append(row_type)

    query += " ORDER BY (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) DESC, time DESC, set_id ASC, rep_number ASC"
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df


def get_gymaware_summary_stats(
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    exercise: str = None,
) -> dict:
    """Calcola statistiche globali (KPI strip) in linea con GymAware."""
    init_gymaware_db()
    conn = get_gymaware_conn()

    filter_sql = ""
    params = []
    if start_date and end_date:
        s_iso = _format_gymaware_date_to_iso(start_date)
        e_iso = _format_gymaware_date_to_iso(end_date)
        filter_sql += " AND (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) BETWEEN ? AND ?"
        params.extend([s_iso, e_iso])
    elif date and date != "Tutte le date":
        filter_sql += " AND date = ?"
        params.append(date)
    if exercise and exercise != "Tutti":
        filter_sql += " AND exercise = ?"
        params.append(exercise)

    total_sets = conn.execute(
        f"SELECT COUNT(DISTINCT set_id) FROM gymaware_data WHERE 1=1 {filter_sql}",
        params,
    ).fetchone()[0]
    total_reps = conn.execute(
        f"SELECT COUNT(*) FROM gymaware_data WHERE row_type = 'Rep' {filter_sql}",
        params,
    ).fetchone()[0]
    total_athletes = conn.execute(
        f"SELECT COUNT(DISTINCT athlete_name) FROM gymaware_data WHERE 1=1 {filter_sql}",
        params,
    ).fetchone()[0]

    mean_vel = conn.execute(
        f"SELECT AVG(mean_velocity) FROM gymaware_data WHERE row_type = 'Average' {filter_sql}",
        params,
    ).fetchone()[0]
    peak_vel = conn.execute(
        f"SELECT MAX(peak_velocity) FROM gymaware_data WHERE row_type IN ('Rep','Maximum') {filter_sql}",
        params,
    ).fetchone()[0]
    mean_pwr = conn.execute(
        f"SELECT AVG(mean_power) FROM gymaware_data WHERE row_type = 'Average' {filter_sql}",
        params,
    ).fetchone()[0]
    max_pwr = conn.execute(
        f"SELECT MAX(mean_power) FROM gymaware_data WHERE row_type IN ('Rep','Maximum') {filter_sql}",
        params,
    ).fetchone()[0]

    tonnage = conn.execute(
        f"SELECT SUM(COALESCE(bar_weight, total_weight, 0)) FROM gymaware_data WHERE row_type = 'Rep' {filter_sql}",
        params,
    ).fetchone()[0]

    conn.close()
    return {
        "total_sets": total_sets or 0,
        "total_reps": total_reps or 0,
        "total_athletes": total_athletes or 0,
        "mean_velocity": round(mean_vel, 2) if mean_vel else 0.0,
        "peak_velocity": round(peak_vel, 2) if peak_vel else 0.0,
        "mean_power": round(mean_pwr, 1) if mean_pwr else 0.0,
        "max_power": round(max_pwr, 1) if max_pwr else 0.0,
        "tonnage_kg": round(tonnage, 1) if tonnage else 0.0,
    }


def get_gymaware_ranking(
    exercise: str = "Trap Bar Jump",
    metric_col: str = "mean_velocity",
    criterion: str = "max",
    date: str = None,
    start_date: str = None,
    end_date: str = None,
    department: str = None,
) -> pd.DataFrame:
    """
    Calcola la classifica degli atleti secondo l'esercizio e la metrica richiesta.
    criterion: 'max' (Miglior Ripetizione / Peak) oppure 'avg' (Media Serie)
    """
    init_gymaware_db()
    conn = get_gymaware_conn()

    valid_metrics = {
        "mean_velocity": "mean_velocity",
        "peak_velocity": "peak_velocity",
        "mean_power": "mean_power",
        "mean_power_wkg": "mean_power_wkg",
        "bar_weight": "bar_weight",
        "total_weight": "bar_weight",
        "height": "height",
    }
    m_col = valid_metrics.get(metric_col, "mean_velocity")

    where_clause = "WHERE exercise = ?"
    params = [exercise]

    if start_date and end_date:
        s_iso = _format_gymaware_date_to_iso(start_date)
        e_iso = _format_gymaware_date_to_iso(end_date)
        where_clause += " AND (substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) BETWEEN ? AND ?"
        params.extend([s_iso, e_iso])
    elif date and date != "Tutte le date":
        where_clause += " AND date = ?"
        params.append(date)

    if criterion == "max":
        where_clause += f" AND row_type IN ('Maximum', 'Rep') AND {m_col} IS NOT NULL AND {m_col} > 0"
        sql = f"""
        SELECT athlete_name,
               MAX({m_col}) as metric_value,
               MAX(COALESCE(bar_weight, total_weight, 0)) as load_kg,
               date as best_date,
               COUNT(DISTINCT set_id) as total_sets
        FROM gymaware_data
        {where_clause}
        GROUP BY athlete_name
        ORDER BY metric_value DESC
        """
    else:
        where_clause += f" AND row_type = 'Average' AND {m_col} IS NOT NULL AND {m_col} > 0"
        sql = f"""
        SELECT athlete_name,
               AVG({m_col}) as metric_value,
               MAX(COALESCE(bar_weight, total_weight, 0)) as load_kg,
               date as best_date,
               COUNT(DISTINCT set_id) as total_sets
        FROM gymaware_data
        {where_clause}
        GROUP BY athlete_name
        ORDER BY metric_value DESC
        """

    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()

    if not df.empty:
        p_df = get_players_df()
        role_map = {}
        dept_map = {}
        club_map = {}
        for _, pr in p_df.iterrows():
            dname = str(pr.get("name_display", "")).strip().lower()
            role_map[dname] = pr.get("role", "N/D")
            dept_map[dname] = pr.get("department", "N/D")
            club_map[dname] = pr.get("club", "FIR")

        roles = []
        depts = []
        clubs = []
        for ath in df["athlete_name"]:
            ath_clean = str(ath).strip().lower()
            # fallback normalizzazione se match non esatto
            matched_r = role_map.get(ath_clean)
            if not matched_r:
                # cerca per cognome
                parts = ath_clean.split()
                last_p = parts[-1] if parts else ""
                for k, v in role_map.items():
                    if last_p and last_p in k:
                        matched_r = v
                        break
            final_role = matched_r or "N/D"
            d_val = dept_map.get(ath_clean)
            if not d_val or d_val == "N/D":
                d_val = ROLE_TO_DEPT.get(final_role, "N/D")
            roles.append(final_role)
            depts.append(d_val)
            clubs.append(club_map.get(ath_clean, "FIR"))

        df["role"] = roles
        df["department"] = depts
        df["club"] = clubs

        if department and department != "Tutti":
            df = df[df["department"] == department]

        df = df.reset_index(drop=True)
        df["rank"] = range(1, len(df) + 1)

    return df


def get_gymaware_exercises() -> list:
    init_gymaware_db()
    conn = get_gymaware_conn()
    rows = conn.execute(
        "SELECT DISTINCT exercise FROM gymaware_data WHERE exercise IS NOT NULL AND exercise != '' ORDER BY exercise ASC"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_gymaware_athletes() -> list:
    init_gymaware_db()
    conn = get_gymaware_conn()
    rows = conn.execute(
        "SELECT DISTINCT athlete_name FROM gymaware_data WHERE athlete_name IS NOT NULL AND athlete_name != '' ORDER BY athlete_name ASC"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_gymaware_dates() -> list:
    """Ritorna tutte le date uniche ordinate cronologicamente dalla più recente."""
    init_gymaware_db()
    conn = get_gymaware_conn()
    rows = conn.execute("""
        SELECT DISTINCT date,
               substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2) as iso_d
        FROM gymaware_data 
        WHERE date IS NOT NULL AND date != '' 
        ORDER BY iso_d DESC
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_gymaware_athletes_for_date(date_str) -> list:
    """Ritorna gli atleti con misurazioni registrate in una specifica data."""
    init_gymaware_db()
    conn = get_gymaware_conn()
    norm_d = _normalize_gymaware_date_str(date_str)
    rows = conn.execute(
        "SELECT DISTINCT athlete_name FROM gymaware_data WHERE date = ? ORDER BY athlete_name ASC",
        (norm_d,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def delete_gymaware_date(date_str) -> int:
    """Elimina tutte le righe di tutti gli atleti per una specifica data."""
    init_gymaware_db()
    conn = get_gymaware_conn()
    norm_d = _normalize_gymaware_date_str(date_str)
    cur = conn.cursor()
    cur.execute("DELETE FROM gymaware_data WHERE date = ?", (norm_d,))
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def delete_gymaware_athlete_date(athlete_name: str, date_str) -> int:
    """Elimina tutte le righe di un singolo atleta in una specifica data."""
    init_gymaware_db()
    conn = get_gymaware_conn()
    norm_d = _normalize_gymaware_date_str(date_str)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM gymaware_data WHERE athlete_name = ? AND date = ?",
        (athlete_name, norm_d),
    )
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count


def get_gymaware_database_overview() -> dict:
    """
    Ritorna le metriche globali del database GymAware:
    totale record, totale sessioni/date, atleti unici, totale serie, totale ripetizioni,
    ultimo batch di importazione (data/ora, numero righe, atleti).
    """
    init_gymaware_db()
    conn = get_gymaware_conn()
    cur = conn.cursor()

    overall = cur.execute("""
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT date) as total_sessions,
            COUNT(DISTINCT athlete_name) as total_athletes,
            COUNT(DISTINCT set_id) as total_sets,
            SUM(CASE WHEN row_type = 'Rep' THEN 1 ELSE 0 END) as total_reps,
            MAX(created_at) as last_upload_ts
        FROM gymaware_data
    """).fetchone()

    last_upload_ts = overall[5] if overall else None
    last_batch_rows = 0
    last_batch_athletes = 0
    if last_upload_ts:
        batch_stat = cur.execute("""
            SELECT COUNT(*), COUNT(DISTINCT athlete_name)
            FROM gymaware_data
            WHERE created_at = ?
        """, (last_upload_ts,)).fetchone()
        if batch_stat:
            last_batch_rows = batch_stat[0]
            last_batch_athletes = batch_stat[1]

    conn.close()

    return {
        "total_rows": overall[0] if overall else 0,
        "total_sessions": overall[1] if overall else 0,
        "total_athletes": overall[2] if overall else 0,
        "total_sets": overall[3] if overall else 0,
        "total_reps": overall[4] if overall and overall[4] else 0,
        "last_upload_ts": last_upload_ts,
        "last_batch_rows": last_batch_rows,
        "last_batch_athletes": last_batch_athletes,
    }


def get_gymaware_recent_sessions_summary(limit: int = 4) -> list:
    """
    Ritorna le ultime sessioni di allenamento GymAware presenti nel database,
    ordinate cronologicamente dalla più recente alla meno recente.
    """
    init_gymaware_db()
    conn = get_gymaware_conn()
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT 
            date,
            substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2) as iso_d,
            COUNT(DISTINCT athlete_name) as n_ath,
            COUNT(DISTINCT set_id) as n_sets,
            SUM(CASE WHEN row_type = 'Rep' THEN 1 ELSE 0 END) as n_reps,
            COUNT(*) as total_rows,
            MAX(total_weight) as max_kg,
            MAX(peak_velocity) as max_vel,
            AVG(CASE WHEN row_type = 'Rep' AND mean_velocity > 0 THEN mean_velocity END) as avg_mean_vel,
            GROUP_CONCAT(DISTINCT exercise) as exercises,
            MAX(created_at) as last_uploaded_at
        FROM gymaware_data
        WHERE date IS NOT NULL AND date != ''
        GROUP BY date
        ORDER BY iso_d DESC
        LIMIT {limit}
    """).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "date": r[0],
            "iso_date": r[1],
            "n_athletes": r[2],
            "n_sets": r[3],
            "n_reps": r[4] or 0,
            "total_rows": r[5],
            "max_kg": r[6] or 0.0,
            "max_vel": r[7] or 0.0,
            "avg_mean_vel": r[8] or 0.0,
            "exercises": r[9] or "",
            "last_uploaded_at": r[10] or "",
        })
    return results


def get_gymaware_batches_summary(limit: int = 10) -> list:
    """
    Ritorna lo storico dei batch di importazione CSV registrati nel database.
    """
    init_gymaware_db()
    conn = get_gymaware_conn()
    cur = conn.cursor()

    rows = cur.execute(f"""
        SELECT 
            created_at,
            COUNT(*) as n_rows,
            COUNT(DISTINCT date) as n_dates,
            COUNT(DISTINCT athlete_name) as n_ath,
            COUNT(DISTINCT set_id) as n_sets,
            SUM(CASE WHEN row_type = 'Rep' THEN 1 ELSE 0 END) as n_reps,
            MIN(substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) as min_iso,
            MAX(substr(date, 7, 4) || '-' || substr(date, 4, 2) || '-' || substr(date, 1, 2)) as max_iso
        FROM gymaware_data
        GROUP BY created_at
        ORDER BY created_at DESC
        LIMIT {limit}
    """).fetchall()
    conn.close()

    batches = []
    for r in rows:
        min_d = f"{r[6][8:10]}/{r[6][5:7]}/{r[6][0:4]}" if r[6] and len(r[6]) == 10 else r[6]
        max_d = f"{r[7][8:10]}/{r[7][5:7]}/{r[7][0:4]}" if r[7] and len(r[7]) == 10 else r[7]
        batches.append({
            "created_at": r[0],
            "n_rows": r[1],
            "n_dates": r[2],
            "n_athletes": r[3],
            "n_sets": r[4],
            "n_reps": r[5] or 0,
            "date_range": f"{min_d} - {max_d}" if min_d != max_d else min_d,
        })
    return batches


def update_gymaware_rows(df_edited: pd.DataFrame) -> int:
    """Aggiorna le righe di gymaware_data a partire da un DataFrame modificato."""
    init_gymaware_db()
    conn = get_gymaware_conn()
    cur = conn.cursor()
    updated_count = 0

    updatable_cols = [
        "exercise",
        "bar_weight",
        "total_weight",
        "mean_velocity",
        "peak_velocity",
        "mean_power",
        "mean_power_wkg",
        "height",
        "dip",
        "notes",
    ]

    for _, row in df_edited.iterrows():
        row_id = row.get("id")
        if pd.isna(row_id):
            continue
        set_clauses = []
        vals = []
        for col in updatable_cols:
            if col in row:
                val = row[col]
                val = None if pd.isna(val) else val
                set_clauses.append(f"{col} = ?")
                vals.append(val)

        if set_clauses:
            vals.append(int(row_id))
            cur.execute(
                f"UPDATE gymaware_data SET {', '.join(set_clauses)} WHERE id = ?",
                vals,
            )
            updated_count += cur.rowcount

    conn.commit()
    conn.close()
    return updated_count


def delete_gymaware_all() -> int:
    init_gymaware_db()
    conn = get_gymaware_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM gymaware_data")
    conn.commit()
    count = cur.rowcount
    conn.close()
    return count






