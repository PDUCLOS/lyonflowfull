"""Seed du référentiel cadence x calendrier.

Sprint VPS-6 (2026-06-11) — Peuple ``referentiel.lieux_calendrier`` depuis
la vue ``referentiel.v_cadence_summary`` (qui agrege ``gold.tcl_vehicle_realtime``
+ ``bronze.calendrier_scolaire`` + ``bronze.jours_feries``).

Idempotent : UPSERT sur (line_ref, day_type, time_bucket).
Recalcul quotidien recommandé via DAG ``refresh_lieux_calendrier`` (Sprint 7+).

Usage::

    # Manuel
    python scripts/seed_lieux_calendrier.py
    # Vérif rapide
    python scripts/seed_lieux_calendrier.py --dry-run
    # Cron quotidien (Sprint 7+)
    0 5 * * *  cd /opt/lyonflow && python scripts/seed_lieux_calendrier.py >> logs/calendrier.log 2>&1
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

# Permet l'import depuis la racine du repo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("seed_lieux_calendrier")

load_dotenv()


def get_db_connection() -> psycopg2.extensions.connection:
    """Connexion DB via variables d'env."""
    pwd = os.getenv("POSTGRES_PASSWORD")
    if not pwd:
        raise SystemExit("[ABORT] POSTGRES_PASSWORD manquant dans .env")
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "lyonflow"),
        user=os.getenv("POSTGRES_USER", "lyonflow"),
        password=pwd,
        connect_timeout=10,
    )


def fetch_cadence_summary(conn) -> list[dict]:
    """Lit la vue v_cadence_summary (cadence observée 7j glissants)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM referentiel.v_cadence_summary")
        return [dict(row) for row in cur.fetchall()]


def upsert_cadence(conn, rows: list[dict], dry_run: bool = False) -> tuple[int, int]:
    """UPSERT dans ``referentiel.lieux_calendrier``.

    Returns:
        (n_inserted_or_updated, n_total_rows)
    """
    if dry_run:
        return (len(rows), len(rows))

    sql = """
        INSERT INTO referentiel.lieux_calendrier
            (line_ref, day_type, time_bucket, cadence_min_per_vehicle,
             n_observations, confidence, computed_at)
        VALUES (%(line_ref)s, %(day_type)s, %(time_bucket)s,
                %(cadence_min_per_vehicle)s, %(n_observations)s,
                %(confidence)s, NOW())
        ON CONFLICT (line_ref, day_type, time_bucket) DO UPDATE SET
            cadence_min_per_vehicle = EXCLUDED.cadence_min_per_vehicle,
            n_observations          = EXCLUDED.n_observations,
            confidence              = EXCLUDED.confidence,
            computed_at             = NOW()
    """
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, sql, rows, page_size=200)
    conn.commit()
    return (len(rows), len(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche ce qui serait inséré sans toucher la DB",
    )
    args = parser.parse_args()

    logger.info("Connexion à PostgreSQL…")
    conn = get_db_connection()
    try:
        logger.info("Lecture de referentiel.v_cadence_summary…")
        rows = fetch_cadence_summary(conn)
        if not rows:
            logger.warning(
                "Aucune ligne dans v_cadence_summary. Causes possibles : "
                "(1) gold.tcl_vehicle_realtime vide — vérifier DAG collect_bronze, "
                "(2) fenêtre 7j trop courte (premier run après install). "
                "Sortie sans erreur."
            )
            return

        # Stats par day_type pour le log
        by_day: dict[str, int] = {}
        for r in rows:
            by_day[r["day_type"]] = by_day.get(r["day_type"], 0) + 1
        logger.info(
            "%d observations lues (%s)",
            len(rows),
            ", ".join(f"{k}={v}" for k, v in sorted(by_day.items())),
        )

        if args.dry_run:
            logger.info("[DRY-RUN] Premières 5 observations :")
            for r in rows[:5]:
                logger.info("  %s", r)
            return

        n_upserted, _ = upsert_cadence(conn, rows, dry_run=False)
        logger.info("✅ %d lignes upsertées dans referentiel.lieux_calendrier", n_upserted)

        # Vérif post-seed
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM referentiel.lieux_calendrier")
            total = cur.fetchone()[0]
            cur.execute(
                "SELECT day_type, COUNT(*) FROM referentiel.lieux_calendrier GROUP BY day_type ORDER BY day_type"
            )
            distribution = cur.fetchall()
        logger.info("Total en DB : %d", total)
        for day_type, n in distribution:
            logger.info("  %s : %d", day_type, n)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
