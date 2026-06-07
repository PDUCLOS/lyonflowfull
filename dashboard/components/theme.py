"""Thème visuel — injection CSS selon le persona.

Applique les couleurs primaires du persona actif au dashboard Streamlit.
Gère aussi le mode dark, les fonts, les espacements.
"""

from __future__ import annotations

import streamlit as st

from src.persona.manager import PersonaManager


def inject_theme() -> None:
    """Injecte le CSS personnalisé selon le persona courant.

    À appeler après st.set_page_config() dans Accueil.py et dans chaque page.
    """
    pm = PersonaManager()
    color_primary = pm.color_primary
    color_accent = pm.config.get("color_accent", color_primary)
    density = pm.theme.get("density", "normal")

    # Espacement selon la densité
    padding = {"compact": "0.4rem", "normal": "0.8rem", "dense": "0.2rem"}.get(density, "0.8rem")

    css = f"""
    <style>
    :root {{
        --primary: {color_primary};
        --accent: {color_accent};
    }}

    /* Boutons primaires */
    .stButton > button {{
        background-color: var(--primary);
        color: white;
        border: none;
        border-radius: 6px;
        padding: {padding} 1rem;
        font-weight: 500;
    }}
    .stButton > button:hover {{
        background-color: var(--accent);
    }}
    .stButton > button:disabled {{
        background-color: #444;
        color: #888;
    }}

    /* Headers */
    h1 {{ color: var(--primary); }}
    h2 {{ color: var(--primary); opacity: 0.85; }}
    h3 {{ color: var(--accent); }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background-color: #0E1117;
        border-right: 1px solid #222;
    }}

    /* Metrics */
    [data-testid="stMetricValue"] {{
        color: var(--primary);
        font-size: 1.8rem;
    }}

    /* Cards */
    .lyonflow-card {{
        background: #1A1D24;
        border: 1px solid #2A2D34;
        border-left: 4px solid var(--primary);
        border-radius: 8px;
        padding: 1rem;
        margin: 0.5rem 0;
    }}

    /* Badges */
    .lyonflow-badge {{
        display: inline-block;
        background: var(--primary);
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }}

    /* Hide Streamlit default menu in production */
    #MainMenu {visibility: hidden;}  # noqa: F821
    footer {visibility: hidden;}  # noqa: F821
    /* Hide native sidebar nav — on a notre propre nav custom par persona */
    [data-testid="stSidebarNav"] {display: none !important;}  # noqa: F821
    """
    st.markdown(css, unsafe_allow_html=True)
