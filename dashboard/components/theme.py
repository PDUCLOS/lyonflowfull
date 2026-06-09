"""Thème visuel — injection CSS selon le persona.

Applique les couleurs primaires du persona actif au dashboard Streamlit.
Gère aussi le mode dark, les fonts, les espacements.
"""

from __future__ import annotations

import streamlit as st

from dashboard.components.colors import COLORS
from src.persona.manager import PersonaManager


def inject_theme() -> None:
    """Injecte le CSS personnalisé selon le persona courant.

    À appeler après st.set_page_config() dans Accueil.py et dans chaque page.
    """
    pm = PersonaManager()
    color_primary = pm.color_primary
    color_accent = pm.config.get("color_accent", color_primary)
    density = pm.theme.get("density", "normal")

    padding = {"compact": "0.4rem", "normal": "0.8rem", "dense": "0.2rem"}.get(density, "0.8rem")

    bg_card = COLORS["bg_card"]
    bg_card_alt = COLORS["bg_card_alt"]
    border_card = COLORS["border_card"]
    text_primary = COLORS["text_primary"]
    text_secondary = COLORS["text_secondary"]
    text_muted = COLORS["text_muted"]

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    @keyframes fadeInUp {{
        from {{ opacity: 0; transform: translateY(15px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}

    :root {{
        --primary: {color_primary};
        --accent: {color_accent};
        --bg-card: {bg_card};
        --bg-card-alt: {bg_card_alt};
        --border-card: {border_card};
        --text-primary: {text_primary};
        --text-secondary: {text_secondary};
        --text-muted: {text_muted};
        --status-ok: {COLORS["status_ok"]};
        --status-warning: {COLORS["status_warning"]};
        --status-critical: {COLORS["status_critical"]};
        --status-info: {COLORS["status_info"]};
        --bg-card-deep: {COLORS["bg_card_deep"]};
        --persona-elu: {COLORS["persona_elu"]};
        --persona-elu-accent: {COLORS["persona_elu_accent"]};
        --persona-usager: {COLORS["persona_usager"]};
        --persona-usager-accent: {COLORS["persona_usager_accent"]};
        --persona-pro-tcl: {COLORS["persona_pro_tcl"]};
        --persona-pro-tcl-accent: {COLORS["persona_pro_tcl_accent"]};
        --chart-purple: {COLORS["chart_purple"]};
        --chart-indigo: {COLORS["chart_indigo"]};
        --chart-yellow: {COLORS["chart_yellow"]};
        --chart-green-light: {COLORS["chart_green_light"]};
        --chart-red-deep: {COLORS["chart_red_deep"]};
        --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
        --shadow-md: 0 4px 12px rgba(0,0,0,0.35);
        --shadow-lg: 0 8px 24px rgba(0,0,0,0.45);
        --radius-sm: 6px;
        --radius-md: 10px;
        --radius-lg: 14px;
        --transition: 180ms cubic-bezier(0.4, 0, 0.2, 1);
    }}

    /* Global font polish */
    html, body, [data-testid="stAppViewContainer"] {{
        font-family: 'Inter', sans-serif !important;
        font-feature-settings: "cv11", "ss01", "ss03";
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}

    /* Boutons primaires */
    .stButton > button {{
        background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
        color: white;
        border: none;
        border-radius: var(--radius-sm);
        padding: {padding} 1.1rem;
        font-weight: 600;
        letter-spacing: 0.2px;
        box-shadow: var(--shadow-sm);
        transition: transform var(--transition), box-shadow var(--transition), filter var(--transition);
    }}
    .stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: var(--shadow-md);
        filter: brightness(1.08);
    }}
    .stButton > button:active {{
        transform: translateY(0);
        filter: brightness(0.95);
    }}
    .stButton > button:disabled {{
        background: #2A2D34;
        color: #666;
        box-shadow: none;
    }}

    /* Headers */
    h1 {{
        background: linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    h2 {{
        color: var(--primary);
        opacity: 0.92;
        font-weight: 600;
    }}
    h3 {{
        color: var(--accent);
        font-weight: 600;
    }}

    /* Sidebar */
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0E1117 0%, #14171D 100%);
        border-right: 1px solid var(--border-card);
    }}

    /* Metrics */
    [data-testid="stMetric"] {{
        background: var(--bg-card);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border-card);
        border-radius: var(--radius-md);
        padding: 0.9rem 1rem;
        box-shadow: var(--shadow-sm);
        transition: transform var(--transition), border-color var(--transition), box-shadow var(--transition);
        animation: fadeInUp 0.4s ease-out forwards;
    }}
    [data-testid="stMetric"]:hover {{
        transform: translateY(-2px);
        border-color: var(--primary);
        box-shadow: var(--shadow-md);
    }}
    [data-testid="stMetricValue"] {{
        color: var(--primary);
        font-size: 1.85rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    [data-testid="stMetricLabel"] {{
        color: var(--text-secondary);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}

    /* Cards */
    .lyonflow-card {{
        background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-card-alt) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border-card);
        border-left: 4px solid var(--primary);
        border-radius: var(--radius-md);
        padding: 1rem 1.1rem;
        margin: 0.5rem 0;
        box-shadow: var(--shadow-sm);
        transition: transform var(--transition), box-shadow var(--transition);
        animation: fadeInUp 0.5s ease-out forwards;
    }}
    .lyonflow-card:hover {{
        transform: translateY(-1px);
        box-shadow: var(--shadow-md);
    }}

    .lyonflow-card-flat {{
        background: var(--bg-card);
        border: 1px solid var(--border-card);
        border-radius: var(--radius-md);
        padding: 0.9rem 1rem;
    }}

    /* KPI tiles (ronds chiffres saillants) */
    .lyonflow-kpi {{
        background: linear-gradient(135deg, var(--bg-card) 0%, var(--bg-card-alt) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border-card);
        border-radius: var(--radius-lg);
        padding: 1.1rem;
        text-align: center;
        height: 170px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: var(--shadow-sm);
        position: relative;
        overflow: hidden;
        transition: transform var(--transition), box-shadow var(--transition);
        animation: fadeInUp 0.6s ease-out forwards;
    }}
    .lyonflow-kpi::before {{
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--primary), var(--accent));
    }}
    .lyonflow-kpi:hover {{
        transform: translateY(-2px);
        box-shadow: var(--shadow-lg);
    }}
    .lyonflow-kpi-label {{
        font-size: 0.72rem;
        opacity: 0.7;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        color: var(--text-secondary);
    }}
    .lyonflow-kpi-value {{
        font-size: 2.3rem;
        font-weight: 700;
        line-height: 1;
        color: var(--primary);
        letter-spacing: -1px;
    }}
    .lyonflow-kpi-unit {{
        font-size: 1rem;
        opacity: 0.55;
        font-weight: 500;
        margin-left: 2px;
    }}
    .lyonflow-kpi-delta {{
        font-size: 0.85rem;
        font-weight: 600;
    }}
    .lyonflow-kpi-target {{
        font-size: 0.7rem;
        opacity: 0.55;
        margin-top: 2px;
    }}

    /* Badges */
    .lyonflow-badge {{
        display: inline-block;
        background: linear-gradient(135deg, var(--primary), var(--accent));
        color: white;
        padding: 3px 11px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.3px;
        box-shadow: var(--shadow-sm);
    }}
    .lyonflow-badge-ok      {{ background: var(--status-ok); }}
    .lyonflow-badge-warning {{ background: var(--status-warning); }}
    .lyonflow-badge-critical{{ background: var(--status-critical); }}
    .lyonflow-badge-info    {{ background: var(--status-info); }}

    /* Tabs */
    [data-testid="stTabs"] button[role="tab"] {{
        font-weight: 500;
        transition: color var(--transition);
    }}
    [data-testid="stTabs"] button[aria-selected="true"] {{
        color: var(--primary) !important;
        border-bottom-color: var(--primary) !important;
    }}

    /* Expander */
    [data-testid="stExpander"] {{
        border: 1px solid var(--border-card);
        border-radius: var(--radius-md);
        background: var(--bg-card);
    }}

    /* Dataframes */
    [data-testid="stDataFrame"] {{
        border-radius: var(--radius-md);
        overflow: hidden;
        box-shadow: var(--shadow-sm);
    }}

    /* Scrollbar */
    ::-webkit-scrollbar {{
        width: 10px;
        height: 10px;
    }}
    ::-webkit-scrollbar-track {{
        background: transparent;
    }}
    ::-webkit-scrollbar-thumb {{
        background: var(--border-card);
        border-radius: 999px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
        background: var(--primary);
    }}

    /* Hide Streamlit chrome */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    [data-testid="stSidebarNav"] {{display: none !important;}}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
