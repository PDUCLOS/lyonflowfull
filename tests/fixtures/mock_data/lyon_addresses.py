"""Adresses lyonnaises avec coordonnées GPS (mock, pas de geocoder).

Sprint 8 — Liste de référence partagée entre :
- search_bar.py (auto-complétion cliquable)
- itinerary.py (résolution texte → coords)

Format: list[dict] avec clés name, lon, lat, type (lieu public / gare /
arrêt métro / parc / quartier).

Note : Sprint suivant remplacera par Nominatim (OpenStreetMap) pour
un vrai geocoder adresse libre.
"""

from __future__ import annotations

LYON_ADDRESSES: list[dict] = [
    # Gares & hubs
    {"name": "Part-Dieu, Lyon", "lon": 4.8589, "lat": 45.7607, "type": "gare"},
    {"name": "Perrache, Lyon", "lon": 4.8340, "lat": 45.7480, "type": "gare"},
    # Places & monuments
    {"name": "Place Bellecour, Lyon", "lon": 4.8324, "lat": 45.7575, "type": "place"},
    {"name": "Hôtel de Ville, Lyon", "lon": 4.8342, "lat": 45.7672, "type": "monument"},
    {"name": "Place des Terreaux, Lyon", "lon": 4.8340, "lat": 45.7671, "type": "place"},
    {"name": "Opéra de Lyon", "lon": 4.8362, "lat": 45.7692, "type": "monument"},
    # Quartiers
    {"name": "Vieux Lyon", "lon": 4.8271, "lat": 45.7626, "type": "quartier"},
    {"name": "Presqu'île, Lyon", "lon": 4.8340, "lat": 45.7580, "type": "quartier"},
    {"name": "Confluence, Lyon", "lon": 4.8165, "lat": 45.7405, "type": "quartier"},
    {"name": "Croix-Rousse, Lyon", "lon": 4.8281, "lat": 45.7773, "type": "quartier"},
    {"name": "Vaise, Lyon", "lon": 4.8058, "lat": 45.7798, "type": "quartier"},
    {"name": "Gerland, Lyon", "lon": 4.8339, "lat": 45.7280, "type": "quartier"},
    {"name": "Mermoz, Lyon", "lon": 4.8700, "lat": 45.7310, "type": "quartier"},
    {"name": "Monplaisir, Lyon", "lon": 4.8603, "lat": 45.7434, "type": "quartier"},
    {"name": "Guillotière, Lyon", "lon": 4.8408, "lat": 45.7431, "type": "quartier"},
    # Places
    {"name": "Place Jean Macé, Lyon", "lon": 4.8417, "lat": 45.7456, "type": "place"},
    {"name": "Saxe-Gambetta, Lyon", "lon": 4.8461, "lat": 45.7496, "type": "place"},
    # Parcs & universités
    {"name": "Parc de la Tête d'Or, Lyon", "lon": 4.8525, "lat": 45.7745, "type": "parc"},
    {"name": "Université Lyon 3, Lyon", "lon": 4.8513, "lat": 45.7481, "type": "universite"},
    # Banlieue
    {"name": "Villeurbanne", "lon": 4.8810, "lat": 45.7715, "type": "banlieue"},
    {"name": "Bron", "lon": 4.9100, "lat": 45.7370, "type": "banlieue"},
]


def get_address_names() -> list[str]:
    """Retourne juste les noms (pour autocomplete)."""
    return [a["name"] for a in LYON_ADDRESSES]


def resolve_address(text: str) -> tuple[float, float] | None:
    """Résout une adresse textuelle en (lon, lat).

    Mock simple : matching par mot-clé. Sprint 6+ : Nominatim.
    """
    if not text:
        return None
    text_lower = text.lower().strip()
    for addr in LYON_ADDRESSES:
        name_lower = addr["name"].lower()
        # Match exact (sans ", Lyon")
        if text_lower == name_lower.replace(", lyon", "").strip():
            return (addr["lon"], addr["lat"])
        # Match par mot-clé commun
        for word in text_lower.split():
            if len(word) > 3 and word in name_lower:
                return (addr["lon"], addr["lat"])
    return None
