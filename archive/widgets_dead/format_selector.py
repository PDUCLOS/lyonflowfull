"""Widget — Sélecteur de format d'export."""

from __future__ import annotations

import streamlit as st


def render_format_selector() -> str:
    """Affiche un selecteur de format d'export.

    Returns:
        Format sélectionné : 'excel' | 'pdf' | 'saeiv' | 'hastus' | 'api'
    """
    format_map = {
        "📊 Excel (.xlsx)": "excel",
        "📄 PDF": "pdf",
        "🔧 SAEIV": "saeiv",
        "⏰ Hastus": "hastus",
        "📡 API JSON": "api",
    }
    selected = st.selectbox(
        "Format d'export",
        list(format_map.keys()),
        key="export_format_selector",
    )
    return format_map[selected]
