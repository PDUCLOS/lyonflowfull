"""Sprint 20 Axe A v3 : wrap les render_X() avec loading_wrapper.

Pour chaque widget dans FILES :
1. Trouve ``def render_X(...)`` (signature multi-ligne)
2. Trouve la fin de la signature (ligne ``) -> TYPE:`` ou ``) -> None:``)
3. Trouve le docstring (s'il y en a un)
4. Trouve la fin du body (prochaine def/class/@decorator au top-level)
5. Insère ``    with loading_wrapper("...", "⏳"):\\n`` après le docstring
6. Indente le body de +4 espaces

Le v3 gère les signatures multi-lignes et les docstrings via un parser
ligne par ligne (pas de regex).
"""

from __future__ import annotations

from pathlib import Path

WIDGETS = Path("dashboard/components/widgets")

FILES = [
    "usager/velov_trip.py",
    "usager/search_bar.py",
    "elu/executive_summary.py",
    "elu/pdf_generator.py",
    "elu/kpi_cards.py",
    "elu/drift_status_badge.py",
    "elu/data_quality_badge.py",
    "pro_tcl/correlation_matrix.py",
    "pro_tcl/source_health_monitor.py",
    "usager/mode_comparison.py",
]

IMPORT_LINE = "from dashboard.components.loading_state import loading_wrapper"


def find_def_signature_end(lines: list[str], start_idx: int) -> int | None:
    """Trouve la ligne qui termine la signature (contient `):` ou `) ->`)."""
    for i in range(start_idx, min(start_idx + 50, len(lines))):
        line = lines[i]
        # Cherche `):` ou `) ->` ou `) -> None:` à la fin de la ligne (pas dans un commentaire)
        stripped = line.rstrip()
        if stripped.endswith(":") and ")" in stripped and stripped.rfind(")") < stripped.rfind(":"):
            return i
    return None


def find_docstring_end(lines: list[str], start_idx: int) -> int:
    """Trouve la fin du docstring (s'il y en a un) après la signature.

    Retourne l'index de la ligne qui termine le docstring, ou start_idx
    si pas de docstring.
    """
    for i in range(start_idx, min(start_idx + 50, len(lines))):
        line = lines[i].strip()
        if line.startswith('"""') and not line.endswith('"""'):
            # Docstring multi-ligne commence ici
            for j in range(i + 1, min(i + 200, len(lines))):
                if '"""' in lines[j]:
                    return j
            return i
        elif line.startswith('"""') and line.endswith('"""') and len(line) > 6:
            # Docstring une seule ligne
            return i
        elif line and not line.startswith("#") and not line.startswith('"""'):
            # Pas un docstring
            return start_idx - 1
    return start_idx - 1


def find_body_end(lines: list[str], start_idx: int) -> int:
    """Trouve la fin du body de la fonction (prochaine def/class au top-level)."""
    for i in range(start_idx, len(lines)):
        line = lines[i]
        if i > start_idx and (line.startswith("def ") or line.startswith("class ") or line.startswith("@")):
            return i
    return len(lines)


def migrate_file(path: Path) -> tuple[int, int]:
    content = path.read_text(encoding="utf-8")

    # Skip si déjà wrappé
    if "with loading_wrapper(" in content:
        return 0, 0

    lines = content.split("\n")

    # 1. Ajouter l'import si pas présent
    import_added = 0
    if IMPORT_LINE not in content:
        last_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("import streamlit") or line.startswith("from dashboard.components."):
                last_idx = i
        if last_idx >= 0:
            lines.insert(last_idx + 1, IMPORT_LINE)
            import_added = 1

    # 2. Trouver def render_X
    def_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("def render_") and "render_" in line:
            def_idx = i
            break

    if def_idx < 0:
        return 0, import_added

    # 3. Fin de la signature
    sig_end = find_def_signature_end(lines, def_idx)
    if sig_end is None:
        return 0, import_added

    # 4. Fin du docstring
    doc_end = find_docstring_end(lines, sig_end + 1)

    # 5. Fin du body
    body_start = doc_end + 1
    body_end = find_body_end(lines, body_start)
    if body_end <= body_start:
        return 0, import_added

    # 6. Extraire le body et l'indenter
    body_lines = lines[body_start:body_end]
    # Trouver l'indentation de base (4 espaces normalement)
    base_indent = "    "
    indented = []
    for line in body_lines:
        if line.strip():
            indented.append(base_indent + line)
        else:
            indented.append(line)
    new_body = "\n".join(indented)

    # 7. Récupérer le nom de la fonction pour le label
    func_name_line = lines[def_idx]
    func_name = func_name_line.split("(")[0].replace("def ", "").replace("render_", "").replace("_", " ").capitalize()

    # 8. Insérer le with loading_wrapper après le docstring
    loading_line = f'{base_indent}with loading_wrapper("Chargement {func_name}…", "⏳"):\n'

    # 9. Reconstruire
    new_lines = [
        *lines[:body_start],
        loading_line.rstrip("\n"),
        new_body,
        *lines[body_end:],
    ]

    path.write_text("\n".join(new_lines), encoding="utf-8")
    return 1, import_added


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
        print(f"{status} {relpath}: {n} render_X wrapped, {imp} import added")
    print(f"\nTotal: {total} render_X wrapped, {total_imp} imports added across {len(FILES)} files")


if __name__ == "__main__":
    main()
