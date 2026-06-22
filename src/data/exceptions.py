"""Exceptions spécifiques à la couche d'accès données du dashboard.

Sprint VPS-6 (2026-06-11) — fail loud en production.

Les fonctions ``load_X()`` du data_loader et certains widgets lèvent
``DashboardDataError`` quand la source de données (PostgreSQL, Airflow,
MLflow) est indisponible. Les widgets catchent l'exception et affichent
un ``st.error(...)`` explicite. Politique "zéro mock" (Sprint 8+) : aucune
source n'a de fallback silencieux.
"""

from __future__ import annotations


class DashboardDataError(Exception):
    """Levée quand une source de données (DB, Airflow, MLflow) est indisponible.

    Le widget appelant doit catcher cette exception et afficher un message
    d'erreur explicite à l'utilisateur (ex. ``st.error("⚠️ Données pipeline
    indisponibles — vérifier Airflow et PostgreSQL")``).

    Attributes:
        source: nom court de la source (ex. ``"postgresql"``, ``"airflow"``,
            ``"mlflow"``, ``"weather_db"``).
        detail: message technique (sera loggé, pas forcément affiché à l'utilisateur).
    """

    def __init__(self, source: str, detail: str = ""):
        self.source = source
        self.detail = detail
        msg = f"[{source}] Données pipeline indisponibles"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
