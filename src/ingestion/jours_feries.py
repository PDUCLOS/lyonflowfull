"""Collecteur — Jours fériés en France (calendrier.api.gouv.fr).

Module responsable de l'ingestion des jours fériés via l'API gouvernementale.
Ces données sont utiles pour les modèles prédictifs, le trafic étant
sensiblement différent lors des jours fériés.

API utilisée : https://calendrier.api.gouv.fr/jours-feries/
Fréquence d'ingestion recommandée : 1 fois par an
Volume estimé : ~11 jours fériés par an
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from src.ingestion.base import CollectorError, DataCollector, FetchResult

logger = logging.getLogger(__name__)


class JoursFeries(DataCollector):
    """Collecteur des jours fériés officiels pour la France métropolitaine."""

    def __init__(self):
        """Initialise le collecteur de jours fériés.

        Configure l'URL cible et la table de destination dans la couche Bronze.
        """
        super().__init__(
            source="jours_feries",
            bronze_table="jours_feries",
            timeout=30,
        )
        self.url = os.getenv(
            "JOURS_FERIES_URL",
            "https://calendrier.api.gouv.fr/jours-feries/",
        )

    def fetch_raw(self) -> FetchResult:
        """Récupère les jours fériés de l'année en cours et de l'année suivante.

        L'API gouvernementale segmente les données par année et par zone (métropole).
        Le collecteur effectue donc deux requêtes (N et N+1) pour anticiper.

        Returns:
            FetchResult: Les données agrégées sous forme de dictionnaire indexé par année.

        Raises:
            CollectorError: Si aucune donnée n'a pu être collectée.
        """
        annees = [datetime.now().year, datetime.now().year + 1]
        all_data = {}

        for annee in annees:
            try:
                r = self._http_get(f"{self.url}metropole/{annee}.json")
                all_data[annee] = r.json()
            except Exception as e:
                logger.warning("Erreur lors de la récupération des jours fériés pour l'année %d: %s", annee, e)
                continue

        # Vérification qu'au moins une année a pu être téléchargée
        if not all_data:
            raise CollectorError("Aucune donnée de jours fériés n'a pu être collectée.")

        n_records = sum(len(v) for v in all_data.values())

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=all_data,
            n_records=n_records,
            status_code=200,
        )
