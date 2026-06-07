"""Générateur PDF LyonFlowFull — pour rapports Élu (CM).

Utilise WeasyPrint pour HTML→PDF. Fallback reportlab si WeasyPrint
n'est pas installable (libpango manquante sur certains systèmes).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# Template HTML de base
# -----------------------------------------------------------------------------
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    """Charge un template HTML depuis le dossier templates."""
    path = TEMPLATES_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _default_template()


def _default_template() -> str:
    """Template par défaut si le fichier n'existe pas."""
    return """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <style>
        @page { size: A4; margin: 2cm; }
        body { font-family: 'Helvetica', 'Arial', sans-serif; color: #222; }
        .header { border-bottom: 3px solid #3F51B5; padding-bottom: 1rem; margin-bottom: 1.5rem; }
        .header h1 { color: #3F51B5; margin: 0; }
        .header .meta { color: #666; font-size: 0.85rem; margin-top: 0.3rem; }
        .kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.8rem; margin: 1rem 0; }
        .kpi-card { background: #F5F5F5; border-left: 4px solid #3F51B5; padding: 0.8rem; border-radius: 4px; }
        .kpi-label { font-size: 0.75rem; color: #666; }
        .kpi-value { font-size: 1.8rem; font-weight: 700; color: #3F51B5; }
        .kpi-delta { font-size: 0.85rem; color: #4CAF50; }
        .section { margin: 1.5rem 0; page-break-inside: avoid; }
        .section h2 { color: #3F51B5; border-bottom: 1px solid #DDD; padding-bottom: 0.3rem; }
        .bottleneck-row { display: flex; justify-content: space-between; padding: 0.5rem; border-bottom: 1px solid #EEE; }
        .footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #DDD; font-size: 0.7rem; color: #999; text-align: center; }
    </style>
</head>
<body>
    <div class="header">
        <h1>{{ title }}</h1>
        <div class="meta">LyonFlowFull · Métropole de Lyon · {{ date }}</div>
    </div>
    {{ content }}
    <div class="footer">
        Document généré par LyonFlowFull · Données open data Grand Lyon · {{ date }}
    </div>
</body>
</html>
"""


def render_html_template(sections: dict[str, Any], template_name: str = "synthese_mensuelle.html") -> str:
    """Génère le HTML d'un rapport.

    Args:
        sections: dict avec clés 'title', 'kpis', 'bottlenecks', 'decisions', etc.
        template_name: nom du fichier template dans templates/

    Returns:
        HTML complet (str).
    """
    html = _load_template(template_name)

    # Remplacements simples (pas de Jinja pour éviter la dépendance)
    title = sections.get("title", "Rapport LyonFlowFull")
    date = sections.get("date", "2026-06-05")

    html = html.replace("{{ title }}", title)
    html = html.replace("{{ date }}", date)

    # Bloc KPIs
    kpis = sections.get("kpis", [])
    kpis_html = '<div class="kpi-grid">'
    for k in kpis:
        delta = k.get("delta_ytd", 0)
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        delta_color = "#4CAF50" if delta > 0 else "#E74C3C"
        kpis_html += f"""
        <div class="kpi-card">
            <div class="kpi-label">{k.get("label", "—")}</div>
            <div class="kpi-value">{k.get("value", "—")}{k.get("unit", "")}</div>
            <div class="kpi-delta" style="color: {delta_color};">{delta_str} vs YTD</div>
        </div>
        """
    kpis_html += "</div>"

    # Sections supplémentaires
    extra_content = ""

    bottlenecks = sections.get("bottlenecks", [])
    if bottlenecks:
        extra_content += '<div class="section"><h2>🎯 Top bottlenecks prioritaires</h2>'
        for b in bottlenecks[:5]:
            extra_content += f"""
            <div class="bottleneck-row">
                <div>
                    <b>#{b.get("rank", "—")} {b.get("zone", "—")}</b><br>
                    <span style="font-size: 0.85rem; color: #666;">
                        {len(b.get("lines_impacted", []))} lignes · {b.get("voyageurs_jour", 0):,} voy/j
                    </span>
                </div>
                <div style="text-align: right;">
                    <b>{b.get("gain_min", 0)} min gagnées</b> · {b.get("cout_M_euros", 0)} M€<br>
                    <span style="font-size: 0.85rem; color: #4CAF50;">ROI {b.get("roi_mois", 0)} mois</span>
                </div>
            </div>
            """
        extra_content += "</div>"

    decisions = sections.get("decisions", [])
    if decisions:
        extra_content += '<div class="section"><h2>🎯 Décisions à arbitrer ce trimestre</h2><ol>'
        for d in decisions:
            extra_content += f"<li>{d}</li>"
        extra_content += "</ol></div>"

    # Remplacer {{ content }} une seule fois avec tout le contenu
    full_content = kpis_html + extra_content
    html = html.replace("{{ content }}", full_content)

    return html


def generate_pdf(html: str) -> bytes:
    """Génère un PDF à partir de HTML.

    Args:
        html: contenu HTML complet.

    Returns:
        Bytes du PDF généré.

    Raises:
        RuntimeError: si ni WeasyPrint ni reportlab ne sont disponibles.
    """
    # Essai 1 : WeasyPrint
    try:
        from weasyprint import HTML  # type: ignore

        pdf_bytes = HTML(string=html).write_pdf()
        if pdf_bytes and len(pdf_bytes) > 100:
            return pdf_bytes
    except (ImportError, OSError):
        pass

    # Essai 2 : reportlab (fallback)
    try:
        from io import BytesIO

        from reportlab.lib.pagesizes import A4  # type: ignore
        from reportlab.pdfgen import canvas  # type: ignore

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, "LyonFlowFull Report")
        c.setFont("Helvetica", 10)
        c.drawString(50, 780, "Generated via reportlab fallback (WeasyPrint unavailable)")
        # Ajouter une partie du texte HTML brut (simplifié)
        plain_text = _html_to_text(html)
        y = 760
        for line in plain_text.split("\n")[:50]:
            if y < 50:
                c.showPage()
                y = 800
            c.drawString(50, y, line[:100])
            y -= 14
        c.save()
        return buffer.getvalue()
    except ImportError:
        pass

    raise RuntimeError(
        "Aucune librairie PDF disponible. Installer weasyprint (recommandé) "
        "ou reportlab (fallback) : `pip install weasyprint reportlab`"
    )


def _html_to_text(html: str) -> str:
    """Convertit HTML en texte brut simple (pour fallback reportlab)."""
    import re

    # Supprimer les balises
    text = re.sub(r"<[^>]+>", " ", html)
    # Supprimer les espaces multiples
    text = re.sub(r"\s+", " ", text)
    return text.strip()
