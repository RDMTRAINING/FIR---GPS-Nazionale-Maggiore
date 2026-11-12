import os
import json
import re
import plotly.graph_objects as go

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
TIMELINES_PATH = os.path.join(DATA_DIR, "session_timelines.json")

CANONICAL_BLOCK_NAMES = [
    "Attivazione",
    "Drill",
    "Collettivo",
    "Contatto",
    "Reparto",
    "Pausa",
    "Clarity",
]

CANONICAL_COLORS = {
    "attivazione": "#FFE600",   # Giallo acceso (come timeline FIR)
    "pausa": "#D0F0FD",         # Celeste chiaro ghiaccio
    "drill": "#FFA500",         # Arancione
    "clarity": "#3CD070",       # Verde brillante
    "collettivo": "#00B0FF",    # Azzurro vivido
    "contatto": "#EF4444",      # Rosso
    "reparto": "#E9D5FF",       # Lilla / Lavanda
}

EXTENDED_PALETTE = [
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316",
    "#6366F1", "#84CC16", "#E11D48", "#06B6D4",
    "#FBBF24", "#A855F7", "#10B981", "#3B82F6",
]

# Baseline per la seduta '261111 volume' tratta fedelmente dall'immagine caricata
DEFAULT_261111_BLOCKS = [
    {"name": "Attivazione", "duration": 15.0},
    {"name": "Pausa", "duration": 3.0},
    {"name": "Drill", "duration": 11.5},
    {"name": "Pausa", "duration": 3.5},
    {"name": "Clarity 1", "duration": 13.0},
    {"name": "Pausa", "duration": 1.5},
    {"name": "Clarity 2", "duration": 10.0},
    {"name": "Pausa", "duration": 1.5},
    {"name": "Collettivo 1", "duration": 15.0},
    {"name": "Pausa", "duration": 3.0},
    {"name": "Collettivo 2", "duration": 2.0},
    {"name": "Pausa", "duration": 3.0},
    {"name": "Reparto", "duration": 33.0},
]


def get_block_color(block_name: str) -> str:
    """
    Restituisce un colore esadecimale consistente per ogni blocco.
    Nomi uguali hanno SEMPRE colori identici.
    I nomi canonici (attivazione, drill, collettivo, contatto, reparto, pausa, clarity)
    hanno i colori coordinati alla timeline ufficiale FIR.
    """
    s = str(block_name or "").strip().lower()
    if not s:
        return "#CBD5E1"

    # Match su radici note
    if "attivaz" in s or "warm" in s:
        return CANONICAL_COLORS["attivazione"]
    if "pausa" in s or "rest" in s or "break" in s:
        return CANONICAL_COLORS["pausa"]
    if "drill" in s:
        return CANONICAL_COLORS["drill"]
    if "clarit" in s:
        # Se '2', variante leggermente più scura come nell'immagine, altrimenti colore standard
        return "#2EB85C" if "2" in s else CANONICAL_COLORS["clarity"]
    if "collettiv" in s:
        return "#0284C7" if "2" in s else CANONICAL_COLORS["collettivo"]
    if "contatt" in s or "contact" in s:
        return CANONICAL_COLORS["contatto"]
    if "repart" in s or "unit" in s:
        return CANONICAL_COLORS["reparto"]

    # Voci personalizzate aggiunte dall'utente: hashing deterministico per colore costante
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return EXTENDED_PALETTE[h % len(EXTENDED_PALETTE)]


def load_all_timelines() -> dict:
    """Carica tutte le timeline salvate per ciascuna sessione."""
    if os.path.exists(TIMELINES_PATH):
        try:
            with open(TIMELINES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def save_all_timelines(timelines: dict) -> bool:
    """Salva tutte le timeline nel file JSON su disco."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(TIMELINES_PATH, "w", encoding="utf-8") as f:
            json.dump(timelines, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_session_timeline(session_name: str) -> list:
    """
    Restituisce la lista ordinata dei blocchi [{'name': ..., 'duration': ...}] per la seduta.
    Se la seduta è '261111 volume' e non è ancora salvata, inizializza con i blocchi reali FIR.
    """
    s_key = str(session_name or "").strip()
    timelines = load_all_timelines()

    if s_key in timelines and isinstance(timelines[s_key], list) and timelines[s_key]:
        return timelines[s_key]

    # Pre-popolamento automatico per la seduta volume del 11 nov (come da immagine)
    if "261111" in s_key or "volume" in s_key.lower():
        timelines[s_key] = [dict(b) for b in DEFAULT_261111_BLOCKS]
        save_all_timelines(timelines)
        return timelines[s_key]

    return []


def save_session_timeline(session_name: str, blocks: list) -> bool:
    """Salva la timeline per una specifica sessione."""
    s_key = str(session_name or "").strip()
    if not s_key:
        return False
    timelines = load_all_timelines()
    clean_blocks = []
    for b in blocks:
        name = str(b.get("name", "")).strip()
        try:
            dur = round(float(b.get("duration", 0)), 1)
        except (ValueError, TypeError):
            dur = 0.0
        if name and dur > 0:
            clean_blocks.append({"name": name, "duration": dur})
    timelines[s_key] = clean_blocks
    return save_all_timelines(timelines)


def build_timeline_plotly_fig(blocks: list, width: int = 1000, height: int = 135) -> go.Figure:
    """
    Costruisce la figura Plotly della timeline dell'allenamento
    graficamente fedele all'immagine:
    - Etichetta verticale 'MINUTI'
    - Segmenti orizzontali colorati proporzionali alla durata
    - Valore della durata centrato all'interno di ciascun blocco
    - Legenda orizzontale in basso con quadratini colorati e nomi
    """
    fig = go.Figure()
    if not blocks:
        fig.add_annotation(
            text="<i>Nessun blocco configurato. Utilizza la tabella in fondo alla pagina per aggiungere la timeline.</i>",
            showarrow=False,
            font=dict(size=12, color="#64748B"),
        )
        fig.update_layout(
            height=70,
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        return fig

    total_dur = sum(float(b.get("duration", 0)) for b in blocks)
    if total_dur <= 0:
        total_dur = 1.0

    seen_legend = set()

    for idx, b in enumerate(blocks):
        b_name = str(b.get("name", "")).strip()
        dur = float(b.get("duration", 0))
        c = get_block_color(b_name)
        dur_str = f"{dur:g}".replace(".", ",")

        # Dimensione testo adattiva in base alla durata del blocco
        pct_w = dur / total_dur
        if pct_w >= 0.08:
            txt_size = 12
        elif pct_w >= 0.04:
            txt_size = 10
        elif pct_w >= 0.02:
            txt_size = 8.5
        else:
            txt_size = 7.5

        # Mostra in legenda ogni singolo blocco (o raggruppamento per nome pulito)
        leg_name = b_name
        show_in_leg = True

        fig.add_trace(go.Bar(
            y=["MINUTI"],
            x=[dur],
            name=leg_name,
            orientation="h",
            marker=dict(
                color=c,
                line=dict(color="#0F172A", width=0.8),
            ),
            text=dur_str,
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(
                family="Arial, Helvetica, sans-serif",
                size=txt_size,
                color="#000000",
                weight="bold",
            ),
            hoverinfo="text",
            hovertext=f"<b>{b_name}</b><br>Durata: {dur_str} min ({(dur / total_dur) * 100:.1f}%)",
            showlegend=show_in_leg,
            legendgroup=b_name,
        ))

    fig.update_layout(
        barmode="stack",
        height=height,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        margin=dict(l=75, r=20, t=10, b=45),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, total_dur],
            fixedrange=True,
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            tickfont=dict(
                family="Arial, Helvetica, sans-serif",
                size=13,
                color="#000000",
                weight="bold",
            ),
            fixedrange=True,
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.30,
            xanchor="center",
            x=0.5,
            font=dict(
                family="Arial, Helvetica, sans-serif",
                size=10,
                color="#0F172A",
                weight="bold",
            ),
            itemwidth=30,
            traceorder="normal",
        ),
        bargap=0.0,
    )
    return fig
