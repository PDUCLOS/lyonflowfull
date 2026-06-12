"""Exceptions spécifiques à la couche d'accès données du dashboard.

Sprint VPS-6 (2026-06-11) — fail loud en production.

Quand le dashboard tourne en mode production (``LYONFLOW_DEMO_MODE!=1``),
les fonctions ``load_X()`` du data_loader et certains widgets lèvent
``DashboardDataError`` au lieu de tomber sur les mocks quand la source
de données (PostgreSQL, Airflow, MLflow) est indisponible. Les widgets
catchent l'exception et affichent un ``st.error(...)`` explicite.

Mode démo (``LYONFLOW_DEMO_MODE=1``) : le comportement historique est
préservé (fallback mock transparent) pour le dev local et les démos.
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
