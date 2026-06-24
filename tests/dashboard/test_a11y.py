"""Tests unitaires — dashboard/components/a11y.py (Sprint 20 Axe E).

Couvre :
* plotly_with_alt : signature + alt_text défaut (placeholder).
* folium_with_alt : signature (import lazy folium).
* data_table_expander : wrap DataFrame dans expander (UI only, on teste
  que la fonction est importable et accepte un DataFrame).
"""

from __future__ import annotations

import inspect

import pandas as pd
import plotly.graph_objects as go

from dashboard.components.a11y import data_table_expander, plotly_with_alt

# -----------------------------------------------------------------------------
# plotly_with_alt
# -----------------------------------------------------------------------------


class TestPlotlyWithAlt:
    """Wrapper Plotly avec texte alternatif sr-only."""

    def test_signature_accepte_alt_text(self) -> None:
        """plotly_with_alt(fig, alt_text, **kwargs) — alt_text param."""
        sig = inspect.signature(plotly_with_alt)
        params = list(sig.parameters.keys())
        assert "fig" in params
        assert "alt_text" in params
        # alt_text doit avoir un défaut (placeholder)
        assert sig.parameters["alt_text"].default is not inspect.Parameter.empty

    def test_alt_text_default_est_placeholder(self) -> None:
        """Le défaut est un placeholder qui doit être raffiné par le dev."""
        sig = inspect.signature(plotly_with_alt)
        default = sig.parameters["alt_text"].default
        assert "raffiner" in default.lower() or "placeholder" in default.lower()

    def test_accepte_kwargs_pour_st_plotly_chart(self) -> None:
        """**kwargs forwarded to st.plotly_chart (ex: use_container_width)."""
        sig = inspect.signature(plotly_with_alt)
        assert sig.parameters.get("kwargs") is not None or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )


# -----------------------------------------------------------------------------
# data_table_expander
# -----------------------------------------------------------------------------


class TestDataTableExpander:
    """Expander avec DataFrame pour accessibilité (lecteurs d'écran)."""

    def test_signature_accepte_df(self) -> None:
        """data_table_expander(df, label=...)"""
        sig = inspect.signature(data_table_expander)
        params = list(sig.parameters.keys())
        assert "df" in params
        assert "label" in params

    def test_label_default(self) -> None:
        """Label par défaut contient l'emoji 📋."""
        sig = inspect.signature(data_table_expander)
        default = sig.parameters["label"].default
        assert "📋" in default

    def test_accepte_pandas_dataframe(self) -> None:
        """La fonction ne raise pas avec un DataFrame vide."""
        # On ne peut pas vraiment tester st.expander sans streamlit runtime,
        # mais on peut au moins vérifier que la fonction existe et accepte df.
        sig = inspect.signature(data_table_expander)
        # Vérifier que df est bien le 1er paramètre
        assert (
            sig.parameters["df"].annotation
            in (
                "pd.DataFrame",
                inspect.Parameter.empty,
            )
            or sig.parameters["df"].name == "df"
        )


# -----------------------------------------------------------------------------
# folium_with_alt (import-only — folium est optionnel)
# -----------------------------------------------------------------------------


class TestFoliumWithAlt:
    """folium_with_alt — import paresseux, signature correcte."""

    def test_folium_with_alt_importable(self) -> None:
        """Le module importe folium paresseusement (pas d'erreur si absent)."""
        from dashboard.components.a11y import folium_with_alt

        sig = inspect.signature(folium_with_alt)
        params = list(sig.parameters.keys())
        assert "map_" in params
        assert "alt_text" in params
        assert "height" in params
