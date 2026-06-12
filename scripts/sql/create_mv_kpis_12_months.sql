-- Sprint 11: mv_kpis_12_months
-- KPI mensuels sur 12 mois glissants : trips, vitesse moyenne, précision prédiction, indice congestion
-- Schéma adapté aux colonnes réelles : fact_traffic_series (timestamp, node_idx, properties_vitesse)
-- et predictions_vs_actuals (target_at, axis_key, speed_actual, speed_pred)

CREATE MATERIALIZED VIEW gold.mv_kpis_12_months AS
WITH monthly AS (
  SELECT
    date_trunc('month', target_at) AS month,
    axis_key AS channel_id,
    COUNT(*) AS total_trips,
    AVG(speed_actual) AS avg_speed_kmh,
    AVG(ABS(speed_actual - speed_pred) / NULLIF(speed_actual, 0) * 100) AS prediction_accuracy
  FROM gold.predictions_vs_actuals
  WHERE target_at >= CURRENT_DATE - INTERVAL '12 months'
  GROUP BY 1, 2
),
percentiles AS (
  SELECT
    channel_id,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY avg_speed_kmh) AS p95,
    PERCENTILE_CONT(0.05) WITHIN GROUP (ORDER BY avg_speed_kmh) AS p05
  FROM monthly
  GROUP BY channel_id
)
SELECT
  m.month,
  m.channel_id,
  m.total_trips,
  ROUND(m.avg_speed_kmh::numeric, 3) AS avg_speed_kmh,
  ROUND(m.prediction_accuracy::numeric, 3) AS prediction_accuracy,
  ROUND((p.p95 / NULLIF(p.p05, 0))::numeric, 3) AS congestion_index
FROM monthly m
JOIN percentiles p ON p.channel_id = m.channel_id
ORDER BY m.month DESC, m.channel_id;

-- Index unique requis pour REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS mv_kpis_12_months_month_channel_idx
    ON gold.mv_kpis_12_months (month, channel_id);
