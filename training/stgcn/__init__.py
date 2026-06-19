"""ST-GCN package — modèle, dataset, training loop.

Modules :
    dataset  — chargeur de séries temporelles gold.fact_traffic_series
    model    — SpatioTemporalGCN (GRU + 2x GCNConv + skip connections)
    train    — boucle d'entraînement + MLflow tracking
    train_cli — entrypoint CLI appelé par Airflow (dag_daily_gnn_retrain)
"""
