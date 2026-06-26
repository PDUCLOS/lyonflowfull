"""Tests unitaires — dashboard/components/plotly_theme.py Axe B).

Couvre :
* LYF_TEMPLATE : thème Plotly cohérent avec le dark mode du dashboard
  (Inter, text_primary, paper transparent, colorway 6 couleurs).
* apply_lyf_theme : in-place + retourne le Figure (pour chaînage).
"""

from __future__ import annotations

import plotly.graph_objects as go

from dashboard.components.colors import COLORS
from dashboard.components.plotly_theme import LYF_TEMPLATE, apply_lyf_theme


class TestLYFTemplate:
    """Le template Plotly unifié a les bonnes propriétés."""

    def test_template_existe(self) -> None:
        """LYF_TEMPLATE est un go.layout.Template valide."""
        assert isinstance(LYF_TEMPLATE, go.layout.Template)
        assert LYF_TEMPLATE.layout is not None

    def test_font_aligne_sur_theme_css(self) -> None:
        """Font = Inter, color = text_primary."""
        assert "Inter" in LYF_TEMPLATE.layout.font.family
        assert LYF_TEMPLATE.layout.font.color == COLORS["text_primary"]

    def test_paper_bgcolor_transparent(self) -> None:
        """Paper transparent pour s'intégrer aux cards glassmorphism Streamlit."""
        assert LYF_TEMPLATE.layout.paper_bgcolor == "rgba(0,0,0,0)"
        assert LYF_TEMPLATE.layout.plot_bgcolor == "rgba(0,0,0,0)"

    def test_colorway_a_au_moins_6_couleurs(self) -> None:
        """6+ couleurs dans le colorway (cohérence inter-widgets)."""
        assert len(LYF_TEMPLATE.layout.colorway) >= 6
        # Toutes les couleurs doivent être des hex ou rgba valides
        for color in LYF_TEMPLATE.layout.colorway:
            assert isinstance(color, str)
            assert color.startswith("#") or color.startswith("rgba(")

    def test_axes_adaptes_dark_mode(self) -> None:
        """Gridlines + labels utilisent text_secondary (lisible sur dark)."""
        assert LYF_TEMPLATE.layout.xaxis.color == COLORS["text_secondary"]
        assert LYF_TEMPLATE.layout.yaxis.color == COLORS["text_secondary"]
        # Gridlines subtiles
        assert "148" in LYF_TEMPLATE.layout.xaxis.gridcolor  # rgba(148, 163, 184, 0.12)

    def test_hoverlabel_dark_mode(self) -> None:
        """Tooltip dark mode cohérent avec le fond de card."""
        assert LYF_TEMPLATE.layout.hoverlabel.bgcolor == COLORS["bg_card_deep"]
        assert LYF_TEMPLATE.layout.hoverlabel.font.color == COLORS["text_primary"]


class TestApplyLyfTheme:
    """apply_lyf_theme applique le template au Figure."""

    def test_apply_in_place(self) -> None:
        """Le Figure est modifié in-place (même objet retourné)."""
        fig = go.Figure(data=[go.Bar(x=["a"], y=[1])])
        result = apply_lyf_theme(fig)
        assert result is fig
        # Le template est appliqué
        assert fig.layout.template is not None

    def test_apply_sur_figure_vide(self) -> None:
        """Fonctionne sur un Figure vide (pas d'erreur)."""
        fig = go.Figure()
        apply_lyf_theme(fig)
        assert fig.layout.template is not None

    def test_apply_preserve_data(self) -> None:
        """Les traces (data) sont préservées après application du thème."""
        fig = go.Figure(data=[go.Bar(x=["a", "b"], y=[1, 2])])
        apply_lyf_theme(fig)
        # Vérifier que les data sont préservées
        assert len(fig.data) == 1
        assert fig.data[0].x == ("a", "b")
        assert fig.data[0].y == (1, 2)

    def test_apply_change_font(self) -> None:
        """Le theme override la font par défaut."""
        fig = go.Figure(data=[go.Bar(x=["a"], y=[1])])
        apply_lyf_theme(fig)
        # Le template est appliqué (font vient du template, pas du layout direct)
        assert fig.layout.template.layout.font.family == "Inter, sans-serif"
