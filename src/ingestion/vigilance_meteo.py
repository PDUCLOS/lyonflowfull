"""Collecteur — Vigilance météo-france, phénomène canicule (département 69).

Ce module ingère le niveau de vigilance officiel "canicule" du Rhône, pour
avertir l'usager Vélov quand le sport en extérieur est déconseillé.

API utilisée : Opendatasoft (miroir public, gratuit, sans clé) du dataset
    officiel "weatherref-france-vigilance-meteo-departement".
    https://public.opendatasoft.com/api/records/1.0/search/
    Paramètres : dataset=weatherref-france-vigilance-meteo-departement,
        refine.domain_id=69, refine.phenomenon=canicule, refine.echeance=J
    Retours : color (vert/jaune/orange/rouge), begin_time, end_time,
        product_datetime (date du bulletin officiel 6h/16h).

Fréquence d'ingestion recommandée : toutes les 6 heures.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

from src.db import execute_query
from src.ingestion.base import CollectorError, DataCollector, FetchResult

DATASET = "weatherref-france-vigilance-meteo-departement"


class VigilanceMeteo(DataCollector):
    """Collecteur de vigilance météo canicule pour le département du Rhône (69)."""

    def __init__(self):
        """Initialise le collecteur (URL, département cible, table Bronze)."""
        super().__init__(
            source="vigilance_meteo",
            bronze_table="vigilance_meteo",
            timeout=20,
        )
        self.url = os.getenv(
            "VIGILANCE_METEO_URL",
            "https://public.opendatasoft.com/api/records/1.0/search/",
        )
        self.departement = os.getenv("VIGILANCE_METEO_DEPARTEMENT", "69")

    def fetch_raw(self) -> FetchResult:
        """Récupère le niveau de vigilance canicule du jour pour le département.

        Returns:
            FetchResult: enregistrements bruts (0 à 2 lignes, une par tranche
            horaire du jour — les bulletins vigilance peuvent subdiviser la
            journée en 2 périodes avec des couleurs différentes).

        Raises:
            CollectorError: si l'appel API échoue.
        """
        params = {
            "dataset": DATASET,
            "refine.domain_id": self.departement,
            "refine.phenomenon": "canicule",
            "refine.echeance": "J",
        }

        try:
            r = self._http_get(self.url, params=params)
            data = r.json()
        except Exception as e:
            raise CollectorError(f"Erreur lors de la récupération de la vigilance météo: {e}") from e

        records = data.get("records", [])

        return FetchResult(
            source=self.source,
            fetched_at=datetime.now(UTC),
            raw_data=data,
            n_records=len(records),
            bytes_fetched=len(r.content),
            status_code=r.status_code,
        )

    def validate(self, result: FetchResult) -> bool:
        """Valide qu'au moins un enregistrement de couleur a été renvoyé.

        Un jour sans aucune vigilance canicule (cas le plus fréquent, vert)
        renvoie tout de même 1 ou 2 enregistrements — 0 enregistrement
        signale un problème côté API (dataset renommé, département invalide).
        """
        return result.n_records > 0

    def _save_raw(self, result: FetchResult) -> None:
        """Persiste chaque enregistrement (période horaire) en une ligne Bronze.

        Surcharge la persistance générique de `DataCollector` (qui n'insère
        que `fetched_at`/`raw_data`) car les colonnes extraites sont
        nécessaires ici sans étape Silver intermédiaire (décision : bronze
        suffit pour une table à faible volume, cf. migration_045).
        """
        if result.error or not result.raw_data:
            return

        records = result.raw_data.get("records", [])
        for rec in records:
            fields = rec.get("fields", {})
            execute_query(
                """
                INSERT INTO bronze.vigilance_meteo
                    (fetched_at, departement, couleur_canicule, echeance,
                     begin_time, end_time, bulletin_date, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (departement, echeance, begin_time, fetched_at) DO NOTHING
                """,
                (
                    result.fetched_at,
                    fields.get("domain_id", self.departement),
                    fields.get("color"),
                    fields.get("echeance", "J"),
                    fields.get("begin_time"),
                    fields.get("end_time"),
                    fields.get("product_datetime"),
                    json.dumps(rec, ensure_ascii=False, default=str),
                ),
            )
