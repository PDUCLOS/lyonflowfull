# LyonFlowFull — Data Governance & RGPD

## Principes

LyonFlowFull traite **uniquement des données ouvertes** (Grand Lyon,
Open-Meteo, Open data.gouv) et **aucune donnée personnelle nominative**.

Les seules données potentiellement identifiantes :
- Adresse IP des utilisateurs (hashée SHA256)
- User-Agent des navigateurs (hashé SHA256)
- Identifiants hashés des comptes Pro TCL / Élu (bcrypt)

## Conformité RGPD

### Article 5 — Minimisation

✅ LyonFlowFull ne collecte **que** des données open data publiques.
Les comptes Pro TCL / Élu sont strictement techniques (auth requise).

### Article 6 — Licéité du traitement

✅ Base légale : **intérêt légitime** (service public mobilité).
✅ Pas de traitement commercial, publicitaire, ou de profilage.

### Article 7 — Consentement

✅ Endpoint `POST /api/v1/rgpd/request` pour demandes utilisateur
(rgpd.data_subject_requests table)
✅ Table `rgpd.user_consents` pour tracer consentement explicite si besoin
✅ Aucun cookie de tracking (Streamlit cookies techniques uniquement)

### Article 15 — Droit d'accès

```
POST /api/v1/rgpd/request
Content-Type: application/json
{
  "user_identifier": "sha256-hash-of-something",
  "request_type": "access"
}
```

→ Délai légal : 30 jours
→ Réponse : JSON avec données utilisateur (vide en pratique)

### Article 17 — Droit à l'effacement

```
POST /api/v1/rgpd/request
{
  "user_identifier": "sha256-hash",
  "request_type": "deletion"
}
```

→ Purge manuelle par l'admin dans les 30 jours

### Article 20 — Portabilité

```
POST /api/v1/rgpd/request
{
  "user_identifier": "sha256-hash",
  "request_type": "portability"
}
```

→ Export des données au format JSON

### Article 30 — Registre des traitements

Toutes les actions sont loggées dans `rgpd.audit_log` :

```sql
SELECT event_time, actor, action, resource_type, resource_id, details
FROM rgpd.audit_log
ORDER BY event_time DESC
LIMIT 100;
```

### Article 32 — Sécurité

✅ Mots de passe hashés bcrypt
✅ SQL paramétré (pas d'injection)
✅ HTTPS recommandé (Let's Encrypt)
✅ Containers non-root (USER appuser)
✅ Audit log immutable
✅ Rétention configurable (purge Bronze 7-45j)

## Anonymisation

Toutes les valeurs potentiellement identifiantes sont hashées :

| Type | Méthode | Réversible ? |
|------|---------|--------------|
| IP | SHA256 truncated (32 chars) | Non (one-way) |
| User-Agent | SHA256 truncated | Non |
| user_identifier (compte) | bcrypt | Non |
| Identifiants techniques | SHA256 | Non |

```python
# src/rgpd/service.py
def _hash(value: str) -> str:
    """Hash SHA256 anonymisé."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
```

## Rétention

| Table | Rétention | Purge DAG |
|-------|-----------|-----------|
| `bronze.trafic_boucles` | 45j | quotidien 03h |
| `bronze.velov` | 14j | quotidien 03h |
| `bronze.tcl_vehicles` | 7j | quotidien 03h |
| `bronze.meteo` | 365j | quotidien 03h |
| `bronze.air_quality` | 365j | quotidien 03h |
| `bronze.chantiers` | 365j | quotidien 03h |
| `silver.*` | ∞ (feature engineering) | manuel |
| `gold.trafic_predictions` | 48h (rétention courte) | quotidien 03h |
| `gold.predictions_vs_actuals` | 365j | annuel |
| `rgpd.audit_log` | 365j | annuel |
| `rgpd.user_consents` | jusqu'à expiration consent | manuel |
| `rgpd.data_subject_requests` | 2 ans (preuve légale) | annuel |

## Data Dictionary

Maintenu automatiquement dans `governance.data_dictionary` :

```sql
SELECT schema_name, table_name, column_name, data_type, pii_level, description
FROM governance.data_dictionary
ORDER BY schema_name, table_name;
```

Export Markdown : `src/governance/data_dictionary.py::export_table_schema_documentation()`

## Lineage

Chaque transformation Bronze→Silver→Gold est tracée :

```sql
SELECT source_table, target_table, transformation, dag_id, updated_at
FROM governance.lineage;
```

Exemple :
```
bronze.trafic_boucles → silver.trafic_boucles_clean
  via: Parse JSON + dédup + géométrie
  by:  dag transform_bronze_to_silver

silver.trafic_boucles_clean → gold.traffic_features_live
  via: lags + deltas + temporel + météo
  by:  dag transform_silver_to_gold
```

## Audit Log (Article 30)

Toutes les actions sont tracées :

```sql
-- Qui a fait quoi quand
SELECT event_time, actor, action, resource_type, resource_id
FROM rgpd.audit_log
ORDER BY event_time DESC
LIMIT 100;

-- Détails d'une action spécifique
SELECT details
FROM rgpd.audit_log
WHERE action = 'login_failed'
ORDER BY event_time DESC
LIMIT 20;
```

## Sécurité applicative

### Mots de passe (comptes Pro TCL / Élu)

```python
# Hash à la création
import bcrypt
password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

# Vérification au login
bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
```

### API key

Header `X-API-Key: <LYONFLOW_API_KEY>` requis sauf pour :
- `GET /health` (public)
- `POST /api/v1/rgpd/request` (public, droit utilisateur)
- `POST /api/v1/auth/login` (public)

### Rate limiting (Nginx)

- 10 req/s sur `/api/`
- 5 req/min sur login (à implémenter)

### Container security

- USER appuser (non-root)
- Filesystem read-only sur /app (à venir)
- Capabilities réduites (à venir)

## Procédure en cas de violation

1. **Notification CNIL** sous 72h (si risque élevé pour les droits)
2. **Notification utilisateurs** si impact direct
3. **Investigation** via audit_log
4. **Remédiation** (patch, revoke clés, etc.)
5. **Documentation** de l'incident

## DPO (Data Protection Officer)

Pour toute demande RGPD : **dpo@lyonflowfull.fr**
Délai légal de réponse : 30 jours.

## Référence

- RGPD (UE 2016/679) : https://www.cnil.fr/fr/reglement-europeen-protection-donnees
- LIL (Loi Informatique et Libertés) : https://www.cnil.fr/fr/la-loi-informatique-et-les-libertes
- Code des bonnes pratiques data : https://github.com/PDUCLOS/lyonflowfull/blob/main/docs/DATA_GOVERNANCE.md
