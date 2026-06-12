"""Widget — Bouton d'export générique."""

from __future__ import annotations

import streamlit as st


def render_export_button(label: str = "📤 Exporter", key_suffix: str = "default", export_format: str = "excel") -> None:
    """Affiche un bouton d'export générique.

    Args:
        label: texte du bouton.
        key_suffix: suffixe unique pour la clé.
        export_format: format (excel, pdf, csv, json).
    """
    if st.button(label, key=f"export_btn_{key_suffix}"):
        st.info(f"🚧 Export {export_format.upper()} — à brancher sur les données réelles.")


def render_excel_export_button(df, filename: str = "export.xlsx", key_suffix: str = "default") -> None:
    """Bouton d'export Excel à partir d'un DataFrame.

    Args:
        df: pandas DataFrame à exporter.
        filename: nom du fichier.
        key_suffix: suffixe pour la clé.
    """
    import io

    # Fallback : export CSV si openpyxl pas dispo
    try:
        import pandas  # noqa: F401  # vérifie dispo

        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        st.download_button(
            label="📥 Télécharger Excel",
            data=buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_excel_{key_suffix}",
        )
    except (ImportError, ValueError):
        # openpyxl missing → CSV fallback
        if hasattr(df, "to_csv"):
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Télécharger CSV (fallback)",
                data=csv,
                file_name=filename.replace(".xlsx", ".csv"),
                mime="text/csv",
                key=f"dl_csv_{key_suffix}",
            )
        else:
            st.info("🚧 Export non disponible — pandas manquant.")
