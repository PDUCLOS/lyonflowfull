"""Sprint 8+ — Politique "zéro mock dans le projet".

Ce module vérifie :
1. Aucune référence à ``src.data.mock.*`` dans ``src/``.
2. Le module ``src/data/mock/`` n'existe plus.
3. Aucun widget dashboard n'importe ``src.data.mock``.
4. Les fonctions deprecated ``_is_demo_mode`` et ``_maybe_force_mock``
   ont été supprimées du data_loader (Sprint 12+).
"""
from __future__ import annotations

from pathlib import Path


def test_deprecated_functions_removed() -> None:
    """_is_demo_mode() et _maybe_force_mock() sont supprimées (Sprint 12+)."""
    import src.data.data_loader as dl

    assert not hasattr(dl, "_is_demo_mode"), "_is_demo_mode doit être supprimée"
    assert not hasattr(dl, "_maybe_force_mock"), "_maybe_force_mock doit être supprimée"
    assert not hasattr(dl, "_demo_mode_cache"), "_demo_mode_cache doit être supprimée"


def test_no_mock_directory_in_src() -> None:
    """Le dossier src/data/mock/ doit avoir été supprimé."""
    project_root = Path(__file__).resolve().parents[2]
    mock_dir = project_root / "src" / "data" / "mock"
    assert not mock_dir.exists(), f"{mock_dir} existe encore — devrait être supprimé"


def test_no_mock_imports_in_src() -> None:
    """Aucune référence à ``src.data.mock`` (import ou appel) dans src/.

    Tolère les mentions dans les docstrings/commentaires.
    """
    project_root = Path(__file__).resolve().parents[2]
    src_dir = project_root / "src"

    for py_file in src_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text()
        for line_no, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            if "src.data.mock" in stripped:
                # Tolère commentaires / docstrings
                if stripped.startswith("#"):
                    continue
                if '"""' in line or "'''" in line:
                    continue
                # Sinon, c'est un import ou un appel → fail
                raise AssertionError(
                    f"{py_file}:{line_no} contient une référence non-doc à src.data.mock :\n  {line}"
                )


def test_widgets_have_no_mock_imports() -> None:
    """Aucun widget dashboard ne doit importer src.data.mock."""
    project_root = Path(__file__).resolve().parents[2]
    dashboard_dir = project_root / "dashboard"

    for py_file in dashboard_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text()
        assert "src.data.mock" not in content, (
            f"{py_file} importe encore src.data.mock — c'est interdit (Sprint 8)"
        )
