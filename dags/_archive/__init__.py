"""DAGs archivés — non chargés par Airflow.

Ce package contient les anciennes versions de DAGs qui ont été remplacées
mais conservées pour traçabilité/historique. Airflow ne doit PAS scanner
ce dossier : il est volontairement placé en dehors du DAG folder
(configuré via ``dags_folder`` dans airflow.cfg).

DAGs archivés :
- ``_disabled_dag_live_speed_retrain.py`` : version Sprint 9+ remplacée
  par ``dag_live_speed_retrain.py`` (Sprint VPS-5, baseline 4 horizons).
  Conservée ici pour archive — NE PAS réactiver sans avoir résolu
  le conflit de dag_id (cf. AUDIT_INTEGRATION_LIVE.md § 1.2.1).
"""
