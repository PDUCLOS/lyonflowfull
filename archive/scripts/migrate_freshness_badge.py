"""Bulk migration Axe F : ajoute render_freshness_badge() aux 15 pages.

Pour chaque page qui a déjà setup_auto_refresh() :
1. Ajoute l'import ``from dashboard.components.freshness_badge import render_freshness_badge``
   (si pas déjà présent)
2. Ajoute l'appel ``render_freshness_badge()`` juste après ``setup_auto_refresh()``

Usage : ``python scripts/migrate_freshness_badge.py``
"""

from __future__ import annotations

from pathlib import Path

PAGES = Path("dashboard/pages")

# Pages qui ont setup_auto_refresh() (15 trouvées)
FILES = [
    "Usager_2_Alertes.py",
    "Elu_5_Rapport.py",
    "Elu_4_Simulateur.py",
    "9_RGPD_Conformite.py",
    "Pro_6_Pipeline_Mgmt.py",
    "Elu_2_Bottlenecks.py",
    "A_Propos.py",
    "Elu_1_Synthese.py",
    "Pro_4_Simulateur.py",
    "Elu_3_Avant_Apres.py",
    "Pro_3_Correlation.py",
    "Usager_1_Mon_Trajet.py",
    "Pro_7_Model_Monitoring.py",
    "Pro_1_PCC_Live.py",
    "Pro_2_Heatmap_OTP.py",
]

IMPORT_LINE = "from dashboard.components.freshness_badge import render_freshness_badge"
CALL_LINE = "render_freshness_badge()"


def migrate_file(path: Path) -> tuple[int, int]:
    """Migre un fichier. Retourne (call_added, import_added)."""
    content = path.read_text(encoding="utf-8")

    call_added = 0
    import_added = 0

    # 1. Skip si déjà migré
    if "render_freshness_badge" in content:
        return 0, 0

    # 2. Ajouter l'appel juste après setup_auto_refresh()
    if "setup_auto_refresh()" in content:
        content = content.replace(
            "setup_auto_refresh()\n",
            "setup_auto_refresh()\nrender_freshness_badge()\n",
            1,
        )
        call_added = 1

    # 3. Ajouter l'import
    if call_added and IMPORT_LINE not in content:
        lines = content.split("\n")
        last_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("from dashboard.components."):
                last_idx = i
        if last_idx >= 0:
            lines.insert(last_idx + 1, IMPORT_LINE)
            content = "\n".join(lines)
            import_added = 1

    if call_added or import_added:
        path.write_text(content, encoding="utf-8")

    return call_added, import_added


def main() -> None:
    total_call = 0
    total_imp = 0
    for relpath in FILES:
        path = PAGES / relpath
        if not path.exists():
            print(f"SKIP {relpath} (not found)")
            continue
        call, imp = migrate_file(path)
        total_call += call
        total_imp += imp
        status = "OK  " if call else "SKIP"
        print(f"{status} {relpath}: call={call} import={imp}")
    print(f"\nTotal: {total_call} calls added, {total_imp} imports added across {len(FILES)} files")


if __name__ == "__main__":
    main()
