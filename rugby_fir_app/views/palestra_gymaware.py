# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import os
import io
import textwrap
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

import config
if not hasattr(config, "render_navigation_cards"):
    import importlib
    importlib.reload(config)
from config import render_page_header, render_navigation_cards
import utils


def render_html(html_str: str):
    """
    Renderizza HTML puro in Streamlit senza innescare la formattazione dei blocchi di codice Markdown.
    In CommonMark/Markdown qualsiasi riga con 4 o più spazi all'inizio viene interpretata come <pre><code>.
    Rimuovendo gli spazi iniziali da ogni riga si garantisce che l'HTML venga interpretato e renderizzato correttamente.
    """
    clean_lines = [line.strip() for line in html_str.splitlines() if line.strip()]
    st.markdown("\n".join(clean_lines), unsafe_allow_html=True)


def _resolve_period(preset: str, custom_dates: tuple, all_dates: list) -> tuple:
    """
    Risolve le date ISO di inizio e fine in base al preset o intervallo selezionato.
    Ritorna: (start_date_iso, end_date_iso, period_label)
    """
    from datetime import datetime, timedelta

    if not all_dates:
        return None, None, "Tutto lo Storico"

    parsed_dates = []
    for d in all_dates:
        if not d:
            continue
        try:
            parsed_dates.append(datetime.strptime(str(d).strip(), "%d/%m/%Y").date())
        except Exception:
            pass

    if parsed_dates:
        min_dt = min(parsed_dates)
        max_dt = max(parsed_dates)
    else:
        max_dt = datetime.now().date()
        min_dt = max_dt - timedelta(days=90)

    min_d_str = min_dt.strftime("%d/%m/%Y")
    max_d_str = max_dt.strftime("%d/%m/%Y")

    if preset == "Tutto lo Storico":
        # Per tutto lo storico ritorniamo None, None: nessun filtro sulle date per includere ogni record
        return None, None, f"Tutto lo Storico ({min_d_str} - {max_d_str})"
    elif preset == "Ultima Seduta":
        return max_dt.strftime("%Y-%m-%d"), max_dt.strftime("%Y-%m-%d"), f"Ultima Seduta ({max_d_str})"
    elif preset == "Ultimi 7 Giorni":
        s_dt = max_dt - timedelta(days=7)
        return s_dt.strftime("%Y-%m-%d"), max_dt.strftime("%Y-%m-%d"), f"Ultimi 7 Giorni ({s_dt.strftime('%d/%m/%Y')} - {max_d_str})"
    elif preset == "Ultimi 30 Giorni":
        s_dt = max_dt - timedelta(days=30)
        return s_dt.strftime("%Y-%m-%d"), max_dt.strftime("%Y-%m-%d"), f"Ultimi 30 Giorni ({s_dt.strftime('%d/%m/%Y')} - {max_d_str})"
    elif preset == "Ultimi 3 Mesi":
        s_dt = max_dt - timedelta(days=90)
        return s_dt.strftime("%Y-%m-%d"), max_dt.strftime("%Y-%m-%d"), f"Ultimi 3 Mesi ({s_dt.strftime('%d/%m/%Y')} - {max_d_str})"
    elif preset == "Periodo Personalizzato":
        if custom_dates and len(custom_dates) == 2:
            s_d, e_d = custom_dates
            if s_d > e_d:
                s_d, e_d = e_d, s_d
            return s_d.strftime("%Y-%m-%d"), e_d.strftime("%Y-%m-%d"), f"Dal {s_d.strftime('%d/%m/%Y')} al {e_d.strftime('%d/%m/%Y')}"
        else:
            return min_dt.strftime("%Y-%m-%d"), max_dt.strftime("%Y-%m-%d"), "Periodo Personalizzato"
    return None, None, preset


def render_palestra_gymaware(t: dict):
    """
    Modulo Analisi Palestra & GymAware (VBT - Velocity Based Training)
    Nazionale Italiana Rugby • Italrugby
    """
    utils.init_gymaware_db()

    render_page_header(
        "Palestra & GymAware • Velocity Based Training (VBT)",
        "Monitoraggio accelerometrico, velocità e potenza alla sbarra • Classifiche di squadra, profili carico-velocità, stima 1RM e analisi rep-by-rep",
        "bi-lightning-charge-fill",
    )

    cards_gymaware = [
        {
            "id": "squadra_ranking",
            "title": "Analisi di Squadra & Ranking",
            "desc": "Classifiche atleti in stile GymAware, card riassuntive, confronto reparti e profili carico-velocità di gruppo",
            "icon": "bi-trophy-fill",
        },
        {
            "id": "analisi_atleta",
            "title": "Analisi Individuale Atleta",
            "desc": "Profilo Carico-Velocità, stima 1RM teorico, analisi rep-by-rep per serie e perdita di velocità (fatigue)",
            "icon": "bi-person-badge-fill",
        },
        {
            "id": "gestione_dati",
            "title": "Caricamento & Gestione CSV",
            "desc": "Importazione guidata file GymAware (Rep Statistics Table), verifica sessioni attive e cancellazione",
            "icon": "bi-cloud-arrow-up-fill",
        },
    ]

    active_tab = render_navigation_cards("palestra_gymaware", cards_gymaware)

    if active_tab == "squadra_ranking":
        _render_tab_squadra(t)
    elif active_tab == "analisi_atleta":
        _render_tab_atleta(t)
    else:
        _render_tab_gestione(t)


# ==============================================================================
# 1. ANALISI DI SQUADRA & RANKING ATLETI (GYMAWARE UI STYLE)
# ==============================================================================

def _render_tab_squadra(t: dict):
    all_dates = utils.get_gymaware_dates()
    all_exercises = utils.get_gymaware_exercises()

    if not all_exercises:
        st.warning("⚠️ Nessun dato GymAware registrato nel database. Carica un file CSV nella sezione 'Caricamento & Gestione CSV'.")
        return

    # --------------------------------------------------------------------------
    # BARRA FILTRI SUPERIORI (PERIODO & REPARTO)
    # --------------------------------------------------------------------------
    period_options = [
        "Tutto lo Storico",
        "Ultima Seduta",
        "Ultimi 7 Giorni",
        "Ultimi 30 Giorni",
        "Ultimi 3 Mesi",
        "Periodo Personalizzato",
    ]
    f_c1, f_c2 = st.columns([1.4, 1.0])
    with f_c1:
        sel_period_preset = st.selectbox("📅 Periodo di Analisi", period_options, index=0, key="gymaware_team_period_preset")
    with f_c2:
        dept_opts = ["Tutti", "Avanti", "TreQuarti"]
        sel_dept = st.selectbox("🏉 Filtra per Reparto", dept_opts, key="gymaware_team_dept")

    custom_dates = None
    if sel_period_preset == "Periodo Personalizzato":
        from datetime import datetime
        try:
            min_d = datetime.strptime(all_dates[-1], "%d/%m/%Y").date()
            max_d = datetime.strptime(all_dates[0], "%d/%m/%Y").date()
        except Exception:
            min_d = datetime.now().date()
            max_d = datetime.now().date()
        custom_dates = st.date_input(
            "Seleziona Intervallo Date",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            key="gymaware_team_custom_dates",
        )

    s_iso, e_iso, period_label = _resolve_period(sel_period_preset, custom_dates, all_dates)

    # --------------------------------------------------------------------------
    # KPI STRIP (Coerente con interfaccia GymAware: Total Sets, Mean Velocity...)
    # --------------------------------------------------------------------------
    stats = utils.get_gymaware_summary_stats(start_date=s_iso, end_date=e_iso)

    kpi_html = textwrap.dedent(f"""
    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:14px; margin-bottom:22px;">
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); text-align:center;">
            <div style="font-size:0.80rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                Total Sets
            </div>
            <div style="font-size:2.4rem; font-weight:900; color:#0F172A; line-height:1.1;">
                {stats['total_sets']:,}
            </div>
            <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                {stats['total_athletes']} atleti monitorati
            </div>
        </div>
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); text-align:center;">
            <div style="font-size:0.80rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                Mean Velocity (m/s)
            </div>
            <div style="font-size:2.4rem; font-weight:900; color:#0066B2; line-height:1.1;">
                {stats['mean_velocity']:.2f}
            </div>
            <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                Picco max: <b>{stats['peak_velocity']:.2f} m/s</b>
            </div>
        </div>
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); text-align:center;">
            <div style="font-size:0.80rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                Total Repetitions
            </div>
            <div style="font-size:2.4rem; font-weight:900; color:#0F172A; line-height:1.1;">
                {stats['total_reps']:,}
            </div>
            <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                Ripetizioni registrate
            </div>
        </div>
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); text-align:center;">
            <div style="font-size:0.80rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                Mean Power (W)
            </div>
            <div style="font-size:2.4rem; font-weight:900; color:#D97706; line-height:1.1;">
                {stats['mean_power']:,.0f} <span style="font-size:1.1rem; font-weight:700;">W</span>
            </div>
            <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                Potenza di picco: <b>{stats['max_power']:,.0f} W</b>
            </div>
        </div>
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); text-align:center;">
            <div style="font-size:0.80rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px;">
                Volume di Lavoro (Tonnaggio)
            </div>
            <div style="font-size:2.4rem; font-weight:900; color:#059669; line-height:1.1;">
                {stats['tonnage_kg']:,.0f} <span style="font-size:1.1rem; font-weight:700;">kg</span>
            </div>
            <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                Carico totale sollevato
            </div>
        </div>
    </div>
    """).strip()
    render_html(kpi_html)

    # --------------------------------------------------------------------------
    # CONTROLLI CLASSIFICA ATHLETE RANKING
    # --------------------------------------------------------------------------
    render_html("""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid #0066B2; border-radius:14px; padding:16px 20px 10px 20px; box-shadow:0 3px 12px rgba(0,0,0,0.05); margin-bottom:14px;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:1.4rem;">🏆</span>
                <div>
                    <div style="font-size:1.25rem; font-weight:800; color:#0F172A; line-height:1.1;">Athlete Ranking</div>
                    <div style="font-size:0.75rem; color:#64748B;">Classifica ufficiale prestazioni VBT per esercizio e parametro accelerometrico</div>
                </div>
            </div>
        </div>
    """)

    rk_c1, rk_c2, rk_c3 = st.columns([1.5, 1.5, 1.2])

    with rk_c1:
        default_ex_idx = all_exercises.index("Trap Bar Jump") if "Trap Bar Jump" in all_exercises else 0
        sel_exercise = st.selectbox("Seleziona Esercizio", all_exercises, index=default_ex_idx, key="gymaware_rank_exercise")

    with rk_c2:
        metric_options = {
            "mean_velocity": "Mean Velocity (m/s)",
            "peak_velocity": "Peak Velocity (m/s)",
            "mean_power": "Mean Power (W)",
            "mean_power_wkg": "Mean Power (W/kg)",
            "bar_weight": "Carico Bilanciere (kg)",
            "height": "Height (m)",
        }
        sel_metric_key = st.selectbox(
            "Seleziona Metrica",
            list(metric_options.keys()),
            format_func=lambda k: metric_options[k],
            index=0,
            key="gymaware_rank_metric",
        )

    with rk_c3:
        sel_criterion = st.radio(
            "Criterio Classifica",
            options=["avg", "max"],
            format_func=lambda x: "Media della Serie (Avg)" if x == "avg" else "Miglior Rep (Peak)",
            horizontal=False,
            key="gymaware_rank_criterion",
        )

    # Calcolo classifica
    ranking_df = utils.get_gymaware_ranking(
        exercise=sel_exercise,
        metric_col=sel_metric_key,
        criterion=sel_criterion,
        start_date=s_iso,
        end_date=e_iso,
        department=sel_dept,
    )

    metric_label = metric_options[sel_metric_key]

    if ranking_df.empty:
        st.info(f"Nessun dato registrato per l'esercizio **{sel_exercise}** nel periodo **{period_label}**.")
    else:
        max_val = ranking_df["metric_value"].max() if len(ranking_df) > 0 else 1.0
        if max_val <= 0:
            max_val = 1.0

        # Costruisce l'intero blocco Leaderboard in un'unica stringa HTML pulita
        rows_html_list = []
        for _, row in ranking_df.iterrows():
            rk = int(row["rank"])
            ath_name = str(row["athlete_name"])
            val = float(row["metric_value"])
            load_kg = float(row.get("load_kg") or 0.0)
            sets_count = int(row.get("total_sets") or 0)
            role = str(row.get("role") or "N/D")
            dept = str(row.get("department") or "N/D")
            club = str(row.get("club") or "FIR")

            if "m/s" in metric_label:
                val_display = f"{val:.2f} <span style='font-size:0.85rem; font-weight:600; color:#64748B;'>m/s</span>"
            elif "W" in metric_label and "W/kg" not in metric_label:
                val_display = f"{val:,.0f} <span style='font-size:0.85rem; font-weight:600; color:#64748B;'>W</span>"
            elif "W/kg" in metric_label:
                val_display = f"{val:.1f} <span style='font-size:0.85rem; font-weight:600; color:#64748B;'>W/kg</span>"
            elif "kg" in metric_label:
                val_display = f"{val:.1f} <span style='font-size:0.85rem; font-weight:600; color:#64748B;'>kg</span>"
            else:
                val_display = f"{val:.2f}"

            if rk == 1:
                badge_style = "background:linear-gradient(135deg, #F59E0B 0%, #D4AF37 100%); color:#031926; box-shadow:0 2px 6px rgba(212,175,55,0.4);"
                badge_text = "🥇 #1"
                row_border = "border:2px solid #D4AF37; background:linear-gradient(90deg, rgba(212,175,55,0.06) 0%, rgba(255,255,255,1) 50%);"
            elif rk == 2:
                badge_style = "background:#94A3B8; color:#0F172A;"
                badge_text = "🥈 #2"
                row_border = "border:1px solid #CBD5E1; background:#FFFFFF;"
            elif rk == 3:
                badge_style = "background:#D97706; color:#FFFFFF;"
                badge_text = "🥉 #3"
                row_border = "border:1px solid #CBD5E1; background:#FFFFFF;"
            else:
                badge_style = "background:#F1F5F9; color:#475569; border:1px solid #E2E8F0;"
                badge_text = f"#{rk}"
                row_border = "border:1px solid #F1F5F9; background:#FFFFFF;"

            b64_photo = utils.get_player_photo_base64(ath_name, max_width=160)
            if b64_photo:
                avatar_html = f'<img src="data:image/jpeg;base64,{b64_photo}" style="width:50px; height:50px; border-radius:50%; object-fit:cover; border:2px solid #0066B2; box-shadow:0 2px 6px rgba(0,0,0,0.12);" alt="{ath_name}">'
            else:
                initials = "".join([part[0] for part in ath_name.split()[:2]]).upper()
                avatar_html = f'<div style="width:50px; height:50px; border-radius:50%; background:#0066B2; color:#FFFFFF; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.05rem; border:2px solid #D4AF37;">{initials}</div>'

            dept_badge = (
                "<span style='background:#0066B2; color:#FFF; font-size:0.65rem; font-weight:700; padding:2px 6px; border-radius:4px;'>AVANTI</span>"
                if dept == "Avanti"
                else "<span style='background:#0284C7; color:#FFF; font-size:0.65rem; font-weight:700; padding:2px 6px; border-radius:4px;'>TREQUARTI</span>"
            )

            bar_pct = max(5, min(100, int((val / max_val) * 100)))

            row_block = f"""
            <div style="{row_border} border-radius:12px; padding:10px 16px; margin-bottom:8px; display:flex; align-items:center; gap:16px;">
                <div style="{badge_style} width:44px; height:32px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:0.85rem; flex-shrink:0;">
                    {badge_text}
                </div>
                <div style="flex-shrink:0;">
                    {avatar_html}
                </div>
                <div style="min-width:180px; flex-shrink:0;">
                    <div style="font-size:1.02rem; font-weight:800; color:#0F172A; line-height:1.2;">
                        {ath_name}
                    </div>
                    <div style="display:flex; align-items:center; gap:6px; margin-top:3px;">
                        {dept_badge}
                        <span style="font-size:0.75rem; color:#64748B;">{role} &bull; {club}</span>
                    </div>
                </div>
                <div style="flex-grow:1; margin:0 14px;">
                    <div style="width:100%; height:10px; background:#E2E8F0; border-radius:999px; overflow:hidden;">
                        <div style="width:{bar_pct}%; height:100%; background:linear-gradient(90deg, #0066B2 0%, #0284C7 70%, #38BDF8 100%); border-radius:999px;"></div>
                    </div>
                    <div style="font-size:0.70rem; color:#94A3B8; margin-top:3px; display:flex; justify-content:space-between;">
                        <span>Carico registrato: <b>{load_kg:.1f} kg</b></span>
                        <span>Set analizzati: <b>{sets_count}</b></span>
                    </div>
                </div>
                <div style="text-align:right; min-width:110px; flex-shrink:0;">
                    <div style="font-size:1.35rem; font-weight:900; color:#0066B2; line-height:1.1;">
                        {val_display}
                    </div>
                </div>
            </div>
            """
            rows_html_list.append(row_block)

        crit_label = 'Media Serie' if sel_criterion == 'avg' else 'Miglior Ripetizione'
        leaderboard_full_html = f"""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:18px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); margin-bottom:24px;">
            <div style="font-size:0.78rem; font-weight:700; color:#0066B2; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:14px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;">
                <span>Atleti Classificati: <b>{len(ranking_df)}</b> &bull; Esercizio: <b>{sel_exercise}</b></span>
                <span>Periodo: <b>{period_label}</b></span>
                <span>Parametro: <b>{metric_label}</b> ({crit_label})</span>
            </div>
            {''.join(rows_html_list)}
        </div>
        """

        render_html(leaderboard_full_html)

    # --------------------------------------------------------------------------
    # GRAFICI DI APPROFONDIMENTO COLLETTIVO (PLOT CARICO-VELOCITÀ & REPARTI)
    # --------------------------------------------------------------------------
    col_g1, col_g2 = st.columns([1.3, 1])

    with col_g1:
        st.markdown(f"##### 📈 Profilo Carico-Velocità di Gruppo • {sel_exercise}")
        st.caption(f"Relazione tra carico sul bilanciere (kg) e velocità media (m/s) &bull; Periodo: **{period_label}**")

        df_sets = utils.get_gymaware_df(exercise=sel_exercise, start_date=s_iso, end_date=e_iso, row_type="Average")
        if not df_sets.empty and "mean_velocity" in df_sets.columns and "bar_weight" in df_sets.columns:
            clean_scatter = df_sets.dropna(subset=["mean_velocity", "bar_weight"])
            if not clean_scatter.empty:
                fig_sc = px.scatter(
                    clean_scatter,
                    x="bar_weight",
                    y="mean_velocity",
                    color="athlete_name",
                    hover_data=["date", "set_id"],
                    labels={"bar_weight": "Carico Bilanciere (kg)", "mean_velocity": "Velocità Media (m/s)"},
                )
                if len(clean_scatter) >= 2 and clean_scatter["bar_weight"].nunique() >= 2:
                    try:
                        slope, intercept = np.polyfit(clean_scatter["bar_weight"], clean_scatter["mean_velocity"], 1)
                        x_vals = np.linspace(clean_scatter["bar_weight"].min(), clean_scatter["bar_weight"].max(), 50)
                        y_vals = slope * x_vals + intercept
                        fig_sc.add_trace(go.Scatter(
                            x=x_vals,
                            y=y_vals,
                            mode="lines",
                            name=f"Trendline Squadra (V={slope:.4f}·L + {intercept:.2f})",
                            line=dict(color="#D4AF37", width=2.5, dash="dash"),
                        ))
                    except Exception:
                        pass
                fig_sc.update_layout(
                    height=360,
                    margin=dict(l=20, r=20, t=10, b=20),
                    plot_bgcolor="#F8FAFC",
                    paper_bgcolor="#FFFFFF",
                    showlegend=False,
                )
                fig_sc.update_xaxes(gridcolor="#E2E8F0", title_font=dict(size=11))
                fig_sc.update_yaxes(gridcolor="#E2E8F0", title_font=dict(size=11))
                st.plotly_chart(fig_sc, use_container_width=True)
            else:
                st.info("Dati insufficienti per il grafico carico-velocità.")
        else:
            st.info("Nessuna serie registrata per questo esercizio.")

    with col_g2:
        st.markdown(f"##### ⚖️ Distribuzione per Reparto (Avanti vs TreQuarti)")
        st.caption(f"Confronto boxplot {metric_label} tra i due reparti federali")

        if not ranking_df.empty and "department" in ranking_df.columns:
            df_valid_dept = ranking_df[ranking_df["department"].isin(["Avanti", "TreQuarti"])]
            if not df_valid_dept.empty:
                fig_box = px.box(
                    df_valid_dept,
                    x="department",
                    y="metric_value",
                    color="department",
                    points="all",
                    hover_name="athlete_name",
                    color_discrete_map={"Avanti": "#0066B2", "TreQuarti": "#0284C7"},
                    labels={"department": "Reparto", "metric_value": metric_label},
                )
                fig_box.update_layout(
                    height=360,
                    margin=dict(l=20, r=20, t=10, b=20),
                    plot_bgcolor="#F8FAFC",
                    paper_bgcolor="#FFFFFF",
                    showlegend=False,
                )
                fig_box.update_xaxes(gridcolor="#E2E8F0", title_font=dict(size=11))
                fig_box.update_yaxes(gridcolor="#E2E8F0", title_font=dict(size=11))
                st.plotly_chart(fig_box, use_container_width=True)
            else:
                st.info("Nessun reparto identificato.")
        else:
            st.info("Dati insufficienti per il confronto tra reparti.")


# ==============================================================================
# 2. ANALISI INDIVIDUALE ATLETA (PROFILI VBT, 1RM TEORICO, REP-BY-REP)
# ==============================================================================

def _render_tab_atleta(t: dict):
    all_athletes = utils.get_gymaware_athletes()
    if not all_athletes:
        st.warning("Nessun atleta con misurazioni GymAware registrate.")
        return

    # --------------------------------------------------------------------------
    # SELETTORE ATLETA CON FOTO & SCHEDA PROFILO
    # --------------------------------------------------------------------------
    sel_c1, sel_c2, sel_c3, sel_c4 = st.columns([1.2, 1.2, 1.1, 1.3])
    with sel_c1:
        sel_ath = st.selectbox("👤 Seleziona Giocatore", all_athletes, key="gymaware_indiv_ath")

    ath_all_data = utils.get_gymaware_df(athlete=sel_ath)
    ath_exercises = sorted(ath_all_data["exercise"].dropna().unique().tolist())

    from datetime import datetime

    def _parse_d_sort(d):
        try:
            return datetime.strptime(str(d).strip(), "%d/%m/%Y")
        except Exception:
            return datetime.min

    ath_dates_raw = ath_all_data["date"].dropna().unique().tolist()
    ath_dates = sorted(ath_dates_raw, key=_parse_d_sort, reverse=True)

    with sel_c2:
        sel_ex = st.selectbox("🏋️ Esercizio", ath_exercises if ath_exercises else ["Tutti"], key="gymaware_indiv_ex")

    period_ath_options = [
        "Tutto lo Storico",
        "Ultima Seduta",
        "Ultimi 7 Giorni",
        "Ultimi 30 Giorni",
        "Ultimi 3 Mesi",
        "Singola Data",
        "Periodo Personalizzato",
    ]
    with sel_c3:
        sel_indiv_period = st.selectbox("📅 Periodo / Seduta", period_ath_options, index=0, key="gymaware_indiv_period")

    # Gestione date per il periodo
    s_iso, e_iso, period_label = None, None, sel_indiv_period
    if sel_indiv_period == "Singola Data":
        chosen_date = st.selectbox("Seleziona Data Specifica", ath_dates if ath_dates else ["Nessuna data"], key="gymaware_indiv_single_date")
        s_iso = utils._format_gymaware_date_to_iso(chosen_date)
        e_iso = s_iso
        period_label = f"Seduta del {chosen_date}"
    elif sel_indiv_period == "Periodo Personalizzato":
        parsed_ath_d = [datetime.strptime(d, "%d/%m/%Y").date() for d in ath_dates if d and _parse_d_sort(d) != datetime.min]
        min_d = min(parsed_ath_d) if parsed_ath_d else datetime.now().date()
        max_d = max(parsed_ath_d) if parsed_ath_d else datetime.now().date()
        c_dates = st.date_input(
            "Intervallo Date Atleta",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
            key="gymaware_indiv_custom_dates",
        )
        s_iso, e_iso, period_label = _resolve_period(sel_indiv_period, c_dates, ath_dates)
    else:
        s_iso, e_iso, period_label = _resolve_period(sel_indiv_period, None, ath_dates)

    # Mappa completa di tutte le metriche accelerometriche supportate
    available_metrics_def = {
        "mean_velocity": {
            "label": "Velocità Media • Mean Velocity (m/s)",
            "short": "Velocità Media",
            "unit": "m/s",
            "loss_label": "Perdita Vel.",
            "fmt": "{:.2f}",
        },
        "peak_velocity": {
            "label": "Velocità di Picco • Peak Velocity (m/s)",
            "short": "Velocità Picco",
            "unit": "m/s",
            "loss_label": "Perdita Vel. Picco",
            "fmt": "{:.2f}",
        },
        "mean_power": {
            "label": "Potenza Media • Mean Power (W)",
            "short": "Potenza Media",
            "unit": "W",
            "loss_label": "Calo Potenza",
            "fmt": "{:,.0f}",
        },
        "mean_power_wkg": {
            "label": "Potenza Relativa • Power W/kg (W/kg)",
            "short": "Potenza W/kg",
            "unit": "W/kg",
            "loss_label": "Calo Potenza W/kg",
            "fmt": "{:.1f}",
        },
        "height": {
            "label": "Altezza Salto / Corsa • Height (m)",
            "short": "Altezza Salto",
            "unit": "m",
            "loss_label": "Calo Elevazione",
            "fmt": "{:.3f}",
        },
        "dip": {
            "label": "Profondità Eccentrica • Dip (m)",
            "short": "Profondità Dip",
            "unit": "m",
            "loss_label": "Variazione Dip",
            "fmt": "{:.3f}",
        },
    }

    # Rileva dinamicamente quali metriche hanno valori registrati per questo esercizio
    ex_data = ath_all_data[ath_all_data["exercise"] == sel_ex] if "exercise" in ath_all_data.columns else ath_all_data
    valid_metric_keys = [
        k for k in available_metrics_def.keys()
        if k in ex_data.columns and ex_data[k].dropna().count() > 0
    ]
    if not valid_metric_keys:
        valid_metric_keys = list(available_metrics_def.keys())

    with sel_c4:
        sel_metric_key = st.selectbox(
            "📊 Parametro da Visualizzare",
            options=valid_metric_keys,
            format_func=lambda k: available_metrics_def[k]["label"],
            key=f"gymaware_indiv_metric_{sel_ex}",
        )

    m_info = available_metrics_def[sel_metric_key]
    m_label = m_info["label"]
    m_short = m_info["short"]
    m_unit = m_info["unit"]
    m_fmt = m_info["fmt"]
    m_loss_label = m_info["loss_label"]

    # Recupera anagrafica da roster
    p_df = utils.get_players_df()
    ath_clean = sel_ath.strip().lower()
    match_player = p_df[p_df["name_display"].str.lower() == ath_clean]
    if match_player.empty:
        last_part = ath_clean.split()[-1] if ath_clean.split() else ""
        match_player = p_df[p_df["name_display"].str.lower().str.contains(last_part)]

    role = match_player.iloc[0]["role"] if not match_player.empty else "N/D"
    dept = match_player.iloc[0]["department"] if not match_player.empty else utils.ROLE_TO_DEPT.get(role, "N/D")
    club = match_player.iloc[0]["club"] if not match_player.empty else "FIR"

    # Statistiche atleta complessive
    ath_sets = ath_all_data["set_id"].nunique()
    ath_reps = len(ath_all_data[ath_all_data["row_type"] == "Rep"])
    ath_max_vel = ath_all_data["peak_velocity"].max() or 0.0
    ath_max_pwr = ath_all_data["mean_power"].max() or 0.0

    b64_photo = utils.get_player_photo_base64(sel_ath, max_width=180)
    photo_html = (
        f'<img src="data:image/jpeg;base64,{b64_photo}" style="width:72px; height:72px; border-radius:50%; object-fit:cover; border:3px solid #D4AF37; box-shadow:0 3px 10px rgba(0,0,0,0.20);" alt="{sel_ath}">'
        if b64_photo
        else f'<div style="width:72px; height:72px; border-radius:50%; background:#0066B2; color:#FFF; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1.3rem; border:3px solid #D4AF37;">{sel_ath[:2].upper()}</div>'
    )

    ath_banner_html = f"""
    <div style="background:linear-gradient(135deg, #002B49 0%, #004D7A 60%, #0066B2 100%); border:2px solid #D4AF37; border-radius:14px; padding:16px 22px; margin:14px 0 22px 0; color:#FFFFFF; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:16px;">
        <div style="display:flex; align-items:center; gap:18px;">
            {photo_html}
            <div>
                <div style="font-size:0.75rem; font-weight:800; text-transform:uppercase; letter-spacing:0.12em; color:#D4AF37;">PASSAPORTO VBT ATLETA &bull; GYMAWARE</div>
                <div style="font-size:1.6rem; font-weight:900; color:#FFFFFF; margin:2px 0;">{sel_ath}</div>
                <div style="font-size:0.80rem; color:#BAE6FD;">
                    Reparto: <b>{dept}</b> &bull; Ruolo: <b>{role}</b> &bull; Club: <b>{club}</b>
                </div>
            </div>
        </div>
        <div style="display:flex; gap:12px; align-items:center;">
            <div style="background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.20); border-radius:10px; padding:8px 14px; text-align:center;">
                <div style="font-size:0.68rem; color:#93C5FD; text-transform:uppercase; font-weight:700;">Serie Totali</div>
                <div style="font-size:1.3rem; font-weight:900; color:#FFFFFF;">{ath_sets}</div>
            </div>
            <div style="background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.20); border-radius:10px; padding:8px 14px; text-align:center;">
                <div style="font-size:0.68rem; color:#93C5FD; text-transform:uppercase; font-weight:700;">Ripetizioni</div>
                <div style="font-size:1.3rem; font-weight:900; color:#FFFFFF;">{ath_reps}</div>
            </div>
            <div style="background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.20); border-radius:10px; padding:8px 14px; text-align:center;">
                <div style="font-size:0.68rem; color:#93C5FD; text-transform:uppercase; font-weight:700;">Peak Vel</div>
                <div style="font-size:1.3rem; font-weight:900; color:#FDE68A;">{ath_max_vel:.2f} <span style="font-size:0.75rem;">m/s</span></div>
            </div>
            <div style="background:rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.20); border-radius:10px; padding:8px 14px; text-align:center;">
                <div style="font-size:0.68rem; color:#93C5FD; text-transform:uppercase; font-weight:700;">Max Power</div>
                <div style="font-size:1.3rem; font-weight:900; color:#34D399;">{ath_max_pwr:,.0f} <span style="font-size:0.75rem;">W</span></div>
            </div>
        </div>
    </div>
    """
    render_html(ath_banner_html)

    ath_filtered = utils.get_gymaware_df(
        athlete=sel_ath,
        exercise=sel_ex,
        start_date=s_iso,
        end_date=e_iso,
    )

    if ath_filtered.empty:
        st.info("Nessuna serie registrata con i filtri selezionati.")
        return

    # --------------------------------------------------------------------------
    # 1. PROFILO CARICO-PARAMETRO & REGRESSIONE SCIENTIFICA
    # --------------------------------------------------------------------------
    st.markdown(f"#### 📊 Profilo Carico-{m_short} • {sel_ex}")
    if sel_metric_key == "mean_velocity":
        st.caption("Regressione lineare VBT e previsione del massimale basata sulla Minimum Velocity Threshold (MVT)")
    elif sel_metric_key == "peak_velocity":
        st.caption("Relazione lineare tra sovraccarico (kg) e velocità di picco istantanea (m/s)")
    elif "power" in sel_metric_key:
        st.caption(f"Curva Carico-{m_short}: erogazione di potenza al variare del carico e individuazione della zona di potenza ottimale (Pmax)")
    elif sel_metric_key == "height":
        st.caption("Relazione tra sovraccarico ed elevazione del salto / spostamento verticale (m)")
    elif sel_metric_key == "dip":
        st.caption("Profondità dell'escursione eccentrica in contromovimento in funzione del carico")
    else:
        st.caption(f"Andamento di {m_short} ({m_unit}) in funzione del carico sollevato")

    reps_data = ath_filtered[ath_filtered["row_type"] == "Rep"].dropna(subset=["bar_weight", sel_metric_key])
    sets_data = ath_filtered[ath_filtered["row_type"] == "Average"].dropna(subset=["bar_weight", sel_metric_key])

    reg_df = sets_data if len(sets_data) >= 3 else reps_data

    col_prof1, col_prof2 = st.columns([1.4, 1])

    with col_prof1:
        if len(reg_df) >= 2 and reg_df["bar_weight"].nunique() >= 2:
            x_loads = reg_df["bar_weight"].values
            y_vals = reg_df[sel_metric_key].values

            slope, intercept = np.polyfit(x_loads, y_vals, 1)
            correlation_matrix = np.corrcoef(x_loads, y_vals)
            r_squared = correlation_matrix[0, 1] ** 2 if correlation_matrix.shape == (2, 2) else 0.0

            mvt_map = {
                "Back Squat": 0.30,
                "Box Squat": 0.30,
                "Bench Press": 0.15,
                "Trap Bar Deadlift": 0.35,
                "Hang Clean Pull": 0.50,
                "Clean Pull": 0.50,
                "Trap Bar Jump": 1.00,
            }
            mvt = mvt_map.get(sel_ex, 0.30)
            estimated_1rm = (mvt - intercept) / slope if (slope < 0 and sel_metric_key == "mean_velocity") else None

            fig_reg = go.Figure()

            if not reps_data.empty:
                fig_reg.add_trace(go.Scatter(
                    x=reps_data["bar_weight"],
                    y=reps_data[sel_metric_key],
                    mode="markers",
                    name="Singole Reps",
                    marker=dict(size=7, color="#94A3B8", opacity=0.6),
                ))

            if not sets_data.empty:
                fig_reg.add_trace(go.Scatter(
                    x=sets_data["bar_weight"],
                    y=sets_data[sel_metric_key],
                    mode="markers",
                    name="Medie Serie",
                    marker=dict(size=11, color="#0066B2", symbol="circle", line=dict(width=2, color="#FFFFFF")),
                ))

            x_max_line = (estimated_1rm if (estimated_1rm and estimated_1rm < 350) else max(x_loads) * 1.15)
            x_line = np.linspace(min(x_loads) * 0.8, x_max_line, 50)
            y_line = slope * x_line + intercept
            fig_reg.add_trace(go.Scatter(
                x=x_line,
                y=y_line,
                mode="lines",
                name=f"Trendline (R²={r_squared:.3f})",
                line=dict(color="#D4AF37", width=3, dash="solid"),
            ))

            if estimated_1rm and 0 < estimated_1rm < 400 and sel_metric_key == "mean_velocity":
                fig_reg.add_trace(go.Scatter(
                    x=[estimated_1rm],
                    y=[mvt],
                    mode="markers+text",
                    name=f"1RM Stimato ({estimated_1rm:.1f} kg)",
                    text=[f"1RM: {estimated_1rm:.1f} kg"],
                    textposition="top right",
                    marker=dict(size=14, color="#EF4444", symbol="star"),
                ))

            fig_reg.update_layout(
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
                plot_bgcolor="#F8FAFC",
                paper_bgcolor="#FFFFFF",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_reg.update_xaxes(title="Carico Bilanciere - Bar Weight (kg)", gridcolor="#E2E8F0")
            fig_reg.update_yaxes(title=f"{m_short} ({m_unit})", gridcolor="#E2E8F0")
            st.plotly_chart(fig_reg, use_container_width=True)
        else:
            slope, intercept, r_squared, estimated_1rm = None, None, None, None
            st.info(f"Sono necessarie almeno 2 serie con carichi differenti per costruire il profilo Carico-{m_short}.")

    with col_prof2:
        if slope is not None and y_vals is not None and len(y_vals) > 0:
            if sel_metric_key == "mean_velocity" and estimated_1rm and 0 < estimated_1rm < 400:
                box_param_html = f"""
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:16px;">
                    <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase;">Stima Massimale Teorico (1RM)</div>
                    <div style="font-size:2.2rem; font-weight:900; color:#EF4444; line-height:1.1; margin:6px 0;">
                        {estimated_1rm:.1f} <span style="font-size:1.1rem; font-weight:700;">kg</span>
                    </div>
                    <div style="font-size:0.75rem; color:#64748B; margin-bottom:12px;">
                        Basato su MVT di <b>{mvt:.2f} m/s</b> ({sel_ex})
                    </div>
                    <div style="border-top:1px solid #E2E8F0; padding-top:10px; margin-top:10px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">Coefficiente R² (Linearità):</span>
                            <b style="color:{'#059669' if r_squared > 0.90 else '#D97706'};">{r_squared:.3f}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">Equazione Lineare:</span>
                            <b style="font-family:monospace; color:#0066B2;">V = {slope:.4f}·L + {intercept:.2f}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem;">
                            <span style="color:#64748B;">Perdita per ogni 10kg:</span>
                            <b>{abs(slope * 10):.2f} m/s</b>
                        </div>
                    </div>
                </div>
                """
            elif "power" in sel_metric_key:
                best_idx = np.argmax(y_vals)
                best_val = y_vals[best_idx]
                best_load = x_loads[best_idx]
                mean_p = np.mean(y_vals)
                box_param_html = f"""
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:16px;">
                    <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase;">Picco di Potenza Registrato</div>
                    <div style="font-size:2.2rem; font-weight:900; color:#D97706; line-height:1.1; margin:6px 0;">
                        {best_val:,.0f} <span style="font-size:1.1rem; font-weight:700;">{m_unit}</span>
                    </div>
                    <div style="font-size:0.75rem; color:#64748B; margin-bottom:12px;">
                        Carico ottimale (Pmax): <b>{best_load:.1f} kg</b>
                    </div>
                    <div style="border-top:1px solid #E2E8F0; padding-top:10px; margin-top:10px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">Potenza Media Serie:</span>
                            <b>{mean_p:,.0f} {m_unit}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">R² Regressione:</span>
                            <b style="color:{'#059669' if r_squared > 0.85 else '#D97706'};">{r_squared:.3f}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem;">
                            <span style="color:#64748B;">Trend Carico-Potenza:</span>
                            <b>{slope:+.2f} {m_unit}/kg</b>
                        </div>
                    </div>
                </div>
                """
            elif sel_metric_key == "height":
                best_h = np.max(y_vals)
                mean_h = np.mean(y_vals)
                box_param_html = f"""
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:16px;">
                    <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase;">Massima Elevazione Raggiunta</div>
                    <div style="font-size:2.2rem; font-weight:900; color:#0066B2; line-height:1.1; margin:6px 0;">
                        {best_h:.3f} <span style="font-size:1.1rem; font-weight:700;">m</span>
                    </div>
                    <div style="font-size:0.75rem; color:#64748B; margin-bottom:12px;">
                        Equivalente: <b>{best_h*100:.1f} cm</b> ({sel_ex})
                    </div>
                    <div style="border-top:1px solid #E2E8F0; padding-top:10px; margin-top:10px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">Media Elevazione:</span>
                            <b>{mean_h*100:.1f} cm</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">R² Linearità:</span>
                            <b style="color:{'#059669' if r_squared > 0.85 else '#D97706'};">{r_squared:.3f}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem;">
                            <span style="color:#64748B;">Decadimento per 10kg:</span>
                            <b>{abs(slope * 10)*100:.1f} cm</b>
                        </div>
                    </div>
                </div>
                """
            else:
                best_v = np.max(y_vals)
                mean_v = np.mean(y_vals)
                box_param_html = f"""
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:12px; padding:16px;">
                    <div style="font-size:0.75rem; font-weight:700; color:#64748B; text-transform:uppercase;">Valore Massimo Registrato</div>
                    <div style="font-size:2.2rem; font-weight:900; color:#0066B2; line-height:1.1; margin:6px 0;">
                        {m_fmt.format(best_v)} <span style="font-size:1.1rem; font-weight:700;">{m_unit}</span>
                    </div>
                    <div style="font-size:0.75rem; color:#64748B; margin-bottom:12px;">
                        Parametro: <b>{m_short}</b> ({sel_ex})
                    </div>
                    <div style="border-top:1px solid #E2E8F0; padding-top:10px; margin-top:10px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">Valore Medio:</span>
                            <b>{m_fmt.format(mean_v)} {m_unit}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem; margin-bottom:6px;">
                            <span style="color:#64748B;">R² Regressione:</span>
                            <b style="color:{'#059669' if r_squared > 0.85 else '#D97706'};">{r_squared:.3f}</b>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.80rem;">
                            <span style="color:#64748B;">Variazione per 10kg:</span>
                            <b>{slope * 10:+.2f} {m_unit}</b>
                        </div>
                    </div>
                </div>
                """
            render_html(box_param_html)
        else:
            st.info(f"Dati insufficienti per calcolare la regressione sul parametro **{m_short}**.")

    # --------------------------------------------------------------------------
    # 2. ANALISI A ISTOGRAMMI REP-BY-REP PER DATA & TREND INTRA-SERIE
    # --------------------------------------------------------------------------
    st.markdown(f"#### ⚡ Analisi Rep-by-Rep a Istogrammi per Data • {m_short}")
    st.caption(
        f"Istogrammi raggruppati per sessione: le ripetizioni della stessa data sono adiacenti (attaccate), separate tra date diverse &bull; Periodo: **{period_label}**"
    )

    reps_only = ath_filtered[ath_filtered["row_type"] == "Rep"].dropna(subset=[sel_metric_key])
    if not reps_only.empty:
        # Ordina cronologicamente le sessioni
        reps_only = reps_only.copy()
        reps_only["iso_dt"] = reps_only["date"].apply(utils._format_gymaware_date_to_iso)
        reps_only = reps_only.sort_values(by=["iso_dt", "set_id", "rep_number"], ascending=[True, True, True])

        # Date disponibili per il grafico
        available_chart_dates = reps_only["date"].unique().tolist()

        col_fc1, col_fc2 = st.columns([3, 1])
        with col_fc1:
            sel_chart_dates = st.multiselect(
                "📅 Date visualizzate nel Grafico (seleziona / deseleziona per filtrare):",
                options=available_chart_dates,
                default=available_chart_dates,
                key=f"chart_dates_{sel_ath}_{sel_ex}",
            )
        with col_fc2:
            show_bar_val = st.checkbox(
                "Mostra valori sulle barre",
                value=True,
                key=f"show_bar_val_{sel_ath}_{sel_ex}",
            )

        if not sel_chart_dates:
            st.info("Nessuna data selezionata. Seleziona almeno una data dal filtro soprastante per visualizzare il grafico.")
            chart_reps = pd.DataFrame()
        else:
            chart_reps = reps_only[reps_only["date"].isin(sel_chart_dates)]

            fig_reps = go.Figure()
            palette = ["#0066B2", "#0284C7", "#D4AF37", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899", "#6366F1", "#14B8A6", "#059669"]

            curr_x = 0
            tickvals = []
            ticktext = []

            for idx, (dt, g_dt) in enumerate(chart_reps.groupby("date", sort=False)):
                c = palette[idx % len(palette)]
                n_reps = len(g_dt)
                x_positions = [curr_x + i for i in range(n_reps)]
                center = curr_x + (n_reps - 1) / 2.0
                bw_val = g_dt.iloc[0].get("bar_weight", 0)

                tickvals.append(center)
                ticktext.append(f"<b>{dt}</b><br><span style='font-size:10px; color:#64748B;'>({n_reps} reps &bull; {bw_val:.0f}kg)</span>")

                hover_texts = []
                bar_texts = []
                for _, r_row in g_dt.iterrows():
                    s_id = r_row["set_id"]
                    r_num = r_row["rep_number"]
                    val = r_row[sel_metric_key]
                    bw = r_row.get("bar_weight", 0)
                    hover_texts.append(
                        f"<b>{dt}</b><br>Set: <b>{s_id}</b> &bull; Rep: <b>#{r_num}</b><br>Carico: <b>{bw:.1f} kg</b><br>{m_short}: <b>{m_fmt.format(val)} {m_unit}</b>"
                    )
                    bar_texts.append(m_fmt.format(val) if show_bar_val else f"R{r_num}")

                fig_reps.add_trace(go.Bar(
                    x=x_positions,
                    y=g_dt[sel_metric_key],
                    name=dt,
                    marker=dict(
                        color=c,
                        line=dict(color="#FFFFFF", width=1.5),
                    ),
                    width=0.98,  # istogrammi adiacenti / attaccati nella stessa data!
                    text=bar_texts,
                    textposition="outside" if show_bar_val else "inside",
                    textfont=dict(size=10, color="#0F172A"),
                    hovertext=hover_texts,
                    hoverinfo="text",
                ))

                # Spazio/stacco marcato tra date diverse
                curr_x += n_reps + 2.5

            fig_reps.update_layout(
                bargap=0.0,
                height=380,
                margin=dict(l=20, r=20, t=30, b=40),
                plot_bgcolor="#F8FAFC",
                paper_bgcolor="#FFFFFF",
                xaxis=dict(
                    tickmode="array",
                    tickvals=tickvals,
                    ticktext=ticktext,
                    gridcolor="#F1F5F9",
                    zeroline=False,
                ),
                yaxis=dict(
                    title=f"{m_short} ({m_unit})",
                    gridcolor="#E2E8F0",
                ),
                legend=dict(
                    title="📅 Date (clicca per attivare/disattivare):",
                    orientation="h",
                    yanchor="bottom",
                    y=1.04,
                    xanchor="right",
                    x=1,
                ),
            )
            st.plotly_chart(fig_reps, use_container_width=True)

        # Tabella di riepilogo per serie
        base_reps_for_table = chart_reps if not chart_reps.empty else reps_only
        set_summaries = []
        for set_id, g in base_reps_for_table.groupby("set_id", sort=False):
            if len(g) >= 1:
                v1 = g.iloc[0][sel_metric_key]
                v_min = g[sel_metric_key].min()
                v_loss = ((v1 - v_min) / v1 * 100) if (v1 and v1 > 0) else 0.0
                set_summaries.append({
                    "set_id": set_id,
                    "date": g.iloc[0]["date"],
                    "time": g.iloc[0]["time"],
                    "exercise": g.iloc[0]["exercise"],
                    "bar_weight": g.iloc[0]["bar_weight"],
                    "total_weight": g.iloc[0].get("total_weight", g.iloc[0]["bar_weight"]),
                    "reps_count": len(g),
                    "v_first": v1,
                    "v_min": v_min,
                    "v_mean": g[sel_metric_key].mean(),
                    "v_loss_pct": v_loss,
                })

        df_set_sum = pd.DataFrame(set_summaries)

        table_rows = []
        for _, sr in df_set_sum.iterrows():
            v_loss = sr["v_loss_pct"]
            if "velocity" in sel_metric_key:
                if v_loss < 10.0:
                    fatigue_badge = "<span style='background:#DCFCE7; color:#15803D; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Ottimale (&lt;10%)</span>"
                elif v_loss <= 20.0:
                    fatigue_badge = "<span style='background:#FEF3C7; color:#B45309; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Forza/Ipertrofia (10-20%)</span>"
                else:
                    fatigue_badge = "<span style='background:#FEE2E2; color:#B91C1C; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Fatica Alta (&gt;20%)</span>"
            elif "power" in sel_metric_key:
                if v_loss < 10.0:
                    fatigue_badge = "<span style='background:#DCFCE7; color:#15803D; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Potenza Stabile (&lt;10%)</span>"
                elif v_loss <= 20.0:
                    fatigue_badge = "<span style='background:#FEF3C7; color:#B45309; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Drop Moderato (10-20%)</span>"
                else:
                    fatigue_badge = "<span style='background:#FEE2E2; color:#B91C1C; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Fatica Severa (&gt;20%)</span>"
            else:
                if v_loss < 10.0:
                    fatigue_badge = "<span style='background:#DCFCE7; color:#15803D; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Costante (&lt;10%)</span>"
                elif v_loss <= 20.0:
                    fatigue_badge = "<span style='background:#FEF3C7; color:#B45309; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Calo Medio (10-20%)</span>"
                else:
                    fatigue_badge = "<span style='background:#FEE2E2; color:#B91C1C; font-weight:700; padding:2px 8px; border-radius:4px; font-size:0.75rem;'>Flessione Elevata (&gt;20%)</span>"

            loss_color = '#15803D' if v_loss < 10 else ('#B45309' if v_loss <= 20 else '#B91C1C')
            val_mean_disp = m_fmt.format(sr['v_mean']) + f" {m_unit}"
            val_first_disp = m_fmt.format(sr['v_first']) + f" {m_unit}"

            table_rows.append(f"""
            <tr style="border-bottom:1px solid #F1F5F9;">
                <td style="padding:8px 12px; font-weight:700;">Set {sr['set_id']}</td>
                <td style="padding:8px 12px; color:#64748B;">{sr['date']} {sr['time']}</td>
                <td style="padding:8px 12px; font-weight:700; color:#0066B2;">{sr['bar_weight']:.1f} kg</td>
                <td style="padding:8px 12px; text-align:center;">{sr['reps_count']}</td>
                <td style="padding:8px 12px; text-align:right; font-weight:700;">{val_mean_disp}</td>
                <td style="padding:8px 12px; text-align:right;">{val_first_disp}</td>
                <td style="padding:8px 12px; text-align:right; font-weight:800; color:{loss_color};">-{v_loss:.1f}%</td>
                <td style="padding:8px 12px; text-align:center;">{fatigue_badge}</td>
            </tr>
            """)

        table_html = f"""
        <table style="width:100%; border-collapse:collapse; font-size:0.82rem; background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; overflow:hidden; margin-top:10px;">
            <thead>
                <tr style="background:#F8FAFC; border-bottom:2px solid #E2E8F0; color:#475569; text-align:left;">
                    <th style="padding:10px 12px;">Set ID</th>
                    <th style="padding:10px 12px;">Data/Ora</th>
                    <th style="padding:10px 12px;">Carico Bilanciere</th>
                    <th style="padding:10px 12px; text-align:center;">Reps</th>
                    <th style="padding:10px 12px; text-align:right;">Media {m_short}</th>
                    <th style="padding:10px 12px; text-align:right;">Rep 1 {m_short}</th>
                    <th style="padding:10px 12px; text-align:right;">{m_loss_label}</th>
                    <th style="padding:10px 12px; text-align:center;">Stato Fatica</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
        """
        render_html(table_html)
    else:
        st.info("Nessuna singola ripetizione dettagliata disponibile per questo atleta.")

    # --------------------------------------------------------------------------
    # 3. TABELLA COMPLETA DETTAGLIO RIPETIZIONI (EXPORT-READY)
    # --------------------------------------------------------------------------
    with st.expander("📋 Mostra Registro Completo Tutte le Righe GymAware dell'Atleta", expanded=False):
        disp_cols = [
            "date", "time", "exercise", "set_id", "row_type", "rep_number",
            "bar_weight", "total_weight", "mean_velocity", "peak_velocity", "mean_power", "height", "dip"
        ]
        available_cols = [c for c in disp_cols if c in ath_filtered.columns]
        st.dataframe(
            ath_filtered[available_cols].rename(columns={
                "date": "Data",
                "time": "Ora",
                "exercise": "Esercizio",
                "set_id": "Set",
                "row_type": "Tipo Riga",
                "rep_number": "Rep #",
                "bar_weight": "Carico Bilanciere (kg)",
                "total_weight": "Peso Totale con BW (kg)",
                "mean_velocity": "Mean Vel (m/s)",
                "peak_velocity": "Peak Vel (m/s)",
                "mean_power": "Mean Power (W)",
                "height": "Height (m)",
                "dip": "Dip (m)",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ==============================================================================
# 3. CARICAMENTO & GESTIONE DATI CSV GYMAWARE
# ==============================================================================

def _render_tab_gestione(t: dict):
    render_html("""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); margin-bottom:22px;">
            <div style="font-size:1.15rem; font-weight:800; color:#0F172A; margin-bottom:4px;">
                📥 Importazione File Esportati da GymAware (VBT)
            </div>
            <div style="font-size:0.75rem; color:#64748B;">
                Supporta l'esportazione standard <code>Rep Statistics Table.csv</code> generata da GymAware Cloud o dall'applicazione iPad
            </div>
        </div>
    """)

    uploaded_file = st.file_uploader(
        "Seleziona o trascina il file CSV GymAware da caricare",
        type=["csv"],
        key="gymaware_csv_uploader",
    )

    if uploaded_file is not None:
        try:
            df_upload = pd.read_csv(uploaded_file)
            st.success(f"File **{uploaded_file.name}** caricato correttamente ({len(df_upload):,} righe rilevate).")

            norm_cols = [c.strip().lower() for c in df_upload.columns]
            has_vel = any("velocity" in c for c in norm_cols)
            has_set = any("set" in c for c in norm_cols)
            has_ath = any(c in norm_cols for c in ["first name", "athlete", "last name"])

            if not (has_vel and has_set and has_ath):
                st.error("Il file CSV caricato non sembra un formato compatibile con GymAware (mancano le colonne di velocità, set o atleta).")
            else:
                sets_detected = df_upload[df_upload.columns[norm_cols.index("set id")]].nunique() if "set id" in norm_cols else "N/D"
                st.info(f"Anteprima Riconoscimento: **{sets_detected}** serie uniche individuate.")

                imp_c1, imp_c2 = st.columns([1, 1])
                with imp_c1:
                    replace_opt = st.checkbox(
                        "Sostituisci l'intero archivio attuale (cancella i dati precedenti prima di importare)",
                        value=False,
                        key="gymaware_replace_check",
                    )
                with imp_c2:
                    if st.button("💾 Conferma e Salva nel Database SQLite", type="primary", use_container_width=True):
                        saved_count = utils.save_gymaware_from_df(df_upload, replace_all=replace_opt)
                        st.success(f"✅ Importazione completata con successo: inserite **{saved_count:,}** righe nel database!")
                        st.rerun()

                with st.expander("🔍 Anteprima Prime 10 Righe del File", expanded=False):
                    st.dataframe(df_upload.head(10), use_container_width=True)

        except Exception as e:
            st.error(f"Errore durante la lettura del file: {e}")

    # --------------------------------------------------------------------------
    # GESTIONE SESSIONI ATTIVE NEL DATABASE
    # --------------------------------------------------------------------------
    render_html("""
        <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:20px; box-shadow:0 2px 8px rgba(0,0,0,0.04); margin-bottom:22px; margin-top:20px;">
            <div style="font-size:1.15rem; font-weight:800; color:#0F172A; margin-bottom:4px;">
                🗂️ Registro Sessioni & Caricamenti GymAware (VBT)
            </div>
            <div style="font-size:0.75rem; color:#64748B;">
                Riepilogo puntuale degli ultimi caricamenti, metriche per sessione e gestione completa dei dati archiviati nel database SQLite
            </div>
        </div>
    """)

    all_data = utils.get_gymaware_df()
    if all_data.empty:
        st.info("Nessuna sessione GymAware presente nel database.")
    else:
        # Metriche generali del database
        db_overview = utils.get_gymaware_database_overview()
        last_up_ts = db_overview.get("last_upload_ts", "")
        if last_up_ts:
            try:
                from datetime import datetime as dt_cls
                ts_obj = dt_cls.strptime(str(last_up_ts)[:19], "%Y-%m-%d %H:%M:%S")
                last_up_str = ts_obj.strftime("%d/%m/%Y %H:%M")
            except Exception:
                last_up_str = str(last_up_ts)[:16]
        else:
            last_up_str = "N/D"

        # 1. KPI RIBBON GENERALE
        kpi_overview_html = textwrap.dedent(f"""
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap:14px; margin-bottom:22px;">
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:16px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
                <div style="font-size:0.72rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;">
                    🗃️ Record Totali
                </div>
                <div style="font-size:2.1rem; font-weight:900; color:#0F172A; line-height:1.1;">
                    {db_overview['total_rows']:,}
                </div>
                <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                    <b>{db_overview['total_reps']:,}</b> reps &bull; <b>{db_overview['total_sets']:,}</b> serie
                </div>
            </div>
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:16px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
                <div style="font-size:0.72rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;">
                    📅 Sessioni Archiviate
                </div>
                <div style="font-size:2.1rem; font-weight:900; color:#0066B2; line-height:1.1;">
                    {db_overview['total_sessions']}
                </div>
                <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                    Giornate distinte di test/allenamento VBT
                </div>
            </div>
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:16px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
                <div style="font-size:0.72rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;">
                    👥 Atleti Monitorati
                </div>
                <div style="font-size:2.1rem; font-weight:900; color:#059669; line-height:1.1;">
                    {db_overview['total_athletes']}
                </div>
                <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                    Giocatori censiti nel database
                </div>
            </div>
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:14px; padding:16px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.04);">
                <div style="font-size:0.72rem; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:4px;">
                    ⏱️ Ultimo Caricamento Batch
                </div>
                <div style="font-size:1.45rem; font-weight:900; color:#D97706; line-height:1.2; margin-top:4px;">
                    {last_up_str}
                </div>
                <div style="font-size:0.75rem; color:#94A3B8; margin-top:4px;">
                    +{db_overview['last_batch_rows']:,} righe &bull; {db_overview['last_batch_athletes']} atleti
                </div>
            </div>
        </div>
        """)
        render_html(kpi_overview_html)

        # 2. CARD DETTAGLIO ULTIMI CARICAMENTI PRESENTI NEL DATABASE
        recent_sessions = utils.get_gymaware_recent_sessions_summary(limit=4)
        if recent_sessions:
            render_html("""
                <div style="font-size:1.0rem; font-weight:800; color:#002B49; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                    <span>⚡ Ultime Sessioni Caricate nel Database</span>
                    <span style="font-size:0.72rem; font-weight:600; color:#64748B; background:#F1F5F9; border-radius:10px; padding:2px 8px;">Riepilogo Rapido</span>
                </div>
            """)

            cards_html_list = []
            for idx, s in enumerate(recent_sessions):
                is_latest = (idx == 0)
                badge_bg = "#ECFDF5" if is_latest else "#EFF6FF"
                badge_color = "#059669" if is_latest else "#0066B2"
                badge_text = "🟢 Più Recente" if is_latest else f"Seduta #{idx + 1}"
                top_border = "#0066B2" if is_latest else "#94A3B8"

                ex_items = [e.strip() for e in s["exercises"].split(",") if e.strip()]
                ex_disp = ", ".join(ex_items[:3])
                if len(ex_items) > 3:
                    ex_disp += f" (+{len(ex_items) - 3})"

                up_time_str = s['last_uploaded_at'][:16] if s['last_uploaded_at'] else "N/D"

                card_box = f"""
                <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-top:4px solid {top_border}; border-radius:14px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,0.04); display:flex; flex-direction:column; justify-content:space-between;">
                    <div>
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                            <div style="font-size:1.08rem; font-weight:900; color:#002B49;">
                                📅 {s['date']}
                            </div>
                            <span style="background:{badge_bg}; color:{badge_color}; font-size:0.68rem; font-weight:700; padding:3px 8px; border-radius:10px;">
                                {badge_text}
                            </span>
                        </div>
                        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; padding:8px 6px; margin-bottom:12px; text-align:center;">
                            <div>
                                <div style="font-size:0.65rem; color:#64748B; font-weight:700; text-transform:uppercase;">Atleti</div>
                                <div style="font-size:1.15rem; font-weight:900; color:#0F172A;">{s['n_athletes']}</div>
                            </div>
                            <div>
                                <div style="font-size:0.65rem; color:#64748B; font-weight:700; text-transform:uppercase;">Serie</div>
                                <div style="font-size:1.15rem; font-weight:900; color:#0066B2;">{s['n_sets']}</div>
                            </div>
                            <div>
                                <div style="font-size:0.65rem; color:#64748B; font-weight:700; text-transform:uppercase;">Reps</div>
                                <div style="font-size:1.15rem; font-weight:900; color:#059669;">{s['n_reps']}</div>
                            </div>
                        </div>
                        <div style="font-size:0.75rem; color:#334155; line-height:1.5; margin-bottom:10px;">
                            <div>⚡ Vel. Media: <b style="color:#0066B2;">{s['avg_mean_vel']:.2f} m/s</b> &bull; Picco: <b>{s['max_vel']:.2f} m/s</b></div>
                            <div>🎯 Carico Max: <b style="color:#D97706;">{s['max_kg']:.1f} kg</b></div>
                        </div>
                        <div style="font-size:0.72rem; color:#64748B; background:#F1F5F9; border-radius:6px; padding:6px 8px; margin-bottom:8px;">
                            <b style="color:#0F172A;">Esercizi:</b> {ex_disp if ex_disp else 'N/D'}
                        </div>
                    </div>
                    <div style="font-size:0.68rem; color:#94A3B8; text-align:right; border-top:1px dashed #E2E8F0; padding-top:6px; margin-top:6px;">
                        🕒 Caricato: {up_time_str}
                    </div>
                </div>
                """
                cards_html_list.append(card_box)

            cards_grid_html = f"""
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap:14px; margin-bottom:22px;">
                {''.join(cards_html_list)}
            </div>
            """
            render_html(cards_grid_html)

        # 3. STORICO BATCH IMPORTAZIONI CSV (COLLAPSIBLE)
        batches = utils.get_gymaware_batches_summary(limit=10)
        if batches:
            with st.expander("📦 Dettaglio Storico Caricamenti Batch (File CSV Importati)", expanded=False):
                df_batches = pd.DataFrame(batches).rename(columns={
                    "created_at": "Data/Ora Importazione",
                    "n_rows": "Righe Importate",
                    "n_dates": "Sessioni Coperte",
                    "n_athletes": "Atleti Coinvolti",
                    "n_sets": "Serie Totali",
                    "n_reps": "Ripetizioni",
                    "date_range": "Intervallo Date Sedute",
                })
                st.dataframe(df_batches, use_container_width=True, hide_index=True)

        # 4. TABELLA CRONOLOGICA COMPLETA DELLE SESSIONI
        render_html("""
            <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-top:16px; margin-bottom:8px;">
                <div style="font-size:1.0rem; font-weight:800; color:#002B49;">
                    📋 Tutte le Sessioni Registrate nel Database
                </div>
                <div style="font-size:0.75rem; color:#64748B;">
                    💡 Ordinata per data decrescente. Clicca sull'intestazione <b>'Data'</b> per invertire l'ordine cronologico in modo puntuale.
                </div>
            </div>
        """)

        date_groups = []
        for d in utils.get_gymaware_dates():
            g = all_data[all_data["date"] == d]
            if g.empty:
                continue
            ex_list = ", ".join(g["exercise"].dropna().unique().tolist()[:4])
            if len(g["exercise"].dropna().unique()) > 4:
                ex_list += "..."
            d_dt = pd.to_datetime(d, format="%d/%m/%Y", errors="coerce")
            date_groups.append({
                "Data": d_dt,
                "Data_str": d,
                "Esercizi": ex_list,
                "Atleti": g["athlete_name"].nunique(),
                "Serie": g["set_id"].nunique(),
                "Ripetizioni": int((g["row_type"] == "Rep").sum()),
                "Righe Totali": len(g),
            })

        df_summary_dates = pd.DataFrame(date_groups)
        st.dataframe(
            df_summary_dates[["Data", "Esercizi", "Atleti", "Serie", "Ripetizioni", "Righe Totali"]],
            column_config={
                "Data": st.column_config.DateColumn(
                    "Data",
                    format="DD/MM/YYYY",
                    help="Data della sessione GymAware (ordinabile cronologicamente in modo puntuale)",
                ),
                "Esercizi": st.column_config.TextColumn("Esercizi Principali"),
                "Atleti": st.column_config.NumberColumn("Atleti Coinvolti", format="%d"),
                "Serie": st.column_config.NumberColumn("Serie Totali", format="%d"),
                "Ripetizioni": st.column_config.NumberColumn("Reps Valide", format="%d"),
                "Righe Totali": st.column_config.NumberColumn("Righe Record", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

        del_date_options = df_summary_dates["Data_str"].tolist()

        st.markdown("<hr style='border-color:#E2E8F0; margin:20px 0;'>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # ELIMINAZIONE DATI (TUTTI GLI ATLETI O SINGOLO ATLETA)
        # ----------------------------------------------------------------------
        render_html("""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:16px 20px; margin-bottom:14px;">
                <div style="font-size:1.05rem; font-weight:800; color:#0F172A;">
                    🗑️ Eliminazione Dati dal Database
                </div>
                <div style="font-size:0.75rem; color:#64748B;">
                    Scegli se rimuovere l'intera giornata di tutta la squadra oppure solo le misurazioni di un singolo atleta
                </div>
            </div>
        """)

        del_mode = st.radio(
            "Seleziona ambito eliminazione:",
            options=["Tutti gli atleti della giornata", "Singolo atleta in una giornata"],
            horizontal=True,
            key="gymaware_del_mode",
        )

        if del_mode == "Tutti gli atleti della giornata":
            col_d1, col_d2 = st.columns([2, 1])
            with col_d1:
                date_to_del = st.selectbox(
                    "Seleziona la data da eliminare per tutta la squadra",
                    del_date_options,
                    key="gymaware_del_date_all",
                )
            with col_d2:
                st.write("")
                st.write("")
                if st.button(f"🗑️ Elimina Tutti i Dati del {date_to_del}", type="secondary", use_container_width=True):
                    deleted_rows = utils.delete_gymaware_date(date_to_del)
                    st.warning(f"Rimosse {deleted_rows} righe per tutta la squadra relative al {date_to_del}.")
                    st.rerun()
        else:
            col_d1, col_d2, col_d3 = st.columns([1.2, 1.2, 1.2])
            with col_d1:
                date_to_del = st.selectbox(
                    "1. Seleziona la data",
                    del_date_options,
                    key="gymaware_del_date_single",
                )
            with col_d2:
                ath_options_for_date = utils.get_gymaware_athletes_for_date(date_to_del)
                ath_to_del = st.selectbox(
                    "2. Seleziona l'atleta",
                    ath_options_for_date if ath_options_for_date else ["Nessun atleta"],
                    key="gymaware_del_ath_single",
                )
            with col_d3:
                st.write("")
                st.write("")
                if st.button(f"🗑️ Elimina {ath_to_del} ({date_to_del})", type="secondary", use_container_width=True):
                    if ath_to_del and ath_to_del != "Nessun atleta":
                        del_rows = utils.delete_gymaware_athlete_date(ath_to_del, date_to_del)
                        st.warning(f"Rimosse {del_rows} righe di {ath_to_del} per la data {date_to_del}.")
                        st.rerun()

        st.markdown("<hr style='border-color:#E2E8F0; margin:24px 0;'>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # MODIFICA DATI SINGOLO ATLETA IN UNA GIORNATA
        # ----------------------------------------------------------------------
        render_html("""
            <div style="background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:16px 20px; margin-bottom:14px;">
                <div style="font-size:1.05rem; font-weight:800; color:#0F172A;">
                    ✏️ Modifica Dati di un Singolo Atleta in una Giornata
                </div>
                <div style="font-size:0.75rem; color:#64748B;">
                    Seleziona data e giocatore per visualizzare e correggere carichi al bilanciere, velocità, serie, ripetizioni o note con salvataggio immediato nel database
                </div>
            </div>
        """)

        ed_c1, ed_c2 = st.columns([1, 1])
        with ed_c1:
            edit_date = st.selectbox(
                "📅 Seleziona Data Sessione da Modificare",
                del_date_options,
                key="gymaware_edit_date_sel",
            )
        with ed_c2:
            athletes_edit_opts = utils.get_gymaware_athletes_for_date(edit_date)
            edit_ath = st.selectbox(
                "👤 Seleziona Giocatore da Modificare",
                athletes_edit_opts if athletes_edit_opts else ["Nessun atleta"],
                key="gymaware_edit_ath_sel",
            )

        if edit_ath and edit_ath != "Nessun atleta":
            df_to_edit = utils.get_gymaware_df(athlete=edit_ath, date=edit_date)
            if df_to_edit.empty:
                st.info(f"Nessun dato registrato per {edit_ath} in data {edit_date}.")
            else:
                st.caption(f"Trovate **{len(df_to_edit)}** righe registrate per **{edit_ath}** in data **{edit_date}**. Modifica i campi desiderati nella tabella e premi Salva Modifiche.")

                # Colonne principali per l'editor interattivo
                cols_order = [
                    "id", "date", "time", "athlete_name", "exercise", "set_id", "row_type",
                    "rep_number", "bar_weight", "total_weight", "mean_velocity", "peak_velocity",
                    "mean_power", "peak_power", "height", "dip", "notes"
                ]
                existing_cols = [c for c in cols_order if c in df_to_edit.columns]
                for c in df_to_edit.columns:
                    if c not in existing_cols:
                        existing_cols.append(c)

                editor_df = df_to_edit[existing_cols].copy()

                edited_df = st.data_editor(
                    editor_df,
                    disabled=["id", "date", "athlete_name", "first_name", "last_name", "created_at"],
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "date": st.column_config.TextColumn("Data", disabled=True),
                        "time": st.column_config.TextColumn("Ora"),
                        "athlete_name": st.column_config.TextColumn("Atleta", disabled=True),
                        "exercise": st.column_config.TextColumn("Esercizio"),
                        "set_id": st.column_config.NumberColumn("Set ID"),
                        "row_type": st.column_config.SelectboxColumn("Tipo Riga", options=["Rep", "Average", "Maximum"]),
                        "rep_number": st.column_config.NumberColumn("Rep #", min_value=1, max_value=50, step=1),
                        "bar_weight": st.column_config.NumberColumn("Carico Bilanciere (kg)", step=0.5, format="%.1f kg"),
                        "total_weight": st.column_config.NumberColumn("Peso Totale con BW (kg)", step=0.5, format="%.1f kg"),
                        "mean_velocity": st.column_config.NumberColumn("Mean Vel (m/s)", step=0.01, format="%.2f m/s"),
                        "peak_velocity": st.column_config.NumberColumn("Peak Vel (m/s)", step=0.01, format="%.2f m/s"),
                        "mean_power": st.column_config.NumberColumn("Mean Power (W)", step=1.0, format="%.0f W"),
                        "peak_power": st.column_config.NumberColumn("Peak Power (W)", step=1.0, format="%.0f W"),
                        "height": st.column_config.NumberColumn("Height (m)", step=0.001, format="%.3f m"),
                        "dip": st.column_config.NumberColumn("Dip (m)", step=0.001, format="%.3f m"),
                        "notes": st.column_config.TextColumn("Note"),
                    },
                    use_container_width=True,
                    hide_index=True,
                    key="gymaware_editor_table",
                )

                btn_save_col, _ = st.columns([1.5, 2])
                with btn_save_col:
                    if st.button(f"💾 Salva Modifiche per {edit_ath} ({edit_date})", type="primary", use_container_width=True):
                        updated_cnt = utils.update_gymaware_rows(edited_df)
                        st.success(f"✅ Aggiornate con successo **{updated_cnt}** righe nel database SQLite per {edit_ath}!")
                        st.rerun()

        st.markdown("<hr style='border-color:#E2E8F0; margin:24px 0;'>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # RIPRISTINO ARCHIVIO INIZIALE
        # ----------------------------------------------------------------------
        st.markdown("##### 🔄 Ripristina Dati Iniziali")
        st.caption("Ricarica il file ufficiale di test <code>261109 - Rep Statistics Table.csv</code> ripristinando tutte le 3.121 misurazioni originali.")
        if st.button("Ripristina Archivio Originale (Reset Completo)", type="secondary", use_container_width=False):
            if os.path.exists(utils.GYMAWARE_SEED_CSV):
                df_seed = pd.read_csv(utils.GYMAWARE_SEED_CSV)
                cnt = utils.save_gymaware_from_df(df_seed, replace_all=True)
                st.success(f"Archivio ripristinato con successo ({cnt:,} righe caricate)!")
                st.rerun()
            else:
                st.error("File di seed non trovato su disco.")
