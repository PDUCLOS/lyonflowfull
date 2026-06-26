"""Exceptions spécifiques à la couche d'accès aux données du dashboard.

Le système est conçu pour échouer de manière explicite ("fail loud") en production.

Les fonctions ``load_X()`` du module `data_loader` et certains widgets lèvent
l'exception ``DashboardDataError`` lorsque la source de données (PostgreSQL, 
Airflow, MLflow) est indisponible. Les widgets interceptent l'exception et affichent
un message explicite via ``st.error(...)``. 

Politique stricte de "zéro mock" : aucune source ne possède de mécanisme de repli 
silencieux (fallback).
"""

from __future__ import annotations


class DashboardDataError(Exception):
    """Levée quand une source de données (DB, Airflow, MLflow) est indisponible.

    Le widget appelant doit intercepter cette exception et afficher un message
    d'erreur explicite à l'utilisateur (ex. ``st.error("⚠️ Données du pipeline
    indisponibles — vérifier Airflow et PostgreSQL")``).

    Attributes:
        source: Nom court de la source (ex. ``"postgresql"``, ``"airflow"``,
            ``"mlflow"``, ``"weather_db"``).
        detail: Message technique additionnel (destiné aux journaux de logs, 
            pas nécessairement affiché à l'utilisateur final).
    """

    def __init__(self, source: str, detail: str = ""):
        self.source = source
        self.detail = detail
        msg = f"[{source}] Données du pipeline indisponibles"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
