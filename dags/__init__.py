"""DAGs package — Airflow DAGs.

Sous-dossiers :
- bronze/ : collect_bronze
- transforms/ : bronze→silver, silver→gold
- ml/ : retrain XGBoost (le GNN est archivé dans archive/legacy/gnn/)
- maintenance/ : quality, purge, drift
- utils/ : helpers, alerting
"""
