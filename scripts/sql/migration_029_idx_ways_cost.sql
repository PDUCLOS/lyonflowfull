-- =============================================================================
-- Migration 029 — Index pgRouting osm.ways (cold start perfo) (Sprint 20 P2.1)
-- =============================================================================
-- Date        : 2026-06-22
-- Version     : v0.11.0 (cible)
-- Branche     : main
-- Prérequis   : Sprint 18 (migration 026 + 027 + 028b) déployé
--
-- Contexte :
-- Bench cold start du 2026-06-22 (cf. docs/NEXT_STEPS_PGROUTING.md) :
--   - Court (2 km)  : 8.8s
--   - Moyen (6 km)   : 7.7s
--   - Long (12 km)   : 21.0s
-- Cible p95 < 150ms (cache applicatif Streamlit absorbe pour l'UX, mais
-- le cold start reste lent). Cause identifiée : full scan sur osm.ways
-- (~100k rows) pour lire cost/reverse_cost.
--
-- Solution : 2 index B-tree sur cost et reverse_cost. Dijkstra lit ces
-- colonnes en permanence pour calculer le shortest path pondéré par le
-- trafic temps réel. Index = lookup O(log n) au lieu de O(n).
--
-- Idempotent : CREATE INDEX IF NOT EXISTS + CONCURRENTLY pour ne pas locker
-- la table pendant la création (~30s sur 100k rows). CONCURRENTLY ne
-- peut pas être dans une transaction.
-- =============================================================================


-- Index 1 : cost (sens aller)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ways_cost
    ON osm.ways (cost)
    WHERE cost > 0;

-- Index 2 : reverse_cost (sens inverse, pour routing bidirectionnel)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ways_reverse_cost
    ON osm.ways (reverse_cost)
    WHERE reverse_cost > 0;

-- Note : on filtre WHERE cost > 0 car les arêtes avec cost = 0 (non
-- calculables) ne sont pas utilisées par Dijkstra. Ça réduit la taille
-- de l'index et accélère le lookup.
