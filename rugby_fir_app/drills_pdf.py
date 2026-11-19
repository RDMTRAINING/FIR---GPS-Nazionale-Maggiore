# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
"""
Generatore PDF Istituzionale FIR per il modulo "Analisi & Confronto Drills".
Produce fascicoli A4 Landscape fedeli alla pagina della webapp, completi di:
  - Header ufficiale FIR con logo, data, seduta, ambito/ruolo e metodologia (Hml >25.5W, HSR >18 Av / >20 Tq)
  - Griglia KPI Cards (Tempo, Distanza/WR, Hml, HSR, Vmax/Acc-Dec)
  - Grafici Plotly ad alta risoluzione (Volume vs WR, Intensità al Minuto, Mappa Durata×Intensità,
    Ripartizione % Tempo/Carico, Confronto Secondario, Radar Multi-Drill)
  - Tabelle comparative complete e differenziali Δ%
  - Footer ufficiale FIR con watermark UID invisibile.
"""

import gc
from io import BytesIO
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from pdf_generator import (
    _build_fir_header_table,
    _build_pdf_with_footer,
)


def _strip_pdf_emojis(text: Any) -> str:
    """Rimuove emoji Unicode non supportate da Helvetica (evita i quadratini neri nei PDF)."""
    s = str(text or "")
    # Rimuove simboli emoji (plane 1 + misc symbols/dingbats/variation selectors) preservando accenti italiani, €, %, ·, Σ, Δ, ×, >
    s = re.sub(r"[\U00010000-\U0010FFFF\u2600-\u27BF\u2300-\u23FF\uFE0F\u200D]", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def _drills_fig_to_rl_image(fig: Optional[go.Figure], width: float = 535, height: float = 200):
    """Converte un grafico Plotly in PNG nitido con proporzioni ampie (nessuna sovrapposizione etichette)."""
    if fig is None:
        styles = getSampleStyleSheet()
        return Paragraph("<i>[Grafico non disponibile]</i>", styles["Normal"])
    try:
        # 1.75x logica + scale=2 garantisce proporzioni ariose identiche alla webapp e nitidezza di stampa
        img_bytes = fig.to_image(format="png", width=int(width * 1.75), height=int(height * 1.75), scale=2)
        return RLImage(BytesIO(img_bytes), width=width, height=height)
    except Exception:
        try:
            img_bytes = fig.to_image(format="png", width=int(width * 1.4), height=int(height * 1.4), scale=1)
            return RLImage(BytesIO(img_bytes), width=width, height=height)
        except Exception:
            styles = getSampleStyleSheet()
            return Paragraph("<i>[Grafico disponibile nella vista interattiva]</i>", styles["Normal"])

# Palette Istituzionale FIR
HEX_AZZURO = "#0066B2"
HEX_ORO = "#D4AF37"
HEX_NAVY = "#031926"
HEX_SLATE = "#475569"
HEX_LIGHT = "#F8FAFC"
HEX_BORDER = "#CBD5E1"


def _fmt_mmss(minutes: float) -> str:
    try:
        tot_sec = max(0, int(round(float(minutes) * 60.0)))
        m, s = divmod(tot_sec, 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"


def _section_banner(title: str, subtitle: str = "", total_width: float = 808) -> Table:
    styles = getSampleStyleSheet()
    st_t = ParagraphStyle(
        "DrillsSecT",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=12,
        textColor=colors.white,
    )
    st_s = ParagraphStyle(
        "DrillsSecS",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor("#E2E8F0"),
    )
    cell = [Paragraph(title, st_t)]
    if subtitle:
        cell.append(Paragraph(subtitle, st_s))
    tbl = Table([[cell]], colWidths=[total_width])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(HEX_NAVY)),
                ("LINEBEFORE", (0, 0), (0, -1), 3.5, colors.HexColor(HEX_ORO)),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return tbl


def _kpi_row_table(kpis: List[Tuple[str, str, str, str]], total_width: float = 808) -> Table:
    """Rende fino a 5 KPI Card in stile FIR (label, valore, subtext, hex_accent)."""
    styles = getSampleStyleSheet()
    st_lbl = ParagraphStyle("KL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=6.5, leading=8, textColor=colors.HexColor("#64748B"))
    st_val = ParagraphStyle("KV", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12.5, leading=14.5, textColor=colors.HexColor(HEX_NAVY))
    st_sub = ParagraphStyle("KS", parent=styles["Normal"], fontName="Helvetica", fontSize=6.7, leading=8.5, textColor=colors.HexColor(HEX_SLATE))

    n = max(1, len(kpis))
    gap = 6.0
    card_w = (total_width - gap * (n - 1)) / n

    row_cells = []
    col_widths = []
    style_cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, (lbl, val, sub, accent) in enumerate(kpis):
        col_idx = i * 2
        row_cells.append(
            [
                Paragraph(_strip_pdf_emojis(lbl).upper(), st_lbl),
                Spacer(1, 2),
                Paragraph(_strip_pdf_emojis(val), st_val),
                Spacer(1, 2),
                Paragraph(_strip_pdf_emojis(sub), st_sub),
            ]
        )
        col_widths.append(card_w)
        style_cmds.extend(
            [
                ("BACKGROUND", (col_idx, 0), (col_idx, 0), colors.HexColor("#FFFFFF")),
                ("BOX", (col_idx, 0), (col_idx, 0), 0.6, colors.HexColor(HEX_BORDER)),
                ("LINEABOVE", (col_idx, 0), (col_idx, 0), 3.0, colors.HexColor(accent)),
                ("TOPPADDING", (col_idx, 0), (col_idx, 0), 6),
                ("BOTTOMPADDING", (col_idx, 0), (col_idx, 0), 6),
                ("LEFTPADDING", (col_idx, 0), (col_idx, 0), 7),
                ("RIGHTPADDING", (col_idx, 0), (col_idx, 0), 7),
            ]
        )
        if i < n - 1:
            row_cells.append("")
            col_widths.append(gap)

    tbl = Table([row_cells], colWidths=col_widths)
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _styled_data_table(
    headers: List[str],
    rows: List[List[Any]],
    col_widths: List[float],
    left_cols: Optional[List[int]] = None,
    font_size: float = 6.8,
) -> Table:
    styles = getSampleStyleSheet()
    left_set = set(left_cols or [0, 1])

    st_h = ParagraphStyle("TH", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=font_size, leading=font_size + 1.8, textColor=colors.white, alignment=1)
    st_hl = ParagraphStyle("THL", parent=st_h, alignment=0)
    st_cl = ParagraphStyle("TCL", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=font_size, leading=font_size + 1.6, textColor=colors.HexColor(HEX_NAVY), alignment=0)
    st_cr = ParagraphStyle("TCR", parent=styles["Normal"], fontName="Helvetica", fontSize=font_size, leading=font_size + 1.6, textColor=colors.HexColor("#1E293B"), alignment=2)

    data = [[Paragraph(_strip_pdf_emojis(h), st_hl if idx in left_set else st_h) for idx, h in enumerate(headers)]]
    for r in rows:
        data.append(
            [
                Paragraph(_strip_pdf_emojis(v), st_cl if idx in left_set else st_cr)
                for idx, v in enumerate(r)
            ]
        )

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(HEX_NAVY)),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor(HEX_ORO)),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for r_idx in range(1, len(data)):
        if r_idx % 2 == 0:
            cmds.append(("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor(HEX_LIGHT)))
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _two_figs_row(
    fig_left: Optional[go.Figure],
    fig_right: Optional[go.Figure],
    total_width: float = 808,
    height: float = 190,
) -> Table:
    gap = 10.0
    w_each = (total_width - gap) / 2.0
    img_l = _drills_fig_to_rl_image(fig_left, width=w_each, height=height)
    img_r = _drills_fig_to_rl_image(fig_right, width=w_each, height=height)
    tbl = Table([[img_l, "", img_r]], colWidths=[w_each, gap, w_each])
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return tbl


def crea_pdf_drills_sessione(
    session_date: str,
    session_name: str,
    scope_label: str,
    is_total_mode: bool,
    df_sess: pd.DataFrame,
    kpis: List[Tuple[str, str, str, str]],
    fig_vol_wr: Optional[go.Figure] = None,
    fig_rates: Optional[go.Figure] = None,
    fig_matrix: Optional[go.Figure] = None,
    fig_share: Optional[go.Figure] = None,
    fig_sec: Optional[go.Figure] = None,
    df_roles_compact: Optional[pd.DataFrame] = None,
    df_excluded: Optional[pd.DataFrame] = None,
) -> bytes:
    """
    Genera il Report PDF completo (A4 Landscape) della vista Sessione Drills,
    fedele ai grafici, alle KPI card e alle tabelle della webapp.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=17,
        rightMargin=17,
        topMargin=16,
        bottomMargin=24,
    )
    W = landscape(A4)[0] - 34  # ~808 pt
    elements: List[Any] = []

    mode_str = "Carico Totale Gruppo/Ruolo (Somma Attivi)" if is_total_mode else "Media Normalizzata Pro-Capite (Σ Ruolo / N° Attivi)"
    method_str = "Hml (>25.5W) · HSR Differenziato FIR (>18 km/h Avanti / >20 km/h Trequarti)"

    # =========================================================================
    # PAGINA 1: HEADER + KPI CARDS + GRAFICI 1 & 2 + TABELLA COMPARATIVA DRILLS
    # =========================================================================
    elements.append(
        _build_fir_header_table(
            main_title=f"ANALISI &amp; CONFRONTO DRILLS — {session_name.upper()}",
            sub_title=f"Seduta del <b>{session_date}</b> · Ambito: <b>{scope_label}</b>",
            right_line1=mode_str,
            right_line2=method_str,
            right_line3=f"Generato il {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(_kpi_row_table(kpis, total_width=W))
    elements.append(Spacer(1, 8))

    elements.append(
        _section_banner(
            "1. CONFRONTO DIRETTO TRA DRILLS — VOLUME, TEMPO E INTENSITÀ RELATIVA AL MINUTO",
            "Confronto affiancato tra volume erogato, durata effettiva e densità metabolica/velocità al minuto (Work Rate, Hml/min, HSR/min).",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 5))
    elements.append(_two_figs_row(fig_vol_wr, fig_rates, total_width=W, height=195))
    elements.append(Spacer(1, 7))

    # Tabella Comparativa Completa Drills della Seduta
    elements.append(
        _section_banner(
            f"2. TABELLA COMPARATIVA COMPLETA DRILLS — {session_date} · {session_name} ({scope_label})",
            f"Parametri volumetrici espressi in modalità: {mode_str}.",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 4))

    tot_dur_s = float(df_sess["Duration_Min"].sum()) if not df_sess.empty else 0.0
    mean_wr_s = float(df_sess["Work_Rate"].mean()) if not df_sess.empty else 0.0

    if is_total_mode:
        t_headers = [
            "Ord.", "Drill", "Att.", "Escl.", "Durata", "% T",
            "Dist. Tot (m)", "WR (m/m)", "Hml Tot (m)", "Hml/m",
            "HSR Tot (m)", "HSR/m", "Acc Tot", "Dec Tot",
        ]
        t_widths = [28, 140, 32, 32, 52, 38, 70, 56, 68, 52, 68, 52, 60, 60]
        t_rows = []
        for _, r in df_sess.iterrows():
            dur_v = float(r.get("Duration_Min", 0.0))
            pct_t = (dur_v / tot_dur_s * 100.0) if tot_dur_s > 0 else 0.0
            t_rows.append(
                [
                    f"#{int(r['Drill_Order'])}",
                    str(r["Drill_Name"])[:28],
                    f"{int(r['Active_Players_Count'])}",
                    f"{int(r.get('Excluded_Players_Count', 0))}",
                    f"{dur_v:.1f}' ({_fmt_mmss(dur_v)})",
                    f"{pct_t:.1f}%",
                    f"{float(r['Total_Distance_Sum']):,.0f}",
                    f"{float(r['Work_Rate']):.1f}",
                    f"{float(r['HMPD_Sum']):,.0f}",
                    f"{float(r.get('HMPD_per_Min', 0.0)):.1f}",
                    f"{float(r['HSR_Sum']):,.0f}",
                    f"{float(r.get('HSR_per_Min', 0.0)):.1f}",
                    f"{float(r['Acc_Events_Sum']):,.0f}",
                    f"{float(r['Dec_Events_Sum']):,.0f}",
                ]
            )
    else:
        t_headers = [
            "Ord.", "Drill", "Att.", "Durata", "% T",
            "Dist (m)", "WR (m/m)", "Δ WR%", "Hml (m)", "Hml/m",
            "HSR (m)", "HSR/m", "Vmax", "Picco", "Acc", "Dec",
        ]
        t_widths = [28, 128, 30, 54, 38, 58, 50, 46, 56, 46, 56, 46, 46, 46, 40, 40]
        t_rows = []
        for _, r in df_sess.iterrows():
            dur_v = float(r.get("Duration_Min", 0.0))
            pct_t = (dur_v / tot_dur_s * 100.0) if tot_dur_s > 0 else 0.0
            wr_v = float(r.get("Work_Rate", 0.0))
            d_wr = ((wr_v - mean_wr_s) / mean_wr_s * 100.0) if mean_wr_s > 0 else 0.0
            d_sign = "+" if d_wr >= 0 else ""
            t_rows.append(
                [
                    f"#{int(r['Drill_Order'])}",
                    str(r["Drill_Name"])[:26],
                    f"{int(r['Active_Players_Count'])}",
                    f"{dur_v:.1f}' ({_fmt_mmss(dur_v)})",
                    f"{pct_t:.1f}%",
                    f"{float(r['Total_Distance']):,.0f}",
                    f"{wr_v:.1f}",
                    f"{d_sign}{d_wr:.1f}%",
                    f"{float(r['HMPD']):,.1f}",
                    f"{float(r.get('HMPD_per_Min', 0.0)):.1f}",
                    f"{float(r['HSR']):,.1f}",
                    f"{float(r.get('HSR_per_Min', 0.0)):.1f}",
                    f"{float(r.get('Max_Speed', 0.0)):.1f}",
                    f"{float(r.get('Max_Speed_Peak', 0.0)):.1f}",
                    f"{float(r.get('Acc_Events', 0.0)):.1f}",
                    f"{float(r.get('Dec_Events', 0.0)):.1f}",
                ]
            )

    elements.append(_styled_data_table(t_headers, t_rows, t_widths, left_cols=[0, 1], font_size=6.5))

    # =========================================================================
    # PAGINA 2: MATRICE DURATA×INTENSITÀ + RIPARTIZIONE % + CONFRONTO SECONDARIO
    # =========================================================================
    elements.append(PageBreak())
    elements.append(
        _build_fir_header_table(
            main_title=f"ANALISI AVANZATA DRILL vs DRILL — {session_name.upper()}",
            sub_title=f"Mappa Durata × Intensità, Ripartizione % del Carico e Profilo Meccanico · Ambito: <b>{scope_label}</b>",
            right_line1=f"Seduta: {session_date}",
            right_line2=method_str,
            total_width=W,
        )
    )
    elements.append(Spacer(1, 6))
    elements.append(
        _section_banner(
            "3. MAPPA DURATA × INTENSITÀ &amp; RIPARTIZIONE % DEL TEMPO E DEL CARICO TRA I DRILLS",
            "Quadranti operativi dei drills e quota percentuale di tempo, distanza, Hml e HSR assorbita da ciascun blocco.",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 5))
    elements.append(_two_figs_row(fig_matrix, fig_share, total_width=W, height=205))
    elements.append(Spacer(1, 8))

    if fig_sec is not None:
        elements.append(
            _section_banner(
                "4. CONFRONTO SECONDARIO VOLUMETRICO / MECCANICO TRA I DRILLS",
                "Vista secondaria selezionata nella piattaforma (Hml vs HSR, Avanti vs Trequarti, Velocità o Acc/Dec).",
                total_width=W,
            )
        )
        elements.append(Spacer(1, 5))
        elements.append(_drills_fig_to_rl_image(fig_sec, width=W, height=195))

    # =========================================================================
    # PAGINA 3 (OPZIONALE): RIEPILOGO COMPATTO RUOLI NORMALIZZATI & ESCLUSI
    # =========================================================================
    has_roles_tbl = df_roles_compact is not None and not df_roles_compact.empty
    has_excl_tbl = df_excluded is not None and not df_excluded.empty
    if has_roles_tbl or has_excl_tbl:
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                main_title=f"APPENDICE TECNICA — {session_name.upper()}",
                sub_title=f"Riepilogo Volumetrico Normalizzato per Ruolo (Σ Ruolo / N° Attivi) &amp; Audit Esclusioni · {session_date}",
                right_line1="Normalizzazione Dinamica FIR",
                right_line2=method_str,
                total_width=W,
            )
        )
        elements.append(Spacer(1, 8))

        if has_roles_tbl:
            elements.append(
                _section_banner(
                    "RIEPILOGO VOLUMETRICO PER RUOLO NELLA SEDUTA (Σ RUOLO / N° GIOCATORI ATTIVI DEL RUOLO)",
                    "Valori medi per drill calcolati dividendo la somma volumetrica del ruolo per il numero effettivo di atleti attivi di quel ruolo.",
                    total_width=W,
                )
            )
            elements.append(Spacer(1, 5))
            r_headers = [
                "Ruolo", "Reparto", "Att. Med.", "Dist. Pro-Cap", "Dist. Tot",
                "WR", "Hml Pro-Cap", "Hml Tot", "HSR Pro-Cap", "HSR Tot", "Vmax",
            ]
            r_widths = [104, 64, 52, 74, 74, 52, 74, 74, 74, 74, 92]
            r_rows = []
            for _, rr in df_roles_compact.iterrows():
                r_rows.append(
                    [
                        str(rr["Role"]),
                        str(rr["Department"]),
                        f"{float(rr['Attivi_Medi']):.1f}",
                        f"{float(rr['Total_Distance']):,.0f} m",
                        f"{float(rr['Total_Distance_Sum']):,.0f} m",
                        f"{float(rr['Work_Rate']):.1f}",
                        f"{float(rr['HMPD']):,.1f} m",
                        f"{float(rr['HMPD_Sum']):,.0f} m",
                        f"{float(rr['HSR']):,.1f} m",
                        f"{float(rr['HSR_Sum']):,.0f} m",
                        f"{float(rr['Max_Speed']):.1f} km/h",
                    ]
                )
            elements.append(_styled_data_table(r_headers, r_rows, r_widths, left_cols=[0, 1], font_size=6.8))
            elements.append(Spacer(1, 10))

        if has_excl_tbl:
            elements.append(
                _section_banner(
                    f"AUDIT ATLETI ESCLUSI AUTOMATICAMENTE (FUORI CAMPO / ROTAZIONI) — {len(df_excluded)} TRACCE",
                    "Esclusi dalle medie pro-capite per prevenire distorsioni al ribasso dovute a panchina o rotazioni parziali.",
                    total_width=W,
                )
            )
            elements.append(Spacer(1, 5))
            e_headers = ["Drill", "Atleta", "Ruolo", "Distanza (m)", "Work Rate", "Vmax", "Motivo Esclusione"]
            e_widths = [110, 130, 80, 72, 66, 60, 290]
            e_rows = []
            for _, er in df_excluded.head(35).iterrows():
                e_rows.append(
                    [
                        str(er.get("Drill_Name", ""))[:26],
                        str(er.get("Player_Name", ""))[:30],
                        str(er.get("Role", "")),
                        f"{float(er.get('Total_Distance', 0.0)):.0f}",
                        f"{float(er.get('Work_Rate', 0.0)):.1f}",
                        f"{float(er.get('Max_Speed', 0.0)):.1f}",
                        str(er.get("Exclusion_Reason", ""))[:70],
                    ]
                )
            elements.append(_styled_data_table(e_headers, e_rows, e_widths, left_cols=[0, 1, 2, 6], font_size=6.6))

    _build_pdf_with_footer(doc, elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    del elements, doc
    gc.collect()
    return pdf_bytes


def crea_pdf_drill_bank(
    selected_drill: str,
    scope_label: str,
    is_total_mode: bool,
    kpis: List[Tuple[str, str, str, str]],
    df_hist: pd.DataFrame,
    fig_long: Optional[go.Figure] = None,
    fig_hi: Optional[go.Figure] = None,
    multi_scope_label: str = "",
    benchmark_drill: str = "",
    fig_radar: Optional[go.Figure] = None,
    fig_bank_matrix: Optional[go.Figure] = None,
    fig_comp: Optional[go.Figure] = None,
    df_diff: Optional[pd.DataFrame] = None,
    df_catalog: Optional[pd.DataFrame] = None,
) -> bytes:
    """
    Genera il Report PDF completo (A4 Landscape) del Tab 2 (Drill Bank Longitudinale
    + Arena Confronto Multi-Drill + Catalogo Completo).
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=17,
        rightMargin=17,
        topMargin=16,
        bottomMargin=24,
    )
    W = landscape(A4)[0] - 34
    elements: List[Any] = []

    mode_str = "Carico Totale Gruppo/Ruolo" if is_total_mode else "Media Normalizzata Pro-Capite (Σ Ruolo / N° Attivi)"
    method_str = "Hml (>25.5W) · HSR Differenziato FIR (>18 km/h Avanti / >20 km/h Trequarti)"

    # =========================================================================
    # PAGINA 1: ANALISI LONGITUDINALE CROSS-SESSION DEL DRILL SELEZIONATO
    # =========================================================================
    elements.append(
        _build_fir_header_table(
            main_title=f"FIR DRILL BANK — ANALISI LONGITUDINALE: {selected_drill.upper()}",
            sub_title=f"Ambito: <b>{scope_label}</b> · Modalità: <b>{mode_str}</b>",
            right_line1=f"{len(df_hist)} esecuzioni storiche",
            right_line2=method_str,
            right_line3=f"Generato il {pd.Timestamp.now().strftime('%d/%m/%Y %H:%M')}",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(_kpi_row_table(kpis, total_width=W))
    elements.append(Spacer(1, 8))

    elements.append(
        _section_banner(
            f"1. EVOLUZIONE LONGITUDINALE CROSS-SESSION — {selected_drill}",
            "Andamento nel tempo della metrica primaria/secondaria e trend alta intensità (Hml & HSR).",
            total_width=W,
        )
    )
    elements.append(Spacer(1, 5))
    elements.append(_two_figs_row(fig_long, fig_hi, total_width=W, height=195))
    elements.append(Spacer(1, 7))

    # Tabella Storica Esecuzioni
    h_headers = [
        "Data", "Allenamento", "Ord.", "Att.", "Durata",
        "Dist Pro-C", "Dist Tot", "WR", "Δ WR%", "Hml Pro-C",
        "Hml/m", "HSR Pro-C", "HSR/m", "Vmax", "Acc", "Dec",
    ]
    h_widths = [54, 112, 26, 28, 50, 56, 58, 46, 44, 54, 44, 54, 44, 46, 46, 46]
    h_rows = []
    for _, r in df_hist.head(22).iterrows():
        dur_v = float(r.get("Duration_Min", 0.0))
        d_wr = float(r.get("Delta_WR_%", 0.0))
        sgn = "+" if d_wr >= 0 else ""
        h_rows.append(
            [
                str(r["Session_Date"]),
                str(r["Session_Name"])[:24],
                f"#{int(r['Drill_Order'])}",
                f"{int(r['Active_Players_Count'])}",
                f"{dur_v:.1f}' ({_fmt_mmss(dur_v)})",
                f"{float(r['Total_Distance']):,.0f}",
                f"{float(r['Total_Distance_Sum']):,.0f}",
                f"{float(r['Work_Rate']):.1f}",
                f"{sgn}{d_wr:.1f}%",
                f"{float(r['HMPD']):,.1f}",
                f"{float(r.get('HMPD_per_Min', 0.0)):.1f}",
                f"{float(r['HSR']):,.1f}",
                f"{float(r.get('HSR_per_Min', 0.0)):.1f}",
                f"{float(r.get('Max_Speed', 0.0)):.1f}",
                f"{float(r.get('Acc_Events', 0.0)):.1f}",
                f"{float(r.get('Dec_Events', 0.0)):.1f}",
            ]
        )
    elements.append(_styled_data_table(h_headers, h_rows, h_widths, left_cols=[0, 1], font_size=6.5))

    # =========================================================================
    # PAGINA 2: ARENA CONFRONTO MULTI-DRILL (RADAR + MATRICE + BENCHMARK Δ%)
    # =========================================================================
    if fig_radar is not None or fig_comp is not None or (df_diff is not None and not df_diff.empty):
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                main_title="ARENA CONFRONTO MULTI-DRILL — PROFILI &amp; BENCHMARK Δ%",
                sub_title=f"Ambito Confronto: <b>{multi_scope_label or scope_label}</b> · Benchmark di riferimento: <b>{benchmark_drill or 'Media'}</b>",
                right_line1=mode_str,
                right_line2=method_str,
                total_width=W,
            )
        )
        elements.append(Spacer(1, 6))
        elements.append(
            _section_banner(
                "2. PROFILO MULTI-METRICA (RADAR) &amp; MAPPA DURATA × INTENSITÀ TRA DRILLS",
                "Confronto diretto tra esercitazioni su Durata (min), Distanza (m), Work Rate, Hml/min, HSR/min e Velocità Massima.",
                total_width=W,
            )
        )
        elements.append(Spacer(1, 5))
        elements.append(_two_figs_row(fig_radar, fig_bank_matrix, total_width=W, height=205))
        elements.append(Spacer(1, 7))

        if df_diff is not None and not df_diff.empty:
            elements.append(
                _section_banner(
                    f"3. TABELLA DIFFERENZIALE MULTI-DRILL (Δ% RISPETTO A '{benchmark_drill}')",
                    "Variazioni percentuali di durata, volume e intensità al minuto per scegliere il drill più coerente con l'obiettivo della seduta.",
                    total_width=W,
                )
            )
            elements.append(Spacer(1, 4))
            d_headers = list(df_diff.columns)
            n_dc = len(d_headers)
            w_first = 128.0
            w_rest = (W - w_first) / max(1, n_dc - 1)
            d_widths = [w_first] + [w_rest] * (n_dc - 1)
            d_rows = [[str(v) for v in row] for row in df_diff.values.tolist()]
            elements.append(_styled_data_table(d_headers, d_rows, d_widths, left_cols=[0], font_size=6.5))

    # =========================================================================
    # PAGINA 3: BARRE COMPARATIVE & CATALOGO COMPLETO DRILL BANK
    # =========================================================================
    if fig_comp is not None or (df_catalog is not None and not df_catalog.empty):
        elements.append(PageBreak())
        elements.append(
            _build_fir_header_table(
                main_title="CATALOGO COMPLETO FIR DRILL BANK",
                sub_title=f"Classifica e parametri medi normalizzati di tutte le esercitazioni archiviate · Ambito: <b>{multi_scope_label or scope_label}</b>",
                right_line1=mode_str,
                right_line2=method_str,
                total_width=W,
            )
        )
        elements.append(Spacer(1, 6))
        if fig_comp is not None:
            elements.append(_drills_fig_to_rl_image(fig_comp, width=W, height=195))
            elements.append(Spacer(1, 8))

        if df_catalog is not None and not df_catalog.empty:
            elements.append(
                _section_banner(
                    "4. TABELLA RIASSUNTIVA CATALOGO DRILL BANK (ORDINATA PER WORK RATE)",
                    "Medie storiche calcolate dividendo la somma volumetrica degli atleti attivi per il numero effettivo di esecuzioni attive.",
                    total_width=W,
                )
            )
            elements.append(Spacer(1, 4))
            c_headers = list(df_catalog.columns)
            n_cc = len(c_headers)
            w_c0 = 124.0
            w_cr = (W - w_c0) / max(1, n_cc - 1)
            c_widths = [w_c0] + [w_cr] * (n_cc - 1)
            c_rows = [[str(v) for v in row] for row in df_catalog.head(30).values.tolist()]
            elements.append(_styled_data_table(c_headers, c_rows, c_widths, left_cols=[0, 1], font_size=6.4))

    _build_pdf_with_footer(doc, elements)
    pdf_bytes = buf.getvalue()
    buf.close()
    del elements, doc
    gc.collect()
    return pdf_bytes
