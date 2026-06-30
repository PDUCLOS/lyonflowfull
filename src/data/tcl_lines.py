"""Référentiel statique des 10 lignes majeures TCL Lyon (Juin 2026).

Attention : Il ne s'agit PAS d'un mock (données simulées). Ce sont des données
publiques fondamentales du réseau TCL lyonnais (comprenant les métros A/B/C/D,
les tramways T1/T2/T3/T6, et les lignes de bus majeures C3/C13). Toutes les
applications lyonnaises de mobilité se basent sur ces 10 lignes névralgiques.

Historiquement, cette liste était par erreur classée dans un répertoire de mock,
sous le nom de `TCL_LINES_PRO`. Cette erreur d'architecture a été rectifiée
vers ce module neutre `tcl_lines.py`.

Pour information, la base de données PostgreSQL maintient le référentiel complet
dans `referentiel.lieux_transports` (56 liaisons) et l'analyse de performance
dans `gold.mv_line_kpis_live` (155 lignes).
"""

from __future__ import annotations

from src.data.labels import MODE_COLORS

# Dictionnaire des 10 lignes emblématiques du réseau TCL Lyon
# Les 145 autres lignes secondaires sont disponibles dynamiquement via
# referentiel.lieux_transports.
TCL_LINES: list[dict] = [
    {"id": "M_A", "name": "Métro A", "mode": "metro", "color": MODE_COLORS["metro"], "icon": "🚇"},
    {"id": "M_B", "name": "Métro B", "mode": "metro", "color": "#0064B0", "icon": "🚇"},
    {"id": "M_C", "name": "Métro C", "mode": "metro", "color": "#FF6600", "icon": "🚇"},
    {"id": "M_D", "name": "Métro D", "mode": "metro", "color": "#00A88E", "icon": "🚇"},
    {"id": "T1", "name": "Tram T1", "mode": "tram", "color": MODE_COLORS["tram"], "icon": "🚊"},
    {"id": "T2", "name": "Tram T2", "mode": "tram", "color": "#A4D65E", "icon": "🚊"},
    {"id": "T3", "name": "Tram T3", "mode": "tram", "color": "#9B59B6", "icon": "🚊"},
    {"id": "T6", "name": "Tram T6", "mode": "tram", "color": "#E67E22", "icon": "🚊"},
    {"id": "C3", "name": "Bus C3", "mode": "bus", "color": MODE_COLORS["bus"], "icon": "🚌"},
    {"id": "C13", "name": "Bus C13", "mode": "bus", "color": "#1ABC9C", "icon": "🚌"},
]
