"""Tests du générateur PDF (WeasyPrint avec fallback reportlab)."""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE))


def test_pdf_renderer_imports():
    """Le module src/reporting/pdf_renderer doit s'importer."""
    from src.reporting import pdf_renderer

    assert hasattr(pdf_renderer, "render_html_template")
    assert hasattr(pdf_renderer, "generate_pdf")
    assert callable(pdf_renderer.render_html_template)
    assert callable(pdf_renderer.generate_pdf)


def test_template_html_exists():
    """Le template HTML de base doit exister."""
    template_path = WORKSPACE / "src" / "reporting" / "templates" / "synthese_mensuelle.html"
    assert template_path.exists(), f"Template manquant : {template_path}"

    content = template_path.read_text(encoding="utf-8")
    # Doit contenir les balises de substitution
    assert "{{ title }}" in content
    assert "{{ date }}" in content
    assert "{{ content }}" in content
    # Doit être un HTML valide (au moins <html>, <body>, </html>)
    assert "<html" in content
    assert "</html>" in content
    assert "<body" in content
    assert "</body>" in content


def test_render_html_template_basic():
    """render_html_template doit retourner du HTML valide avec les sections fournies."""
    from src.reporting.pdf_renderer import render_html_template

    sections = {
        "title": "Test Rapport",
        "date": "2026-06-05",
        "kpis": [
            {"label": "Test KPI", "value": 42, "unit": "%", "delta_ytd": 1.5},
        ],
    }
    html = render_html_template(sections)

    assert isinstance(html, str)
    assert "Test Rapport" in html
    assert "Test KPI" in html
    assert "42" in html


def test_render_html_template_with_bottlenecks():
    """render_html_template doit gérer les bottlenecks."""
    from src.reporting.pdf_renderer import render_html_template

    sections = {
        "title": "Test",
        "bottlenecks": [
            {
                "rank": 1,
                "zone": "Rue Test",
                "lines_impacted": ["T1", "C3"],
                "voyageurs_jour": 50000,
                "gain_min": 5,
                "cout_M_euros": 1.5,
                "roi_mois": 12,
            },
        ],
    }
    html = render_html_template(sections)
    assert "Rue Test" in html
    assert "Top bottlenecks" in html


def test_generate_pdf_returns_bytes():
    """generate_pdf doit retourner des bytes (WeasyPrint ou fallback reportlab)."""
    from src.reporting.pdf_renderer import generate_pdf, render_html_template

    sections = {
        "title": "Test PDF",
        "kpis": [{"label": "Test", "value": 100, "unit": "%", "delta_ytd": 0}],
    }
    html = render_html_template(sections)

    try:
        pdf = generate_pdf(html)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 100, f"PDF trop petit ({len(pdf)} octets)"
        # Un PDF commence par %PDF
        assert pdf[:4] == b"%PDF", f"Pas un PDF valide (header: {pdf[:10]})"
    except RuntimeError as e:
        # Si ni WeasyPrint ni reportlab ne sont installés
        if "weasyprint" in str(e) or "reportlab" in str(e):
            import pytest

            pytest.skip(f"Librairie PDF non installée : {e}")
        raise
