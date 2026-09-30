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

Saisonnalité : la vigilance canicule n'est publiée que pendant la veille
saisonnière (1er juin → 15 septembre, parfois prolongée si un épisode de
chaleur persiste). Hors saison, l'API ne renvoie aucun enregistrement
canicule, pour aucun département — les autres phénomènes (orages, vent,
pluie, neige/verglas) restent publiés. Constaté le 2026-09-30 : 0 résultat
France entière alors que le Rhône avait 4 phénomènes actifs.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.db import execute_query
from src.ingestion.base import CollectorError, DataCollector, FetchResult

DATASET = "weatherref-france-vigilance-meteo-departement"

# Veille saisonnière canicule (Santé publique France / Météo-France).
CANICULE_SEASON_START = (6, 1)
CANICULE_SEASON_END = (9, 15)


def is_canicule_season(day: date | None = None) -> bool:
    """Indique si la date tombe dans la veille saisonnière canicule.

    Args:
        day: date à tester (défaut : aujourd'hui, heure de Paris).

    Returns:
        True entre le 1er juin et le 15 septembre inclus.
    """
    d = day or datetime.now(ZoneInfo("Europe/Paris")).date()
    return CANICULE_SEASON_START <= (d.month, d.day) <= CANICULE_SEASON_END


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
        """Valide la réponse de l'API selon la saison.

        En saison, un jour sans vigilance (vert) renvoie tout de même 1 ou 2
        enregistrements : 0 enregistrement signale un problème côté API
        (dataset renommé, département invalide). Hors saison, 0 enregistrement
        est la réponse normale — on exige seulement une réponse bien formée.
        """
        if not isinstance(result.raw_data, dict) or "records" not in result.raw_data:
            return False
        if result.n_records > 0:
            return True
        return not is_canicule_season()

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
