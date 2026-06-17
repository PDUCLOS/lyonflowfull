"""Debug: inspect gold.traffic_features_live values.

Useful to validate that the silver→gold transform produces sensible
speed values (no negative speeds, speeds within reasonable bounds,
vitesse_limite_kmh populated, etc.).

Usage (depuis la racine du repo) :
    python scripts/debug/query_traffic_gold.py

Sortie :
    - 20 premières lignes de gold.traffic_features_live
    - Agrégat (avg, min, max) sur toute la table

Si la DB est down, le script affiche l'erreur et sort avec code 1.
"""

import pandas as pd

from src.db.connection import execute_query


def main() -> int:
    try:
        rows = execute_query(
            "SELECT speed_kmh, vitesse_limite_kmh "
            "FROM gold.traffic_features_live LIMIT 20",
            (),
        )
        df = pd.DataFrame(rows)
        print("Gold speed values (first 20 rows):")
        print(df)

        rows2 = execute_query(
            "SELECT AVG(speed_kmh) AS avg, "
            "       MIN(speed_kmh) AS min, "
            "       MAX(speed_kmh) AS max, "
            "       COUNT(*) AS n "
            "FROM gold.traffic_features_live",
            (),
        )
        print("\nAggregate:")
        print(pd.DataFrame(rows2))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
