"""Fonds de carte communs à toutes les cartes du dashboard.

Fournisseurs sans clé d'API ni inscription. CARTO exige une clé depuis le
23/09/2026 : ses tuiles affichaient « API KEY REQUIRED » sur toutes les cartes.

- Leaflet / folium (tuiles raster) : OpenStreetMap standard.
- pydeck (tuiles vectorielles MapLibre) : OpenFreeMap, style Positron.
"""

from __future__ import annotations

FOLIUM_TILES = "OpenStreetMap"
PYDECK_MAP_STYLE = "https://tiles.openfreemap.org/styles/positron"
