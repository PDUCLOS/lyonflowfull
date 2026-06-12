# Sprint 10 — LyonFlow : Favoris Multimodaux

**Date** : 2026-06-12
**Branche** : `sprint10-favorites`
**Statut** : ✅ Terminé

---

## Résumé

Sprint 10 a livré deux fonctionnalités complémentaires :

1. **Track DB** — persistance SQL des favoris utilisateur dans `public.user_favorites`, avec API CRUD complète
2. **Track UI** — recommandations multimodales alternatives pour chaque favori, affichées dans le widget Streamlit

---

## Tables SQL

### `public.user_favorites`

```sql
CREATE TABLE public.user_favorites (
    id          VARCHAR(50)   NOT NULL,
    user_id     VARCHAR(100)  NOT NULL DEFAULT 'default_user',
    nom         VARCHAR(255) NOT NULL,
    origin      VARCHAR(255) NOT NULL,
    destination VARCHAR(255) NOT NULL,
    origin_coords  VARCHAR(50),
    dest_coords   VARCHAR(50),
    mode_pref   VARCHAR(10)  NOT NULL,
    line_ref    VARCHAR(20),
    temps_min   INTEGER,
    alert       BOOLEAN      NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, id)
);
```

**4 enregistrements seedés (default_user)** :

| id | Nom | Origin | Destination | Mode | Durée |
|----|-----|--------|-------------|------|-------|
| fav_1 | 🏠→💼 | Maison | Boulot | M A | 22min |
| fav_2 | 💼→🏠 | Boulot | Maison | M A | 22min |
| fav_3 | 🏠→🛒 | Maison | Carrefour | C17 | 35min |
| fav_4 | 💼→🏋️ | Boulot | Salle | T1 | 18min |

---

## Endpoints API

### CRUD (4 endpoints)

| Méthode | Path | Description |
|---------|------|-------------|
| `GET` | `/api/favorites` | Liste tous les favoris (filtré par user_id) |
| `POST` | `/api/favorites` | Crée un favori (génère UUID) |
| `PATCH` | `/api/favorites/{id}/alert` | Toggle alerte actif/inactif |
| `DELETE` | `/api/favorites/{id}` | Supprime un favori |

### Bonus (1 endpoint)

| Méthode | Path | Description |
|---------|------|-------------|
| `GET` | `/api/favorites/{id}/alternatives` | Retourne 4 alternatives multimodales (velov, bus, walk, vtc) avec scores de confiance |

**Tests curl** (API key: `8844c8687ab0fa13a0ed81dcf2489808ac477b50af8176c9b115955c95dd3f16`) :
```
GET  /api/favorites                   → 200, 4 favoris JSON
POST /api/favorites                   → 201, UUID généré
PATCH /api/favorites/{id}/alert       → 200, alert togglé
DELETE /api/favorites/{id}            → 204
GET  /api/favorites/fav_1/alternatives → 200, 4 alternatives (velov:25min/1.0, bus:14min/0.8, vtc:7min/0.75, walk:17min/0.26)
```

---

## Fichiers modifiés/créés

### Track DB

| Fichier | Action |
|---------|--------|
| `scripts/sql/create_user_favorites.sql` | créé |
| `scripts/sql/seed_user_favorites.sql` | créé |
| `src/api/favorites.py` | créé (router CRUD) |
| `src/api/main.py` | modifié (include_router) |
| `src/data/data_loader.py` | modifié (load_favorites DB-first) |

### Track UI

| Fichier | Action |
|---------|--------|
| `src/routing/recommendation.py` | créé (~487 lignes — moteur recommandations) |
| `src/api/favorites.py` | modifié (+52 lignes endpoint alternatives) |
| `dashboard/components/widgets/usager/favorite_list.py` | modifié (+152 insertions) |
| `docker-compose.yml` | modifié (rebuild lyonflow-api) |

---

## Commits

| Track | Commit | Message |
|-------|--------|---------|
| user_favorites-db | `19f650c9` | Tables, CRUD API, load_favorites() |
| reco-multimodale | `91acb54f` | Recommandations multimodales + endpoint alternatives |
| **sprint10-summary** | _(ce commit)_ | sprint10-summary.md |

---

## Recommandations Sprint 11

### 1. Authentification — `user_id` via JWT `sub`

**Problème** : `CURRENT_USER_ID = "default_user"` est hardcodé. Tous les utilisateurs partagent les mêmes favoris.

**Solution** :
- Lire le header `Authorization: Bearer <JWT>` dans les endpoints `/api/favorites`
- Extraire le claim `sub` du payload JWT comme `user_id`
- Filtrer toutes les queries par `user_id`
- Ajouter un endpoint `/api/auth/me` pour tester le token

**Fichiers impactés** : `src/api/favorites.py`, middleware JWT (via FastAPI Depends ou décorateur)

---

### 2. KPIs 12 mois — Persona Élu

**Problème** : Le persona "Élu territorial" (TCL pass, déplacements domicile-travail daily, alerte trafic) a besoin de métriques de performance sur 12 mois glissants.

**Solution** :
- Ajouter une table `public.trip_history` (date, origin, dest, mode_used, temps_reel, delay_min, alternatives_scores)
- Calculer métriques mensuelles : taux de respect horaire, temps moyen par mode, nombre d'alertes déclenchées, économie CO2 vs voiture
- Dashboard Streamlit dédié (section "Mes Performances") : graphiques 12 mois, comparatif velov vs TCL vs driving

**Fichiers impactés** : nouveau `scripts/sql/create_trip_history.sql`, enrichissement `load_favorites()` pour log les trajets, widget Streamlit dédié

---

## Notes techniques

- **Container API** : image reconstruite à 19:07 UTC (sha256:350113a2b0e...), les 5 endpoints sont actifs
- **DB fallback** : `load_favorites()` en mode prod → DB-first → lève `DashboardDataError` si down → mock fallback
- **Coords** : hardcodées à (45.7600, 4.8500) pour Sprint 10. Sprint 11 : geocoder origin/dest names depuis `user_favorites`
- **Push GitHub** : clé de déploiement read-only — code sur VPS uniquement
- **Vélov réel** : 29 vélos à Part-Dieu utilisés pour le calcul des alternatives