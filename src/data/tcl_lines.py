"""Référentiel statique des 10 lignes TCL Lyon (Sprint 8, 2026-06-12).

Ce n'est PAS un mock : ce sont des **données publiques du réseau TCL**
(métros A/B/C/D, trams T1/T2/T3/T6, bus C3/C13). Toutes les apps
lyonnaises (TCL, Citymapper, Google Maps) connaissent ces 10 lignes.

Avant Sprint 8, cette liste était dans un module `mock`, importée
comme `TCL_LINES_PRO`. Détournée vers la couche mock par erreur de
nomenclature. Maintenant, module neutre `tcl_lines.py`. La DB
contient `referentiel.lieux_transports` (56 liaisons) et
`gold.mv_line_kpis_live` (155 lignes) avec les vraies données
observées.
"""

from __future__ import annotations

from src.data.labels import MODE_COLORS

# 10 lignes emblématiques du réseau TCL Lyon
# (les 145 autres lignes sont dans referentiel.lieux_transports).
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
