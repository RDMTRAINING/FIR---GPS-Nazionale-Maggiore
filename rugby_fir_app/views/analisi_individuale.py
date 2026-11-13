# Copyright 2026 Riccardo Di Maio / M0V3 S.r.l.
import streamlit as st
import pandas as pd
import config
if not hasattr(config, "render_navigation_cards"):
    import importlib
    importlib.reload(config)
from config import render_page_header, render_navigation_cards
import utils
import views.report_6weeks
import views.oval_match
import views.dossier_multi_export


def render_analisi_individuale(t: dict):
    render_page_header(
        "Analisi Individuale Atleta FIR",
        "Passaporto Unificato Atleta (GPS 21 Giorni, Carico & Benchmark) • Scheda Storica Carriera Oval (Caps, Minuti, Stagioni & Club) • Dossier Multi-Giocatore",
        "bi-person-bounding-box",
    )

    cards_individuale = [
        {
            "id": "gps_atleta",
            "title": "Analisi GPS Atleta",
            "desc": "Passaporto unificato giocatore, semaforo Vmax, densità e progressione carico 21gg",
            "icon": "bi-person-bounding-box",
        },
        {
            "id": "caps_minuti",
            "title": "Analisi Caps e Minuti Atleta",
            "desc": "Scheda storica carriera Oval, caps ufficiali, minutaggio per stagione e club",
            "icon": "bi-trophy-fill",
        },
        {
            "id": "dossier_multi",
            "title": "Dossier Multi-Giocatore (Export PDF)",
            "desc": "Export fascicolo PDF multi-pagina per la lista G.I.N. (GPS, Minuti Oval o Integrato Totale)",
            "icon": "bi-file-earmark-pdf-fill",
        },
    ]

    active_tab = render_navigation_cards("analisi_individuale", cards_individuale)

    if active_tab == "gps_atleta":
        views.report_6weeks._render_tab_singolo_atleta_3w(t)
    elif active_tab == "caps_minuti":
        oval_df = utils.get_oval_matches_df()
        views.oval_match._render_tab_scheda_atleta(oval_df)
    else:
        views.dossier_multi_export.render_dossier_multi_export(t)
