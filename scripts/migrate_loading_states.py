"""Bulk migration Sprint 20 Axe A : wrap les render_X() dans loading_wrapper.

Pour chaque widget dans WIDGETS qui a un ``def render_X():`` non encore
migré :
1. Ajoute l'import ``from dashboard.components.loading_state import loading_wrapper``
   (si pas déjà présent)
2. Wrap le body de la fonction dans ``with loading_wrapper("…", "⏳"):``

Heuristiques :
- Skip si le body est déjà wrappé (chercher loading_wrapper au début)
- Skip si le widget est dans la liste SKIP_WIDGETS (déjà migrés manuellement)
- Indent proprement le body (ajoute 4 espaces à chaque ligne)

Usage : ``python scripts/migrate_loading_states.py``
"""

from __future__ import annotations

import re
from pathlib import Path

WIDGETS = Path("dashboard/components/widgets")

# Fichiers à scanner
FILES = [
    "elu/bottleneck_map.py",
    "elu/bottleneck_ranking.py",
    "elu/data_quality_badge.py",
    "elu/data_quality_detail.py",
    "elu/drift_status_badge.py",
    "elu/executive_summary.py",
    "elu/kpi_cards.py",
    "elu/map_painter.py",
    "elu/network_health_gauge.py",
    "elu/project_selector.py",
    "elu/roi_calculator.py",
    "elu/top_decisions.py",
    "elu/trend_chart.py",
    "pro_tcl/alert_ticker.py",
    "pro_tcl/backtest_dashboard.py",
    "pro_tcl/bus_traffic_spatial.py",
    "pro_tcl/coherence_scatter.py",
    "pro_tcl/correlation_matrix.py",
    "pro_tcl/gnn_map.py",
    "pro_tcl/line_comparison.py",
    "pro_tcl/line_kpis.py",
    "pro_tcl/line_selector.py",
    "pro_tcl/meteo_impact.py",
    "pro_tcl/modal_shift_alert.py",
    "pro_tcl/multimodal_heatmap.py",
    "pro_tcl/network_map.py",
    "pro_tcl/otp_heatmap.py",
    "pro_tcl/pipeline_management.py",
    "pro_tcl/propagation_map.py",
    "pro_tcl/segment_table.py",
    "pro_tcl/source_health_monitor.py",
    "usager/search_bar.py",
    "usager/traffic_widget.py",
    "usager/transit_trip.py",
    "usager/velov_map.py",
    "usager/velov_widget.py",
    "usager/weather_widget.py",
]

# Widgets déjà migrés manuellement (skip)
ALREADY_MIGRATED = {
    "pro_tcl/model_monitoring.py",  # utilise déjà loading_wrapper
    "usager/itinerary.py",  # utilise déjà loading_wrapper
}

# Pattern pour trouver le body d'une def render_X():
# Captures : 1=ligne def + signature, 2=body
_RENDER_PATTERN = re.compile(
    r"^(def\s+render_\w+\([^)]*\)[^:]*:\n)((?:(?:    |\t).*\n)+)",
    re.MULTILINE,
)

IMPORT_LINE = "from dashboard.components.loading_state import loading_wrapper"


def indent_block(text: str, extra: int = 4) -> str:
    """Indente un block de texte de N espaces supplémentaires."""
    pad = " " * extra
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


def migrate_file(path: Path) -> tuple[int, int]:
    """Migre un fichier. Retourne (render_migrated, import_added)."""
    content = path.read_text(encoding="utf-8")

    # 1. Skip si déjà migré
    if "loading_wrapper" in content and "from dashboard.components.loading_state" in content:
        return 0, 0

    # 2. Ajouter l'import si pas déjà présent
    import_added = 0
    if IMPORT_LINE not in content:
        lines = content.split("\n")
        # Trouver le dernier import standard (après les imports streamlit et dashboard)
        last_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("import streamlit") or line.startswith("from dashboard.components."):
                last_idx = i
        if last_idx >= 0:
            lines.insert(last_idx + 1, IMPORT_LINE)
            content = "\n".join(lines)
            import_added = 1

    # 3. Wrap les render_X() dans loading_wrapper
    matches = list(_RENDER_PATTERN.finditer(content))
    if not matches:
        return 0, import_added

    # Reconstruire le contenu
    new_content = content
    offset = 0
    migrated = 0
    for m in matches:
        # Vérifier que ce render_X n'est pas déjà dans un with loading_wrapper
        # (regex: chercher "with loading_wrapper" dans les 50 chars après la def)
        start_pos = m.end() + offset
        if "loading_wrapper" in new_content[start_pos : start_pos + 200]:
            continue

        def_line = m.group(1)
        body = m.group(2)
        # Le label est dérivé du nom de la fonction
        func_name = re.search(r"def\s+(render_\w+)", def_line).group(1)
        widget_label = func_name.replace("render_", "").replace("_", " ").capitalize()
        loading_call = f'    with loading_wrapper("Chargement {widget_label}…", "⏳"):\n'

        # Indenter le body
        indented_body = indent_block(body, 4)
        new_block = loading_call + indented_body
        # Remplacer dans new_content
        old_block = def_line + body
        new_pos = new_content.find(old_block, start_pos - len(def_line) - 200 if start_pos > 200 else 0)
        if new_pos == -1:
            continue
        new_content = new_content[:new_pos] + def_line + new_block + new_content[new_pos + len(old_block) :]
        offset += len(new_block) - len(old_block)
        migrated += 1

    path.write_text(new_content, encoding="utf-8")
    return migrated, import_added


def main() -> None:
    total_mig = 0
    total_imp = 0
    for relpath in FILES:
        if relpath in ALREADY_MIGRATED:
            print(f"SKIP {relpath} (already migrated)")
            continue
        path = WIDGETS / relpath
        if not path.exists():
            print(f"SKIP {relpath} (not found)")
            continue
        mig, imp = migrate_file(path)
        total_mig += mig
        total_imp += imp
        print(f"OK   {relpath}: {mig} render_X wrapped, {imp} import added")
    print(f"\nTotal: {total_mig} render_X wrapped, {total_imp} imports added across {len(FILES)} files")


if __name__ == "__main__":
    main()
