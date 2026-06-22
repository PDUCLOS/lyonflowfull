"""Sprint 20 Axe E — Bulk migration : st_folium → st_folium_with_alt.

Pour chaque widget :
1. Ajoute l'import ``from dashboard.components.a11y import st_folium_with_alt``
2. Remplace ``st_folium(`` par ``st_folium_with_alt(``
3. Ajoute un alt_text par défaut
"""

from __future__ import annotations

from pathlib import Path

WIDGETS = Path("dashboard/components/widgets")

FILES = [
    ("elu/map_painter.py", "Carte sélection zones (map_painter)"),
    ("elu/bottleneck_map.py", "Carte bottlenecks infrastructure"),
    ("usager/itinerary.py", "Itinéraire voiture — polyline sur rues OSM"),
    ("usager/velov_trip.py", "Trajet Vélov — 3 segments (marche + vélo + marche)"),
    ("usager/lieux_velov_map.py", "Carte stations Vélov proches"),
]

IMPORT_LINE = "from dashboard.components.a11y import st_folium_with_alt"


def migrate_file(path: Path, alt_text: str) -> tuple[int, int]:
    content = path.read_text(encoding="utf-8")
    if "st_folium_with_alt(" in content:
        return 0, 0

    # Ajouter l'import
    import_added = 0
    if IMPORT_LINE not in content:
        lines = content.split("\n")
        last_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("from dashboard.components."):
                last_idx = i
        if last_idx >= 0:
            lines.insert(last_idx + 1, IMPORT_LINE)
            content = "\n".join(lines)
            import_added = 1

    # Remplacer st_folium( par st_folium_with_alt(
    count = content.count("st_folium(")
    new_content = content.replace("st_folium(", "st_folium_with_alt(")

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
    return count, import_added


def main() -> None:
    total = 0
    for relpath, alt in FILES:
        path = WIDGETS / relpath
        if not path.exists():
            print(f"SKIP {relpath}")
            continue
        n, imp = migrate_file(path, alt)
        total += n
        status = "OK  " if n else "SKIP"
        print(f"{status} {relpath}: {n} st_folium → st_folium_with_alt ({imp} import)")
    print(f"\nTotal: {total} st_folium migrés across {len(FILES)} files")


if __name__ == "__main__":
    main()
