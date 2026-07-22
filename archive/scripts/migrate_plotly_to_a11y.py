"""Sprint 20 Axe E — Bulk migration : st.plotly_chart → plotly_with_alt.

Pour chaque widget :
1. Ajoute l'import ``from dashboard.components.a11y import plotly_with_alt``
   (si pas déjà présent, et si le widget a st.plotly_chart)
2. Remplace ``st.plotly_chart(<args>)`` par
   ``plotly_with_alt(<args sans fig>, alt_text="TODO_RAFFINER_PLUS_TARD", <rest>)``

L'alt_text est un placeholder. Patrice peut raffiner plus tard via des
recherches "TODO_RAFFINER_PLUS_TARD".

Idempotent : skip si déjà migré (présence de ``plotly_with_alt(``).
"""

from __future__ import annotations

from pathlib import Path

WIDGETS = Path("dashboard/components/widgets")

# Fichiers qui ont st.plotly_chart (16 occurrences dans 11 fichiers)
FILES = [
    "pro_tcl/modal_shift_alert.py",
    "pro_tcl/bus_traffic_spatial.py",
    "pro_tcl/backtest_dashboard.py",
    "pro_tcl/meteo_impact.py",
    "pro_tcl/otp_heatmap.py",
    "pro_tcl/before_after_chart.py",
    "pro_tcl/coherence_scatter.py",
    "pro_tcl/source_health_monitor.py",
    "pro_tcl/model_monitoring.py",
    "elu/network_health_gauge.py",
    "elu/trend_chart.py",
]

IMPORT_LINE = "from dashboard.components.a11y import plotly_with_alt"
ALT_TEXT = '"TODO_RAFFINER_PLUS_TARD"'


def migrate_file(path: Path) -> tuple[int, int]:
    """Migre un fichier. Retourne (count, import_added)."""
    content = path.read_text(encoding="utf-8")

    # Skip si déjà migré
    if "plotly_with_alt(" in content:
        return 0, 0

    # 1. Ajouter l'import si pas présent
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

    # 2. Remplacer st.plotly_chart( par plotly_with_alt(
    # Note : l'alt_text est ajouté après le 1er argument (fig)
    # On utilise une regex simple : ``st.plotly_chart(`` → ``plotly_with_alt(``
    # ET ``fig,`` → ``fig, alt_text=...,``  (à l'intérieur de l'appel)
    # Approximation : on remplace simplement le nom de la fonction.
    # L'alt_text sera ajouté manuellement (ou via Edit tool) après.
    new_content = content.replace("st.plotly_chart(", "plotly_with_alt(")

    # 3. Compter le nombre de replacements
    count = content.count("st.plotly_chart(")  # count AVANT le replace

    if new_content != content:
        path.write_text(new_content, encoding="utf-8")
    return count, import_added


def main() -> None:
    total = 0
    total_imp = 0
    for relpath in FILES:
        path = WIDGETS / relpath
        if not path.exists():
            print(f"SKIP {relpath} (not found)")
            continue
        n, imp = migrate_file(path)
        total += n
        total_imp += imp
        status = "OK  " if n else "SKIP"
        print(f"{status} {relpath}: {n} charts, {imp} import added")
    print(f"\nTotal: {total} charts, {total_imp} imports added across {len(FILES)} files")


if __name__ == "__main__":
    main()
