"""Reporting package — génération de rapports PDF/HTML."""

from src.reporting.pdf_renderer import (
    render_html_template,
    generate_pdf,
    _html_to_text,  # noqa: F401
)

__all__ = ["render_html_template", "generate_pdf"]
