"""Bulk migration Sprint 20 Axe D : remplace st.error(f"⚠️ {e}") par show_error("db_down", str(e)).

Pour chaque widget dans WIDGET_FILES :
1. Ajoute l'import ``from dashboard.components.error_display import show_error``
   après le dernier import ``from dashboard.components.*``
2. Remplace ``st.error(f"⚠️ {e}")`` par ``show_error("db_down", str(e))``

Usage : ``python scripts/migrate_error_display.py``
"""

from __future__ import annotations

from pathlib import Path

WIDGETS = Path("dashboard/components/widgets")

FILES = [
    "pro_tcl/segment_table.py",
    "pro_tcl/bus_traffic_spatial.py",
    "pro_tcl/network_map.py",
    "pro_tcl/propagation_map.py",
    "pro_tcl/multimodal_heatmap.py",
    "pro_tcl/modal_shift_alert.py",
    "pro_tcl/correlation_matrix.py",
    "pro_tcl/coherence_scatter.py",
    "pro_tcl/model_monitoring.py",
    "pro_tcl/meteo_impact.py",
    "pro_tcl/pipeline_management.py",
    "usager/weather_widget.py",
    "usager/itinerary.py",
    "usager/transit_trip.py",
    "usager/lieux_velov_map.py",
    "usager/velov_trip.py",
]

IMPORT_LINE = "from dashboard.components.error_display import show_error\n"
OLD_PATTERN = 'st.error(f"⚠️ {e}")'
NEW_PATTERN = 'show_error("db_down", str(e))'


def migrate_file(path: Path) -> tuple[int, int]:
    """Migre un fichier. Retourne (occurrences remplacées, import ajouté)."""
    content = path.read_text(encoding="utf-8")

    # 1. Compter + remplacer les st.error
    occurrences = content.count(OLD_PATTERN)
    content = content.replace(OLD_PATTERN, NEW_PATTERN)

    # 2. Ajouter l'import si pas déjà présent
    import_added = 0
    if "from dashboard.components.error_display import show_error" not in content:
        # Trouver le dernier import "from dashboard.components"
        lines = content.split("\n")
        last_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("from dashboard.components."):
                last_idx = i
        if last_idx >= 0:
            # Insérer l'import après le dernier import dashboard.components
            lines.insert(last_idx + 1, IMPORT_LINE.rstrip("\n"))
            content = "\n".join(lines)
            import_added = 1

    path.write_text(content, encoding="utf-8")
    return occurrences, import_added


def main() -> None:
    total_occ = 0
    total_imp = 0
    for relpath in FILES:
        path = WIDGETS / relpath
        if not path.exists():
            print(f"SKIP {relpath} (not found)")
            continue
        occ, imp = migrate_file(path)
        total_occ += occ
        total_imp += imp
        print(f"OK   {relpath}: {occ} replaced, {imp} import added")
    print(f"\nTotal: {total_occ} replacements, {total_imp} imports added across {len(FILES)} files")


if __name__ == "__main__":
    main()
