# Opérations finales — Déploiement v0.7.0+ (2026-06-19)

> Checklist complète pour finaliser le déploiement. Ordre séquentiel.

---

## Étape 0 — Commit local (avant déploiement)

2 fichiers modifiés non commités :

```bash
git add src/data/airflow_client.py dashboard/components/widgets/pro_tcl/pipeline_management.py
git commit -m "feat(airflow): boutons Clear/MarkFailed dans Pro_6 pour DAGs stuck"
```

**Contenu** :
- `airflow_client.py` : +`clear_stuck_dag_run()`, +`mark_dag_run_failed()`, +`last_dag_run_id`
- `pipeline_management.py` : boutons conditionnels (Clear/Fail pour running, Clear/Trigger pour failed)

---

## Étape 1 — Déployer sur VPS

```bash
make deploy-vps
```

> Déploie tout : commits `70678b0` → `a16d9cb` + le commit ci-dessus.
> Résout d'un coup : identifiants SYTRAL bruts, legacy cards, HTML escape, traductions FR, bouton profil, cause_analysis HTML, None→"—" drift.

**Vérification post-deploy** :
```bash
./scripts/healthcheck-vps.sh
```
- [ ] Sidebar affiche `v0.7.0` (ou supérieur)
- [ ] `</div>` ne leak plus sur page d'accueil ni Pro_6

---

## Étape 2 — Appliquer migration SQL (sur VPS)

```bash
ssh lyonflow@51.83.159.224
docker exec -i lyonflow-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB \
  -f /opt/lyonflow/scripts/sql/migration_15_aggregate_line_ref.sql
```

Ou si le fichier n'est pas monté dans le container :
```bash
cat scripts/sql/migration_15_aggregate_line_ref.sql | \
  docker exec -i lyonflow-postgres psql -U $POSTGRES_USER -d $POSTGRES_DB
```

**Vérifications** :
```sql
-- Doit retourner ~40 (pas 163)
SELECT COUNT(*) FROM gold.mv_line_kpis_live;

-- Doit retourner 0
SELECT COUNT(*) FROM gold.mv_line_kpis_live
WHERE line_ref LIKE '%_h%' AND line_ref LIKE '%:SYTRAL%';

-- Doit retourner 0 (cap à 100)
SELECT COUNT(*) FROM gold.mv_line_kpis_live WHERE charge_pct > 100;
```

- [ ] ~40 lignes physiques
- [ ] 0 suffixes `_hNN`
- [ ] 0 charge > 100%

---

## Étape 3 — Purger cache Python sur VPS

```bash
ssh lyonflow@51.83.159.224
docker exec lyonflow-airflow-scheduler \
  find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +
docker exec lyonflow-airflow-worker \
  find /opt/airflow -name __pycache__ -type d -exec rm -rf {} +
```

> Les DAGs chargent l'ancienne version sinon (gotcha Sprint 8+).

---

## Étape 4 — Débloquer DAGs via Pro_6

Aller sur `http://51.83.159.224/Pro_6_Pipeline_Mgmt` (mot de passe `demo2026`, profil Pro TCL).

- [ ] **`maintenance_backfill_dim_spatial_lat_lon`** (running depuis 7j) → bouton **⏹ Clear** ou **❌ Fail**
- [ ] **`purge_bronze`** (failed) → bouton **🔄 Clear** puis **▶️ Trigger**
- [ ] **`build_spatial_mapping`** (failed, 4.4h timeout) → bouton **🔄 Clear** puis **▶️ Trigger**

Si les boutons Clear/Fail n'apparaissent pas, fallback SSH :
```bash
ssh lyonflow@51.83.159.224
# Clear le DAG stuck
docker exec lyonflow-airflow-scheduler \
  airflow tasks clear maintenance_backfill_dim_spatial_lat_lon -y
# Mark failed
docker exec lyonflow-airflow-scheduler \
  airflow dags backfill maintenance_backfill_dim_spatial_lat_lon --reset-dagruns -y
```

---

## Étape 5 — Vérifier Airflow webserver

```bash
ssh lyonflow@51.83.159.224
docker logs --tail 50 lyonflow-airflow-webserver
docker restart lyonflow-airflow-webserver
```

Vérifier que `http://51.83.159.224/airflow/` charge l'UI Airflow.
Si le container n'existe pas, vérifier `docker-compose.yml` service `airflow-webserver`.

- [ ] Airflow UI accessible via `/airflow/`

---

## Étape 6 — Relancer modèles ML

```bash
ssh lyonflow@51.83.159.224
# XGBoost Speed
docker exec lyonflow-airflow-scheduler \
  airflow dags trigger dag_daily_speed_train

# Vélov
docker exec lyonflow-airflow-scheduler \
  airflow dags trigger retrain_velov

# Inférence (après training)
docker exec lyonflow-airflow-scheduler \
  airflow dags trigger dag_inference_xgboost
```

**Vérifications** :
```sql
-- Prédictions trafic récentes (< 1h)
SELECT COUNT(*) FROM gold.trafic_predictions
WHERE calculated_at > NOW() - INTERVAL '1 hour';

-- Prédictions Vélov
SELECT COUNT(*) FROM gold.velov_predictions;
```

- [ ] Prédictions trafic fraîches
- [ ] Prédictions Vélov présentes
- [ ] Pro_7 : XGB H+60min DISPO = ✅

---

## Étape 7 — Vérification visuelle VPS

Ouvrir `http://51.83.159.224` et vérifier chaque page Pro TCL :

| Page | Vérification | OK |
|------|--------------|----|
| Pro_1 | KPI table ~40 lignes, charge ≤ 100%, pas de ` ; 20h`, pas de legacy cards | [ ] |
| Pro_2 | Heatmap ~40 lignes sur Y, tableau sans index, valeurs arrondies | [ ] |
| Pro_3 | Matrice en français, cause_analysis en `<b>` pas `**`, pas de `</div>` | [ ] |
| Pro_5 | **Page supprimée** (ou stub documenté) | [ ] |
| Pro_6 | Boutons Clear/Fail fonctionnels, pas de `</div>` dans health checks | [ ] |
| Pro_7 | Drift sans `None → None`, pas de HTML brut, modèles dispo | [ ] |
| Accueil | Pas de `</div>` sur cards personas | [ ] |

---

## Étape 8 — TomTom (optionnel)

Si clé API disponible :
```bash
ssh lyonflow@51.83.159.224
# Ajouter dans .env :
echo 'TOMTOM_API_KEY=<ta_clé>' >> /opt/lyonflow/.env
docker restart lyonflow-airflow-scheduler
```

- [ ] `collect_tomtom_traffic` passe de "unknown" à "success"

---

## Étape 9 — Supprimer Pro_5_Export (code)

Pas encore fait. À faire dans un commit séparé :

```bash
# Fichiers à supprimer :
rm dashboard/pages/Pro_5_Export.py
rm dashboard/components/widgets/pro_tcl/saeiv_export.py
rm dashboard/components/widgets/pro_tcl/export_button.py

# Mettre à jour :
# - dashboard/components/widgets/pro_tcl/__init__.py (retirer imports)
# - tests/persona/test_pro_tcl_widgets.py (retirer Pro_5 des assertions)

git add -A && git commit -m "feat(pro_tcl): suppression Pro_5_Export (page stub non fonctionnelle)"
```

---

## Résumé séquentiel

| # | Action | Lieu | Durée |
|---|--------|------|-------|
| 0 | Commit local (Clear/Fail buttons) | Local | 1 min |
| 1 | `make deploy-vps` | Local | 3 min |
| 2 | Migration 15 SQL | VPS (SSH) | 2 min |
| 3 | Purger `__pycache__` Airflow | VPS (SSH) | 1 min |
| 4 | Clear DAGs stuck via Pro_6 | Browser | 2 min |
| 5 | Restart airflow-webserver | VPS (SSH) | 1 min |
| 6 | Trigger modèles ML | VPS (SSH) | 5 min |
| 7 | Vérification visuelle | Browser | 10 min |
| 8 | TomTom (optionnel) | VPS (SSH) | 2 min |
| 9 | Supprimer Pro_5 (code) | Local | 5 min |
| | **Total** | | **~30 min** |
