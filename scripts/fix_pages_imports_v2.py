"""Fix le bloc d'import cassé dans les pages (v2)."""
import re
from pathlib import Path

files = [
    "Elu_3_Avant_Apres.py", "Elu_4_Simulateur.py", "Elu_5_Rapport.py",
    "Pro_1_PCC_Live.py", "Pro_2_Heatmap_OTP.py", "Pro_3_Correlation.py",
    "Pro_4_Simulateur.py", "Usager_1_Mon_Trajet.py", "Usager_2_Alertes.py",
    "9_RGPD_Conformite.py", "A_Propos.py", "Elu_1_Synthese.py", "Elu_2_Bottlenecks.py",
]

# Pattern: from X import (\n...freshness_badge...\n) — block contenant un freshness_badge
# On restructure en : from X import (\n... sans freshness_badge ...)\nfrom dashboard.components.freshness_badge import render_freshness_badge
PATTERN = re.compile(
    r"^(from dashboard\.components\.\w+(?:\.\w+)* import \()\n"
    r"((?:    .+\n)+?)"  # contenu multiline indenté (non-greedy)
    r"\)",  # fermeture du bloc
    re.MULTILINE,
)


def fix_file(path: Path) -> int:
    c = path.read_text(encoding="utf-8")
    # 1. Trouver tous les blocs `from X import (...)` qui contiennent freshness_badge
    matches = list(PATTERN.finditer(c))
    if not matches:
        return 0

    new_c = c
    offset = 0
    fixed = 0
    for m in matches:
        start = m.start() + offset
        end = m.end() + offset
        block = new_c[start:end]
        if "freshness_badge" not in block:
            continue
        # Extraire les imports valides (sans freshness_badge)
        inner = m.group(2)
        cleaned_inner = re.sub(
            r"^.*freshness_badge.*\n", "", inner, flags=re.MULTILINE
        ).rstrip("\n")
        # Si cleaned est vide ou ne contient que des whitespace, ne pas garder le bloc
        if not cleaned_inner.strip():
            # Supprime tout le bloc (incluant le from X import () et l'import cassé)
            replacement = "from dashboard.components.freshness_badge import render_freshness_badge\n"
        else:
            replacement = (
                m.group(1) + "\n" + cleaned_inner + "\n)\n"
                "from dashboard.components.freshness_badge import render_freshness_badge\n"
            )
        new_c = new_c[:start] + replacement + new_c[end:]
        offset += len(replacement) - (end - start)
        fixed += 1

    # 2. Supprime les doublons freshness_badge
    new_c = re.sub(
        r"(from dashboard\.components\.freshness_badge import render_freshness_badge\n)+",
        "from dashboard.components.freshness_badge import render_freshness_badge\n",
        new_c,
    )

    if new_c != c:
        path.write_text(new_c, encoding="utf-8")
    return fixed


def main() -> None:
    total = 0
    for f in files:
        p = Path("dashboard/pages") / f
        if not p.exists():
            continue
        n = fix_file(p)
        if n > 0:
            print(f"FIXED {f}: {n} blocs")
            total += n
    print(f"Total: {total}")


if __name__ == "__main__":
    main()
