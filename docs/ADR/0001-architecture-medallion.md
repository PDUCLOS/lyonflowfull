# ADR-0001 : Architecture Medallion (Bronze/Silver/Gold)

## Statut
Accepté (2026-06-06)

## Contexte
Nous avions besoin d'une architecture data pour ingérer 8 sources open
data, transformer en features ML-ready, et servir via API + dashboard.
Trois options considérées :
1. Lake (S3 + Athena + dbt)
2. Warehouse unique (PostgreSQL + PostGIS)
3. **Medallion (Bronze/Silver/Gold) sur PostgreSQL** ✅

## Décision
Architecture Medallion en 3 couches sur PostgreSQL 16 + PostGIS :
- **Bronze** : raw JSONB immutable + fetched_at
- **Silver** : dédup, géo, normalisé
- **Gold** : features ML + prédictions + analytique

## Conséquences

### Positives
- ✅ SQL familier (pas de nouveau tool)
- ✅ PostGIS pour la géo (capteurs, zones)
- ✅ Pas de coût supplémentaire (VPS existant)
- ✅ psycopg2 pur (compatible Airflow)
- ✅ Idempotent (UPSERT partout)

### Négatives
- ⚠️ Pas de streaming (batch uniquement)
- ⚠️ 1 seule machine (pas de scaling horizontal)
- ⚠️ Backup volumineux (Postgres + JSONB)

## Alternatives écartées

### Lake (S3 + Athena)
- ❌ Coût supplémentaire
- ❌ Latence requêtes SQL
- ❌ Pas nécessaire à notre échelle

### MongoDB / Cassandra
- ❌ Pas adapté aux features tabulaires
- ❌ Pas de PostGIS équivalent
