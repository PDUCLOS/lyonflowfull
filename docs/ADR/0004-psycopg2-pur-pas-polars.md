# ADR-0004 : psycopg2 pur (pas de Polars) dans Airflow

## Statut
Accepté (2026-06-06)

## Contexte
Les transformations Bronze→Silver→Gold pourraient utiliser :
1. Polars (rapide, DataFrame en mémoire)
2. **psycopg2 pur (SQL)** ✅
3. pandas + SQLAlchemy

## Décision
psycopg2 pur pour toutes les transformations.

## Rationale
- ✅ Compatible avec l'image Airflow de base (pas de dep supplémentaire)
- ✅ Streaming natif (cur.execute itère sur la DB)
- ✅ RAM bornée (pas de chargement en mémoire)
- ✅ SQL lisible et auditable
- ⚠️ Plus verbeux que pandas
- ⚠️ Pas d'agrégations complexes sans SQL

## Quand reconsidérer
- Si la taille d'un batch Bronze dépasse 10M rows
- Si l'équipe devient pandas-fluent
- Si on a besoin d'agrégations window functions avancées
