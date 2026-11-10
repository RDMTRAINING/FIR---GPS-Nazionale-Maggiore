import os
import re
import io
from io import BytesIO
import base64
from PIL import Image
import utils
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
    PageBreak,
    Flowable,
)
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from config import LOGO_PATH, get_logo_base64


def slugify_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(text or "")).strip("_")


def fig_to_rl_image(fig, width=535, height=210):
    """Converte un grafico Plotly in un'immagine ad alta risoluzione per ReportLab."""
    if fig is None:
        styles = getSampleStyleSheet()
        return Paragraph("<i>[Grafico non disponibile]</i>", styles["Normal"])
    try:
        img_bytes = fig.to_image(format="png", width=int(width * 2.0), height=int(height * 2.0), scale=2)
        return RLImage(BytesIO(img_bytes), width=width, height=height)
    except Exception as e1:
        try:
            # Fallback a scala standard 1
            img_bytes = fig.to_image(format="png", width=int(width), height=int(height), scale=1)
            return RLImage(BytesIO(img_bytes), width=width, height=height)
        except Exception as e2:
            import logging
            logging.getLogger("fir_pdf").warning(f"Errore conversione grafico in immagine: {e1} | {e2}")
            styles = getSampleStyleSheet()
            return Paragraph("<i>[Grafico incluso nella vista interattiva]</i>", styles["Normal"])


def _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • GPS ANALYTICS"):
    generato = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
    width_pt = getattr(doc, "pagesize", A4)[0]

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
        canvas.setLineWidth(0.5)
        canvas.line(16, 16, width_pt - 16, 16)
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawString(16, 8, f"{brand}   |   Report generato il {generato}")
        canvas.drawRightString(width_pt - 16, 8, f"Pagina {d.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=_footer, onLaterPages=_footer)


def _build_fir_header_table(main_title: str, sub_title: str, right_line1: str, right_line2: str = "", right_line3: str = "", total_width: float = 808):
    styles = getSampleStyleSheet()
    t_style = ParagraphStyle("FIRTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=13.5, leading=16, textColor=colors.HexColor("#031926"))
    s_style = ParagraphStyle("FIRSub", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=11.5, textColor=colors.HexColor("#334155"))
    r1_style = ParagraphStyle("FIRRight1", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, alignment=2, textColor=colors.HexColor("#031926"))
    r2_style = ParagraphStyle("FIRRight2", parent=styles["Normal"], fontName="Helvetica", fontSize=7.5, leading=9.5, alignment=2, textColor=colors.HexColor("#475569"))

    left_logo = RLImage(LOGO_PATH, width=32, height=38) if os.path.exists(LOGO_PATH) else Paragraph("<b>FIR</b>", t_style)
    center_block = [Paragraph(main_title, t_style), Paragraph(sub_title, s_style)]
    right_block = [Paragraph(right_line1, r1_style)]
    if right_line2:
        right_block.append(Paragraph(right_line2, r2_style))
    if right_line3:
        right_block.append(Paragraph(right_line3, r2_style))

    # Larghezza dinamica (808 pt default per A4 Landscape)
    c_w = [44, max(200, total_width - 324), 280]
    tbl = Table([[left_logo, center_block, right_block]], colWidths=c_w)
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#031926")),
    ]))
    return tbl


def _build_individual_rl_table(df_data: pd.DataFrame, neutral_mode: bool = False) -> Table:
    headers = [
        "Giocatore", "Tempo", "Distanza", "m\\min", "Run Dist",
        "Hml >25W", "Hml>40W", "VHml>50W", "Power Ev.",
        "HSR >18", "HSR>20", "VHSR>25", "V max", "% Vmax",
    ]
    data_rows = [headers]
    f_size = 7.4 if neutral_mode else 6.6
    f_lead = 9.0 if neutral_mode else 7.8
    pad_v = 2.0 if neutral_mode else 0.9
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), f_size),
        ("LEADING", (0, 0), (-1, -1), f_lead),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), pad_v),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]

    status_colors = {
        "Modified": "#86EFAC",
        "RTP": "#FEF08A",
        "Off Feet": "#FCA5A5",
    }

    # Calcolo Top 5 (Verde) e Bottom 3 (Rosso) per reparto per ogni metrica numerica (solo se non in neutral_mode)
    metric_cols_map = [
        ("Tempo", 1), ("Distanza", 2), ("m_min", 3), ("Run_Dist", 4),
        ("Hml_25", 5), ("Hml_40", 6), ("VHml_50", 7), ("Power_Events", 8),
        ("HSR_18", 9), ("HSR_20", 10), ("VHSR_25", 11), ("V_max", 12), ("V_max_pct", 13)
    ]
    top5_coords = set()
    bot3_coords = set()

    if not neutral_mode:
        for dept_val in ["Avanti", "TreQuarti"]:
            d_mask = df_data["department"] == dept_val if "department" in df_data.columns else pd.Series([True]*len(df_data))
            d_sub = df_data[d_mask]
            for m_key, col_pos in metric_cols_map:
                if m_key in d_sub.columns:
                    s = pd.to_numeric(d_sub[m_key], errors="coerce").fillna(0)
                    s_pos = s[s > 0]
                    if len(s_pos) >= 1:
                        n_top = min(5, len(s_pos))
                        top_idx_list = s_pos.nlargest(n_top).index.tolist()
                        for t_orig_idx in top_idx_list:
                            row_num = df_data.index.get_loc(t_orig_idx) + 1
                            top5_coords.add((col_pos, row_num))

                        if len(s_pos) >= 4:
                            n_bot = min(3, len(s_pos) - n_top if len(s_pos) < n_top + 3 else 3)
                            if n_bot > 0:
                                bot_idx_list = s_pos.nsmallest(n_bot).index.tolist()
                                for b_orig_idx in bot_idx_list:
                                    if b_orig_idx not in top_idx_list:
                                        row_num = df_data.index.get_loc(b_orig_idx) + 1
                                        bot3_coords.add((col_pos, row_num))

    prev_dept = None
    for idx, (_, r) in enumerate(df_data.iterrows(), start=1):
        dept = str(r.get("department") or "Avanti")
        if prev_dept is not None and dept != prev_dept:
            cmds.append(("LINEABOVE", (0, idx), (-1, idx), 1.4, colors.HexColor("#334155" if neutral_mode else "#0284C7")))
        prev_dept = dept

        bg_base = "#FFFFFF" if idx % 2 == 1 else ("#F8FAFC" if neutral_mode else "#F0F9FF")
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg_base)))

        if not neutral_mode:
            st_lbl = str(r.get("status") or "Full")
            if st_lbl in status_colors:
                cmds.append(("BACKGROUND", (0, idx), (0, idx), colors.HexColor(status_colors[st_lbl])))

            # Applica evidenziazione Top 5 (verde) e Bottom 3 (rosso)
            for _, c_pos in metric_cols_map:
                coord = (c_pos, idx)
                if coord in top5_coords:
                    cmds.append(("BACKGROUND", coord, coord, colors.HexColor("#DCFCE7")))
                    cmds.append(("TEXTCOLOR", coord, coord, colors.HexColor("#15803D")))
                    cmds.append(("FONTNAME", coord, coord, "Helvetica-Bold"))
                elif coord in bot3_coords:
                    cmds.append(("BACKGROUND", coord, coord, colors.HexColor("#FEE2E2")))
                    cmds.append(("TEXTCOLOR", coord, coord, colors.HexColor("#B91C1C")))
                    cmds.append(("FONTNAME", coord, coord, "Helvetica-Bold"))

        vhsr_num = int(pd.to_numeric(r.get("VHSR_25", r.get("vhsr_25", 0)), errors="coerce") or 0)
        vhsr_str = str(vhsr_num) if vhsr_num > 0 else ""
        vmax_val = float(pd.to_numeric(r.get("V_max", r.get("v_max", 0)), errors="coerce") or 0.0)
        vmax_str = f"{vmax_val:.1f}".replace(".", ",") if bool(r.get("has_gps", True)) else "0,0"

        def _as_int(v):
            return str(int(round(float(pd.to_numeric(v, errors="coerce") or 0))))

        data_rows.append([
            str(r.get("player_name", "-")),
            _as_int(r.get("Tempo", r.get("duration", 0))),
            _as_int(r.get("Distanza", r.get("distance_m", 0))),
            _as_int(r.get("m_min", r.get("m_per_min", 0))),
            _as_int(r.get("Run_Dist", r.get("run_dist", 0))),
            _as_int(r.get("Hml_25", r.get("hml_25", 0))),
            _as_int(r.get("Hml_40", r.get("vhml_40", 0))),
            _as_int(r.get("VHml_50", r.get("vhml_50", 0))),
            _as_int(r.get("Power_Events", r.get("power_events", 0))),
            _as_int(r.get("HSR_18", r.get("hsr_18", 0))),
            _as_int(r.get("HSR_20", r.get("hsr_20", 0))),
            vhsr_str,
            vmax_str,
            _as_int(r.get("V_max_pct", r.get("v_max_pct", 0))),
        ])

    cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))

    # Larghezza 808 pt esatta per layout orizzontale A4
    col_widths = [160, 48, 54, 46, 54, 54, 52, 52, 52, 52, 52, 48, 42, 42]
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_role_dept_rl_table(role_df: pd.DataFrame, dept_df: pd.DataFrame, include_tempo: bool = True) -> Table:
    if include_tempo:
        headers = [
            "Ruolo / Reparto", "Tempo", "Distanza", "m\\min", "Run Dist",
            "Hml >25W", "Hml>40W", "VHml>50W", "N 40\\50W",
            "HSR >18", "HSR>20", "VHSR>25", "V max", "% Vmax",
        ]
        col_widths = [160, 48, 54, 46, 54, 54, 52, 52, 52, 52, 52, 48, 42, 42]
    else:
        headers = [
            "Ruolo / Reparto", "Distanza", "m\\min", "Run Dist",
            "Hml >25W", "Hml>35W", "N >50W", "Power Ev.",
            "HSR >18", "HSR>20", "VHSR>25", "V max", "% Vmax",
        ]
        col_widths = [180, 58, 50, 58, 58, 54, 54, 54, 54, 54, 50, 42, 42]

    def _as_int(v):
        return str(int(round(float(pd.to_numeric(v, errors="coerce") or 0))))

    data_rows = [headers]
    for _, rr in role_df.iterrows():
        row_vals = [str(rr.get("Label", "-"))]
        if include_tempo:
            row_vals.append(_as_int(rr.get("Tempo", rr.get("duration", 0))))
        row_vals.extend([
            _as_int(rr.get("Distanza", rr.get("distance_m", 0))),
            _as_int(rr.get("m_min", rr.get("m_per_min", 0))),
            _as_int(rr.get("Run_Dist", rr.get("run_dist", 0))),
            _as_int(rr.get("Hml_25", rr.get("hml_25", 0))),
            _as_int(rr.get("Hml_40", rr.get("vhml_40", 0))),
            _as_int(rr.get("VHml_50", rr.get("vhml_50", 0))),
            _as_int(rr.get("Power_Events", rr.get("power_events", 0))),
            _as_int(rr.get("HSR_18", rr.get("hsr_18", 0))),
            _as_int(rr.get("HSR_20", rr.get("hsr_20", 0))),
            _as_int(rr.get("VHSR_25", rr.get("vhsr_25", 0))),
            _as_int(rr.get("V_max", rr.get("v_max", 0))),
            _as_int(rr.get("V_max_pct", rr.get("v_max_pct", 0))),
        ])
        data_rows.append(row_vals)

    dept_start_idx = len(data_rows)
    for _, dr in dept_df.iterrows():
        row_vals = [str(dr.get("Label", "-"))]
        if include_tempo:
            row_vals.append(_as_int(dr.get("Tempo", dr.get("duration", 0))))
        row_vals.extend([
            _as_int(dr.get("Distanza", dr.get("distance_m", 0))),
            _as_int(dr.get("m_min", dr.get("m_per_min", 0))),
            _as_int(dr.get("Run_Dist", dr.get("run_dist", 0))),
            _as_int(dr.get("Hml_25", dr.get("hml_25", 0))),
            _as_int(dr.get("Hml_40", dr.get("vhml_40", 0))),
            _as_int(dr.get("VHml_50", dr.get("vhml_50", 0))),
            _as_int(dr.get("Power_Events", dr.get("power_events", 0))),
            _as_int(dr.get("HSR_18", dr.get("hsr_18", 0))),
            _as_int(dr.get("HSR_20", dr.get("hsr_20", 0))),
            _as_int(dr.get("VHSR_25", dr.get("vhsr_25", 0))),
            _as_int(dr.get("V_max", dr.get("v_max", 0))),
            _as_int(dr.get("V_max_pct", dr.get("v_max_pct", 0))),
        ])
        data_rows.append(row_vals)

    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#38BDF8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("LEADING", (0, 0), (-1, -1), 7.8),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("BACKGROUND", (0, 1), (-1, dept_start_idx - 1), colors.HexColor("#BAE6FD")),
        ("BACKGROUND", (0, dept_start_idx), (-1, -1), colors.HexColor("#7DD3FC")),
        ("FONTNAME", (0, dept_start_idx), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, dept_start_idx), (-1, dept_start_idx), 1.2, colors.HexColor("#0284C7")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#7DD3FC")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_target_individual_rl_table(df_data: pd.DataFrame, target_hml: float, target_hsr: float, tol: float, is_day: bool = False, is_match_workrate: bool = False) -> Table:
    if not is_day:
        if is_match_workrate:
            headers = [
                "Giocatore", "Tempo (Oval)", "Distanza/min", "Power Ev./min",
                "Hml/min >25.5W", "Hml % Match", "HSR/min >18\\20", "HSR % Match",
                "V max", "% Vmax",
            ]
        else:
            # Colonne Pagina 1: Giocatore, Tempo, Distanza, Power Events, Hml >25.5W, Hml % Match, HSR >18\20, HSR % Match, V max, % Vmax
            headers = [
                "Giocatore", "Tempo", "Distanza", "Power Ev.",
                "Hml >25.5W", "Hml % Match", "HSR >18\\20", "HSR % Match",
                "V max", "% Vmax",
            ]
        col_widths = [160, 56, 62, 64, 80, 88, 80, 88, 65, 65]  # sum = 808
    else:
        # Colonne Pagina 3: Giocatore, Tempo, Distanza, Hml % Match, Hml >25.5W, HSR % Match, HSR >18\20, V max, % Vmax, VHML >50, VHSR >25, Power Events
        headers = [
            "Giocatore", "Tempo", "Distanza",
            "Hml % Match", "Hml >25.5W", "HSR % Match", "HSR >18\\20",
            "V max", "% Vmax", "VHML >50", "VHSR >25", "Power Ev.",
        ]
        col_widths = [144, 48, 56, 72, 70, 72, 70, 48, 48, 60, 60, 60]  # sum = 808

    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("LEADING", (0, 0), (-1, -1), 7.8),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]

    status_colors = {
        "Modified": "#86EFAC",
        "Modificato": "#86EFAC",
        "RTP": "#FEF08A",
        "Off Feet": "#FCA5A5",
    }

    hml_min, hml_max = target_hml - tol, target_hml + tol
    hsr_min, hsr_max = target_hsr - tol, target_hsr + tol

    def _as_int(v):
        return str(int(round(float(pd.to_numeric(v, errors="coerce") or 0))))

    def _as_wr(v, has_g: bool = True):
        if not has_g:
            return "0,0" if is_match_workrate else "0"
        if is_match_workrate:
            return f"{float(pd.to_numeric(v, errors='coerce') or 0.0):.1f}".replace(".", ",")
        return _as_int(v)

    prev_dept = None
    for idx, (_, r) in enumerate(df_data.iterrows(), start=1):
        dept = str(r.get("department") or "Avanti")
        if prev_dept is not None and dept != prev_dept:
            cmds.append(("LINEABOVE", (0, idx), (-1, idx), 1.4, colors.HexColor("#0284C7")))
        prev_dept = dept

        bg_base = "#FFFFFF" if idx % 2 == 1 else "#F0F9FF"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg_base)))

        st_lbl = str(r.get("status") or "Full")
        if st_lbl in status_colors:
            cmds.append(("BACKGROUND", (0, idx), (0, idx), colors.HexColor(status_colors[st_lbl])))

        has_g = bool(r.get("has_gps", True)) and float(pd.to_numeric(r.get("Tempo", r.get("duration", 0)), errors="coerce") or 0) > 0
        vmax_val = float(pd.to_numeric(r.get("V_max", r.get("v_max", 0)), errors="coerce") or 0.0)
        vmax_str = f"{vmax_val:.1f}".replace(".", ",") if has_g else "0,0"
        vpct_str = _as_int(r.get("V_max_pct", r.get("v_max_pct", 0))) if has_g else "0"

        pct_hml = int(pd.to_numeric(r.get("pct_hml_match", 0), errors="coerce") or 0)
        pct_hsr = int(pd.to_numeric(r.get("pct_hsr_match", 0), errors="coerce") or 0)

        hsr_raw_val = r.get("HSR_18" if dept == "Avanti" else "HSR_20", 0)

        if not is_day:
            data_rows.append([
                str(r.get("player_name", "-")),
                _as_int(r.get("Tempo", r.get("duration", 0))),
                _as_wr(r.get("Distanza", r.get("distance_m", 0)), has_g),
                _as_wr(r.get("Power_Events", r.get("power_events", 0)), has_g),
                _as_wr(r.get("Hml_25", r.get("hml_25", 0)), has_g),
                f"{pct_hml}%",
                _as_wr(hsr_raw_val, has_g),
                f"{pct_hsr}%",
                vmax_str,
                vpct_str,
            ])
            col_pct_hml_idx = 5
            col_pct_hsr_idx = 7
        else:
            hsr_val = int(pd.to_numeric(hsr_raw_val, errors="coerce") or 0)
            vhsr_num = int(pd.to_numeric(r.get("VHSR_25", r.get("vhsr_25", 0)), errors="coerce") or 0)
            data_rows.append([
                str(r.get("player_name", "-")),
                _as_int(r.get("Tempo", r.get("duration", 0))),
                _as_int(r.get("Distanza", r.get("distance_m", 0))),
                f"{pct_hml}%",
                _as_int(r.get("Hml_25", r.get("hml_25", 0))),
                f"{pct_hsr}%",
                str(hsr_val),
                vmax_str,
                vpct_str,
                _as_int(r.get("VHml_50", r.get("vhml_50", 0))),
                str(vhsr_num) if vhsr_num > 0 else "",
                _as_int(r.get("Power_Events", r.get("power_events", 0))),
            ])
            col_pct_hml_idx = 3
            col_pct_hsr_idx = 5

        # Colora la cella HML % Match
        if pct_hml > 0:
            if pct_hml < hml_min:
                hml_bg, hml_fg = "#FEE2E2", "#B91C1C"
            elif pct_hml > hml_max:
                hml_bg, hml_fg = "#FEF3C7", "#B45309"
            else:
                hml_bg, hml_fg = "#DCFCE7", "#15803D"
            cmds.append(("BACKGROUND", (col_pct_hml_idx, idx), (col_pct_hml_idx, idx), colors.HexColor(hml_bg)))
            cmds.append(("TEXTCOLOR", (col_pct_hml_idx, idx), (col_pct_hml_idx, idx), colors.HexColor(hml_fg)))
            cmds.append(("FONTNAME", (col_pct_hml_idx, idx), (col_pct_hml_idx, idx), "Helvetica-Bold"))

        # Colora la cella HSR % Match
        if pct_hsr > 0:
            if pct_hsr < hsr_min:
                hsr_bg, hsr_fg = "#FEE2E2", "#B91C1C"
            elif pct_hsr > hsr_max:
                hsr_bg, hsr_fg = "#FEF3C7", "#B45309"
            else:
                hsr_bg, hsr_fg = "#DCFCE7", "#15803D"
            cmds.append(("BACKGROUND", (col_pct_hsr_idx, idx), (col_pct_hsr_idx, idx), colors.HexColor(hsr_bg)))
            cmds.append(("TEXTCOLOR", (col_pct_hsr_idx, idx), (col_pct_hsr_idx, idx), colors.HexColor(hsr_fg)))
            cmds.append(("FONTNAME", (col_pct_hsr_idx, idx), (col_pct_hsr_idx, idx), "Helvetica-Bold"))

    cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_target_role_dept_rl_table(role_df: pd.DataFrame, dept_df: pd.DataFrame, is_day: bool = False, is_match_workrate: bool = False) -> Table:
    if not is_day:
        if is_match_workrate:
            headers = ["Ruolo / Reparto", "Distanza/min", "Hml/min >25.5W", "HSR/min >18\\20", "% Vmax"]
        else:
            headers = ["Ruolo / Reparto", "Distanza", "Hml >25.5W", "HSR >18\\20", "% Vmax"]
        col_widths = [248, 140, 140, 140, 140]  # sum = 808
    else:
        headers = ["Ruolo / Reparto", "Distanza", "Hml >25.5W", "HSR >18\\20", "V max", "% Vmax", "Power Ev."]
        col_widths = [208, 100, 100, 100, 100, 100, 100]  # sum = 808

    def _as_int(v):
        return str(int(round(float(pd.to_numeric(v, errors="coerce") or 0))))

    def _as_wr(v, has_r: bool = True):
        if not has_r:
            return "0,0" if is_match_workrate else "0"
        if is_match_workrate:
            return f"{float(pd.to_numeric(v, errors='coerce') or 0.0):.1f}".replace(".", ",")
        return _as_int(v)

    data_rows = [headers]
    for _, rr in role_df.iterrows():
        r_lbl = str(rr.get("Label", "-"))
        dept = str(rr.get("department", "Avanti"))
        has_r = float(pd.to_numeric(rr.get("Tempo", 0), errors="coerce") or 0) > 0
        hsr_raw = rr.get("HSR_18" if dept == "Avanti" else "HSR_20", 0)
        if not is_day:
            data_rows.append([
                r_lbl,
                _as_wr(rr.get("Distanza", 0), has_r),
                _as_wr(rr.get("Hml_25", 0), has_r),
                _as_wr(hsr_raw, has_r),
                _as_int(rr.get("V_max_pct", 0)),
            ])
        else:
            data_rows.append([
                r_lbl,
                _as_int(rr.get("Distanza", 0)),
                _as_int(rr.get("Hml_25", 0)),
                _as_int(hsr_raw),
                f"{float(pd.to_numeric(rr.get('V_max', 0), errors='coerce') or 0):.1f}".replace(".", ","),
                _as_int(rr.get("V_max_pct", 0)),
                _as_int(rr.get("Power_Events", 0)),
            ])

    dept_start_idx = len(data_rows)
    for _, dr in dept_df.iterrows():
        d_lbl = str(dr.get("Label", "-"))
        has_d = float(pd.to_numeric(dr.get("Tempo", 0), errors="coerce") or 0) > 0
        hsr_raw = dr.get("HSR_18" if "AVANTI" in d_lbl.upper() else "HSR_20", 0)
        if not is_day:
            data_rows.append([
                d_lbl,
                _as_wr(dr.get("Distanza", 0), has_d),
                _as_wr(dr.get("Hml_25", 0), has_d),
                _as_wr(hsr_raw, has_d),
                _as_int(dr.get("V_max_pct", 0)),
            ])
        else:
            data_rows.append([
                d_lbl,
                _as_int(dr.get("Distanza", 0)),
                _as_int(dr.get("Hml_25", 0)),
                _as_int(hsr_raw),
                f"{float(pd.to_numeric(dr.get('V_max', 0), errors='coerce') or 0):.1f}".replace(".", ","),
                _as_int(dr.get("V_max_pct", 0)),
                _as_int(dr.get("Power_Events", 0)),
            ])

    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.0),
        ("LEADING", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 1), (-1, dept_start_idx - 1), colors.HexColor("#F0F9FF")),
        ("BACKGROUND", (0, dept_start_idx), (-1, -1), colors.HexColor("#E0F2FE")),
        ("FONTNAME", (0, dept_start_idx), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, dept_start_idx), (-1, dept_start_idx), 1.2, colors.HexColor("#0284C7")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
    ]
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_settimana_23_rl_table(df_23: pd.DataFrame, role_means_dict: dict) -> Table:
    headers = [
        "Giocatore", "N°", "Tempo", "Distanza", "m\\min", "Run Dist",
        "Hml >25W", "Hml>40W", "VHml>50W", "HSR >18", "HSR>20", "VHSR>25", "Power Ev.", "V max", "% Vmax"
    ]
    col_widths = [136, 26, 48, 54, 46, 54, 54, 52, 52, 52, 52, 48, 52, 41, 41]  # sum = 808

    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("LEADING", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]

    metric_keys = [
        ("Tempo", 2), ("Distanza", 3), ("m_min", 4), ("Run_Dist", 5),
        ("Hml_25", 6), ("Hml_40", 7), ("VHml_50", 8),
        ("HSR_18", 9), ("HSR_20", 10), ("VHSR_25", 11),
        ("Power_Events", 12), ("V_max", 13), ("V_max_pct", 14),
    ]

    def _as_int(v):
        return str(int(round(float(pd.to_numeric(v, errors="coerce") or 0))))

    for idx, (_, r) in enumerate(df_23.iterrows(), start=1):
        bg_base = "#FFFFFF" if idx % 2 == 1 else "#F0F9FF"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg_base)))

        j_num = int(pd.to_numeric(r.get("jersey_number", 0), errors="coerce") or 0)
        if j_num == 16:
            cmds.append(("LINEABOVE", (0, idx), (-1, idx), 1.5, colors.HexColor("#D97706")))

        vmax_val = float(pd.to_numeric(r.get("V_max", r.get("v_max", 0)), errors="coerce") or 0.0)
        vmax_str = f"{vmax_val:.1f}".replace(".", ",") if vmax_val > 0 else "0,0"
        vhsr_num = int(pd.to_numeric(r.get("VHSR_25", r.get("vhsr_25", 0)), errors="coerce") or 0)

        data_rows.append([
            str(r.get("player_name", "-")),
            str(j_num) if j_num > 0 else "-",
            _as_int(r.get("Tempo", 0)),
            _as_int(r.get("Distanza", 0)),
            _as_int(r.get("m_min", 0)),
            _as_int(r.get("Run_Dist", 0)),
            _as_int(r.get("Hml_25", 0)),
            _as_int(r.get("Hml_40", 0)),
            _as_int(r.get("VHml_50", 0)),
            _as_int(r.get("HSR_18", 0)),
            _as_int(r.get("HSR_20", 0)),
            str(vhsr_num) if vhsr_num > 0 else "0",
            _as_int(r.get("Power_Events", 0)),
            vmax_str,
            _as_int(r.get("V_max_pct", 0)),
        ])

        r_group = str(r.get("role_group", r.get("role", "")))
        r_mean_row = role_means_dict.get(r_group, {})

        if r_mean_row and float(r.get("Tempo", 0)) > 0:
            for m_key, col_pos in metric_keys:
                raw_v = float(pd.to_numeric(r.get(m_key, 0), errors="coerce") or 0)
                mean_v = float(pd.to_numeric(r_mean_row.get(m_key, 0), errors="coerce") or 0)
                if mean_v > 0:
                    if raw_v > mean_v * 1.15:
                        cmds.append(("BACKGROUND", (col_pos, idx), (col_pos, idx), colors.HexColor("#DCFCE7")))
                        cmds.append(("TEXTCOLOR", (col_pos, idx), (col_pos, idx), colors.HexColor("#15803D")))
                        cmds.append(("FONTNAME", (col_pos, idx), (col_pos, idx), "Helvetica-Bold"))
                    elif raw_v < mean_v * 0.85:
                        cmds.append(("BACKGROUND", (col_pos, idx), (col_pos, idx), colors.HexColor("#FEE2E2")))
                        cmds.append(("TEXTCOLOR", (col_pos, idx), (col_pos, idx), colors.HexColor("#B91C1C")))
                        cmds.append(("FONTNAME", (col_pos, idx), (col_pos, idx), "Helvetica-Bold"))

    cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_settimana_23_kpi_rl_table(kpis: dict) -> Table:
    styles = getSampleStyleSheet()
    p_style = ParagraphStyle('KPIStyle', fontName='Helvetica', fontSize=6.8, leading=8.8, textColor=colors.HexColor('#0F172A'))

    top_hml_lines = "<br/>".join([f"<b>{i+1}. {name}</b>: {val}%" for i, (name, val) in enumerate(kpis.get("top_5_hml", []))]) or "—"
    top_hsr_lines = "<br/>".join([f"<b>{i+1}. {name}</b>: {val}%" for i, (name, val) in enumerate(kpis.get("top_5_hsr", []))]) or "—"

    dist_hml = kpis.get("dist_hml", {})
    hml_dist_lines = (
        f"&bull; Superiore al 200%: <b>{dist_hml.get('sup_200', 0)}</b><br/>"
        f"&bull; Tra 100% e 200%: <b>{dist_hml.get('tra_100_200', 0)}</b><br/>"
        f"&bull; Sotto il 100%: <b>{dist_hml.get('sotto_100', 0)}</b>"
    )

    dist_hsr = kpis.get("dist_hsr", {})
    hsr_dist_lines = (
        f"&bull; Superiore al 200%: <b>{dist_hsr.get('sup_200', 0)}</b><br/>"
        f"&bull; Tra 100% e 200%: <b>{dist_hsr.get('tra_100_200', 0)}</b><br/>"
        f"&bull; Sotto il 100%: <b>{dist_hsr.get('sotto_100', 0)}</b>"
    )

    st_fin = kpis.get("starters_finishers", {})
    st_fin_lines = (
        f"<b>Starters (1-15):</b><br/>"
        f"HML: <b>{st_fin.get('starters_hml', 0)}%</b> | HSR: <b>{st_fin.get('starters_hsr', 0)}%</b><br/><br/>"
        f"<b>Finishers (16-23):</b><br/>"
        f"HML: <b>{st_fin.get('finishers_hml', 0)}%</b> | HSR: <b>{st_fin.get('finishers_hsr', 0)}%</b>"
    )

    kpi_data = [
        ["TOP % MATCH HML", "TOP % MATCH HSR 18\\20", "SUDDIVISIONE % HML", "SUDDIVISIONE % HSR", "STARTERS / FINISHERS"],
        [
            Paragraph(top_hml_lines, p_style),
            Paragraph(top_hsr_lines, p_style),
            Paragraph(hml_dist_lines, p_style),
            Paragraph(hsr_dist_lines, p_style),
            Paragraph(st_fin_lines, p_style),
        ]
    ]
    col_widths = [165, 165, 160, 160, 158]  # sum = 808
    tbl = Table(kpi_data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.2),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ("VALIGN", (0, 1), (-1, 1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]))
    return tbl


def _build_top_rankings_rl_table(rankings_dict: dict) -> Table:
    """
    Costruisce la tabella delle 5 classifiche Top Ranking Players per il PDF con ISTOGRAMMI ORIZZONTALI (Horizontal Bars)
    identica al portale FIR (TreQuarti a sinistra, Avanti a destra).
    """
    styles = getSampleStyleSheet()
    hdr_style = ParagraphStyle("RkHdr", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.0, leading=8.5, textColor=colors.HexColor("#0F172A"))
    cell_p_style = ParagraphStyle("RkCellP", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=7.5, textColor=colors.HexColor("#0F172A"))
    cell_v_style = ParagraphStyle("RkCellV", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=7.5, alignment=2, textColor=colors.HexColor("#0F172A"))

    pairs = [
        ("top_hml_tq", "Top Hml TQ (>25.5 W/kg)", "top_hml_av", "Top Hml AV (>25.5 W/kg)", "#38BDF8", "#7C3AED", "m"),
        ("top_hsr_tq", "Top HSR 20 TQ (>20 km/h)", "top_hsr_av", "Top HSR 18 AV (>18 km/h)", "#E11D48", "#DC2626", "m"),
        ("top_vmax_tq", "Top Vmax TQ (Peak of Speed)", "top_vmax_av", "TOP VMAX AV (Peak of Speed)", "#EC4899", "#DB2777", "km/h"),
        ("top_vhml_tq", "Top VHml > 50W TQ", "top_vhml_av", "Top VHml > 40W AV", "#0284C7", "#0D9488", "m"),
        ("top_vhsr_tq", "Top VHSR > 25 TQ", "top_pev_av", "Top POWER Events AV", "#059669", "#16A34A", "evt"),
    ]

    all_rows = []
    table_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 0.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
    ]

    def _make_bar(val_f, max_f, bar_w, color_hex):
        pct = min(1.0, max(0.06, float(val_f) / float(max_f))) if max_f > 0 else 0.06
        d = Drawing(bar_w, 8)
        d.add(Rect(0, 0, bar_w, 8, fillColor=colors.HexColor("#F1F5F9"), strokeColor=None, rx=2, ry=2))
        d.add(Rect(0, 0, pct * bar_w, 8, fillColor=colors.HexColor(color_hex), strokeColor=None, rx=2, ry=2))
        return d

    cur_row_idx = 0
    for k_tq, title_tq, k_av, title_av, bar_c_tq, bar_c_av, unit in pairs:
        all_rows.append([
            Paragraph(f"<b>⚡ {title_tq}</b>", hdr_style), "", "",
            "",
            Paragraph(f"<b>🏉 {title_av}</b>", hdr_style), "", ""
        ])
        table_cmds.append(("SPAN", (0, cur_row_idx), (2, cur_row_idx)))
        table_cmds.append(("SPAN", (4, cur_row_idx), (6, cur_row_idx)))
        table_cmds.append(("BACKGROUND", (0, cur_row_idx), (2, cur_row_idx), colors.HexColor("#E0F2FE")))
        table_cmds.append(("BACKGROUND", (4, cur_row_idx), (6, cur_row_idx), colors.HexColor("#EDE9FE")))
        table_cmds.append(("LINEBELOW", (0, cur_row_idx), (2, cur_row_idx), 1.0, colors.HexColor("#0284C7")))
        table_cmds.append(("LINEBELOW", (4, cur_row_idx), (6, cur_row_idx), 1.0, colors.HexColor("#7C3AED")))
        cur_row_idx += 1

        def _to_pairs(raw_val):
            if isinstance(raw_val, pd.DataFrame):
                return raw_val.iloc[:, :2].values.tolist()
            return raw_val or []

        tq_items = _to_pairs(rankings_dict.get(k_tq))
        av_items = _to_pairs(rankings_dict.get(k_av))
        max_tq = max([float(it[1]) for it in tq_items]) if tq_items and max([float(it[1]) for it in tq_items]) > 0 else 1.0
        max_av = max([float(it[1]) for it in av_items]) if av_items and max([float(it[1]) for it in av_items]) > 0 else 1.0

        for i in range(5):
            p_tq = tq_items[i][0] if i < len(tq_items) else ""
            v_tq_raw = tq_items[i][1] if i < len(tq_items) else 0.0
            v_tq = f"{v_tq_raw:.1f} km/h" if unit == "km/h" and p_tq else (f"{v_tq_raw:,.0f} {unit}".replace(",", ".") if p_tq else "")
            bar_tq = _make_bar(v_tq_raw, max_tq, 180, bar_c_tq) if p_tq else ""

            p_av = av_items[i][0] if i < len(av_items) else ""
            v_av_raw = av_items[i][1] if i < len(av_items) else 0.0
            v_av = f"{v_av_raw:.1f} km/h" if unit == "km/h" and p_av else (f"{v_av_raw:,.0f} {unit}".replace(",", ".") if p_av else "")
            bar_av = _make_bar(v_av_raw, max_av, 180, bar_c_av) if p_av else ""

            all_rows.append([
                Paragraph(p_tq, cell_p_style),
                bar_tq,
                Paragraph(v_tq, cell_v_style),
                "",
                Paragraph(p_av, cell_p_style),
                bar_av,
                Paragraph(v_av, cell_v_style),
            ])
            bg_c = colors.HexColor("#F8FAFC") if i % 2 == 1 else colors.white
            table_cmds.append(("BACKGROUND", (0, cur_row_idx), (2, cur_row_idx), bg_c))
            table_cmds.append(("BACKGROUND", (4, cur_row_idx), (6, cur_row_idx), bg_c))
            table_cmds.append(("LINEBELOW", (0, cur_row_idx), (2, cur_row_idx), 0.2, colors.HexColor("#E2E8F0")))
            table_cmds.append(("LINEBELOW", (4, cur_row_idx), (6, cur_row_idx), 0.2, colors.HexColor("#E2E8F0")))
            cur_row_idx += 1

        all_rows.append(["", "", "", "", "", "", ""])
        table_cmds.append(("SPAN", (0, cur_row_idx), (-1, cur_row_idx)))
        cur_row_idx += 1

    col_widths = [125, 185, 80, 18, 125, 185, 80]
    tbl = Table(all_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(table_cmds))
    return tbl


def _build_storytelling_rl_box(narrative: dict) -> Table:
    """
    Costruisce il riquadro ufficiale FIR di Storytelling della Seduta per il PDF in formato Landscape (808 pt):
    - Bordo dorato (#D4AF37) e sfondo navy (#0B192C)
    - Titolo FIR Sport Science Storytelling + Badge Carico Esecutivo
    - Narrazione Esecutiva (Cosa è successo & Reparti Avanti / TreQuarti)
    - Barra Highlight: Top Speed, Top Engine, Differenziati
    - Striscia 4 KPI Delta (Distanza, HML, Run Dist, HSR)
    """
    if not narrative:
        return Table([[""]], colWidths=[808])

    styles = getSampleStyleSheet()
    title_st = ParagraphStyle(
        "StTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=9.0,
        textColor=colors.HexColor("#D4AF37"),
    )
    badge_st = ParagraphStyle(
        "StBadge",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.8,
        leading=8.2,
        alignment=2,
        textColor=colors.HexColor("#FFFFFF"),
    )
    body_st = ParagraphStyle(
        "StBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.8,
        leading=8.8,
        textColor=colors.HexColor("#F8FAFC"),
    )
    hl_st = ParagraphStyle(
        "StHL",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=6.2,
        leading=7.8,
        textColor=colors.HexColor("#BAE6FD"),
    )
    kpi_lbl_st = ParagraphStyle(
        "StKpiLbl",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=5.5,
        leading=6.8,
        textColor=colors.HexColor("#93C5FD"),
        alignment=1,
    )
    kpi_val_st = ParagraphStyle(
        "StKpiVal",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=11.0,
        textColor=colors.HexColor("#FFFFFF"),
        alignment=1,
    )
    kpi_sub_st = ParagraphStyle(
        "StKpiSub",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=5.2,
        leading=6.2,
        textColor=colors.HexColor("#34D399"),
        alignment=1,
    )

    cur_type = str(narrative.get("cur_type", "Allenamento")).upper()
    badge_txt = str(narrative.get("load_badge", "")).strip()
    story_txt = str(narrative.get("story_text", "")).strip()
    top_spd = str(narrative.get("top_speed", "-")).strip()
    top_eng = str(narrative.get("top_engine", "-")).strip()
    diff_str = str(narrative.get("differenziati", "-")).strip()

    # Riga 1: Titolo e badge
    r1 = [
        Paragraph(f"<b>🎙️ RACCONTO DELLA SEDUTA & HIGHLIGHT TATTICO-FISICI • TIPOLOGIA: {cur_type}</b>", title_st),
        Paragraph(f"<b>{badge_txt}</b>", badge_st),
    ]

    # Riga 2: Narrazione Esecutiva
    r2 = [Paragraph(story_txt, body_st), ""]

    # Riga 3: Barra highlight
    hl_text = (
        f"⚡ <b>Top Speed:</b> {top_spd} &nbsp;&nbsp;&bull;&nbsp;&nbsp; "
        f"🔥 <b>Top Engine:</b> {top_eng} &nbsp;&nbsp;&bull;&nbsp;&nbsp; "
        f"🛡️ <b>Differenziati:</b> {diff_str}"
    )
    r3 = [Paragraph(hl_text, hl_st), ""]

    # Riga 4: Striscia 4 KPI Delta (larghezza 800 pt)
    kpi_list = narrative.get("kpis", [])
    kpi_cells = []
    for k in kpi_list:
        sub_c = colors.HexColor(k.get("color", "#34D399"))
        k_items = [
            Paragraph(k.get("label", "").upper(), kpi_lbl_st),
            Paragraph(k.get("val", "-"), kpi_val_st),
            Paragraph(k.get("sub", ""), ParagraphStyle("SubK", parent=kpi_sub_st, textColor=sub_c)),
        ]
        tk = Table([[it] for it in k_items], colWidths=[195])
        tk.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1E293B")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#334155")),
        ]))
        kpi_cells.append(tk)

    while len(kpi_cells) < 4:
        kpi_cells.append("")

    t_kpis = Table([kpi_cells], colWidths=[198, 198, 198, 198])
    t_kpis.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    r4 = [t_kpis, ""]

    outer = Table([r1, r2, r3, r4], colWidths=[580, 228])
    outer.setStyle(TableStyle([
        ("SPAN", (0, 1), (1, 1)),
        ("SPAN", (0, 2), (1, 2)),
        ("SPAN", (0, 3), (1, 3)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0B192C")),
        ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#D4AF37")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 4.0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3.0),
        ("TOPPADDING", (0, 1), (-1, 1), 2.5),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 3.0),
        ("TOPPADDING", (0, 2), (-1, 2), 2.0),
        ("BOTTOMPADDING", (0, 2), (-1, 2), 3.5),
        ("TOPPADDING", (0, 3), (-1, 3), 2.0),
        ("BOTTOMPADDING", (0, 3), (-1, 3), 4.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (1, 0), 0.5, colors.HexColor("#334155")),
        ("LINEBELOW", (0, 2), (1, 2), 0.5, colors.HexColor("#334155")),
    ]))
    return outer


def _build_trombinoscopio_rl_table(pitch_bundle: dict) -> Table:
    """
    Costruisce la tabella ufficiale ReportLab per lo Schieramento 1-23 Convocati (Foglio 2 Dati Generali):
    - Sinistra: Titolari 1-15 con minutaggio da Oval Match (80') e metriche fisiche (398 pt)
    - Destra: Finishers 16-23 + Box Medie Reparti normalizzate ad 80 minuti + Legenda GPExe (398 pt)
    """
    if not pitch_bundle:
        return Table([["Nessun dato formazione disponibile"]], colWidths=[808])

    starters_df = pitch_bundle.get("starters_df", pd.DataFrame())
    finishers_df = pitch_bundle.get("finishers_df", pd.DataFrame())
    player_stats = pitch_bundle.get("player_stats", {})
    rep_averages = pitch_bundle.get("rep_averages", {})

    styles = getSampleStyleSheet()
    th_st = ParagraphStyle("TromH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.6, leading=6.8, textColor=colors.HexColor("#FFFFFF"), alignment=1)
    th_l_st = ParagraphStyle("TromHL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.6, leading=6.8, textColor=colors.HexColor("#FFFFFF"), alignment=0)
    td_c_st = ParagraphStyle("TromC", parent=styles["Normal"], fontName="Helvetica", fontSize=5.8, leading=7.0, textColor=colors.HexColor("#0F172A"), alignment=1)
    td_b_st = ParagraphStyle("TromB", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.8, leading=7.0, textColor=colors.HexColor("#0F172A"), alignment=1)
    td_l_st = ParagraphStyle("TromL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.8, leading=7.0, textColor=colors.HexColor("#0F172A"), alignment=0)
    rep_title_st = ParagraphStyle("RepT", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.2, leading=7.5, textColor=colors.HexColor("#D4AF37"), alignment=0)

    # Larghezza 398 pt esatta (13 colonne: 6 GPS + 3 Oval Match)
    col_w = [14, 78, 42, 20, 24, 30, 30, 30, 28, 28, 24, 25, 25]

    def _make_table_for_group(group_df: pd.DataFrame, title: str) -> Table:
        rows = [
            [Paragraph(f"<b>{title}</b>", th_l_st), "", "", "", "", "", "", "", "", "", "", "", ""],
            [
                Paragraph("N°", th_st),
                Paragraph("GIOCATORE", th_l_st),
                Paragraph("RUOLO", th_l_st),
                Paragraph("MIN", th_st),
                Paragraph("POS", th_st),
                Paragraph("DT", th_st),
                Paragraph("DC", th_st),
                Paragraph("HML", th_st),
                Paragraph("VHML", th_st),
                Paragraph("HSR", th_st),
                Paragraph("CIC", th_st),
                Paragraph("TCK", th_st),
                Paragraph("RCK", th_st),
            ]
        ]
        table_cmds = [
            ("SPAN", (0, 0), (-1, 0)),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#0F172A")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
            ("GRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ]
        r_idx = 2
        for _, r in group_df.iterrows():
            p_name = str(r.get("player_name", "")).strip()
            j_num = int(r.get("jersey_number", 0))
            role = str(r.get("role", "")).strip()
            st_p = player_stats.get(p_name, {})
            m_val = int(round(st_p.get("minutes", 0)))
            pos = f"{st_p.get('PoS', 0):.1f}" if st_p.get("PoS", 0) > 0 else "-"
            dt = f"{int(st_p.get('DT', 0)):,}".replace(",", ".") if st_p.get("DT", 0) > 0 else "-"
            dc = f"{int(st_p.get('DC', 0)):,}".replace(",", ".") if st_p.get("DC", 0) > 0 else "-"
            hml = f"{int(st_p.get('Hml', 0)):,}".replace(",", ".") if st_p.get("Hml", 0) > 0 else "-"
            vhml = f"{int(st_p.get('VHml', 0)):,}".replace(",", ".") if st_p.get("VHml", 0) > 0 else "-"
            hsr = f"{int(st_p.get('HSR', 0)):,}".replace(",", ".") if st_p.get("HSR", 0) > 0 else "-"
            cic = f"{int(round(st_p.get('CIC', 0)))}" if st_p.get("CIC", 0) > 0 else "0"
            tck = f"{int(round(st_p.get('TCK', 0)))}" if st_p.get("TCK", 0) > 0 else "0"
            rck = f"{int(round(st_p.get('RCK', 0)))}" if st_p.get("RCK", 0) > 0 else "0"

            bg_c = colors.HexColor("#EFF6FF") if r_idx % 2 == 1 else colors.white
            table_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), bg_c))

            rows.append([
                Paragraph(str(j_num), td_b_st),
                Paragraph(p_name[:18], td_l_st),
                Paragraph(role[:11], td_c_st),
                Paragraph(str(m_val), td_b_st),
                Paragraph(pos, td_c_st),
                Paragraph(dt, td_c_st),
                Paragraph(dc, td_c_st),
                Paragraph(hml, td_c_st),
                Paragraph(vhml, td_c_st),
                Paragraph(hsr, td_c_st),
                Paragraph(cic, td_b_st),
                Paragraph(tck, td_b_st),
                Paragraph(rck, td_b_st),
            ])
            r_idx += 1

        t_grp = Table(rows, colWidths=col_w)
        t_grp.setStyle(TableStyle(table_cmds))
        return t_grp

    left_tbl = _make_table_for_group(starters_df, "TITOLARI (1–15)")
    right_fin_tbl = _make_table_for_group(finishers_df, "FINISHERS (16–23) • PANCHINA")

    # Box Medie Reparti (Somma Avanti / 8, Somma TreQuarti / 7 - larghezza 398 pt)
    col_w_rep = [54, 32, 24, 28, 34, 34, 34, 32, 36, 30, 30, 30]
    rep_rows = [
        [Paragraph("<b>MEDIE REPARTI MATCH (SOMMA AVANTI ÷ 8 • SOMMA TREQUARTI ÷ 7)</b>", rep_title_st), "", "", "", "", "", "", "", "", "", "", ""],
        [
            Paragraph("REPARTO", th_l_st),
            Paragraph("POSIZ.", th_st),
            Paragraph("MIN", th_st),
            Paragraph("POS", th_st),
            Paragraph("DT", th_st),
            Paragraph("DC", th_st),
            Paragraph("HML", th_st),
            Paragraph("VHML", th_st),
            Paragraph("HSR", th_st),
            Paragraph("CIC", th_st),
            Paragraph("TCK", th_st),
            Paragraph("RCK", th_st),
        ],
    ]
    rep_cmds = [
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#1E293B")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("GRID", (0, 1), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]
    cur_rr = 2
    for d_name in ["Avanti", "TreQuarti"]:
        d_info = rep_averages.get(d_name, {})
        divisor_val = d_info.get("divisor", 8 if d_name == "Avanti" else 7)
        avg_min = int(round(d_info.get("minutes", 80)))
        rep_rows.append([
            Paragraph(d_name.upper(), td_l_st),
            Paragraph(f"÷ {divisor_val}", td_b_st),
            Paragraph(f"{avg_min}'", td_c_st),
            Paragraph(f"{d_info.get('PoS', 0):.1f}", td_c_st),
            Paragraph(f"{int(round(d_info.get('DT', 0))):,}".replace(",", "."), td_c_st),
            Paragraph(f"{int(round(d_info.get('DC', 0))):,}".replace(",", "."), td_c_st),
            Paragraph(f"{int(round(d_info.get('Hml', 0))):,}".replace(",", "."), td_c_st),
            Paragraph(f"{int(round(d_info.get('VHml', 0))):,}".replace(",", "."), td_c_st),
            Paragraph(f"{int(round(d_info.get('HSR', 0))):,}".replace(",", "."), td_c_st),
            Paragraph(f"{d_info.get('CIC', 0):.1f}", td_b_st),
            Paragraph(f"{d_info.get('TCK', 0):.1f}", td_b_st),
            Paragraph(f"{d_info.get('RCK', 0):.1f}", td_b_st),
        ])
        rep_cmds.append(("BACKGROUND", (0, cur_rr), (-1, cur_rr), colors.HexColor("#F8FAFC")))
        cur_rr += 1

    rep_tbl = Table(rep_rows, colWidths=col_w_rep)
    rep_tbl.setStyle(TableStyle(rep_cmds))

    # Box Legenda Metriche GPExe & Oval (larghezza 398 pt)
    leg_p_st = ParagraphStyle("TromLeg", parent=styles["Normal"], fontName="Helvetica", fontSize=5.3, leading=6.8, textColor=colors.HexColor("#334155"))
    leg_rows = [
        [Paragraph("<b>LEGENDA METRICHE GPEXE &amp; OVAL MATCH (FIR)</b>", rep_title_st)],
        [Paragraph(
            "<b>• PoS:</b> Vmax (km/h) &nbsp;|&nbsp; <b>• DT:</b> Dist. Totale (m) &nbsp;|&nbsp; <b>• DC:</b> Corsa &gt;6 km/h (m) &nbsp;|&nbsp; "
            "<b>• Hml:</b> &gt;25.5 W/kg &nbsp;|&nbsp; <b>• VHml:</b> &gt;50 W/kg &nbsp;|&nbsp; <b>• HSR:</b> &gt;18 AV / &gt;20 TQ<br/>"
            "<b>• CIC:</b> TotalCarriesInContact &nbsp;|&nbsp; <b>• TCK:</b> TackleComplete &nbsp;|&nbsp; <b>• RCK:</b> TotalRuckEntries",
            leg_p_st
        )]
    ]
    leg_tbl = Table(leg_rows, colWidths=[398])
    leg_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F1F5F9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.0),
    ]))

    right_combined = Table([[right_fin_tbl], [Spacer(1, 4)], [rep_tbl], [Spacer(1, 4)], [leg_tbl]], colWidths=[398])
    right_combined.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    outer_match = Table([[left_tbl, "", right_combined]], colWidths=[398, 12, 398])
    outer_match.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return outer_match


def _build_typologies_benchmark_rl_table(multi_bundle: dict) -> Table:
    """
    Costruisce la tabella ufficiale ReportLab con i Benchmark di tutte le 10 Tipologie FIR (Foglio 2):
    Volume, Velocità, Rugby, Team run, Clarity, Reparto, Extra, Lavoro fisico, Match, RTP
    Larghezza 808 pt esatta con dati storici reali.
    """
    styles = getSampleStyleSheet()
    th_st = ParagraphStyle("TypH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.6, leading=6.8, textColor=colors.HexColor("#FFFFFF"), alignment=1)
    th_l_st = ParagraphStyle("TypHL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.6, leading=6.8, textColor=colors.HexColor("#FFFFFF"), alignment=0)
    td_c_st = ParagraphStyle("TypC", parent=styles["Normal"], fontName="Helvetica", fontSize=5.8, leading=7.2, textColor=colors.HexColor("#0F172A"), alignment=1)
    td_b_st = ParagraphStyle("TypB", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=5.8, leading=7.2, textColor=colors.HexColor("#0F172A"), alignment=0)

    rows = [
        [
            Paragraph("TIPOLOGIA FIR", th_l_st),
            Paragraph("SEDUTE", th_st),
            Paragraph("AV DIST", th_st),
            Paragraph("AV M/MIN", th_st),
            Paragraph("AV RUN", th_st),
            Paragraph("AV HML", th_st),
            Paragraph("AV HSR18", th_st),
            Paragraph("TQ DIST", th_st),
            Paragraph("TQ M/MIN", th_st),
            Paragraph("TQ RUN", th_st),
            Paragraph("TQ HML", th_st),
            Paragraph("TQ HSR20", th_st),
        ]
    ]
    table_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]

    typ_data = multi_bundle.get("typologies_data", []) if multi_bundle else []
    if not typ_data:
        from views.report_comparazione import SESSION_TYPE_BASELINES
        for cat, base in SESSION_TYPE_BASELINES.items():
            av = base.get("Avanti", {})
            tq = base.get("TreQuarti", {})
            typ_data.append({
                "typology": cat,
                "n_sess": "Storico",
                "av_dist": f"{int(round(av.get('distance_m', 0))):,}".replace(",", "."),
                "av_mmin": f"{av.get('m_per_min', 0):.0f}",
                "av_run": f"{int(round(av.get('run_dist', 0))):,}".replace(",", "."),
                "av_hml": f"{int(round(av.get('hml', 0))):,}".replace(",", "."),
                "av_hsr": f"{int(round(av.get('hsr', 0))):,}".replace(",", "."),
                "tq_dist": f"{int(round(tq.get('distance_m', 0))):,}".replace(",", "."),
                "tq_mmin": f"{tq.get('m_per_min', 0):.0f}",
                "tq_run": f"{int(round(tq.get('run_dist', 0))):,}".replace(",", "."),
                "tq_hml": f"{int(round(tq.get('hml', 0))):,}".replace(",", "."),
                "tq_hsr": f"{int(round(tq.get('hsr', 0))):,}".replace(",", "."),
            })

    for i, td in enumerate(typ_data):
        r_num = i + 1
        bg = colors.HexColor("#F8FAFC") if r_num % 2 == 1 else colors.white
        table_cmds.append(("BACKGROUND", (0, r_num), (-1, r_num), bg))
        rows.append([
            Paragraph(f"<b>{td['typology']}</b>", td_b_st),
            Paragraph(str(td.get("n_sess", "-")), td_c_st),
            Paragraph(str(td.get("av_dist", "-")), td_c_st),
            Paragraph(str(td.get("av_mmin", "-")), td_c_st),
            Paragraph(str(td.get("av_run", "-")), td_c_st),
            Paragraph(str(td.get("av_hml", "-")), td_c_st),
            Paragraph(str(td.get("av_hsr", "-")), td_c_st),
            Paragraph(str(td.get("tq_dist", "-")), td_c_st),
            Paragraph(str(td.get("tq_mmin", "-")), td_c_st),
            Paragraph(str(td.get("tq_run", "-")), td_c_st),
            Paragraph(str(td.get("tq_hml", "-")), td_c_st),
            Paragraph(str(td.get("tq_hsr", "-")), td_c_st),
        ])

    col_widths = [120, 48, 66, 54, 66, 66, 66, 66, 54, 66, 66, 71]
    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(table_cmds))
    return tbl


def _build_multisession_matrix_rl_table(matrix_df: pd.DataFrame) -> Table:
    """
    Costruisce la tabella comparativa per il Confronto Multi-Sessione (2+ sedute):
    Mostra i parametri fisici a confronto tra le sedute selezionate,
    con colonna MEDIA evidenziata in verde smeraldo e colonna Δ % in ambra.
    Larghezza totale: 808 pt esatti.
    """
    if matrix_df is None or matrix_df.empty:
        return Table([[Paragraph("Nessun dato di confronto disponibile", getSampleStyleSheet()["Normal"])]], colWidths=[808])

    styles = getSampleStyleSheet()
    th_st = ParagraphStyle("MultiMatH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.0, leading=7.5, textColor=colors.HexColor("#FFFFFF"), alignment=1)
    th_l_st = ParagraphStyle("MultiMatHL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.0, leading=7.5, textColor=colors.HexColor("#FFFFFF"), alignment=0)
    td_c_st = ParagraphStyle("MultiMatC", parent=styles["Normal"], fontName="Helvetica", fontSize=6.2, leading=7.8, textColor=colors.HexColor("#0F172A"), alignment=1)
    td_b_st = ParagraphStyle("MultiMatB", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.2, leading=7.8, textColor=colors.HexColor("#0F172A"), alignment=0)
    td_m_st = ParagraphStyle("MultiMatM", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.2, leading=7.8, textColor=colors.HexColor("#065F46"), alignment=1)
    td_d_st = ParagraphStyle("MultiMatD", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.2, leading=7.8, textColor=colors.HexColor("#92400E"), alignment=1)

    cols = list(matrix_df.columns)
    sess_cols = [c for c in cols if c not in ("Parametro", "MEDIA", "Min", "Max", "Δ %")]
    n_sess = max(1, len(sess_cols))
    sess_w = max(45.0, 412.0 / n_sess)
    param_w = 808.0 - (sess_w * n_sess) - 62.0 - 52.0 - 52.0 - 52.0
    if param_w < 140.0:
        param_w = 140.0
        sess_w = (808.0 - param_w - 62.0 - 156.0) / n_sess

    col_widths = []
    for c in cols:
        if c == "Parametro":
            col_widths.append(param_w)
        elif c == "MEDIA":
            col_widths.append(62.0)
        elif c in ("Min", "Max", "Δ %"):
            col_widths.append(52.0)
        else:
            col_widths.append(sess_w)

    header_cells = []
    for c in cols:
        if c == "Parametro":
            header_cells.append(Paragraph("PARAMETRO FISICO / METRICA", th_l_st))
        elif c == "MEDIA":
            header_cells.append(Paragraph("★ MEDIA", th_st))
        else:
            header_cells.append(Paragraph(str(c)[:25], th_st))

    rows = [header_cells]
    table_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
    ]

    media_col_idx = cols.index("MEDIA") if "MEDIA" in cols else -1
    delta_col_idx = cols.index("Δ %") if "Δ %" in cols else -1

    for r_idx, (_, r) in enumerate(matrix_df.iterrows()):
        row_num = r_idx + 1
        bg = colors.HexColor("#F8FAFC") if row_num % 2 == 1 else colors.white
        table_cmds.append(("BACKGROUND", (0, row_num), (-1, row_num), bg))
        if media_col_idx >= 0:
            table_cmds.append(("BACKGROUND", (media_col_idx, row_num), (media_col_idx, row_num), colors.HexColor("#DCFCE7")))
        if delta_col_idx >= 0:
            table_cmds.append(("BACKGROUND", (delta_col_idx, row_num), (delta_col_idx, row_num), colors.HexColor("#FEF3C7")))

        row_cells = []
        for c_idx, c in enumerate(cols):
            val = str(r[c])
            if c == "Parametro":
                row_cells.append(Paragraph(f"<b>{val}</b>", td_b_st))
            elif c == "MEDIA":
                row_cells.append(Paragraph(f"<b>{val}</b>", td_m_st))
            elif c == "Δ %":
                row_cells.append(Paragraph(f"<b>{val}</b>", td_d_st))
            else:
                row_cells.append(Paragraph(val, td_c_st))
        rows.append(row_cells)

    tbl = Table(rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(table_cmds))
    return tbl


class RugbyPitchFlowable(Flowable):
    """Flowable personalizzato ReportLab che disegna il campo di gioco rugby con i 15 titolari, foto e panchina."""
    def __init__(self, pitch_bundle, meta):
        Flowable.__init__(self)
        self.width = 808
        self.height = 569.27
        self.pitch_bundle = pitch_bundle or {}
        self.meta = meta or {}

    def wrap(self, availWidth, availHeight):
        return self.width, availHeight

    def draw(self):
        self.canv.saveState()
        self.canv.translate(-16.0, -14.0)
        pb = self.pitch_bundle
        m_meta = {
            "title": str(pb.get("match_name") or self.meta.get("session_name") or "NUOVA ZELANDA - ITALIA").upper(),
            "date_str": str(pb.get("date_str") or self.meta.get("date_disp") or self.meta.get("date_str") or "").upper(),
            "slogan": "PRIMI SEMPRE • ATTACCARE SEMPRE",
            "competition": str(self.meta.get("week_competition") or "NATIONS CHAMPIONSHIP").upper(),
        }
        _draw_schieramento_pitch_on_canvas(
            self.canv,
            match_meta=m_meta,
            starters_df=pb.get("starters_df", pd.DataFrame()),
            finishers_df=pb.get("finishers_df", pd.DataFrame()),
            player_stats=pb.get("player_stats", {}),
            rep_averages=pb.get("rep_averages", {}),
        )
        self.canv.restoreState()


def _build_densita_individual_rl_table(df_dens: pd.DataFrame) -> Table:
    headers = ["Giocatore", "Ruolo", "Min", "HML (m)", "HML/min", "% Match HML", "HSR (m)", "HSR/min", "% Match HSR", "V max", "% Vmax"]
    col_widths = [168, 75, 45, 60, 60, 65, 60, 60, 65, 75, 75]  # sum = 808
    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("LEADING", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]
    for idx, (_, r) in enumerate(df_dens.iterrows(), start=1):
        bg = "#FFFFFF" if idx % 2 == 1 else "#F8FAFC"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))
        p_nm = str(r.get("player_name", "-"))
        role = str(r.get("role", "-"))
        dur = int(round(float(pd.to_numeric(r.get("duration", r.get("Tempo", 0)), errors="coerce") or 0)))
        hml = int(round(float(pd.to_numeric(r.get("hml", r.get("Hml_25", 0)), errors="coerce") or 0)))
        hml_m = float(pd.to_numeric(r.get("hml_min", (hml / max(1, dur))), errors="coerce") or 0.0)
        pct_hml = int(round(float(pd.to_numeric(r.get("pct_hml_match", 0), errors="coerce") or 0)))
        hsr = int(round(float(pd.to_numeric(r.get("hsr", r.get("HSR_18", r.get("HSR_20", 0))), errors="coerce") or 0)))
        hsr_m = float(pd.to_numeric(r.get("hsr_min", (hsr / max(1, dur))), errors="coerce") or 0.0)
        pct_hsr = int(round(float(pd.to_numeric(r.get("pct_hsr_match", 0), errors="coerce") or 0)))
        vmax = float(pd.to_numeric(r.get("v_max", r.get("V_max", 0)), errors="coerce") or 0.0)
        vpct = int(round(float(pd.to_numeric(r.get("v_max_pct", r.get("V_max_pct", 0)), errors="coerce") or 0)))

        row_vals = [
            p_nm, role, str(dur), str(hml), f"{hml_m:.1f}".replace(".", ","),
            f"{pct_hml}%" if pct_hml > 0 else "-",
            str(hsr), f"{hsr_m:.1f}".replace(".", ","),
            f"{pct_hsr}%" if pct_hsr > 0 else "-",
            f"{vmax:.1f}".replace(".", ","), f"{vpct}%" if vpct > 0 else "-"
        ]
        data_rows.append(row_vals)
        if pct_hml >= 90:
            cmds.extend([("BACKGROUND", (5, idx), (5, idx), colors.HexColor("#DCFCE7")), ("TEXTCOLOR", (5, idx), (5, idx), colors.HexColor("#15803D"))])
        elif pct_hml >= 75:
            cmds.extend([("BACKGROUND", (5, idx), (5, idx), colors.HexColor("#FEF3C7")), ("TEXTCOLOR", (5, idx), (5, idx), colors.HexColor("#B45309"))])
        elif pct_hml > 0:
            cmds.extend([("BACKGROUND", (5, idx), (5, idx), colors.HexColor("#FEE2E2")), ("TEXTCOLOR", (5, idx), (5, idx), colors.HexColor("#B91C1C"))])

        if pct_hsr >= 90:
            cmds.extend([("BACKGROUND", (8, idx), (8, idx), colors.HexColor("#DCFCE7")), ("TEXTCOLOR", (8, idx), (8, idx), colors.HexColor("#15803D"))])
        elif pct_hsr >= 75:
            cmds.extend([("BACKGROUND", (8, idx), (8, idx), colors.HexColor("#FEF3C7")), ("TEXTCOLOR", (8, idx), (8, idx), colors.HexColor("#B45309"))])
        elif pct_hsr > 0:
            cmds.extend([("BACKGROUND", (8, idx), (8, idx), colors.HexColor("#FEE2E2")), ("TEXTCOLOR", (8, idx), (8, idx), colors.HexColor("#B91C1C"))])

    cmds.append(("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"))
    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_semaforo_kpi_rl_table(kpis: dict) -> Table:
    """Costruisce le 4 card KPI per il Semaforo Vmax identiche al portale FIR."""
    title_g = ParagraphStyle("KpiTitleG", fontName="Helvetica-Bold", fontSize=7.2, leading=9.0, textColor=colors.HexColor("#15803D"), alignment=1)
    title_y = ParagraphStyle("KpiTitleY", fontName="Helvetica-Bold", fontSize=7.2, leading=9.0, textColor=colors.HexColor("#B45309"), alignment=1)
    title_r = ParagraphStyle("KpiTitleR", fontName="Helvetica-Bold", fontSize=7.2, leading=9.0, textColor=colors.HexColor("#B91C1C"), alignment=1)
    title_b = ParagraphStyle("KpiTitleB", fontName="Helvetica-Bold", fontSize=7.2, leading=9.0, textColor=colors.HexColor("#0369A1"), alignment=1)

    val_g = ParagraphStyle("KpiValG", fontName="Helvetica-Bold", fontSize=11.5, leading=14.0, textColor=colors.HexColor("#15803D"), alignment=1)
    val_y = ParagraphStyle("KpiValY", fontName="Helvetica-Bold", fontSize=11.5, leading=14.0, textColor=colors.HexColor("#B45309"), alignment=1)
    val_r = ParagraphStyle("KpiValR", fontName="Helvetica-Bold", fontSize=11.5, leading=14.0, textColor=colors.HexColor("#B91C1C"), alignment=1)
    val_b = ParagraphStyle("KpiValB", fontName="Helvetica-Bold", fontSize=11.5, leading=14.0, textColor=colors.HexColor("#0369A1"), alignment=1)

    n_green = kpis.get("n_green", 0)
    n_yellow = kpis.get("n_yellow", 0)
    n_red = kpis.get("n_red", 0)
    pct_green = kpis.get("pct_green", 0.0)
    avg_wpct = kpis.get("avg_wpct", 0.0)
    w_start = kpis.get("w_start", "")
    w_end = kpis.get("w_end", "")

    header_row = [
        Paragraph("COPERTI (&ge;85% ULTIMI 7gg)", title_g),
        Paragraph("DA RICHIAMARE (8–14gg)", title_y),
        Paragraph("SCOPERTI (&gt;14gg SENZA &ge;85%)", title_r),
        Paragraph("PICCO MEDIO % VMAX SETTIMANA", title_b),
    ]

    body_row = [
        Paragraph(f"<b>{n_green} atleti</b><br/><font size='6.8' color='#475569'>{pct_green:.0f}% del gruppo</font>", val_g),
        Paragraph(f"<b>{n_yellow} atleti</b><br/><font size='6.8' color='#475569'>Richiamo velocità consigliato</font>", val_y),
        Paragraph(f"<b>{n_red} atleti</b><br/><font size='6.8' color='#475569'>Attenzione esposizione sprint</font>", val_r),
        Paragraph(f"<b>{avg_wpct:.1f}%</b><br/><font size='6.8' color='#475569'>Settimana {w_start} &rarr; {w_end}</font>", val_b),
    ]

    col_widths = [202, 202, 202, 202]  # sum = 808
    tbl = Table([header_row, body_row], colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#DCFCE7")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FEF3C7")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#FEE2E2")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#E0F2FE")),
        ("BACKGROUND", (0, 1), (0, 1), colors.HexColor("#F0FDF4")),
        ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#FFFBEB")),
        ("BACKGROUND", (2, 1), (2, 1), colors.HexColor("#FEF2F2")),
        ("BACKGROUND", (3, 1), (3, 1), colors.HexColor("#F0F9FF")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 3.0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2.5),
        ("TOPPADDING", (0, 1), (-1, 1), 3.5),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 4.0),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (0, 1), 1.0, colors.HexColor("#16A34A")),
        ("BOX", (1, 0), (1, 1), 1.0, colors.HexColor("#F59E0B")),
        ("BOX", (2, 0), (2, 1), 1.0, colors.HexColor("#DC2626")),
        ("BOX", (3, 0), (3, 1), 1.0, colors.HexColor("#0284C7")),
    ]))
    return tbl


def _build_semaforo_vmax_rl_table(df_vmax: pd.DataFrame) -> Table:
    """Tabella analitica a 9 colonne conforme alla schermata del portale Semaforo Vmax."""
    headers = [
        "Giocatore", "Ruolo / Reparto", "Vmax Roster",
        "Picco Seduta", "Picco Settimana", "Picco 3 Sett.",
        "Ultima Toccata ≥85%", "Ultima Toccata ≥90%", "Semaforo Vmax"
    ]
    col_widths = [130, 95, 65, 78, 80, 80, 90, 90, 100]  # sum = 808
    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.6),
        ("LEADING", (0, 0), (-1, -1), 7.8),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
    ]

    for idx, (_, r) in enumerate(df_vmax.iterrows(), start=1):
        bg = "#FFFFFF" if idx % 2 == 1 else "#F8FAFC"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))

        p_nm = str(r.get("player_name", "-"))
        role = str(r.get("role", "-"))
        dept = str(r.get("department", "-"))
        role_dept = f"{role} ({dept})"

        v_roster = float(r.get("roster_vmax", 30.0) or 30.0)
        v_roster_str = f"{v_roster:.1f} km/h".replace(".", ",")

        v_sess = float(r.get("sess_vmax", 0.0) or 0.0)
        p_sess = float(r.get("sess_pct", 0.0) or 0.0)
        sess_str = f"{v_sess:.1f} ({p_sess:.0f}%)".replace(".", ",") if v_sess > 0 else "—"

        v_wk = float(r.get("week_vmax", 0.0) or 0.0)
        p_wk = float(r.get("week_pct", 0.0) or 0.0)
        wk_str = f"{v_wk:.1f} ({p_wk:.0f}%)".replace(".", ",") if v_wk > 0 else "—"

        v_21 = float(r.get("vmax_21", 0.0) or 0.0)
        p_21 = float(r.get("pct_21", 0.0) or 0.0)
        v21_str = f"{v_21:.1f} ({p_21:.0f}%)".replace(".", ",") if v_21 > 0 else "—"

        d85 = int(r.get("days_85", 999))
        l85 = str(r.get("last_85_dt", ""))
        d85_str = f"{d85} gg fa ({l85})" if d85 < 900 else "Oltre 60 gg / N.D."

        d90 = int(r.get("days_90", 999))
        l90 = str(r.get("last_90_dt", ""))
        d90_str = f"{d90} gg fa ({l90})" if d90 < 900 else "Oltre 60 gg / N.D."

        sc = str(r.get("status_code", "red")).lower()
        if sc == "green":
            st_lbl = "COPERTO (≤7gg)"
            st_bg, st_fg = "#DCFCE7", "#15803D"
        elif sc == "yellow":
            st_lbl = "RICHIAMO (8–14gg)"
            st_bg, st_fg = "#FEF3C7", "#B45309"
        else:
            st_lbl = "SCOPERTO (>14gg)"
            st_bg, st_fg = "#FEE2E2", "#B91C1C"

        row_vals = [
            p_nm, role_dept, v_roster_str, sess_str, wk_str, v21_str, d85_str, d90_str, st_lbl
        ]
        data_rows.append(row_vals)

        cmds.extend([
            ("BACKGROUND", (2, idx), (2, idx), colors.HexColor("#F0F9FF")),
            ("TEXTCOLOR", (2, idx), (2, idx), colors.HexColor("#0369A1")),
            ("FONTNAME", (2, idx), (2, idx), "Helvetica-Bold"),
            ("FONTNAME", (4, idx), (5, idx), "Helvetica-Bold"),
            ("BACKGROUND", (8, idx), (8, idx), colors.HexColor(st_bg)),
            ("TEXTCOLOR", (8, idx), (8, idx), colors.HexColor(st_fg)),
            ("FONTNAME", (8, idx), (8, idx), "Helvetica-Bold"),
        ])
        if p_wk >= 90:
            cmds.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#15803D")))
        elif p_wk >= 85:
            cmds.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#0284C7")))
        elif p_wk >= 78:
            cmds.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#B45309")))
        elif p_wk > 0:
            cmds.append(("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#B91C1C")))

    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_confronto_settimane_summary_rl_table(sum_df: pd.DataFrame, wk_a_short: str, wk_b_short: str) -> Table:
    headers = [
        "Reparto / Gruppo", "Atleti",
        f"Dist {wk_a_short[:10]}", f"Dist {wk_b_short[:10]}", "Δ Dist",
        f"HML {wk_a_short[:10]}", f"HML {wk_b_short[:10]}", "Δ HML",
        f"HSR {wk_a_short[:10]}", f"HSR {wk_b_short[:10]}", "Δ HSR",
        "HML/min", "HSR/min", "Vmax"
    ]
    col_widths = [124, 46, 54, 54, 46, 50, 50, 46, 48, 48, 46, 64, 64, 68]  # Sum = 808
    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("LEADING", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]
    for idx, (_, r) in enumerate(sum_df.iterrows(), start=1):
        bg = "#FFFFFF" if idx % 2 == 1 else "#F8FAFC"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))
        grp = str(r.get("Gruppo", "-"))
        atl = str(r.get("Atleti A / B", "-"))
        d_a = str(r.get(f"Distanza ({wk_a_short})", "-"))
        d_b = str(r.get(f"Distanza ({wk_b_short})", "-"))
        d_dt = str(r.get("Δ Dist %", "-"))
        h_a = str(r.get(f"HML ({wk_a_short})", "-"))
        h_b = str(r.get(f"HML ({wk_b_short})", "-"))
        d_hm = str(r.get("Δ HML %", "-"))
        s_a = str(r.get(f"HSR ({wk_a_short})", "-"))
        s_b = str(r.get(f"HSR ({wk_b_short})", "-"))
        d_sr = str(r.get("Δ HSR %", "-"))
        hm_min = str(r.get("HML/min (A vs B)", "-"))
        sr_min = str(r.get("HSR/min (A vs B)", "-"))
        vmax = str(r.get("Picco Vmax (A vs B)", "-"))

        data_rows.append([grp, atl, d_a, d_b, d_dt, h_a, h_b, d_hm, s_a, s_b, d_sr, hm_min, sr_min, vmax])
        cmds.append(("FONTNAME", (0, idx), (0, idx), "Helvetica-Bold"))
        for col_i, d_val in [(4, d_dt), (7, d_hm), (10, d_sr)]:
            if "+" in d_val:
                cmds.extend([("BACKGROUND", (col_i, idx), (col_i, idx), colors.HexColor("#DCFCE7")), ("TEXTCOLOR", (col_i, idx), (col_i, idx), colors.HexColor("#15803D")), ("FONTNAME", (col_i, idx), (col_i, idx), "Helvetica-Bold")])
            elif "-" in d_val:
                cmds.extend([("BACKGROUND", (col_i, idx), (col_i, idx), colors.HexColor("#FEE2E2")), ("TEXTCOLOR", (col_i, idx), (col_i, idx), colors.HexColor("#B91C1C")), ("FONTNAME", (col_i, idx), (col_i, idx), "Helvetica-Bold")])

    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _build_confronto_settimane_players_rl_table(merged_p: pd.DataFrame, wk_a_short: str, wk_b_short: str) -> Table:
    headers = [
        "Giocatore", "Reparto",
        f"HML {wk_a_short[:10]}", f"HML {wk_b_short[:10]}", "Δ HML (m)",
        f"HSR {wk_a_short[:10]}", f"HSR {wk_b_short[:10]}", "Δ HSR (m)",
        f"HML/min", f"HSR/min", "Vmax"
    ]
    col_widths = [158, 65, 60, 60, 55, 60, 60, 55, 75, 75, 85]  # Sum = 808
    data_rows = [headers]
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("LEADING", (0, 0), (-1, -1), 7.6),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]
    for idx, (_, r) in enumerate(merged_p.sort_values(by=["dept_A", "player_name"]).iterrows(), start=1):
        bg = "#FFFFFF" if idx % 2 == 1 else "#F8FAFC"
        cmds.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor(bg)))
        p_nm = str(r.get("player_name", "-"))
        dept = str(r.get("dept_A", "-"))
        h_a = int(round(float(pd.to_numeric(r.get("hml_25_A", 0), errors="coerce") or 0)))
        h_b = int(round(float(pd.to_numeric(r.get("hml_25_B", 0), errors="coerce") or 0)))
        d_hml = h_a - h_b
        s_a = int(round(float(pd.to_numeric(r.get("hsr_spec_A", 0), errors="coerce") or 0)))
        s_b = int(round(float(pd.to_numeric(r.get("hsr_spec_B", 0), errors="coerce") or 0)))
        d_hsr = s_a - s_b
        hm_min = f"{float(r.get('hml_min_A', 0)):.1f} vs {float(r.get('hml_min_B', 0)):.1f}"
        sr_min = f"{float(r.get('hsr_min_A', 0)):.2f} vs {float(r.get('hsr_min_B', 0)):.2f}"
        vm = f"{float(r.get('v_max_A', 0)):.1f} vs {float(r.get('v_max_B', 0)):.1f}"

        data_rows.append([
            p_nm, dept,
            str(h_a), str(h_b), f"{d_hml:+d}",
            str(s_a), str(s_b), f"{d_hsr:+d}",
            hm_min, sr_min, vm
        ])
        cmds.append(("FONTNAME", (0, idx), (0, idx), "Helvetica-Bold"))
        if d_hml > 0:
            cmds.extend([("BACKGROUND", (4, idx), (4, idx), colors.HexColor("#DCFCE7")), ("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#15803D"))])
        elif d_hml < 0:
            cmds.extend([("BACKGROUND", (4, idx), (4, idx), colors.HexColor("#FEE2E2")), ("TEXTCOLOR", (4, idx), (4, idx), colors.HexColor("#B91C1C"))])

        if d_hsr > 0:
            cmds.extend([("BACKGROUND", (7, idx), (7, idx), colors.HexColor("#DCFCE7")), ("TEXTCOLOR", (7, idx), (7, idx), colors.HexColor("#15803D"))])
        elif d_hsr < 0:
            cmds.extend([("BACKGROUND", (7, idx), (7, idx), colors.HexColor("#FEE2E2")), ("TEXTCOLOR", (7, idx), (7, idx), colors.HexColor("#B91C1C"))])

    tbl = Table(data_rows, colWidths=col_widths)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def crea_pdf_cruscotto_fir(
    sottoarea: str,
    meta: dict,
    sess_bundle: dict,
    day_bundle: dict,
    week_bundle: dict,
    comp_bundle: dict = None,
    pitch_bundle: dict = None,
    multi_bundle: dict = None,
    multisess_bundle: dict = None,
    typologies_bundle: dict = None,
    target_sess_bundle: dict = None,
    target_day_bundle: dict = None,
    settimana_23_bundle: dict = None,
    densita_bundle: dict = None,
    semaforo_bundle: dict = None,
    confronto_settimane_bundle: dict = None,
) -> bytes:
    """
    Genera il PDF ufficiale FIR in formato A4 Orizzontale (Landscape):
    - Impaginazione a due fogli ottimizzati dove necessario per evitare spazi bianchi
    - Grafici di benchmark ed attainment a tutta larghezza (808 pt)
    - Istogrammi orizzontali grafici nel report TOP RANKING PLAYERS
    - Trombinoscopio con campo grafico (15 titolari + foto) e tabella analitica 1-23 su 2 fogli
    - Grafici % Match 80' ad alta risoluzione (440 pt di altezza) per la massima leggibilità dei nomi
    - Grafici e matrice comparativa completa per le 10 tipologie FIR
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=16,
        leftMargin=16,
        topMargin=12,
        bottomMargin=14,
    )
    elements = []

    def _add_page_sessione():
        # Foglio 1: Dati Individuali e Medie di Reparto
        elements.append(
            _build_fir_header_table(
                "Report Sessione",
                "Dati individuali di Seduta",
                meta.get("session_name", ""),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Tipologia: {meta.get('session_type', meta.get('archetype', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_individual_rl_table(sess_bundle["df"]))
        elements.append(Spacer(1, 4))
        elements.append(_build_role_dept_rl_table(sess_bundle.get("role_df", pd.DataFrame()), sess_bundle.get("dept_df", pd.DataFrame()), include_tempo=True))

        # Foglio 2: Raggiungimento Target & Benchmark della Tipologia allungato per riempire bene la pagina
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Sessione",
                "Raggiungimento Target di Seduta vs Benchmark Tipologia FIR",
                meta.get("session_name", ""),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Benchmark: {meta.get('session_type', meta.get('archetype', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        if sess_bundle.get("fig") is not None:
            elements.append(fig_to_rl_image(sess_bundle["fig"], width=808, height=430))
            elements.append(Spacer(1, 6))

    def _add_page_scheda_giocatori():
        # Pagina singola neutra per i giocatori: SOLO dati individuali senza colori di evidenziazione e senza medie/analisi
        df_players_sheet = sess_bundle.get("df_players_sheet", sess_bundle["df"])
        sheet_title = sess_bundle.get("players_sheet_title", "Scheda Giocatori")
        sheet_sub = sess_bundle.get("players_sheet_sub", "Dati Individuali di Seduta")
        sheet_sess = sess_bundle.get("players_sheet_sess", meta.get("session_name", ""))
        elements.append(
            _build_fir_header_table(
                sheet_title,
                sheet_sub,
                sheet_sess,
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Raduno: {meta.get('week_name', '')}",
                "",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        elements.append(_build_individual_rl_table(df_players_sheet, neutral_mode=True))

    def _add_page_istogramma():
        elements.append(
            _build_fir_header_table(
                "Report Sessione",
                "ISTOGRAMMA INDIVIDUALE DEI GIOCATORI",
                meta.get("session_name", ""),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • {meta.get('session_type', meta.get('archetype', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        if sess_bundle.get("fig_hist_fw") is not None:
            elements.append(fig_to_rl_image(sess_bundle["fig_hist_fw"], width=808, height=230))
            elements.append(Spacer(1, 4))
        if sess_bundle.get("fig_hist_bk") is not None:
            elements.append(fig_to_rl_image(sess_bundle["fig_hist_bk"], width=808, height=230))

    def _add_page_report_generale():
        # Foglio 1: Storytelling, 4 KPI cards e Grafici di Reparto
        elements.append(
            _build_fir_header_table(
                "Report Allenamento",
                "Dati Collettivi & Storytelling Esecutivo",
                f"{meta.get('session_name', '')} • {meta.get('session_type', meta.get('archetype', ''))}",
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        if comp_bundle is not None:
            if comp_bundle.get("narrative"):
                elements.append(_build_storytelling_rl_box(comp_bundle["narrative"]))
                elements.append(Spacer(1, 6))

            if comp_bundle.get("fig_av") is not None and comp_bundle.get("fig_tq") is not None:
                img_av = fig_to_rl_image(comp_bundle["fig_av"], width=398, height=255)
                img_tq = fig_to_rl_image(comp_bundle["fig_tq"], width=398, height=255)
                t_charts = Table([[img_av, img_tq]], colWidths=[404, 404])
                t_charts.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                elements.append(t_charts)

        # Foglio 2: Top Rankings con istogrammi orizzontali colorati
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Allenamento",
                "Classifiche di Reparto per Metrica & Top Ranking Players (Istogrammi)",
                f"{meta.get('session_name', '')} • {meta.get('session_type', meta.get('archetype', ''))}",
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        if comp_bundle is not None and comp_bundle.get("rankings") is not None:
            elements.append(_build_top_rankings_rl_table(comp_bundle["rankings"]))

    def _add_page_schieramento():
        # Foglio 1: Disegno del Campo, 15 Titolari con Foto, Panchina e Medie 80'
        if pitch_bundle is not None:
            elements.append(RugbyPitchFlowable(pitch_bundle, meta))
        else:
            elements.append(_build_trombinoscopio_rl_table({}))

        # Foglio 2: Tabella Analitica Completa 1-23 e Statistiche Match
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Trombinoscopio Match",
                "Tabella Analitica Convocati (1-23) & Minutaggi Ufficiali",
                (pitch_bundle or {}).get("match_name", "Gara"),
                f"Data: {(pitch_bundle or {}).get('date_str', meta.get('date_str', ''))} • {meta.get('week_competition', 'Nazionale')}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        elements.append(_build_trombinoscopio_rl_table(pitch_bundle or {}))

    def _add_page_giornata():
        sess_list_str = " • ".join(day_bundle.get("sessions_list", []))
        # Foglio 1: Dati Individuali della Giornata
        elements.append(
            _build_fir_header_table(
                "Report Giornata",
                "Dati individuali Cumulati (Tutte le Sedute del Giorno)",
                day_bundle.get("date_short", meta.get("date_str", "")),
                sess_list_str,
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_individual_rl_table(day_bundle.get("df", pd.DataFrame())))
        elements.append(Spacer(1, 4))
        elements.append(_build_role_dept_rl_table(day_bundle.get("role_df", pd.DataFrame()), day_bundle.get("dept_df", pd.DataFrame()), include_tempo=False))

        # Foglio 2: Grafico % Match 80' a tutta altezza con nomi leggibili al 100%
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Giornata",
                "Distribuzione Parametri vs Benchmark 80' Match (% Match per Giocatore)",
                day_bundle.get("date_short", meta.get("date_str", "")),
                sess_list_str,
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        if day_bundle.get("fig_match_pct") is not None:
            elements.append(fig_to_rl_image(day_bundle["fig_match_pct"], width=808, height=440))

    def _add_page_settimana():
        # Foglio 1: Dati Individuali Settimanali
        elements.append(
            _build_fir_header_table(
                "Report Settimanale",
                "Dati individuali Cumulati del Periodo / Raduno",
                f"Periodo: {week_bundle.get('period_str', '')}",
                f"{week_bundle.get('competition', '')} • {week_bundle.get('week_name', '')}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_individual_rl_table(week_bundle.get("df", pd.DataFrame())))
        elements.append(Spacer(1, 4))
        elements.append(_build_role_dept_rl_table(week_bundle.get("role_df", pd.DataFrame()), week_bundle.get("dept_df", pd.DataFrame()), include_tempo=False))

        # Foglio 2: Grafico % Match 80' Settimanale a tutta altezza con tutti i nomi leggibili
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Settimanale",
                "Distribuzione Cumulata vs Benchmark 80' Match (% Match per Giocatore)",
                f"Periodo: {week_bundle.get('period_str', '')}",
                f"{week_bundle.get('competition', '')} • {week_bundle.get('week_name', '')}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        if week_bundle.get("fig_match_pct") is not None:
            elements.append(fig_to_rl_image(week_bundle["fig_match_pct"], width=808, height=440))

    if typologies_bundle is None:
        typologies_bundle = multi_bundle or {}
    if multisess_bundle is None:
        multisess_bundle = multi_bundle or {}

    def _add_page_confronto_multisessione():
        # Foglio 1: Grafici Comparativi Multi-Sessione (Volume, Intensità, Sprint con Barra MEDIA)
        n_ms_sess = len(multisess_bundle.get("session_summaries", []))
        elements.append(
            _build_fir_header_table(
                "Confronto Multi-Sessione",
                "Grafici Comparativi Volume, Intensità e Sprint (con Barra MEDIA)",
                f"{n_ms_sess} Sedute FIR a Confronto" if n_ms_sess > 0 else "CONFRONTO MULTI-SESSIONE",
                f"Filtro Reparto: {multisess_bundle.get('filter_dept', 'Tutti (Collettivo)')}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        c_dist = multisess_bundle.get("fig_dist")
        c_hml = multisess_bundle.get("fig_hml")
        c_hsr = multisess_bundle.get("fig_hsr")
        c_mmin = multisess_bundle.get("fig_mmin") or multisess_bundle.get("fig_tempo")
        if c_dist is not None and c_hml is not None:
            img_dist = fig_to_rl_image(c_dist, width=398, height=172)
            img_hml = fig_to_rl_image(c_hml, width=398, height=172)
            row1 = [img_dist, img_hml]
            if c_hsr is not None and c_mmin is not None:
                img_hsr = fig_to_rl_image(c_hsr, width=398, height=172)
                img_mmin = fig_to_rl_image(c_mmin, width=398, height=172)
                row2 = [img_hsr, img_mmin]
                t_grid = Table([row1, row2], colWidths=[404, 404])
            else:
                t_grid = Table([row1], colWidths=[404, 404])
            t_grid.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            elements.append(t_grid)
        elif multisess_bundle.get("fig_radar") is not None:
            elements.append(fig_to_rl_image(multisess_bundle["fig_radar"], width=808, height=360))

        # Foglio 2: Radar di Profilo Collettivo + Matrice Comparativa Parametri
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Confronto Multi-Sessione",
                "Radar di Profilo e Matrice Comparativa Parametri tra le Sedute Selezionate",
                f"{n_ms_sess} Sedute FIR a Confronto" if n_ms_sess > 0 else "CONFRONTO MULTI-SESSIONE",
                f"Filtro Reparto: {multisess_bundle.get('filter_dept', 'Tutti (Collettivo)')}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        if multisess_bundle.get("fig_radar") is not None:
            elements.append(fig_to_rl_image(multisess_bundle["fig_radar"], width=460, height=175))
            elements.append(Spacer(1, 4))
        mat_df = multisess_bundle.get("matrix_df")
        if mat_df is not None and not mat_df.empty:
            elements.append(_build_multisession_matrix_rl_table(mat_df))

    def _add_page_medie_tipologie_fir():
        # Foglio 1: Grafici di Confronto Tipologie FIR (Distanza per Reparto & HML/HSR)
        elements.append(
            _build_fir_header_table(
                "Medie Tipologie FIR",
                "Grafici Comparativi Carichi per Tipologia FIR (Avanti vs TreQuarti)",
                "BENCHMARK STORICO NAZIONALE FIR",
                meta.get("date_disp", meta.get("date_str", "")),
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        if typologies_bundle.get("fig_dist") is not None and typologies_bundle.get("fig_hml") is not None:
            img_dist = fig_to_rl_image(typologies_bundle["fig_dist"], width=398, height=360)
            img_hml = fig_to_rl_image(typologies_bundle["fig_hml"], width=398, height=360)
            t_mcharts = Table([[img_dist, img_hml]], colWidths=[404, 404])
            t_mcharts.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(t_mcharts)

        # Foglio 2: Tabella Matrice Benchmark Completa su Tutte le 10 Tipologie FIR
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Medie Tipologie FIR",
                "Benchmark Medie Tipologie FIR (Database Nazionale Ufficiale)",
                "BENCHMARK STORICO NAZIONALE FIR",
                meta.get("date_disp", meta.get("date_str", "")),
                total_width=808,
            )
        )
        elements.append(Spacer(1, 6))
        elements.append(_build_typologies_benchmark_rl_table(typologies_bundle))

    def _add_page_target_sessione():
        if not target_sess_bundle or target_sess_bundle.get("df") is None:
            return
        t_df = target_sess_bundle["df"]
        t_hml = target_sess_bundle.get("target_hml", 70.0)
        t_hsr = target_sess_bundle.get("target_hsr", 40.0)
        t_tol = target_sess_bundle.get("tol", 5.0)
        is_match_wr = bool(target_sess_bundle.get("is_match_workrate", False))

        sub_hdr = (
            "Analisi Match su Minutaggio Ufficiale Oval (Work Rate /min eccetto V max e % Vmax)"
            if is_match_wr
            else "Dati individuali e TARGET — Sessione"
        )

        # Foglio 1: Dati individuali e TARGET Sessione
        elements.append(
            _build_fir_header_table(
                "Report Coaches",
                sub_hdr,
                meta.get("session_name", ""),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Target HML: {t_hml:.0f}% • Target HSR: {t_hsr:.0f}% (±{t_tol:.0f}%)",
                "Green: TARGET CENTRATO  •  Red: INFERIORE AL TARGET  •  Yellow: SUPERIORE AL TARGET",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_target_individual_rl_table(t_df, t_hml, t_hsr, t_tol, is_day=False, is_match_workrate=is_match_wr))

        # Foglio 2: Grafici Raggiungimento Target 100% Stacked e Medie Ruolo e Reparto
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Coaches",
                "RAGGIUNGIMENTO TARGET 100% STACKED & MEDIE DI RUOLO E REPARTO",
                meta.get("session_name", ""),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Benchmark: {meta.get('session_type', meta.get('archetype', ''))}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        f_hml = target_sess_bundle.get("fig_hml")
        f_hsr = target_sess_bundle.get("fig_hsr")
        if f_hml is not None and f_hsr is not None:
            img_hml = fig_to_rl_image(f_hml, width=398, height=220)
            img_hsr = fig_to_rl_image(f_hsr, width=398, height=220)
            t_charts = Table([[img_hml, img_hsr]], colWidths=[404, 404])
            t_charts.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(t_charts)
            elements.append(Spacer(1, 6))

        r_df = target_sess_bundle.get("role_df", pd.DataFrame())
        d_df = target_sess_bundle.get("dept_df", pd.DataFrame())
        elements.append(_build_target_role_dept_rl_table(r_df, d_df, is_day=False, is_match_workrate=is_match_wr))

    def _add_page_target_giornata():
        if not target_day_bundle or target_day_bundle.get("df") is None:
            return
        t_df = target_day_bundle["df"]
        t_hml = target_day_bundle.get("target_hml", 60.0)
        t_hsr = target_day_bundle.get("target_hsr", 50.0)
        t_tol = target_day_bundle.get("tol", 5.0)
        sess_list_str = " • ".join(meta.get("day_sessions_list", []))

        # Foglio 1: Dati individuali e TARGET Giornata Cumulata
        elements.append(
            _build_fir_header_table(
                "Report TOTALE GIORNATA",
                "Dati individuali e TARGET — Giornata Cumulata",
                meta.get("date_short", meta.get("date_str", "")),
                f"Sedute: {sess_list_str} • Target HML: {t_hml:.0f}% • Target HSR: {t_hsr:.0f}% (±{t_tol:.0f}%)",
                "Green: TARGET CENTRATO  •  Red: INFERIORE AL TARGET  •  Yellow: SUPERIORE AL TARGET",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_target_individual_rl_table(t_df, t_hml, t_hsr, t_tol, is_day=True))

        # Foglio 2: Raggiungimento Target 100% Stacked e Medie Ruolo e Reparto Giornaliere
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report TOTALE GIORNATA",
                "RAGGIUNGIMENTO TARGET 100% STACKED & MEDIE DI RUOLO E REPARTO",
                meta.get("date_short", meta.get("date_str", "")),
                f"Sedute: {sess_list_str}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        f_hml = target_day_bundle.get("fig_hml")
        f_hsr = target_day_bundle.get("fig_hsr")
        if f_hml is not None and f_hsr is not None:
            img_hml = fig_to_rl_image(f_hml, width=398, height=220)
            img_hsr = fig_to_rl_image(f_hsr, width=398, height=220)
            t_charts = Table([[img_hml, img_hsr]], colWidths=[404, 404])
            t_charts.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(t_charts)
            elements.append(Spacer(1, 6))

        r_df = target_day_bundle.get("role_df", pd.DataFrame())
        d_df = target_day_bundle.get("dept_df", pd.DataFrame())
        elements.append(_build_target_role_dept_rl_table(r_df, d_df, is_day=True))

    def _add_page_settimana_23():
        if not settimana_23_bundle or settimana_23_bundle.get("df_23") is None:
            return
        df_23 = settimana_23_bundle["df_23"]
        m_info = settimana_23_bundle.get("match_info", {})
        m_name = m_info.get("match_name", meta.get("session_name", "Gara"))
        m_date = m_info.get("date_str", meta.get("date_str", ""))

        # Foglio 1: Dati individuali dei 23 Convocati e Medie Ruolo
        elements.append(
            _build_fir_header_table(
                "Report Settimana",
                "Dati individuali — 23 Convocati",
                f"{m_name} • {meta.get('week_name', 'Raduno')}",
                f"Periodo: {meta.get('week_period_disp', '')} • Gara: {m_date}",
                "Green: > +15% rispetto alla media del ruolo  •  Red: < -15% rispetto alla media del ruolo",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        role_means = settimana_23_bundle.get("role_means_dict", {})
        elements.append(_build_settimana_23_rl_table(df_23, role_means))
        elements.append(Spacer(1, 4))
        r_df = settimana_23_bundle.get("role_df", pd.DataFrame())
        d_df = settimana_23_bundle.get("dept_df", pd.DataFrame())
        elements.append(_build_target_role_dept_rl_table(r_df, d_df, is_day=False))

        # Foglio 2: Grafici % Match 80' Individuali dei 23 Convocati e Box KPI Riassuntivi
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                "Report Settimana",
                "RAGGIUNGIMENTO MEDIA MATCH 80' INDIVIDUALE (HML & HSR 18\\20) — 23 CONVOCATI",
                f"{m_name} • {meta.get('week_name', 'Raduno')}",
                f"Periodo: {meta.get('week_period_disp', '')} • Gara: {m_date}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        f_hml = settimana_23_bundle.get("fig_hml_23")
        f_hsr = settimana_23_bundle.get("fig_hsr_23")
        if f_hml is not None:
            elements.append(fig_to_rl_image(f_hml, width=808, height=155))
            elements.append(Spacer(1, 3))
        if f_hsr is not None:
            elements.append(fig_to_rl_image(f_hsr, width=808, height=155))
            elements.append(Spacer(1, 4))

        kpis = settimana_23_bundle.get("kpis", {})
        elements.append(_build_settimana_23_kpi_rl_table(kpis))

    def _add_page_densita_gara():
        df_d = densita_bundle.get("df") if densita_bundle and "df" in densita_bundle else (sess_bundle.get("df") if sess_bundle else None)
        if df_d is None or df_d.empty:
            df_d = week_bundle.get("df") if week_bundle else pd.DataFrame()
        elements.append(
            _build_fir_header_table(
                "Report Densità da Gara",
                "Work Rate al Minuto — HML/min & HSR/min vs Benchmark Match 80'",
                meta.get("session_name", meta.get("week_name", "Seduta")),
                f"Data: {meta.get('date_disp', meta.get('date_str', ''))} • Benchmark: Ritmo Gara (80')",
                "Green: >= 90% Ritmo Match  •  Yellow: 75-89%  •  Red: < 75%",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_densita_individual_rl_table(df_d))

    def _add_page_semaforo_vmax():
        nonlocal semaforo_bundle
        if semaforo_bundle is None or "df" not in semaforo_bundle or "kpis" not in semaforo_bundle:
            try:
                import views.report_comparazione
                p_df = utils.get_players_df()
                h_df = utils.get_gps_history_df("all")
                t_map = utils.get_fir_session_types()
                df_f = views.report_comparazione._prepare_fir_data_with_metrics(h_df, p_df, t_map)
                cp_all = utils.get_camp_players_df()
                camps_all = utils.get_camps_df()
                cur_w_name = str(meta.get("week_name") or "")
                matching_camps = camps_all[camps_all["name"] == cur_w_name] if not camps_all.empty and "name" in camps_all.columns else pd.DataFrame()
                cp_for_w = pd.DataFrame()
                if not matching_camps.empty and not cp_all.empty:
                    cid = matching_camps.iloc[0]["id"]
                    cp_for_w = cp_all[cp_all["camp_id"] == cid]
                semaforo_bundle = views.report_comparazione.build_semaforo_vmax_bundle(
                    df_fir=df_f,
                    players_df=p_df,
                    meta=meta,
                    camp_players=cp_for_w,
                    scope_mode="raduno",
                    src_mode="all",
                    dept_f="Tutti",
                )
            except Exception:
                pass

        df_v = semaforo_bundle.get("df", pd.DataFrame()) if semaforo_bundle else pd.DataFrame()
        kpis = semaforo_bundle.get("kpis", {}) if semaforo_bundle else {}
        fig = semaforo_bundle.get("fig") if semaforo_bundle else None
        ref_date = str(meta.get("date_str", ""))[:10]
        w_period = meta.get("week_period_disp", "")
        w_name = meta.get("week_name", "Raduno")

        n_green = kpis.get("n_green", 0)
        n_yellow = kpis.get("n_yellow", 0)
        n_red = kpis.get("n_red", 0)
        pct_green = kpis.get("pct_green", 0.0)
        avg_wpct = kpis.get("avg_wpct", 0.0)

        # FOGLIO 1: Dashboard Sintetica (Header FIR + 4 Card KPI + Grafico a barre & target 85/90%)
        elements.append(
            _build_fir_header_table(
                "Semaforo Esposizione Alta Velocità",
                "Monitoraggio Vmax e % Vmax (Soglie 85% e 90%) — Prevenzione Hamstring",
                f"RADUNO: {w_name}",
                f"Periodo: {w_period} • Riferimento: {ref_date}",
                f"Coperti (≥85%): {n_green} ({pct_green:.0f}%) • Da Richiamare: {n_yellow} • Scoperti: {n_red} • Picco Medio: {avg_wpct:.1f}%",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_semaforo_kpi_rl_table(kpis))
        elements.append(Spacer(1, 6))

        if fig is not None:
            elements.append(fig_to_rl_image(fig, width=808, height=360))
            # FOGLIO 2: Tabella Analitica Dettagliata (9 Colonne conformi al portale)
            elements.append(PageBreak())
            elements.append(
                _build_fir_header_table(
                    "Semaforo Esposizione Alta Velocità — Dettaglio Atleti",
                    "Monitoraggio Individuale Vmax, Picchi e Ultima Esposizione ad Alta Velocità",
                    f"RADUNO: {w_name}",
                    f"Periodo: {w_period} • Riferimento: {ref_date}",
                    "Green: ≤7gg (Coperto)  •  Yellow: 8–14gg (Richiamo)  •  Red: >14gg (Scoperto / Mai)",
                    total_width=808,
                )
            )
            elements.append(Spacer(1, 4))
            elements.append(_build_semaforo_vmax_rl_table(df_v))
        else:
            elements.append(Spacer(1, 4))
            elements.append(_build_semaforo_vmax_rl_table(df_v))

    def _add_page_confronto_settimane():
        if not confronto_settimane_bundle or not confronto_settimane_bundle.get("wk_a"):
            return
        wk_a = confronto_settimane_bundle["wk_a"]
        wk_b = confronto_settimane_bundle["wk_b"]
        sum_df = confronto_settimane_bundle.get("summary_df", pd.DataFrame())
        f_h = confronto_settimane_bundle.get("fig_h")
        f_s = confronto_settimane_bundle.get("fig_s")
        merged_p = confronto_settimane_bundle.get("merged_p", pd.DataFrame())

        # Foglio 1: Sintesi di Squadra e Reparto + Grafici per Ruolo
        elements.append(
            _build_fir_header_table(
                "Confronto Settimane di Raduno",
                f"{wk_a['short']} vs {wk_b['short']}",
                "CONFRONTO DIRETTO MICROCICLI RADUNO",
                f"Settimana A: {wk_a['mon']} → {wk_a['sun']}  •  Settimana B: {wk_b['mon']} → {wk_b['sun']}",
                total_width=808,
            )
        )
        elements.append(Spacer(1, 4))
        elements.append(_build_confronto_settimane_summary_rl_table(sum_df, wk_a["short"], wk_b["short"]))
        elements.append(Spacer(1, 6))

        if f_h is not None and f_s is not None:
            img_h = fig_to_rl_image(f_h, width=398, height=180)
            img_s = fig_to_rl_image(f_s, width=398, height=180)
            t_charts = Table([[img_h, img_s]], colWidths=[404, 404])
            t_charts.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            elements.append(t_charts)

        # Foglio 2: Dettaglio Atleti Presenti in Entrambi i Raduni
        if not merged_p.empty:
            elements.append(PageBreak())
            elements.append(
                _build_fir_header_table(
                    "Confronto Settimane di Raduno",
                    f"Dati Individuali Atleti Presenti in Entrambi i Raduni ({len(merged_p)} atleti)",
                    f"{wk_a['short']} vs {wk_b['short']}",
                    f"Periodo: {wk_a['mon']} vs {wk_b['mon']}",
                    total_width=808,
                )
            )
            elements.append(Spacer(1, 4))
            elements.append(_build_confronto_settimane_players_rl_table(merged_p, wk_a["short"], wk_b["short"]))

    s_key = str(sottoarea or "").strip().lower()
    if "scheda_giocatori" in s_key or "scheda giocatori" in s_key or "giocatori_neutr" in s_key:
        _add_page_scheda_giocatori()
    elif "target_sess" in s_key or ("target" in s_key and "sess" in s_key):
        _add_page_target_sessione()
    elif "target_giorn" in s_key or ("target" in s_key and "giorn" in s_key):
        _add_page_target_giornata()
    elif "settimana_23" in s_key or "convocati" in s_key or "23" in s_key:
        _add_page_settimana_23()
    elif "densita" in s_key:
        _add_page_densita_gara()
    elif "semaforo" in s_key or "vmax" in s_key:
        _add_page_semaforo_vmax()
    elif "confronto_settimane" in s_key or "settimane" in s_key or "raduni" in s_key or "raduno" in s_key:
        _add_page_confronto_settimane()
    elif "sess" in s_key and "isto" not in s_key and "comp" not in s_key and "mult" not in s_key:
        _add_page_sessione()
    elif "isto" in s_key:
        _add_page_istogramma()
    elif "generale" in s_key or "story" in s_key or "collettiv" in s_key:
        _add_page_report_generale()
    elif "schieramento" in s_key or "campo" in s_key:
        _add_page_schieramento()
    elif "giorn" in s_key:
        _add_page_giornata()
    elif "tutte_settimana" in s_key:
        _add_page_settimana()
        elements.append(PageBreak())
        _add_page_settimana_23()
        elements.append(PageBreak())
        _add_page_semaforo_vmax()
    elif "sett" in s_key:
        _add_page_settimana()
    elif "multisess" in s_key or "multi" in s_key:
        _add_page_confronto_multisessione()
    elif "tipolog" in s_key or "tipo" in s_key or "bench" in s_key:
        _add_page_medie_tipologie_fir()
    elif "confronto" in s_key or "comparaz" in s_key:
        _add_page_medie_tipologie_fir()
        elements.append(PageBreak())
        _add_page_confronto_multisessione()
        if confronto_settimane_bundle and confronto_settimane_bundle.get("wk_a"):
            elements.append(PageBreak())
            _add_page_confronto_settimane()
    else:
        # TUTTE LE PAGINE (Pacchetto Completo con tutte le analisi in formato Orizzontale Landscape)
        _add_page_sessione()
        elements.append(PageBreak())
        _add_page_istogramma()
        elements.append(PageBreak())
        _add_page_report_generale()
        elements.append(PageBreak())
        _add_page_schieramento()
        elements.append(PageBreak())
        _add_page_densita_gara()
        elements.append(PageBreak())
        _add_page_giornata()
        elements.append(PageBreak())
        _add_page_settimana()
        elements.append(PageBreak())
        _add_page_confronto_multisessione()
        elements.append(PageBreak())
        _add_page_medie_tipologie_fir()
        elements.append(PageBreak())
        _add_page_target_sessione()
        elements.append(PageBreak())
        _add_page_target_giornata()
        elements.append(PageBreak())
        _add_page_settimana_23()
        elements.append(PageBreak())
        _add_page_semaforo_vmax()
        if confronto_settimane_bundle and confronto_settimane_bundle.get("wk_a"):
            elements.append(PageBreak())
            _add_page_confronto_settimane()

    _build_pdf_with_footer(doc, elements)
    return buffer.getvalue()


def crea_pdf_report_gin(
    sub_code: str,
    rep_df: pd.DataFrame,
    weeks_meta: list,
    last_round_df: pd.DataFrame,
    rep_meta: dict,
    sort_mode: str = "minuti",
) -> bytes:
    """
    Genera il report PDF ufficiale FIR A4 Orizzontale per il Report 6/12 Settimane G.I.N. (Oval Match):
    - 'completo': Tabella 6/12 Settimane G.I.N. + Tabella Ultima Giornata
    - 'tabella_gin': Solo Tabella 6/12 Settimane G.I.N.
    - 'ultima_giornata': Solo Tabella Ultima Giornata
    """
    buffer = BytesIO()
    pagesize = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        rightMargin=14,
        leftMargin=14,
        topMargin=12,
        bottomMargin=18,
    )
    elements = []
    sub_key = str(sub_code or "").strip().lower()

    ordinamento_map = {
        "minuti": "Ranking Minuti Stagionali (1 Ago – 30 Lug)",
        "ruoli": "Ordine per Ruolo Ufficiale FIR (Piloni → Ali/Estremo)",
        "min_6w": "Ranking Minuti 6 WEEKS",
    }
    ord_lbl = ordinamento_map.get(sort_mode, sort_mode)

    # 1. HEADER REPORT GIN
    def _build_gin_pdf_header(title: str, subtitle: str):
        b64_has_logo = os.path.exists(LOGO_PATH)
        logo_cell = RLImage(LOGO_PATH, width=28, height=36) if b64_has_logo else Paragraph("<b>FIR</b>", getSampleStyleSheet()["Normal"])

        t_style = ParagraphStyle(
            "GINHeaderTitle",
            fontName="Helvetica-Bold",
            fontSize=9.5,
            leading=11.5,
            textColor=colors.HexColor("#002B49"),
        )
        r_style = ParagraphStyle(
            "GINHeaderRight",
            fontName="Helvetica",
            fontSize=6.5,
            leading=8.2,
            alignment=2,
            textColor=colors.HexColor("#334155"),
        )

        left_p = Paragraph(f"<b>FEDERAZIONE ITALIANA RUGBY</b><br/><font color='#0066B2'>{title.upper()}</font><br/><font color='#64748B' size='6.2'>{subtitle}</font>", t_style)
        right_p = Paragraph(
            f"<b>Stagione:</b> {rep_meta.get('season_label', '')}<br/>"
            f"<b>Settimana Rif.:</b> {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']}<br/>"
            f"<b>Ordinamento:</b> {ord_lbl} • <b>Atleti:</b> {len(rep_df)}",
            r_style,
        )
        h_table = Table([[logo_cell, left_p, right_p]], colWidths=[36, 450, 326])
        h_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 1.2, colors.HexColor("#0066B2")),
        ]))
        return h_table

    # Build 6/12 Settimane Table helper
    def _build_gin_rl_table(df_subset: pd.DataFrame, is_compact: bool = False) -> Table:
        show_opta = sort_mode == "ruoli"
        n_rows = len(df_subset)
        auto_compact = is_compact or (n_rows > 42)

        r0 = [f"Settimana analizzata: {rep_meta.get('ref_monday_disp', '')} — {rep_meta.get('ref_next_monday_disp', '')}"]
        left_cols_cnt = 3 if show_opta else 2
        for _ in range(left_cols_cnt - 1):
            r0.append("")
        for _ in range(12):
            r0.append("12 WEEKS (MINUTI GIOCATI • BORDO ROSSO = TITOLARE)")
        r0.extend([f"STAGIONE {rep_meta.get('season_label', '')}", ""])
        r0.extend(["6 WEEKS", "", "", "", ""])

        r1 = ["NOME", "CODICE", "RUOLO"] if show_opta else ["NOME", "RUOLO"]
        for w_pos, wm in enumerate(weeks_meta):
            if w_pos < 6:
                r1.append(f"{wm['label']}\n{wm['start_disp'][:5]}-{wm['end_disp'][:5]}")
            else:
                w_short = wm["label"].replace("WEEK-", "W-")
                r1.append(f"{w_short}\n{wm['start_disp'][:5]}")
        r1.extend(["CAPS", "MINUTI", "CAPS", "MINUTI", "TITOL.\n6W", "MAX\n6W", "TOT\n12W"])

        data_rows = [r0, r1]

        f_size_h0 = 5.2 if auto_compact else 6.2
        leading_h0 = 6.0 if auto_compact else 7.5
        f_size_h1 = 4.7 if auto_compact else 5.6
        leading_h1 = 5.4 if auto_compact else 6.8

        f_size_row = 4.6 if auto_compact else 5.8
        leading_row = 5.3 if auto_compact else 7.0
        pad_top = 0.3 if auto_compact else 1.3
        pad_bot = 0.3 if auto_compact else 1.3

        w0_idx = left_cols_cnt
        w5_idx = left_cols_cnt + 5
        w11_idx = left_cols_cnt + 11
        s_caps_idx = w11_idx + 1
        s_min_idx = w11_idx + 2
        w6_start_idx = s_min_idx + 1
        w6_end_idx = w6_start_idx + 4

        cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), f_size_h0),
            ("LEADING", (0, 0), (-1, 0), leading_h0),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), f_size_h1),
            ("LEADING", (0, 1), (-1, 1), leading_h1),
            ("ALIGN", (0, 0), (-1, 1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), pad_top),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad_bot),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),

            # Spans for Row 0
            ("SPAN", (0, 0), (left_cols_cnt - 1, 0)),
            ("SPAN", (w0_idx, 0), (w11_idx, 0)),
            ("SPAN", (s_caps_idx, 0), (s_min_idx, 0)),
            ("SPAN", (w6_start_idx, 0), (w6_end_idx, 0)),

            # Colors for Row 0
            ("BACKGROUND", (0, 0), (left_cols_cnt - 1, 0), colors.HexColor("#EFF6FF")),
            ("TEXTCOLOR", (0, 0), (left_cols_cnt - 1, 0), colors.HexColor("#1E3A8A")),
            ("BACKGROUND", (w0_idx, 0), (w11_idx, 0), colors.HexColor("#064E3B")),
            ("TEXTCOLOR", (w0_idx, 0), (w11_idx, 0), colors.HexColor("#FFFFFF")),
            ("BACKGROUND", (s_caps_idx, 0), (s_min_idx, 0), colors.HexColor("#FFF1F2")),
            ("TEXTCOLOR", (s_caps_idx, 0), (s_min_idx, 0), colors.HexColor("#9F1239")),
            ("BACKGROUND", (w6_start_idx, 0), (w6_end_idx, 0), colors.HexColor("#FEF2F2")),
            ("TEXTCOLOR", (w6_start_idx, 0), (w6_end_idx, 0), colors.HexColor("#B91C1C")),

            # Row 1 headers
            ("BACKGROUND", (0, 1), (left_cols_cnt - 1, 1), colors.HexColor("#F8FAFC")),
            ("TEXTCOLOR", (0, 1), (left_cols_cnt - 1, 1), colors.HexColor("#334155")),
            # Ultime 6 settimane (W0..W5): verde smeraldo brillante
            ("BACKGROUND", (w0_idx, 1), (w5_idx, 1), colors.HexColor("#ECFDF5")),
            ("TEXTCOLOR", (w0_idx, 1), (w5_idx, 1), colors.HexColor("#065F46")),
            # Settimane precedenti (W6..W11): slate delicato
            ("BACKGROUND", (w5_idx + 1, 1), (w11_idx, 1), colors.HexColor("#F1F5F9")),
            ("TEXTCOLOR", (w5_idx + 1, 1), (w11_idx, 1), colors.HexColor("#475569")),
            # Summary headers
            ("BACKGROUND", (s_caps_idx, 1), (s_min_idx, 1), colors.HexColor("#FFF1F2")),
            ("TEXTCOLOR", (s_caps_idx, 1), (s_min_idx, 1), colors.HexColor("#9F1239")),
            ("BACKGROUND", (w6_start_idx, 1), (w6_end_idx, 1), colors.HexColor("#FFF5F5")),
            ("TEXTCOLOR", (w6_start_idx, 1), (w6_end_idx, 1), colors.HexColor("#991B1B")),

            # Linee verticali divisorie identiche al portale
            ("LINEAFTER", (left_cols_cnt - 1, 0), (left_cols_cnt - 1, -1), 1.5, colors.HexColor("#047857")),
            ("LINEAFTER", (w5_idx, 0), (w5_idx, -1), 1.3, colors.HexColor("#10B981")), # divisore 6 settimane
            ("LINEAFTER", (w11_idx, 0), (w11_idx, -1), 1.5, colors.HexColor("#BE123C")), # fine 12 settimane
            ("LINEAFTER", (s_min_idx, 0), (s_min_idx, -1), 1.5, colors.HexColor("#B91C1C")), # fine stagione
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#002B49")),
        ]

        prev_role = None
        for idx, row in df_subset.iterrows():
            r_idx = len(data_rows)
            p_name = str(row.get("player_name", ""))[:24]
            opta_disp = str(row.get("opta_id", ""))[:10]
            role_disp = str(row.get("role", ""))[:18]

            bg_tr = "#FFFFFF" if r_idx % 2 == 0 else "#F8FAFC"
            cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor(bg_tr)))

            if show_opta and prev_role is not None and role_disp != prev_role:
                cmds.append(("LINEABOVE", (0, r_idx), (-1, r_idx), 1.1, colors.HexColor("#0284C7")))
            prev_role = role_disp

            curr_row = [p_name, opta_disp, role_disp] if show_opta else [p_name, role_disp]

            # 12 weeks (supporta sia liste w_mins/w_starters sia colonne w_0..w_11)
            w_mins_list = row.get("w_mins") if isinstance(row.get("w_mins"), (list, tuple)) else None
            w_starts_list = row.get("w_starters") if isinstance(row.get("w_starters"), (list, tuple)) else None

            for w_pos, wm in enumerate(weeks_meta):
                w_idx_num = wm.get("idx", w_pos)
                if w_mins_list is not None and w_idx_num < len(w_mins_list):
                    m_val = int(float(w_mins_list[w_idx_num] or 0))
                    is_st = bool(w_starts_list[w_idx_num]) if (w_starts_list is not None and w_idx_num < len(w_starts_list)) else False
                else:
                    w_val = row.get(f"w_{w_idx_num}")
                    if isinstance(w_val, dict):
                        m_val = int(w_val.get("minutes", 0))
                        is_st = bool(w_val.get("starter", False))
                    else:
                        try:
                            m_val = int(float(w_val or 0))
                        except Exception:
                            m_val = 0
                        is_st = False

                col_pos = len(curr_row)
                if m_val > 0:
                    curr_row.append(str(m_val))
                    if is_st:
                        cmds.append(("BACKGROUND", (col_pos, r_idx), (col_pos, r_idx), colors.HexColor("#FFE4E6")))
                        cmds.append(("TEXTCOLOR", (col_pos, r_idx), (col_pos, r_idx), colors.HexColor("#991B1B")))
                        cmds.append(("FONTNAME", (col_pos, r_idx), (col_pos, r_idx), "Helvetica-Bold"))
                        cmds.append(("BOX", (col_pos, r_idx), (col_pos, r_idx), 0.9, colors.HexColor("#EF4444")))
                    else:
                        cmds.append(("BACKGROUND", (col_pos, r_idx), (col_pos, r_idx), colors.HexColor("#E0F2FE")))
                        cmds.append(("TEXTCOLOR", (col_pos, r_idx), (col_pos, r_idx), colors.HexColor("#0369A1")))
                        cmds.append(("FONTNAME", (col_pos, r_idx), (col_pos, r_idx), "Helvetica-Bold"))
                        cmds.append(("BOX", (col_pos, r_idx), (col_pos, r_idx), 0.6, colors.HexColor("#38BDF8")))
                else:
                    curr_row.append("0")
                    cmds.append(("TEXTCOLOR", (col_pos, r_idx), (col_pos, r_idx), colors.HexColor("#CBD5E1")))

            # Stagione Caps & Minuti
            try:
                s_caps_i = int(float(row.get("season_caps", 0) or 0))
                s_min_i = int(float(row.get("season_min", 0) or 0))
            except Exception:
                s_caps_i, s_min_i = 0, 0
            curr_row.extend([str(s_caps_i), str(s_min_i)])
            col_sc = len(curr_row) - 2
            col_sm = len(curr_row) - 1
            cmds.append(("FONTNAME", (col_sc, r_idx), (col_sc, r_idx), "Helvetica-Bold"))
            if s_min_i > 0:
                cmds.append(("FONTNAME", (col_sm, r_idx), (col_sm, r_idx), "Helvetica-Bold"))
                cmds.append(("BACKGROUND", (col_sm, r_idx), (col_sm, r_idx), colors.HexColor("#FFE4E6")))
                cmds.append(("TEXTCOLOR", (col_sm, r_idx), (col_sm, r_idx), colors.HexColor("#881337")))

            # 6 Weeks
            try:
                c6_num = int(float(row.get("caps_6w", 0) or 0))
            except Exception:
                c6_num = 0
            try:
                m6_num = int(float(row.get("min_6w", 0) or 0))
            except Exception:
                m6_num = 0

            cs_raw = str(row.get("consec_starts_6w", "/")).strip()
            cs_num = int(cs_raw) if cs_raw.isdigit() else 0
            cs_str = cs_raw if cs_raw else "/"

            try:
                mc_num = int(float(row.get("max_consec_6w", 0) or 0))
            except Exception:
                mc_num = 0
            try:
                t12_num = int(float(row.get("tot_12w", 0) or 0))
            except Exception:
                t12_num = 0

            curr_row.extend([str(c6_num), str(m6_num), cs_str, str(mc_num), str(t12_num)])

            col_c6 = len(curr_row) - 5
            col_m6 = len(curr_row) - 4
            col_cs = len(curr_row) - 3
            col_mc = len(curr_row) - 2
            col_t12 = len(curr_row) - 1

            if c6_num > 0:
                cmds.append(("BACKGROUND", (col_c6, r_idx), (col_c6, r_idx), colors.HexColor("#E0F2FE")))
                cmds.append(("FONTNAME", (col_c6, r_idx), (col_c6, r_idx), "Helvetica-Bold"))
            if m6_num > 0:
                cmds.append(("BACKGROUND", (col_m6, r_idx), (col_m6, r_idx), colors.HexColor("#DCFCE7")))
                cmds.append(("TEXTCOLOR", (col_m6, r_idx), (col_m6, r_idx), colors.HexColor("#166534")))
                cmds.append(("FONTNAME", (col_m6, r_idx), (col_m6, r_idx), "Helvetica-Bold"))
            if cs_num >= 4:
                cmds.append(("BACKGROUND", (col_cs, r_idx), (col_cs, r_idx), colors.HexColor("#FEF08A")))
                cmds.append(("TEXTCOLOR", (col_cs, r_idx), (col_cs, r_idx), colors.HexColor("#854D0E")))
                cmds.append(("FONTNAME", (col_cs, r_idx), (col_cs, r_idx), "Helvetica-Bold"))
            if mc_num >= 5:
                cmds.append(("BACKGROUND", (col_mc, r_idx), (col_mc, r_idx), colors.HexColor("#FEF08A")))
                cmds.append(("TEXTCOLOR", (col_mc, r_idx), (col_mc, r_idx), colors.HexColor("#854D0E")))
                cmds.append(("FONTNAME", (col_mc, r_idx), (col_mc, r_idx), "Helvetica-Bold"))
            cmds.append(("TEXTCOLOR", (col_t12, r_idx), (col_t12, r_idx), colors.HexColor("#0369A1")))
            cmds.append(("FONTNAME", (col_t12, r_idx), (col_t12, r_idx), "Helvetica-Bold"))

            cmds.append(("FONTSIZE", (0, r_idx), (-1, r_idx), f_size_row))
            cmds.append(("LEADING", (0, r_idx), (-1, r_idx), leading_row))
            cmds.append(("ALIGN", (0, r_idx), (0, r_idx), "LEFT"))
            cmds.append(("FONTNAME", (0, r_idx), (0, r_idx), "Helvetica-Bold"))
            if show_opta:
                cmds.append(("ALIGN", (1, r_idx), (1, r_idx), "CENTER"))
                cmds.append(("TEXTCOLOR", (1, r_idx), (1, r_idx), colors.HexColor("#64748B")))
                cmds.append(("ALIGN", (2, r_idx), (2, r_idx), "CENTER"))
                cmds.append(("TEXTCOLOR", (2, r_idx), (2, r_idx), colors.HexColor("#1E40AF")))
                cmds.append(("FONTNAME", (2, r_idx), (2, r_idx), "Helvetica-Bold"))
                cmds.append(("ALIGN", (3, r_idx), (-1, r_idx), "CENTER"))
            else:
                cmds.append(("ALIGN", (1, r_idx), (1, r_idx), "CENTER"))
                cmds.append(("TEXTCOLOR", (1, r_idx), (1, r_idx), colors.HexColor("#1E40AF")))
                cmds.append(("FONTNAME", (1, r_idx), (1, r_idx), "Helvetica-Bold"))
                cmds.append(("ALIGN", (2, r_idx), (-1, r_idx), "CENTER"))

            data_rows.append(curr_row)

        # Larghezza totale calibrata esattamente ad A4 Landscape (814pt utili)
        # NOME ristretto a 102pt, RUOLO a 56pt. Ultime 6 settimane allargate a 36pt cad., precedenti a 26pt.
        if show_opta:
            col_widths = [86, 32, 48] + [35] * 6 + [25] * 6 + [28, 46, 28, 46, 45, 44, 45]
        else:
            col_widths = [102, 56] + [36] * 6 + [26] * 6 + [28, 46, 28, 46, 46, 44, 46]

        row_heights = None
        if auto_compact and 42 < n_rows <= 76:
            # Garantisce che fino a 76 righe + 2 righe header restino esattamente in 1 singola pagina A4 Landscape
            avail_h = 516.0
            r_h = max(5.6, min(6.7, avail_h / float(n_rows)))
            row_heights = [11.0, 14.0] + [r_h] * n_rows

        tbl = Table(data_rows, colWidths=col_widths, rowHeights=row_heights, repeatRows=2)
        tbl.setStyle(TableStyle(cmds))
        return tbl

    # Build Ultima Giornata Table
    def _add_section_ultima_giornata():
        elements.append(
            _build_gin_pdf_header(
                "DETTAGLIO ULTIMA GIORNATA MATCH (OVAL)",
                f"Presenze e Minutaggio Settimana {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(last_round_df)} presenze)"
            )
        )
        elements.append(Spacer(1, 4))

        if last_round_df.empty:
            elements.append(Paragraph("<i>Nessuna partita disputata registrata nell'ultima settimana selezionata.</i>", getSampleStyleSheet()["Normal"]))
            return

        n_ug = len(last_round_df)
        ug_compact = n_ug > 32
        ug_fsize = 5.5 if ug_compact else 6.3
        ug_lead = 6.4 if ug_compact else 7.5
        ug_pad = 1.1 if ug_compact else 2.2

        ug_headers = ["NOME GIOCATORE", "DATA GARA", "HOME / AWAY", "INCONTRO (PARTITA OVAL)", "PUNTEGGIO", "IMPIEGO IN GARA", "MINUTI"]
        ug_data = [ug_headers]
        ug_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 6.5),
            ("LEADING", (0, 0), (-1, 0), 7.8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), ug_pad),
            ("BOTTOMPADDING", (0, 0), (-1, -1), ug_pad),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
        ]

        for i, row in last_round_df.iterrows():
            r_idx = len(ug_data)
            bg = colors.HexColor("#FFFFFF") if r_idx % 2 == 1 else colors.HexColor("#F8FAFC")
            ug_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), bg))

            p_name = str(row.get("Giocatore") or row.get("NOME") or row.get("player_name", ""))
            d_val = str(row.get("Data") or row.get("match_date", ""))
            ha = str(row.get("Home\\Away") or row.get("home_away", "HOME")).upper()
            game = str(row.get("Match") or row.get("game", ""))
            res = str(row.get("Score") or row.get("result", "")).strip()
            st_raw = str(row.get("Titolare") or "")
            is_st = ("STARTER" in st_raw.upper()) or bool(row.get("is_starter", False))
            st_lbl = "STARTER (Titolare)" if is_st else "FINISHER (Panchina)"
            try:
                m_val = str(int(float(row.get("Minuti") or row.get("minutes", 0))))
            except Exception:
                m_val = "0"

            ug_data.append([p_name, d_val, ha, game, res, st_lbl, f"{m_val}'"])

            ug_cmds.append(("FONTSIZE", (0, r_idx), (-1, r_idx), ug_fsize))
            ug_cmds.append(("LEADING", (0, r_idx), (-1, r_idx), ug_lead))
            ug_cmds.append(("ALIGN", (0, r_idx), (0, r_idx), "LEFT"))
            ug_cmds.append(("FONTNAME", (0, r_idx), (0, r_idx), "Helvetica-Bold"))
            ug_cmds.append(("ALIGN", (1, r_idx), (2, r_idx), "CENTER"))
            ug_cmds.append(("ALIGN", (3, r_idx), (3, r_idx), "LEFT"))
            ug_cmds.append(("ALIGN", (4, r_idx), (-1, r_idx), "CENTER"))
            ug_cmds.append(("FONTNAME", (6, r_idx), (6, r_idx), "Helvetica-Bold"))

            if ha == "HOME":
                ug_cmds.append(("BACKGROUND", (2, r_idx), (2, r_idx), colors.HexColor("#DCFCE7")))
                ug_cmds.append(("TEXTCOLOR", (2, r_idx), (2, r_idx), colors.HexColor("#15803D")))
                ug_cmds.append(("FONTNAME", (2, r_idx), (2, r_idx), "Helvetica-Bold"))
            else:
                ug_cmds.append(("BACKGROUND", (2, r_idx), (2, r_idx), colors.HexColor("#FEE2E2")))
                ug_cmds.append(("TEXTCOLOR", (2, r_idx), (2, r_idx), colors.HexColor("#B91C1C")))
                ug_cmds.append(("FONTNAME", (2, r_idx), (2, r_idx), "Helvetica-Bold"))

            if res.upper().startswith("W"):
                ug_cmds.append(("BACKGROUND", (4, r_idx), (4, r_idx), colors.HexColor("#DCFCE7")))
                ug_cmds.append(("TEXTCOLOR", (4, r_idx), (4, r_idx), colors.HexColor("#15803D")))
                ug_cmds.append(("FONTNAME", (4, r_idx), (4, r_idx), "Helvetica-Bold"))
            elif res.upper().startswith("L"):
                ug_cmds.append(("BACKGROUND", (4, r_idx), (4, r_idx), colors.HexColor("#FEE2E2")))
                ug_cmds.append(("TEXTCOLOR", (4, r_idx), (4, r_idx), colors.HexColor("#B91C1C")))
                ug_cmds.append(("FONTNAME", (4, r_idx), (4, r_idx), "Helvetica-Bold"))

            if is_st:
                ug_cmds.append(("BACKGROUND", (5, r_idx), (5, r_idx), colors.HexColor("#DCFCE7")))
                ug_cmds.append(("TEXTCOLOR", (5, r_idx), (5, r_idx), colors.HexColor("#15803D")))
                ug_cmds.append(("FONTNAME", (5, r_idx), (5, r_idx), "Helvetica-Bold"))
            else:
                ug_cmds.append(("BACKGROUND", (5, r_idx), (5, r_idx), colors.HexColor("#FFEDD5")))
                ug_cmds.append(("TEXTCOLOR", (5, r_idx), (5, r_idx), colors.HexColor("#C2410C")))
                ug_cmds.append(("FONTNAME", (5, r_idx), (5, r_idx), "Helvetica-Bold"))

        col_w = [145, 65, 65, 262, 85, 125, 65]
        tbl_ug = Table(ug_data, colWidths=col_w, repeatRows=1)
        tbl_ug.setStyle(TableStyle(ug_cmds))
        elements.append(tbl_ug)

    def _append_paginated_gin_tables(df_target: pd.DataFrame, header_title: str, header_sub: str, is_compact: bool):
        if df_target.empty:
            elements.append(_build_gin_pdf_header(header_title, header_sub))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph("<i>Nessun atleta trovato con i filtri selezionati.</i>", getSampleStyleSheet()["Normal"]))
            return
        max_per_page = 74 if is_compact else 36
        if len(df_target) <= max_per_page:
            elements.append(_build_gin_pdf_header(header_title, header_sub))
            elements.append(Spacer(1, 3))
            elements.append(_build_gin_rl_table(df_target, is_compact=is_compact))
        else:
            chunks = [df_target.iloc[i : i + max_per_page] for i in range(0, len(df_target), max_per_page)]
            for c_idx, ch_df in enumerate(chunks):
                if c_idx > 0:
                    elements.append(PageBreak())
                sub_p = f"{header_sub} • Pagina {c_idx + 1}/{len(chunks)}"
                elements.append(_build_gin_pdf_header(header_title, sub_p))
                elements.append(Spacer(1, 3))
                elements.append(_build_gin_rl_table(ch_df, is_compact=False))

    # Route based on sub_key and sort_mode
    df_avanti = rep_df[rep_df["department"] == "Avanti"].copy() if "department" in rep_df.columns else pd.DataFrame()
    df_trequarti = rep_df[rep_df["department"] == "TreQuarti"].copy() if "department" in rep_df.columns else pd.DataFrame()

    if "ultima" in sub_key:
        _add_section_ultima_giornata()
    elif "solo_avanti" in sub_key:
        _append_paginated_gin_tables(
            df_avanti if not df_avanti.empty else rep_df,
            "REPORT G.I.N. (OVAL MATCH) — REPARTO AVANTI",
            f"Monitoraggio Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(df_avanti)} atleti)",
            is_compact=False,
        )
    elif "solo_trequarti" in sub_key:
        _append_paginated_gin_tables(
            df_trequarti if not df_trequarti.empty else rep_df,
            "REPORT G.I.N. (OVAL MATCH) — REPARTO TREQUARTI",
            f"Monitoraggio Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(df_trequarti)} atleti)",
            is_compact=False,
        )
    elif "tabella_1pag" in sub_key:
        _append_paginated_gin_tables(
            rep_df,
            "REPORT 6/12 SETTIMANE G.I.N. (OVAL MATCH)",
            f"Ranking Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(rep_df)} atleti)",
            is_compact=True,
        )
    elif "completo_1pag" in sub_key:
        _append_paginated_gin_tables(
            rep_df,
            "REPORT 6/12 SETTIMANE G.I.N. (OVAL MATCH)",
            f"Ranking Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(rep_df)} atleti)",
            is_compact=True,
        )
        if not last_round_df.empty:
            elements.append(PageBreak())
            _add_section_ultima_giornata()
    elif "tabella_gin" in sub_key:
        _append_paginated_gin_tables(
            rep_df,
            "REPORT 6/12 SETTIMANE G.I.N. (OVAL MATCH)",
            f"Ranking Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(rep_df)} atleti)",
            is_compact=False,
        )
    elif "ruoli_split" in sub_key:
        _append_paginated_gin_tables(
            df_avanti if not df_avanti.empty else rep_df,
            "REPORT G.I.N. (OVAL MATCH) — REPARTO AVANTI",
            f"Monitoraggio Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(df_avanti)} atleti)",
            is_compact=False,
        )
        if not df_trequarti.empty:
            elements.append(PageBreak())
            _append_paginated_gin_tables(
                df_trequarti,
                "REPORT G.I.N. (OVAL MATCH) — REPARTO TREQUARTI",
                f"Monitoraggio Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(df_trequarti)} atleti)",
                is_compact=False,
            )
        if not last_round_df.empty:
            elements.append(PageBreak())
            _add_section_ultima_giornata()
    else:
        # Default per Allenatori: Tabella 6/12 Settimane impaginata in modo chiaro e leggibile + Foglio Ultima Giornata
        _append_paginated_gin_tables(
            rep_df,
            "REPORT 6/12 SETTIMANE G.I.N. (OVAL MATCH)",
            f"Ranking Minutaggi Stagionali • Settimana: {weeks_meta[0]['start_disp']} — {weeks_meta[0]['end_disp']} ({len(rep_df)} atleti)",
            is_compact=False,
        )
        if not last_round_df.empty:
            elements.append(PageBreak())
            _add_section_ultima_giornata()

    _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • REPORT G.I.N. OVAL MATCH")
    return buffer.getvalue()


# ==============================================================================
# REPORT 6 WEEKS GPS (CARICHI SETTIMANALI & ACWR) — MOTORE PDF REPORTLAB
# ==============================================================================

def crea_pdf_report_6weeks(
    sub_code: str,
    rep_df: pd.DataFrame,
    weeks_meta: list,
    metric_key: str,
    rep_meta: dict,
    sort_mode: str,
) -> bytes:
    """
    Genera il PDF ufficiale FIR del Report 6 Weeks GPS (A4 Orizzontale)
    Supporta:
    - 'singolo_parametro': Report completo con il parametro attivo + medie ruolo/reparto
    - 'ruoli_split': 2 fogli separati (Foglio 1: Avanti, Foglio 2: TreQuarti)
    - 'completo_federale': Layout multi-parametro stile federale
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=10,
        bottomMargin=12,
    )

    elements = []
    minfo = utils.GPS_6W_METRICS.get(metric_key, utils.GPS_6W_METRICS["DT"])
    is_mx = minfo["is_max"]

    def _build_6w_pdf_header(title_txt: str, sub_txt: str):
        b64_logo = get_logo_base64()
        logo_cell = ""
        if b64_logo:
            try:
                logo_bytes = base64.b64decode(b64_logo)
                img = RLImage(io.BytesIO(logo_bytes), width=24, height=30)
                logo_cell = img
            except Exception:
                logo_cell = ""
        if not logo_cell:
            logo_cell = Paragraph("<b>FIR</b>", ParagraphStyle("FIRLogo", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#002B49")))

        head_p = Paragraph(f"<b>{title_txt}</b>", ParagraphStyle("H1_6W", fontSize=9, fontName="Helvetica-Bold", textColor=colors.HexColor("#002B49"), leading=11))
        sub_p = Paragraph(sub_txt, ParagraphStyle("H2_6W", fontSize=6.5, fontName="Helvetica", textColor=colors.HexColor("#475569"), leading=8))
        date_p = Paragraph(
            f"<b>SETTIMANA WEEK</b><br/><b>{weeks_meta[0]['start_disp']} &mdash; {weeks_meta[0]['end_disp']}</b>",
            ParagraphStyle("D_6W", fontSize=6.5, fontName="Helvetica-Bold", textColor=colors.HexColor("#065F46"), alignment=2, leading=8),
        )

        h_tbl = Table([[logo_cell, [head_p, sub_p], date_p]], colWidths=[32, 600, 180])
        h_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("PADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return h_tbl

    def _build_metric_table_for_df(df_subset: pd.DataFrame, m_k: str, is_compact: bool = False):
        if df_subset.empty:
            return Paragraph("Nessun dato disponibile.", ParagraphStyle("Empty", fontSize=8))

        m_info_local = utils.GPS_6W_METRICS.get(m_k, utils.GPS_6W_METRICS["DT"])
        is_mx_loc = m_info_local["is_max"]
        f_size = 4.8 if is_compact else 5.8
        leading = 5.6 if is_compact else 6.8
        pad_v = 0.4 if is_compact else 1.2

        th_s = ParagraphStyle("TH_6w", fontName="Helvetica-Bold", fontSize=f_size + 0.5, leading=leading, alignment=1, textColor=colors.white)
        th_date_s = ParagraphStyle("THD_6w", fontName="Helvetica", fontSize=f_size - 0.5, leading=leading - 1, alignment=1, textColor=colors.HexColor("#065F46"))
        td_s = ParagraphStyle("TD_6w", fontName="Helvetica", fontSize=f_size, leading=leading, textColor=colors.HexColor("#0F172A"))
        td_bold_s = ParagraphStyle("TDB_6w", fontName="Helvetica-Bold", fontSize=f_size, leading=leading, textColor=colors.HexColor("#0F172A"))
        td_c_s = ParagraphStyle("TDC_6w", fontName="Helvetica", fontSize=f_size, leading=leading, alignment=1, textColor=colors.HexColor("#0F172A"))
        td_cb_s = ParagraphStyle("TDCB_6w", fontName="Helvetica-Bold", fontSize=f_size, leading=leading, alignment=1, textColor=colors.HexColor("#0F172A"))

        # Row 0: Top headers
        h_row0 = [
            Paragraph("<b>GIOCATORE</b>", th_s),
            Paragraph("<b>RUOLO</b>", th_s),
            Paragraph("<b>CLUB</b>", th_s),
            Paragraph("<b>ANNO</b>", th_s),
        ]
        for wm in weeks_meta:
            h_row0.append(Paragraph(f"<b>{wm['label']}</b>", th_s))
        h_row0.extend([
            Paragraph("<b>ACUTO (7G)</b>", th_s),
            Paragraph("<b>CRONICO (28G)</b>", th_s),
            Paragraph("<b>ACWR</b>", th_s),
        ])

        # Row 1: Dates
        h_row1 = [
            "", "", "", "",
            Paragraph(f"{weeks_meta[0]['start_disp']}<br/>{weeks_meta[0]['end_disp']}", th_date_s),
            Paragraph(f"{weeks_meta[1]['start_disp']}<br/>{weeks_meta[1]['end_disp']}", th_date_s),
            Paragraph(f"{weeks_meta[2]['start_disp']}<br/>{weeks_meta[2]['end_disp']}", th_date_s),
            Paragraph(f"{weeks_meta[3]['start_disp']}<br/>{weeks_meta[3]['end_disp']}", th_date_s),
            Paragraph(f"{weeks_meta[4]['start_disp']}<br/>{weeks_meta[4]['end_disp']}", th_date_s),
            Paragraph(f"{weeks_meta[5]['start_disp']}<br/>{weeks_meta[5]['end_disp']}", th_date_s),
            "", "", "",
        ]

        data_rows = [h_row0, h_row1]
        cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#064E3B")),
            ("BACKGROUND", (0, 1), (3, 1), colors.HexColor("#002B49")),
            ("BACKGROUND", (4, 1), (9, 1), colors.HexColor("#ECFDF5")),
            ("BACKGROUND", (10, 0), (-1, 1), colors.HexColor("#1E3A8A")),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (1, 1)),
            ("SPAN", (2, 0), (2, 1)),
            ("SPAN", (3, 0), (3, 1)),
            ("SPAN", (10, 0), (10, 1)),
            ("SPAN", (11, 0), (11, 1)),
            ("SPAN", (12, 0), (12, 1)),
            ("ALIGN", (0, 0), (2, -1), "LEFT"),
            ("ALIGN", (3, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), pad_v),
            ("BOTTOMPADDING", (0, 0), (-1, -1), pad_v),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("LINEAFTER", (3, 0), (3, -1), 1.2, colors.HexColor("#047857")),
            ("LINEAFTER", (9, 0), (9, -1), 1.2, colors.HexColor("#0066B2")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
        ]

        for _, r in df_subset.iterrows():
            r_idx = len(data_rows)
            m_item = r["metrics"][m_k]
            w_vals = m_item["w_vals"]
            acute = m_item["acute"]
            chronic = m_item["chronic"]
            acwr = m_item["acwr"]

            row_cells = [
                Paragraph(f"<b>{r['player_name']}</b>", td_bold_s),
                Paragraph(r["role"], td_s),
                Paragraph(r["club"], td_s),
                Paragraph(str(r["birth_year"]), td_c_s),
            ]

            for w_i in range(6):
                val = w_vals[w_i]
                if is_mx_loc:
                    val_str = f"{val:.1f}".replace(".", ",") if val > 0 else "0"
                else:
                    val_str = f"{int(round(val)):,}".replace(",", ".") if val > 0 else "0"
                row_cells.append(Paragraph(val_str, td_cb_s if w_i == 0 else td_c_s))

            acute_str = f"{acute:.1f}".replace(".", ",") if is_mx_loc else f"{int(round(acute)):,}".replace(",", ".")
            chron_str = f"{chronic:.1f}".replace(".", ",") if is_mx_loc else f"{int(round(chronic)):,}".replace(",", ".")
            acwr_str = f"{acwr:.1f}".replace(".", ",") if acwr > 0 else "/"

            row_cells.extend([
                Paragraph(f"<b>{acute_str}</b>", td_cb_s),
                Paragraph(chron_str, td_c_s),
                Paragraph(f"<b>{acwr_str}</b>", td_cb_s),
            ])
            data_rows.append(row_cells)

            # Cell styling
            if w_vals[0] > 0:
                cmds.append(("BACKGROUND", (4, r_idx), (4, r_idx), colors.HexColor("#DCFCE7")))
            if acwr > 0:
                if 0.80 <= acwr <= 1.30:
                    cmds.append(("BACKGROUND", (12, r_idx), (12, r_idx), colors.HexColor("#DCFCE7")))
                    cmds.append(("TEXTCOLOR", (12, r_idx), (12, r_idx), colors.HexColor("#166534")))
                elif acwr > 1.50:
                    cmds.append(("BACKGROUND", (12, r_idx), (12, r_idx), colors.HexColor("#FEE2E2")))
                    cmds.append(("TEXTCOLOR", (12, r_idx), (12, r_idx), colors.HexColor("#991B1B")))
                elif acwr > 1.30:
                    cmds.append(("BACKGROUND", (12, r_idx), (12, r_idx), colors.HexColor("#FFEDD5")))

        col_w = [115, 65, 75, 28, 50, 50, 50, 50, 50, 50, 55, 55, 45]
        t = Table(data_rows, colWidths=col_w)
        t.setStyle(TableStyle(cmds))
        return t

    # Sub-code routing
    sub_key = str(sub_code).lower()
    df_avanti = rep_df[rep_df["department"] == "Avanti"].copy()
    df_trequarti = rep_df[rep_df["department"] == "TreQuarti"].copy()

    if "ruoli_split" in sub_key:
        # Foglio 1: Avanti
        elements.append(_build_6w_pdf_header(f"REPORT 6 WEEKS GPS: {minfo['name'].upper()} &mdash; AVANTI", f"Carichi Settimanali & ACWR • {len(df_avanti)} atleti"))
        elements.append(Spacer(1, 3))
        elements.append(_build_metric_table_for_df(df_avanti, metric_key, is_compact=False))
        if not df_trequarti.empty:
            elements.append(PageBreak())
            elements.append(_build_6w_pdf_header(f"REPORT 6 WEEKS GPS: {minfo['name'].upper()} &mdash; TREQUARTI", f"Carichi Settimanali & ACWR • {len(df_trequarti)} atleti"))
            elements.append(Spacer(1, 3))
            elements.append(_build_metric_table_for_df(df_trequarti, metric_key, is_compact=False))
    elif "completo_federale" in sub_key:
        # Multi-parametro federale: include TUTTI i 6 parametri analizzati (DT, HML, HSR18, HSR20, HSR25, Vmax)
        all_metrics_order = [
            ("DT", "REPORT 6 WEEKS GPS: DISTANZA TOTALE (DT)", "Volume Totale Settimanale (m) & ACWR (Carico Acuto 7g / Cronico 28g)"),
            ("HML", "REPORT 6 WEEKS GPS: HIGH METABOLIC LOAD (>25.5W)", "Metri ad Alta Potenza Metabolica & ACWR"),
            ("HSR_18", "REPORT 6 WEEKS GPS: HIGH SPEED RUNNING (>18 KM/H)", "Corsa ad Alta Velocità >18 km/h & ACWR (Specifico Avanti)"),
            ("HSR_20", "REPORT 6 WEEKS GPS: HIGH SPEED RUNNING (>20 KM/H)", "Corsa ad Alta Velocità >20 km/h & ACWR (Specifico Trequarti)"),
            ("HSR_25", "REPORT 6 WEEKS GPS: VERY HIGH SPEED RUNNING (>25 KM/H)", "Metri ad Altissima Velocità / Sprint & ACWR"),
            ("VMAX", "REPORT 6 WEEKS GPS: PICCO VELOCITÀ MASSIMA (V MAX)", "Velocità Massima Picco Settimanale (km/h)"),
        ]
        for m_idx, (m_k, m_title, m_sub_title) in enumerate(all_metrics_order):
            if m_idx > 0:
                elements.append(PageBreak())
            elements.append(_build_6w_pdf_header(m_title, m_sub_title))
            elements.append(Spacer(1, 2))
            elements.append(_build_metric_table_for_df(rep_df, m_k, is_compact=True))
    else:
        # Default: Singolo parametro compatto in 1 pagina
        elements.append(_build_6w_pdf_header(f"REPORT 6 WEEKS GPS: {minfo['name'].upper()}", f"Analisi Longitudinale & ACWR (7gg/28gg) &bull; {len(rep_df)} atleti monitorati"))
        elements.append(Spacer(1, 2))
        elements.append(_build_metric_table_for_df(rep_df, metric_key, is_compact=True))

    _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • REPORT 6 WEEKS GPS & ACWR")
    return buffer.getvalue()


# ==============================================================================
# REPORT FRANCHIGE DAY (CARICO GIORNALIERO & MATCH) — MOTORE PDF REPORTLAB
# ==============================================================================

def crea_pdf_report_franchige_day(
    sub_code: str,
    rep_df: pd.DataFrame,
    date_str: str,
    is_match_day: bool,
    rep_meta: dict,
    sort_mode: str = "ruoli",
) -> bytes:
    """
    Genera il PDF ufficiale FIR del Report Franchige Day (A4 Orizzontale)
    con carichi GPS giornalieri e colonne match dedicate se giornata di gara.
    Supporta:
    - 'completo': Tutti gli atleti in tabella coordinata
    - 'ruoli_split': 2 fogli separati (Foglio 1: Avanti, Foglio 2: TreQuarti)
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=10,
        bottomMargin=12,
    )

    elements = []
    date_disp = rep_meta.get("date_disp", date_str)
    match_sum = rep_meta.get("match_summary", "")

    def _build_day_pdf_header(title_txt: str, sub_txt: str):
        b64_logo = get_logo_base64()
        logo_cell = ""
        if b64_logo:
            try:
                logo_bytes = base64.b64decode(b64_logo)
                img = RLImage(io.BytesIO(logo_bytes), width=24, height=30)
                logo_cell = img
            except Exception:
                logo_cell = ""
        if not logo_cell:
            logo_cell = Paragraph("<b>FIR</b>", ParagraphStyle("FIRLogo", fontSize=10, fontName="Helvetica-Bold", textColor=colors.HexColor("#002B49")))

        head_p = Paragraph(f"<b>{title_txt}</b>", ParagraphStyle("H1_Day", fontSize=9, fontName="Helvetica-Bold", textColor=colors.HexColor("#002B49"), leading=11))
        sub_p = Paragraph(f"<font color='#0066B2'>FEDERAZIONE ITALIANA RUGBY • NAZIONALE MAGGIORE</font><br/><font color='#475569'>{sub_txt}</font>", ParagraphStyle("H2_Day", fontSize=6.5, fontName="Helvetica", textColor=colors.HexColor("#334155"), leading=8))

        k_stats = rep_meta.get("squad_totals", {})
        dt_val = f"{int(k_stats.get('distance_m', 0)):,} m".replace(",", ".")
        hml_val = f"{int(k_stats.get('hml', 0)):,} m".replace(",", ".")
        vmax_val = f"{k_stats.get('v_max_peak', 0.0):.1f} km/h".replace(".", ",")
        n_act = k_stats.get("n_gps", 0)
        n_m = k_stats.get("n_match", 0)

        badge_txt = f"Atleti GPS: <b>{n_act}</b> &bull; Media DT: <b>{dt_val}</b> &bull; HML: <b>{hml_val}</b> &bull; Vmax: <b>{vmax_val}</b>"
        if is_match_day:
            badge_txt = f"<b>MATCH DAY</b> &bull; Gare: <b>{n_m} atleti</b> &bull; " + badge_txt

        kpi_p = Paragraph(f"<font color='#002B49'>{badge_txt}</font>", ParagraphStyle("KPI_Day", fontSize=6.5, fontName="Helvetica-Bold", alignment=2, leading=8))

        t = Table([[logo_cell, [head_p, sub_p], kpi_p]], colWidths=[28, 480, 290])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#D4AF37")),
        ]))
        return t

    def _build_day_table_for_df(df_sub: pd.DataFrame, is_compact: bool = True) -> Table:
        if df_sub.empty:
            return Table([[Paragraph("Nessun dato disponibile", ParagraphStyle("Empty", fontSize=8))]], colWidths=[800])

        if is_match_day:
            # 14 Colonne con Match
            headers = [
                Paragraph("<b>GIOCATORE</b>", ParagraphStyle("TH_L", fontSize=5.5, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>RUOLO</b>", ParagraphStyle("TH_L", fontSize=5.5, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>TEAM</b>", ParagraphStyle("TH_L", fontSize=5.5, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>ANNO</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>PARTITA</b>", ParagraphStyle("TH_L", fontSize=5.5, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>MIN</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>IMP</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>RIS</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>DUR</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>DT (m)</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>m/min</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HML</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR18</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR20</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR25</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>V MAX</b>", ParagraphStyle("TH_C", fontSize=5.5, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
            ]
            col_w = [105, 60, 65, 26, 120, 30, 42, 34, 30, 48, 38, 44, 42, 42, 38, 40]
        else:
            # 12 Colonne senza Match
            headers = [
                Paragraph("<b>GIOCATORE</b>", ParagraphStyle("TH_L", fontSize=6.0, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>RUOLO</b>", ParagraphStyle("TH_L", fontSize=6.0, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>SQUADRA</b>", ParagraphStyle("TH_L", fontSize=6.0, fontName="Helvetica-Bold", textColor=colors.white)),
                Paragraph("<b>ANNO</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>DURATA</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>DISTANZA (m)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>m/min</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HML >25.5W (m)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR >18 (m)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR >20 (m)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>HSR >25 (m)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
                Paragraph("<b>V MAX (km/h)</b>", ParagraphStyle("TH_C", fontSize=6.0, fontName="Helvetica-Bold", alignment=1, textColor=colors.white)),
            ]
            col_w = [135, 75, 85, 30, 45, 65, 50, 65, 60, 60, 55, 60]

        data_rows = [headers]
        cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ]

        f_size = 5.2 if is_match_day else 5.8
        p_bold = ParagraphStyle("PB", fontSize=f_size, fontName="Helvetica-Bold", textColor=colors.HexColor("#0F172A"), leading=7)
        p_norm = ParagraphStyle("PN", fontSize=f_size, fontName="Helvetica", textColor=colors.HexColor("#334155"), leading=7)
        p_cen = ParagraphStyle("PC", fontSize=f_size, fontName="Helvetica", alignment=1, leading=7)
        p_cen_b = ParagraphStyle("PCB", fontSize=f_size, fontName="Helvetica-Bold", alignment=1, leading=7)

        for _, r in df_sub.iterrows():
            r_idx = len(data_rows)
            bg_col = colors.white if (r_idx % 2 == 1) else colors.HexColor("#F8FAFC")
            cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), bg_col))

            p_name = r["player_name"]
            role = r["role"]
            club = str(r["club"])[:14]
            b_yr = str(r["birth_year"])

            dur_s = f"{int(round(r['duration']))}'" if r["duration"] > 0 else "0"
            dt_s = f"{int(round(r['distance_m'])):,}".replace(",", ".") if r["distance_m"] > 0 else "0"
            mmin_s = f"{r['m_per_min']:.1f}".replace(".", ",") if r["m_per_min"] > 0 else "0"
            hml_s = f"{int(round(r['hml'])):,}".replace(",", ".") if r["hml"] > 0 else "0"
            h18_s = f"{int(round(r['hsr_18'])):,}".replace(",", ".") if r["hsr_18"] > 0 else "0"
            h20_s = f"{int(round(r['hsr_20'])):,}".replace(",", ".") if r["hsr_20"] > 0 else "0"
            h25_s = f"{int(round(r['hsr_25'])):,}".replace(",", ".") if r["hsr_25"] > 0 else "0"
            vmax_s = f"{r['v_max']:.1f}".replace(".", ",") if r["v_max"] > 0 else "0"

            if is_match_day:
                game_s = str(r.get("game") or "-")[:24]
                min_s = f"{int(r['match_min'])}'" if r["match_min"] > 0 else "-"
                imp_s = "TIT" if r["is_starter"] else ("PAN" if r["has_match"] else "-")
                res_s = str(r.get("result") or "-")[:8]

                row_cells = [
                    Paragraph(p_name, p_bold),
                    Paragraph(role, p_norm),
                    Paragraph(club, p_norm),
                    Paragraph(b_yr, p_cen),
                    Paragraph(game_s, p_norm),
                    Paragraph(min_s, p_cen_b if r["match_min"] > 0 else p_cen),
                    Paragraph(imp_s, p_cen_b if r["is_starter"] else p_cen),
                    Paragraph(res_s, p_cen),
                    Paragraph(dur_s, p_cen),
                    Paragraph(dt_s, p_cen_b if r["distance_m"] > 0 else p_cen),
                    Paragraph(mmin_s, p_cen),
                    Paragraph(hml_s, p_cen_b if r["hml"] > 0 else p_cen),
                    Paragraph(h18_s, p_cen),
                    Paragraph(h20_s, p_cen),
                    Paragraph(h25_s, p_cen),
                    Paragraph(vmax_s, p_cen_b if r["v_max"] > 0 else p_cen),
                ]
                if r["is_starter"]:
                    cmds.append(("TEXTCOLOR", (5, r_idx), (6, r_idx), colors.HexColor("#B91C1C")))
                    cmds.append(("BACKGROUND", (5, r_idx), (6, r_idx), colors.HexColor("#FEE2E2")))
                elif r["match_min"] > 0:
                    cmds.append(("BACKGROUND", (5, r_idx), (5, r_idx), colors.HexColor("#E0F2FE")))
            else:
                row_cells = [
                    Paragraph(p_name, p_bold),
                    Paragraph(role, p_norm),
                    Paragraph(club, p_norm),
                    Paragraph(b_yr, p_cen),
                    Paragraph(dur_s, p_cen),
                    Paragraph(dt_s, p_cen_b if r["distance_m"] > 0 else p_cen),
                    Paragraph(mmin_s, p_cen),
                    Paragraph(hml_s, p_cen_b if r["hml"] > 0 else p_cen),
                    Paragraph(h18_s, p_cen),
                    Paragraph(h20_s, p_cen),
                    Paragraph(h25_s, p_cen),
                    Paragraph(vmax_s, p_cen_b if r["v_max"] > 0 else p_cen),
                ]
            data_rows.append(row_cells)

        # Department averages row at bottom of table
        d_avgs = rep_meta.get("dept_averages", {})
        d_name_sub = "Avanti" if (df_sub["department"].iloc[0] == "Avanti" if not df_sub.empty else False) else "TreQuarti"
        stat_d = d_avgs.get(d_name_sub, {})
        if stat_d and stat_d.get("distance_m", 0) > 0:
            avg_r_idx = len(data_rows)
            cmds.append(("BACKGROUND", (0, avg_r_idx), (-1, avg_r_idx), colors.HexColor("#E2E8F0")))
            cmds.append(("TEXTCOLOR", (0, avg_r_idx), (-1, avg_r_idx), colors.HexColor("#0F172A")))
            avg_lbl = f"MEDIA REPARTO: {d_name_sub.upper()}"
            avg_dt = f"{int(stat_d.get('distance_m', 0)):,}".replace(",", ".")
            avg_hml = f"{int(stat_d.get('hml', 0)):,}".replace(",", ".")
            avg_h18 = f"{int(stat_d.get('hsr_18', 0)):,}".replace(",", ".")
            avg_h20 = f"{int(stat_d.get('hsr_20', 0)):,}".replace(",", ".")
            avg_h25 = f"{int(stat_d.get('hsr_25', 0)):,}".replace(",", ".")
            avg_vm = f"{stat_d.get('v_max_avg', 0.0):.1f}".replace(".", ",")
            avg_mmin = f"{stat_d.get('m_per_min', 0.0):.1f}".replace(".", ",")
            avg_dur = f"{int(round(stat_d.get('duration', 0)))}'"

            if is_match_day:
                avg_min_m = f"{int(stat_d.get('match_min_avg', 0))}'"
                avg_row = [
                    Paragraph(f"<b>{avg_lbl}</b>", p_bold), Paragraph("", p_norm), Paragraph("", p_norm), Paragraph("", p_cen),
                    Paragraph(f"<b>{stat_d.get('n_match', 0)} atleti gara</b>", p_norm),
                    Paragraph(f"<b>{avg_min_m}</b>", p_cen_b), Paragraph("-", p_cen), Paragraph("-", p_cen),
                    Paragraph(f"<b>{avg_dur}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_dt}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_mmin}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_hml}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h18}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h20}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h25}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_vm}</b>", p_cen_b),
                ]
            else:
                avg_row = [
                    Paragraph(f"<b>{avg_lbl}</b>", p_bold), Paragraph("", p_norm), Paragraph("", p_norm), Paragraph("", p_cen),
                    Paragraph(f"<b>{avg_dur}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_dt}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_mmin}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_hml}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h18}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h20}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_h25}</b>", p_cen_b),
                    Paragraph(f"<b>{avg_vm}</b>", p_cen_b),
                ]
            data_rows.append(avg_row)

        t = Table(data_rows, colWidths=col_w)
        t.setStyle(TableStyle(cmds))
        return t

    # Sub-code routing
    sub_key = str(sub_code).lower()
    df_avanti = rep_df[rep_df["department"] == "Avanti"].copy()
    df_trequarti = rep_df[rep_df["department"] == "TreQuarti"].copy()

    if "ruoli_split" in sub_key:
        elements.append(_build_day_pdf_header(f"REPORT FRANCHIGE DAY &mdash; AVANTI ({date_disp})", f"{match_sum} &bull; {len(df_avanti)} atleti"))
        elements.append(Spacer(1, 3))
        elements.append(_build_day_table_for_df(df_avanti))
        if not df_trequarti.empty:
            elements.append(PageBreak())
            elements.append(_build_day_pdf_header(f"REPORT FRANCHIGE DAY &mdash; TREQUARTI ({date_disp})", f"{match_sum} &bull; {len(df_trequarti)} atleti"))
            elements.append(Spacer(1, 3))
            elements.append(_build_day_table_for_df(df_trequarti))
    else:
        # Default: Report completo coordinato
        elements.append(_build_day_pdf_header(f"REPORT FRANCHIGE DAY &mdash; {date_disp}", f"{match_sum} &bull; {len(rep_df)} atleti monitorati"))
        elements.append(Spacer(1, 3))
        elements.append(_build_day_table_for_df(rep_df))

    _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • REPORT FRANCHIGE DAY")
    return buffer.getvalue()


# ==============================================================================
# REPORT SCHIERAMENTO IN CAMPO (1-23 MATCH REPORT) — MOTORE PDF REPORTLAB
# ==============================================================================

def _draw_schieramento_pitch_on_canvas(
    c: canvas.Canvas,
    match_meta: dict,
    starters_df: pd.DataFrame,
    finishers_df: pd.DataFrame,
    player_stats: dict,
    rep_averages: dict,
):
    w_pt, h_pt = landscape(A4)

    title_txt = str(match_meta.get("title") or "ITALIA - SUD AFRICA NC NOV 2026").upper()
    date_txt = str(match_meta.get("date_str") or "SABATO 7 NOVEMBRE 2026").upper()
    slogan_txt = str(match_meta.get("slogan") or "PRIMI SEMPRE • ATTACCARE SEMPRE").upper()
    comp_txt = str(match_meta.get("competition") or "NATIONS CHAMPIONSHIP").upper()

    # --------------------------------------------------------------------------
    # 1. HEADER SUPERIORE FIR (Banda Blu Navy Ufficiale)
    # --------------------------------------------------------------------------
    header_x, header_y, header_w, header_h = 16, h_pt - 48, w_pt - 32, 32
    c.setFillColor(colors.HexColor("#002B49"))
    c.setStrokeColor(colors.HexColor("#D4AF37"))
    c.setLineWidth(1.2)
    c.roundRect(header_x, header_y, header_w, header_h, 5, fill=1, stroke=1)

    # Logo FIR a sinistra
    logo_drawn = False
    if os.path.exists(LOGO_PATH):
        try:
            ir_logo = ImageReader(LOGO_PATH)
            c.drawImage(ir_logo, header_x + 8, header_y + 2.5, width=23, height=27, mask="auto")
            logo_drawn = True
        except Exception:
            logo_drawn = False
    if not logo_drawn:
        c.setFillColor(colors.HexColor("#D4AF37"))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(header_x + 10, header_y + 11, "FIR")

    # Titolo Match e Slogan
    text_x = header_x + (38 if logo_drawn else 32)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11.0)
    c.drawString(text_x, header_y + 17, title_txt)

    c.setFillColor(colors.HexColor("#D4AF37"))
    c.setFont("Helvetica-Bold", 7.2)
    c.drawString(text_x, header_y + 6.5, f"FEDERAZIONE ITALIANA RUGBY • {slogan_txt}")

    # Data e Competizione a destra
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9.0)
    c.drawRightString(header_x + header_w - 12, header_y + 17, date_txt)

    c.setFillColor(colors.HexColor("#93C5FD"))
    c.setFont("Helvetica", 7.2)
    c.drawRightString(header_x + header_w - 12, header_y + 6.5, comp_txt)

    # --------------------------------------------------------------------------
    # 2. CAMPO DI GIOCO RUGBY (Titolari 1–15)
    # --------------------------------------------------------------------------
    pitch_x, pitch_y, pitch_w, pitch_h = 16, 92, 582, 448
    c.setFillColor(colors.HexColor("#15803D"))  # Verde campo rugby
    c.setStrokeColor(colors.white)
    c.setLineWidth(1.8)
    c.roundRect(pitch_x, pitch_y, pitch_w, pitch_h, 6, fill=1, stroke=1)

    # Segnature campo (Linee rugby regolamentari)
    c.setStrokeColor(colors.HexColor("#FFFFFF"))
    # Linea di metà campo (50m)
    mid_y = pitch_y + (pitch_h / 2.0)
    c.setLineWidth(1.2)
    c.line(pitch_x, mid_y, pitch_x + pitch_w, mid_y)

    # Linee dei 10m (tratteggiate)
    c.setLineWidth(0.8)
    c.setDash([4, 4])
    c.line(pitch_x, mid_y - 56, pitch_x + pitch_w, mid_y - 56)
    c.line(pitch_x, mid_y + 56, pitch_x + pitch_w, mid_y + 56)
    c.setDash([])

    # Linee dei 22m (continue)
    c.setLineWidth(1.0)
    c.line(pitch_x, pitch_y + 76, pitch_x + pitch_w, pitch_y + 76)
    c.line(pitch_x, pitch_y + pitch_h - 76, pitch_x + pitch_w, pitch_y + pitch_h - 76)

    # Linee di meta / in-goal (tratteggiate)
    c.setDash([3, 3])
    c.line(pitch_x, pitch_y + 20, pitch_x + pitch_w, pitch_y + 20)
    c.line(pitch_x, pitch_y + pitch_h - 20, pitch_x + pitch_w, pitch_y + pitch_h - 20)
    c.setDash([])

    # --------------------------------------------------------------------------
    # 3. FUNZIONE DI DISEGNO CARD GIOCATORE (Cornici Blu/Rosse per Ruolo e Spaziatura)
    # --------------------------------------------------------------------------
    starters_map = {int(r["jersey_number"]): r.to_dict() for _, r in starters_df.iterrows()} if not starters_df.empty else {}
    finishers_map = {int(r["jersey_number"]): r.to_dict() for _, r in finishers_df.iterrows()} if not finishers_df.empty else {}

    players_roster_df = utils.get_players_df()
    roster_role_map = {}
    if not players_roster_df.empty:
        for _, pr in players_roster_df.iterrows():
            nm = str(pr.get("name_display") or "").strip().upper()
            if nm:
                roster_role_map[nm] = str(pr.get("role") or "").strip()

    def _get_pitch_card_border_color(j_num: int, role_str: str = "", p_name: str = "") -> str:
        """
        Restituisce il colore della cornice della card:
        - Avanti (Cornice Blu):
          * Scuro (#172554): 1-2-3 (Prima Linea: Piloni e Tallonatore)
          * Normale (#2563EB): 4-5 (Seconda Linea)
          * Chiaro (#38BDF8): 6-7-8 (Terza Linea)
        - Trequarti (Cornice Rossa):
          * Scuro (#7F1D1D): 9-10 (Mediani di Mischia e Apertura)
          * Normale (#EF4444): 12-13 (Centri)
          * Chiaro (#FDA4AF): 11-14-15 (Triangolo Allargato: Ali ed Estremo)
        Per la panchina (16-23) usa il ruolo del giocatore.
        """
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

    def _draw_player_box(bx: float, by: float, bw: float, bh: float, j_num: int):
        p_row = starters_map.get(j_num) if j_num in starters_map else (finishers_map.get(j_num) if j_num in finishers_map else {})
        p_name = str(p_row.get("player_name") or f"Maglia {j_num}").strip()
        p_role = str(p_row.get("role") or "").strip()
        if j_num >= 16:
            r_from_roster = roster_role_map.get(p_name.upper())
            if r_from_roster:
                p_role = r_from_roster
        border_hex = _get_pitch_card_border_color(j_num, p_role, p_name)

        st_data = player_stats.get(p_name) or player_stats.get(j_num) or {}
        minuti_val = st_data.get("minutes", st_data.get("duration", 0))
        pos_val = st_data.get("PoS", st_data.get("v_max", 0.0))
        dt_val = st_data.get("DT", st_data.get("distance_m", 0.0))
        dc_val = st_data.get("DC", st_data.get("run_distance_m", 0.0))
        hml_val = st_data.get("Hml", st_data.get("hml_distance_m", 0.0))
        vhml_val = st_data.get("VHml", st_data.get("vhml_distance_m", 0.0))
        hsr_val = st_data.get("HSR", st_data.get("hsr_distance_m", 0.0))
        cic_val = st_data.get("CIC", 0.0)
        tck_val = st_data.get("TCK", 0.0)
        rck_val = st_data.get("RCK", 0.0)

        # 1. Sfondo bianco card con angoli arrotondati
        c.setFillColor(colors.white)
        c.roundRect(bx, by, bw, bh, 3.5, fill=1, stroke=0)

        # 2. Foto a tutta altezza sulla sinistra (35% della larghezza della card)
        pw = round(bw * 0.35, 1)
        photo_b64 = utils.get_player_photo_base64(p_name, max_width=160)
        photo_drawn = False
        if photo_b64:
            try:
                p_bytes = base64.b64decode(photo_b64)
                with Image.open(io.BytesIO(p_bytes)) as pil_img:
                    target_w = int(pw * 3)
                    target_h = int((bh - 2.0) * 3)
                    img_w, img_h = pil_img.size
                    scale = max(target_w / img_w, target_h / img_h)
                    new_w = int(round(img_w * scale))
                    new_h = int(round(img_h * scale))
                    resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    left = (new_w - target_w) // 2
                    top = 0
                    cropped = resized.crop((left, top, left + target_w, top + target_h))
                    buf = io.BytesIO()
                    cropped.convert("RGB").save(buf, format="JPEG", quality=90)
                    buf.seek(0)
                    ir_p = ImageReader(buf)
                    c.drawImage(ir_p, bx + 1.0, by + 1.0, width=pw - 1.0, height=bh - 2.0)
                    photo_drawn = True
            except Exception:
                photo_drawn = False

        if not photo_drawn:
            c.setFillColor(colors.HexColor("#F1F5F9"))
            c.roundRect(bx + 1.0, by + 1.0, pw - 1.0, bh - 2.0, 2, fill=1, stroke=0)
            inits = "".join(part[0] for part in p_name.split()[:2]).upper()
            c.setFillColor(colors.HexColor("#002B49"))
            c.setFont("Helvetica-Bold", 8.0)
            c.drawCentredString(bx + (pw / 2.0), by + (bh / 2.0) - 2.5, inits)

        # Linea verticale divisoria tra foto e dati
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.5)
        c.line(bx + pw, by + 1.0, bx + pw, by + bh - 1.0)

        # 3. Sezione Dati Destra
        rx = bx + pw
        rw = bw - pw

        # Header area (altezza 14.0 pt)
        hdr_h = 14.0
        hdr_y = by + bh - hdr_h
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.4)
        c.line(rx, hdr_y, bx + bw - 1.0, hdr_y)

        # Badge circolare con numero di maglia
        badge_r = 5.2
        badge_cx = rx + 7.5
        badge_cy = by + bh - 7.0
        c.setFillColor(colors.HexColor(border_hex))
        c.circle(badge_cx, badge_cy, badge_r, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 5.8)
        c.drawCentredString(badge_cx, badge_cy - 2.0, str(j_num))

        # Nome giocatore formattato
        parts = p_name.strip().split()
        if len(parts) >= 3 and parts[1].lower() in ('di', 'de', 'del', 'della', 'da'):
            display_name = f"{parts[0][0]}. {' '.join(parts[1:])}"
        elif len(parts) >= 3:
            display_name = f"{parts[0][0]}. {parts[1][0]}. {' '.join(parts[2:])}"
        elif len(parts) == 2:
            display_name = f"{parts[0][0]}. {parts[1]}"
        else:
            display_name = p_name

        c.setFillColor(colors.HexColor("#0F172A"))
        d_len = len(display_name)
        f_size = 5.0 if d_len > 13 else (5.6 if d_len > 10 else 6.2)
        c.setFont("Helvetica-Bold", f_size)
        c.drawString(rx + 14.5, by + bh - 8.8, display_name)

        # Minuti in alto a destra
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica-Bold", 4.0)
        c.drawRightString(bx + bw - 3.0, by + bh - 5.5, "min")
        c.setFillColor(colors.HexColor("#0284C7"))
        c.setFont("Helvetica-Bold", 6.2)
        c.drawRightString(bx + bw - 3.0, by + bh - 12.0, f"{int(round(minuti_val))}")

        # Griglia 6 Metriche GPExe (2 colonne x 3 righe)
        pos_str = f"{pos_val:.1f}" if pos_val > 0 else "0"
        dt_str = f"{int(dt_val):,}".replace(",", ".") if dt_val > 0 else "0"
        dc_str = f"{int(dc_val):,}".replace(",", ".") if dc_val > 0 else "0"
        hml_str = f"{int(hml_val):,}".replace(",", ".") if hml_val > 0 else "0"
        vhml_str = f"{int(vhml_val):,}".replace(",", ".") if vhml_val > 0 else "0"
        hsr_str = f"{int(hsr_val):,}".replace(",", ".") if hsr_val > 0 else "0"

        c1_lbl_x = rx + 2.5
        c1_val_x = rx + (rw / 2.0) - 2.5
        c2_lbl_x = rx + (rw / 2.0) + 2.0
        c2_val_x = bx + bw - 3.0

        r1_y = by + 27.5
        r2_y = by + 19.0
        r3_y = by + 10.5

        # Riga 1: PoS | DT
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c1_lbl_x, r1_y, "PoS")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c1_val_x, r1_y, pos_str)

        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c2_lbl_x, r1_y, "DT")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c2_val_x, r1_y, dt_str)

        # Riga 2: DC | Hml
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c1_lbl_x, r2_y, "DC")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c1_val_x, r2_y, dc_str)

        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c2_lbl_x, r2_y, "Hml")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c2_val_x, r2_y, hml_str)

        # Riga 3: VHml | HSR
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c1_lbl_x, r3_y, "VHml")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c1_val_x, r3_y, vhml_str)

        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 4.5)
        c.drawString(c2_lbl_x, r3_y, "HSR")
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 5.4)
        c.drawRightString(c2_val_x, r3_y, hsr_str)

        # Linea divisoria tratteggiata sopra i dati Oval
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.4)
        c.setDash([2, 2])
        c.line(rx + 1.5, by + 8.8, bx + bw - 1.5, by + 8.8)
        c.setDash([])

        # Fascia Inferiore Dati Oval (CIC / TCK / RCK)
        cic_str = f"{int(round(cic_val))}" if cic_val > 0 else "0"
        tck_str = f"{int(round(tck_val))}" if tck_val > 0 else "0"
        rck_str = f"{int(round(rck_val))}" if rck_val > 0 else "0"

        r4_y = by + 2.5
        third_w = rw / 3.0
        ov_items = [
            ("CIC", cic_str, "#0369A1", rx + 2.0),
            ("TCK", tck_str, "#B91C1C", rx + third_w + 1.0),
            ("RCK", rck_str, "#047857", rx + 2.0 * third_w + 1.0),
        ]
        for o_lbl, o_val_s, o_col, ox in ov_items:
            c.setFillColor(colors.HexColor("#64748B"))
            c.setFont("Helvetica-Bold", 4.3)
            c.drawString(ox, r4_y, o_lbl)
            c.setFillColor(colors.HexColor(o_col))
            c.setFont("Helvetica-Bold", 5.4)
            c.drawRightString(ox + third_w - 2.5, r4_y, o_val_s)

        # 4. Cornice arrotondata per ruolo
        c.setStrokeColor(colors.HexColor(border_hex))
        c.setLineWidth(1.8)
        c.roundRect(bx, by, bw, bh, 3.5, fill=0, stroke=1)

    # Posizionamento Titolari 1–15 con spaziatura netta tra le file (in particolare tra 9-12 e 10-13)
    cw, ch = 118, 54.5
    starter_positions = {
        # 1. Prima Linea (Blu Scuro)
        1: (32, 481),
        2: (248, 481),
        3: (464, 481),
        # 2. Seconda Linea (Blu Normale)
        4: (140, 420),
        5: (356, 420),
        # 3. Terza Linea (Blu Chiaro)
        6: (32, 359),
        8: (248, 359),
        7: (464, 359),
        # 4. Mediani (Rosso Scuro)
        9: (140, 297),
        10: (356, 297),
        # 5. Centri (Rosso Normale) — distanziati con 15.5 pt di margine netto sotto 9 e 10
        12: (140, 229),
        13: (356, 229),
        # 6. Ali (Rosso Chiaro)
        11: (24, 163),
        14: (472, 163),
        # 7. Estremo (Rosso Chiaro)
        15: (248, 98),
    }

    for j_num, (pos_x, pos_y) in starter_positions.items():
        _draw_player_box(pos_x, pos_y, cw, ch, j_num)

    # --------------------------------------------------------------------------
    # 4. PANNELLO FINISHERS (Maglie 16–23 a destra in 2 colonne da 4)
    # --------------------------------------------------------------------------
    fin_x, fin_y, fin_w, fin_h = 604, 92, 222, 448
    c.setFillColor(colors.HexColor("#031926"))
    c.setStrokeColor(colors.HexColor("#D4AF37"))
    c.setLineWidth(1.2)
    c.roundRect(fin_x, fin_y, fin_w, fin_h, 6, fill=1, stroke=1)

    # Header Finishers
    c.setFillColor(colors.HexColor("#D4AF37"))
    c.setFont("Helvetica-Bold", 9.0)
    c.drawCentredString(fin_x + (fin_w / 2.0), fin_y + fin_h - 14, "FINISHERS (16–23)")
    c.setFillColor(colors.HexColor("#94A3B8"))
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(fin_x + (fin_w / 2.0), fin_y + fin_h - 24, "PANCHINA GARA")

    fcw, fch = 104, 54.5
    fin_col1_x = fin_x + 5
    fin_col2_x = fin_x + 113

    # Sotto-intestazioni Colonne
    c.setFillColor(colors.HexColor("#FCD34D"))
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(fin_col1_x + (fcw / 2.0), fin_y + fin_h - 36, "COLONNA 1")
    c.drawCentredString(fin_col2_x + (fcw / 2.0), fin_y + fin_h - 36, "COLONNA 2")

    finisher_positions = {
        16: (fin_col1_x, 432),
        20: (fin_col2_x, 432),
        17: (fin_col1_x, 328),
        21: (fin_col2_x, 328),
        18: (fin_col1_x, 224),
        22: (fin_col2_x, 224),
        19: (fin_col1_x, 120),
        23: (fin_col2_x, 120),
    }

    for f_num, (f_x, f_y) in finisher_positions.items():
        _draw_player_box(f_x, f_y, fcw, fch, f_num)

    # Footer discreto in fondo al pannello
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(fin_x + (fin_w / 2.0), 102, "FEDERAZIONE ITALIANA RUGBY • NAZIONALE MAGGIORE")

    # --------------------------------------------------------------------------
    # 5. BOX INFERIORI: MEDIE REPARTI & LEGENDA GPEXE
    # --------------------------------------------------------------------------
    bot_y = 14
    bot_h = 72

    # BOX 1: MEDIE REPARTI (Sinistra, larghezza 380 pt)
    b1_x, b1_w = 16, 380
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.HexColor("#002B49"))
    c.setLineWidth(1.0)
    c.roundRect(b1_x, bot_y, b1_w, bot_h, 5, fill=1, stroke=1)

    # Intestazione Medie Reparti
    c.setFillColor(colors.HexColor("#002B49"))
    c.roundRect(b1_x, bot_y + bot_h - 16, b1_w, 16, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.0)
    c.drawString(b1_x + 8, bot_y + bot_h - 11.5, "MEDIE REPARTI GPS (÷ 8 / 7) • SOMME REPARTI OVAL (TOT)")

    avg_fwd = rep_averages.get("Avanti", {})
    avg_bks = rep_averages.get("TreQuarti", {})

    col_w_arr = [52, 41, 41, 41, 40, 49, 34, 34, 34]
    t_headers = ["Reparto", "DT (m)", "DC (m)", "Hml (m)", "VHml", "HSR (m)", "CIC (Tot)", "TCK (Tot)", "RCK (Tot)"]
    t_x = b1_x + 6

    # Riga Header Tabella
    th_y = bot_y + bot_h - 28
    c.setFillColor(colors.HexColor("#F1F5F9"))
    c.rect(t_x, th_y - 2, b1_w - 12, 11, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#475569"))
    c.setFont("Helvetica-Bold", 5.5)
    cur_tx = t_x + 3
    for i, h_lbl in enumerate(t_headers):
        if i == 0:
            c.drawString(cur_tx, th_y + 1, h_lbl)
        else:
            c.drawRightString(cur_tx + col_w_arr[i] - 4, th_y + 1, h_lbl)
        cur_tx += col_w_arr[i]

    # Riga Avanti
    rf_y = bot_y + bot_h - 41
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 5.8)
    c.drawString(t_x + 3, rf_y, "Avanti (÷ 8)")
    c.setFont("Helvetica", 5.6)
    cur_tx = t_x + col_w_arr[0]
    c.drawRightString(cur_tx + col_w_arr[1] - 4, rf_y, f"{int(avg_fwd.get('DT', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[1]
    c.drawRightString(cur_tx + col_w_arr[2] - 4, rf_y, f"{int(avg_fwd.get('DC', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[2]
    c.drawRightString(cur_tx + col_w_arr[3] - 4, rf_y, f"{int(avg_fwd.get('Hml', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[3]
    c.drawRightString(cur_tx + col_w_arr[4] - 4, rf_y, f"{int(avg_fwd.get('VHml', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[4]
    c.drawRightString(cur_tx + col_w_arr[5] - 4, rf_y, f"{int(avg_fwd.get('HSR', 0)):,} (>18)".replace(",", "."))
    cur_tx += col_w_arr[5]
    c.setFont("Helvetica-Bold", 5.6)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawRightString(cur_tx + col_w_arr[6] - 4, rf_y, f"{int(round(avg_fwd.get('CIC', 0)))}")
    cur_tx += col_w_arr[6]
    c.setFillColor(colors.HexColor("#B91C1C"))
    c.drawRightString(cur_tx + col_w_arr[7] - 4, rf_y, f"{int(round(avg_fwd.get('TCK', 0)))}")
    cur_tx += col_w_arr[7]
    c.setFillColor(colors.HexColor("#047857"))
    c.drawRightString(cur_tx + col_w_arr[8] - 4, rf_y, f"{int(round(avg_fwd.get('RCK', 0)))}")

    # Riga TreQuarti
    rb_y = bot_y + bot_h - 54
    c.setFillColor(colors.HexColor("#0F172A"))
    c.setFont("Helvetica-Bold", 5.8)
    c.drawString(t_x + 3, rb_y, "TreQuarti (÷ 7)")
    c.setFont("Helvetica", 5.6)
    cur_tx = t_x + col_w_arr[0]
    c.drawRightString(cur_tx + col_w_arr[1] - 4, rb_y, f"{int(avg_bks.get('DT', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[1]
    c.drawRightString(cur_tx + col_w_arr[2] - 4, rb_y, f"{int(avg_bks.get('DC', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[2]
    c.drawRightString(cur_tx + col_w_arr[3] - 4, rb_y, f"{int(avg_bks.get('Hml', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[3]
    c.drawRightString(cur_tx + col_w_arr[4] - 4, rb_y, f"{int(avg_bks.get('VHml', 0)):,}".replace(",", "."))
    cur_tx += col_w_arr[4]
    c.drawRightString(cur_tx + col_w_arr[5] - 4, rb_y, f"{int(avg_bks.get('HSR', 0)):,} (>20)".replace(",", "."))
    cur_tx += col_w_arr[5]
    c.setFont("Helvetica-Bold", 5.6)
    c.setFillColor(colors.HexColor("#0369A1"))
    c.drawRightString(cur_tx + col_w_arr[6] - 4, rb_y, f"{int(round(avg_bks.get('CIC', 0)))}")
    cur_tx += col_w_arr[6]
    c.setFillColor(colors.HexColor("#B91C1C"))
    c.drawRightString(cur_tx + col_w_arr[7] - 4, rb_y, f"{int(round(avg_bks.get('TCK', 0)))}")
    cur_tx += col_w_arr[7]
    c.setFillColor(colors.HexColor("#047857"))
    c.drawRightString(cur_tx + col_w_arr[8] - 4, rb_y, f"{int(round(avg_bks.get('RCK', 0)))}")

    # Nota HSR in calce
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Oblique", 4.8)
    c.drawString(t_x + 4, bot_y + 4, "* Medie GPS (Avanti ÷ 8, TreQuarti ÷ 7). Per i parametri Oval (CIC, TCK, RCK) è indicata la Somma Totale di reparto.")

    # BOX 2: LEGENDA METRICHE GPEXE & OVAL (Destra, larghezza 422 pt)
    b2_x, b2_w = 404, 422
    c.setFillColor(colors.HexColor("#FFFFFF"))
    c.setStrokeColor(colors.HexColor("#002B49"))
    c.setLineWidth(1.0)
    c.roundRect(b2_x, bot_y, b2_w, bot_h, 5, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#002B49"))
    c.roundRect(b2_x, bot_y + bot_h - 16, b2_w, 16, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.0)
    c.drawString(b2_x + 8, bot_y + bot_h - 11.5, "LEGENDA METRICHE GPEXE & OVAL MATCH (FIR)")

    leg_lines = [
        ("PoS/DT/DC", "Peak of Speed (Vmax km/h) • Distanza Totale (m) • Distanza Corsa >6.0 km/h (m)."),
        ("Hml/VHml", "High Metabolic Load >25.5 W/kg (m) • Very High Metabolic Load >50.0 W/kg (m)."),
        ("HSR", "High Speed Running: Corsa ad alta velocità (>18 km/h Avanti, >20 km/h TreQuarti)."),
        ("CIC", "TotalCarriesInContact (Oval): Carries portati in contatto nel match."),
        ("TCK", "TackleComplete (Oval): Placcaggi completati con successo nel match."),
        ("RCK", "TotalRuckEntries (Oval): Ingressi totali in ruck / punto d'incontro nel match."),
    ]

    leg_start_y = bot_y + bot_h - 26
    for idx, (abbr, desc) in enumerate(leg_lines):
        line_y = leg_start_y - (idx * 7.5)
        c.setFillColor(colors.HexColor("#0369A1"))
        c.setFont("Helvetica-Bold", 5.3)
        c.drawString(b2_x + 8, line_y, f"• {abbr}:")
        c.setFillColor(colors.HexColor("#334155"))
        c.setFont("Helvetica", 5.2)
        c.drawString(b2_x + 48, line_y, desc)


def crea_pdf_schieramento_campo(
    match_meta: dict,
    starters_df: pd.DataFrame,
    finishers_df: pd.DataFrame,
    player_stats: dict,
    rep_averages: dict,
) -> bytes:
    """
    Genera il PDF ufficiale FIR dello Schieramento in Campo (1-23 Match Lineup),
    replicando fedelmente il layout, i box giocatori con foto ufficiale, le metriche GPExe
    (PoS, DT, DC >6km/h, Hml >25.5W, VHml >50W, HSR 18/20) e il riquadro Medie Reparti.
    Formato: A4 Orizzontale (Landscape).
    """
    buffer = io.BytesIO()
    w_pt, h_pt = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(w_pt, h_pt))
    _draw_schieramento_pitch_on_canvas(
        c,
        match_meta=match_meta,
        starters_df=starters_df,
        finishers_df=finishers_df,
        player_stats=player_stats,
        rep_averages=rep_averages,
    )
    c.save()
    return buffer.getvalue()


# ==============================================================================
# REPORT SINGOLO ATLETA (3 SETTIMANE DAY-BY-DAY) — MOTORE PDF REPORTLAB
# ==============================================================================

def _build_single_athlete_gps_flowables(
    player_name: str,
    p_meta: dict,
    df_21: pd.DataFrame,
    week_stats: dict,
    fig: go.Figure = None,
    ref_week_lbl: str = "",
    include_charts: bool = True,
) -> list:
    """Costruisce la scheda GPS e carichi 21 giorni del singolo atleta condensata in 1 sola pagina A4 Landscape."""
    elements = []

    # 1. Header FIR Pagina Unica GPS
    elements.append(
        _build_fir_header_table(
            main_title="SCHEDA MONITORAGGIO LONGITUDINALE ATLETA (3 SETTIMANE DAY-BY-DAY)",
            sub_title=f"Analisi carichi GPS unificati (FIR + Franchigie) e tabella 21 giorni per {player_name.upper()}",
            right_line1=f"SETTIMANA W0: {ref_week_lbl}",
            right_line2="DATABASE UNIFICATO FIR",
            right_line3="MONITORAGGIO LONGITUDINALE",
            total_width=808.0,
        )
    )
    elements.append(Spacer(1, 2))

    # 2. Player Banner Card Compatto (Foto + Ruolo + Reparto + Club + Vmax)
    photo_b64 = utils.get_player_photo_base64(player_name, max_width=120)
    photo_cell = ""
    if photo_b64:
        try:
            im_bytes = base64.b64decode(photo_b64)
            photo_cell = RLImage(io.BytesIO(im_bytes), width=40, height=48)
        except Exception:
            photo_cell = ""
    if not photo_cell:
        inits = "".join(part[0] for part in player_name.split()[:2]).upper()
        photo_cell = Paragraph(f"<b>{inits}</b>", ParagraphStyle("Inits", fontName="Helvetica-Bold", fontSize=14, alignment=1, textColor=colors.HexColor("#002B49")))

    p_role = str(p_meta.get("role") or "Avanti")
    p_dept = str(p_meta.get("department") or "Avanti")
    p_club = str(p_meta.get("club") or "FIR")
    p_vmax = float(p_meta.get("v_max") or 30.0)

    info_p = Paragraph(
        f"<font size='10.5' color='#002B49'><b>{player_name.upper()}</b></font><br/>"
        f"<font size='6.8' color='#475569'>Ruolo: <b>{p_role}</b> &bull; Reparto: <b>{p_dept}</b><br/>"
        f"Squadra: <b>{p_club}</b> &bull; V max: <b>{p_vmax:.1f} km/h</b></font>",
        ParagraphStyle("PInfo", fontName="Helvetica", fontSize=6.8, leading=8.8),
    )

    # 3 Summary Cards Settimanali
    st2 = week_stats.get("Week -2", {})
    st1 = week_stats.get("Week -1", {})
    st0 = week_stats.get("Week 0 (Attuale)", {})

    dt2 = st2.get("DT", 0.0)
    dt1 = st1.get("DT", 0.0)
    dt0 = st0.get("DT", 0.0)

    d1_pct = ((dt1 - dt2) / dt2 * 100.0) if dt2 > 0 else 0.0
    d0_pct = ((dt0 - dt1) / dt1 * 100.0) if dt1 > 0 else 0.0

    kpi_card_w2 = Paragraph(
        f"<font size='6.2' color='#0369A1'><b>WEEK -2 (DUE SETT. FA)</b></font><br/>"
        f"<font size='9.5' color='#0F172A'><b>{int(dt2):,} m</b></font><br/>"
        f"<font size='5.8' color='#475569'>HML: <b>{int(st2.get('Hml',0)):,} m</b> | HSR: <b>{int(st2.get('HSR',0)):,} m</b><br/>"
        f"Vmax: <b>{st2.get('Vmax',0):.1f} km/h</b> | Match: <b>{int(st2.get('Match_Min',0))}'</b></font>".replace(",", "."),
        ParagraphStyle("CardW2", fontName="Helvetica", leading=7.5, alignment=1),
    )

    d1_sign = "+" if d1_pct >= 0 else ""
    kpi_card_w1 = Paragraph(
        f"<font size='6.2' color='#4338CA'><b>WEEK -1 ({d1_sign}{d1_pct:.1f}%)</b></font><br/>"
        f"<font size='9.5' color='#0F172A'><b>{int(dt1):,} m</b></font><br/>"
        f"<font size='5.8' color='#475569'>HML: <b>{int(st1.get('Hml',0)):,} m</b> | HSR: <b>{int(st1.get('HSR',0)):,} m</b><br/>"
        f"Vmax: <b>{st1.get('Vmax',0):.1f} km/h</b> | Match: <b>{int(st1.get('Match_Min',0))}'</b></font>".replace(",", "."),
        ParagraphStyle("CardW1", fontName="Helvetica", leading=7.5, alignment=1),
    )

    d0_sign = "+" if d0_pct >= 0 else ""
    kpi_card_w0 = Paragraph(
        f"<font size='6.2' color='#059669'><b>WEEK 0 ({d0_sign}{d0_pct:.1f}%)</b></font><br/>"
        f"<font size='9.5' color='#0F172A'><b>{int(dt0):,} m</b></font><br/>"
        f"<font size='5.8' color='#475569'>HML: <b>{int(st0.get('Hml',0)):,} m</b> | HSR: <b>{int(st0.get('HSR',0)):,} m</b><br/>"
        f"Vmax: <b>{st0.get('Vmax',0):.1f} km/h</b> | Match: <b>{int(st0.get('Match_Min',0))}'</b></font>".replace(",", "."),
        ParagraphStyle("CardW0", fontName="Helvetica", leading=7.5, alignment=1),
    )

    top_banner_tbl = Table(
        [[photo_cell, info_p, kpi_card_w2, kpi_card_w1, kpi_card_w0]],
        colWidths=[48, 204, 185, 185, 186],
    )
    top_banner_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (1, 0), colors.HexColor("#F0F9FF")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#E0F2FE")),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#EEF2FF")),
        ("BACKGROUND", (4, 0), (4, 0), colors.HexColor("#ECFDF5")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#0284C7")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(top_banner_tbl)
    elements.append(Spacer(1, 2))

    # 3. Grafico Plotly giorno per giorno compatto (altezza ottimizzata per stare nella pagina)
    if fig is not None and include_charts:
        try:
            chart_img = fig_to_rl_image(fig, width=808, height=105)
            if chart_img:
                elements.append(chart_img)
                elements.append(Spacer(1, 2))
        except Exception:
            pass

    # 4. Tabella Dettagliata 21 Giorni con Subtotali (SULLA STESSA PAGINA, larghezza perfetta 808pt)
    elements.append(
        _PortalSectionHeaderFlowable(
            "Dettaglio Carichi Giornalieri (21 Giorni: Week -2, Week -1, Week 0)",
            "Seduta per seduta e partite Oval Match delle ultime 3 settimane con subtotali",
            accent_hex="#0284C7",
            width=808.0,
            height=14.0,
        )
    )
    elements.append(Spacer(1, 2))

    th_s = ParagraphStyle("TH_D", fontName="Helvetica-Bold", fontSize=5.8, leading=6.8, alignment=1, textColor=colors.white)
    headers = [
        Paragraph("<b>GIORNO & DATA</b>", ParagraphStyle("TH_D0", parent=th_s, alignment=0)),
        Paragraph("<b>SETTIMANA</b>", th_s),
        Paragraph("<b>SQUADRA</b>", th_s),
        Paragraph("<b>SEDUTA / MATCH</b>", th_s),
        Paragraph("<b>MIN MATCH</b>", th_s),
        Paragraph("<b>DURATA (MIN)</b>", th_s),
        Paragraph("<b>DISTANZA (DT)</b>", th_s),
        Paragraph("<b>DC (>6KM/H)</b>", th_s),
        Paragraph("<b>HML (>25.5W)</b>", th_s),
        Paragraph("<b>VHML (>50W)</b>", th_s),
        Paragraph("<b>HSR (18/20)</b>", th_s),
        Paragraph("<b>V MAX (KM/H)</b>", th_s),
    ]
    t_rows = [headers]
    t_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (3, -1), "LEFT"),
        ("ALIGN", (4, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 5.5),
        ("LEADING", (0, 0), (-1, -1), 6.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (0, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]

    current_w = None
    sub_dt = sub_dc = sub_hml = sub_vhml = sub_hsr = sub_min = sub_dur = 0.0

    for _, r in df_21.iterrows():
        w_code = str(r.get("week_code", r.get("week_idx", "W0")))
        if current_w is not None and w_code != current_w:
            sub_r_idx = len(t_rows)
            t_rows.append([
                Paragraph(f"<b>SUBTOTALE {current_w.upper()}</b>", ParagraphStyle("SubL", fontName="Helvetica-Bold", fontSize=5.8, textColor=colors.HexColor("#002B49"))),
                "", "", "",
                Paragraph(f"<b>{int(sub_min)}'</b>", ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1, textColor=colors.HexColor("#0284C7"))),
                Paragraph(f"<b>{int(sub_dur)}'</b>", ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
                Paragraph(f"<b>{int(sub_dt):,}</b>".replace(",", "."), ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
                Paragraph(f"<b>{int(sub_dc):,}</b>".replace(",", "."), ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
                Paragraph(f"<b>{int(sub_hml):,}</b>".replace(",", "."), ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1, textColor=colors.HexColor("#D97706"))),
                Paragraph(f"<b>{int(sub_vhml):,}</b>".replace(",", "."), ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
                Paragraph(f"<b>{int(sub_hsr):,}</b>".replace(",", "."), ParagraphStyle("SubC", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
                "-",
            ])
            t_cmds.extend([
                ("SPAN", (0, sub_r_idx), (3, sub_r_idx)),
                ("BACKGROUND", (0, sub_r_idx), (-1, sub_r_idx), colors.HexColor("#E2E8F0")),
                ("FONTNAME", (0, sub_r_idx), (-1, sub_r_idx), "Helvetica-Bold"),
                ("LINEABOVE", (0, sub_r_idx), (-1, sub_r_idx), 0.8, colors.HexColor("#94A3B8")),
                ("LINEBELOW", (0, sub_r_idx), (-1, sub_r_idx), 0.8, colors.HexColor("#94A3B8")),
            ])
            sub_dt = sub_dc = sub_hml = sub_vhml = sub_hsr = sub_min = sub_dur = 0.0

        current_w = w_code
        r_idx = len(t_rows)
        has_match = bool(r["is_match"])

        bg_row = "#FFF1F2" if has_match else ("#FFFFFF" if r_idx % 2 == 1 else "#F8FAFC")
        t_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor(bg_row)))

        sub_dt += float(r.get("DT") or 0.0)
        sub_dc += float(r.get("DC") or 0.0)
        sub_hml += float(r.get("Hml") or 0.0)
        sub_vhml += float(r.get("VHml") or 0.0)
        sub_hsr += float(r.get("HSR") or 0.0)
        sub_min += float(r.get("match_min") or 0.0)
        sub_dur += float(r.get("Duration") or 0.0)

        dt_val = int(r["DT"])
        dc_val = int(r["DC"])
        hml_val = int(r["Hml"])
        vhml_val = int(r["VHml"])
        hsr_val = int(r["HSR"])
        vmax_val = float(r["Vmax"])
        dur_val = int(r["Duration"])
        min_val = int(r["match_min"])

        sess_lbl = str(r.get("match_info") or r.get("session_name") or "-")
        if has_match and not sess_lbl.startswith("vs") and sess_lbl != "Partita":
            sess_lbl = f"MATCH: {sess_lbl}"

        day_cell = Paragraph(f"<b>{r['day_label']}</b>", ParagraphStyle("DayP", fontName="Helvetica", fontSize=5.6, leading=6.6, textColor=colors.HexColor("#0F172A")))

        t_rows.append([
            day_cell,
            str(r["week_code"]),
            str(r["team"]),
            sess_lbl,
            f"{min_val}'" if min_val > 0 else "-",
            f"{dur_val}'" if dur_val > 0 else "-",
            f"{dt_val:,}".replace(",", ".") if dt_val > 0 else "-",
            f"{dc_val:,}".replace(",", ".") if dc_val > 0 else "-",
            f"{hml_val:,}".replace(",", ".") if hml_val > 0 else "-",
            f"{vhml_val:,}".replace(",", ".") if vhml_val > 0 else "-",
            f"{hsr_val:,}".replace(",", ".") if hsr_val > 0 else "-",
            f"{vmax_val:.1f}".replace(".", ",") if vmax_val > 0 else "-",
        ])

    if current_w is not None:
        sub_r_idx = len(t_rows)
        t_rows.append([
            Paragraph(f"<b>SUBTOTALE {current_w.upper()}</b>", ParagraphStyle("SubL2", fontName="Helvetica-Bold", fontSize=5.8, textColor=colors.HexColor("#0F172A"))),
            "", "", "",
            Paragraph(f"<b>{int(sub_min)}'</b>", ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1, textColor=colors.HexColor("#0284C7"))),
            Paragraph(f"<b>{int(sub_dur)}'</b>", ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
            Paragraph(f"<b>{int(sub_dt):,}</b>".replace(",", "."), ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
            Paragraph(f"<b>{int(sub_dc):,}</b>".replace(",", "."), ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
            Paragraph(f"<b>{int(sub_hml):,}</b>".replace(",", "."), ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1, textColor=colors.HexColor("#D97706"))),
            Paragraph(f"<b>{int(sub_vhml):,}</b>".replace(",", "."), ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
            Paragraph(f"<b>{int(sub_hsr):,}</b>".replace(",", "."), ParagraphStyle("SubC2", fontName="Helvetica-Bold", fontSize=5.8, alignment=1)),
            "-",
        ])
        t_cmds.extend([
            ("SPAN", (0, sub_r_idx), (3, sub_r_idx)),
            ("BACKGROUND", (0, sub_r_idx), (-1, sub_r_idx), colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, sub_r_idx), (-1, sub_r_idx), "Helvetica-Bold"),
            ("LINEABOVE", (0, sub_r_idx), (-1, sub_r_idx), 0.8, colors.HexColor("#94A3B8")),
            ("LINEBELOW", (0, sub_r_idx), (-1, sub_r_idx), 0.8, colors.HexColor("#94A3B8")),
        ])

    # Larghezza perfetta 808pt: margini laterali puliti di 17pt e colonna Giorno & Data leggibile
    col_w = [92, 74, 84, 142, 44, 44, 56, 54, 56, 54, 54, 54]
    tbl_21 = Table(t_rows, colWidths=col_w)
    tbl_21.setStyle(TableStyle(t_cmds))
    elements.append(tbl_21)
    return elements


def crea_pdf_singolo_atleta_3w(
    player_name: str,
    p_meta: dict,
    df_21: pd.DataFrame,
    week_stats: dict,
    fig: go.Figure,
    ref_week_lbl: str,
) -> bytes:
    """
    Genera il PDF ufficiale FIR dell'Analisi Workload Singolo Atleta (3 Settimane Day-by-Day)
    in formato A4 Orizzontale (Landscape), completo di header FIR, foto atleta,
    card riassuntive delle 3 settimane con delta di variazione, grafico Plotly e tabella dei 21 giorni con subtotali.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=10,
        bottomMargin=12,
    )
    elements = _build_single_athlete_gps_flowables(
        player_name=player_name,
        p_meta=p_meta,
        df_21=df_21,
        week_stats=week_stats,
        fig=fig,
        ref_week_lbl=ref_week_lbl,
        include_charts=True,
    )
    _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • SCHEDA MONITORAGGIO LONGITUDINALE ATLETA")
    return buffer.getvalue()


# ==============================================================================
# SCHEDA ATLETA OVAL & ARCHIVIO GARE OVAL — MOTORE PDF REPORTLAB (A4 LANDSCAPE)
# ==============================================================================

class _PortalHeroCardFlowable(Flowable):
    """Riproduce fedelmente in vettoriale la Hero Card blu scuro/oro della Scheda Atleta del portale."""

    def __init__(self, prof: dict, width: float = 808.0, height: float = 78.0):
        super().__init__()
        self.prof = prof
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        w, h = self.width, self.height

        # Sfondo principale blu scuro FIR con angoli arrotondati
        c.setFillColor(colors.HexColor("#002B49"))
        c.setStrokeColor(colors.HexColor("#031926"))
        c.setLineWidth(0.8)
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=1)

        # Bordo sinistro oro (#D4AF37)
        c.setFillColor(colors.HexColor("#D4AF37"))
        c.roundRect(0, 0, 5.5, h, 3, fill=1, stroke=0)

        p_name = str(self.prof.get("player_name") or "Atleta FIR")
        p_role = str(self.prof.get("role") or "-")
        p_dept = str(self.prof.get("department") or "-")
        p_club = str(self.prof.get("club") or "-")
        p_byear = str(self.prof.get("birth_year") or "-")
        p_age = str(self.prof.get("age_str") or "")
        p_opta = str(self.prof.get("opta_id") or "-")
        is_gin = bool(self.prof.get("is_gin", False))
        c_tot = self.prof.get("career_totals", {})
        photo_b64 = self.prof.get("photo_b64")

        # 1. Foto Atleta incorniciata in oro (o badge iniziali FIR)
        px, py, pw, ph = 14.0, 7.0, 50.0, 64.0
        c.setFillColor(colors.HexColor("#031926"))
        c.setStrokeColor(colors.HexColor("#D4AF37"))
        c.setLineWidth(1.8)
        c.roundRect(px, py, pw, ph, 6, fill=1, stroke=1)

        drew_photo = False
        if photo_b64:
            try:
                im_bytes = base64.b64decode(photo_b64)
                img_reader = ImageReader(BytesIO(im_bytes))
                c.drawImage(img_reader, px + 1.5, py + 1.5, width=pw - 3.0, height=ph - 3.0, preserveAspectRatio=True, anchor="c", mask="auto")
                c.setStrokeColor(colors.HexColor("#D4AF37"))
                c.setLineWidth(1.6)
                c.roundRect(px, py, pw, ph, 6, fill=0, stroke=1)
                drew_photo = True
            except Exception:
                drew_photo = False

        if not drew_photo:
            inits = "".join(part[0] for part in p_name.split()[:2]).upper()
            c.setFillColor(colors.HexColor("#D4AF37"))
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(px + pw / 2.0, py + ph / 2.0 + 2, inits)
            c.setFillColor(colors.HexColor("#93C5FD"))
            c.setFont("Helvetica-Bold", 6.5)
            c.drawCentredString(px + pw / 2.0, py + 10, "FIR")

        # 2. Testi e Pill Badges al centro-sinistra
        tx = px + pw + 14.0
        # Riga superiore: FEDERAZIONE ITALIANA RUGBY • NAZIONALE MAGGIORE + Badge GIN
        c.setFillColor(colors.HexColor("#D4AF37"))
        c.setFont("Helvetica-Bold", 6.8)
        hdr_lbl = "FEDERAZIONE ITALIANA RUGBY  •  NAZIONALE MAGGIORE"
        c.drawString(tx, h - 18, hdr_lbl)
        hdr_w = c.stringWidth(hdr_lbl, "Helvetica-Bold", 6.8)

        gin_txt = "G.I.N. MONITORATO" if is_gin else "ROSTER ALLARGATO"
        gin_w = c.stringWidth(gin_txt, "Helvetica-Bold", 6.2) + 12
        gx = tx + hdr_w + 8
        gy = h - 21.5
        if is_gin:
            c.setFillColor(colors.HexColor("#D4AF37"))
            c.roundRect(gx, gy, gin_w, 11, 5.5, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#031926"))
        else:
            c.setFillColor(colors.HexColor("#1E3A5F"))
            c.roundRect(gx, gy, gin_w, 11, 5.5, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 6.2)
        c.drawCentredString(gx + gin_w / 2.0, gy + 3.2, gin_txt)

        # Nome Giocatore grande in bianco
        c.setFillColor(colors.HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 16.5)
        c.drawString(tx, h - 40, p_name)

        # Riga Pill Badges (Ruolo, Reparto, Club, Anno/Età, Codice Oval)
        bx = tx
        by = 10.0
        bh = 14.0
        pills = [
            (p_role, "#0284C7", "#FFFFFF", True),
            (p_dept, "#0A3A60", "#E0F2FE", False),
            (p_club, "#059669", "#FFFFFF", True),
            (f"Anno {p_byear} ({p_age})", "#07263E", "#CBD5E1", False),
        ]
        for p_txt, bg_h, fg_h, is_b in pills:
            if not p_txt or p_txt == "-":
                continue
            f_name = "Helvetica-Bold" if is_b else "Helvetica"
            pw_pill = c.stringWidth(p_txt, f_name, 7.0) + 12
            c.setFillColor(colors.HexColor(bg_h))
            c.roundRect(bx, by, pw_pill, bh, 4, fill=1, stroke=0)
            c.setFillColor(colors.HexColor(fg_h))
            c.setFont(f_name, 7.0)
            c.drawCentredString(bx + pw_pill / 2.0, by + 4.2, p_txt)
            bx += pw_pill + 5

        c.setFillColor(colors.HexColor("#94A3B8"))
        c.setFont("Helvetica", 7.0)
        c.drawString(bx + 2, by + 4.2, f"Codice Oval: ")
        ow = c.stringWidth("Codice Oval: ", "Helvetica", 7.0)
        c.setFillColor(colors.HexColor("#E2E8F0"))
        c.setFont("Helvetica-Bold", 7.0)
        c.drawString(bx + 2 + ow, by + 4.2, str(p_opta))

        # 3. Box Destro: RIEPILOGO RAPIDO CARRIERA (identico al portale)
        rw = 212.0
        rh = 66.0
        rx = w - rw - 12.0
        ry = 6.0
        c.setFillColor(colors.HexColor("#062338"))
        c.setStrokeColor(colors.HexColor("#1E496B"))
        c.setLineWidth(0.8)
        c.roundRect(rx, ry, rw, rh, 6, fill=1, stroke=1)

        c.setFillColor(colors.HexColor("#D4AF37"))
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(rx + 10, ry + rh - 12, "RIEPILOGO RAPIDO CARRIERA")

        tot_min_disp = f"{int(c_tot.get('total_min', 0)):,}' min".replace(",", ".")
        rows_summary = [
            ("Presenze Totali (CAPS):", f"{c_tot.get('total_caps', 0)}", "#FFFFFF"),
            ("Minuti Totali Giocati:", tot_min_disp, "#38BDF8"),
            ("Gare da Titolare:", f"{c_tot.get('total_starts', 0)} ({c_tot.get('starter_pct', 0)}%)", "#34D399"),
            ("Record Vittorie:", f"{c_tot.get('win_pct', 0)}% W", "#FBBF24"),
        ]
        sy = ry + rh - 23
        for lbl_s, val_s, col_s in rows_summary:
            c.setFillColor(colors.HexColor("#CBD5E1"))
            c.setFont("Helvetica", 7.0)
            c.drawString(rx + 10, sy, lbl_s)
            c.setFillColor(colors.HexColor(col_s))
            c.setFont("Helvetica-Bold", 7.4)
            c.drawRightString(rx + rw - 10, sy, val_s)
            sy -= 11.5

        c.restoreState()


class _PortalKpiRowFlowable(Flowable):
    """Riproduce le 5 Card KPI della Scheda Atleta con spaziatura verticale perfetta per evitare qualsiasi sovrapposizione."""

    def __init__(self, items: list, width: float = 808.0, height: float = 56.0):
        super().__init__()
        self.items = items
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        n = len(self.items)
        gap = 8.0
        card_w = (self.width - gap * (n - 1)) / float(n)
        h = self.height

        for i, item in enumerate(self.items):
            x = i * (card_w + gap)
            c.setFillColor(colors.HexColor("#FFFFFF"))
            c.setStrokeColor(colors.HexColor("#CBD5E1"))
            c.setLineWidth(0.8)
            c.roundRect(x, 0, card_w, h, 6, fill=1, stroke=1)

            # Label in alto (grigio chiaro, font 6.8)
            c.setFillColor(colors.HexColor("#475569"))
            c.setFont("Helvetica", 6.8)
            c.drawString(x + 8, h - 11.5, str(item.get("label", "")))

            # Valore principale grande (nero/blu, font 13.5, y centrato tra label e pill)
            c.setFillColor(colors.HexColor("#0F172A"))
            c.setFont("Helvetica-Bold", 13.5)
            c.drawString(x + 8, h - 27.0, str(item.get("value", "")))

            # Pill verde in basso con delta/sotto-testo (non si sovrappone mai al valore principale)
            raw_sub = str(item.get("sub", ""))
            sub_txt = f"↑ {raw_sub}" if not raw_sub.startswith("↑") else raw_sub
            max_pw = card_w - 16.0

            c.setFont("Helvetica-Bold", 6.0)
            while len(sub_txt) > 4 and (c.stringWidth(sub_txt, "Helvetica-Bold", 6.0) + 10) > max_pw:
                sub_txt = sub_txt[:-4] + "..."

            pw = min(max_pw, c.stringWidth(sub_txt, "Helvetica-Bold", 6.0) + 10)
            c.setFillColor(colors.HexColor("#DCFCE7"))
            c.roundRect(x + 8, 4.5, pw, 12.0, 4, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#15803D"))
            c.drawString(x + 13, 8.0, sub_txt)

        c.restoreState()


class _PortalSectionHeaderFlowable(Flowable):
    """Riproduce l'intestazione di sezione del portale con titolo a sinistra, sottotitolo a destra e linea colorata inferiore."""

    def __init__(self, title: str, subtitle: str, accent_hex: str = "#0066B2", width: float = 808.0, height: float = 18.0):
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.accent_hex = accent_hex
        self.width = width
        self.height = height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        # Icona quadrata colorata a sinistra
        c.setFillColor(colors.HexColor(self.accent_hex))
        c.roundRect(0, 6.5, 8, 8, 2, fill=1, stroke=0)

        # Titolo
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 9.8)
        c.drawString(13, 7.2, self.title)

        # Sottotitolo a destra
        c.setFillColor(colors.HexColor("#64748B"))
        c.setFont("Helvetica", 7.0)
        c.drawRightString(self.width, 7.2, self.subtitle)

        # Linea inferiore colorata a tutta larghezza
        c.setStrokeColor(colors.HexColor(self.accent_hex))
        c.setLineWidth(1.5)
        c.line(0, 1.5, self.width, 1.5)
        c.restoreState()


class _ProgressBarCellFlowable(Flowable):
    """Disegna una barra di progresso grafica dentro una cella di tabella ReportLab, identica a quella HTML del portale."""

    def __init__(
        self,
        width: float,
        height: float,
        pct: float,
        text: str,
        fill_hex: str = "#86EFAC",
        border_hex: str = "#CBD5E1",
        text_hex: str = "#064E3B",
        bg_hex: str = "#F1F5F9",
        border_width: float = 0.6,
    ):
        super().__init__()
        self.width = width
        self.height = height
        self.pct = max(0.0, min(100.0, float(pct or 0.0)))
        self.text = str(text)
        self.fill_hex = fill_hex
        self.border_hex = border_hex
        self.text_hex = text_hex
        self.bg_hex = bg_hex
        self.border_width = border_width

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        w, h = self.width, self.height
        # Sfondo barra
        c.setFillColor(colors.HexColor(self.bg_hex))
        c.roundRect(0, 0, w, h, 2.5, fill=1, stroke=0)

        # Riempimento proporzionale
        if self.pct > 0:
            fw = max(3.0, (w * self.pct) / 100.0)
            c.setFillColor(colors.HexColor(self.fill_hex))
            c.roundRect(0, 0, fw, h, 2.5, fill=1, stroke=0)

        # Bordo barra
        c.setStrokeColor(colors.HexColor(self.border_hex))
        c.setLineWidth(self.border_width)
        c.roundRect(0, 0, w, h, 2.5, fill=0, stroke=1)

        # Testo centrato
        c.setFillColor(colors.HexColor(self.text_hex))
        c.setFont("Helvetica-Bold", 6.6)
        c.drawCentredString(w / 2.0, (h - 6.6) / 2.0 + 1.0, self.text)
        c.restoreState()


class _PillBadgeFlowable(Flowable):
    """Disegna un badge arrotondato dentro una cella di tabella ReportLab."""

    def __init__(
        self,
        width: float,
        height: float,
        text: str,
        bg_hex: str,
        text_hex: str = "#FFFFFF",
        border_hex: str = None,
        align_left: bool = False,
    ):
        super().__init__()
        self.width = width
        self.height = height
        self.text = str(text)
        self.bg_hex = bg_hex
        self.text_hex = text_hex
        self.border_hex = border_hex
        self.align_left = align_left

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        w, h = self.width, self.height
        tw = min(w, c.stringWidth(self.text, "Helvetica-Bold", 6.3) + 12.0)
        bx = 0.0 if self.align_left else (w - tw) / 2.0

        c.setFillColor(colors.HexColor(self.bg_hex))
        if self.border_hex:
            c.setStrokeColor(colors.HexColor(self.border_hex))
            c.setLineWidth(0.8)
            c.roundRect(bx, 0, tw, h, 3.0, fill=1, stroke=1)
        else:
            c.roundRect(bx, 0, tw, h, 3.0, fill=1, stroke=0)

        c.setFillColor(colors.HexColor(self.text_hex))
        c.setFont("Helvetica-Bold", 6.3)
        c.drawCentredString(bx + tw / 2.0, (h - 6.3) / 2.0 + 1.0, self.text)
        c.restoreState()


def crea_pdf_scheda_atleta_oval(
    prof: dict,
    matches_df: pd.DataFrame,
    filter_meta: dict = None,
    sub_code: str = "completo",
    fig_seasons: go.Figure = None,
    fig_teams: go.Figure = None,
    fig_matches: go.Figure = None,
) -> bytes:
    """
    Genera il Dossier PDF Ufficiale FIR A4 Orizzontale con l'ESATTO LAYOUT DEL PORTALE per la Scheda Atleta & Minutaggio Storico Oval:
    - Pagina 1: Hero Card Identità Atleta + 5 Card KPI + Sezione 1 (Tabella Stagioni full-width con barre grafiche e pillole colorate)
    - Pagina 2: Grafico Trend Minuti per Stagione full-width + Sezione 2 (Tabella Squadre/Club a sinistra + Grafico a Ciambella a destra)
    - Pagina 3+: Sezione 3 (Grafico Timeline Minutaggi Partita per Partita + Tabella Dettaglio Gare con barre 80' e bordi rossi Starter)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=12,
        bottomMargin=18,
    )
    elements = []
    filter_meta = filter_meta or {}
    sub_key = str(sub_code or "completo").strip().lower()

    p_name = str(prof.get("player_name") or "Atleta FIR")
    p_role = str(prof.get("role") or "-")
    p_dept = str(prof.get("department") or "-")
    p_club = str(prof.get("club") or "-")
    p_opta = str(prof.get("opta_id") or "-")
    is_gin = bool(prof.get("is_gin", False))
    c_tot = prof.get("career_totals", {})
    s_curr = prof.get("curr_season_totals", {})
    s_df = prof.get("seasons_df", pd.DataFrame())
    t_df = prof.get("teams_df", pd.DataFrame())

    tot_min_s = f"{int(c_tot.get('total_min', 0)):,}".replace(",", ".")
    peak_6w_s = f"{int(c_tot.get('peak_6w_min', 0)):,}".replace(",", ".")

    def _build_top_page_header(section_tag: str):
        return _build_fir_header_table(
            main_title=f"SCHEDA ATLETA & MINUTAGGIO STORICO OVAL • {p_name.upper()}",
            sub_title=f"{section_tag} • Monitoraggio longitudinale (1 Agosto – 30 Luglio)",
            right_line1=f"RUOLO: {p_role.upper()} ({p_dept.upper()})",
            right_line2=f"CLUB: {p_club.upper()}",
            right_line3=f"CODICE OVAL: {p_opta} • {'G.I.N. MONITORATO' if is_gin else 'ROSTER FIR'}",
        )

    def _add_sezione_1_identity_and_seasons():
        elements.append(_build_top_page_header("SEZIONE 1: IDENTITÀ ATLETA, KPI CARRIERA & STAGIONI SPORTIVE"))
        elements.append(Spacer(1, 4))

        # 1. Hero Card Identità Atleta (identica al portale)
        elements.append(_PortalHeroCardFlowable(prof, width=812.0, height=76.0))
        elements.append(Spacer(1, 5))

        # 2. Riga delle 5 Card KPI (identiche al portale)
        kpi_items = [
            {
                "label": "Presenze Totali (CAPS)",
                "value": f"{c_tot.get('total_caps', 0)}",
                "sub": f"{c_tot.get('total_starts', 0)} Titolare • {c_tot.get('total_bench', 0)} Sub",
            },
            {
                "label": "Minuti Totali Oval",
                "value": f"{tot_min_s}' min",
                "sub": f"Media {c_tot.get('avg_min_match', 0)}' a gara",
            },
            {
                "label": "Stagione Attuale (2026/27)",
                "value": f"{int(s_curr.get('minutes', 0))}' min",
                "sub": f"{s_curr.get('caps', 0)} presenze • {s_curr.get('starter_pct', 0)}% Starter",
            },
            {
                "label": "Squadre Rappresentate",
                "value": f"{c_tot.get('teams_count', 0)} Team",
                "sub": ", ".join(c_tot.get("teams_list", [])[:2]) if c_tot.get("teams_list") else "Club / Naz.",
            },
            {
                "label": "Record Vittorie Carriera",
                "value": f"{c_tot.get('win_pct', 0)}%",
                "sub": f"{c_tot.get('total_wins', 0)} V • {c_tot.get('total_losses', 0)} S • {c_tot.get('total_draws', 0)} P",
            },
        ]
        elements.append(_PortalKpiRowFlowable(kpi_items, width=808.0, height=56.0))
        elements.append(Spacer(1, 6))

        # 3. SEZIONE 1: Minutaggi & Presenze per Stagione (1 Agosto – 30 Luglio) a tutta larghezza (812pt)
        elements.append(
            _PortalSectionHeaderFlowable(
                "Minutaggi & Presenze per Stagione (1 Agosto – 30 Luglio)",
                "Analisi longitudinale completa delle stagioni sportive registrate in archivio Oval",
                accent_hex="#0066B2",
                width=812.0,
                height=18.0,
            )
        )
        elements.append(Spacer(1, 3))

        if not s_df.empty:
            max_s_min = max(int(s_df["minutes"].max()), 1)
            max_s_caps = max(int(s_df["caps"].max()), 1)
            n_s_body = len(s_df) + 1  # righe stagioni + riga TOTALE CARRIERA
            # Calibra l'altezza riga in modo che la Tabella Stagioni entri sempre perfettamente nella Pagina 1 (max 340pt disponibili)
            s_row_h = max(13.5, min(18.5, 330.0 / float(max(n_s_body, 1))))
            s_bar_h = max(10.0, min(13.0, s_row_h - 4.0))
            s_pad_v = max(1.0, min(2.4, (s_row_h - s_bar_h) / 2.0))
            s_font_sz = 6.3 if n_s_body > 14 else 6.8

            s_headers = [
                "STAGIONE",
                "SQUADRA / CLUB",
                "CAPS",
                "TITOLARE",
                "SUB (PAN)",
                "MINUTI TOTALI",
                "MEDIA MIN",
                "MAX MINUTI 6 SETT.",
            ]
            s_data = [s_headers]
            s_cmds = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
                ("BACKGROUND", (7, 0), (7, 0), colors.HexColor("#0B1F33")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 6.6),
                ("LEADING", (0, 0), (-1, 0), 7.8),
                ("ALIGN", (0, 0), (1, 0), "LEFT"),
                ("ALIGN", (2, 0), (-1, 0), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), s_pad_v),
                ("BOTTOMPADDING", (0, 0), (-1, -1), s_pad_v),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#002B49")),
            ]

            for _, sr in s_df.iterrows():
                r_idx = len(s_data)
                s_lbl = str(sr.get("season", ""))
                is_sub = bool(sr.get("is_subtotal", False))
                is_cur_s = ("2026/27" in s_lbl) and not is_sub
                tm_name = str(sr.get("team", ""))

                if is_sub:
                    s_cell = Paragraph(
                        f"<font size='{s_font_sz}' color='#002B49'><b>{s_lbl}</b></font>",
                        ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2),
                    )
                    team_cell = Paragraph(
                        f"<font size='{s_font_sz - 0.2}' color='#475569'><b>{tm_name}</b></font>",
                        ParagraphStyle(f"TM_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz - 0.2, leading=s_font_sz + 1.0),
                    )
                else:
                    if is_cur_s:
                        s_cell = Paragraph(
                            f"<font size='{s_font_sz}' color='#0F172A'><b>{s_lbl}</b></font> "
                            f"<font size='5.5' color='#B45309'><b>[IN CORSO]</b></font>",
                            ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2),
                        )
                    else:
                        s_cell = Paragraph(
                            f"<font size='{s_font_sz}' color='#0F172A'><b>{s_lbl}</b></font>",
                            ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2),
                        )
                    tm_bg = "#0066B2" if "ital" in tm_name.lower() else "#059669"
                    team_cell = _PillBadgeFlowable(185.0, s_bar_h, tm_name, bg_hex=tm_bg, text_hex="#FFFFFF", align_left=True)

                c_val = int(sr.get("caps", 0))
                c_pct = (c_val / float(max_s_caps)) * 100.0 if c_val > 0 else 0.0
                c_bar = _ProgressBarCellFlowable(
                    width=76.0,
                    height=s_bar_h,
                    pct=c_pct,
                    text=str(c_val),
                    fill_hex="#BAE6FD",
                    border_hex="#CBD5E1",
                    text_hex="#0369A1",
                )

                m_val = int(sr.get("minutes", 0))
                m_disp = f"{m_val:,}' min".replace(",", ".")
                m_pct = (m_val / float(max_s_min)) * 100.0 if m_val > 0 else 0.0
                m_bar = _ProgressBarCellFlowable(
                    width=118.0,
                    height=s_bar_h,
                    pct=m_pct,
                    text=m_disp,
                    fill_hex="#A7F3D0",
                    border_hex="#CBD5E1",
                    text_hex="#064E3B",
                )

                m6w_v = sr.get("max_6w_min")
                if m6w_v is not None and pd.notna(m6w_v) and str(m6w_v) not in ("-", "None", "nan"):
                    m6w_cell = _PillBadgeFlowable(
                        width=96.0,
                        height=s_bar_h,
                        text=f"{int(float(m6w_v))}' min",
                        bg_hex="#002B49",
                        text_hex="#FFFFFF",
                        border_hex="#D4AF37",
                    )
                else:
                    m6w_cell = "-"

                st_str = f"{int(sr.get('starts', 0))} ({float(sr.get('starter_pct', 0)):.0f}%)"
                bench_str = str(int(sr.get("bench", 0)))
                avg_str = f"{float(sr.get('avg_minutes', 0)):.1f}'"

                s_data.append([s_cell, team_cell, c_bar, st_str, bench_str, m_bar, avg_str, m6w_cell])
                s_cmds.extend([
                    ("FONTSIZE", (0, r_idx), (-1, r_idx), s_font_sz),
                    ("LEADING", (0, r_idx), (-1, r_idx), s_font_sz + 1.2),
                    ("ALIGN", (0, r_idx), (1, r_idx), "LEFT"),
                    ("ALIGN", (2, r_idx), (-1, r_idx), "CENTER"),
                    ("FONTNAME", (3, r_idx), (3, r_idx), "Helvetica-Bold"),
                    ("FONTNAME", (6, r_idx), (6, r_idx), "Helvetica-Bold"),
                ])
                if is_sub:
                    s_cmds.extend([
                        ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F1F5F9")),
                        ("LINEABOVE", (0, r_idx), (-1, r_idx), 1.0, colors.HexColor("#94A3B8")),
                        ("LINEBELOW", (0, r_idx), (-1, r_idx), 1.2, colors.HexColor("#CBD5E1")),
                        ("FONTNAME", (3, r_idx), (4, r_idx), "Helvetica-Bold"),
                    ])
                elif is_cur_s:
                    s_cmds.extend([
                        ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FEF3C7")),
                        ("BOX", (0, r_idx), (-1, r_idx), 1.3, colors.HexColor("#D97706")),
                    ])
                else:
                    s_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FFFFFF")))

            # Riga TOTALE CARRIERA (identica al portale)
            tot_idx = len(s_data)
            tot_m6w_badge = _PillBadgeFlowable(
                width=96.0,
                height=s_bar_h,
                text=f"{peak_6w_s}' min",
                bg_hex="#D4AF37",
                text_hex="#002B49",
            )
            s_data.append([
                "TOTALE CARRIERA",
                f"{c_tot.get('teams_count', 0)} Squadre (Club + Naz.)",
                f"{c_tot.get('total_caps', 0)} CAPS",
                f"{c_tot.get('total_starts', 0)} ({c_tot.get('starter_pct', 0):.0f}%)",
                f"{c_tot.get('total_bench', 0)}",
                f"{tot_min_s}' min",
                f"{c_tot.get('avg_min_match', 0):.1f}'",
                tot_m6w_badge,
            ])
            s_cmds.extend([
                ("BACKGROUND", (0, tot_idx), (-1, tot_idx), colors.HexColor("#E2E8F0")),
                ("LINEABOVE", (0, tot_idx), (-1, tot_idx), 2.0, colors.HexColor("#002B49")),
                ("FONTNAME", (0, tot_idx), (-1, tot_idx), "Helvetica-Bold"),
                ("FONTSIZE", (0, tot_idx), (-1, tot_idx), s_font_sz),
                ("LEADING", (0, tot_idx), (-1, tot_idx), s_font_sz + 1.2),
                ("TEXTCOLOR", (0, tot_idx), (1, tot_idx), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (2, tot_idx), (2, tot_idx), colors.HexColor("#0369A1")),
                ("TEXTCOLOR", (5, tot_idx), (5, tot_idx), colors.HexColor("#064E3B")),
                ("ALIGN", (0, tot_idx), (1, tot_idx), "LEFT"),
                ("ALIGN", (2, tot_idx), (-1, tot_idx), "CENTER"),
            ])

            # Larghezze calibrate esattamente a 812pt + rowHeights calibrate per restare nella Pagina 1
            col_w_s = [96, 198, 88, 86, 62, 130, 66, 86]
            row_h_s = [16.5] + [s_row_h] * n_s_body
            tbl_s = Table(s_data, colWidths=col_w_s, rowHeights=row_h_s, repeatRows=1)
            tbl_s.setStyle(TableStyle(s_cmds))
            elements.append(tbl_s)

    def _add_sezione_2_charts_and_teams():
        elements.append(_build_top_page_header("SEZIONE 2: TREND STAGIONALE & SQUADRE / CLUB IN CARRIERA"))
        elements.append(Spacer(1, 5))

        # 1. Grafico Trend Minuti per Stagione a tutta larghezza (812pt, come nel portale)
        if fig_seasons is not None:
            img_s = fig_to_rl_image(fig_seasons, width=812, height=190)
            if img_s:
                elements.append(img_s)
                elements.append(Spacer(1, 8))

        # 2. SEZIONE 2: Squadre & Club con cui ha giocato in Carriera (Tabella a sinistra + Ciambella a destra)
        elements.append(
            _PortalSectionHeaderFlowable(
                "Squadre & Club con cui ha giocato in Carriera",
                "Ripartizione minuti tra Club di appartenenza e Nazionale Italiana",
                accent_hex="#059669",
                width=812.0,
            )
        )
        elements.append(Spacer(1, 5))

        if not t_df.empty:
            t_headers = ["SQUADRA / CLUB", "PERIODO", "CAPS", "TITOLARE", "MINUTI TOTALI", "RECORD (W-L)"]
            t_data = [t_headers]
            t_cmds = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 6.8),
                ("LEADING", (0, 0), (-1, 0), 8.2),
                ("ALIGN", (0, 0), (1, 0), "LEFT"),
                ("ALIGN", (2, 0), (-1, 0), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 4.0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.0),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#0F172A")),
            ]

            for _, tr in t_df.iterrows():
                r_idx = len(t_data)
                tm_n = str(tr.get("team_name", ""))
                is_nat = "ital" in tm_n.lower()
                tm_col = "#0066B2" if is_nat else "#059669"

                w_pill = _PillBadgeFlowable(
                    width=94.0,
                    height=13.0,
                    text=f"{int(tr.get('wins', 0))}V - {int(tr.get('losses', 0))}S ({float(tr.get('win_pct', 0)):.0f}%)",
                    bg_hex="#DCFCE7",
                    text_hex="#15803D",
                )
                t_min_disp = f"{int(tr.get('minutes', 0)):,}' min".replace(",", ".")

                t_data.append([
                    tm_n,
                    str(tr.get("period", "-")),
                    str(int(tr.get("caps", 0))),
                    f"{int(tr.get('starts', 0))} ({float(tr.get('starter_pct', 0)):.0f}%)",
                    t_min_disp,
                    w_pill,
                ])
                t_cmds.extend([
                    ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FFFFFF")),
                    ("FONTSIZE", (0, r_idx), (-1, r_idx), 7.2),
                    ("LEADING", (0, r_idx), (-1, r_idx), 8.6),
                    ("ALIGN", (0, r_idx), (1, r_idx), "LEFT"),
                    ("ALIGN", (2, r_idx), (-1, r_idx), "CENTER"),
                    ("FONTNAME", (0, r_idx), (0, r_idx), "Helvetica-Bold"),
                    ("TEXTCOLOR", (0, r_idx), (0, r_idx), colors.HexColor(tm_col)),
                    ("TEXTCOLOR", (1, r_idx), (1, r_idx), colors.HexColor("#64748B")),
                    ("FONTNAME", (2, r_idx), (2, r_idx), "Helvetica-Bold"),
                    ("FONTNAME", (4, r_idx), (4, r_idx), "Helvetica-Bold"),
                    ("TEXTCOLOR", (4, r_idx), (4, r_idx), colors.HexColor("#064E3B")),
                ])

            # Tabella Squadre (500pt) + Grafico a Ciambella (300pt) affiancati come nel portale (col_t1 1.6 : col_t2 1.0)
            tbl_teams = Table(t_data, colWidths=[132, 68, 48, 74, 82, 96])
            tbl_teams.setStyle(TableStyle(t_cmds))

            img_pie = fig_to_rl_image(fig_teams, width=298, height=185) if fig_teams is not None else ""
            if img_pie:
                layout_t = Table([[tbl_teams, "", img_pie]], colWidths=[500, 14, 298])
                layout_t.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                elements.append(layout_t)
            else:
                elements.append(tbl_teams)

    def _add_sezione_3_gare():
        f_stag = filter_meta.get("season", "Tutte le Stagioni")
        f_team = filter_meta.get("team", "Tutte le Squadre")
        f_imp = filter_meta.get("starter", "Tutti")
        f_out = filter_meta.get("outcome", "Tutti")
        n_m = len(matches_df) if matches_df is not None and not matches_df.empty else 0
        tot_m_filt = int(pd.to_numeric(matches_df["minutes"], errors="coerce").fillna(0).sum()) if n_m > 0 else 0

        elements.append(
            _build_fir_header_table(
                main_title=f"SCHEDA ATLETA OVAL • DETTAGLIO GARE DISPUTATE: {p_name.upper()}",
                sub_title=f"Filtri attivi: Stagione={f_stag} • Squadra={f_team} • Impiego={f_imp} • Risultato={f_out}",
                right_line1=f"GARE VISUALIZZATE: {n_m}",
                right_line2=f"MINUTI TOTALI: {tot_m_filt:,}'".replace(",", "."),
                right_line3=f"MEDIA: {(tot_m_filt / n_m if n_m else 0):.1f}' / GARA",
            )
        )
        elements.append(Spacer(1, 5))

        elements.append(
            _PortalSectionHeaderFlowable(
                "Dettaglio Gare Disputate & Minutaggi Singola Partita",
                f"Ispezione di tutte le partite giocate ({n_m} gare • Verde=Vittoria, Rosso=Sconfitta)",
                accent_hex="#D97706",
                width=812.0,
            )
        )
        elements.append(Spacer(1, 4))

        # Grafico Timeline Partita per Partita a tutta larghezza (812pt)
        if fig_matches is not None and n_m > 0:
            img_m = fig_to_rl_image(fig_matches, width=812, height=150)
            if img_m:
                elements.append(img_m)
                elements.append(Spacer(1, 5))

        if matches_df is None or matches_df.empty:
            elements.append(Paragraph("<i>Nessuna partita trovata con i filtri selezionati.</i>", getSampleStyleSheet()["Normal"]))
            return

        # Tabella a 13 colonne identica al portale con barra grafica minuti (bordo rosso Starter) e pillole Impiego/Risultato
        m_headers = [
            "DATA", "PARTITA (OVAL)", "SQUADRA", "AVVERSARIO",
            "H/A", "MINUTI", "IMPIEGO", "RISULTATO",
            "CARRIES", "METRI ADV", "PLACCAGGI", "TURNOVER", "FALLI",
        ]
        m_data = [m_headers]
        m_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 6.2),
            ("LEADING", (0, 0), (-1, 0), 7.5),
            ("ALIGN", (0, 0), (3, 0), "LEFT"),
            ("ALIGN", (4, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0),
            ("LEFTPADDING", (0, 0), (-1, -1), 3.0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3.0),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
            ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#002B49")),
        ]

        for _, mr in matches_df.iterrows():
            r_idx = len(m_data)
            m_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FFFFFF")))

            d_disp = str(mr.get("date_disp") or mr.get("match_date") or "")[:10]
            g_disp = str(mr.get("game") or "")[:30]
            t_disp = str(mr.get("team") or "")[:20]
            opp_disp = str(mr.get("opponent") or "")[:20]
            ha_disp = str(mr.get("ha") or "-")

            m_raw = pd.to_numeric(mr.get("minutes", 0), errors="coerce")
            m_val = int(round(float(0.0 if pd.isna(m_raw) else m_raw)))
            m_pct = min(100.0, (m_val / 80.0) * 100.0)
            is_st = bool(mr.get("is_starter", False))

            # Cella MINUTI con barra grafica su 80' e bordo rosso per TITOLARE (identica al portale)
            min_flow = _ProgressBarCellFlowable(
                width=52.0,
                height=12.5,
                pct=m_pct,
                text=f"{m_val}'",
                fill_hex="#93C5FD" if is_st else "#BAE6FD",
                border_hex="#EF4444" if is_st else "#93C5FD",
                text_hex="#0F172A",
                bg_hex="#F8FAFC",
                border_width=1.2 if is_st else 0.6,
            )

            jer_raw = pd.to_numeric(mr.get("jersey", 0), errors="coerce")
            jer_val = int(round(float(0.0 if pd.isna(jer_raw) else jer_raw)))
            jer_str = f" #{jer_val}" if jer_val > 0 else ""

            if is_st:
                imp_flow = _PillBadgeFlowable(
                    width=66.0,
                    height=12.5,
                    text=f"TITOLARE{jer_str}",
                    bg_hex="#FEE2E2",
                    text_hex="#B91C1C",
                    border_hex="#FECACA",
                )
            else:
                imp_flow = _PillBadgeFlowable(
                    width=66.0,
                    height=12.5,
                    text=f"FINISHER{jer_str}",
                    bg_hex="#E0F2FE",
                    text_hex="#0369A1",
                )

            res_str = str(mr.get("result") or "").strip()
            out_str = str(mr.get("outcome") or "-")
            if res_str:
                r_bg = "#DCFCE7" if out_str == "WIN" else ("#FEE2E2" if out_str == "LOSS" else "#F1F5F9")
                r_fg = "#15803D" if out_str == "WIN" else ("#B91C1C" if out_str == "LOSS" else "#475569")
                res_flow = _PillBadgeFlowable(width=50.0, height=12.5, text=res_str, bg_hex=r_bg, text_hex=r_fg)
            else:
                res_flow = "-"

            car_v = int(float(pd.to_numeric(mr.get("carries", 0), errors="coerce") or 0))
            pcm_v = float(pd.to_numeric(mr.get("pcm", 0.0), errors="coerce") or 0.0)
            tck_v = int(float(pd.to_numeric(mr.get("tackles", 0), errors="coerce") or 0))
            trn_v = int(float(pd.to_numeric(mr.get("turnovers_won", 0), errors="coerce") or 0))
            pen_v = int(float(pd.to_numeric(mr.get("penalties", 0), errors="coerce") or 0))

            m_data.append([
                d_disp, g_disp, t_disp, opp_disp,
                ha_disp, min_flow, imp_flow, res_flow,
                str(car_v), f"{pcm_v:.1f} m", str(tck_v), str(trn_v), str(pen_v),
            ])

            m_cmds.extend([
                ("FONTSIZE", (0, r_idx), (-1, r_idx), 6.2),
                ("LEADING", (0, r_idx), (-1, r_idx), 7.4),
                ("ALIGN", (0, r_idx), (3, r_idx), "LEFT"),
                ("ALIGN", (4, r_idx), (-1, r_idx), "CENTER"),
                ("FONTNAME", (0, r_idx), (1, r_idx), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, r_idx), (0, r_idx), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (1, r_idx), (1, r_idx), colors.HexColor("#0066B2")),
                ("TEXTCOLOR", (2, r_idx), (2, r_idx), colors.HexColor("#334155")),
                ("TEXTCOLOR", (3, r_idx), (3, r_idx), colors.HexColor("#475569")),
                ("FONTNAME", (11, r_idx), (11, r_idx), "Helvetica-Bold"),
                ("TEXTCOLOR", (11, r_idx), (11, r_idx), colors.HexColor("#0369A1")),
                ("TEXTCOLOR", (12, r_idx), (12, r_idx), colors.HexColor("#B91C1C")),
            ])
            if ha_disp == "Home":
                m_cmds.append(("BACKGROUND", (4, r_idx), (4, r_idx), colors.HexColor("#EFF6FF")))

        # Larghezze calibrate esattamente a 812pt per le 13 colonne del portale
        col_w_m = [52, 146, 94, 94, 32, 60, 74, 58, 42, 46, 44, 38, 32]
        tbl_m = Table(m_data, colWidths=col_w_m, repeatRows=1)
        tbl_m.setStyle(TableStyle(m_cmds))
        elements.append(tbl_m)

    if "sintesi" in sub_key or "carriera" in sub_key:
        _add_sezione_1_identity_and_seasons()
        elements.append(PageBreak())
        _add_sezione_2_charts_and_teams()
    elif "solo_gare" in sub_key or "gare" in sub_key:
        _add_sezione_3_gare()
    else:
        _add_sezione_1_identity_and_seasons()
        elements.append(PageBreak())
        _add_sezione_2_charts_and_teams()
        elements.append(PageBreak())
        _add_sezione_3_gare()

    _build_pdf_with_footer(doc, elements, brand=f"FEDERAZIONE ITALIANA RUGBY • SCHEDA CARRIERA OVAL: {p_name.upper()}")
    return buffer.getvalue()


def crea_pdf_archivio_oval(
    filt_df: pd.DataFrame,
    view_mode: str = "Sintesi Minutaggio & Match",
    filter_meta: dict = None,
    sub_code: str = "archivio_150",
) -> bytes:
    """
    Genera il Report PDF Ufficiale FIR A4 Orizzontale per l'Archivio Gare Oval & Statistiche:
    - Calibra dinamicamente le colonne in base al Gruppo Statistiche selezionato (view_mode)
    - Garantisce impaginazione multi-pagina pulita con intestazione ripetuta (repeatRows=1)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=12,
        bottomMargin=18,
    )
    elements = []
    filter_meta = filter_meta or {}
    sub_key = str(sub_code or "archivio_150").strip().lower()

    f_player = filter_meta.get("player", "Tutti i Giocatori")
    f_team = filter_meta.get("team", "Tutte le Squadre")
    f_dfrom = filter_meta.get("d_from", "") or "Inizio Archivio"
    f_dto = filter_meta.get("d_to", "") or "Oggi"

    n_total = len(filt_df) if filt_df is not None and not filt_df.empty else 0
    if "50" in sub_key:
        work_df = filt_df.head(50).copy() if n_total > 0 else pd.DataFrame()
    elif "150" in sub_key:
        work_df = filt_df.head(150).copy() if n_total > 0 else pd.DataFrame()
    else:
        work_df = filt_df.head(500).copy() if n_total > 0 else pd.DataFrame()

    n_starts = int(pd.to_numeric(filt_df.get("MatchesStarted", 0), errors="coerce").fillna(0).sum()) if n_total > 0 and "MatchesStarted" in filt_df.columns else 0
    tot_min = int(pd.to_numeric(filt_df.get("Min", 0), errors="coerce").fillna(0).sum()) if n_total > 0 and "Min" in filt_df.columns else 0
    avg_min = float(pd.to_numeric(filt_df.get("Min", 0), errors="coerce").fillna(0).mean()) if n_total > 0 and "Min" in filt_df.columns else 0.0
    tot_carries = int(pd.to_numeric(filt_df.get("TotalCarries", 0), errors="coerce").fillna(0).sum()) if n_total > 0 and "TotalCarries" in filt_df.columns else 0
    tot_tackles = int(pd.to_numeric(filt_df.get("TotalTackleAttempts", 0), errors="coerce").fillna(0).sum()) if n_total > 0 and "TotalTackleAttempts" in filt_df.columns else 0

    elements.append(
        _build_fir_header_table(
            main_title=f"ARCHIVIO UFFICIALE GARE OVAL & STATISTICHE • {view_mode.upper()}",
            sub_title=f"Giocatore: {f_player} • Squadra: {f_team} • Periodo: {f_dfrom} → {f_dto}",
            right_line1=f"RECORD FILTRATI: {n_total:,} (ESPORTATI: {len(work_df):,})",
            right_line2=f"MINUTI TOTALI: {tot_min:,}' ({tot_min/80:.1f} GARE EQ.)",
            right_line3=f"MEDIA MIN/GARA: {avg_min:.1f}'",
        )
    )
    elements.append(Spacer(1, 4))

    # Barra 5 KPI (812pt totali)
    st_pct = round(n_starts / n_total * 100) if n_total > 0 else 0
    k_boxes = []
    for k_title, k_val, k_sub, k_col in [
        ("PARTITE GIOCATE", f"{n_total:,}", f"Titolare: {n_starts} ({st_pct}%)", "#0066B2"),
        ("MINUTI TOTALI", f"{tot_min:,}' min", f"Equiv. a {tot_min/80:.1f} gare da 80'", "#B45309"),
        ("MEDIA MINUTI / GARA", f"{avg_min:.1f}' min", "Minutaggio medio", "#059669"),
        ("CARRIES TOTALI", f"{tot_carries:,}", f"Media: {(tot_carries/n_total if n_total else 0):.1f}/gara", "#0284C7"),
        ("PLACCAGGI TENTATI", f"{tot_tackles:,}", f"Media: {(tot_tackles/n_total if n_total else 0):.1f}/gara", "#DC2626"),
    ]:
        k_boxes.append(
            Paragraph(
                f"<font size='5.8' color='{k_col}'><b>{k_title}</b></font><br/>"
                f"<font size='10' color='#0F172A'><b>{k_val}</b></font><br/>"
                f"<font size='5.8' color='#475569'>{k_sub}</font>",
                ParagraphStyle(f"ArchK_{k_title[:4]}", fontName="Helvetica", leading=8.0, alignment=1),
            )
        )
    kpi_tbl = Table([k_boxes], colWidths=[162, 163, 162, 162, 163])
    kpi_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    elements.append(kpi_tbl)
    elements.append(Spacer(1, 5))

    if work_df.empty:
        elements.append(Paragraph("<i>Nessun record presente con i filtri selezionati.</i>", getSampleStyleSheet()["Normal"]))
        _build_pdf_with_footer(doc, elements, brand="FEDERAZIONE ITALIANA RUGBY • ARCHIVIO GARE OVAL")
        return buffer.getvalue()

    # Configurazione colonne dinamiche per Gruppo Statistiche (somma colWidths = 812pt)
    base_spec = [
        ("match_date", "DATA", 44, "str"),
        ("fir_player_name", "GIOCATORE FIR", 98, "left_bold"),
        ("teamName", "SQUADRA", 78, "left"),
        ("game", "PARTITA (OVAL)", 118, "left"),
        ("result", "RIS.", 42, "res"),
        ("pos", "RUOLO", 34, "str"),
        ("Jersey", "MAG.", 26, "int"),
        ("MatchesStarted", "TIT.", 26, "starter"),
        ("Min", "MIN", 30, "min"),
    ]  # Totale base = 496pt -> Restano 316pt per le 7-9 colonne statistiche

    if view_mode == "Attacco, Carries & Contatto":
        extra_spec = [
            ("TotalCarries", "CARRIES", 40, "int"),
            ("TotalCarriesInContact", "CONTATTO", 42, "int"),
            ("PostContactMeters", "METRI ADV", 44, "float1"),
            ("%DominantCarry", "% DOM.", 38, "float1"),
            ("%CrossedGainline", "% GAIN.", 38, "float1"),
            ("DefenderBeaten", "DEF. BEAT", 40, "int"),
            ("Drive", "DRIVE", 36, "int"),
            ("PickAndGo", "PICK&GO", 38, "int"),
        ]
    elif view_mode == "Difesa, Placcaggi & Turnover":
        extra_spec = [
            ("TotalTackleAttempts", "PLACC. TENT.", 46, "int"),
            ("MissedTackle", "PLACC. MANC.", 46, "int"),
            ("TackleSuccessRate", "% PLACC.", 42, "float1"),
            ("%DominantTackles", "% DOM. TCK", 44, "float1"),
            ("TotalTurnoversWon", "TURN. VINTI", 46, "int"),
            ("TotalTurnoversConceded", "TURN. CONC.", 46, "int"),
            ("TotalPenalties", "FALLI", 46, "int"),
        ]
    elif view_mode == "Ruck & Breakdown":
        extra_spec = [
            ("TotalRuckEntries", "RUCK TOT.", 46, "int"),
            ("TotalEffectiveRuckEntries", "RUCK EFF.", 46, "int"),
            ("AttackingRuckEntries", "RUCK ATT.", 46, "int"),
            ("AttackingRuckCleanedOut", "CLEAN OUT", 46, "int"),
            ("AttackingRuckSecured", "SECURED", 44, "int"),
            ("AttackRuckEntry1st", "1° ARRIVO", 44, "int"),
            ("AttackRuckEntry2nd", "2° ARRIVO", 44, "int"),
        ]
    elif view_mode == "Passaggi, Calci & Touche":
        extra_spec = [
            ("TotalPasses", "PASSAGGI", 46, "int"),
            ("CompletePass", "COMPLETI", 46, "int"),
            ("PassError", "ERR. PASS", 44, "int"),
            ("%PassSuccess", "% PASS", 42, "float1"),
            ("TotalKicks", "CALCI TOT.", 46, "int"),
            ("KickBox", "BOX KICK", 46, "int"),
            ("TotalLineoutThrows", "TOUCHE", 46, "int"),
        ]
    else:
        # Default: Sintesi Minutaggio & Match (usato anche come vista riepilogativa PDF per Tutte le Colonne)
        extra_spec = [
            ("TotalCarries", "CARRIES", 38, "int"),
            ("PostContactMeters", "METRI ADV", 42, "float1"),
            ("DefenderBeaten", "DEF. BEAT", 38, "int"),
            ("TotalTackleAttempts", "PLACCAGGI", 42, "int"),
            ("MissedTackle", "MANCATI", 38, "int"),
            ("TackleSuccessRate", "% PLACC.", 38, "float1"),
            ("TotalRuckEntries", "RUCK", 40, "int"),
            ("TotalTurnoversWon", "TURNOVER", 40, "int"),
        ]

    full_spec = base_spec + extra_spec
    headers = [s[1] for s in full_spec]
    col_widths = [s[2] for s in full_spec]

    t_data = [headers]
    t_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#031926")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 5.4),
        ("LEADING", (0, 0), (-1, 0), 6.5),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2.0),
        ("LINEAFTER", (8, 0), (8, -1), 1.1, colors.HexColor("#0066B2")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#031926")),
    ]

    for _, r in work_df.iterrows():
        r_idx = len(t_data)
        bg_c = "#FFFFFF" if r_idx % 2 == 1 else "#F8FAFC"
        t_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor(bg_c)))

        row_cells = []
        for c_idx, (col_key, _, _, fmt_type) in enumerate(full_spec):
            raw_v = r.get(col_key)
            if fmt_type == "str":
                val_s = str(raw_v if pd.notna(raw_v) else "")[:12]
            elif fmt_type == "left_bold":
                val_s = str(raw_v if pd.notna(raw_v) else "")[:22]
                t_cmds.append(("ALIGN", (c_idx, r_idx), (c_idx, r_idx), "LEFT"))
                t_cmds.append(("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
            elif fmt_type == "left":
                max_len = 24 if col_key == "game" else 16
                val_s = str(raw_v if pd.notna(raw_v) else "")[:max_len]
                t_cmds.append(("ALIGN", (c_idx, r_idx), (c_idx, r_idx), "LEFT"))
            elif fmt_type == "res":
                val_s = str(raw_v if pd.notna(raw_v) else "")[:10].strip()
                if val_s.upper().startswith("W"):
                    t_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#DCFCE7")))
                    t_cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#15803D")))
                    t_cmds.append(("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
                elif val_s.upper().startswith("L"):
                    t_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#FEE2E2")))
                    t_cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#B91C1C")))
                    t_cmds.append(("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
            elif fmt_type == "starter":
                num_v = pd.to_numeric(raw_v, errors="coerce")
                is_st = (not pd.isna(num_v)) and float(num_v) >= 1
                val_s = "SI" if is_st else "SUB"
                if is_st:
                    t_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#FEE2E2")))
                    t_cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#991B1B")))
                    t_cmds.append(("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
            elif fmt_type == "min":
                num_v = pd.to_numeric(raw_v, errors="coerce")
                m_i = int(round(float(0.0 if pd.isna(num_v) else num_v)))
                val_s = f"{m_i}'"
                t_cmds.append(("FONTNAME", (c_idx, r_idx), (c_idx, r_idx), "Helvetica-Bold"))
                if m_i > 0:
                    t_cmds.append(("BACKGROUND", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#E0F2FE")))
                    t_cmds.append(("TEXTCOLOR", (c_idx, r_idx), (c_idx, r_idx), colors.HexColor("#0369A1")))
            elif fmt_type == "int":
                num_v = pd.to_numeric(raw_v, errors="coerce")
                v_i = int(round(float(0.0 if pd.isna(num_v) else num_v)))
                val_s = str(v_i) if (v_i > 0 or col_key != "Jersey") else "-"
            elif fmt_type == "float1":
                num_v = pd.to_numeric(raw_v, errors="coerce")
                v_f = float(0.0 if pd.isna(num_v) else num_v)
                val_s = f"{v_f:.1f}"
            else:
                val_s = str(raw_v if pd.notna(raw_v) else "")
            row_cells.append(val_s)

        t_cmds.extend([
            ("FONTSIZE", (0, r_idx), (-1, r_idx), 5.3),
            ("LEADING", (0, r_idx), (-1, r_idx), 6.4),
            ("ALIGN", (0, r_idx), (0, r_idx), "CENTER"),
            ("ALIGN", (4, r_idx), (-1, r_idx), "CENTER"),
        ])
        t_data.append(row_cells)

    tbl_arch = Table(t_data, colWidths=col_widths, repeatRows=1)
    tbl_arch.setStyle(TableStyle(t_cmds))
    elements.append(tbl_arch)

    _build_pdf_with_footer(doc, elements, brand=f"FEDERAZIONE ITALIANA RUGBY • ARCHIVIO GARE OVAL ({view_mode.upper()})")
    return buffer.getvalue()


# ==============================================================================
# DOSSIER MULTI-GIOCATORE G.I.N. (BATCH PDF A4 LANDSCAPE)
# ==============================================================================

def _build_single_athlete_oval_flowables(prof: dict, fig_seasons=None, include_charts: bool = True) -> list:
    """Costruisce le 2 pagine Flowables per la scheda Carriera, Stagioni & Squadre Oval dell'atleta."""
    elements = []
    p_name = str(prof.get("player_name") or "Atleta FIR")
    p_role = str(prof.get("role") or "-")
    p_dept = str(prof.get("department") or "-")
    p_club = str(prof.get("club") or "-")
    p_opta = str(prof.get("opta_id") or "-")
    is_gin = bool(prof.get("is_gin", False))
    c_tot = prof.get("career_totals", {})
    s_curr = prof.get("curr_season_totals", {})
    s_df = prof.get("seasons_df", pd.DataFrame())
    t_df = prof.get("teams_df", pd.DataFrame())

    tot_min_s = f"{int(c_tot.get('total_min', 0)):,}".replace(",", ".")
    peak_6w_s = f"{int(c_tot.get('peak_6w_min', 0)):,}".replace(",", ".")

    def _build_top_hdr(sec_tag: str):
        return _build_fir_header_table(
            main_title=f"SCHEDA ATLETA & MINUTAGGIO STORICO OVAL • {p_name.upper()}",
            sub_title=f"{sec_tag} • Monitoraggio longitudinale (1 Agosto – 30 Luglio)",
            right_line1=f"RUOLO: {p_role.upper()} ({p_dept.upper()})",
            right_line2=f"CLUB: {p_club.upper()}",
            right_line3=f"CODICE OVAL: {p_opta} • {'G.I.N. MONITORATO' if is_gin else 'ROSTER FIR'}",
        )

    # Pagina 1: Identità, KPI Carriera & Stagioni
    elements.append(_build_top_hdr("SEZIONE 1: IDENTITÀ ATLETA, KPI CARRIERA & STAGIONI SPORTIVE"))
    elements.append(Spacer(1, 4))
    elements.append(_PortalHeroCardFlowable(prof, width=808.0, height=78.0))
    elements.append(Spacer(1, 4))

    kpi_items = [
        {"label": "Presenze Totali (CAPS)", "value": f"{c_tot.get('total_caps', 0)}", "sub": f"{c_tot.get('total_starts', 0)} Titolare • {c_tot.get('total_bench', 0)} Sub"},
        {"label": "Minuti Totali Oval", "value": f"{tot_min_s}' min", "sub": f"Media {c_tot.get('avg_min_match', 0)}' a gara"},
        {"label": "Stagione Attuale (2026/27)", "value": f"{int(s_curr.get('minutes', 0))}' min", "sub": f"{s_curr.get('caps', 0)} presenze • {s_curr.get('starter_pct', 0)}% Starter"},
        {"label": "Squadre Rappresentate", "value": f"{c_tot.get('teams_count', 0)} Team", "sub": ", ".join(c_tot.get("teams_list", [])[:2]) if c_tot.get("teams_list") else "Club / Naz."},
        {"label": "Record Vittorie Carriera", "value": f"{c_tot.get('win_pct', 0)}%", "sub": f"{c_tot.get('total_wins', 0)} V • {c_tot.get('total_losses', 0)} S • {c_tot.get('total_draws', 0)} P"},
    ]
    elements.append(_PortalKpiRowFlowable(kpi_items, width=808.0, height=56.0))
    elements.append(Spacer(1, 6))

    elements.append(
        _PortalSectionHeaderFlowable(
            "Minutaggi & Presenze per Stagione (1 Agosto – 30 Luglio)",
            "Analisi longitudinale completa delle stagioni sportive registrate in archivio Oval",
            accent_hex="#0066B2",
            width=812.0,
            height=18.0,
        )
    )
    elements.append(Spacer(1, 3))

    if not s_df.empty:
        max_s_min = max(int(s_df["minutes"].max()), 1)
        max_s_caps = max(int(s_df["caps"].max()), 1)
        n_s_body = len(s_df) + 1
        s_row_h = max(13.5, min(18.5, 330.0 / float(max(n_s_body, 1))))
        s_bar_h = max(10.0, min(13.0, s_row_h - 4.0))
        s_pad_v = max(1.0, min(2.4, (s_row_h - s_bar_h) / 2.0))
        s_font_sz = 6.3 if n_s_body > 14 else 6.8

        s_headers = ["STAGIONE", "SQUADRA / CLUB", "CAPS", "TITOLARE", "SUB (PAN)", "MINUTI TOTALI", "MEDIA MIN", "MAX MINUTI 6 SETT."]
        s_data = [s_headers]
        s_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("BACKGROUND", (7, 0), (7, 0), colors.HexColor("#0B1F33")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 6.6),
            ("LEADING", (0, 0), (-1, 0), 7.8),
            ("ALIGN", (0, 0), (1, 0), "LEFT"),
            ("ALIGN", (2, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), s_pad_v),
            ("BOTTOMPADDING", (0, 0), (-1, -1), s_pad_v),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#002B49")),
        ]

        for _, sr in s_df.iterrows():
            r_idx = len(s_data)
            s_lbl = str(sr.get("season", ""))
            is_sub = bool(sr.get("is_subtotal", False))
            is_cur_s = ("2026/27" in s_lbl) and not is_sub
            tm_name = str(sr.get("team", ""))

            if is_sub:
                s_cell = Paragraph(f"<font size='{s_font_sz}' color='#002B49'><b>{s_lbl}</b></font>", ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2))
                team_cell = Paragraph(f"<font size='{s_font_sz - 0.2}' color='#475569'><b>{tm_name}</b></font>", ParagraphStyle(f"TM_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz - 0.2, leading=s_font_sz + 1.0))
            else:
                if is_cur_s:
                    s_cell = Paragraph(f"<font size='{s_font_sz}' color='#0F172A'><b>{s_lbl}</b></font> <font size='5.5' color='#B45309'><b>[IN CORSO]</b></font>", ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2))
                else:
                    s_cell = Paragraph(f"<font size='{s_font_sz}' color='#0F172A'><b>{s_lbl}</b></font>", ParagraphStyle(f"SL_{r_idx}", fontName="Helvetica-Bold", fontSize=s_font_sz, leading=s_font_sz + 1.2))
                tm_bg = "#0066B2" if "ital" in tm_name.lower() else "#059669"
                team_cell = _PillBadgeFlowable(185.0, s_bar_h, tm_name, bg_hex=tm_bg, text_hex="#FFFFFF", align_left=True)

            c_val = int(sr.get("caps", 0))
            c_pct = (c_val / float(max_s_caps)) * 100.0 if c_val > 0 else 0.0
            c_bar = _ProgressBarCellFlowable(width=76.0, height=s_bar_h, pct=c_pct, text=str(c_val), fill_hex="#BAE6FD", border_hex="#CBD5E1", text_hex="#0369A1")

            m_val = int(sr.get("minutes", 0))
            m_disp = f"{m_val:,}' min".replace(",", ".")
            m_pct = (m_val / float(max_s_min)) * 100.0 if m_val > 0 else 0.0
            m_bar = _ProgressBarCellFlowable(width=118.0, height=s_bar_h, pct=m_pct, text=m_disp, fill_hex="#A7F3D0", border_hex="#CBD5E1", text_hex="#064E3B")

            st_val = int(sr.get("starts", 0))
            b_val = int(sr.get("bench", 0))
            avg_v = float(sr.get("avg_min", 0.0))
            m6w_v = int(sr.get("max_consec_6w_min", 0))
            m6w_badge = _PillBadgeFlowable(width=76.0, height=s_bar_h, text=f"{m6w_v}'" if m6w_v > 0 else "-", bg_hex="#FEF08A" if m6w_v >= 400 else "#F1F5F9", text_hex="#854D0E" if m6w_v >= 400 else "#475569")

            s_data.append([s_cell, team_cell, c_bar, str(st_val), str(b_val), m_bar, f"{avg_v:.0f}'", m6w_badge])
            s_cmds.extend([
                ("ALIGN", (0, r_idx), (1, r_idx), "LEFT"),
                ("ALIGN", (2, r_idx), (-1, r_idx), "CENTER"),
                ("FONTNAME", (3, r_idx), (4, r_idx), "Helvetica"),
                ("FONTSIZE", (3, r_idx), (4, r_idx), s_font_sz),
                ("LEADING", (3, r_idx), (4, r_idx), s_font_sz + 1.2),
                ("FONTNAME", (6, r_idx), (6, r_idx), "Helvetica-Bold"),
                ("FONTSIZE", (6, r_idx), (6, r_idx), s_font_sz),
                ("LEADING", (6, r_idx), (6, r_idx), s_font_sz + 1.2),
                ("TEXTCOLOR", (6, r_idx), (6, r_idx), colors.HexColor("#0F172A")),
            ])

            if is_sub:
                s_cmds.extend([
                    ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#F1F5F9")),
                    ("LINEABOVE", (0, r_idx), (-1, r_idx), 1.0, colors.HexColor("#94A3B8")),
                    ("LINEBELOW", (0, r_idx), (-1, r_idx), 1.2, colors.HexColor("#CBD5E1")),
                    ("FONTNAME", (3, r_idx), (4, r_idx), "Helvetica-Bold"),
                ])
            elif is_cur_s:
                s_cmds.extend([
                    ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FEF3C7")),
                    ("BOX", (0, r_idx), (-1, r_idx), 1.3, colors.HexColor("#D97706")),
                ])
            else:
                s_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FFFFFF")))

        tot_idx = len(s_data)
        tot_m6w_badge = _PillBadgeFlowable(width=96.0, height=s_bar_h, text=f"{peak_6w_s}' min", bg_hex="#D4AF37", text_hex="#002B49")
        s_data.append([
            "TOTALE CARRIERA",
            f"{c_tot.get('teams_count', 0)} Squadre (Club + Naz.)",
            f"{c_tot.get('total_caps', 0)} CAPS",
            f"{c_tot.get('total_starts', 0)} ({c_tot.get('starter_pct', 0):.0f}%)",
            f"{c_tot.get('total_bench', 0)}",
            f"{tot_min_s}' min",
            f"{c_tot.get('avg_min_match', 0):.1f}'",
            tot_m6w_badge,
        ])
        s_cmds.extend([
            ("BACKGROUND", (0, tot_idx), (-1, tot_idx), colors.HexColor("#E2E8F0")),
            ("LINEABOVE", (0, tot_idx), (-1, tot_idx), 2.0, colors.HexColor("#002B49")),
            ("FONTNAME", (0, tot_idx), (-1, tot_idx), "Helvetica-Bold"),
            ("FONTSIZE", (0, tot_idx), (-1, tot_idx), s_font_sz),
            ("LEADING", (0, tot_idx), (-1, tot_idx), s_font_sz + 1.2),
            ("TEXTCOLOR", (0, tot_idx), (1, tot_idx), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (2, tot_idx), (2, tot_idx), colors.HexColor("#0369A1")),
            ("TEXTCOLOR", (5, tot_idx), (5, tot_idx), colors.HexColor("#064E3B")),
            ("ALIGN", (0, tot_idx), (1, tot_idx), "LEFT"),
            ("ALIGN", (2, tot_idx), (-1, tot_idx), "CENTER"),
        ])

        col_w_s = [96, 198, 88, 86, 62, 130, 66, 86]
        row_h_s = [16.5] + [s_row_h] * n_s_body
        tbl_s = Table(s_data, colWidths=col_w_s, rowHeights=row_h_s, repeatRows=1)
        tbl_s.setStyle(TableStyle(s_cmds))
        elements.append(tbl_s)

    # Pagina 2: Trend e Squadre / Club in Carriera
    elements.append(PageBreak())
    elements.append(_build_top_hdr("SEZIONE 2: TREND STAGIONALE & SQUADRE / CLUB IN CARRIERA"))
    elements.append(Spacer(1, 5))

    if fig_seasons is not None and include_charts:
        img_s = fig_to_rl_image(fig_seasons, width=812, height=190)
        if img_s:
            elements.append(img_s)
            elements.append(Spacer(1, 8))

    elements.append(
        _PortalSectionHeaderFlowable(
            "Squadre & Club con cui ha giocato in Carriera",
            "Ripartizione minuti tra Club di appartenenza e Nazionale Italiana",
            accent_hex="#059669",
            width=812.0,
        )
    )
    elements.append(Spacer(1, 5))

    if not t_df.empty:
        t_headers = ["SQUADRA / CLUB", "PERIODO", "CAPS", "TITOLARE", "MINUTI TOTALI", "RECORD (W-L)"]
        t_data = [t_headers]
        t_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 6.8),
            ("LEADING", (0, 0), (-1, 0), 8.2),
            ("ALIGN", (0, 0), (1, 0), "LEFT"),
            ("ALIGN", (2, 0), (-1, 0), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4.0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.0),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#0F172A")),
        ]

        for _, tr in t_df.iterrows():
            r_idx = len(t_data)
            tm_n = str(tr.get("team_name", ""))
            is_nat = "ital" in tm_n.lower()
            tm_col = "#0066B2" if is_nat else "#059669"

            w_pill = _PillBadgeFlowable(
                width=94.0,
                height=13.0,
                text=f"{int(tr.get('wins', 0))}V - {int(tr.get('losses', 0))}S ({float(tr.get('win_pct', 0)):.0f}%)",
                bg_hex="#DCFCE7",
                text_hex="#15803D",
            )
            t_min_disp = f"{int(tr.get('minutes', 0)):,}' min".replace(",", ".")

            t_data.append([
                tm_n,
                str(tr.get("period", "-")),
                str(int(tr.get("caps", 0))),
                f"{int(tr.get('starts', 0))} ({float(tr.get('starter_pct', 0)):.0f}%)",
                t_min_disp,
                w_pill,
            ])
            t_cmds.extend([
                ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor("#FFFFFF")),
                ("FONTSIZE", (0, r_idx), (-1, r_idx), 7.2),
                ("LEADING", (0, r_idx), (-1, r_idx), 8.6),
                ("ALIGN", (0, r_idx), (1, r_idx), "LEFT"),
                ("ALIGN", (2, r_idx), (-1, r_idx), "CENTER"),
                ("FONTNAME", (0, r_idx), (0, r_idx), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, r_idx), (0, r_idx), colors.HexColor(tm_col)),
                ("FONTNAME", (4, r_idx), (4, r_idx), "Helvetica-Bold"),
                ("TEXTCOLOR", (4, r_idx), (4, r_idx), colors.HexColor("#064E3B")),
            ])

        col_w_t = [212, 110, 80, 110, 150, 150]
        tbl_t = Table(t_data, colWidths=col_w_t)
        tbl_t.setStyle(TableStyle(t_cmds))
        elements.append(tbl_t)

    return elements


def _build_multi_dossier_cover(dossier_type: str, ref_week_lbl: str, player_records: list, season_lbl: str = "2026/27") -> list:
    """Costruisce la Copertina e l'Indice Generale con numeri di pagina per il fascicolo multi-giocatore."""
    elements = []
    type_titles = {
        "integrato": "DOSSIER INTEGRATO MULTI-GIOCATORE (GPS 21GG + MINUTI OVAL)",
        "gps": "DOSSIER MULTI-GIOCATORE MONITORAGGIO GPS (PASSAPORTO 21GG)",
        "oval": "DOSSIER MULTI-GIOCATORE MINUTAGGI & CARRIERA OVAL (CAPS & STAGIONI)",
    }
    type_sub = {
        "integrato": "Fascicolo Ufficiale Staff Tecnico & Preparatori FIR • Monitoraggio Fisico e Minutaggi Partita G.I.N.",
        "gps": "Fascicolo Ufficiale Monitoraggio Fisico e Carichi 21 Giorni • Gruppo di Interesse Nazionale (G.I.N.)",
        "oval": "Fascicolo Ufficiale Minutaggi, Presenze e Carriera Storica • Gruppo di Interesse Nazionale (G.I.N.)",
    }
    main_t = type_titles.get(dossier_type, "DOSSIER INDIVIDUALE MULTI-GIOCATORE G.I.N.")
    sub_t = type_sub.get(dossier_type, "Fascicolo Ufficiale Federazione Italiana Rugby")

    elements.append(
        _build_fir_header_table(
            main_title=main_t,
            sub_title=sub_t,
            right_line1=f"STAGIONE: {season_lbl}",
            right_line2=f"SETTIMANA W0: {ref_week_lbl}",
            right_line3=f"ATLETI INCLUSI: {len(player_records)} G.I.N.",
        )
    )
    elements.append(Spacer(1, 8))

    n_tot = len(player_records)
    n_fw = sum(1 for p in player_records if str(p.get("department", "")).lower() == "avanti")
    n_bk = n_tot - n_fw
    n_ben = sum(1 for p in player_records if "benetton" in str(p.get("club", "")).lower())
    n_zeb = sum(1 for p in player_records if "zebre" in str(p.get("club", "")).lower())
    n_oth = n_tot - n_ben - n_zeb

    kpi_summary = Table(
        [[
            Paragraph(f"<b>ATLETI INCLUSI</b><br/><font size='14' color='#002B49'><b>{n_tot}</b></font><br/><font size='6.5' color='#64748B'>Lista G.I.N.</font>", ParagraphStyle("K1", fontName="Helvetica", alignment=1, leading=10)),
            Paragraph(f"<b>REPARTO AVANTI</b><br/><font size='14' color='#0284C7'><b>{n_fw}</b></font><br/><font size='6.5' color='#64748B'>Piloni, Tall., Seconde, Terze</font>", ParagraphStyle("K2", fontName="Helvetica", alignment=1, leading=10)),
            Paragraph(f"<b>REPARTO TREQUARTI</b><br/><font size='14' color='#7C3AED'><b>{n_bk}</b></font><br/><font size='6.5' color='#64748B'>Mediani, Centri, Ali, Estremi</font>", ParagraphStyle("K3", fontName="Helvetica", alignment=1, leading=10)),
            Paragraph(f"<b>BENETTON RUGBY</b><br/><font size='14' color='#059669'><b>{n_ben}</b></font><br/><font size='6.5' color='#64748B'>Atleti Franchigia TV</font>", ParagraphStyle("K4", fontName="Helvetica", alignment=1, leading=10)),
            Paragraph(f"<b>ZEBRE PARMA</b><br/><font size='14' color='#D97706'><b>{n_zeb}</b></font><br/><font size='6.5' color='#64748B'>Atleti Franchigia PR</font>", ParagraphStyle("K5", fontName="Helvetica", alignment=1, leading=10)),
            Paragraph(f"<b>ALTRI / ESTERO</b><br/><font size='14' color='#475569'><b>{n_oth}</b></font><br/><font size='6.5' color='#64748B'>Top14 / Prem / Altri</font>", ParagraphStyle("K6", fontName="Helvetica", alignment=1, leading=10)),
        ]],
        colWidths=[135, 135, 135, 135, 135, 135],
    )
    kpi_summary.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(kpi_summary)
    elements.append(Spacer(1, 8))

    elements.append(
        _PortalSectionHeaderFlowable(
            "Sommario & Indice Generale Atleti",
            "Elenco dei giocatori inclusi nel fascicolo con indicazione della pagina di partenza",
            accent_hex="#002B49",
            width=812.0,
            height=18.0,
        )
    )
    elements.append(Spacer(1, 4))

    pages_per_player = 3 if dossier_type == "integrato" else (1 if dossier_type == "gps" else 2)
    index_pages = 1 if n_tot <= 34 else 2

    idx_headers = ["N°", "NOME GIOCATORE", "RUOLO", "REPARTO", "CLUB", "CONTENUTO SCHEDA", "PAGINA"]
    idx_data = [idx_headers]
    idx_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 6.8),
        ("LEADING", (0, 0), (-1, 0), 8.0),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("ALIGN", (2, 0), (4, -1), "LEFT"),
        ("ALIGN", (5, 0), (5, -1), "LEFT"),
        ("ALIGN", (6, 0), (6, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
    ]

    tipo_label = {
        "integrato": "Passaporto GPS 21gg (1 pag.) + Storico Oval (2 pag.)",
        "gps": "Passaporto Fisico & 21 Giorni (1 pag.)",
        "oval": "Carriera & Stagioni Oval (2 pag.)",
    }.get(dossier_type, "Scheda Atleta")

    for i, pr in enumerate(player_records):
        r_idx = len(idx_data)
        bg = colors.HexColor("#FFFFFF") if r_idx % 2 == 1 else colors.HexColor("#F8FAFC")
        idx_cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), bg))

        st_page = index_pages + 1 + i * pages_per_player
        p_name = str(pr.get("player_name") or "-")
        p_role = str(pr.get("role") or "-")
        p_dept = str(pr.get("department") or "-")
        p_club = str(pr.get("club") or "-")

        idx_data.append([
            str(i + 1),
            p_name,
            p_role,
            p_dept,
            p_club,
            tipo_label,
            f"Pag. {st_page}",
        ])

        idx_cmds.extend([
            ("FONTNAME", (1, r_idx), (1, r_idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (1, r_idx), (1, r_idx), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (2, r_idx), (2, r_idx), colors.HexColor("#1E40AF")),
            ("FONTNAME", (6, r_idx), (6, r_idx), "Helvetica-Bold"),
            ("TEXTCOLOR", (6, r_idx), (6, r_idx), colors.HexColor("#0066B2")),
            ("FONTSIZE", (0, r_idx), (-1, r_idx), 6.5),
            ("LEADING", (0, r_idx), (-1, r_idx), 7.8),
        ])

    idx_widths = [26, 180, 110, 80, 110, 228, 80]
    if n_tot <= 34:
        tbl_idx = Table(idx_data, colWidths=idx_widths, repeatRows=1)
        tbl_idx.setStyle(TableStyle(idx_cmds))
        elements.append(tbl_idx)
    else:
        tbl1 = Table(idx_data[:35], colWidths=idx_widths, repeatRows=1)
        tbl1.setStyle(TableStyle([c for c in idx_cmds if c[1][1] <= 34 or c[0] in ["GRID"]]))
        elements.append(tbl1)
        elements.append(PageBreak())

        elements.append(
            _build_fir_header_table(
                main_title=f"{main_t} • INDICE (PARTE 2)",
                sub_title="Continuazione elenco atleti inclusi nel fascicolo",
                right_line1=f"STAGIONE: {season_lbl}",
                right_line2=f"SETTIMANA W0: {ref_week_lbl}",
                right_line3=f"ATLETI 35-{n_tot} di {n_tot}",
            )
        )
        elements.append(Spacer(1, 6))
        tbl2_data = [idx_headers] + idx_data[35:]
        tbl2 = Table(tbl2_data, colWidths=idx_widths, repeatRows=1)
        t2_cmds = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#002B49")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#FFFFFF")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 6.8),
            ("LEADING", (0, 0), (-1, 0), 8.0),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (1, 0), (1, -1), "LEFT"),
            ("ALIGN", (2, 0), (4, -1), "LEFT"),
            ("ALIGN", (5, 0), (5, -1), "LEFT"),
            ("ALIGN", (6, 0), (6, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#002B49")),
        ]
        for r_i in range(1, len(tbl2_data)):
            bg = colors.HexColor("#FFFFFF") if r_i % 2 == 1 else colors.HexColor("#F8FAFC")
            t2_cmds.append(("BACKGROUND", (0, r_i), (-1, r_i), bg))
            t2_cmds.extend([
                ("FONTNAME", (1, r_i), (1, r_i), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, r_i), (1, r_i), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (2, r_i), (2, r_i), colors.HexColor("#1E40AF")),
                ("FONTNAME", (6, r_i), (6, r_i), "Helvetica-Bold"),
                ("TEXTCOLOR", (6, r_i), (6, r_i), colors.HexColor("#0066B2")),
                ("FONTSIZE", (0, r_i), (-1, r_i), 6.5),
                ("LEADING", (0, r_i), (-1, r_i), 7.8),
            ])
        tbl2.setStyle(TableStyle(t2_cmds))
        elements.append(tbl2)

    return elements


def crea_pdf_dossier_multi_giocatore(
    dossier_payload: list,
    ref_week_lbl: str,
    dossier_type: str = "integrato",
    season_lbl: str = "2026/27",
    include_charts: bool = True,
) -> bytes:
    """
    Genera il Dossier PDF Multi-Giocatore A4 Landscape per la Lista G.I.N. (GPS, Minuti Oval o Integrato Totale).
    Include Copertina ufficiale con Indice Generale atleti e numeri di pagina, seguito dalle schede di ciascun giocatore.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=14,
        rightMargin=14,
        topMargin=12,
        bottomMargin=16,
    )
    elements = []

    # 1. Copertina & Indice Generale
    cover_elements = _build_multi_dossier_cover(
        dossier_type=dossier_type,
        ref_week_lbl=ref_week_lbl,
        player_records=dossier_payload,
        season_lbl=season_lbl,
    )
    elements.extend(cover_elements)

    # 2. Schede di ciascun atleta
    for p_data in dossier_payload:
        p_name = p_data.get("player_name", "")
        p_meta = p_data.get("p_meta", {})
        df_21 = p_data.get("df_21")
        week_stats = p_data.get("week_stats", {})
        fig_gps = p_data.get("fig_gps") if include_charts else None
        prof = p_data.get("prof")

        # Scheda GPS (2 pagine)
        has_gps_sec = False
        if dossier_type in ["gps", "integrato"]:
            if df_21 is not None and not df_21.empty:
                elements.append(PageBreak())
                gps_flowables = _build_single_athlete_gps_flowables(
                    player_name=p_name,
                    p_meta=p_meta,
                    df_21=df_21,
                    week_stats=week_stats,
                    fig=fig_gps,
                    ref_week_lbl=ref_week_lbl,
                    include_charts=include_charts,
                )
                elements.extend(gps_flowables)
                has_gps_sec = True

        # Scheda Oval (2 pagine)
        if dossier_type in ["oval", "integrato"]:
            if prof is not None and prof.get("has_oval_data", False):
                elements.append(PageBreak())
                oval_flowables = _build_single_athlete_oval_flowables(
                    prof=prof,
                    include_charts=include_charts,
                )
                elements.extend(oval_flowables)

    _build_pdf_with_footer(doc, elements, brand=f"FEDERAZIONE ITALIANA RUGBY • DOSSIER MULTI-GIOCATORE G.I.N. ({dossier_type.upper()})")
    return buffer.getvalue()




