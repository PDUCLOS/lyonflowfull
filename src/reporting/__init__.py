"""Reporting package — génération de rapports PDF/HTML."""

from src.reporting.pdf_renderer import (
    _html_to_text,  # noqa: F401
    generate_pdf,
    render_html_template,
)

__all__ = ["generate_pdf", "render_html_template"]
