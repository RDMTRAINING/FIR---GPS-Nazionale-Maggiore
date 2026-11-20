# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
# Modulo Monitoraggio Peso Corporeo - FIR GPS Analytics Platform
from __future__ import annotations

import datetime
import re
import unicodedata
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from reportlab.graphics.shapes import Circle, Drawing, Polygon, PolyLine
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import utils
from config import LOGO_PATH, render_action_bar, render_page_header, render_tab_navigation
from pdf_generator import _build_fir_header_table, _build_pdf_with_footer, slugify_name


WEIGHT_TABLE_NAME = "player_weights"
WEIGHT_COLUMNS = ["player_name", "csv_name", "date_str", "weight_kg", "updated_at"]


def _norm_name_key(s: str) -> str:
    txt = "".join(
        c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn"
    )
    for ch in ("'", "’", "`", "´"):
        txt = txt.replace(ch, "")
    return re.sub(r"\s+", " ", txt).strip().upper()


def _build_roster_name_resolver(players_df: pd.DataFrame) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    if players_df is None or players_df.empty:
        return lookup
    for _, r in players_df.iterrows():
        nd = str(r.get("name_display") or "").strip()
        if not nd:
            continue
        ns = str(r.get("name_sheet") or "").strip()
        ln = str(r.get("last_name") or "").strip()
        fn = str(r.get("first_name") or "").strip()
        for cand in (nd, ns, f"{ln} {fn}", f"{fn} {ln}"):
            k = _norm_name_key(cand)
            if k:
                lookup[k] = nd
    return lookup


def resolve_csv_athlete_name(raw_name: str, roster_lookup: Dict[str, str]) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""
    k = _norm_name_key(raw)
    if k in roster_lookup:
        return roster_lookup[k]

    parts = k.split()
    if len(parts) >= 2:
        for rk, rv in roster_lookup.items():
            r_parts = rk.split()
            if parts[0] in r_parts and parts[1][:4] in rk:
                return rv
        # Fallback: convert "Cognome Nome" -> "Nome Cognome"
        clean_raw = re.sub(r"['’`´]+$", "", raw).strip()
        raw_parts = clean_raw.split()
        if len(raw_parts) >= 2:
            return f"{' '.join(raw_parts[1:])} {raw_parts[0]}".strip()
    return raw


def _parse_date_col_header(col_name: str) -> Optional[str]:
    s = str(col_name or "").strip()
    m = re.match(r"^(\d{2})-(\d{2})-(\d{2})$", s)
    if m:
        dd, mm, yy = m.groups()
        year = f"20{yy}"
        try:
            dt = datetime.date(int(year), int(mm), int(dd))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    m2 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m2:
        return s
    m3 = re.match(r"^(\d{2})/(\d{2})/(\d{2,4})$", s)
    if m3:
        dd, mm, yy = m3.groups()
        year = f"20{yy}" if len(yy) == 2 else yy
        try:
            dt = datetime.date(int(year), int(mm), int(dd))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _parse_weight_value(val: Any) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip().lower()
    if not s or s in ("-", "nan", "none", "null"):
        return None
    s = s.replace("kg", "").replace(",", ".").strip()
    try:
        num = float(s)
        if 30.0 <= num <= 250.0:
            return round(num, 2)
    except ValueError:
        return None
    return None


def parse_weights_csv(file_source: Any, players_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Legge un CSV impaginato come export (3).csv ed estrae esclusivamente (atleta, data, peso_kg)."""
    raw_df = pd.read_csv(file_source)
    if raw_df.empty or "Atleta" not in raw_df.columns:
        return pd.DataFrame(columns=WEIGHT_COLUMNS)

    if players_df is None:
        players_df = utils.get_players_df()
    roster_lookup = _build_roster_name_resolver(players_df)

    date_cols: List[Tuple[str, str]] = []
    for c in raw_df.columns:
        iso_d = _parse_date_col_header(c)
        if iso_d:
            date_cols.append((c, iso_d))

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    records: List[Dict[str, Any]] = []
    for _, row in raw_df.iterrows():
        csv_name = str(row.get("Atleta") or "").strip()
        if not csv_name:
            continue
        canon_name = resolve_csv_athlete_name(csv_name, roster_lookup)
        for orig_col, iso_date in date_cols:
            w = _parse_weight_value(row.get(orig_col))
            if w is not None:
                records.append(
                    {
                        "player_name": canon_name,
                        "csv_name": csv_name,
                        "date_str": iso_date,
                        "weight_kg": float(w),
                        "updated_at": now_str,
                    }
                )
    if not records:
        return pd.DataFrame(columns=WEIGHT_COLUMNS)
    out = pd.DataFrame(records)
    out = out.drop_duplicates(subset=["player_name", "date_str"], keep="last")
    return out.sort_values(["player_name", "date_str"]).reset_index(drop=True)


def load_player_weights_df() -> pd.DataFrame:
    df = utils.load_table(WEIGHT_TABLE_NAME)
    if df is None or df.empty:
        return pd.DataFrame(columns=WEIGHT_COLUMNS)
    out = df.copy()
    for c in WEIGHT_COLUMNS:
        if c not in out.columns:
            out[c] = "" if c != "weight_kg" else np.nan
    out["player_name"] = out["player_name"].astype(str).str.strip()
    out["date_str"] = out["date_str"].astype(str).str[:10]
    out["weight_kg"] = pd.to_numeric(out["weight_kg"], errors="coerce")
    out = out[out["player_name"].ne("") & out["date_str"].ne("") & out["weight_kg"].notna() & (out["weight_kg"] > 0)].copy()
    return out.sort_values(["player_name", "date_str"]).reset_index(drop=True)


def save_player_weights_df(df: pd.DataFrame) -> None:
    clean = df.copy()
    for c in WEIGHT_COLUMNS:
        if c not in clean.columns:
            clean[c] = "" if c != "weight_kg" else np.nan
    clean = clean[WEIGHT_COLUMNS].copy()
    clean["player_name"] = clean["player_name"].astype(str).str.strip()
    clean["date_str"] = clean["date_str"].astype(str).str[:10]
    clean["weight_kg"] = pd.to_numeric(clean["weight_kg"], errors="coerce")
    clean = clean[clean["player_name"].ne("") & clean["date_str"].ne("") & clean["weight_kg"].notna() & (clean["weight_kg"] > 0)].copy()
    clean = clean.drop_duplicates(subset=["player_name", "date_str"], keep="last")
    clean = clean.sort_values(["player_name", "date_str"]).reset_index(drop=True)
    utils.save_table(WEIGHT_TABLE_NAME, clean)


def upsert_player_weights(new_rows_df: pd.DataFrame) -> int:
    if new_rows_df is None or new_rows_df.empty:
        return 0
    existing = load_player_weights_df()
    combined = pd.concat([existing, new_rows_df[WEIGHT_COLUMNS]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["player_name", "date_str"], keep="last")
    save_player_weights_df(combined)
    return len(new_rows_df)


def _compute_player_period_series(
    df_weights: pd.DataFrame,
    selected_players: List[str],
    start_date_str: str,
    end_date_str: str,
) -> Tuple[List[str], Dict[str, List[Dict[str, Any]]]]:
    """
    Restituisce (date_ordinate_nel_periodo, mappa {player_name: [{date_str, weight_kg, pct_prev, is_ref}]}).
    Il primo peso registrato nel periodo selezionato funge da primo riferimento (pct_prev=None).
    """
    if df_weights.empty or not selected_players:
        return [], {}

    sub = df_weights[
        df_weights["player_name"].isin(selected_players)
        & (df_weights["date_str"] >= start_date_str)
        & (df_weights["date_str"] <= end_date_str)
    ].copy()
    if sub.empty:
        return [], {}

    sub = sub.sort_values(["player_name", "date_str"]).reset_index(drop=True)
    dates_in_period = sorted(sub["date_str"].unique().tolist())

    player_series: Dict[str, List[Dict[str, Any]]] = {}
    for pname in selected_players:
        p_rows = sub[sub["player_name"] == pname].sort_values("date_str")
        if p_rows.empty:
            continue
        entries: List[Dict[str, Any]] = []
        prev_w: Optional[float] = None
        for _, r in p_rows.iterrows():
            w = float(r["weight_kg"])
            if prev_w is None:
                pct = None
                is_ref = True
            else:
                pct = ((w - prev_w) / prev_w) * 100.0 if prev_w > 0 else 0.0
                is_ref = False
            entries.append(
                {
                    "date_str": str(r["date_str"]),
                    "weight_kg": w,
                    "pct_prev": pct,
                    "is_ref": is_ref,
                }
            )
            prev_w = w
        player_series[pname] = entries

    return dates_in_period, player_series


def _build_sparkline_svg(entries: List[Dict[str, Any]], width: int = 96, height: int = 26) -> str:
    if not entries:
        return "<span style='color:#94A3B8; font-size:0.72rem;'>—</span>"
    vals = [e["weight_kg"] for e in entries]
    if len(vals) == 1:
        return (
            f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>"
            f"<circle cx='{width/2:.1f}' cy='{height/2:.1f}' r='3.2' fill='#0066B2'/>"
            f"</svg>"
        )
    v_min, v_max = min(vals), max(vals)
    span = max(v_max - v_min, 0.2)
    pad_x, pad_y = 6.0, 5.0
    usable_w = width - 2 * pad_x
    usable_h = height - 2 * pad_y
    pts = []
    for idx, v in enumerate(vals):
        x = pad_x + (idx / (len(vals) - 1)) * usable_w
        y = pad_y + (1.0 - ((v - v_min) / span)) * usable_h
        pts.append((x, y))

    delta = vals[-1] - vals[0]
    stroke_col = "#059669" if delta > 0.05 else ("#DC2626" if delta < -0.05 else "#0066B2")
    poly_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    circles = "".join(
        f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{2.6 if idx == len(pts)-1 else 1.8}' fill='{stroke_col}'/>"
        for idx, (x, y) in enumerate(pts)
    )
    return (
        f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' xmlns='http://www.w3.org/2000/svg'>"
        f"<polyline fill='none' stroke='{stroke_col}' stroke-width='1.8' points='{poly_str}'/>"
        f"{circles}</svg>"
    )


def _build_rl_sparkline(entries: List[Dict[str, Any]], width: int = 58, height: int = 16) -> Drawing:
    d = Drawing(width, height)
    if not entries:
        return d
    vals = [e["weight_kg"] for e in entries]
    if len(vals) == 1:
        d.add(Circle(width / 2.0, height / 2.0, 2.0, fillColor=colors.HexColor("#0066B2"), strokeColor=None))
        return d
    v_min, v_max = min(vals), max(vals)
    span = max(v_max - v_min, 0.2)
    pad_x, pad_y = 4.0, 3.0
    uw = width - 2 * pad_x
    uh = height - 2 * pad_y
    coords: List[float] = []
    pts: List[Tuple[float, float]] = []
    for idx, v in enumerate(vals):
        x = pad_x + (idx / (len(vals) - 1)) * uw
        y = pad_y + ((v - v_min) / span) * uh
        coords.extend([x, y])
        pts.append((x, y))
    delta = vals[-1] - vals[0]
    col = colors.HexColor("#059669" if delta > 0.05 else ("#DC2626" if delta < -0.05 else "#0066B2"))
    d.add(PolyLine(coords, strokeColor=col, strokeWidth=1.3))
    d.add(Circle(pts[-1][0], pts[-1][1], 1.8, fillColor=col, strokeColor=None))
    return d


def crea_pdf_peso_corporeo(
    dates_in_period: List[str],
    player_series: Dict[str, List[Dict[str, Any]]],
    meta_info: Dict[str, str],
) -> bytes:
    """Esporta in PDF A4 landscape la tabella completa dei pesi registrati identica al portale."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=16,
        rightMargin=16,
        topMargin=14,
        bottomMargin=22,
    )
    styles = getSampleStyleSheet()
    elements: List[Any] = []

    elements.append(
        _build_fir_header_table(
            "Monitoraggio Peso Corporeo",
            f"Target: {meta_info.get('target_label', 'Roster')} • Periodo: {meta_info.get('period_label', '')}",
            f"Ultimo Peso: {meta_info.get('latest_date_disp', '--')}",
            f"Atleti: {len(player_series)} • Date: {len(dates_in_period)}",
            total_width=808,
        )
    )
    elements.append(Spacer(1, 6))

    if not player_series or not dates_in_period:
        elements.append(Paragraph("Nessun peso registrato nel periodo selezionato.", styles["Normal"]))
        _build_pdf_with_footer(doc, elements)
        return buffer.getvalue()

    # Se ci sono molte date nel periodo, suddividi in blocchi orizzontali da max 10 date per pagina per leggibilità perfetta
    max_dates_per_chunk = 10
    date_chunks = [
        dates_in_period[i : i + max_dates_per_chunk]
        for i in range(0, len(dates_in_period), max_dates_per_chunk)
    ]

    p_hdr = ParagraphStyle("pw_hdr", fontName="Helvetica-Bold", fontSize=7.0, textColor=colors.white, alignment=1, leading=8.5)
    p_hdr_l = ParagraphStyle("pw_hdr_l", fontName="Helvetica-Bold", fontSize=7.2, textColor=colors.white, alignment=0, leading=8.5)
    p_name = ParagraphStyle("pw_name", fontName="Helvetica-Bold", fontSize=7.2, textColor=colors.HexColor("#0F172A"), leading=9)
    p_cell = ParagraphStyle("pw_cell", fontName="Helvetica", fontSize=6.8, textColor=colors.HexColor("#0F172A"), alignment=1, leading=8.5)

    for c_idx, chunk_dates in enumerate(date_chunks):
        if c_idx > 0:
            elements.append(Spacer(1, 8))

        headers = [Paragraph("Atleta", p_hdr_l), Paragraph("Trend", p_hdr)]
        for dt_s in chunk_dates:
            try:
                dt_short = pd.to_datetime(dt_s).strftime("%d/%m/%y")
            except Exception:
                dt_short = dt_s
            headers.append(Paragraph(dt_short, p_hdr))

        rows = [headers]
        for pname in sorted(player_series.keys()):
            entries = player_series[pname]
            by_date = {e["date_str"]: e for e in entries}
            row_cells: List[Any] = [
                Paragraph(pname, p_name),
                _build_rl_sparkline(entries, width=56, height=15),
            ]
            for dt_s in chunk_dates:
                e = by_date.get(dt_s)
                if not e:
                    row_cells.append(Paragraph("<font color='#94A3B8'>—</font>", p_cell))
                else:
                    w_txt = f"<b>{e['weight_kg']:.1f} kg</b>"
                    if e["is_ref"] or e["pct_prev"] is None:
                        sub_txt = "<font size='5.8' color='#0369A1'>RIF.</font>"
                    else:
                        pct = float(e["pct_prev"])
                        col_hex = "#059669" if pct > 0.05 else ("#DC2626" if pct < -0.05 else "#475569")
                        sign = "+" if pct > 0 else ""
                        sub_txt = f"<font size='5.8' color='{col_hex}'>{sign}{pct:.1f}%</font>"
                    row_cells.append(Paragraph(f"{w_txt}<br/>{sub_txt}", p_cell))
            rows.append(row_cells)

        name_w = 115
        trend_w = 62
        rem_w = 808 - name_w - trend_w
        date_col_w = rem_w / max(len(chunk_dates), 1)
        col_widths = [name_w, trend_w] + [date_col_w] * len(chunk_dates)

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(tbl)

    _build_pdf_with_footer(doc, elements)
    return buffer.getvalue()


def _compute_two_date_comparison(
    df_weights: pd.DataFrame,
    selected_players: List[str],
    start_date_str: str,
    end_date_str: str,
) -> List[Dict[str, Any]]:
    """
    Per ogni giocatore selezionato, trova il peso registrato con data più vicina a `start_date_str`
    e il peso registrato con data più vicina a `end_date_str`, calcolando delta kg, delta % e direzione.
    """
    if df_weights.empty or not selected_players:
        return []

    target_start = pd.to_datetime(start_date_str)
    target_end = pd.to_datetime(end_date_str)

    sub = df_weights[df_weights["player_name"].isin(selected_players)].copy()
    if sub.empty:
        return []

    sub["_dt"] = pd.to_datetime(sub["date_str"], errors="coerce")
    sub = sub[sub["_dt"].notna()].copy()

    rows: List[Dict[str, Any]] = []
    for pname in sorted(set(selected_players)):
        p_df = sub[sub["player_name"] == pname].sort_values("_dt")
        if p_df.empty:
            continue

        # Più vicino a Data Inizio (a parità di distanza, preferisce la data precedente)
        p_df["_dist_start"] = (p_df["_dt"] - target_start).abs()
        start_row = p_df.sort_values(["_dist_start", "_dt"], ascending=[True, True]).iloc[0]

        # Più vicino a Data Fine (a parità di distanza, preferisce la data successiva)
        p_df["_dist_end"] = (p_df["_dt"] - target_end).abs()
        end_row = p_df.sort_values(["_dist_end", "_dt"], ascending=[True, False]).iloc[0]

        w_start = float(start_row["weight_kg"])
        w_end = float(end_row["weight_kg"])
        diff_kg = round(w_end - w_start, 2)
        diff_pct = ((w_end - w_start) / w_start) * 100.0 if w_start > 0 else 0.0

        if diff_kg > 0.05:
            direction = "up"
        elif diff_kg < -0.05:
            direction = "down"
        else:
            direction = "flat"

        rows.append(
            {
                "player_name": pname,
                "start_date_actual": str(start_row["date_str"]),
                "start_weight_kg": w_start,
                "end_date_actual": str(end_row["date_str"]),
                "end_weight_kg": w_end,
                "diff_kg": diff_kg,
                "diff_pct": diff_pct,
                "direction": direction,
            }
        )
    return rows


def _render_two_date_comparison_html(
    comp_rows: List[Dict[str, Any]],
    start_disp: str,
    end_disp: str,
) -> str:
    ths = (
        "<th style='background:#002B49; color:#FFFFFF; text-align:left; padding:10px 12px;'>Atleta</th>"
        f"<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:10px 10px;'>Peso Iniziale<br><span style='font-weight:400; font-size:0.68rem; color:#CBD5E1;'>vicino al {start_disp}</span></th>"
        f"<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:10px 10px;'>Peso Finale<br><span style='font-weight:400; font-size:0.68rem; color:#CBD5E1;'>vicino al {end_disp}</span></th>"
        "<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:10px 10px;'>Direzione</th>"
        "<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:10px 10px;'>Differenza (kg)</th>"
        "<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:10px 10px;'>Differenza (%)</th>"
    )
    trs = []
    for idx, r in enumerate(comp_rows):
        bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"
        d_dir = r["direction"]
        diff_kg = float(r["diff_kg"])
        diff_pct = float(r["diff_pct"])
        sign = "+" if diff_kg > 0 else ""

        if d_dir == "up":
            arrow_html = (
                "<span style='display:inline-flex; align-items:center; justify-content:center; "
                "width:32px; height:32px; border-radius:999px; background:#DCFCE7; color:#15803D; "
                "font-size:1.25rem; font-weight:900; border:1.5px solid #22C55E;' title='Peso in aumento'>&#9650;</span>"
            )
            badge_bg, badge_col, badge_bd = "#DCFCE7", "#166534", "#86EFAC"
            arrow_txt = "&#9650;"
        elif d_dir == "down":
            arrow_html = (
                "<span style='display:inline-flex; align-items:center; justify-content:center; "
                "width:32px; height:32px; border-radius:999px; background:#FEE2E2; color:#B91C1C; "
                "font-size:1.25rem; font-weight:900; border:1.5px solid #EF4444;' title='Peso in calo'>&#9660;</span>"
            )
            badge_bg, badge_col, badge_bd = "#FEE2E2", "#991B1B", "#FCA5A5"
            arrow_txt = "&#9660;"
        else:
            arrow_html = (
                "<span style='display:inline-flex; align-items:center; justify-content:center; "
                "width:32px; height:32px; border-radius:999px; background:#F1F5F9; color:#475569; "
                "font-size:1.05rem; font-weight:900; border:1.5px solid #CBD5E1;' title='Peso stabile'>=</span>"
            )
            badge_bg, badge_col, badge_bd = "#F1F5F9", "#475569", "#CBD5E1"
            arrow_txt = "="

        trs.append(
            f"<tr style='background:{bg}; border-bottom:1px solid #E2E8F0;'>"
            f"<td style='padding:9px 12px; font-weight:800; color:#0F172A;'>{r['player_name']}</td>"
            f"<td style='padding:8px 10px; text-align:center;'>"
            f"  <div style='font-weight:800; font-size:0.95rem; color:#0F172A;'>{r['start_weight_kg']:.1f} kg</div>"
            f"  <div style='font-size:0.70rem; color:#64748B;'>{_fmt_date_it(r['start_date_actual'])}</div>"
            f"</td>"
            f"<td style='padding:8px 10px; text-align:center;'>"
            f"  <div style='font-weight:800; font-size:0.95rem; color:#0F172A;'>{r['end_weight_kg']:.1f} kg</div>"
            f"  <div style='font-size:0.70rem; color:#64748B;'>{_fmt_date_it(r['end_date_actual'])}</div>"
            f"</td>"
            f"<td style='padding:8px 10px; text-align:center;'>{arrow_html}</td>"
            f"<td style='padding:8px 10px; text-align:center;'>"
            f"  <span style='background:{badge_bg}; color:{badge_col}; border:1px solid {badge_bd}; font-weight:900; font-size:0.88rem; padding:4px 10px; border-radius:6px;'>{arrow_txt} {sign}{diff_kg:.1f} kg</span>"
            f"</td>"
            f"<td style='padding:8px 10px; text-align:center;'>"
            f"  <span style='background:{badge_bg}; color:{badge_col}; border:1px solid {badge_bd}; font-weight:900; font-size:0.88rem; padding:4px 10px; border-radius:6px;'>{arrow_txt} {sign}{diff_pct:.1f}%</span>"
            f"</td>"
            "</tr>"
        )

    return (
        "<div style='overflow-x:auto; border:1px solid #CBD5E1; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.04);'>"
        "<table style='width:100%; border-collapse:collapse; font-family:Inter,system-ui,sans-serif; font-size:0.86rem;'>"
        f"<thead><tr>{ths}</tr></thead>"
        f"<tbody>{''.join(trs)}</tbody>"
        "</table></div>"
    )


def _build_rl_arrow_drawing(direction: str, size: int = 14) -> Drawing:
    d = Drawing(size, size)
    if direction == "up":
        d.add(Polygon([2, 2, size - 2, 2, size / 2.0, size - 2], fillColor=colors.HexColor("#16A34A"), strokeColor=colors.HexColor("#15803D"), strokeWidth=0.6))
    elif direction == "down":
        d.add(Polygon([2, size - 2, size - 2, size - 2, size / 2.0, 2], fillColor=colors.HexColor("#DC2626"), strokeColor=colors.HexColor("#B91C1C"), strokeWidth=0.6))
    else:
        d.add(Circle(size / 2.0, size / 2.0, 3.2, fillColor=colors.HexColor("#64748B"), strokeColor=None))
    return d


def crea_pdf_confronto_2_date(comp_rows: List[Dict[str, Any]], meta_info: Dict[str, str]) -> bytes:
    """Esporta in PDF A4 il confronto pesi tra 2 date con frecce vettoriali su/giù."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20,
        rightMargin=20,
        topMargin=16,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    elements: List[Any] = []

    elements.append(
        _build_fir_header_table(
            "Confronto Peso Corporeo (2 Date)",
            f"Target: {meta_info.get('target_label', 'Roster')} • {meta_info.get('start_disp', '')} -> {meta_info.get('end_disp', '')}",
            f"Ultimo Peso: {meta_info.get('latest_date_disp', '--')}",
            f"Atleti: {len(comp_rows)}",
            total_width=555,
        )
    )
    elements.append(Spacer(1, 8))

    if not comp_rows:
        elements.append(Paragraph("Nessun peso disponibile per il confronto.", styles["Normal"]))
        _build_pdf_with_footer(doc, elements)
        return buffer.getvalue()

    p_hdr = ParagraphStyle("c2_hdr", fontName="Helvetica-Bold", fontSize=8.0, textColor=colors.white, alignment=1, leading=9.5)
    p_hdr_l = ParagraphStyle("c2_hdr_l", fontName="Helvetica-Bold", fontSize=8.0, textColor=colors.white, alignment=0, leading=9.5)
    p_name = ParagraphStyle("c2_name", fontName="Helvetica-Bold", fontSize=8.2, textColor=colors.HexColor("#0F172A"), leading=10)
    p_cell = ParagraphStyle("c2_cell", fontName="Helvetica", fontSize=8.0, textColor=colors.HexColor("#0F172A"), alignment=1, leading=9.5)

    rows: List[List[Any]] = [
        [
            Paragraph("Atleta", p_hdr_l),
            Paragraph(f"Peso Iniziale<br/>({meta_info.get('start_disp', '')})", p_hdr),
            Paragraph(f"Peso Finale<br/>({meta_info.get('end_disp', '')})", p_hdr),
            Paragraph("Trend", p_hdr),
            Paragraph("Diff. (kg)", p_hdr),
            Paragraph("Diff. (%)", p_hdr),
        ]
    ]

    for r in comp_rows:
        d_dir = r["direction"]
        diff_kg = float(r["diff_kg"])
        diff_pct = float(r["diff_pct"])
        sign = "+" if diff_kg > 0 else ""
        col_hex = "#15803D" if d_dir == "up" else ("#B91C1C" if d_dir == "down" else "#475569")

        rows.append(
            [
                Paragraph(r["player_name"], p_name),
                Paragraph(f"<b>{r['start_weight_kg']:.1f} kg</b><br/><font size='6.5' color='#64748B'>{_fmt_date_it(r['start_date_actual'])}</font>", p_cell),
                Paragraph(f"<b>{r['end_weight_kg']:.1f} kg</b><br/><font size='6.5' color='#64748B'>{_fmt_date_it(r['end_date_actual'])}</font>", p_cell),
                _build_rl_arrow_drawing(d_dir, size=14),
                Paragraph(f"<b><font color='{col_hex}'>{sign}{diff_kg:.1f} kg</font></b>", p_cell),
                Paragraph(f"<b><font color='{col_hex}'>{sign}{diff_pct:.1f}%</font></b>", p_cell),
            ]
        )

    col_widths = [145, 100, 100, 42, 84, 84]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements.append(tbl)
    _build_pdf_with_footer(doc, elements)
    return buffer.getvalue()


def _fmt_date_it(iso_str: str) -> str:
    try:
        return pd.to_datetime(iso_str).strftime("%d/%m/%Y")
    except Exception:
        return iso_str


def _render_portal_matrix_html(dates_in_period: List[str], player_series: Dict[str, List[Dict[str, Any]]]) -> str:
    ths = [
        "<th style='position:sticky; left:0; z-index:3; background:#002B49; color:#FFFFFF; text-align:left; padding:8px 10px; min-width:165px; border-right:2px solid #D4AF37;'>Atleta</th>",
        "<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:8px 6px; min-width:105px;'>Trend</th>",
    ]
    for dt_s in dates_in_period:
        try:
            lbl = pd.to_datetime(dt_s).strftime("%d/%m/%y")
        except Exception:
            lbl = dt_s
        ths.append(f"<th style='background:#002B49; color:#FFFFFF; text-align:center; padding:8px 6px; min-width:78px; white-space:nowrap;'>{lbl}</th>")

    trs = []
    for idx, pname in enumerate(sorted(player_series.keys())):
        entries = player_series[pname]
        by_date = {e["date_str"]: e for e in entries}
        bg = "#FFFFFF" if idx % 2 == 0 else "#F8FAFC"
        svg = _build_sparkline_svg(entries)
        tds = [
            f"<td style='position:sticky; left:0; z-index:2; background:{bg}; font-weight:700; color:#0F172A; padding:7px 10px; border-right:2px solid #CBD5E1; white-space:nowrap;'>{pname}</td>",
            f"<td style='background:{bg}; text-align:center; padding:4px 6px; vertical-align:middle;'>{svg}</td>",
        ]
        for dt_s in dates_in_period:
            e = by_date.get(dt_s)
            if not e:
                tds.append(f"<td style='background:{bg}; text-align:center; color:#CBD5E1; padding:6px;'>—</td>")
            else:
                try:
                    d_short = pd.to_datetime(dt_s).strftime("%d/%m")
                except Exception:
                    d_short = dt_s
                if e["is_ref"] or e["pct_prev"] is None:
                    pct_html = "<span style='background:#E0F2FE; color:#0369A1; font-weight:800; font-size:0.65rem; padding:1px 5px; border-radius:4px;'>RIF.</span>"
                else:
                    pct = float(e["pct_prev"])
                    if pct > 0.05:
                        p_bg, p_col = "#DCFCE7", "#166534"
                        sign = "+"
                    elif pct < -0.05:
                        p_bg, p_col = "#FEE2E2", "#991B1B"
                        sign = ""
                    else:
                        p_bg, p_col = "#F1F5F9", "#475569"
                        sign = ""
                    pct_html = f"<span style='background:{p_bg}; color:{p_col}; font-weight:800; font-size:0.66rem; padding:1px 5px; border-radius:4px;'>{sign}{pct:.1f}%</span>"

                cell_html = (
                    f"<div style='line-height:1.25;'>"
                    f"<div style='font-weight:800; font-size:0.84rem; color:#0F172A;'>{e['weight_kg']:.1f} kg</div>"
                    f"<div style='font-size:0.64rem; color:#64748B;'>{d_short}</div>"
                    f"<div style='margin-top:2px;'>{pct_html}</div>"
                    f"</div>"
                )
                tds.append(f"<td style='background:{bg}; text-align:center; padding:5px 6px; vertical-align:middle; border-left:1px solid #E2E8F0;'>{cell_html}</td>")
        trs.append(f"<tr style='border-bottom:1px solid #E2E8F0;'>{''.join(tds)}</tr>")

    return (
        "<div style='overflow-x:auto; border:1px solid #CBD5E1; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.04);'>"
        "<table style='width:100%; border-collapse:collapse; font-family:Inter,system-ui,sans-serif; font-size:0.82rem;'>"
        f"<thead><tr>{''.join(ths)}</tr></thead>"
        f"<tbody>{''.join(trs)}</tbody>"
        "</table></div>"
    )


def _render_single_player_chart(pname: str, entries: List[Dict[str, Any]]) -> go.Figure:
    xs = [_fmt_date_it(e["date_str"]) for e in entries]
    ys = [e["weight_kg"] for e in entries]
    texts = []
    for e in entries:
        if e["is_ref"] or e["pct_prev"] is None:
            texts.append(f"{e['weight_kg']:.1f} kg<br>(RIF.)")
        else:
            pct = float(e["pct_prev"])
            sign = "+" if pct > 0 else ""
            texts.append(f"{e['weight_kg']:.1f} kg<br>({sign}{pct:.1f}%)")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="lines+markers+text",
            text=texts,
            textposition="top center",
            textfont=dict(size=10, color="#0F172A"),
            line=dict(color="#004B87", width=2.5),
            marker=dict(size=8, color="#D4AF37", line=dict(width=1.5, color="#002B49")),
            hovertemplate="<b>%{x}</b><br>Peso: %{y:.1f} kg<extra></extra>",
        )
    )
    y_pad = max(1.0, (max(ys) - min(ys)) * 0.35) if len(ys) > 1 else 2.0
    fig.update_layout(
        title=dict(text=f"Trend Peso Corporeo — {pname}", font=dict(size=14, color="#002B49")),
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=340,
        margin=dict(l=40, r=25, t=48, b=40),
        yaxis=dict(title="Peso (kg)", range=[min(ys) - y_pad, max(ys) + y_pad], gridcolor="#E2E8F0"),
        xaxis=dict(title="Data Misurazione", gridcolor="#F1F5F9"),
    )
    return fig


def render_peso_corporeo(t: dict):
    render_page_header(
        "Monitoraggio Peso Corporeo",
        "Visualizzazione esclusiva dei pesi registrati per Roster, Raduno o Singolo Giocatore con variazione % vs peso precedente",
        "bi-speedometer2",
    )

    df_weights = load_player_weights_df()
    players_df = utils.get_players_df()
    camps_df = utils.get_camps_df()
    camp_players_df = utils.get_camp_players_df()

    # Card dedicata: Data ultimo peso inserito
    latest_date_iso = str(df_weights["date_str"].max()) if not df_weights.empty else ""
    latest_date_disp = _fmt_date_it(latest_date_iso) if latest_date_iso else "Nessun dato"
    n_latest_players = int(df_weights[df_weights["date_str"] == latest_date_iso]["player_name"].nunique()) if latest_date_iso else 0
    total_athletes_db = int(df_weights["player_name"].nunique()) if not df_weights.empty else 0

    c_card, c_k1, c_k2 = st.columns([2.2, 1.2, 1.2])
    with c_card:
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg, #031926 0%, #002B49 65%, #004B87 100%); border-radius:12px; padding:14px 18px; border-left:5px solid #D4AF37; color:#FFFFFF; margin-bottom:10px;">
                <div style="font-size:0.70rem; font-weight:800; letter-spacing:0.10em; text-transform:uppercase; color:#D4AF37;">
                    📅 ULTIMO PESO INSERITO IN ARCHIVIO
                </div>
                <div style="font-size:1.45rem; font-weight:900; margin-top:2px;">{latest_date_disp}</div>
                <div style="font-size:0.78rem; color:#CBD5E1;">{n_latest_players} atleti pesati in questa data</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    c_k1.metric("Atleti con Pesi in Archivio", f"{total_athletes_db}")
    c_k2.metric("Misurazioni Totali Salvate", f"{len(df_weights):,}")

    active_pw_tab = render_tab_navigation(
        "peso_corporeo",
        [
            ("storico", "Storico & Gestione Pesi", "bi-table"),
            ("confronto_2_date", "Confronto 2 Date", "bi-arrow-left-right"),
        ],
    )

    # Selettori Target (condivisi tra entrambe le sottopagine)
    all_weight_players = sorted(df_weights["player_name"].unique().tolist()) if not df_weights.empty else []
    roster_names = sorted(players_df["name_display"].dropna().astype(str).str.strip().unique().tolist()) if not players_df.empty else []
    combined_player_options = sorted(set(all_weight_players) | set(roster_names))

    s_col1, s_col2 = st.columns([1.4, 1.6])
    target_mode = s_col1.radio(
        "1. Selezione Giocatori:",
        ["Intero Roster", "Settimana Raduno", "Singolo Giocatore"],
        horizontal=True,
        key="pw_target_mode",
    )

    selected_camp_row = None
    selected_players: List[str] = []
    target_label = "Intero Roster"

    if target_mode == "Intero Roster":
        selected_players = combined_player_options
        target_label = f"Intero Roster ({len(selected_players)} atleti)"
    elif target_mode == "Settimana Raduno":
        if camps_df.empty:
            st.warning("Nessun raduno presente.")
            selected_players = combined_player_options
        else:
            camp_ids = [int(x) for x in camps_df["id"].tolist()]
            camp_labels = {
                int(r["id"]): f"{r['start_date_str']} • {r['week_name']} ({r['competition']}) — {int(r.get('total_count') or 0)} atleti"
                for _, r in camps_df.iterrows()
            }
            sel_cid = s_col2.selectbox(
                "Seleziona Raduno:",
                camp_ids,
                format_func=lambda cid: camp_labels.get(cid, str(cid)),
                key="pw_sel_camp_id",
            )
            selected_camp_row = camps_df[camps_df["id"] == sel_cid].iloc[0]
            cp_sub = camp_players_df[camp_players_df["camp_id"] == sel_cid] if not camp_players_df.empty else pd.DataFrame()
            selected_players = sorted(cp_sub["player_name"].dropna().astype(str).str.strip().unique().tolist()) if not cp_sub.empty else []
            target_label = f"Raduno {selected_camp_row['week_name']} ({len(selected_players)} convocati)"
    else:
        if combined_player_options:
            sel_single = s_col2.selectbox("Seleziona Giocatore:", combined_player_options, key="pw_sel_single_player")
            selected_players = [sel_single]
            target_label = sel_single

    ref_max_dt = pd.to_datetime(latest_date_iso).date() if latest_date_iso else datetime.date.today()
    ref_min_dt = pd.to_datetime(str(df_weights["date_str"].min())).date() if not df_weights.empty else ref_max_dt

    # =========================================================================
    # SOTTOPAGINA 2: CONFRONTO 2 DATE (SOLA VISUALIZZAZIONE)
    # =========================================================================
    if active_pw_tab == "confronto_2_date":
        d_c1, d_c2 = st.columns(2)
        default_d0 = max(ref_min_dt, ref_max_dt - datetime.timedelta(days=14))
        c2_d0 = d_c1.date_input("2. Data di Inizio:", value=default_d0, key="pw_c2_d0")
        c2_d1 = d_c2.date_input("3. Data di Fine:", value=ref_max_dt, key="pw_c2_d1")
        if c2_d0 > c2_d1:
            c2_d0, c2_d1 = c2_d1, c2_d0

        c2_d0_str = c2_d0.strftime("%Y-%m-%d")
        c2_d1_str = c2_d1.strftime("%Y-%m-%d")
        c2_d0_disp = c2_d0.strftime("%d/%m/%Y")
        c2_d1_disp = c2_d1.strftime("%d/%m/%Y")

        comp_rows = _compute_two_date_comparison(df_weights, selected_players, c2_d0_str, c2_d1_str)

        render_action_bar(
            meta_items=[
                ("ULTIMO PESO", latest_date_disp),
                ("TARGET", target_label),
                ("DATA INIZIO", c2_d0_disp),
                ("DATA FINE", c2_d1_disp),
            ],
            pdf_options={"Report Confronto Pesi (2 Date)": "confronto_2_date"},
            pdf_key=f"pw_c2_pdf_{target_mode}_{c2_d0_str}_{c2_d1_str}",
            generate_fn=lambda _: crea_pdf_confronto_2_date(
                comp_rows,
                meta_info={
                    "target_label": target_label,
                    "start_disp": c2_d0_disp,
                    "end_disp": c2_d1_disp,
                    "latest_date_disp": latest_date_disp,
                },
            ),
            filename_fn=lambda _: f"FIR_Confronto_Pesi_{slugify_name(target_label)}_{c2_d0_str}_{c2_d1_str}.pdf",
        )

        if not comp_rows:
            st.info(f"Nessun peso disponibile per **{target_label}**.")
            return

        n_up = sum(1 for r in comp_rows if r["direction"] == "up")
        n_down = sum(1 for r in comp_rows if r["direction"] == "down")
        n_flat = sum(1 for r in comp_rows if r["direction"] == "flat")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Atleti Confrontati", f"{len(comp_rows)}")
        m2.metric("▲ In Aumento", f"{n_up}")
        m3.metric("▼ In Calo", f"{n_down}")
        m4.metric("= Stabili", f"{n_flat}")

        st.markdown(_render_two_date_comparison_html(comp_rows, c2_d0_disp, c2_d1_disp), unsafe_allow_html=True)
        return

    # =========================================================================
    # SOTTOPAGINA 1: STORICO COMPLETO, IMPORT CSV & GESTIONE SMART
    # =========================================================================

    p_col1, p_col2, p_col3 = st.columns([1.6, 1.0, 1.0])
    preset_opts = [
        "Ultimi 7 giorni",
        "Ultimi 14 giorni",
        "Ultimi 30 giorni",
        "Ultimi 3 mesi",
        "Tutto lo storico",
        "Periodo Personalizzato",
    ]
    if selected_camp_row is not None:
        preset_opts.insert(0, "Settimana Raduno Selezionata")

    period_choice = p_col1.selectbox("2. Periodo di Tempo:", preset_opts, key="pw_period_choice")

    if period_choice == "Settimana Raduno Selezionata" and selected_camp_row is not None:
        d0 = pd.to_datetime(str(selected_camp_row["start_date_str"])[:10]).date()
        d1 = d0 + datetime.timedelta(days=6)
    elif period_choice == "Ultimi 7 giorni":
        d1 = ref_max_dt
        d0 = d1 - datetime.timedelta(days=6)
    elif period_choice == "Ultimi 14 giorni":
        d1 = ref_max_dt
        d0 = d1 - datetime.timedelta(days=13)
    elif period_choice == "Ultimi 30 giorni":
        d1 = ref_max_dt
        d0 = d1 - datetime.timedelta(days=29)
    elif period_choice == "Ultimi 3 mesi":
        d1 = ref_max_dt
        d0 = d1 - datetime.timedelta(days=90)
    elif period_choice == "Tutto lo storico":
        d0, d1 = ref_min_dt, ref_max_dt
    else:
        d0 = p_col2.date_input("Data Inizio:", value=max(ref_min_dt, ref_max_dt - datetime.timedelta(days=29)), key="pw_custom_d0")
        d1 = p_col3.date_input("Data Fine:", value=ref_max_dt, key="pw_custom_d1")
        if d0 > d1:
            d0, d1 = d1, d0

    start_date_str = d0.strftime("%Y-%m-%d")
    end_date_str = d1.strftime("%Y-%m-%d")
    period_label = f"{d0.strftime('%d/%m/%Y')} — {d1.strftime('%d/%m/%Y')}"

    dates_in_period, player_series = _compute_player_period_series(df_weights, selected_players, start_date_str, end_date_str)

    # Action bar con Export PDF fedele alla schermata
    render_action_bar(
        meta_items=[
            ("ULTIMO PESO", latest_date_disp),
            ("TARGET", target_label),
            ("PERIODO", period_label),
            ("ATLETI VISIBILI", f"{len(player_series)}"),
        ],
        pdf_options={"Tabella Completa Pesi & Trend (Come Portale)": "peso_corporeo"},
        pdf_key=f"pw_pdf_{target_mode}_{start_date_str}_{end_date_str}",
        generate_fn=lambda _: crea_pdf_peso_corporeo(
            dates_in_period,
            player_series,
            meta_info={
                "target_label": target_label,
                "period_label": period_label,
                "latest_date_disp": latest_date_disp,
            },
        ),
        filename_fn=lambda _: f"FIR_Peso_Corporeo_{slugify_name(target_label)}_{start_date_str}_{end_date_str}.pdf",
    )

    # Visualizzazione Principale
    if not player_series or not dates_in_period:
        st.info(f"Nessun peso registrato per **{target_label}** nel periodo **{period_label}**.")
    else:
        if target_mode == "Singolo Giocatore" and len(player_series) == 1:
            pname = list(player_series.keys())[0]
            entries = player_series[pname]
            st.plotly_chart(_render_single_player_chart(pname, entries), use_container_width=True)
            tbl_rows = []
            for e in entries:
                pct_str = "RIF. (1° Peso)" if (e["is_ref"] or e["pct_prev"] is None) else f"{'+' if e['pct_prev'] > 0 else ''}{e['pct_prev']:.2f}%"
                tbl_rows.append({"Data": _fmt_date_it(e["date_str"]), "Peso (kg)": f"{e['weight_kg']:.1f} kg", "Δ% vs Precedente": pct_str})
            st.dataframe(pd.DataFrame(tbl_rows), use_container_width=True, hide_index=True)
        else:
            st.markdown(
                f"<div style='font-size:0.84rem; color:#475569; margin-bottom:8px;'>"
                f"Visualizzati <b>{len(player_series)}</b> atleti con pesi registrati su <b>{len(dates_in_period)}</b> date "
                f"(<i>il primo peso di ciascun giocatore nel periodo è indicato come <b>RIF.</b></i>)</div>",
                unsafe_allow_html=True,
            )
            st.markdown(_render_portal_matrix_html(dates_in_period, player_series), unsafe_allow_html=True)

            with st.expander("📈 Grafici Individuali Trend nel Periodo", expanded=False):
                sorted_p = sorted(player_series.keys())
                cols_g = st.columns(3)
                for idx_g, pn_g in enumerate(sorted_p):
                    ents = player_series[pn_g]
                    xs_g = [pd.to_datetime(e["date_str"]).strftime("%d/%m") for e in ents]
                    ys_g = [e["weight_kg"] for e in ents]
                    fg = go.Figure(
                        go.Scatter(
                            x=xs_g,
                            y=ys_g,
                            mode="lines+markers",
                            line=dict(color="#004B87", width=2),
                            marker=dict(size=6, color="#D4AF37"),
                        )
                    )
                    fg.update_layout(
                        title=dict(text=pn_g, font=dict(size=12, color="#002B49")),
                        paper_bgcolor="white",
                        plot_bgcolor="white",
                        height=200,
                        margin=dict(l=30, r=12, t=34, b=26),
                        xaxis=dict(tickfont=dict(size=9)),
                        yaxis=dict(tickfont=dict(size=9), gridcolor="#E2E8F0"),
                    )
                    cols_g[idx_g % 3].plotly_chart(fg, use_container_width=True, key=f"pw_mini_chart_{idx_g}")

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # Sezione Caricamento CSV Futuri
    with st.expander("📤 Carica Nuovo CSV Pesi Corporei (Formato Export)", expanded=False):
        st.caption("Carica un CSV impaginato esattamente come `export (3).csv`. I nuovi pesi verranno uniti in modo non distruttivo all'archivio (upsert su Atleta + Data) e salvati su Cloud.")
        up_csv = st.file_uploader("Seleziona file CSV pesi", type=["csv"], key="pw_csv_uploader")
        if up_csv is not None:
            parsed_df = parse_weights_csv(up_csv, players_df=players_df)
            if parsed_df.empty:
                st.warning("Nessun peso valido rilevato nel CSV caricato.")
            else:
                st.info(
                    f"Rilevati **{len(parsed_df)}** pesi validi su **{parsed_df['player_name'].nunique()}** atleti "
                    f"(dal `{parsed_df['date_str'].min()}` al `{parsed_df['date_str'].max()}`)."
                )
                st.dataframe(parsed_df.head(15), use_container_width=True, hide_index=True)
                if st.button("💾 Importa e Salva Pesi nel Database", type="primary", key="pw_btn_import_csv"):
                    n_up = upsert_player_weights(parsed_df)
                    st.success(f"Importati/aggiornati {n_up} pesi corporei su Cloud!")
                    st.rerun()

    # Sezione Gestione & Modifica Smart
    with st.expander("✏️ Gestione, Modifica & Cancellazione Smart Pesi", expanded=False):
        tab_smart, tab_single_cell, tab_date_ops, tab_player_ops = st.tabs(
            [
                "⚡ Inserimento / Modifica Smart (Multi-Atleta)",
                "🎯 Singolo Giocatore in Data Specifica",
                "📅 Modifica / Cancella Intera Data",
                "👤 Gestisci / Cancella Singolo Giocatore",
            ]
        )

        with tab_smart:
            smart_dt = st.date_input("Data di riferimento per inserimento/modifica:", value=datetime.date.today(), key="pw_smart_date")
            smart_dt_str = smart_dt.strftime("%Y-%m-%d")
            existing_on_dt = df_weights[df_weights["date_str"] == smart_dt_str].set_index("player_name")["weight_kg"].to_dict() if not df_weights.empty else {}
            smart_rows = [
                {
                    "Atleta": pn,
                    "Peso (kg)": float(existing_on_dt[pn]) if pn in existing_on_dt else None,
                }
                for pn in selected_players
            ]
            edited_smart = st.data_editor(
                pd.DataFrame(smart_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Atleta": st.column_config.TextColumn("Atleta", disabled=True),
                    "Peso (kg)": st.column_config.NumberColumn("Peso (kg)", min_value=40.0, max_value=200.0, step=0.1, format="%.1f"),
                },
                key=f"pw_smart_editor_{smart_dt_str}_{len(selected_players)}",
            )
            if st.button("💾 Salva Modifiche Smart per Questa Data", type="primary", key="pw_btn_save_smart"):
                now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                new_recs = []
                to_remove_players = set()
                for _, er in edited_smart.iterrows():
                    pn_e = str(er["Atleta"]).strip()
                    val_e = er["Peso (kg)"]
                    if pd.notna(val_e) and float(val_e) > 0:
                        new_recs.append(
                            {
                                "player_name": pn_e,
                                "csv_name": pn_e,
                                "date_str": smart_dt_str,
                                "weight_kg": round(float(val_e), 2),
                                "updated_at": now_s,
                            }
                        )
                    elif pn_e in existing_on_dt:
                        to_remove_players.add(pn_e)

                base_df = df_weights.copy()
                if to_remove_players:
                    base_df = base_df[~((base_df["date_str"] == smart_dt_str) & (base_df["player_name"].isin(to_remove_players)))]
                if new_recs:
                    base_df = pd.concat([base_df, pd.DataFrame(new_recs)], ignore_index=True)
                save_player_weights_df(base_df)
                st.success(f"Aggiornati i pesi del {_fmt_date_it(smart_dt_str)} su Cloud!")
                st.rerun()

        with tab_single_cell:
            sc1, sc2, sc3 = st.columns([1.6, 1.2, 1.0])
            sc_player = sc1.selectbox("Atleta:", combined_player_options, key="pw_sc_player")
            sc_date = sc2.date_input("Data:", value=datetime.date.today(), key="pw_sc_date")
            sc_date_str = sc_date.strftime("%Y-%m-%d")
            cur_hit = df_weights[(df_weights["player_name"] == sc_player) & (df_weights["date_str"] == sc_date_str)]
            cur_val = float(cur_hit.iloc[0]["weight_kg"]) if not cur_hit.empty else 90.0
            sc_weight = sc3.number_input("Peso (kg):", min_value=40.0, max_value=200.0, value=cur_val, step=0.1, format="%.1f", key="pw_sc_weight")
            b1, b2 = st.columns(2)
            if b1.button("💾 Salva / Aggiorna Singolo Peso", type="primary", key="pw_btn_sc_save", use_container_width=True):
                now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                upsert_player_weights(
                    pd.DataFrame([{"player_name": sc_player, "csv_name": sc_player, "date_str": sc_date_str, "weight_kg": round(float(sc_weight), 2), "updated_at": now_s}])
                )
                st.success(f"Salvato {sc_player} ({_fmt_date_it(sc_date_str)}): {sc_weight:.1f} kg")
                st.rerun()
            if not cur_hit.empty and b2.button("🗑️ Elimina Questo Singolo Peso", key="pw_btn_sc_del", use_container_width=True):
                rem = df_weights[~((df_weights["player_name"] == sc_player) & (df_weights["date_str"] == sc_date_str))]
                save_player_weights_df(rem)
                st.success(f"Eliminato peso di {sc_player} del {_fmt_date_it(sc_date_str)}.")
                st.rerun()

        with tab_date_ops:
            avail_dates = sorted(df_weights["date_str"].unique().tolist(), reverse=True) if not df_weights.empty else []
            if not avail_dates:
                st.info("Nessuna data presente in archivio.")
            else:
                sel_del_date = st.selectbox("Seleziona Data da modificare o eliminare:", avail_dates, format_func=_fmt_date_it, key="pw_del_date_sel")
                sub_dt = df_weights[df_weights["date_str"] == sel_del_date][["player_name", "weight_kg"]].copy()
                st.caption(f"Misurazioni presenti il **{_fmt_date_it(sel_del_date)}**: {len(sub_dt)}")
                ed_dt = st.data_editor(
                    sub_dt,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "player_name": st.column_config.TextColumn("Atleta", disabled=True),
                        "weight_kg": st.column_config.NumberColumn("Peso (kg)", min_value=40.0, max_value=200.0, step=0.1, format="%.1f"),
                    },
                    key=f"pw_ed_date_{sel_del_date}",
                )
                dc1, dc2 = st.columns(2)
                if dc1.button("💾 Salva Modifiche della Data", type="primary", key="pw_btn_save_date_ed", use_container_width=True):
                    now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    others = df_weights[df_weights["date_str"] != sel_del_date].copy()
                    ed_dt["csv_name"] = ed_dt["player_name"]
                    ed_dt["date_str"] = sel_del_date
                    ed_dt["updated_at"] = now_s
                    save_player_weights_df(pd.concat([others, ed_dt[WEIGHT_COLUMNS]], ignore_index=True))
                    st.success(f"Modifiche salvate per il {_fmt_date_it(sel_del_date)}.")
                    st.rerun()
                if dc2.button("🗑️ Elimina TUTTI i Pesi di Questa Data", key="pw_btn_del_entire_date", use_container_width=True):
                    rem = df_weights[df_weights["date_str"] != sel_del_date].copy()
                    save_player_weights_df(rem)
                    st.success(f"Eliminati tutti i pesi del {_fmt_date_it(sel_del_date)}.")
                    st.rerun()

        with tab_player_ops:
            if not all_weight_players:
                st.info("Nessun atleta presente in archivio pesi.")
            else:
                sel_op_player = st.selectbox("Seleziona Giocatore:", all_weight_players, key="pw_op_player_sel")
                sub_pl = df_weights[df_weights["player_name"] == sel_op_player][["date_str", "weight_kg"]].sort_values("date_str", ascending=False).copy()
                ed_pl = st.data_editor(
                    sub_pl,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_config={
                        "date_str": st.column_config.TextColumn("Data (YYYY-MM-DD)"),
                        "weight_kg": st.column_config.NumberColumn("Peso (kg)", min_value=40.0, max_value=200.0, step=0.1, format="%.1f"),
                    },
                    key=f"pw_ed_pl_{sel_op_player}",
                )
                pc1, pc2 = st.columns(2)
                if pc1.button("💾 Salva Storico Giocatore", type="primary", key="pw_btn_save_pl_ed", use_container_width=True):
                    now_s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    others = df_weights[df_weights["player_name"] != sel_op_player].copy()
                    ed_pl["player_name"] = sel_op_player
                    ed_pl["csv_name"] = sel_op_player
                    ed_pl["updated_at"] = now_s
                    save_player_weights_df(pd.concat([others, ed_pl[WEIGHT_COLUMNS]], ignore_index=True))
                    st.success(f"Storico pesi aggiornato per {sel_op_player}.")
                    st.rerun()
                if pc2.button(f"🗑️ Elimina Tutti i Pesi di {sel_op_player}", key="pw_btn_del_entire_pl", use_container_width=True):
                    rem = df_weights[df_weights["player_name"] != sel_op_player].copy()
                    save_player_weights_df(rem)
                    st.success(f"Eliminati tutti i pesi di {sel_op_player}.")
                    st.rerun()
