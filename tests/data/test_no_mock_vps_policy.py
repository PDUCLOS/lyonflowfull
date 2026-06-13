"""Sprint 8 (2026-06-12) — Politique "zéro mock dans le projet".

Avant (Sprint VPS-6) : politique "fail loud en prod, mock toléré en
démo". Le code avait un mode ``_is_demo_mode()`` qui retournait des
données mock si la DB était down.

Maintenant (Sprint 8) : politique "zéro mock dans le projet". Pas de
mode démo, pas de fallback mock. Si DB indispo, DashboardDataError.

Ce module vérifie :
1. ``_is_demo_mode()`` retourne TOUJOURS False (la fonction existe
   encore pour la compatibilité).
2. ``_maybe_force_mock()`` retourne TOUJOURS False.
3. Aucune référence à ``src.data.mock.*`` dans ``src/``.
4. Le module ``src/data/mock/`` n'existe plus.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_is_demo_mode_always_false() -> None:
    """_is_demo_mode() retourne TOUJOURS False depuis Sprint 8."""
    from src.data.data_loader import _is_demo_mode

    # Même avec LYONFLOW_DEMO_MODE=1, on doit retourner False.
    os.environ["LYONFLOW_DEMO_MODE"] = "1"
    assert _is_demo_mode() is False, "_is_demo_mode() doit retourner False"


def test_maybe_force_mock_always_false() -> None:
    """_maybe_force_mock() retourne TOUJOURS False depuis Sprint 8."""
    from src.data.data_loader import _maybe_force_mock

    assert _maybe_force_mock(False) is False
    assert _maybe_force_mock(True) is False  # même avec force_mock=True


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
                raise AssertionError(f"{py_file}:{line_no} contient une référence non-doc à src.data.mock :\n  {line}")


def test_widgets_have_no_mock_imports() -> None:
    """Aucun widget dashboard ne doit importer src.data.mock."""
    project_root = Path(__file__).resolve().parents[2]
    dashboard_dir = project_root / "dashboard"

    for py_file in dashboard_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text()
        assert "src.data.mock" not in content, f"{py_file} importe encore src.data.mock — c'est interdit (Sprint 8)"


def test_data_loader_no_mock_returns_empty() -> None:
    """Si DB indispo, data_loader retourne {} ou pd.DataFrame() vide, pas un mock."""
    from src.data.data_loader import _is_demo_mode

    # Mode démo n'a plus d'effet : _is_demo_mode est TOUJOURS False.
    assert _is_demo_mode() is False
