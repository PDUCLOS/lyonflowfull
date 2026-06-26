"""Migration auto : font-size inline → classes CSS lyf-*.

 audit (AUDIT_DASHBOARD_SPRINT15.md §5.1, option C) :
remplace les `style="font-size:0.7Xrem;..."` par `class="lyf-..."`
en gardant le reste des styles inline.

Mapping (basé sur l'audit) :
- 0.7rem  → lyf-sublabel (0.88rem + opacity 0.7)
- 0.75rem → lyf-sublabel
- 0.82rem → lyf-badge
- 0.85rem → lyf-detail
- 0.95rem → lyf-label
- 1.3rem  → lyf-value
- 1.4rem  → lyf-value

Le script est IDEMPOTENT : si la balise a déjà class="lyf-X", on ne
touche pas. Si elle a déjà class="lyonflow-card", on AJOUTE lyf-X.

Usage : ``python scripts/migrate_font_size_to_lyf.py [--apply]``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Mapping font-size (en rem) → classe CSS lyf-*
SIZE_TO_CLASS: dict[str, str] = {
    "0.7": "lyf-sublabel",
    "0.75": "lyf-sublabel",
    "0.82": "lyf-badge",
    "0.85": "lyf-detail",
    "0.95": "lyf-label",
    "1.3": "lyf-value",
    "1.4": "lyf-value",
}

# Match un font-size dans un style="..." inline.
# Capture : (1) la balise ouvrante jusqu'au début de style= (SANS le style=),
# (2) le style AVANT le font-size, (3) le font-size avec sa valeur, (4) le
# style APRÈS le font-size, (5) la fermeture du style.
FONT_SIZE_IN_STYLE_RE = re.compile(
    r"(<[a-zA-Z][a-zA-Z0-9-]*\b[^>]*?)"  # <tag ... (SANS style=)
    r'(\sstyle=")'  # style=" (séparé du tag)
    r'([^"]*?)'  # contenu du style avant font-size
    r"(font-size:([\d.]+)rem;?)"  # le font-size
    r'([^"]*?)'  # contenu du style après font-size
    r'(")',  # fermeture du style
    re.DOTALL,
)


def add_class_to_tag(tag_str: str, lyf_class: str) -> str:
    """Ajoute lyf_class à l'attribut class= de la balise tag_str, ou le crée."""
    class_match = re.search(r'class="([^"]*)"', tag_str)
    if class_match:
        existing = class_match.group(1).split()
        if lyf_class in existing:
            return tag_str  # déjà là
        existing.append(lyf_class)
        new_class = " ".join(existing)
        return tag_str[: class_match.start()] + f'class="{new_class}"' + tag_str[class_match.end() :]
    # Pas de class= : on l'ajoute juste après le tag name
    return re.sub(
        r"(<[a-zA-Z][a-zA-Z0-9-]*\b)",
        rf'\1 class="{lyf_class}"',
        tag_str,
        count=1,
    )


def migrate_text(content: str) -> tuple[str, int, int]:
    """Migre le contenu. Retourne (nouveau, found, replaced)."""
    found = 0
    replaced = 0

    def replace_one(match: re.Match[str]) -> str:
        nonlocal found, replaced
        found += 1
        size = match.group(5)
        if size not in SIZE_TO_CLASS:
            return match.group(0)
        lyf_class = SIZE_TO_CLASS[size]

        # Retrait du font-size du style : on splitte sur ;, on filtre les
        # entrées vides, on rejoint proprement avec ;
        full_style = match.group(3) + match.group(6)
        decls = [d.strip() for d in full_style.split(";") if d.strip()]
        # Filtrer le font-size de la liste (au cas où il serait dans before/after)
        decls = [d for d in decls if not d.lower().startswith("font-size:")]
        new_style_attr = f' style="{";".join(decls)};"' if decls else ""

        # Ajout de la classe à la balise parente
        new_tag = add_class_to_tag(match.group(1), lyf_class)

        replaced += 1
        return f"{new_tag}{new_style_attr}"

    new_content = FONT_SIZE_IN_STYLE_RE.sub(replace_one, content)
    return new_content, found, replaced


def migrate_file(path: Path, dry_run: bool = True) -> tuple[int, int]:
    content = path.read_text(encoding="utf-8")
    new_content, found, replaced = migrate_text(content)
    if not dry_run and new_content != content:
        path.write_text(new_content, encoding="utf-8")
    return found, replaced


def main() -> int:
    dry_run = "--apply" not in sys.argv
    dashboard = Path("dashboard")
    # Fichiers à NE PAS migrer (f-strings complexes où la regex casse
    # la syntaxe Python, ex: `{p["color_primary"]}` interprété à tort
    # comme une déclaration CSS). Patch manuel requis pour ces cas.
    blacklist = {
        "dashboard/components/persona_switcher.py",
    }
    targets = sorted(p for p in dashboard.rglob("*.py") if "__pycache__" not in str(p) and str(p) not in blacklist)

    total_found = 0
    total_replaced = 0
    files_changed = 0

    for path in targets:
        found, replaced = migrate_file(path, dry_run=dry_run)
        if found > 0:
            total_found += found
            total_replaced += replaced
            if replaced > 0:
                files_changed += 1
                tag = "🔍" if dry_run else "✅"
                print(f"  {tag} {path}: {found} trouvées, {replaced} migrées")
            else:
                print(f"  ⏭ {path}: {found} trouvées mais hors mapping (0.6rem, 0.65rem, etc.)")

    print()
    print(f"Total: {total_found} occurrences trouvées, {total_replaced} migrées sur {files_changed} fichiers")
    if dry_run:
        print("⚠️  DRY-RUN. Relance avec --apply pour écrire les changements.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
