"""Fix le pattern cassé dans les pages (Sprint 20 Axe F)."""

import re
from pathlib import Path

files = [
    "Elu_3_Avant_Apres.py",
    "Elu_4_Simulateur.py",
    "Elu_5_Rapport.py",
    "Pro_1_PCC_Live.py",
    "Pro_2_Heatmap_OTP.py",
    "Pro_3_Correlation.py",
    "Pro_4_Simulateur.py",
    "Pro_6_Pipeline_Mgmt.py",
    "Pro_7_Model_Monitoring.py",
    "Usager_1_Mon_Trajet.py",
    "Usager_2_Alertes.py",
]

target = "import (\nfrom dashboard.components.freshness_badge import render_freshness_badge"
# Replacement : ajoute un \n supplémentaire pour séparer l'import cassé du bloc
replacement = "import (\n\nfrom dashboard.components.freshness_badge import render_freshness_badge"

for f in files:
    p = Path("dashboard/pages") / f
    c = p.read_text(encoding="utf-8")
    if target not in c:
        print(f"NO MATCH {f}")
        continue
    new = c.replace(target, replacement, 1)
    new = re.sub(
        r"(from dashboard\.components\.freshness_badge import render_freshness_badge\n)+",
        "from dashboard.components.freshness_badge import render_freshness_badge\n",
        new,
    )
    p.write_text(new, encoding="utf-8")
    print(f"FIXED {f}")
