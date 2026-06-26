"""Fix Axe F : déplace l'import mal placé dans les pages.

Le script ``migrate_freshness_badge.py`` a inséré l'import au mauvais endroit
dans ~10 fichiers : après le ``(`` d'un multi-ligne ``from X import (`` au lieu
d'après le ``)`` de fermeture. Résultat : invalid-syntax.

Ce script détecte le pattern et le corrige.
"""

from __future__ import annotations

import re
from pathlib import Path

PAGES = Path("dashboard/pages")

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

# Pattern cassé : ligne `from X import (` puis ligne `from dashboard.components.freshness_badge import render_freshness_badge`
# puis contenu du `import (...)` puis `)`.
# On veut déplacer la ligne freshness_badge après le `)`.
BROKEN_PATTERN = re.compile(
    r"^(from dashboard\.components\.\w+(?:\.\w+)* import \()\n"
    r"(from dashboard\.components\.freshness_badge import render_freshness_badge\n)"
    r"((?:    .+\n)+)"
    r"(\))",
    re.MULTILINE,
)


def fix_file(path: Path) -> int:
    content = path.read_text(encoding="utf-8")
    new_content, n = BROKEN_PATTERN.subn(
        r"\1\2\3\nfrom dashboard.components.freshness_badge import render_freshness_badge",
        content,
    )
    if n > 0:
        path.write_text(new_content, encoding="utf-8")
    return n


def main() -> None:
    total = 0
    for relpath in FILES:
        path = PAGES / relpath
        if not path.exists():
            continue
        n = fix_file(path)
        if n > 0:
            print(f"FIXED {relpath}: {n} occurrences")
            total += n
    print(f"\nTotal: {total} fixes")


if __name__ == "__main__":
    main()
