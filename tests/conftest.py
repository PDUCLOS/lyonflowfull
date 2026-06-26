"""Conftest minimal — (2026-06-19).

Setup unique : ajoute la racine du projet à ``sys.path`` pour permettre
les imports ``from src.xxx import yyy`` depuis les tests.

 la classe ``MockDB`` et la fixture ``mock_db`` ont été
virées (audit Patrice 2026-06-19, politique "zéro mock" durcie). Pour
tester du code qui touche la DB, marquer ``@pytest.mark.integration``
(skippé par défaut via ``pyproject.toml`` ``addopts``).
"""

from __future__ import annotations

import os
import sys

# Permet les imports ``from src.xxx import yyy`` depuis les tests
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
